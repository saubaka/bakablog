"""Stage fifteen: add Cloudgate OIDC identity sessions and administrator binding."""

import sqlalchemy as sa
from alembic import op

revision = "e83b0f4c912d"
down_revision = "d71f6a9c204e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite can add this nullable column in place. Avoid a batch table rebuild:
    # dropping the temporary users table would trigger ON DELETE CASCADE on the
    # existing user_roles rows while foreign-key enforcement is enabled.
    op.add_column("users", sa.Column("gateway_subject", sa.String(length=100), nullable=True))
    op.create_index("ix_users_gateway_subject", "users", ["gateway_subject"], unique=True)

    op.create_table(
        "gateway_identity_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("gateway_subject", sa.String(length=100), nullable=False),
        sa.Column("preferred_username", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False, server_default=""),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "scope",
            sa.String(length=300),
            nullable=False,
            server_default="openid profile email",
        ),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("linked_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["linked_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_gateway_identity_sessions_token_hash",
        "gateway_identity_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_gateway_identity_sessions_gateway_subject",
        "gateway_identity_sessions",
        ["gateway_subject"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_linked_user_id",
        "gateway_identity_sessions",
        ["linked_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_expires_at",
        "gateway_identity_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_revoked_at",
        "gateway_identity_sessions",
        ["revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_gateway_identity_sessions_subject_active",
        "gateway_identity_sessions",
        ["gateway_subject", "revoked_at", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("gateway_identity_sessions")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_gateway_subject")
        batch.drop_column("gateway_subject")
