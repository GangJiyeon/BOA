"""Merge moisture policy and team hair studio migration heads.

Both branches must run before this revision; no schema or data is rewritten.
"""

revision = "f1010a1b2c3d"
down_revision = ("f0910a1b2c3d", "b2c3d4e5f6a7")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
