"""add source_file_url to resumes and job_postings

Revision ID: 010
Revises: 009
Create Date: 2026-03-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "resumes",
        sa.Column("source_file_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "job_postings",
        sa.Column("source_file_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "source_file_url")
    op.drop_column("resumes", "source_file_url")
