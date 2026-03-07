"""
Convert PDF and image files to format suitable for OpenAI vision API.
Used by CV scoring when passing document directly to LLM.
"""

import base64
import logging
from typing import List, Tuple

import pymupdf

from app.services.text_extraction import (
    SUPPORTED_FILE_CONTENT_TYPES,
    _detect_content_type,
)

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 4
PDF_DPI = 150


def _is_pdf(content_type: str) -> bool:
    return (content_type or "").strip().lower() == "application/pdf"


def _is_image(content_type: str) -> bool:
    ct = (content_type or "").strip().lower()
    return ct.startswith("image/") and ct in SUPPORTED_FILE_CONTENT_TYPES


def file_to_vision_content(
    content: bytes,
    content_type: str | None = None,
) -> Tuple[List[dict], str]:
    """
    Convert file bytes to OpenAI vision API content format.

    For PDF: Converts each page (up to MAX_PDF_PAGES) to PNG, base64-encodes.
    For image: Base64-encodes the raw bytes.

    Returns:
        (content_parts, detail) - content_parts is a list for the "content" array
        in the message. Each image is added as {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}.
        detail is a string like "4 pages" or "image" for logging.
    """
    if not content or len(content) < 4:
        raise ValueError("Empty or invalid file content")

    ct = (content_type or "").strip().lower()
    if ct in ("", "application/octet-stream"):
        ct = _detect_content_type(content)
    if not ct:
        raise ValueError("Unsupported file type. Use PDF or image (PNG, JPEG, WebP).")

    parts: List[dict] = []
    detail = ""

    if _is_pdf(ct):
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Invalid PDF: {e}") from e

        try:
            page_count = min(len(doc), MAX_PDF_PAGES)
            for i in range(page_count):
                page = doc[i]
                pix = page.get_pixmap(dpi=PDF_DPI)
                png_bytes = pix.tobytes("png")
                b64 = base64.b64encode(png_bytes).decode("ascii")
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })
            detail = f"{page_count} page(s)"
        finally:
            doc.close()

    elif _is_image(ct):
        b64 = base64.b64encode(content).decode("ascii")
        mime = "image/png" if "png" in ct else "image/jpeg" if "jpeg" in ct or "jpg" in ct else "image/webp"
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
        detail = "image"
    else:
        raise ValueError(f"Unsupported file type: {ct}. Use PDF or image (PNG, JPEG, WebP).")

    return parts, detail
