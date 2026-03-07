"""Users API: readiness dashboard, etc."""

import uuid as uuid_pkg
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.common.http_response_model import CommonResponse
from app.models import JobPosting, Message, PrepSession, Resume, User
from app.services.readiness_aggregator import compute_combined_readiness
from app.services.skill_gap_service import analyze_skill_gap
from app.services.cv_scoring import score_cv_from_raw_text

router = APIRouter()

LAST_N_SESSIONS = 5


async def _compute_session_readiness(db: AsyncSession, session_id: uuid_pkg.UUID) -> Optional[float]:
    """Compute readiness as average of FEEDBACK message scores."""
    result = await db.execute(
        select(Message).where(
            Message.session_id == session_id,
            Message.type == "FEEDBACK",
        )
    )
    messages = list(result.scalars().all())
    scores: list[float] = []
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
    cv_score: Optional[float] = None
    gap_severity: Optional[str] = None

    if resume_id:
        resume = await db.get(Resume, resume_id)
        if resume is None or resume.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Resume not found.")

        if (resume.raw_text or "").strip():
            try:
                result = await score_cv_from_raw_text(resume.raw_text)
                cv_score = result.score
            except ValueError:
                pass  # CV scoring disabled or failed; continue without cv_score

        if job_posting_id:
            job = await db.get(JobPosting, job_posting_id)
            if job is None or job.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="Job posting not found.")
            gap_result = analyze_skill_gap(
                resume_entities=resume.entities or {},
                job_entities=job.entities or {},
            )
            gap_severity = gap_result.get("severity")

    # Session average
    result = await db.execute(
        select(PrepSession)
        .where(PrepSession.user_id == current_user.id)
        .order_by(PrepSession.updated_at.desc())
        .limit(LAST_N_SESSIONS)
    )
    sessions = list(result.scalars().all())
    session_scores: list[float] = []
    for s in sessions:
        rs = await _compute_session_readiness(db, s.id)
        if rs is not None:
            session_scores.append(rs)
    session_avg: Optional[float] = round(sum(session_scores) / len(session_scores), 2) if session_scores else None

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
