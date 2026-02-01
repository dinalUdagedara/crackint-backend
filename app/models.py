"""
SQLModel table definitions: base mixins, User, Resume.
"""

import uuid as uuid_pkg
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import ConfigDict
from sqlalchemy import Column, text
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
    """User table: minimal fields for now (id, name, email, timestamps)."""

    __tablename__ = "users"

    name: str = Field(nullable=False)
    email: str = Field(nullable=False, index=True, unique=True)


class Resume(UUIDModel, TimestampModel, table=True):
    """Resume table: extracted entities (JSONB) and optional raw text; user_id nullable until auth."""

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
