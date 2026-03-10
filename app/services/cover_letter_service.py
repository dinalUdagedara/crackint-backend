"""
Cover letter service:
- Fetch resume and job posting records.
- Build LLM context.
- Call cover letter agent.
- Upsert CoverLetter row and optionally create a Message in the session.
"""

import logging
import uuid as uuid_pkg
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.cover_letter_agent import CoverLetterContext, generate_cover_letter
from app.models import CoverLetter, JobPosting, Message, PrepSession, Resume, User


logger = logging.getLogger(__name__)


async def _get_own_resume(
    db: AsyncSession,
    resume_id: uuid_pkg.UUID,
    current_user: User,
) -> Resume:
    resume = await db.get(Resume, resume_id)
    if resume is None or resume.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Resume not found.")
    return resume


async def _get_own_job_posting(
    db: AsyncSession,
    job_posting_id: uuid_pkg.UUID,
    current_user: User,
) -> JobPosting:
    job = await db.get(JobPosting, job_posting_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    return job


async def _get_own_prep_session(
    db: AsyncSession,
    session_id: uuid_pkg.UUID,
    current_user: User,
) -> PrepSession:
    session = await db.get(PrepSession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Prep session not found.")
    return session


async def _summarize_session_for_cover_letter(
    db: AsyncSession,
    prep_session: PrepSession,
) -> Optional[str]:
    """
    Produce a short textual summary from existing PrepSession.summary and messages.
    Keep it lightweight to avoid extra LLM calls.
    """
    parts: list[str] = []
    summary = prep_session.summary or {}
    title = summary.get("title")
    strengths = summary.get("strengths")
    areas = summary.get("areas_for_improvement")
    if title:
        parts.append(f"Session title: {title}")
    if strengths:
        parts.append(f"Strengths: {strengths}")
    if areas:
        parts.append(f"Areas for improvement: {areas}")

    if not parts:
        return None
    return " | ".join(parts)


async def generate_and_store_cover_letter(
    db: AsyncSession,
    current_user: User,
    *,
    resume_id: Optional[uuid_pkg.UUID] = None,
    job_posting_id: Optional[uuid_pkg.UUID] = None,
    session_id: Optional[uuid_pkg.UUID] = None,
    tone: Optional[str] = None,
    length: Optional[str] = None,
    user_notes: Optional[str] = None,
    create_session_message: bool = True,
) -> CoverLetter:
    """
    Orchestrate cover letter generation and persistence.

    At least (resume_id and job_posting_id) or session_id must be provided.
    If session_id is provided, missing resume/job IDs are inferred from the session.
    """
    if not resume_id and not job_posting_id and not session_id:
        raise HTTPException(
            status_code=400,
            detail="Must provide resume_id and job_posting_id or a session_id.",
        )

    prep_session: Optional[PrepSession] = None
    if session_id:
        prep_session = await _get_own_prep_session(db, session_id, current_user)
        resume_id = resume_id or prep_session.resume_id
        job_posting_id = job_posting_id or prep_session.job_posting_id

    if not resume_id or not job_posting_id:
        raise HTTPException(
            status_code=400,
            detail="Both resume and job posting must be linked to generate a cover letter.",
        )

    resume = await _get_own_resume(db, resume_id, current_user)
    job = await _get_own_job_posting(db, job_posting_id, current_user)

    session_summary: Optional[str] = None
    if prep_session is not None:
        session_summary = await _summarize_session_for_cover_letter(db, prep_session)

    context = CoverLetterContext(
        resume_entities=resume.entities or {},
        job_entities=job.entities or {},
        resume_text=resume.raw_text,
        job_text=job.raw_text,
        tone=tone or "formal",
        length=length or "medium",
        user_notes=user_notes,
        session_summary=session_summary,
    )

    logger.info(
        "Cover letter: generating for user=%s resume=%s job=%s session=%s tone=%s length=%s",
        current_user.id,
        resume.id,
        job.id,
        prep_session.id if prep_session else None,
        context.tone,
        context.length,
    )

    content = await generate_cover_letter(context)

    # Upsert CoverLetter for (user_id, resume_id, job_posting_id)
    stmt = select(CoverLetter).where(
        CoverLetter.user_id == current_user.id,
        CoverLetter.resume_id == resume.id,
        CoverLetter.job_posting_id == job.id,
    )
    result = await db.execute(stmt)
    existing = result.scalars().one_or_none()

    if existing is None:
        cover = CoverLetter(
            user_id=current_user.id,
            resume_id=resume.id,
            job_posting_id=job.id,
            session_id=prep_session.id if prep_session else None,
            content=content,
            meta={
                "tone": context.tone,
                "length": context.length,
            },
        )
        db.add(cover)
    else:
        existing.content = content
        existing.session_id = prep_session.id if prep_session else existing.session_id
        meta = dict(existing.meta or {})
        meta.update({"tone": context.tone, "length": context.length})
        existing.meta = meta
        cover = existing

    if create_session_message and prep_session is not None:
        message = Message(
            session_id=prep_session.id,
            sender="ASSISTANT",
            type="COVER_LETTER",
            content=content,
            meta={
                "source": "cover_letter_service",
                "resume_id": str(resume.id),
                "job_posting_id": str(job.id),
            },
        )
        db.add(message)

    await db.commit()
    await db.refresh(cover)
    return cover


async def get_cover_letter_for_pair(
    db: AsyncSession,
    current_user: User,
    *,
    resume_id: uuid_pkg.UUID,
    job_posting_id: uuid_pkg.UUID,
) -> Optional[CoverLetter]:
    """Return latest cover letter for a given (user, resume, job) trio."""
    stmt = select(CoverLetter).where(
        CoverLetter.user_id == current_user.id,
        CoverLetter.resume_id == resume_id,
        CoverLetter.job_posting_id == job_posting_id,
    )
    result = await db.execute(stmt)
    return result.scalars().one_or_none()


async def update_cover_letter_content(
    db: AsyncSession,
    current_user: User,
    *,
    cover_letter_id: uuid_pkg.UUID,
    content: str,
) -> CoverLetter:
    """Update the content of an existing cover letter owned by the current user."""
    cover = await db.get(CoverLetter, cover_letter_id)
    if cover is None or cover.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cover letter not found.")

    cover.content = content
    await db.commit()
    await db.refresh(cover)
    return cover


async def delete_cover_letter_for_pair(
    db: AsyncSession,
    current_user: User,
    *,
    resume_id: uuid_pkg.UUID,
    job_posting_id: uuid_pkg.UUID,
) -> bool:
    """
    Delete the cover letter for a given (user, resume, job) trio.
    Returns True if a record was deleted, False if none existed.
    """
    stmt = select(CoverLetter).where(
        CoverLetter.user_id == current_user.id,
        CoverLetter.resume_id == resume_id,
        CoverLetter.job_posting_id == job_posting_id,
    )
    result = await db.execute(stmt)
    cover = result.scalars().one_or_none()
    if cover is None:
        return False

    await db.delete(cover)
    await db.commit()
    return True


