"""Record which ingredient rules support photo-based care suggestions."""
from alembic import op
import sqlalchemy as sa

revision = "f1110a1b2c3d"
down_revision = "f1010a1b2c3d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("category_ingredients", sa.Column(
        "photo_eligible", sa.Boolean(), nullable=False, server_default=sa.false(),
    ))


def downgrade():
    used = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM category_ingredients WHERE photo_eligible"
    )).scalar()
    if used:
        raise RuntimeError("Photo rule history exists; refusing a lossy downgrade.")
    with op.batch_alter_table("category_ingredients") as batch:
        batch.drop_column("photo_eligible")
