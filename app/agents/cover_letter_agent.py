"""
Cover letter generation agent.

Uses resume + job posting context (entities and optional raw text) to generate
one tailored cover letter as plain text.
"""

import json
import logging
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings


logger = logging.getLogger(__name__)


class CoverLetterContext(BaseModel):
    """Structured context passed to the cover letter LLM."""

    resume_entities: Dict[str, List[str]] = Field(
        default_factory=dict, description="NER entities extracted from the resume."
    )
    job_entities: Dict[str, List[str]] = Field(
        default_factory=dict, description="NER entities extracted from the job posting."
    )
    resume_text: Optional[str] = Field(
        default=None, description="Raw resume text, if available."
    )
    job_text: Optional[str] = Field(
        default=None, description="Raw job posting text, if available."
    )
    tone: Optional[str] = Field(
        default="formal",
        description="Desired tone for the cover letter (e.g., formal, warm, concise).",
    )
    length: Optional[str] = Field(
        default="medium",
        description="Approximate length hint (e.g., short, medium, long).",
    )
    user_notes: Optional[str] = Field(
        default=None,
        description="Optional free-form notes from the user about their goals or preferences.",
    )
    session_summary: Optional[str] = Field(
        default=None,
        description="Optional short summary of session strengths/weaknesses to personalize the letter.",
    )


COVER_LETTER_SYSTEM_PROMPT = """You are an expert career coach and professional writer.
Your task is to write a tailored cover letter for a specific job based on the candidate's resume and the job description.

You will receive:
- Resume entities (skills, experience, education, projects, etc.)
- Job posting entities (title, company, skills required, responsibilities, etc.)
- Optional raw text of the resume and job posting
- Optional notes from the candidate and a brief session summary

Write a cover letter that:
- Is addressed generically (e.g., \"Dear Hiring Manager,\") unless a company name or contact is clearly available.
- Connects the candidate's most relevant skills and experiences to the job requirements.
- Highlights 1–3 concrete achievements or projects where possible.
- Shows enthusiasm for the specific role and company.
- Sounds natural, confident, and concise (avoid excessive buzzwords).

Formatting rules:
- Output plain text only (no markdown, no bullets).
- Include: greeting, 2–4 body paragraphs, and a closing with the candidate thanking the reader.
- Do NOT invent personal details like phone numbers, email, or addresses.
- If some information is missing (e.g., company name), write a reasonable generic cover letter without apologizing for missing details.
"""


def _is_cover_letter_agent_available() -> bool:
    """True if cover letter agent is enabled and API key is set."""
    return bool(
        getattr(settings, "COVER_LETTER_AGENT_ENABLED", False)
        and getattr(settings, "OPENAI_API_KEY", None)
    )


async def generate_cover_letter(context: CoverLetterContext) -> str:
    """
    Call LLM to generate a cover letter.

    Raises ValueError if agent disabled/API key missing or LLM fails.
    """
    if not _is_cover_letter_agent_available():
        raise ValueError(
            "Cover letter agent is disabled (COVER_LETTER_AGENT_ENABLED=false or OPENAI_API_KEY unset)."
        )

    resume_json = json.dumps(context.resume_entities, ensure_ascii=False, indent=2)
    job_json = json.dumps(context.job_entities, ensure_ascii=False, indent=2)

    user_parts: list[str] = [
        "Resume entities:",
        resume_json,
        "",
        "Job posting entities:",
        job_json,
        "",
    ]

    if context.resume_text:
        user_parts.extend(["Raw resume text:", context.resume_text, ""])
    if context.job_text:
        user_parts.extend(["Raw job description text:", context.job_text, ""])
    if context.user_notes:
        user_parts.extend(["Candidate notes:", context.user_notes, ""])
    if context.session_summary:
        user_parts.extend(["Session summary:", context.session_summary, ""])

    user_parts.append(f"Desired tone: {context.tone or 'formal'}")
    user_parts.append(f"Desired length: {context.length or 'medium'}")

    user_content = "\n".join(user_parts)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("Cover letter: could not create OpenAI client: %s", e)
        raise ValueError("OpenAI client unavailable.") from e

    model = getattr(settings, "COVER_LETTER_AGENT_MODEL", "gpt-4o-mini")
    temperature = getattr(settings, "COVER_LETTER_AGENT_TEMPERATURE", 0.7)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned empty content for cover letter.")
        return content
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        logger.warning("Cover letter generation failed: %s", e)
        raise ValueError("Cover letter generation failed.") from e

