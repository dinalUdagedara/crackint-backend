"""Schemas for match/skill-gap API."""

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SkillGapAlert(BaseModel):
    """Single alert from skill-gap analysis."""

    type: str = Field(
        ...,
        description="missing_skill | weak_experience | weak_education | location_mismatch",
    )
    message: str = Field(..., description="Human-readable alert message.")
    severity: str = Field(..., description="low | medium | high")


class LocationSuitability(BaseModel):
    """Job suitability by location: remote vs on-site, distance vs candidate location."""

    job_location_display: str = Field(
        default="",
        description="Parsed job location (city, country) or 'Remote'.",
    )
    is_remote: bool = Field(
        default=False,
        description="True if job is remote / work-from-home.",
    )
    candidate_location: str | None = Field(
        default=None,
        description="Candidate location from profile or CV (if provided).",
    )
    suitability: str = Field(
        ...,
        description="good | caution | unknown — good for remote or same region; caution if non-remote and far.",
    )
    message: str = Field(
        default="",
        description="Human-readable message (e.g. relocation note or remote highlight).",
    )
    highlight_remote_match: bool = Field(
        default=False,
        description="True when job is remote — highlight as better match regardless of distance.",
    )


class ResumeJobFitAnalysis(BaseModel):
    """Optional LLM-based resume–job fit analysis (when RESUME_JOB_FIT_LLM_ENABLED and raw text present)."""

    fit_score: float = Field(..., ge=0, le=100, description="How well the resume fits this job (0-100).")
    summary: str = Field(default="", description="Short narrative summary of fit and gaps.")
    tailored_suggestions: List[str] = Field(
        default_factory=list,
        description="Job-specific improvement or highlight suggestions.",
    )


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
    llm_fit_analysis: ResumeJobFitAnalysis | None = Field(
        default=None,
        description="LLM analysis of resume vs job (fit score, summary, tailored suggestions) when enabled and raw text available.",
    )
    location_suitability: LocationSuitability | None = Field(
        default=None,
        description="Job suitability by location (remote vs on-site, distance vs candidate location); alerts when non-remote and far.",
    )
    analyzed_at: datetime | None = Field(
        default=None,
        description="When this analysis was run (set when stored or returned from cache).",
    )


class SkillGapRequest(BaseModel):
    """Request body for skill-gap analysis."""

    resume_id: str = Field(..., description="Resume UUID.")
    job_posting_id: str = Field(..., description="Job posting UUID.")
    candidate_location: str | None = Field(
        default=None,
        description="Optional candidate location (city, country) from profile or CV for location suitability.",
    )
