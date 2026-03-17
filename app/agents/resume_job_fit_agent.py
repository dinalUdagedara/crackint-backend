"""
Resume–job fit agent: LLM-based analysis of a CV/résumé against a specific job posting.
Produces a fit score (0–100), short summary, job-tailored suggestions, and optional location suitability.
"""

import json
import logging
from typing import Any, Dict, List, Optional

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

When job location and/or candidate location are provided, also assess LOCATION SUITABILITY:
- If the job is REMOTE (work from home, WFH, remote, distributed, etc.): set location_suitability.suitability to "good", message "Remote role — location is not a barrier.", highlight_remote_match true, is_remote true.
- If NOT remote: compare candidate location to job location. Treat as "good" (no caution) when they are in the SAME city/area OR within roughly 30 km / same metro (e.g. Galkissa, Dematagoda, Borella, Colombo Fort, Colombo, Dehiwala are all in the Colombo area, Sri Lanka — within reasonable distance, so suitability "good", message "Job is within a reasonable distance."). Only use "caution" when they are clearly far apart (different cities/regions or different countries), with message like "This job may not be practical unless relocation is possible." or "Consider commute or relocation."
- If candidate location is missing: location_suitability.suitability = "unknown", message "Add your location to see if this job is practical for you."

Respond with a single JSON object with these exact keys:
- "fit_score": number 0-100 (how well the resume fits this job; 100 = excellent match)
- "summary": string, 2-4 sentences summarizing fit and main gaps or strengths for this job
- "tailored_suggestions": array of 3-5 strings: actionable, job-specific suggestions
- "location_suitability": object (only when job/candidate location was provided) with: "job_location_display" (string), "is_remote" (boolean), "candidate_location" (string or null), "suitability" ("good"|"caution"|"unknown"), "message" (string), "highlight_remote_match" (boolean), "alert_message" (string or null; if suitability is "caution", set to the message to show as an alert)

Do not include any text outside the JSON object."""


class ResumeJobFitResult(BaseModel):
    """Structured result from resume–job fit LLM analysis."""

    fit_score: float = Field(..., ge=0, le=100, description="How well the resume fits this job (0-100).")
    summary: str = Field(default="", description="Short narrative summary of fit and gaps.")
    tailored_suggestions: List[str] = Field(
        default_factory=list,
        description="Job-specific improvement or highlight suggestions.",
    )
    location_suitability: Optional[Dict[str, Any]] = Field(
        default=None,
        description="When location was passed: job_location_display, is_remote, candidate_location, suitability, message, highlight_remote_match.",
    )
    location_alert: Optional[Dict[str, str]] = Field(
        default=None,
        description="When location suitability is caution: { type, message, severity } for UI alert.",
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


def _parse_and_validate_llm_response(
    content: str, include_location: bool = False
) -> ResumeJobFitResult:
    """Parse JSON from LLM response and return ResumeJobFitResult."""
    content = _strip_json_fence(content)
    parsed = json.loads(content)
    score = float(parsed.get("fit_score", 0))
    score = max(0, min(100, score))
    summary = str(parsed.get("summary") or "").strip()
    suggestions = parsed.get("tailored_suggestions") or []
    if isinstance(suggestions, list):
        suggestions = [str(s).strip() for s in suggestions if str(s).strip()]

    location_suitability = None
    location_alert = None
    if include_location and parsed.get("location_suitability"):
        loc = parsed["location_suitability"]
        if isinstance(loc, dict):
            job_display = str(loc.get("job_location_display") or "").strip()
            is_remote = bool(loc.get("is_remote"))
            cand_loc = loc.get("candidate_location")
            if cand_loc is not None:
                cand_loc = str(cand_loc).strip() or None
            suitability = str(loc.get("suitability") or "unknown").strip().lower()
            if suitability not in ("good", "caution", "unknown"):
                suitability = "unknown"
            message = str(loc.get("message") or "").strip()
            highlight = bool(loc.get("highlight_remote_match"))
            location_suitability = {
                "job_location_display": job_display or ("Remote" if is_remote else ""),
                "is_remote": is_remote,
                "candidate_location": cand_loc,
                "suitability": suitability,
                "message": message or "Add your location to see if this job is practical for you.",
                "highlight_remote_match": highlight,
            }
            if suitability == "caution":
                # Alert uses same message as location_suitability so UI is consistent
                location_alert = {
                    "type": "location_mismatch",
                    "message": message or "Consider commute or relocation.",
                    "severity": "medium",
                }

    return ResumeJobFitResult(
        fit_score=round(score, 1),
        summary=summary[:2000],
        tailored_suggestions=suggestions[:10],
        location_suitability=location_suitability,
        location_alert=location_alert,
    )


async def analyze_resume_job_fit(
    resume_text: str,
    job_text: str,
    job_location_display: Optional[str] = None,
    candidate_location: Optional[str] = None,
) -> ResumeJobFitResult:
    """
    Analyze how well a resume fits a job posting using the LLM.
    When job_location_display and/or candidate_location are provided, also returns location_suitability.
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

    include_location = job_location_display is not None or candidate_location is not None
    model = getattr(settings, "RESUME_JOB_FIT_LLM_MODEL", "gpt-4o-mini")
    user_content = f"""CANDIDATE CV/RÉSUMÉ:
---
{resume_text}
---

JOB POSTING:
---
{job_text}
---"""
    if include_location:
        user_content += f"""

LOCATION (for suitability):
- Job location: {job_location_display or "(not provided)"}
- Candidate location: {candidate_location or "(not provided)"}

Analyze the fit and return the JSON object (fit_score, summary, tailored_suggestions, and location_suitability as specified)."""
    else:
        user_content += """

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

        result = _parse_and_validate_llm_response(content, include_location=include_location)
        logger.info(
            "Resume–job fit: LLM returned fit_score=%.1f, location_suitability=%s",
            result.fit_score,
            "yes" if result.location_suitability else "no",
        )
        return result
    except json.JSONDecodeError as e:
        logger.warning("Resume–job fit: invalid JSON from LLM: %s", e)
        raise ValueError("Invalid response from resume–job fit analysis.") from e
    except ValueError:
        raise
    except Exception as e:
        logger.warning("Resume–job fit: LLM call failed: %s", e)
        raise ValueError("Resume–job fit analysis failed.") from e
