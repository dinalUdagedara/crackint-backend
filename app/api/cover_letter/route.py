"""
Cover letter API endpoints.
"""

import uuid as uuid_pkg
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cover_letter.schemas import (
    CoverLetterDeleteResponse,
    CoverLetterGenerateRequest,
    CoverLetterRead,
    CoverLetterUpdateRequest,
)
from app.api.deps import get_current_user, get_db
from app.common.http_response_model import CommonResponse
from app.models import User
from app.services.cover_letter_service import (
    delete_cover_letter_for_pair,
    generate_and_store_cover_letter,
    get_cover_letter_for_pair,
    update_cover_letter_content,
)


router = APIRouter()


@router.post(
    "/generate",
    response_model=CommonResponse[CoverLetterRead],
    name="Generate cover letter",
    summary="Generate a tailored cover letter for a resume + job (optionally inside a prep session).",
)
async def post_generate_cover_letter(
    body: CoverLetterGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a cover letter based on a stored resume and job posting.

    You must provide either:
    - resume_id and job_posting_id, or
    - session_id (from which resume/job are inferred).
    """
    cover = await generate_and_store_cover_letter(
        db,
        current_user,
        resume_id=body.resume_id,
        job_posting_id=body.job_posting_id,
        session_id=body.session_id,
        tone=body.tone,
        length=body.length,
        user_notes=body.user_notes,
        create_session_message=True,
    )
    return CommonResponse(
        success=True,
        message="Cover letter generated successfully",
        payload=CoverLetterRead.from_model(cover),
    )


@router.get(
    "",
    response_model=CommonResponse[Optional[CoverLetterRead]],
    name="Get cover letter for resume + job",
    summary="Fetch the latest cover letter for a given resume + job posting pair.",
)
async def get_cover_letter(
    resume_id: uuid_pkg.UUID = Query(..., description="Resume ID."),
    job_posting_id: uuid_pkg.UUID = Query(..., description="Job posting ID."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cover = await get_cover_letter_for_pair(
        db,
        current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )
    if cover is None:
        return CommonResponse(
            success=True,
            message="No cover letter found for this resume + job pair",
            payload=None,
        )
    return CommonResponse(
        success=True,
        message="Cover letter retrieved successfully",
        payload=CoverLetterRead.from_model(cover),
    )


@router.put(
    "/{cover_letter_id}",
    response_model=CommonResponse[CoverLetterRead],
    name="Update cover letter content",
    summary="Overwrite the content of an existing cover letter owned by the current user.",
)
async def put_cover_letter(
    cover_letter_id: uuid_pkg.UUID = Path(..., description="Cover letter ID to update."),
    body: CoverLetterUpdateRequest = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cover = await update_cover_letter_content(
        db,
        current_user,
        cover_letter_id=cover_letter_id,
        content=body.content,
    )
    return CommonResponse(
        success=True,
        message="Cover letter updated successfully",
        payload=CoverLetterRead.from_model(cover),
    )


@router.delete(
    "",
    response_model=CommonResponse[CoverLetterDeleteResponse],
    name="Delete cover letter for resume + job",
    summary="Delete the cover letter for a given resume + job posting pair, if it exists.",
)
async def delete_cover_letter(
    resume_id: uuid_pkg.UUID = Query(..., description="Resume ID."),
    job_posting_id: uuid_pkg.UUID = Query(..., description="Job posting ID."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_cover_letter_for_pair(
        db,
        current_user,
        resume_id=resume_id,
        job_posting_id=job_posting_id,
    )
    return CommonResponse(
        success=True,
        message=(
            "Cover letter deleted successfully"
            if deleted
            else "No cover letter existed for this resume + job pair"
        ),
        payload=CoverLetterDeleteResponse(deleted=deleted),
    )


