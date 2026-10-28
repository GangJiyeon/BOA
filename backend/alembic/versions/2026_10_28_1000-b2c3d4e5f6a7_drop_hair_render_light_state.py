"""drop unused hair render light generation state

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-10-28 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("hair_renders", "light_error")
    op.drop_column("hair_renders", "light_status")


def downgrade() -> None:
    op.add_column("hair_renders", sa.Column("light_status", sa.String(length=20), nullable=True))
    op.add_column("hair_renders", sa.Column("light_error", sa.String(length=300), nullable=True))
