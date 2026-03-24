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
    source_file_url: Optional[str] = Field(
        default=None,
        description="URL of the original uploaded file in S3, if saved.",
    )
    cv_score: Optional[float] = None
    cv_scored_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DeleteAllResumesResponse(BaseModel):
    """Payload returned after deleting all resumes."""

    deleted_count: int = Field(..., description="Number of resumes deleted.")


class DeleteResumeResponse(BaseModel):
    """Payload returned after deleting a single resume."""

    deleted: bool = Field(..., description="Whether the resume was deleted.")


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
    resume_id: uuid_pkg.UUID = Field(..., description="ID of the persisted resume row.")
    source_file_url: str | None = Field(
        default=None,
        description="Public URL of the uploaded file in S3 when a file was sent and S3 is configured.",
    )


class ResumeScoreResponse(BaseModel):
    """Payload returned from CV scoring (POST /score or GET /{resume_id}/score)."""

    score: float = Field(..., ge=0, le=100, description="Overall CV strength score (0-100).")
    breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Scores per dimension: content, structure, clarity.",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Actionable improvement suggestions.",
    )
    scored_at: Optional[datetime] = Field(
        default=None,
        description="When this score was computed (set when stored or returned from cache).",
    )


class ResumeExtractPreviewResponse(BaseModel):
    """Payload for preview endpoint: text passed to the model and resulting entities (no DB write)."""

    extracted_text: str = Field(
        ...,
        description="Exact text passed to the NER model (from PDF extraction or raw input). Use to monitor/debug input.",
    )
    entities: Dict[str, List[str]] = Field(
        ...,
        description="Entities extracted by the model from extracted_text.",
    )
