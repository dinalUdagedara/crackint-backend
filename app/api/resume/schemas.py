"""
Request/response schemas for resume extract API.
"""

from typing import Dict, List

from pydantic import BaseModel, Field


class ResumeExtractTextRequest(BaseModel):
    """Body when client sends raw text instead of file."""

    text: str = Field(..., min_length=1, description="Raw resume text to extract entities from.")


class ResumeExtractResponse(BaseModel):
    """Payload returned after entity extraction."""

    entities: Dict[str, List[str]] = Field(
        ...,
        description="Extracted entities by type: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.",
    )
    raw_text: str | None = Field(
        default=None,
        description="Raw text used for extraction (if client sent file). Omitted if client sent text.",
    )
