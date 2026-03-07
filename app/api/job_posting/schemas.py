"""
Request/response schemas for job posting APIs.
"""

from datetime import datetime
from typing import Dict, List, Optional

import uuid as uuid_pkg
from pydantic import BaseModel, ConfigDict, Field


class JobPostingListItem(BaseModel):
    """Single job posting record as returned in list/get responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid_pkg.UUID
    user_id: Optional[uuid_pkg.UUID] = None
    entities: Dict[str, List[str]] = Field(
        ...,
        description="Extracted job entities (JOB_TITLE, COMPANY, LOCATION, SALARY, SKILLS_REQUIRED, EXPERIENCE_REQUIRED, EDUCATION_REQUIRED, JOB_TYPE, etc.).",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Raw job description text used for extraction, when available.",
    )
    location: Optional[str] = None
    deadline: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JobPostingCreate(BaseModel):
    """Body when creating a job posting record from existing extracted entities."""

    user_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        description="Ignored; owner is set from the authenticated user.",
    )
    entities: Dict[str, List[str]] = Field(
        ...,
        description="Extracted job entities from the /jobs/extract endpoint.",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Optional raw job description text used for extraction.",
    )
    location: Optional[str] = Field(
        default=None,
        description="Optional normalized location string.",
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Optional job or interview deadline.",
    )


class JobPostingUpdate(BaseModel):
    """Body for PATCH: update only the fields you send. Omitted keys are left unchanged."""

    entities: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Entity keys to merge into existing entities. Replaces only provided keys.",
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Raw job description text.",
    )
    location: Optional[str] = Field(
        default=None,
        description="Normalized location string.",
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Job or interview deadline.",
    )

