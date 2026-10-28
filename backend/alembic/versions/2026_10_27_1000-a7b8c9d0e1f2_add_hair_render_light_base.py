"""add hair render original hair color

원래 머리색 (hair_hex). The light generation state columns are dropped by the next revision.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-10-27 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hair_renders", sa.Column("light_status", sa.String(length=20), nullable=True))
    op.add_column("hair_renders", sa.Column("light_error", sa.String(length=300), nullable=True))
    op.add_column("hair_renders", sa.Column("hair_hex", sa.String(length=7), nullable=True))


def downgrade() -> None:
    op.drop_column("hair_renders", "hair_hex")
    op.drop_column("hair_renders", "light_error")
    op.drop_column("hair_renders", "light_status")
