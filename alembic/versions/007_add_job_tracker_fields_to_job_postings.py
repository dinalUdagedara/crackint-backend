"""add job tracker fields to job_postings

Revision ID: 007
Revises: 006
Create Date: 2026-03-15

Adds display_order, cover_image_url, notes, questions_to_ask, interview_at,
contact_name, contact_email, talking_points, application_url, stage to job_postings
for job tracker and job detail page support.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("display_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("cover_image_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("questions_to_ask", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column(
            "interview_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "job_postings",
        sa.Column("contact_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("contact_email", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("talking_points", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("application_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("stage", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "stage")
    op.drop_column("job_postings", "application_url")
    op.drop_column("job_postings", "talking_points")
    op.drop_column("job_postings", "contact_email")
    op.drop_column("job_postings", "contact_name")
    op.drop_column("job_postings", "interview_at")
    op.drop_column("job_postings", "questions_to_ask")
    op.drop_column("job_postings", "notes")
    op.drop_column("job_postings", "cover_image_url")
    op.drop_column("job_postings", "display_order")
