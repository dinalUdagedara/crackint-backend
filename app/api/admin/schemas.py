"""Request/response schemas for admin API."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserListItem(BaseModel):
    """User row for admin list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    is_admin: bool
    created_at: datetime
    updated_at: datetime


class AdminUserUpdate(BaseModel):
    """PATCH body for admin user update."""

    name: Optional[str] = Field(default=None, min_length=1)
    email: Optional[EmailStr] = None


class AdminUserDeletePayload(BaseModel):
    """Summary returned after deleting a user and related data."""

    deleted_user_id: UUID
    prep_sessions_deleted: int
    cover_letters_deleted: int
    resumes_deleted: int
    job_postings_deleted: int


class AdminSessionListItem(BaseModel):
    """Prep session row for admin list with owner summary."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    resume_id: Optional[UUID] = None
    job_posting_id: Optional[UUID] = None
    mode: str
    status: str
    readiness_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime
