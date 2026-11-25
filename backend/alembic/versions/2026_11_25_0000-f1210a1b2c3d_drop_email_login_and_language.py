"""이메일 로그인·다국어 제거: email_verifications 테이블, users.language 칼럼 삭제"""
from alembic import op
import sqlalchemy as sa

revision = "f1210a1b2c3d"
down_revision = "f1110a1b2c3d"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("email_verifications")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("language")


def downgrade():
    # 기존 회원 언어는 복구 불가, 기본값 ko로 채움
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("language", sa.String(length=5), nullable=False, server_default="ko"))
    op.create_table(
        "email_verifications",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email", name=op.f("pk_email_verifications")),
    )
