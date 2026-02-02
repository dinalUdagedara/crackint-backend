"""
Request/response schemas for resume extract API.
"""

from datetime import datetime
from typing import Dict, List, Optional

import uuid as uuid_pkg
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResumeListItem(BaseModel):
    """Single resume record as returned in list/get responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid_pkg.UUID
    user_id: Optional[uuid_pkg.UUID] = None
    entities: Dict[str, List[str]] = Field(..., description="NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.")
    raw_text: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DeleteAllResumesResponse(BaseModel):
    """Payload returned after deleting all resumes."""

    deleted_count: int = Field(..., description="Number of resumes deleted.")


# Entity types allowed for resume entities (used by PATCH entities endpoint).
RESUME_ENTITY_TYPES = frozenset({"NAME", "EMAIL", "SKILL", "OCCUPATION", "EDUCATION", "EXPERIENCE"})


class ResumeEntitiesUpdate(BaseModel):
    """Body for PATCH: update only the entity fields you send. Omitted keys are left unchanged."""

    entities: Dict[str, List[str]] = Field(
        ...,
        min_length=1,
        description="Entity type -> list of values. Allowed keys: NAME, EMAIL, SKILL, OCCUPATION, EDUCATION, EXPERIENCE.",
    )

    @field_validator("entities")
    @classmethod
    def validate_entity_keys(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        invalid = set(v) - RESUME_ENTITY_TYPES
        if invalid:
            raise ValueError(f"Invalid entity keys: {sorted(invalid)}. Allowed: {sorted(RESUME_ENTITY_TYPES)}")
        return v


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
