"""Schemas for match/skill-gap API."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SkillGapAlert(BaseModel):
    """Single alert from skill-gap analysis."""

    type: str = Field(..., description="missing_skill | weak_experience | weak_education")
    message: str = Field(..., description="Human-readable alert message.")
    severity: str = Field(..., description="low | medium | high")


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


class SkillGapRequest(BaseModel):
    """Request body for skill-gap analysis."""

    resume_id: str = Field(..., description="Resume UUID.")
    job_posting_id: str = Field(..., description="Job posting UUID.")
