"""add cover_letters table

Revision ID: 004
Revises: 003
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cover_letters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=False),
            server_default=sa.text("current_timestamp(0)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=False),
            server_default=sa.text("current_timestamp(0)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["prep_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
    )
    op.create_index(op.f("ix_cover_letters_id"), "cover_letters", ["id"], unique=False)
    op.create_index(
        op.f("ix_cover_letters_user_id"),
        "cover_letters",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letters_resume_id"),
        "cover_letters",
        ["resume_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letters_job_posting_id"),
        "cover_letters",
        ["job_posting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letters_session_id"),
        "cover_letters",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cover_letters_session_id"), table_name="cover_letters")
    op.drop_index(op.f("ix_cover_letters_job_posting_id"), table_name="cover_letters")
    op.drop_index(op.f("ix_cover_letters_resume_id"), table_name="cover_letters")
    op.drop_index(op.f("ix_cover_letters_user_id"), table_name="cover_letters")
    op.drop_index(op.f("ix_cover_letters_id"), table_name="cover_letters")
    op.drop_table("cover_letters")

