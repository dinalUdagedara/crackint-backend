from typing import Optional

import uuid as uuid_pkg
from pydantic import BaseModel, Field

from app.models import CoverLetter


class CoverLetterGenerateRequest(BaseModel):
    """Request body for generating a cover letter."""

    resume_id: Optional[uuid_pkg.UUID] = Field(
        default=None, description="Resume ID. Required if session_id not provided."
    )
    job_posting_id: Optional[uuid_pkg.UUID] = Field(
        default=None, description="Job posting ID. Required if session_id not provided."
    )
    session_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        description=(
            "Prep session ID. If provided, resume/job IDs can be inferred from the session."
        ),
    )
    tone: Optional[str] = Field(
        default="formal",
        description="Desired tone for cover letter (e.g., formal, warm, concise).",
    )
    length: Optional[str] = Field(
        default="medium",
        description="Approximate length hint (e.g., short, medium, long).",
    )
    user_notes: Optional[str] = Field(
        default=None,
        description="Optional notes from the user about goals or points to emphasize.",
    )


class CoverLetterRead(BaseModel):
    """Cover letter as returned to clients."""

    id: uuid_pkg.UUID
    resume_id: Optional[uuid_pkg.UUID]
    job_posting_id: Optional[uuid_pkg.UUID]
    session_id: Optional[uuid_pkg.UUID]
    content: str

    @classmethod
    def from_model(cls, model: CoverLetter) -> "CoverLetterRead":
        return cls(
            id=model.id,
            resume_id=model.resume_id,
            job_posting_id=model.job_posting_id,
            session_id=model.session_id,
            content=model.content,
        )


class CoverLetterUpdateRequest(BaseModel):
    """Request body for updating an existing cover letter's content."""

    content: str = Field(
        ...,
        min_length=1,
        description="Updated cover letter text (overwrites existing content).",
    )


class CoverLetterDeleteResponse(BaseModel):
    """Response indicating whether a cover letter was deleted."""

    deleted: bool = Field(
        ...,
        description="True if a cover letter existed and was deleted; False if none was found.",
    )


