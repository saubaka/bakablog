"""stage 12 cloudtrace seo and configurable 2FA

Revision ID: a81e62c4d9f1
Revises: f2a95c7d6e18
Create Date: 2026-07-18 18:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "a81e62c4d9f1"
down_revision = "f2a95c7d6e18"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_preferences",
        sa.Column("two_factor_actions", sa.Text(), nullable=False, server_default="login"),
    )


def downgrade():
    with op.batch_alter_table("user_preferences", schema=None) as batch_op:
        batch_op.drop_column("two_factor_actions")
