"""
CV scoring agent: LLM-based analysis of CV/résumé.
Supports vision (PDF/image) and text input.
"""

import json
import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

CV_SCORING_SYSTEM_PROMPT = """You are an expert CV/résumé reviewer and career coach. Your task is to analyze a candidate's CV and provide:

1. An overall strength score from 0 to 100.
2. A breakdown of scores for: content (relevance, completeness, clarity of experience), structure (organization, sections, readability), and clarity (professional language, conciseness).
3. Three to five actionable suggestions for improvement.

Evaluate as a hiring manager would: consider completeness (contact info, education, experience), quality of experience descriptions (impact, metrics), skills presentation, formatting/layout, and professional tone.

Respond with a single JSON object with these exact keys:
- "score": number 0-100
- "breakdown": object with "content" (0-100), "structure" (0-100), "clarity" (0-100)
- "suggestions": array of strings (3-5 items)

Do not include any text outside the JSON object."""

CV_SCORING_TEXT_USER_PREFIX = "Analyze the following CV/résumé text and provide the scoring JSON:\n\n---\n\n"


class CVScoreResult(BaseModel):
    """Structured result from CV scoring."""

    score: float = Field(..., ge=0, le=100, description="Overall CV strength score.")
    breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Scores per dimension: content, structure, clarity.",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Actionable improvement suggestions.",
    )


def _is_cv_scoring_available() -> bool:
    """True if CV scoring is enabled and API key is set."""
    return bool(
        getattr(settings, "CV_SCORING_ENABLED", False)
        and getattr(settings, "OPENAI_API_KEY", None)
    )


def _strip_json_fence(content: str) -> str:
    """Remove markdown code fence if present."""
    content = (content or "").strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    return content


def _parse_and_validate_llm_response(content: str) -> CVScoreResult:
    """Parse JSON from LLM response and return CVScoreResult."""
    content = _strip_json_fence(content)
    parsed = json.loads(content)
    score = float(parsed.get("score", 0))
    score = max(0, min(100, score))
    breakdown = parsed.get("breakdown") or {}
    if isinstance(breakdown, dict):
        breakdown = {k: float(v) for k, v in breakdown.items() if isinstance(v, (int, float))}
    suggestions = parsed.get("suggestions") or []
    if isinstance(suggestions, list):
        suggestions = [str(s) for s in suggestions if s]
    return CVScoreResult(
        score=round(score, 1),
        breakdown=breakdown,
        suggestions=suggestions[:10],
    )


async def score_cv_from_vision(image_content_parts: List[dict]) -> CVScoreResult:
    """
    Score a CV from vision content (list of image_url parts from file_to_vision).
    Raises ValueError if agent disabled or LLM fails.
    """
    if not _is_cv_scoring_available():
        raise ValueError(
            "CV scoring is disabled (CV_SCORING_ENABLED=false or OPENAI_API_KEY unset)."
        )

    model = getattr(settings, "CV_SCORING_MODEL", "gpt-4o-mini")

    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": "Analyze this CV/résumé document and provide the scoring JSON as specified."},
        *image_content_parts,
    ]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("CV scoring: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    try:
        logger.info("CV scoring: calling LLM (model=%s, vision parts=%d)", model, len(image_content_parts))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CV_SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        result = _parse_and_validate_llm_response(content)
        logger.info("CV scoring: LLM returned score=%.1f", result.score)
        return result
    except json.JSONDecodeError as e:
        logger.warning("CV scoring: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from CV scorer.") from e
    except ValueError:
        raise
    except Exception as e:
        logger.warning("CV scoring: LLM call failed: %s", e)
        raise ValueError("CV scoring failed.") from e


async def score_cv_from_text(raw_text: str) -> CVScoreResult:
    """
    Score a CV from raw text (fallback when no file available).
    Raises ValueError if agent disabled or LLM fails.
    """
    if not _is_cv_scoring_available():
        raise ValueError(
            "CV scoring is disabled (CV_SCORING_ENABLED=false or OPENAI_API_KEY unset)."
        )

    model = getattr(settings, "CV_SCORING_MODEL", "gpt-4o-mini")
    user_content = CV_SCORING_TEXT_USER_PREFIX + (raw_text or "")[: 12000]

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("CV scoring: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    try:
        logger.info("CV scoring: calling LLM (model=%s, text len=%d)", model, len(user_content))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CV_SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        result = _parse_and_validate_llm_response(content)
        logger.info("CV scoring: LLM returned score=%.1f", result.score)
        return result
    except json.JSONDecodeError as e:
        logger.warning("CV scoring: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from CV scorer.") from e
    except ValueError:
        raise
    except Exception as e:
        logger.warning("CV scoring: LLM call failed: %s", e)
        raise ValueError("CV scoring failed.") from e
