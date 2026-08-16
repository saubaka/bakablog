"""Stage sixteen: store the Cloudgate client configuration in SQLite."""

import sqlalchemy as sa
from alembic import op

revision = "c6f9a2d81b47"
down_revision = "e83b0f4c912d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column(
            "scopes",
            sa.String(length=300),
            nullable=False,
            server_default="openid profile email",
        ),
        sa.Column(
            "http_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "introspection_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column(
            "refresh_token_ttl_days",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "http_timeout_seconds BETWEEN 2 AND 30",
            name="ck_gateway_config_timeout",
        ),
        sa.CheckConstraint(
            "introspection_interval_seconds BETWEEN 60 AND 3600",
            name="ck_gateway_config_introspection",
        ),
        sa.CheckConstraint(
            "refresh_token_ttl_days BETWEEN 1 AND 90",
            name="ck_gateway_config_refresh_days",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # The former environment-backed connection cannot be trusted as the new
    # database-backed connection. Force the documented first-binding gate.
    op.execute("UPDATE users SET gateway_subject = NULL WHERE gateway_subject IS NOT NULL")
    op.execute(
        "UPDATE gateway_identity_sessions "
        "SET revoked_at = CURRENT_TIMESTAMP WHERE revoked_at IS NULL"
    )
    op.execute(
        "UPDATE site_settings SET setting_value = 'false' "
        "WHERE setting_key IN ("
        "'gateway_frontend_login_enabled',"
        "'gateway_registration_enabled',"
        "'gateway_admin_login_enabled',"
        "'gateway_nav_buttons_enabled'"
        ")"
    )


def downgrade() -> None:
    op.drop_table("gateway_configurations")
