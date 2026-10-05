"""create account tables

회원·약관·동의 이력·토큰·이메일 인증·키오스크·비회원 세션 테이블 생성
>> 피부 테이블과 같은 규칙(복수형 테이블명, 기본키 id)을 따름
>> 참고: user, terms, guest_session 등 단수형(이전 스키마) 테이블은 삭제(있다면)

Revision ID: ae596f5070ae
Revises: e0710a1b2c3d
Create Date: 2026-10-01 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ae596f5070ae"
down_revision: Union[str, Sequence[str], None] = "e0710a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 계정 테이블 ver0 // CASCADE >> FK 제약 같이 삭제
LEGACY_TABLES = (
    "consent_history",
    "refresh_token",
    "email_verification",
    "guest_session",
    "kiosk",
    "terms",
    '"user"',
)


def upgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {', '.join(LEGACY_TABLES)} CASCADE")

    # ── 회원 ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=5), nullable=False),
        sa.Column("nationality", sa.CHAR(length=2), nullable=True),
        sa.Column("resides_in_korea", sa.Boolean(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_users_google_sub")),
    )

    # ── 약관 버전 ─────────────────────────────────────────────────────
    op.create_table(
        "terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_terms")),
        sa.UniqueConstraint("type", "version", name=op.f("uq_terms_type")),
    )

    # ── 동의 이력 ─────────────────────────────────────────────────────
    op.create_table(
        "consent_histories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("terms_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_consent_histories_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["terms_id"], ["terms.id"], name=op.f("fk_consent_histories_terms_id_terms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_histories")),
    )
    op.create_index(
        op.f("ix_consent_histories_user_id"), "consent_histories", ["user_id"]
    )

    # ── 리프레시 토큰 ─────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"])

    # ── 이메일 인증 코드 ──────────────────────────────────────────────
    op.create_table(
        "email_verifications",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_email_verifications")),
    )

    # ── 키오스크 기기 ─────────────────────────────────────────────────
    op.create_table(
        "kiosks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kiosks")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_kiosks_token_hash")),
    )

    # ── 비회원 세션 (웹·키오스크) ─────────────────────────────────────
    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("kiosk_id", sa.Integer(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("qr_token_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("face_terms_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_guest_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["kiosk_id"], ["kiosks.id"], name=op.f("fk_guest_sessions_kiosk_id_kiosks")
        ),
        sa.ForeignKeyConstraint(
            ["face_terms_id"], ["terms.id"], name=op.f("fk_guest_sessions_face_terms_id_terms")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guest_sessions")),
        sa.UniqueConstraint("qr_token_hash", name=op.f("uq_guest_sessions_qr_token_hash")),
    )
    op.create_index(op.f("ix_guest_sessions_ip_hash"), "guest_sessions", ["ip_hash"])


def downgrade() -> None:
    # 예전 단수형 테이블 복구x (필요; 팀 스키마 SQL 다시 실행)
    op.drop_table("guest_sessions")
    op.drop_table("kiosks")
    op.drop_table("email_verifications")
    op.drop_table("refresh_tokens")
    op.drop_table("consent_histories")
    op.drop_table("terms")
    op.drop_table("users")
