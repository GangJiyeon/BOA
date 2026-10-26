"""create hair_renders

AI 스튜디오 헤어 합성 결과 (요청 1건 = 1행, 이미지는 static/studio/{asset_dir}/)

Revision ID: f1a2b3c4d5e6
Revises: ae596f5070ae
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "ae596f5070ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hair_renders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("style_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("asset_dir", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["hair_rec_runs.id"], name=op.f("fk_hair_renders_run_id_hair_rec_runs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["style_id"], ["hair_style_catalog.style_id"], name=op.f("fk_hair_renders_style_id_hair_style_catalog")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hair_renders")),
        sa.UniqueConstraint("asset_dir", name=op.f("uq_hair_renders_asset_dir")),
    )
    op.create_index(op.f("ix_hair_renders_user_id"), "hair_renders", ["user_id"])
    op.create_index(op.f("ix_hair_renders_guest_id"), "hair_renders", ["guest_id"])
    op.create_index(op.f("ix_hair_renders_created_at"), "hair_renders", ["created_at"])


def downgrade() -> None:
    op.drop_table("hair_renders")
