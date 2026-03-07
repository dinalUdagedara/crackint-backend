"""
Job posting CRUD endpoints.
"""

import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.job_posting.schemas import (
    JobPostingCreate,
    JobPostingListItem,
    JobPostingUpdate,
)
from app.common.http_response_model import CommonResponse, PageMeta
from app.models import JobPosting, User

router = APIRouter()

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "",
    response_model=CommonResponse[list[JobPostingListItem]],
    name="List job postings",
    summary="List the current user's job postings with pagination.",
)
async def list_job_postings(
    page: int = Query(
        1,
        ge=1,
        description="Page number (1-based).",
    ),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Items per page.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Returns a paginated list of job postings for the authenticated user."""
    count_q = (
        select(func.count())
        .select_from(JobPosting)
        .where(JobPosting.user_id == current_user.id)
    )
    total_result = await session.execute(count_q)
    total_items = total_result.scalar_one() or 0
    total_pages = max(1, (total_items + page_size - 1) // page_size)

    offset = (page - 1) * page_size
    q = (
        select(JobPosting)
        .where(JobPosting.user_id == current_user.id)
        .order_by(JobPosting.updated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(q)
    rows = list(result.scalars().all())

    payload = [JobPostingListItem.model_validate(row) for row in rows]
    meta = PageMeta(
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        total_items=total_items,
    )
    return CommonResponse(
        success=True,
        message="Job postings retrieved successfully",
        payload=payload,
        meta=meta,
    )


@router.get(
    "/{job_posting_id}",
    response_model=CommonResponse[JobPostingListItem],
    name="Get job posting by ID",
    summary="Get a single job posting by ID.",
)
async def get_job_posting(
    job_posting_id: uuid_pkg.UUID = Path(..., description="Job posting ID."),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Returns the job posting record if found and owned by the current user; 404 otherwise."""
    row = await session.get(JobPosting, job_posting_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    return CommonResponse(
        success=True,
        message="Job posting retrieved successfully",
        payload=JobPostingListItem.model_validate(row),
    )


@router.post(
    "",
    response_model=CommonResponse[JobPostingListItem],
    name="Create job posting",
    summary="Create a new job posting record from extracted entities.",
)
async def create_job_posting(
    body: JobPostingCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new job posting record from entities produced by `/jobs/extract`.
    """
    record = JobPosting(
        user_id=current_user.id,
        entities=body.entities,
        raw_text=body.raw_text,
        location=body.location,
        deadline=body.deadline,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return CommonResponse(
        success=True,
        message="Job posting created successfully",
        payload=JobPostingListItem.model_validate(record),
    )


@router.patch(
    "/{job_posting_id}",
    response_model=CommonResponse[JobPostingListItem],
    name="Update job posting",
    summary="Partially update a job posting (entities, raw_text, location, deadline).",
)
async def update_job_posting(
    job_posting_id: uuid_pkg.UUID = Path(..., description="Job posting ID to update."),
    body: JobPostingUpdate = ...,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Update only the fields present in the request body. Entities are merged by key."""
    row = await session.get(JobPosting, job_posting_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    sent = body.model_dump(exclude_unset=True)
    if "entities" in sent and body.entities is not None:
        updated = dict(row.entities or {})
        for key, values in body.entities.items():
            updated[key] = values
        row.entities = updated
    if "raw_text" in sent:
        row.raw_text = body.raw_text
    if "location" in sent:
        row.location = body.location
    if "deadline" in sent:
        row.deadline = body.deadline
    await session.commit()
    await session.refresh(row)
    return CommonResponse(
        success=True,
        message="Job posting updated successfully",
        payload=JobPostingListItem.model_validate(row),
    )
