"""stage 10 user system foundation

Revision ID: e7c41f0a92b6
Revises: c420a0b39922
Create Date: 2026-07-17 20:00:00
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "e7c41f0a92b6"
down_revision = "c420a0b39922"
branch_labels = None
depends_on = None


NEW_PERMISSIONS = {
    "admin.access": "进入管理后台",
    "users.private.view": "查看用户受限信息",
    "users.manage": "编辑用户资料与状态",
    "users.moderate": "暂停、封禁与恢复账号",
    "users.roles.manage": "分配和移除用户角色",
    "roles.view": "查看角色与权限",
    "roles.manage": "创建和编辑角色权限",
    "registration.manage": "管理注册与登录策略",
    "sessions.manage": "撤销用户登录会话",
    "user_data.manage": "处理用户数据与注销",
}


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=160), nullable=True))
        batch_op.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active")
        )
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("suspended_until", sa.DateTime(timezone=True)))
        batch_op.add_column(
            sa.Column("status_reason", sa.String(length=300), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("bio", sa.String(length=500), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("website", sa.String(length=500), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "profile_visibility", sa.String(length=20), nullable=False, server_default="private"
            )
        )
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True)))
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_users_deleted_at"), ["deleted_at"], unique=False)
        batch_op.create_index("ix_users_status_created", ["status", "created_at"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_sessions_user_id"), ["user_id"])
        batch_op.create_index(
            batch_op.f("ix_user_sessions_token_hash"), ["token_hash"], unique=True
        )
        batch_op.create_index(batch_op.f("ix_user_sessions_expires_at"), ["expires_at"])
        batch_op.create_index(batch_op.f("ix_user_sessions_revoked_at"), ["revoked_at"])
        batch_op.create_index(
            "ix_user_sessions_user_active", ["user_id", "revoked_at", "expires_at"]
        )

    op.create_table(
        "user_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    with op.batch_alter_table("user_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_tokens_user_id"), ["user_id"])
        batch_op.create_index(batch_op.f("ix_user_tokens_purpose"), ["purpose"])
        batch_op.create_index(batch_op.f("ix_user_tokens_token_hash"), ["token_hash"], unique=True)
        batch_op.create_index(batch_op.f("ix_user_tokens_expires_at"), ["expires_at"])
        batch_op.create_index(batch_op.f("ix_user_tokens_used_at"), ["used_at"])
        batch_op.create_index("ix_user_tokens_user_purpose", ["user_id", "purpose", "created_at"])

    op.create_table(
        "user_moderation_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer()),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    with op.batch_alter_table("user_moderation_actions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_moderation_actions_user_id"), ["user_id"])
        batch_op.create_index(batch_op.f("ix_user_moderation_actions_actor_id"), ["actor_id"])
        batch_op.create_index("ix_user_moderation_target_created", ["user_id", "created_at"])

    with op.batch_alter_table("friend_links", schema=None) as batch_op:
        batch_op.add_column(sa.Column("applicant_user_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_friend_links_applicant_user_id_users",
            "users",
            ["applicant_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("guestbook_messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_guestbook_messages_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index(batch_op.f("ix_guestbook_messages_user_id"), ["user_id"])

    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_comments_user_id_users", "users", ["user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_index(batch_op.f("ix_comments_user_id"), ["user_id"])
        batch_op.drop_constraint("ck_comments_author_type", type_="check")
        batch_op.create_check_constraint(
            "ck_comments_author_type", "author_type IN ('visitor', 'member', 'staff')"
        )
    op.execute(
        "UPDATE comments SET user_id = admin_user_id, author_type = 'staff' "
        "WHERE admin_user_id IS NOT NULL"
    )

    with op.batch_alter_table("comment_reactions", schema=None) as batch_op:
        batch_op.alter_column("visitor_hash", existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column("user_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_comment_reactions_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index(batch_op.f("ix_comment_reactions_user_id"), ["user_id"])
        batch_op.create_unique_constraint("uq_comment_reaction_user", ["comment_id", "user_id"])

    with op.batch_alter_table("comment_reports", schema=None) as batch_op:
        batch_op.alter_column("visitor_hash", existing_type=sa.String(length=64), nullable=True)
        batch_op.add_column(sa.Column("user_id", sa.Integer()))
        batch_op.create_foreign_key(
            "fk_comment_reports_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index(batch_op.f("ix_comment_reports_user_id"), ["user_id"])
        batch_op.create_unique_constraint("uq_comment_report_user", ["comment_id", "user_id"])

    _seed_identity_permissions()


def _seed_identity_permissions() -> None:
    connection = op.get_bind()
    for code, name in NEW_PERMISSIONS.items():
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO permissions (code, name, description) "
                "VALUES (:code, :name, '')"
            ),
            {"code": code, "name": name},
        )
    for code, name in (
        ("member", "普通用户"),
        ("moderator", "互动审核员"),
        ("editor", "内容编辑"),
        ("superadmin", "超级管理员"),
    ):
        connection.execute(
            sa.text("INSERT OR IGNORE INTO roles (code, name, is_system) VALUES (:code, :name, 1)"),
            {"code": code, "name": name},
        )
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
            "WHERE r.code IN ('administrator', 'superadmin')"
        )
    )
    connection.execute(sa.text("UPDATE roles SET name = '管理员' WHERE code = 'administrator'"))
    moderator_permissions = (
        "admin.access",
        "dashboard.view",
        "moderation.view",
        "moderation.manage",
        "users.view",
        "users.moderate",
    )
    editor_permissions = (
        "admin.access",
        "dashboard.view",
        "media.view",
        "media.manage",
        "posts.view",
        "posts.manage",
        "posts.publish",
        "taxonomy.manage",
        "projects.view",
        "projects.manage",
        "projects.publish",
        "moments.view",
        "moments.manage",
        "moments.publish",
        "pages.manage",
    )
    for role_code, permission_codes in (
        ("moderator", moderator_permissions),
        ("editor", editor_permissions),
    ):
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
                "WHERE r.code = :role_code AND p.code IN :permission_codes"
            ).bindparams(sa.bindparam("permission_codes", expanding=True)),
            {"role_code": role_code, "permission_codes": list(permission_codes)},
        )
    connection.execute(
        sa.text(
            "INSERT OR IGNORE INTO user_roles (user_id, role_id) "
            "SELECT ur.user_id, sr.id FROM user_roles ur "
            "JOIN roles ar ON ar.id = ur.role_id AND ar.code = 'administrator' "
            "JOIN roles sr ON sr.code = 'superadmin'"
        )
    )
    connection.execute(
        sa.text("UPDATE users SET password_changed_at = :now WHERE password_changed_at IS NULL"),
        {"now": datetime.now(UTC)},
    )


def downgrade():
    op.execute("UPDATE comments SET author_type = 'admin' WHERE author_type = 'staff'")
    op.execute("UPDATE comments SET author_type = 'visitor' WHERE author_type = 'member'")
    op.execute(
        "UPDATE comment_reactions SET visitor_hash = 'downgrade-user-' || id "
        "WHERE visitor_hash IS NULL"
    )
    op.execute(
        "UPDATE comment_reports SET visitor_hash = 'downgrade-user-' || id "
        "WHERE visitor_hash IS NULL"
    )

    with op.batch_alter_table("comment_reports", schema=None) as batch_op:
        batch_op.drop_constraint("uq_comment_report_user", type_="unique")
        batch_op.drop_index(batch_op.f("ix_comment_reports_user_id"))
        batch_op.drop_constraint("fk_comment_reports_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.alter_column("visitor_hash", existing_type=sa.String(length=64), nullable=False)

    with op.batch_alter_table("comment_reactions", schema=None) as batch_op:
        batch_op.drop_constraint("uq_comment_reaction_user", type_="unique")
        batch_op.drop_index(batch_op.f("ix_comment_reactions_user_id"))
        batch_op.drop_constraint("fk_comment_reactions_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.alter_column("visitor_hash", existing_type=sa.String(length=64), nullable=False)

    with op.batch_alter_table("comments", schema=None) as batch_op:
        batch_op.drop_constraint("ck_comments_author_type", type_="check")
        batch_op.create_check_constraint(
            "ck_comments_author_type", "author_type IN ('visitor', 'admin')"
        )
        batch_op.drop_index(batch_op.f("ix_comments_user_id"))
        batch_op.drop_constraint("fk_comments_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("guestbook_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_guestbook_messages_user_id"))
        batch_op.drop_constraint("fk_guestbook_messages_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("friend_links", schema=None) as batch_op:
        batch_op.drop_constraint("fk_friend_links_applicant_user_id_users", type_="foreignkey")
        batch_op.drop_column("applicant_user_id")

    op.drop_table("user_moderation_actions")
    op.drop_table("user_tokens")
    op.drop_table("user_sessions")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_status_created")
        batch_op.drop_index(batch_op.f("ix_users_deleted_at"))
        batch_op.drop_index(batch_op.f("ix_users_status"))
        batch_op.drop_index(batch_op.f("ix_users_email"))
        for column in (
            "deleted_at",
            "password_changed_at",
            "last_seen_at",
            "profile_visibility",
            "website",
            "bio",
            "status_reason",
            "suspended_until",
            "email_verified_at",
            "status",
            "email",
        ):
            batch_op.drop_column(column)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN :codes)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": list(NEW_PERMISSIONS)},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": list(NEW_PERMISSIONS)},
    )
    connection.execute(
        sa.text(
            "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code IN ('member','moderator','editor','superadmin'))"
        )
    )
    connection.execute(
        sa.text("DELETE FROM roles WHERE code IN ('member','moderator','editor','superadmin')")
    )
