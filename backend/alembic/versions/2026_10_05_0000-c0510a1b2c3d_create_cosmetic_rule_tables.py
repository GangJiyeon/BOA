"""Add versioned cosmetic ingredient rules and evidence (schema only).

Revision ID: c0510a1b2c3d
Revises: 400e4e798f5c
"""
from alembic import op
import sqlalchemy as sa

revision = "c0510a1b2c3d"
down_revision = "400e4e798f5c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("cosmetic_rule_sets",
        sa.Column("version", sa.String(80), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False))
    op.create_table("cosmetic_rule_evidence",
        sa.Column("rule_version", sa.String(80), sa.ForeignKey("cosmetic_rule_sets.version"), primary_key=True),
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("access_scope", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("reviewed_on", sa.Date(), nullable=False))
    op.create_table("category_ingredients",
        sa.Column("rule_version", sa.String(80), sa.ForeignKey("cosmetic_rule_sets.version"), primary_key=True),
        sa.Column("code", sa.String(80), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("skin_metric_categories.id"), nullable=False),
        sa.Column("ingredient_id", sa.BigInteger(), sa.ForeignKey("ingredients.ingredient_id"), nullable=False),
        sa.Column("effect", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("match_score", sa.SmallInteger(), nullable=False),
        sa.Column("hard_exclude", sa.Boolean(), nullable=False),
        sa.Column("condition", sa.String(30), nullable=False),
        sa.Column("usage_scope", sa.String(40), nullable=False),
        sa.Column("evidence_code", sa.String(80), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["rule_version", "evidence_code"], ["cosmetic_rule_evidence.rule_version", "cosmetic_rule_evidence.code"]),
        sa.UniqueConstraint("rule_version", "category_id", "ingredient_id", "effect", name="uq_category_ingredient_rule"),
        sa.CheckConstraint("status IN ('active', 'deferred')", name="rule_status"),
        sa.CheckConstraint("effect IN ('match', 'exclude', 'caution')", name="rule_effect"),
        sa.CheckConstraint("(effect = 'match' AND match_score = 1) OR (effect <> 'match' AND match_score = 0)", name="rule_score"),
        sa.CheckConstraint("(effect = 'exclude' AND hard_exclude) OR (effect <> 'exclude' AND NOT hard_exclude)", name="rule_exclusion"),
        sa.CheckConstraint("condition IN ('always', 'redness_opt_in')", name="rule_condition"),
        sa.CheckConstraint("usage_scope = 'leave_on_candidate'", name="rule_usage"))
    op.create_index("ix_category_ingredients_category_id", "category_ingredients", ["category_id"])
    op.create_index("ix_category_ingredients_ingredient_id", "category_ingredients", ["ingredient_id"])


def downgrade():
    # 명시적인 downgrade는 규칙 이력만 삭제한다. 기존 상품/분석 테이블은 변경하지 않는다.
    op.drop_index("ix_category_ingredients_ingredient_id", table_name="category_ingredients")
    op.drop_index("ix_category_ingredients_category_id", table_name="category_ingredients")
    op.drop_table("category_ingredients")
    op.drop_table("cosmetic_rule_evidence")
    op.drop_table("cosmetic_rule_sets")
