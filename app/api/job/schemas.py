"""
Request/response schemas for job description extract API.
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class JobExtractResponse(BaseModel):
    """Payload returned after job description entity extraction."""

    entities: Dict[str, List[str]] = Field(
        ...,
        description="Only entity types with at least one value are included. Job poster NER: typically SKILLS_REQUIRED and SALARY (rule-based). Resume NER fallback: SKILL, OCCUPATION, EDUCATION, EXPERIENCE.",
    )
    raw_text: str | None = Field(
        default=None,
        description="Raw text used for extraction (if client sent file). Omitted if client sent text.",
    )
