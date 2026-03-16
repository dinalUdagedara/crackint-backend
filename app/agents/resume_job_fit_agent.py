"""
Resume–job fit agent: LLM-based analysis of a CV/résumé against a specific job posting.
Produces a fit score (0–100), short summary, and job-tailored suggestions.
"""

import json
import logging
from typing import List

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# Cap input length per document to stay within context limits
MAX_RESUME_CHARS = 8000
MAX_JOB_CHARS = 6000

RESUME_JOB_FIT_SYSTEM_PROMPT = """You are an expert recruiter and career coach. Your task is to analyze how well a candidate's CV/résumé matches a specific job posting.

Consider:
- Alignment of skills (required vs. stated)
- Relevance of experience to the role
- Education and qualifications fit
- Gaps or weak areas for this specific job
- Strengths the candidate should highlight for this role

Respond with a single JSON object with these exact keys:
- "fit_score": number 0-100 (how well the resume fits this job; 100 = excellent match)
- "summary": string, 2-4 sentences summarizing fit and main gaps or strengths for this job
- "tailored_suggestions": array of 3-5 strings: actionable, job-specific suggestions (e.g. "Add a project that demonstrates X mentioned in the job", "Emphasize your Y experience in the summary")

Do not include any text outside the JSON object."""


class ResumeJobFitResult(BaseModel):
    """Structured result from resume–job fit LLM analysis."""

    fit_score: float = Field(..., ge=0, le=100, description="How well the resume fits this job (0-100).")
    summary: str = Field(default="", description="Short narrative summary of fit and gaps.")
    tailored_suggestions: List[str] = Field(
        default_factory=list,
        description="Job-specific improvement or highlight suggestions.",
    )


def _is_resume_job_fit_available() -> bool:
    """True if resume–job fit LLM is enabled and API key is set."""
    return bool(
        getattr(settings, "RESUME_JOB_FIT_LLM_ENABLED", False)
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


def _parse_and_validate_llm_response(content: str) -> ResumeJobFitResult:
    """Parse JSON from LLM response and return ResumeJobFitResult."""
    content = _strip_json_fence(content)
    parsed = json.loads(content)
    score = float(parsed.get("fit_score", 0))
    score = max(0, min(100, score))
    summary = str(parsed.get("summary") or "").strip()
    suggestions = parsed.get("tailored_suggestions") or []
    if isinstance(suggestions, list):
        suggestions = [str(s).strip() for s in suggestions if str(s).strip()]
    return ResumeJobFitResult(
        fit_score=round(score, 1),
        summary=summary[:2000],
        tailored_suggestions=suggestions[:10],
    )


async def analyze_resume_job_fit(
    resume_text: str,
    job_text: str,
) -> ResumeJobFitResult:
    """
    Analyze how well a resume fits a job posting using the LLM.
    Raises ValueError if agent disabled or LLM fails.
    """
    if not _is_resume_job_fit_available():
        raise ValueError(
            "Resume–job fit LLM is disabled (RESUME_JOB_FIT_LLM_ENABLED=false or OPENAI_API_KEY unset)."
        )

    resume_text = (resume_text or "").strip()[:MAX_RESUME_CHARS]
    job_text = (job_text or "").strip()[:MAX_JOB_CHARS]
    if not resume_text or not job_text:
        raise ValueError("Both resume text and job text are required for fit analysis.")

    model = getattr(settings, "RESUME_JOB_FIT_LLM_MODEL", "gpt-4o-mini")
    user_content = f"""CANDIDATE CV/RÉSUMÉ:
---
{resume_text}
---

JOB POSTING:
---
{job_text}
---

Analyze the fit and return the JSON object as specified (fit_score, summary, tailored_suggestions)."""

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Resume–job fit: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    try:
        logger.info(
            "Resume–job fit: calling LLM (model=%s, resume_len=%d, job_len=%d)",
            model,
            len(resume_text),
            len(job_text),
        )
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": RESUME_JOB_FIT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content.")

        result = _parse_and_validate_llm_response(content)
        logger.info("Resume–job fit: LLM returned fit_score=%.1f", result.fit_score)
        return result
    except json.JSONDecodeError as e:
        logger.warning("Resume–job fit: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from resume–job fit analysis.") from e
    except ValueError:
        raise
    except Exception as e:
        logger.warning("Resume–job fit: LLM call failed: %s", e)
        raise ValueError("Resume–job fit analysis failed.") from e
