"""Add managed third-party link classifications."""

import sqlalchemy as sa
from alembic import op

revision = "f8b3c6d1a204"
down_revision = "e5c7a9b2d413"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_link_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("note", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('safe', 'dangerous')",
            name="ck_external_link_rules_classification",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hostname"),
    )
    op.create_index(
        "ix_external_link_rules_hostname",
        "external_link_rules",
        ["hostname"],
        unique=True,
    )
    op.create_index(
        "ix_external_link_rules_classification",
        "external_link_rules",
        ["classification"],
        unique=False,
    )
    op.create_index(
        "ix_external_link_rules_classification_hostname",
        "external_link_rules",
        ["classification", "hostname"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_link_rules_classification_hostname",
        table_name="external_link_rules",
    )
    op.drop_index("ix_external_link_rules_classification", table_name="external_link_rules")
    op.drop_index("ix_external_link_rules_hostname", table_name="external_link_rules")
    op.drop_table("external_link_rules")
