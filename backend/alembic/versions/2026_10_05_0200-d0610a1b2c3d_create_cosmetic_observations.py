"""Preserve source ingredient observations; schema only, no catalog rewrites.

Revision ID: d0610a1b2c3d
Revises: c0510a1b2c3d
"""
from alembic import op
import sqlalchemy as sa

revision = "d0610a1b2c3d"
down_revision = "c0510a1b2c3d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("cosmetic_observation_batches",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("source_file_sha256", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("importer_version", sa.String(40), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("amount_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("record_count >= 0 AND amount_count >= 0 AND amount_count <= record_count", name="observation_counts"))
    op.create_table("product_ingredient_observations",
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("cosmetic_observation_batches.batch_id"), primary_key=True),
        sa.Column("source_formula_id", sa.String(255), primary_key=True),
        sa.Column("source_position", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("ingredient_id", sa.BigInteger(), nullable=False),
        sa.Column("source_product_id", sa.String(255), nullable=False),
        sa.Column("source_ingredient_id", sa.BigInteger(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_record_hash", sa.Text(), nullable=False),
        sa.Column("raw_token", sa.Text(), nullable=False),
        sa.Column("amount_text", sa.Text(), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(["product_id", "ingredient_id"], ["product_ingredients.product_id", "product_ingredients.ingredient_id"]),
        sa.CheckConstraint("source_position >= 0", name="observation_position"),
        sa.CheckConstraint("review_status = 'unreviewed'", name="observation_review_status"))
    op.create_index("ix_product_ingredient_observations_product_id", "product_ingredient_observations", ["product_id"])


def downgrade():
    # 명시적 downgrade는 관측 이력을 삭제한다. 기존 카탈로그/규칙은 변경하지 않는다.
    op.drop_index("ix_product_ingredient_observations_product_id", table_name="product_ingredient_observations")
    op.drop_table("product_ingredient_observations")
    op.drop_table("cosmetic_observation_batches")
