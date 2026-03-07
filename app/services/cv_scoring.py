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

logger = logging.getLogger(__name__)


async def score_cv_from_file(
    content: bytes,
    content_type: str | None = None,
) -> CVScoreResult:
    """
    Score a CV from file bytes (PDF or image).
    Converts to vision format and calls LLM.
    Raises ValueError if content invalid or scoring fails.
    """
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
