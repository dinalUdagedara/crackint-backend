"""
Optional AI agent to validate and correct NER-extracted resume entities.
Uses an LLM grounded on the raw resume text; returns corrected entities or falls back to NER output.
"""

import json
import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)

# Required entity keys; must match NER output shape.
RESUME_ENTITY_KEYS = ("NAME", "EMAIL", "SKILL", "OCCUPATION", "EDUCATION", "EXPERIENCE")


class ResumeEntitiesSchema(BaseModel):
    """Strict schema for LLM response: exactly six keys, each a list of strings."""

    NAME: List[str] = Field(default_factory=list, description="Full name(s).")
    EMAIL: List[str] = Field(default_factory=list, description="Email address(es).")
    SKILL: List[str] = Field(default_factory=list, description="Skills.")
    OCCUPATION: List[str] = Field(default_factory=list, description="Job titles/occupations.")
    EDUCATION: List[str] = Field(default_factory=list, description="Education entries.")
    EXPERIENCE: List[str] = Field(default_factory=list, description="Work experience entries.")


SYSTEM_PROMPT = """You are a resume entity checker. You will receive raw resume text and a JSON object of already-extracted entities with these exact keys: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE. Each key maps to a list of strings.

Your task: Check whether all relevant information from the resume text is captured in the entities. If something is missing or wrong, produce a corrected JSON object with the same six keys. If the extraction looks complete and correct, you may return it unchanged.

Rules:
- Only output entities that appear in the provided resume text. Do not invent names, skills, emails, or experiences.
- Return a single JSON object with exactly these keys: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE. Each value must be a list of strings (possibly empty).
- Do not include any explanation or markdown; output only the JSON object."""


def _entities_to_dict(schema: ResumeEntitiesSchema) -> Dict[str, List[str]]:
    """Convert Pydantic schema to the API entity dict (six keys, list of strings)."""
    return {k: getattr(schema, k) for k in RESUME_ENTITY_KEYS}


def _is_agent_available() -> bool:
    """True if agent is enabled and API key is set."""
    return bool(
        getattr(settings, "RESUME_ENTITY_AGENT_ENABLED", False)
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
            "Resume entity agent: skipped (RESUME_ENTITY_AGENT_ENABLED=false or OPENAI_API_KEY unset), returning NER entities"
        )
        return entities

    logger.info(
        "Resume entity agent: running validation (raw_text_len=%d, NER entities: NAME=%d, EMAIL=%d, SKILL=%d, OCCUPATION=%d, EDUCATION=%d, EXPERIENCE=%d)",
        len(raw_text),
        len(entities.get("NAME", [])),
        len(entities.get("EMAIL", [])),
        len(entities.get("SKILL", [])),
        len(entities.get("OCCUPATION", [])),
        len(entities.get("EDUCATION", [])),
        len(entities.get("EXPERIENCE", [])),
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.warning("Resume entity agent: could not create OpenAI client: %s", e)
        return entities

    entities_json = json.dumps(entities, ensure_ascii=False)
    user_content = f"""Resume text:
---
{raw_text}
---

Current extracted entities (JSON):
{entities_json}

Return a single JSON object with keys NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE. Each value is a list of strings. Only include information that appears in the resume text above."""

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
            logger.warning("Resume entity agent: LLM returned empty content, using NER output")
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

        schema = ResumeEntitiesSchema(
            NAME=to_str_list(parsed.get("NAME")),
            EMAIL=to_str_list(parsed.get("EMAIL")),
            SKILL=to_str_list(parsed.get("SKILL")),
            OCCUPATION=to_str_list(parsed.get("OCCUPATION")),
            EDUCATION=to_str_list(parsed.get("EDUCATION")),
            EXPERIENCE=to_str_list(parsed.get("EXPERIENCE")),
        )
        corrected = _entities_to_dict(schema)
        logger.info(
            "Resume entity agent: corrected entities (NAME=%d, EMAIL=%d, SKILL=%d, OCCUPATION=%d, EDUCATION=%d, EXPERIENCE=%d)",
            len(corrected["NAME"]),
            len(corrected["EMAIL"]),
            len(corrected["SKILL"]),
            len(corrected["OCCUPATION"]),
            len(corrected["EDUCATION"]),
            len(corrected["EXPERIENCE"]),
        )
        return corrected
    except Exception as e:
        logger.warning("Resume entity agent: LLM call or parse failed, using NER output: %s", e)
        return entities
