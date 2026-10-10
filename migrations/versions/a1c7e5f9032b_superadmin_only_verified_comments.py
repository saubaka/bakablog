"""Superadmin-only access and independently controlled comments.

Revision ID: a1c7e5f9032b
Revises: f8b3c6d1a204
"""

import sqlalchemy as sa
from alembic import op

revision = "a1c7e5f9032b"
down_revision = "f8b3c6d1a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("allow_comments", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "moments",
        sa.Column("allow_comments", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("comments") as batch:
        batch.alter_column("post_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("moment_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_comments_moment_id_moments", "moments", ["moment_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_check_constraint(
            "ck_comments_single_target",
            "(post_id IS NOT NULL AND moment_id IS NULL) OR "
            "(post_id IS NULL AND moment_id IS NOT NULL)",
        )
    op.create_index(
        "ix_comments_moment_public",
        "comments",
        ["moment_id", "status", "is_pinned", "created_at"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO permissions (code,name,description) "
            "SELECT 'admin.access','进入管理后台','' "
            "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code='admin.access')"
        )
    )
    connection.execute(
        sa.text("UPDATE roles SET name='超级管理员', is_system=1 WHERE code='superadmin'")
    )
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id,permission_id) "
            "SELECT r.id,p.id FROM roles r,permissions p "
            "WHERE r.code='superadmin' AND p.code='admin.access' "
            "AND NOT EXISTS (SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id=r.id AND rp.permission_id=p.id)"
        )
    )
    superadmin_id = connection.execute(
        sa.text(
            "SELECT u.id FROM users u JOIN user_roles ur ON ur.user_id=u.id "
            "JOIN roles r ON r.id=ur.role_id WHERE r.code='superadmin' ORDER BY u.id LIMIT 1"
        )
    ).scalar()
    user_count = connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar() or 0
    if user_count and superadmin_id is None:
        raise RuntimeError(
            "数据库存在账号但没有超级管理员；请先恢复一个superadmin角色后再执行升级。"
        )
    if superadmin_id is not None:
        connection.execute(
            sa.text("UPDATE posts SET author_id=:admin WHERE author_id<>:admin"),
            {"admin": superadmin_id},
        )
        connection.execute(
            sa.text("UPDATE media SET created_by_id=:admin WHERE created_by_id<>:admin"),
            {"admin": superadmin_id},
        )
        for table, column in (
            ("audit_logs", "actor_id"),
            ("comments", "admin_user_id"),
            ("friend_links", "applicant_user_id"),
            ("gateway_identity_sessions", "linked_user_id"),
            ("guestbook_messages", "user_id"),
            ("login_logs", "user_id"),
            ("notification_broadcasts", "sender_id"),
            ("post_versions", "created_by_id"),
            ("user_moderation_actions", "actor_id"),
            ("user_notifications", "sender_id"),
        ):
            connection.execute(
                sa.text(f"UPDATE {table} SET {column}=NULL WHERE {column}<>:admin"),
                {"admin": superadmin_id},
            )
        for table in (
            "comment_reactions",
            "post_bookmarks",
            "user_deletion_requests",
            "user_moderation_actions",
            "user_notifications",
            "user_preferences",
            "user_recovery_codes",
            "user_sessions",
            "user_tokens",
        ):
            connection.execute(sa.text(f"DELETE FROM {table} WHERE user_id<>:admin"), {"admin": superadmin_id})
        connection.execute(
            sa.text("DELETE FROM user_roles WHERE user_id<>:admin"), {"admin": superadmin_id}
        )
        connection.execute(
            sa.text("DELETE FROM users WHERE id<>:admin"), {"admin": superadmin_id}
        )
    connection.execute(sa.text("DELETE FROM gateway_identity_sessions"))
    connection.execute(sa.text("DELETE FROM gateway_configurations"))
    op.drop_table("gateway_identity_sessions")
    op.drop_table("gateway_configurations")
    # Do not batch-rebuild users on SQLite: replacing the table would fire the
    # user_roles ON DELETE CASCADE relationship and detach the superadmin.
    op.drop_index("ix_users_gateway_subject", table_name="users")
    op.drop_column("users", "gateway_subject")


def downgrade() -> None:
    # Account and external identity removal is deliberately irreversible. A full
    # application backup is the supported rollback path for this release.
    raise RuntimeError("此迁移删除了用户与外部身份数据，请通过完整站点备份回退。")
