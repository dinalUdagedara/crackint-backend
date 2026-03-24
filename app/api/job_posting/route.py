"""
Job posting CRUD endpoints.
"""

from datetime import datetime, timedelta, timezone
import uuid as uuid_pkg

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.job_posting.schemas import (
    DeleteJobPostingResponse,
    JobPostingCreate,
    JobPostingListItem,
    JobPostingNearDeadlineItem,
    JobPostingReorderRequest,
    JobPostingUpdate,
    ReorderResponse,
)
from app.common.http_response_model import CommonResponse, PageMeta
from app.models import JobPosting, User

router = APIRouter()

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Convert timezone-aware datetime to naive UTC for DB columns (TIMESTAMP WITHOUT TIME ZONE)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


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
        .order_by(
            JobPosting.display_order.asc().nulls_last(),
            JobPosting.updated_at.desc(),
        )
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


@router.put(
    "/reorder",
    response_model=CommonResponse[ReorderResponse],
    name="Reorder job postings",
    summary="Set display order for job postings by providing IDs in desired order.",
)
async def reorder_job_postings(
    body: JobPostingReorderRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Update display_order for each job posting to match the index in the request.
    All IDs must belong to the current user's job postings.
    """
    if not body.order:
        return CommonResponse(
            success=True,
            message="No jobs to reorder.",
            payload=ReorderResponse(updated=True),
        )
    # Load all job postings for this user that are in the requested id list
    q = select(JobPosting).where(
        JobPosting.user_id == current_user.id,
        JobPosting.id.in_(body.order),
    )
    result = await session.execute(q)
    rows = {row.id: row for row in result.scalars().all()}
    if len(rows) != len(body.order):
        missing = set(body.order) - set(rows.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Job posting(s) not found or not owned by you: {missing}",
        )
    for idx, job_id in enumerate(body.order):
        rows[job_id].display_order = idx
    await session.commit()
    return CommonResponse(
        success=True,
        message="Job postings reordered successfully",
        payload=ReorderResponse(updated=True),
    )


@router.get(
    "/near-deadline",
    response_model=CommonResponse[list[JobPostingNearDeadlineItem]],
    name="List job postings near deadline",
    summary="List job postings with a deadline or interview date within the next N days (for notifications/reminders).",
)
async def list_job_postings_near_deadline(
    days: int = Query(
        7,
        ge=1,
        le=90,
        description="Include postings whose deadline or interview date falls within the next N days.",
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Returns job postings that have either a deadline or interview_at in the next `days` days.
    Each item includes the job, the next milestone date, its type (deadline vs interview), and days_until.
    Sorted by soonest milestone first.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    end_utc = now_utc + timedelta(days=days)

    q = (
        select(JobPosting)
        .where(JobPosting.user_id == current_user.id)
        .where(
            or_(
                JobPosting.deadline.isnot(None),
                JobPosting.interview_at.isnot(None),
            ),
        )
    )
    result = await session.execute(q)
    rows = list(result.scalars().all())

    out: list[JobPostingNearDeadlineItem] = []
    for row in rows:
        candidates: list[tuple[datetime, str]] = []
        deadline_naive = _naive_utc(row.deadline) if row.deadline is not None else None
        interview_naive = _naive_utc(row.interview_at) if row.interview_at is not None else None
        if deadline_naive is not None and now_utc <= deadline_naive <= end_utc:
            candidates.append((deadline_naive, "deadline"))
        if interview_naive is not None and now_utc <= interview_naive <= end_utc:
            candidates.append((interview_naive, "interview"))
        if not candidates:
            continue
        next_date, next_type = min(candidates, key=lambda x: x[0])
        delta = next_date - now_utc
        days_until = max(0, delta.days)
        out.append(
            JobPostingNearDeadlineItem(
                job=JobPostingListItem.model_validate(row),
                next_milestone_date=next_date,
                next_milestone_type=next_type,
                days_until=days_until,
            ),
        )

    out.sort(key=lambda x: x.next_milestone_date)
    return CommonResponse(
        success=True,
        message="Job postings near deadline retrieved successfully",
        payload=out,
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
        source_file_url=body.source_file_url,
        location=body.location,
        deadline=_naive_utc(body.deadline),
        cover_image_url=body.cover_image_url,
        notes=body.notes,
        questions_to_ask=body.questions_to_ask,
        interview_at=_naive_utc(body.interview_at),
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        talking_points=body.talking_points,
        application_url=body.application_url,
        stage=body.stage,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return CommonResponse(
        success=True,
        message="Job posting created successfully",
        payload=JobPostingListItem.model_validate(record),
    )


@router.delete(
    "/{job_posting_id}",
    response_model=CommonResponse[DeleteJobPostingResponse],
    name="Delete job posting by ID",
    summary="Delete a single job posting by ID.",
)
async def delete_job_posting(
    job_posting_id: uuid_pkg.UUID = Path(..., description="Job posting ID to delete."),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    Deletes the job posting if it belongs to the current user. Returns 404 if not found or not owned.
    """
    row = await session.get(JobPosting, job_posting_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    await session.delete(row)
    await session.commit()
    return CommonResponse(
        success=True,
        message="Job posting deleted successfully",
        payload=DeleteJobPostingResponse(deleted=True),
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
        row.deadline = _naive_utc(body.deadline)
    if "display_order" in sent:
        row.display_order = body.display_order
    if "cover_image_url" in sent:
        row.cover_image_url = body.cover_image_url
    if "source_file_url" in sent:
        row.source_file_url = body.source_file_url
    if "notes" in sent:
        row.notes = body.notes
    if "questions_to_ask" in sent:
        row.questions_to_ask = body.questions_to_ask
    if "interview_at" in sent:
        row.interview_at = _naive_utc(body.interview_at)
    if "contact_name" in sent:
        row.contact_name = body.contact_name
    if "contact_email" in sent:
        row.contact_email = body.contact_email
    if "talking_points" in sent:
        row.talking_points = body.talking_points
    if "application_url" in sent:
        row.application_url = body.application_url
    if "stage" in sent:
        row.stage = body.stage
    await session.commit()
    await session.refresh(row)
    return CommonResponse(
        success=True,
        message="Job posting updated successfully",
        payload=JobPostingListItem.model_validate(row),
    )
