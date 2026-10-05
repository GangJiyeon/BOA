"""add sex enum to hair tables

Revision ID: cc6b285ae356
Revises: 400e4e798f5c
Create Date: 2026-10-05 05:20:02.497906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc6b285ae356'
down_revision: Union[str, Sequence[str], None] = '400e4e798f5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# models.hair.Sex의 .value("male"/"female"/"unisex")와 동일한 값으로 DB enum을 정의한다.
sex_enum = sa.Enum('male', 'female', 'unisex', name='sex_enum')


def upgrade() -> None:
    """Upgrade schema."""
    # 1. enum 타입을 DB에 먼저 생성한다 (ALTER TABLE ADD COLUMN은 타입을 자동 생성해주지 않는다)
    sex_enum.create(op.get_bind())

    # 2. 두 테이블에 일단 nullable로 컬럼 추가
    op.add_column('face_analyses', sa.Column('sex', sex_enum, nullable=True))
    op.add_column('hair_style_catalog', sa.Column('sex', sex_enum, nullable=True))
    op.add_column('hair_style_catalog', sa.Column('image_credit', sa.String(length=255), nullable=True))

    # 3. 기존 테스트 데이터 백필 (운영 데이터 아니므로 임시값으로 채움)
    op.execute("UPDATE face_analyses SET sex = 'unisex' WHERE sex IS NULL")
    op.execute("UPDATE hair_style_catalog SET sex = 'unisex' WHERE sex IS NULL")

    # 4. NOT NULL로 잠그기
    op.alter_column('face_analyses', 'sex', nullable=False)
    op.alter_column('hair_style_catalog', 'sex', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('hair_style_catalog', 'image_credit')
    op.drop_column('hair_style_catalog', 'sex')
    op.drop_column('face_analyses', 'sex')
    sex_enum.drop(op.get_bind())