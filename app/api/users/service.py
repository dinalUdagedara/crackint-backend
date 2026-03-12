"""
Users API service: readiness dashboard logic.
Used by GET /users/me/readiness, /readiness/summary, and /readiness/trend.
"""

import uuid as uuid_pkg
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobPosting, Message, PrepSession, Resume, User
from app.services.cv_scoring import score_cv_from_raw_text
from app.services.skill_gap_service import analyze_skill_gap


async def compute_session_readiness(
    db: AsyncSession, session_id: uuid_pkg.UUID
) -> Optional[float]:
    """Compute readiness for a session as average of FEEDBACK message scores."""
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


async def get_cv_and_gap(
    db: AsyncSession,
    current_user: User,
    resume_id: Optional[uuid_pkg.UUID],
    job_posting_id: Optional[uuid_pkg.UUID],
) -> tuple[Optional[float], Optional[str]]:
    """
    Compute CV score and gap severity (if IDs provided and owned by user).
    Raises HTTPException 404 if resume_id or job_posting_id is invalid or not owned.
    """
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


async def get_recent_session_stats(
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
        difficulty_distribution: counts of QUESTION messages by difficulty (easy/medium/hard).
    """
    total_result = await db.execute(
        select(func.count()).select_from(PrepSession).where(PrepSession.user_id == current_user.id)
    )
    session_count_total = int(total_result.scalar_one() or 0)

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
        rs = await compute_session_readiness(db, s.id)
        if rs is not None:
            session_scores.append(rs)
        session_ids.append(s.id)

    session_count_with_scores = len(session_scores)
    session_avg: Optional[float] = (
        round(sum(session_scores) / len(session_scores), 2) if session_scores else None
    )

    # Difficulty is stored on QUESTION messages (when the question is generated), not on FEEDBACK.
    difficulty_distribution: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    if session_ids:
        msg_result = await db.execute(
            select(Message).where(
                Message.session_id.in_(session_ids),
                Message.type == "QUESTION",
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


async def get_readiness_trend_data(
    db: AsyncSession,
    user_id: uuid_pkg.UUID,
    limit: int,
) -> List[Dict]:
    """
    Return list of recent sessions with readiness score and metadata for trend charts.
    Each item: session_id, created_at (ISO str), mode, readiness_score, title.
    """
    result = await db.execute(
        select(PrepSession)
        .where(PrepSession.user_id == user_id)
        .order_by(PrepSession.created_at.desc())
        .limit(limit)
    )
    sessions = list(result.scalars().all())

    items: List[Dict] = []
    for s in sessions:
        readiness = await compute_session_readiness(db, s.id)
        summary = s.summary or {}
        try:
            title = summary.get("title")
        except AttributeError:
            title = None
        items.append({
            "session_id": s.id,
            "created_at": s.created_at.isoformat(),
            "mode": s.mode,
            "readiness_score": readiness,
            "title": title,
        })
    return items
