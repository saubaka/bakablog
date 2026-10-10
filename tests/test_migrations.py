from __future__ import annotations

from sqlalchemy import inspect
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User


def test_empty_instance_can_migrate_and_initialize(tmp_path):
    app = create_app("testing", instance_path=str(tmp_path / "migration-instance"))
    runner = app.test_cli_runner()

    result = runner.invoke(
        args=[
            "site-init",
            "--username",
            "owner",
            "--display-name",
            "站点主人",
            "--password",
            "migration-test-password",
        ]
    )
    assert result.exit_code == 0, result.output
    assert "站点初始化完成" in result.output

    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        assert {
            "alembic_version",
            "users",
            "roles",
            "permissions",
            "media",
            "login_logs",
            "audit_logs",
            "categories",
            "tags",
            "posts",
            "post_tags",
            "post_versions",
            "site_profiles",
            "personal_skills",
            "experiences",
            "personal_goals",
            "social_links",
            "projects",
            "moments",
            "home_modules",
            "navigation_items",
            "site_settings",
            "external_link_rules",
            "custom_pages",
            "friend_categories",
            "friend_links",
            "albums",
            "photos",
            "comments",
            "comment_reactions",
            "guestbook_messages",
            "moderation_notifications",
            "user_sessions",
        }.issubset(tables)
        assert {
            "user_tokens",
            "user_moderation_actions",
            "user_preferences",
            "user_notifications",
            "notification_broadcasts",
            "post_bookmarks",
            "user_recovery_codes",
            "user_deletion_requests",
        }.isdisjoint(tables)
        comment_columns = {column["name"] for column in inspect(db.engine).get_columns("comments")}
        assert "report_count" not in comment_columns
        assert "user_id" not in comment_columns
        user_columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
        assert {
            "email",
            "bio",
            "website",
            "profile_visibility",
            "avatar_media_id",
            "totp_seed",
            "totp_enabled_at",
        }.isdisjoint(user_columns)
        user = db.session.scalar(db.select(User).where(User.username == "owner"))
        assert user is not None
        assert user.has_permission("media.manage")
        assert user.has_permission("posts.publish")
        assert user.has_permission("profile.manage")
        assert user.has_permission("projects.publish")
        assert user.has_permission("site.manage")
        assert user.has_permission("friends.manage")
        assert user.has_permission("albums.manage")
        assert user.has_permission("moderation.manage")
        assert not user.has_permission("user_notifications.manage")
        assert not user.has_permission("user_data.manage")
        fts = db.session.execute(
            db.text("SELECT name FROM sqlite_master WHERE type='table' AND name='posts_fts'")
        ).scalar_one_or_none()
        assert fts == "posts_fts"
        site_search_fts = db.session.execute(
            db.text("SELECT name FROM sqlite_master WHERE type='table' AND name='site_search_fts'")
        ).scalar_one_or_none()
        assert site_search_fts == "site_search_fts"

    check = runner.invoke(args=["db-check"])
    assert check.exit_code == 0
    assert "SQLite完整性检查：ok" in check.output


def test_user_foundation_migration_preserves_existing_administrator_access(tmp_path):
    app = create_app("testing", instance_path=str(tmp_path / "existing-admin-migration"))
    runner = app.test_cli_runner()
    old_head = runner.invoke(args=["db", "upgrade", "c420a0b39922"])
    assert old_head.exit_code == 0, old_head.output
    with app.app_context():
        db.session.execute(
            db.text(
                "INSERT INTO roles (code,name,is_system) VALUES ('administrator','超级管理员',1)"
            )
        )
        db.session.execute(
            db.text(
                "INSERT INTO permissions (code,name,description) VALUES "
                "('dashboard.view','查看仪表盘','')"
            )
        )
        db.session.execute(
            db.text(
                "INSERT INTO role_permissions (role_id,permission_id) "
                "SELECT r.id,p.id FROM roles r,permissions p "
                "WHERE r.code='administrator' AND p.code='dashboard.view'"
            )
        )
        db.session.execute(
            db.text(
                "INSERT INTO users "
                "(username,display_name,password_hash,is_active,created_at,updated_at) "
                "VALUES ('legacy-owner','旧站长',:password,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ),
            {"password": generate_password_hash("legacy-owner-password")},
        )
        db.session.execute(
            db.text(
                "INSERT INTO user_roles (user_id,role_id) "
                "SELECT u.id,r.id FROM users u,roles r "
                "WHERE u.username='legacy-owner' AND r.code='administrator'"
            )
        )
        db.session.commit()
    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == "legacy-owner"))
        assert user is not None
        assert user.has_permission("admin.access")
        assert any(role.code == "superadmin" for role in user.roles)


def test_superadmin_only_migration_requires_backup_for_downgrade(tmp_path):
    app = create_app("testing", instance_path=str(tmp_path / "round-trip-migration"))
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    downgrade = runner.invoke(args=["db", "downgrade", "c420a0b39922"])
    assert downgrade.exit_code != 0
    assert "完整站点备份" in downgrade.output
