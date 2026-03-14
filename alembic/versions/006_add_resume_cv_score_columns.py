"""add resume cv_score columns

Revision ID: 006
Revises: 005
Create Date: 2026-03-14

Adds cv_score, cv_breakdown, cv_suggestions, cv_scored_at to resumes
for storing latest LLM CV score (Option A: columns on Resume).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("cv_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "resumes",
        sa.Column(
            "cv_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "resumes",
        sa.Column(
            "cv_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "resumes",
        sa.Column(
            "cv_scored_at",
            postgresql.TIMESTAMP(timezone=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("resumes", "cv_scored_at")
    op.drop_column("resumes", "cv_suggestions")
    op.drop_column("resumes", "cv_breakdown")
    op.drop_column("resumes", "cv_score")
