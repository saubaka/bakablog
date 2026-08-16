"""Remove the unused administrator-session IP hash."""

import sqlalchemy as sa
from alembic import op

revision = "a12e8f4c6b90"
down_revision = "d9f4a7c2e615"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.drop_column("ip_hash")


def downgrade() -> None:
    with op.batch_alter_table("user_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ip_hash",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )
