"""
Image upload endpoint: upload to S3 and return URL for use as cover_image_url etc.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.api.uploads.schemas import UploadImageResponse
from app.common.http_response_model import CommonResponse
from app.config import settings
from app.models import User
from app.services.s3_uploads import is_s3_uploads_configured, upload_image_to_s3

router = APIRouter()

# Allowed image types for cover images (no PDF)
ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
MAX_BYTES = (getattr(settings, "MAX_COVER_IMAGE_SIZE_MB", 5) or 5) * 1024 * 1024


@router.post(
    "/image",
    response_model=CommonResponse[UploadImageResponse],
    name="Upload image",
    summary="Upload an image file to S3 and get back a URL (e.g. for job posting cover image).",
)
async def upload_image(
    file: UploadFile = File(..., description="Image file (JPEG, PNG, or WebP)"),
    current_user: User = Depends(get_current_user),
):
    """
    Accepts a single image file, uploads it to S3, and returns the public URL.
    Use this URL as `cover_image_url` when creating or updating a job posting.

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

    try:
        url = upload_image_to_s3(content, content_type)
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
