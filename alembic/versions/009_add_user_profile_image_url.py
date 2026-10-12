"""add profile_image_url to users

Revision ID: 009
Revises: 008
Create Date: 2026-03-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("profile_image_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_image_url")
