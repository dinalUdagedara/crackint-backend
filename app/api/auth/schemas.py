"""Request/response schemas for auth API."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class RegisterRequest(BaseModel):
    """Body for user registration."""

    email: EmailStr = Field(..., description="User email (unique).")
    password: str = Field(..., min_length=8, description="Plain password (min 8 chars).")
    name: str = Field(..., min_length=1, description="Display name.")


class LoginRequest(BaseModel):
    """Body for login."""

    email: EmailStr = Field(..., description="User email.")
    password: str = Field(..., description="Plain password.")


class GoogleTokenRequest(BaseModel):
    """Body for Google login: Google OAuth ID token from the client."""

    id_token: str = Field(..., description="Google OAuth ID token from the frontend.")


class UserRead(BaseModel):
    """User payload returned in auth responses (no password)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    is_admin: bool = False
    profile_image_url: Optional[str] = None
    created_at: datetime


class UserProfileUpdate(BaseModel):
    """Body for PATCH /auth/me: update profile fields (send only fields to change)."""

    name: str | None = Field(default=None, min_length=1, description="New display name.")
    email: EmailStr | None = Field(default=None, description="New email (must be unique).")
    profile_image_url: str | None = Field(
        default=None,
        description="Public URL of profile image (e.g. from POST /uploads/image?purpose=profile). Omit unchanged; send null to clear.",
    )


class TokenResponse(BaseModel):
    """Login response: access token and user info."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
