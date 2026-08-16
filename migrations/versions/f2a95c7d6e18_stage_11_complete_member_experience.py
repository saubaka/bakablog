"""stage 11 complete member experience

Revision ID: f2a95c7d6e18
Revises: e7c41f0a92b6
Create Date: 2026-07-17 21:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a95c7d6e18"
down_revision = "e7c41f0a92b6"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite can add a nullable REFERENCES column directly. Avoid batch rebuilding
    # users here because many existing tables point at it and their rows must not
    # be touched during an upgrade.
    op.get_bind().exec_driver_sql(
        "ALTER TABLE users ADD COLUMN avatar_media_id INTEGER "
        "REFERENCES media(id) ON DELETE SET NULL"
    )
    op.add_column("users", sa.Column("totp_seed", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True)))

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("notify_moderation", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_replies", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_friend_links", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_security", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timezone", sa.String(length=60), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer()),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("target_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("dedupe_key", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_user_notifications_user_id", "user_notifications", ["user_id"])
    op.create_index("ix_user_notifications_sender_id", "user_notifications", ["sender_id"])
    op.create_index(
        "ix_user_notifications_notification_type", "user_notifications", ["notification_type"]
    )
    op.create_index("ix_user_notifications_dedupe_key", "user_notifications", ["dedupe_key"])
    op.create_index("ix_user_notifications_created_at", "user_notifications", ["created_at"])
    op.create_index("ix_user_notifications_read_at", "user_notifications", ["read_at"])
    op.create_index(
        "ix_user_notifications_user_read_created",
        "user_notifications",
        ["user_id", "read_at", "created_at"],
    )
    op.create_index(
        "ix_user_notifications_type_created",
        "user_notifications",
        ["notification_type", "created_at"],
    )

    op.create_table(
        "notification_broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer()),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("target_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("audience", sa.String(length=30), nullable=False, server_default="all"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_notification_broadcasts_created_at", "notification_broadcasts", ["created_at"]
    )

    op.create_table(
        "post_bookmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "post_id", name="uq_post_bookmark_user_post"),
    )
    op.create_index("ix_post_bookmarks_user_id", "post_bookmarks", ["user_id"])
    op.create_index("ix_post_bookmarks_post_id", "post_bookmarks", ["post_id"])
    op.create_index("ix_post_bookmarks_user_created", "post_bookmarks", ["user_id", "created_at"])

    op.create_table(
        "user_recovery_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_recovery_codes_user_id", "user_recovery_codes", ["user_id"])
    op.create_index("ix_user_recovery_user_used", "user_recovery_codes", ["user_id", "used_at"])

    op.create_table(
        "user_deletion_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_deletion_requests_user_id", "user_deletion_requests", ["user_id"])
    op.create_index("ix_user_deletion_requests_status", "user_deletion_requests", ["status"])
    op.create_index(
        "ix_user_deletion_requests_scheduled_for", "user_deletion_requests", ["scheduled_for"]
    )
    op.create_index(
        "ix_user_deletion_status_scheduled",
        "user_deletion_requests",
        ["status", "scheduled_for"],
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO permissions (code, name, description) "
            "VALUES ('user_notifications.manage', '发布和管理用户通知', '')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
            "WHERE r.code IN ('administrator', 'superadmin') "
            "AND p.code = 'user_notifications.manage'"
        )
    )


def downgrade():
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = 'user_notifications.manage')"
        )
    )
    connection.execute(sa.text("DELETE FROM permissions WHERE code = 'user_notifications.manage'"))
    op.drop_table("user_deletion_requests")
    op.drop_table("user_recovery_codes")
    op.drop_table("post_bookmarks")
    op.drop_table("notification_broadcasts")
    op.drop_table("user_notifications")
    op.drop_table("user_preferences")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("totp_enabled_at")
        batch_op.drop_column("totp_seed")
        batch_op.drop_column("avatar_media_id")
