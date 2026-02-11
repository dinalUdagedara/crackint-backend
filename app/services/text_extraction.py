"""
Extract raw text from uploaded files: PDF (PyMuPDF) and images (OCR via Tesseract).
Used by resume and job extraction when the client uploads a file.
"""

from typing import Optional

import pymupdf  # PyMuPDF (import as pymupdf, not fitz for clarity in deps)

# Content types accepted for file upload (PDF + images). Use in routes for validation.
SUPPORTED_FILE_CONTENT_TYPES = frozenset({
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
})


def _detect_content_type(content: bytes) -> Optional[str]:
    """Infer content type from magic bytes when client sends application/octet-stream."""
    if len(content) < 12:
        return None
    if content[:4] == b"%PDF":
        return "application/pdf"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def extract_text_from_pdf(file_content: bytes) -> str:
    """
    Extract plain text from PDF bytes.

    Args:
        file_content: Raw PDF file bytes.

    Returns:
        Extracted text as a single string. Returns empty string if no text found.

    Raises:
        ValueError: If content is not valid PDF.
    """
    if not file_content or len(file_content) < 4:
        raise ValueError("Empty or invalid PDF content")

    try:
        doc = pymupdf.open(stream=file_content, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Invalid PDF: {e}") from e

    try:
        parts: list[str] = []
        for page in doc:
            text = page.get_text()
            if text:
                parts.append(text.strip())
        return "\n\n".join(parts).strip() or ""
    finally:
        doc.close()


def extract_text_from_file(content: bytes, content_type: Optional[str] = None) -> str:
    """
    Extract plain text from file bytes (PDF or image). Dispatches to PDF extraction or OCR.

    Args:
        content: Raw file bytes.
        content_type: MIME type (e.g. application/pdf, image/png). If None or application/octet-stream, inferred from magic bytes.

    Returns:
        Extracted text as a single string.

    Raises:
        ValueError: If content is empty, type is unsupported, or extraction fails.
    """
    if not content or len(content) < 4:
        raise ValueError("Empty or invalid file content")

    ct = (content_type or "").strip().lower()
    if ct in ("", "application/octet-stream"):
        ct = _detect_content_type(content)
    if not ct:
        raise ValueError("Unsupported file type. Use PDF or image (PNG, JPEG, WebP).")

    if ct == "application/pdf":
        return extract_text_from_pdf(content)

    if ct in SUPPORTED_FILE_CONTENT_TYPES and ct.startswith("image/"):
        from app.services.ocr import extract_text_from_image
        return extract_text_from_image(content, content_type=ct)

    raise ValueError(f"Unsupported file type: {content_type}. Use PDF or image (PNG, JPEG, WebP).")
