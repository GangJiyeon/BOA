"""create skin score tables

피부 분석 점수 산출·라벨링 범위의 테이블만 만든다.
화장품/성분/추천 테이블은 각 담당자가 별도 리비전으로 추가한다.

Revision ID: b7c41d9e2f30
Revises: 4f12eb785a30
Create Date: 2026-09-29 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c41d9e2f30"
down_revision: Union[str, Sequence[str], None] = "4f12eb785a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 피부 지표 정의 ────────────────────────────────────────────────
    op.create_table(
        "skin_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("higher_is_better", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_metrics")),
        sa.UniqueConstraint("code", name=op.f("uq_skin_metrics_code")),
    )

    # ── 지표별 판정 구간 (경계값은 이후 UPDATE로 조정 가능) ──────────────
    op.create_table(
        "skin_metric_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("min_score", sa.SmallInteger(), nullable=False),
        sa.Column("max_score", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "min_score <= max_score", name=op.f("ck_skin_metric_categories_score_range")
        ),
        sa.CheckConstraint(
            "min_score >= 0 AND max_score <= 100",
            name=op.f("ck_skin_metric_categories_score_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["skin_metrics.id"],
            name=op.f("fk_skin_metric_categories_metric_id_skin_metrics"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_metric_categories")),
        sa.UniqueConstraint(
            "metric_id", "min_score", name=op.f("uq_skin_metric_categories_metric_id")
        ),
    )

    # ── 분석 1건 ─────────────────────────────────────────────────────
    # user_id / guest_id는 인증 파트 테이블이 아직 없어 FK 없이 컬럼만 둔다.
    op.create_table(
        "skin_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_id", sa.Uuid(), nullable=True),
        sa.Column("image_id", sa.Integer(), nullable=True),
        sa.Column("logic_version", sa.String(length=20), nullable=False),
        sa.Column("moisture_source", sa.String(length=10), nullable=False),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "moisture_source IN ('sensor', 'manual', 'none')",
            name=op.f("ck_skin_analyses_moisture_source"),
        ),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["images.id"],
            name=op.f("fk_skin_analyses_image_id_images"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_analyses")),
    )
    op.create_index(op.f("ix_skin_analyses_user_id"), "skin_analyses", ["user_id"])
    op.create_index(op.f("ix_skin_analyses_guest_id"), "skin_analyses", ["guest_id"])

    # ── 지표별 점수와 판정 결과 ───────────────────────────────────────
    op.create_table(
        "skin_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("metric_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint(
            "score BETWEEN 0 AND 100", name=op.f("ck_skin_scores_score_bounds")
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["skin_analyses.id"],
            name=op.f("fk_skin_scores_analysis_id_skin_analyses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["skin_metric_categories.id"],
            name=op.f("fk_skin_scores_category_id_skin_metric_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"],
            ["skin_metrics.id"],
            name=op.f("fk_skin_scores_metric_id_skin_metrics"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_scores")),
        sa.UniqueConstraint(
            "analysis_id", "metric_id", name=op.f("uq_skin_scores_analysis_id")
        ),
    )
    op.create_index(op.f("ix_skin_scores_analysis_id"), "skin_scores", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("skin_scores")
    op.drop_table("skin_analyses")
    op.drop_table("skin_metric_categories")
    op.drop_table("skin_metrics")
