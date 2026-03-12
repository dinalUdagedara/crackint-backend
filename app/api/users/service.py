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
            "job_posting_id": s.job_posting_id,
        })
    return items


# --- Home summary card builders ---

async def get_jump_back_in_items(
    db: AsyncSession,
    current_user: User,
    limit: int = 5,
) -> List[Dict]:
    """
    Build items for the Jump Back In card: recent sessions with title and session_id.
    Returns list of dicts suitable for HomeSummaryItem (title, session_id, href).
    """
    result = await db.execute(
        select(PrepSession)
        .where(PrepSession.user_id == current_user.id)
        .order_by(PrepSession.updated_at.desc())
        .limit(limit)
    )
    sessions = list(result.scalars().all())
    items: List[Dict] = []
    for s in sessions:
        summary = s.summary or {}
        title = summary.get("title") if isinstance(summary, dict) else None
        if not title or not str(title).strip():
            title = "Practice session"
        items.append({
            "title": str(title).strip(),
            "session_id": str(s.id),
            "href": f"/sessions/{s.id}",
        })
    return items


async def get_refine_cv_items(
    db: AsyncSession,
    current_user: User,
    max_items: int = 5,
) -> List[Dict]:
    """
    Build items for the Refine CV card from skill-gap suggestions across resume+job pairs.
    Returns list of dicts suitable for HomeSummaryItem.
    """
    resumes_result = await db.execute(
        select(Resume).where(Resume.user_id == current_user.id).limit(3)
    )
    resumes = list(resumes_result.scalars().all())
    jobs_result = await db.execute(
        select(JobPosting).where(JobPosting.user_id == current_user.id).limit(5)
    )
    jobs = list(jobs_result.scalars().all())

    if not resumes or not jobs:
        return [{
            "title": "Upload a resume and add a job to get tailored suggestions.",
            "action_type": "open_cv",
        }]

    items: List[Dict] = []
    for resume in resumes:
        for job in jobs:
            if len(items) >= max_items:
                break
            result = analyze_skill_gap(
                resume_entities=resume.entities or {},
                job_entities=job.entities or {},
            )
            for suggestion in (result.get("suggestions") or []):
                if len(items) >= max_items:
                    break
                if not suggestion or not str(suggestion).strip():
                    continue
                items.append({
                    "title": str(suggestion).strip(),
                    "resume_id": str(resume.id),
                    "job_posting_id": str(job.id),
                    "href": f"/resumes/{resume.id}",
                })
        if len(items) >= max_items:
            break

    if not items:
        items = [{
            "title": "Your CV aligns well with your saved jobs. Add more jobs for new suggestions.",
            "action_type": "open_cv",
        }]
    return items


def _job_label_from_entities(entities: Optional[Dict]) -> str:
    """Derive a short human-readable job label from job posting entities."""
    if not entities or not isinstance(entities, dict):
        return "Job"
    titles = entities.get("JOB_TITLE") or entities.get("JOB_TITLE_REQUIRED") or []
    companies = entities.get("COMPANY") or []
    if isinstance(titles, list) and titles:
        title_part = titles[0] if titles else "Job"
    else:
        title_part = "Job"
    if isinstance(companies, list) and companies:
        return f"{title_part} ({companies[0]})"
    return str(title_part)


async def get_readiness_tracker_items(
    db: AsyncSession,
    current_user: User,
    limit: int = 5,
) -> List[Dict]:
    """
    Build items for the Readiness Tracker card from recent sessions with readiness scores.
    Enriches with job title when session has job_posting_id.
    Returns list of dicts suitable for HomeSummaryItem.
    """
    trend = await get_readiness_trend_data(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )
    items: List[Dict] = []
    for row in trend:
        session_id = row.get("session_id")
        score = row.get("readiness_score")
        session_title = row.get("title")
        job_posting_id = row.get("job_posting_id")

        if job_posting_id:
            job = await db.get(JobPosting, job_posting_id)
            if job and job.user_id == current_user.id:
                label = _job_label_from_entities(job.entities)
                title = f"Readiness for {label} is {score:.0f}%" if score is not None else f"Readiness for {label} — no score yet"
            else:
                label = session_title or "Session"
                title = f"Readiness: {label} — {score:.0f}%" if score is not None else f"Readiness: {label}"
        else:
            label = session_title or "Session"
            title = f"Readiness: {label} — {score:.0f}%" if score is not None else f"Readiness: {label}"

        item = {
            "title": title,
            "session_id": str(session_id),
            "href": f"/sessions/{session_id}",
        }
        if job_posting_id:
            item["job_posting_id"] = str(job_posting_id)
            item["href"] = f"/job-postings/{job_posting_id}"
        items.append(item)

    items.append({
        "title": "Start practice",
        "action_type": "start_session",
    })
    return items
