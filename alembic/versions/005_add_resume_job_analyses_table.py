"""add resume_job_analyses table

Revision ID: 005
Revises: 004
Create Date: 2026-03-14

Stores skill-gap (and optional LLM fit) analysis per resume+job pair.
One row per (resume_id, job_posting_id); overwritten when analysis is re-run.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_job_analyses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_posting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "analyzed_at",
            postgresql.TIMESTAMP(timezone=False),
            server_default=sa.text("current_timestamp(0)"),
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
        sa.ForeignKeyConstraint(["resume_id"], ["resumes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint(
            "resume_id",
            "job_posting_id",
            name="uq_resume_job_analyses_resume_job",
        ),
    )
    op.create_index(
        op.f("ix_resume_job_analyses_id"),
        "resume_job_analyses",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resume_job_analyses_resume_id"),
        "resume_job_analyses",
        ["resume_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resume_job_analyses_job_posting_id"),
        "resume_job_analyses",
        ["job_posting_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_resume_job_analyses_job_posting_id"),
        table_name="resume_job_analyses",
    )
    op.drop_index(
        op.f("ix_resume_job_analyses_resume_id"),
        table_name="resume_job_analyses",
    )
    op.drop_index(op.f("ix_resume_job_analyses_id"), table_name="resume_job_analyses")
    op.drop_table("resume_job_analyses")
