"""
Request/response schemas for prep session and message APIs.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

import uuid as uuid_pkg
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import MessageType, RoleLevel, SenderType, SessionMode, SessionStatus

QuestionTypeLiteral = Literal["technical", "behavioral", "system_design"]


class PrepSessionCreate(BaseModel):
    """Body to create a new preparation session."""

    user_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        description="User who owns the session (nullable until auth is added).",
    )
    resume_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        description="Associated resume ID, if any.",
    )
    job_posting_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        description="Associated job posting ID, if any.",
    )
    mode: SessionMode = Field(
        default=SessionMode.TARGETED,
        description="Session mode, e.g. TARGETED or QUICK_PRACTICE.",
    )


class PrepSessionSummary(BaseModel):
    """High-level summary fields for a session."""

    readiness_score: Optional[float] = Field(
        default=None,
        description="Overall readiness score for this session (0-100).",
    )
    strengths: Optional[str] = Field(
        default=None,
        description="Free-text strengths summary.",
    )
    areas_for_improvement: Optional[str] = Field(
        default=None,
        description="Free-text areas for improvement summary.",
    )


class PrepSessionRead(BaseModel):
    """Session record as returned in list/get responses (without messages by default)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid_pkg.UUID
    user_id: Optional[uuid_pkg.UUID] = None
    resume_id: Optional[uuid_pkg.UUID] = None
    job_posting_id: Optional[uuid_pkg.UUID] = None
    mode: SessionMode
    status: SessionStatus
    readiness_score: Optional[float] = None
    summary: Dict[str, Optional[str]]
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    """Body to append a new chat message in a session."""

    sender: SenderType = Field(
        ...,
        description="Sender of the message: USER or ASSISTANT.",
    )
    type: MessageType = Field(
        ...,
        description="Message type: QUESTION, ANSWER, or FEEDBACK.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Text content of the message.",
    )
    metadata: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Optional metadata such as scores, categories, etc.",
    )


class MessageRead(BaseModel):
    """Chat message as returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid_pkg.UUID
    session_id: uuid_pkg.UUID
    sender: SenderType
    type: MessageType
    content: str
    metadata: Dict[str, Optional[str]] = Field(
        ...,
        alias="meta",
    )
    created_at: datetime
    updated_at: datetime


class PrepSessionWithMessages(PrepSessionRead):
    """Session including its messages."""

    messages: List[MessageRead] = Field(
        default_factory=list,
        description="Messages in this session, ordered by created_at ascending.",
    )


# --- Session Q&A (next-question, evaluate-answer) ---


class NextQuestionRequest(BaseModel):
    """Body for POST /sessions/{id}/next-question."""

    question_type: Optional[QuestionTypeLiteral] = Field(
        default=None,
        description="Requested type: technical, behavioral, or system_design.",
    )
    role_level: Optional[RoleLevel] = Field(
        default=RoleLevel.ASE,
        description="Candidate level for question difficulty (default: ASE).",
    )


class NextQuestionPayload(BaseModel):
    """Payload returned when a new question is generated."""

    question: str = Field(..., description="Generated interview question.")
    difficulty: Optional[str] = Field(
        default=None,
        description="easy, medium, or hard.",
    )
    question_type: Optional[str] = Field(
        default=None,
        description="technical, behavioral, or system_design.",
    )
    message_id: uuid_pkg.UUID = Field(
        ...,
        description="ID of the stored Message (sender=ASSISTANT, type=QUESTION).",
    )


class EvaluateAnswerRequest(BaseModel):
    """Body for POST /sessions/{id}/evaluate-answer."""

    answer: str = Field(
        ...,
        min_length=1,
        description="The candidate's answer text to evaluate.",
    )


class EvaluateAnswerPayload(BaseModel):
    """Payload returned after evaluating an answer."""

    feedback: str = Field(..., description="Text feedback for the candidate.")
    score: int = Field(..., ge=0, le=100, description="Score 0-100.")
    dimension_tags: List[str] = Field(
        default_factory=list,
        description="Tags such as technical, communication, structure.",
    )
    message_id: uuid_pkg.UUID = Field(
        ...,
        description="ID of the stored Message (sender=ASSISTANT, type=FEEDBACK).",
    )

