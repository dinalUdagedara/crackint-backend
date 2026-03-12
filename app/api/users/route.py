"""Users API: readiness dashboard, etc."""

import uuid as uuid_pkg
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.http_response_model import CommonResponse
from app.models import JobPosting, Message, PrepSession, Resume, User
from app.services.readiness_aggregator import compute_combined_readiness
from app.services.skill_gap_service import analyze_skill_gap
from app.services.cv_scoring import score_cv_from_raw_text

router = APIRouter()

# Default window for readiness calculations (number of recent sessions).
LAST_N_SESSIONS = 5


class ReadinessSummaryResponse(BaseModel):
    """Dashboard-friendly readiness summary for the current user."""

    combined_score: float = Field(..., description="Combined readiness score 0-100.")
    trend: str = Field(
        ...,
        description='Trend label from aggregator: "improving", "stable", or "declining".',
    )
    cv_score: Optional[float] = Field(
        default=None,
        description="CV score 0-100 if available, otherwise null.",
    )
    session_avg: Optional[float] = Field(
        default=None,
        description="Average readiness across recent sessions, if any.",
    )
    gap_severity: Optional[str] = Field(
        default=None,
        description="Skill-gap severity label if gap analysis was computed.",
    )
    session_count_total: int = Field(
        ...,
        description="Total number of prep sessions owned by the current user.",
    )
    session_count_with_scores: int = Field(
        ...,
        description="Number of sessions that have at least one FEEDBACK score.",
    )
    last_n_sessions: int = Field(
        ...,
        description="Number of recent sessions considered when computing session_avg and difficulty_distribution.",
    )
    difficulty_distribution: Dict[str, int] = Field(
        ...,
        description='Counts of FEEDBACK messages by difficulty in recent sessions, e.g. {"easy": 4, "medium": 7, "hard": 2}.',
    )


class ReadinessTrendItem(BaseModel):
    """Single point in the readiness trend over sessions."""

    session_id: uuid_pkg.UUID = Field(..., description="Prep session ID.")
    created_at: str = Field(
        ...,
        description="Session creation timestamp (ISO 8601).",
    )
    mode: str = Field(
        ...,
        description="Session mode, e.g. TARGETED, QUICK_PRACTICE, TUTOR_CHAT.",
    )
    readiness_score: Optional[float] = Field(
        default=None,
        description="Readiness score for this session if feedback scores exist.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional human-friendly session title from summary, if present.",
    )


async def _compute_session_readiness(db: AsyncSession, session_id: uuid_pkg.UUID) -> Optional[float]:
    """Compute readiness as average of FEEDBACK message scores."""
    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    messages = list(result.scalars().all())
    scores: List[float] = []
    for m in messages:
        raw = (m.meta or {}).get("score")
        if raw is not None:
            try:
                scores.append(float(raw))
            except (TypeError, ValueError):
                pass
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


async def _get_cv_and_gap(
    db: AsyncSession,
    current_user: User,
    resume_id: Optional[uuid_pkg.UUID],
    job_posting_id: Optional[uuid_pkg.UUID],
) -> tuple[Optional[float], Optional[str]]:
    """Compute CV score and gap severity (if IDs provided and owned by user)."""
    cv_score: Optional[float] = None
    gap_severity: Optional[str] = None

    if not resume_id:
        return cv_score, gap_severity

    resume = await db.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if (resume.raw_text or "").strip():
        try:
            result = await score_cv_from_raw_text(resume.raw_text)
            cv_score = result.score
        except ValueError:
            # CV scoring disabled or failed; continue without cv_score.
            pass

    if job_posting_id:
        job = await db.get(JobPosting, job_posting_id)
        if job is None or job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job posting not found.")
        gap_result = analyze_skill_gap(
            resume_entities=resume.entities or {},
            job_entities=job.entities or {},
        )
        gap_severity = gap_result.get("severity")

    return cv_score, gap_severity


async def _get_recent_session_stats(
    db: AsyncSession,
    current_user: User,
    last_n_sessions: int,
) -> tuple[Optional[float], int, int, Dict[str, int]]:
    """
    Compute session readiness aggregates and difficulty distribution over recent sessions.

    Returns:
        session_avg: mean readiness over recent sessions, or None.
        session_count_total: total sessions for this user.
        session_count_with_scores: number of sessions that contributed to session_avg.
        difficulty_distribution: counts of FEEDBACK messages by difficulty (easy/medium/hard).
    """
    # Total session count for the user.
    total_result = await db.execute(
        select(func.count()).select_from(PrepSession).where(PrepSession.user_id == current_user.id)
    )
    session_count_total = int(total_result.scalar_one() or 0)

    # Recent sessions limited by last_n_sessions.
    result = await db.execute(
        select(PrepSession)
        .where(PrepSession.user_id == current_user.id)
        .order_by(PrepSession.updated_at.desc())
        .limit(last_n_sessions)
    )
    sessions = list(result.scalars().all())

    session_scores: List[float] = []
    session_ids: List[uuid_pkg.UUID] = []
    for s in sessions:
        rs = await _compute_session_readiness(db, s.id)
        if rs is not None:
            session_scores.append(rs)
        session_ids.append(s.id)

    session_count_with_scores = len(session_scores)
    session_avg: Optional[float] = (
        round(sum(session_scores) / len(session_scores), 2) if session_scores else None
    )

    # Difficulty distribution from FEEDBACK messages over these recent sessions.
    difficulty_distribution: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    if session_ids:
        msg_result = await db.execute(
            select(Message).where(
                Message.session_id.in_(session_ids),
                Message.type == "FEEDBACK",
            )
        )
        messages = list(msg_result.scalars().all())
        for m in messages:
            meta = m.meta or {}
            diff_raw = meta.get("difficulty")
            if not diff_raw:
                continue
            d = str(diff_raw).lower()
            if d in difficulty_distribution:
                difficulty_distribution[d] += 1

    return session_avg, session_count_total, session_count_with_scores, difficulty_distribution


@router.get(
    "/me/readiness",
    response_model=CommonResponse[dict],
    name="Get combined readiness",
    summary="Get combined readiness score (CV + sessions + gap) for current user.",
)
async def get_my_readiness(
    resume_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional resume ID for CV score and gap analysis.",
    ),
    job_posting_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional job posting ID for gap analysis (requires resume_id).",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns combined readiness score aggregating:
    - CV score (if resume_id provided and CV scoring enabled)
    - Average of last N session readiness scores
    - Gap penalty (if resume_id and job_posting_id provided)
    """
    cv_score, gap_severity = await _get_cv_and_gap(
        db=db,
        current_user=current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )

    # Session average over the default LAST_N_SESSIONS window.
    session_avg, _total, _with_scores, _dist = await _get_recent_session_stats(
        db=db,
        current_user=current_user,
        last_n_sessions=LAST_N_SESSIONS,
    )

    combined, trend = compute_combined_readiness(
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
    )

    payload = {
        "combined_score": combined,
        "cv_score": cv_score,
        "session_avg": session_avg,
        "gap_severity": gap_severity,
        "trend": trend,
    }
    return CommonResponse(
        success=True,
        message="Readiness retrieved successfully",
        payload=payload,
    )


@router.get(
    "/me/readiness/trend",
    response_model=CommonResponse[List[ReadinessTrendItem]],
    name="Get readiness trend",
    summary="Get recent session readiness scores for the current user.",
)
async def get_my_readiness_trend(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of recent sessions to return.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a list of recent sessions with individual readiness scores and timestamps
    for plotting trends in the frontend.
    """
    result = await db.execute(
        select(PrepSession)
        .where(PrepSession.user_id == current_user.id)
        .order_by(PrepSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(result.scalars().all())

    items: List[ReadinessTrendItem] = []
    for s in sessions:
        readiness = await _compute_session_readiness(db, s.id)
        summary = s.summary or {}
        title = None
        try:
            # summary is stored as JSONB dict; be defensive.
            title = summary.get("title")  # type: ignore[assignment]
        except AttributeError:
            title = None
        item = ReadinessTrendItem(
            session_id=s.id,
            created_at=s.created_at.isoformat(),
            mode=s.mode,
            readiness_score=readiness,
            title=title,
        )
        items.append(item)

    return CommonResponse(
        success=True,
        message="Readiness trend retrieved successfully",
        payload=items,
    )


@router.get(
    "/me/readiness/summary",
    response_model=CommonResponse[ReadinessSummaryResponse],
    name="Get readiness summary",
    summary="Get readiness summary and aggregates for the current user (dashboard).",
)
async def get_my_readiness_summary(
    resume_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional resume ID for CV score and gap analysis.",
    ),
    job_posting_id: Optional[uuid_pkg.UUID] = Query(
        default=None,
        description="Optional job posting ID for gap analysis (requires resume_id).",
    ),
    last_n_sessions: int = Query(
        default=LAST_N_SESSIONS,
        ge=1,
        le=50,
        description="Number of recent sessions to consider for session_avg and difficulty distribution.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a dashboard-friendly readiness summary aggregating:
    - Combined readiness score and trend
    - CV score and gap severity (if resume/job IDs provided)
    - Session averages and counts
    - Difficulty distribution over recent sessions
    """
    cv_score, gap_severity = await _get_cv_and_gap(
        db=db,
        current_user=current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )

    session_avg, session_count_total, session_count_with_scores, difficulty_distribution = (
        await _get_recent_session_stats(
            db=db,
            current_user=current_user,
            last_n_sessions=last_n_sessions,
        )
    )

    combined, trend = compute_combined_readiness(
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
    )

    payload = ReadinessSummaryResponse(
        combined_score=combined,
        trend=trend,
        cv_score=cv_score,
        session_avg=session_avg,
        gap_severity=gap_severity,
        session_count_total=session_count_total,
        session_count_with_scores=session_count_with_scores,
        last_n_sessions=last_n_sessions,
        difficulty_distribution=difficulty_distribution,
    )
    return CommonResponse(
        success=True,
        message="Readiness summary retrieved successfully",
        payload=payload,
    )
