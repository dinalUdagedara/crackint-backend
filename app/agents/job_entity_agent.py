"""
Optional AI agent to validate and correct NER-extracted job description entities.
Uses an LLM grounded on the raw job description text; returns corrected entities or falls back to NER output.
"""

import json
import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# Required entity keys; must match job poster NER output shape.
JOB_ENTITY_KEYS = (
    "JOB_TITLE",
    "COMPANY",
    "LOCATION",
    "SALARY",
    "SKILLS_REQUIRED",
    "EXPERIENCE_REQUIRED",
    "EDUCATION_REQUIRED",
    "JOB_TYPE",
)


class JobEntitiesSchema(BaseModel):
    """Strict schema for LLM response: exactly eight keys, each a list of strings."""

    JOB_TITLE: List[str] = Field(default_factory=list, description="Job title(s).")
    COMPANY: List[str] = Field(default_factory=list, description="Company name(s).")
    LOCATION: List[str] = Field(default_factory=list, description="Location(s).")
    SALARY: List[str] = Field(default_factory=list, description="Salary information.")
    SKILLS_REQUIRED: List[str] = Field(
        default_factory=list, description="Required skills."
    )
    EXPERIENCE_REQUIRED: List[str] = Field(
        default_factory=list, description="Required experience."
    )
    EDUCATION_REQUIRED: List[str] = Field(
        default_factory=list, description="Required education."
    )
    JOB_TYPE: List[str] = Field(
        default_factory=list, description="Job type (full-time, part-time, etc.)."
    )


SYSTEM_PROMPT = """You are a job description entity checker. You will receive raw job description text and a JSON object of already-extracted entities with these exact keys: JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE. Each key maps to a list of strings.

Your task: Check whether all relevant information from the job description text is captured in the entities. If something is missing or wrong, produce a corrected JSON object with the same eight keys. If the extraction looks complete and correct, you may return it unchanged.

Rules:
- Only output entities that appear in the provided job description text. Do not invent job titles, companies, skills, salaries, or requirements.
- Return a single JSON object with exactly these keys: JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE. Each value must be a list of strings (possibly empty).
- Do not include any explanation or markdown; output only the JSON object."""


def _entities_to_dict(schema: JobEntitiesSchema) -> Dict[str, List[str]]:
    """Convert Pydantic schema to the API entity dict (eight keys, list of strings)."""
    return {k: getattr(schema, k) for k in JOB_ENTITY_KEYS}


def _is_agent_available() -> bool:
    """True if agent is enabled and API key is set."""
    return bool(
        getattr(settings, "JOB_ENTITY_AGENT_ENABLED", False)
        and getattr(settings, "OPENAI_API_KEY", None)
    )


async def validate_and_correct_entities(
    raw_text: str,
    entities: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Optionally validate and correct NER entities using an LLM grounded on raw_text.
    If the agent is disabled, API key missing, or the LLM call fails, returns the original entities.
    """
    if not _is_agent_available():
        logger.info(
            "Job entity agent: skipped (JOB_ENTITY_AGENT_ENABLED=false or OPENAI_API_KEY unset), returning NER entities"
        )
        return entities

    logger.info(
        "Job entity agent: running validation (raw_text_len=%d, NER entities: JOB_TITLE=%d, COMPANY=%d, LOCATION=%d, SALARY=%d, SKILLS_REQUIRED=%d, EXPERIENCE_REQUIRED=%d, EDUCATION_REQUIRED=%d, JOB_TYPE=%d)",
        len(raw_text),
        len(entities.get("JOB_TITLE", [])),
        len(entities.get("COMPANY", [])),
        len(entities.get("LOCATION", [])),
        len(entities.get("SALARY", [])),
        len(entities.get("SKILLS_REQUIRED", [])),
        len(entities.get("EXPERIENCE_REQUIRED", [])),
        len(entities.get("EDUCATION_REQUIRED", [])),
        len(entities.get("JOB_TYPE", [])),
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.warning("Job entity agent: could not create OpenAI client: %s", e)
        return entities

    entities_json = json.dumps(entities, ensure_ascii=False)
    user_content = f"""Job description text:
---
{raw_text}
---

Current extracted entities (JSON):
{entities_json}

Return a single JSON object with keys JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE. Each value is a list of strings. Only include information that appears in the job description text above."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            logger.warning(
                "Job entity agent: LLM returned empty content, using NER output"
            )
            return entities

        # Strip markdown code fence if present
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        parsed = json.loads(content)

        # Coerce each value to list of strings (LLM may return wrong types)
        def to_str_list(val: object) -> List[str]:
            if not isinstance(val, list):
                return []
            return [str(x).strip() for x in val if x is not None]

        schema = JobEntitiesSchema(
            JOB_TITLE=to_str_list(parsed.get("JOB_TITLE")),
            COMPANY=to_str_list(parsed.get("COMPANY")),
            LOCATION=to_str_list(parsed.get("LOCATION")),
            SALARY=to_str_list(parsed.get("SALARY")),
            SKILLS_REQUIRED=to_str_list(parsed.get("SKILLS_REQUIRED")),
            EXPERIENCE_REQUIRED=to_str_list(parsed.get("EXPERIENCE_REQUIRED")),
            EDUCATION_REQUIRED=to_str_list(parsed.get("EDUCATION_REQUIRED")),
            JOB_TYPE=to_str_list(parsed.get("JOB_TYPE")),
        )
        corrected = _entities_to_dict(schema)
        logger.info(
            "Job entity agent: corrected entities (JOB_TITLE=%d, COMPANY=%d, LOCATION=%d, SALARY=%d, SKILLS_REQUIRED=%d, EXPERIENCE_REQUIRED=%d, EDUCATION_REQUIRED=%d, JOB_TYPE=%d)",
            len(corrected["JOB_TITLE"]),
            len(corrected["COMPANY"]),
            len(corrected["LOCATION"]),
            len(corrected["SALARY"]),
            len(corrected["SKILLS_REQUIRED"]),
            len(corrected["EXPERIENCE_REQUIRED"]),
            len(corrected["EDUCATION_REQUIRED"]),
            len(corrected["JOB_TYPE"]),
        )
        return corrected
    except Exception as e:
        logger.warning(
            "Job entity agent: LLM call or parse failed, using NER output: %s", e
        )
        return entities
