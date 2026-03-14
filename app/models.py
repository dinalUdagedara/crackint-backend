"""
SQLModel table definitions: base mixins, User, Resume.
"""

import uuid as uuid_pkg
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import ConfigDict
from sqlalchemy import Column, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class UUIDModel(SQLModel):
    """Base mixin: UUID primary key with server default."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid_pkg.UUID = Field(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
        sa_column_kwargs={"server_default": text("gen_random_uuid()"), "unique": True},
    )


class TimestampModel(SQLModel):
    """Base mixin: created_at and updated_at with server defaults."""

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime = Field(
        default_factory=datetime.now,
        nullable=False,
        sa_column_kwargs={"server_default": text("current_timestamp(0)")},
    )

    updated_at: datetime = Field(
        default_factory=datetime.now,
        nullable=False,
        sa_column_kwargs={
            "server_default": text("current_timestamp(0)"),
            "onupdate": text("current_timestamp(0)"),
        },
    )


class User(UUIDModel, TimestampModel, table=True):
    """User table: id, name, email, hashed_password, timestamps."""

    __tablename__ = "users"

    name: str = Field(nullable=False)
    email: str = Field(nullable=False, index=True, unique=True)
    hashed_password: str = Field(nullable=False)


class Resume(UUIDModel, TimestampModel, table=True):
    """Resume table: extracted entities (JSONB) and optional raw text; user_id set from auth."""

    __tablename__ = "resumes"

    user_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    raw_text: Optional[str] = Field(default=None, nullable=True)


class JobPosting(UUIDModel, TimestampModel, table=True):
    """Job posting table: extracted entities (JSONB) and optional raw text; user_id set from auth."""

    __tablename__ = "job_postings"

    user_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    entities: Dict[str, List[str]] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    raw_text: Optional[str] = Field(default=None, nullable=True)
    location: Optional[str] = Field(default=None, nullable=True)
    deadline: Optional[datetime] = Field(default=None, nullable=True)


class PrepSession(UUIDModel, TimestampModel, table=True):
    """Prep session table: links user, resume, job posting and stores high-level summary."""

    __tablename__ = "prep_sessions"

    user_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    resume_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="resumes.id",
        nullable=True,
        index=True,
    )
    job_posting_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="job_postings.id",
        nullable=True,
        index=True,
    )

    mode: str = Field(
        default="TARGETED",
        nullable=False,
        description="Session mode, e.g. TARGETED or QUICK_PRACTICE",
    )
    status: str = Field(
        default="ACTIVE",
        nullable=False,
        description="Session status, e.g. ACTIVE or COMPLETED",
    )
    readiness_score: Optional[float] = Field(
        default=None,
        nullable=True,
        description="Overall readiness score for this session (0-100).",
    )
    summary: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        sa_column=Column(
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        description="Summary data such as strengths and areas_for_improvement.",
    )


class Message(UUIDModel, TimestampModel, table=True):
    """Chat message within a prep session."""

    __tablename__ = "messages"

    session_id: uuid_pkg.UUID = Field(
        foreign_key="prep_sessions.id",
        nullable=False,
        index=True,
    )
    sender: str = Field(
        nullable=False,
        description="Sender of the message: USER or ASSISTANT.",
    )
    type: str = Field(
        nullable=False,
        description="Message type: QUESTION, ANSWER, or FEEDBACK.",
    )
    content: str = Field(
        nullable=False,
        description="Message content (text).",
    )
    meta: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        sa_column=Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        description="Optional metadata such as scores, categories, etc.",
    )


class ResumeJobAnalysis(UUIDModel, TimestampModel, table=True):
    """Stored result of resume vs job skill-gap (and optional LLM fit) analysis. One row per (resume_id, job_posting_id); overwritten on re-run."""

    __tablename__ = "resume_job_analyses"
    __table_args__ = (UniqueConstraint("resume_id", "job_posting_id", name="uq_resume_job_analyses_resume_job"),)

    resume_id: uuid_pkg.UUID = Field(
        foreign_key="resumes.id",
        nullable=False,
        index=True,
    )
    job_posting_id: uuid_pkg.UUID = Field(
        foreign_key="job_postings.id",
        nullable=False,
        index=True,
    )
    result: Dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Full skill-gap response (missing_skills, severity, llm_fit_analysis, etc.) as JSON.",
    )
    analyzed_at: datetime = Field(
        default_factory=datetime.now,
        nullable=False,
        sa_column_kwargs={"server_default": text("current_timestamp(0)")},
        description="When the analysis was run.",
    )


class CoverLetter(UUIDModel, TimestampModel, table=True):
    """Cover letter table: stores generated cover letters per user + resume + job posting."""

    __tablename__ = "cover_letters"

    user_id: uuid_pkg.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
    )
    resume_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="resumes.id",
        nullable=True,
        index=True,
    )
    job_posting_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="job_postings.id",
        nullable=True,
        index=True,
    )
    session_id: Optional[uuid_pkg.UUID] = Field(
        default=None,
        foreign_key="prep_sessions.id",
        nullable=True,
        index=True,
    )
    content: str = Field(
        nullable=False,
        description="Latest generated (or edited) cover letter text.",
    )
    meta: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        sa_column=Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=text("'{}'::jsonb"),
        ),
        description="Metadata such as model, temperature, tone, language, etc.",
    )
