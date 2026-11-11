"""Persist relative moisture observations without changing recommendation scores."""
from alembic import op
import sqlalchemy as sa
revision = 'f0810a1b2c3d'
down_revision = 'ae596f5070ae'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('moisture_observations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('measurement_id', sa.String(36), nullable=False, unique=True),
        sa.Column('analysis_id', sa.Integer(), sa.ForeignKey('skin_analyses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_moisture_observations_analysis_id', 'moisture_observations', ['analysis_id'])

def downgrade():
    op.drop_index('ix_moisture_observations_analysis_id', table_name='moisture_observations')
    op.drop_table('moisture_observations')
