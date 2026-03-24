"""Admin business logic: user wipe and list queries."""

import uuid as uuid_pkg
from typing import List, Optional, Tuple

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.schemas import AdminSessionListItem, AdminUserListItem
from app.models import CoverLetter, JobPosting, PrepSession, Resume, User
from app.schemas.common import SessionStatus


async def delete_user_and_all_data(
    db: AsyncSession,
    user_id: uuid_pkg.UUID,
) -> Tuple[int, int, int, int]:
    """
    Delete all application data for user_id, then the user row.
    Returns counts: (prep_sessions, cover_letters, resumes, job_postings).
    """
    n_ps = await db.scalar(
        select(func.count()).select_from(PrepSession).where(PrepSession.user_id == user_id)
    )
    n_cl = await db.scalar(
        select(func.count()).select_from(CoverLetter).where(CoverLetter.user_id == user_id)
    )
    n_r = await db.scalar(
        select(func.count()).select_from(Resume).where(Resume.user_id == user_id)
    )
    n_j = await db.scalar(
        select(func.count()).select_from(JobPosting).where(JobPosting.user_id == user_id)
    )

    await db.execute(delete(PrepSession).where(PrepSession.user_id == user_id))
    await db.execute(delete(CoverLetter).where(CoverLetter.user_id == user_id))
    await db.execute(delete(Resume).where(Resume.user_id == user_id))
    await db.execute(delete(JobPosting).where(JobPosting.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()

    return (
        int(n_ps or 0),
        int(n_cl or 0),
        int(n_r or 0),
        int(n_j or 0),
    )


async def list_users_admin(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    search: Optional[str],
) -> Tuple[List[AdminUserListItem], int]:
    filters = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                User.email.ilike(term),
                User.name.ilike(term),
            )
        )

    count_q = select(func.count()).select_from(User)
    q = select(User)
    if filters:
        count_q = count_q.where(*filters)
        q = q.where(*filters)

    total_result = await db.execute(count_q)
    total_items = int(total_result.scalar_one() or 0)

    offset = (page - 1) * page_size
    q = q.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(q)
    rows = list(result.scalars().all())
    items = [AdminUserListItem.model_validate(r) for r in rows]
    return items, total_items


async def list_sessions_admin(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    status_filter: Optional[SessionStatus],
    user_id_filter: Optional[uuid_pkg.UUID],
) -> Tuple[List[AdminSessionListItem], int]:
    filters = []
    if status_filter is not None:
        filters.append(PrepSession.status == status_filter.value)
    if user_id_filter is not None:
        filters.append(PrepSession.user_id == user_id_filter)

    count_q = select(func.count()).select_from(PrepSession)
    stmt = (
        select(PrepSession, User.email, User.name)
        .outerjoin(User, PrepSession.user_id == User.id)
    )
    if filters:
        count_q = count_q.where(*filters)
        stmt = stmt.where(*filters)

    total_result = await db.execute(count_q)
    total_items = int(total_result.scalar_one() or 0)

    offset = (page - 1) * page_size
    stmt = (
        stmt.order_by(PrepSession.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.all()
    items: List[AdminSessionListItem] = []
    for prep_session, user_email, user_name in rows:
        items.append(
            AdminSessionListItem(
                id=prep_session.id,
                user_id=prep_session.user_id,
                user_email=user_email,
                user_name=user_name,
                resume_id=prep_session.resume_id,
                job_posting_id=prep_session.job_posting_id,
                mode=prep_session.mode,
                status=prep_session.status,
                readiness_score=prep_session.readiness_score,
                created_at=prep_session.created_at,
                updated_at=prep_session.updated_at,
            )
        )
    return items, total_items
