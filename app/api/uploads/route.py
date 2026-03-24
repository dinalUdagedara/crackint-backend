"""
Upload endpoints: images and documents to S3; return public URLs for DB fields.
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.api.deps import get_current_user
from app.api.uploads.schemas import UploadImageResponse
from app.common.http_response_model import CommonResponse
from app.config import settings
from app.models import User
from app.services.s3_uploads import (
    is_s3_uploads_configured,
    upload_document_to_s3,
    upload_image_to_s3,
)
from app.services.text_extraction import UNSUPPORTED_UPLOAD_DETAIL, upload_content_type_allowed

router = APIRouter()

# Allowed image types for cover images (no PDF)
ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
MAX_BYTES = (getattr(settings, "MAX_COVER_IMAGE_SIZE_MB", 5) or 5) * 1024 * 1024
MAX_DOC_BYTES = (getattr(settings, "MAX_UPLOAD_SIZE_MB", 10) or 10) * 1024 * 1024


@router.post(
    "/image",
    response_model=CommonResponse[UploadImageResponse],
    name="Upload image",
    summary="Upload an image file to S3 and get back a URL (e.g. for job posting cover image).",
)
async def upload_image(
    file: UploadFile = File(..., description="Image file (JPEG, PNG, or WebP)"),
    purpose: Literal["cover", "profile"] = Query(
        "cover",
        description="cover: job posting cover images; profile: user profile pictures (S3 prefix only).",
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Accepts a single image file, uploads it to S3, and returns the public URL.
    - Use `purpose=cover` (default) with job postings as `cover_image_url`.
    - Use `purpose=profile` for avatars, then set `profile_image_url` via PATCH /auth/me.

    Requires S3_UPLOADS_BUCKET and AWS credentials to be set.
    """
    if not is_s3_uploads_configured():
        raise HTTPException(
            status_code=503,
            detail="Image upload is not configured. Set S3_UPLOADS_BUCKET and AWS credentials.",
        )

    content_type = (file.content_type or "").strip().lower()
    if content_type and content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only image files are accepted (JPEG, PNG, WebP).",
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        max_mb = getattr(settings, "MAX_COVER_IMAGE_SIZE_MB", 5) or 5
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed ({max_mb} MB).",
        )

    if not content_type:
        content_type = "image/jpeg"

    prefix = (
        "uploads/profile-images"
        if purpose == "profile"
        else "uploads/cover-images"
    )
    try:
        url = upload_image_to_s3(content, content_type, prefix=prefix)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Upload failed: {str(e)}",
        ) from e

    return CommonResponse(
        success=True,
        message="Image uploaded successfully",
        payload=UploadImageResponse(url=url),
    )


@router.post(
    "/document",
    response_model=CommonResponse[UploadImageResponse],
    name="Upload document",
    summary="Upload a resume or job description file (PDF, DOCX, images) to S3 and get a URL.",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, Word (.docx), or image (PNG, JPEG, WebP)"),
    purpose: Literal["resume", "job"] = Query(
        "resume",
        description="resume: store URL on Resume.source_file_url; job: JobPosting.source_file_url.",
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Same bucket/credentials as POST /uploads/image. Use the returned URL when creating or updating
    records, or rely on automatic upload during POST /resumes/extract and POST /jobs/extract.

    Requires S3_UPLOADS_BUCKET and AWS credentials.
    """
    if not is_s3_uploads_configured():
        raise HTTPException(
            status_code=503,
            detail="Upload is not configured. Set S3_UPLOADS_BUCKET and AWS credentials.",
        )

    if file.content_type and not upload_content_type_allowed(
        file.content_type, file.filename
    ):
        raise HTTPException(status_code=400, detail=UNSUPPORTED_UPLOAD_DETAIL)

    content = await file.read()
    if len(content) > MAX_DOC_BYTES:
        max_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 10) or 10
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed ({max_mb} MB).",
        )

    prefix = (
        "uploads/job-sources" if purpose == "job" else "uploads/resumes"
    )
    try:
        url = upload_document_to_s3(
            content, file.content_type, file.filename, prefix=prefix
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Upload failed: {str(e)}",
        ) from e

    return CommonResponse(
        success=True,
        message="Document uploaded successfully",
        payload=UploadImageResponse(url=url),
    )
