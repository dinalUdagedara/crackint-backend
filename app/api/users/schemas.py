"""Request/response schemas for users API (readiness dashboard, etc.)."""

import uuid as uuid_pkg
from typing import Dict, Optional

from pydantic import BaseModel, Field


class ReadinessSummaryResponse(BaseModel):
    """Dashboard-friendly readiness summary for the current user."""

    combined_score: float = Field(..., description="Combined readiness score 0-100.")
    trend: str = Field(
        ...,
        description='Trend label from aggregator: "improving", "stable", or "declining".',
    )
    cv_score: Optional[float] = Field(
        default=None,
        description="CV score 0-100 if available, otherwise null.",
    )
    session_avg: Optional[float] = Field(
        default=None,
        description="Average readiness across recent sessions, if any.",
    )
    gap_severity: Optional[str] = Field(
        default=None,
        description="Skill-gap severity label if gap analysis was computed.",
    )
    session_count_total: int = Field(
        ...,
        description="Total number of prep sessions owned by the current user.",
    )
    session_count_with_scores: int = Field(
        ...,
        description="Number of sessions that have at least one FEEDBACK score.",
    )
    last_n_sessions: int = Field(
        ...,
        description="Number of recent sessions considered when computing session_avg and difficulty_distribution.",
    )
    difficulty_distribution: Dict[str, int] = Field(
        ...,
        description='Counts of QUESTION messages by difficulty in recent sessions (easy/medium/hard), e.g. {"easy": 4, "medium": 7, "hard": 2}.',
    )


class ReadinessTrendItem(BaseModel):
    """Single point in the readiness trend over sessions."""

    session_id: uuid_pkg.UUID = Field(..., description="Prep session ID.")
    created_at: str = Field(
        ...,
        description="Session creation timestamp (ISO 8601).",
    )
    mode: str = Field(
        ...,
        description="Session mode, e.g. TARGETED, QUICK_PRACTICE, TUTOR_CHAT.",
    )
    readiness_score: Optional[float] = Field(
        default=None,
        description="Readiness score for this session if feedback scores exist.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional human-friendly session title from summary, if present.",
    )
