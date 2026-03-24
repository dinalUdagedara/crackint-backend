"""
Request/response schemas for job posting APIs.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

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
    source_file_url: Optional[str] = Field(
        default=None,
        description="URL of the original uploaded job file in S3 (from /jobs/extract or manual upload).",
    )
    location: Optional[str] = None
    deadline: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # Job tracker / job detail (optional)
    display_order: Optional[int] = None
    cover_image_url: Optional[str] = None
    notes: Optional[str] = None
    questions_to_ask: Optional[str] = None
    interview_at: Optional[datetime] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    talking_points: Optional[str] = None
    application_url: Optional[str] = None
    stage: Optional[str] = None


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
    source_file_url: Optional[str] = Field(
        default=None,
        description="Optional URL of uploaded job file (e.g. from /jobs/extract response or POST /uploads/document).",
    )
    location: Optional[str] = Field(
        default=None,
        description="Optional normalized location string.",
    )
    deadline: Optional[datetime] = Field(
        default=None,
        description="Optional job or interview deadline.",
    )
    cover_image_url: Optional[str] = Field(default=None, description="Optional cover image URL.")
    notes: Optional[str] = Field(default=None, description="Optional free-form notes.")
    questions_to_ask: Optional[str] = Field(default=None, description="Questions to ask in the interview.")
    interview_at: Optional[datetime] = Field(default=None, description="Interview date/time (ISO 8601).")
    contact_name: Optional[str] = Field(default=None, description="Recruiter/contact name.")
    contact_email: Optional[str] = Field(default=None, description="Recruiter/contact email.")
    talking_points: Optional[str] = Field(default=None, description="Key points to mention.")
    application_url: Optional[str] = Field(default=None, description="Link to job ad or application page.")
    stage: Optional[str] = Field(default=None, description="Application stage, e.g. saved, applied, interview, offer.")


class JobPostingReorderRequest(BaseModel):
    """Body for PUT /job-postings/reorder: list of job posting IDs in desired order."""

    order: List[uuid_pkg.UUID] = Field(
        ...,
        description="Job posting IDs in the desired display order (index = display_order).",
    )


class ReorderResponse(BaseModel):
    """Payload returned after bulk reorder."""

    updated: bool = Field(..., description="Whether the order was updated.")


class JobPostingNearDeadlineItem(BaseModel):
    """Job posting with its next upcoming milestone (deadline or interview) for notification/reminder use."""

    job: JobPostingListItem = Field(..., description="The job posting.")
    next_milestone_date: datetime = Field(
        ...,
        description="The date of the upcoming milestone (deadline or interview).",
    )
    next_milestone_type: Literal["deadline", "interview"] = Field(
        ...,
        description="Whether the milestone is an application deadline or an interview date.",
    )
    days_until: int = Field(
        ...,
        description="Whole days until the milestone (0 = today, 1 = tomorrow).",
    )


class DeleteJobPostingResponse(BaseModel):
    """Payload returned after deleting a single job posting."""

    deleted: bool = Field(..., description="Whether the job posting was deleted.")


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
    display_order: Optional[int] = Field(default=None, description="User-defined display order.")
    cover_image_url: Optional[str] = Field(default=None, description="Cover image URL (null to clear).")
    source_file_url: Optional[str] = Field(
        default=None,
        description="Uploaded job file URL in S3 (null to clear).",
    )
    notes: Optional[str] = Field(default=None, description="Free-form notes.")
    questions_to_ask: Optional[str] = Field(default=None, description="Questions to ask in the interview.")
    interview_at: Optional[datetime] = Field(default=None, description="Interview date/time (ISO 8601).")
    contact_name: Optional[str] = Field(default=None, description="Recruiter/contact name.")
    contact_email: Optional[str] = Field(default=None, description="Recruiter/contact email.")
    talking_points: Optional[str] = Field(default=None, description="Key points to mention.")
    application_url: Optional[str] = Field(default=None, description="Link to job ad or application page.")
    stage: Optional[str] = Field(default=None, description="Application stage, e.g. saved, applied, interview, offer.")

