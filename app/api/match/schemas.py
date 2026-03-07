"""Schemas for match/skill-gap API."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SkillGapAlert(BaseModel):
    """Single alert from skill-gap analysis."""

    type: str = Field(..., description="missing_skill | weak_experience | weak_education")
    message: str = Field(..., description="Human-readable alert message.")
    severity: str = Field(..., description="low | medium | high")


class SkillGapResponse(BaseModel):
    """Response from skill-gap analysis."""

    missing_skills: List[str] = Field(
        default_factory=list,
        description="Job-required skills not found in resume.",
    )
    weak_experience: bool = Field(
        default=False,
        description="Whether experience appears insufficient.",
    )
    weak_experience_message: str | None = Field(
        default=None,
        description="Explanation if weak_experience is true.",
    )
    weak_education: bool = Field(
        default=False,
        description="Whether education appears insufficient.",
    )
    weak_education_message: str | None = Field(
        default=None,
        description="Explanation if weak_education is true.",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Actionable improvement suggestions.",
    )
    severity: str = Field(
        ...,
        description="Overall severity: low | medium | high",
    )
    alerts: List[SkillGapAlert] = Field(
        default_factory=list,
        description="Structured alerts for UI display.",
    )


class SkillGapRequest(BaseModel):
    """Request body for skill-gap analysis."""

    resume_id: str = Field(..., description="Resume UUID.")
    job_posting_id: str = Field(..., description="Job posting UUID.")
