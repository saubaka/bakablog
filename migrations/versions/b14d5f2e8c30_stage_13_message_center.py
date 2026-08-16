"""Stage thirteen: distinguish broadcast messages from system notices."""

import sqlalchemy as sa
from alembic import op

revision = "b14d5f2e8c30"
down_revision = "a81e62c4d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_broadcasts",
        sa.Column("notification_kind", sa.String(length=20), nullable=False, server_default="system"),
    )


def downgrade() -> None:
    op.drop_column("notification_broadcasts", "notification_kind")
