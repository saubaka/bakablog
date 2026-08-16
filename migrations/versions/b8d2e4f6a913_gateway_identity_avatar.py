"""Store the avatar URL supplied by Cloudgate UserInfo."""

import sqlalchemy as sa
from alembic import op

revision = "b8d2e4f6a913"
down_revision = "f4b9e2d7a631"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("gateway_identity_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("avatar_url", sa.String(length=800), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("gateway_identity_sessions") as batch_op:
        batch_op.drop_column("avatar_url")
