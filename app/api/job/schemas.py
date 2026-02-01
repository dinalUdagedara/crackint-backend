"""
Request/response schemas for job description extract API.
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class JobExtractResponse(BaseModel):
    """Payload returned after job description entity extraction."""

    entities: Dict[str, List[str]] = Field(
        ...,
        description="When job poster NER is used: JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE. When fallback (resume NER): SKILL, OCCUPATION, EDUCATION, EXPERIENCE.",
    )
    raw_text: str | None = Field(
        default=None,
        description="Raw text used for extraction (if client sent file). Omitted if client sent text.",
    )
