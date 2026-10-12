"""add role_level to prep_sessions

Revision ID: 012
Revises: 011
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prep_sessions", sa.Column("role_level", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("prep_sessions", "role_level")
