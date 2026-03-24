"""
CV scoring orchestration: file handling and agent delegation.
"""

import logging
from typing import List

from app.agents.cv_scoring_agent import (
    CVScoreResult,
    score_cv_from_text,
    score_cv_from_vision,
)
from app.services.file_to_vision import file_to_vision_content
from app.services.text_extraction import (
    DOCX_CONTENT_TYPE,
    extract_text_from_file,
    get_resolved_mime_type,
)

logger = logging.getLogger(__name__)


async def score_cv_from_file(
    content: bytes,
    content_type: str | None = None,
    filename: str | None = None,
) -> CVScoreResult:
    """
    Score a CV from file bytes: PDF and images go to the vision model; .docx is
    converted to plain text and scored with the text path (same as stored resumes).
    Raises ValueError if content invalid or scoring fails.
    """
    eff = get_resolved_mime_type(content, content_type, filename)
    if eff == DOCX_CONTENT_TYPE:
        try:
            raw = extract_text_from_file(content, content_type, filename)
        except ValueError as e:
            raise ValueError(str(e)) from e
        if not (raw or "").strip():
            raise ValueError("No CV text to analyze.")
        logger.info("CV scoring: DOCX → text path (len=%d)", len(raw))
        return await score_cv_from_raw_text(raw)

    parts, detail = file_to_vision_content(content, content_type)
    logger.info("CV scoring: file converted to vision (%s), %d part(s)", detail, len(parts))
    return await score_cv_from_vision(parts)


async def score_cv_from_raw_text(raw_text: str) -> CVScoreResult:
    """
    Score a CV from raw text (fallback for existing resumes).
    Raises ValueError if raw_text empty or scoring fails.
    """
    if not (raw_text or "").strip():
        raise ValueError("No CV text to analyze.")
    return await score_cv_from_text(raw_text)
