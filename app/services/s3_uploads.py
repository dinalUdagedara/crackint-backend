"""
Upload files to S3 and return a public or configured URL.
Used for cover images, profile pictures, resume/job source files, etc.
"""

import logging
from typing import Optional

import uuid as uuid_pkg

from app.config import settings
from app.services.text_extraction import DOCX_CONTENT_TYPE, resolve_effective_content_type

logger = logging.getLogger(__name__)


# Content type -> file extension for S3 key
_CONTENT_TYPE_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _get_region() -> str:
    """Region for S3 uploads (uploads bucket or default)."""
    return (settings.S3_UPLOADS_REGION or settings.AWS_DEFAULT_REGION or "us-east-1").strip()


def upload_image_to_s3(
    content: bytes,
    content_type: str,
    prefix: str = "uploads/cover-images",
) -> str:
    """
    Upload image bytes to S3 and return the object URL.

    Args:
        content: Raw file bytes.
        content_type: MIME type (image/jpeg, image/png, image/webp).
        prefix: S3 key prefix (folder).

    Returns:
        Public URL to the object, e.g. https://bucket.s3.region.amazonaws.com/key

    Raises:
        ValueError: If S3 is not configured or content_type is not supported.
        Exception: On S3 upload failure.
    """
    bucket = settings.S3_UPLOADS_BUCKET
    if not bucket or not bucket.strip():
        raise ValueError("S3 uploads are not configured: set S3_UPLOADS_BUCKET (and AWS credentials).")

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise ValueError("AWS credentials are not set: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")

    ext = _CONTENT_TYPE_TO_EXT.get(content_type.lower() if content_type else "")
    if not ext:
        raise ValueError(f"Unsupported image type: {content_type}. Use JPEG, PNG, or WebP.")

    key = f"{prefix.rstrip('/')}/{uuid_pkg.uuid4().hex}.{ext}"
    region = _get_region()

    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    extra = {"ContentType": content_type}
    # Optional: make object publicly readable (bucket must allow this)
    # extra["ACL"] = "public-read"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        **extra,
    )

    # Standard public URL (works if bucket/object is public or has a bucket policy allowing GetObject)
    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    return url


# MIME after resolution -> file extension for S3 key
_DOCUMENT_EXT: dict[str, str] = {
    "application/pdf": "pdf",
    DOCX_CONTENT_TYPE: "docx",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}


def upload_document_to_s3(
    content: bytes,
    declared_content_type: Optional[str],
    filename: Optional[str],
    prefix: str,
) -> str:
    """
    Upload resume/job document bytes (PDF, DOCX, images) to S3 and return the object URL.

    Uses the same bucket/credentials as images. Content type is resolved from
    declared MIME, filename, and magic bytes (see resolve_effective_content_type).
    """
    bucket = settings.S3_UPLOADS_BUCKET
    if not bucket or not bucket.strip():
        raise ValueError("S3 uploads are not configured: set S3_UPLOADS_BUCKET (and AWS credentials).")

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise ValueError("AWS credentials are not set: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")

    effective = resolve_effective_content_type(declared_content_type, filename, content)
    if effective == "application/octet-stream":
        raise ValueError("Could not determine file type for upload (unsupported or empty file).")

    ext = _DOCUMENT_EXT.get(effective.lower())
    if not ext:
        raise ValueError(f"Unsupported document type for S3 upload: {effective}")

    key = f"{prefix.rstrip('/')}/{uuid_pkg.uuid4().hex}.{ext}"
    region = _get_region()

    import boto3

    client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=effective,
    )

    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def try_upload_document_to_s3(
    content: bytes,
    declared_content_type: Optional[str],
    filename: Optional[str],
    prefix: str,
) -> Optional[str]:
    """
    Upload document bytes to S3 when configured. On misconfiguration or upload errors,
    logs a warning and returns None so callers can still complete extraction without failing.
    """
    if not is_s3_uploads_configured():
        return None
    try:
        return upload_document_to_s3(content, declared_content_type, filename, prefix)
    except Exception:
        logger.warning(
            "S3 document upload failed; continuing without stored file URL.",
            exc_info=True,
        )
        return None


def is_s3_uploads_configured() -> bool:
    """Return True if S3 uploads can be used (bucket and credentials set)."""
    bucket = settings.S3_UPLOADS_BUCKET
    return bool(
        bucket
        and bucket.strip()
        and settings.AWS_ACCESS_KEY_ID
        and settings.AWS_SECRET_ACCESS_KEY
    )
