"""
Extract raw text from resume files (PDF). Used when client uploads a file.
"""

from typing import Optional

import pymupdf  # PyMuPDF (import as pymupdf, not fitz for clarity in deps)


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
