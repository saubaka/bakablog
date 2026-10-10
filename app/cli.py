"""Local administration and maintenance commands."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

import click
from flask import Flask, current_app
from flask.cli import with_appcontext
from flask_migrate import upgrade

from app.extensions import db
from app.models import Permission, Role, User
from app.security import normalize_admin_username, validate_admin_password
from app.services.access import (
    normalize_host,
    save_bound_urls,
    save_security_policy,
)
from app.services.admin_bootstrap import issue_setup_code, reset_superadmin_credentials
from app.services.auth import revoke_all_user_sessions
from app.services.backup import (
    BackupError,
    check_database,
    create_site_backup,
    restore_site_backup,
    verify_site_backup,
)
from app.services.migrations import migration_head

PERMISSIONS = {
    "admin.access": "进入管理后台",
    "dashboard.view": "查看仪表盘",
    "media.view": "查看媒体库",
    "media.manage": "管理媒体文件",
    "audit.view": "查看审计与登录日志",
    "system.maintain": "执行系统维护",
    "posts.view": "查看文章与版本",
    "posts.manage": "创建和编辑文章",
    "posts.publish": "发布、定时和撤回文章",
    "taxonomy.manage": "管理分类和标签",
    "profile.manage": "管理个人资料、技能与经历",
    "projects.view": "查看项目作品",
    "projects.manage": "创建和编辑项目作品",
    "projects.publish": "发布和撤回项目作品",
    "moments.view": "查看动态",
    "moments.manage": "创建和编辑动态",
    "moments.publish": "发布和撤回动态",
    "site.manage": "管理首页、导航与页脚",
    "pages.manage": "管理独立页面",
    "friends.view": "查看友链与申请",
    "friends.manage": "管理、审核和检查友链",
    "albums.view": "查看相册与照片",
    "albums.manage": "管理相册与照片",
    "moderation.view": "查看评论、留言与通知",
    "moderation.manage": "审核、回复和处置访客内容",
}


def register_commands(app: Flask) -> None:
    app.cli.add_command(site_init)
    app.cli.add_command(seed_permissions)
    app.cli.add_command(create_superadmin)
    app.cli.add_command(db_check)
    app.cli.add_command(db_optimize)
    app.cli.add_command(site_backup)
    app.cli.add_command(site_backup_verify)
    app.cli.add_command(site_restore)
    app.cli.add_command(system_check)
    app.cli.add_command(configure_deployment_domain)
    app.cli.add_command(reset_superadmin)
    app.cli.add_command(issue_admin_setup_code)


@click.command("configure-deployment-domain")
@click.argument("domain")
@with_appcontext
def configure_deployment_domain(domain: str) -> None:
    """Bind production access to one exact HTTPS domain."""

    try:
        host = normalize_host(domain)
        if "." not in host:
            raise ValueError("部署域名必须是至少包含两个标签的完整域名。")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("部署域名不能使用 IP 地址。")
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    policy = save_bound_urls(f"https://{host}")
    save_security_policy(require_https=True, hotlink_protection=policy.hotlink_protection)
    click.echo(f"生产访问域名已绑定：https://{host}")


def ensure_permissions(*, commit: bool = True) -> Role:
    permission_models: list[Permission] = []
    for code, name in PERMISSIONS.items():
        permission = db.session.scalar(db.select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, name=name)
            db.session.add(permission)
        permission_models.append(permission)

    role = db.session.scalar(db.select(Role).where(Role.code == "superadmin"))
    if role is None:
        role = Role(code="superadmin", name="超级管理员", is_system=True)
        db.session.add(role)
    else:
        role.name = "超级管理员"
        role.is_system = True
    role.permissions = permission_models
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return role


def create_or_update_admin(username: str, password: str, display_name: str) -> User:
    username = normalize_admin_username(username)
    role = ensure_permissions()
    user = db.session.scalar(db.select(User).where(User.username == username))
    existing_user = user is not None
    if user is None:
        user = User(username=username, display_name=display_name)
        db.session.add(user)
    user.display_name = display_name
    user.is_active = True
    user.set_password(password)
    user.roles = [role]
    if existing_user:
        revoke_all_user_sessions(user.id)
    db.session.commit()
    return user


@click.command("site-init")
@click.option("--username", default="admin", show_default=True, help="管理员登录名。")
@click.option("--display-name", default="站点管理员", show_default=True, help="后台显示名称。")
@click.password_option(confirmation_prompt=True, help="至少14个字符的独立管理员密码。")
@with_appcontext
def site_init(username: str, display_name: str, password: str) -> None:
    """Upgrade the database and create the first administrator."""

    username = _validate_credentials(username, password)
    upgrade()
    user = create_or_update_admin(username, password, display_name.strip())
    click.echo(f"站点初始化完成，管理员：{user.username}")


@click.command("seed-permissions")
@with_appcontext
def seed_permissions() -> None:
    """Create or synchronize built-in roles and permissions."""

    ensure_permissions()
    click.echo("内置角色与权限已同步。")


@click.command("create-superadmin")
@click.option("--username", prompt="超级管理员用户名")
@click.option("--display-name", prompt="显示名称", default="超级管理员")
@click.password_option(confirmation_prompt=True)
@with_appcontext
def create_superadmin(username: str, display_name: str, password: str) -> None:
    """Create or reset the only supported local account type."""

    username = _validate_credentials(username, password)
    user = create_or_update_admin(username, password, display_name.strip())
    click.echo(f"超级管理员账号已保存：{user.username}")


@click.command("reset-superadmin")
@click.option("--yes", is_flag=True, help="确认清除旧凭据并进入初始化状态。")
@with_appcontext
def reset_superadmin(yes: bool) -> None:
    """Back up the site and clear administrator credentials without breaking content FKs."""

    if not yes:
        raise click.ClickException("此操作会撤销全部管理员登录；确认后请增加--yes。")
    try:
        archive, code = reset_superadmin_credentials()
    except Exception as error:
        db.session.rollback()
        raise click.ClickException(f"管理员重置失败，数据库未提交：{error}") from error
    click.echo(f"管理员凭据已清除；备份：{archive}")
    click.echo(f"远程或生产初始化口令（30分钟有效）：{code}")


@click.command("issue-admin-setup-code")
@with_appcontext
def issue_admin_setup_code() -> None:
    """Issue a replacement one-time setup code while no administrator exists."""

    try:
        code = issue_setup_code()
    except Exception as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"一次性初始化口令（30分钟有效）：{code}")


@click.command("db-check")
@with_appcontext
def db_check() -> None:
    """Run SQLite integrity and foreign-key checks."""

    try:
        result = check_database()
    except BackupError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"SQLite完整性检查：{result}")


@click.command("db-optimize")
@click.option(
    "--truncate",
    is_flag=True,
    help="在低流量维护窗口回收已经完成检查点的 WAL 文件空间。",
)
@with_appcontext
def db_optimize(truncate: bool) -> None:
    """Refresh query statistics and checkpoint the SQLite WAL."""

    db.session.execute(db.text("PRAGMA optimize"))
    checkpoint_mode = "TRUNCATE" if truncate else "PASSIVE"
    busy, wal_pages, checkpointed_pages = db.session.execute(
        db.text(f"PRAGMA wal_checkpoint({checkpoint_mode})")
    ).one()
    click.echo(
        "SQLite维护完成："
        f"mode={checkpoint_mode.lower()}, busy={busy}, wal_pages={wal_pages}, "
        f"checkpointed_pages={checkpointed_pages}"
    )


@click.command("site-backup")
@click.option("--output", type=click.Path(path_type=Path), help="可选的备份ZIP路径。")
@with_appcontext
def site_backup(output: Path | None) -> None:
    """Create a consistent SQLite and media archive."""

    try:
        archive = create_site_backup(output)
    except BackupError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"备份已创建：{archive}")


@click.command("site-backup-verify")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@with_appcontext
def site_backup_verify(archive: Path) -> None:
    """Verify a backup archive without modifying live data."""

    try:
        manifest = verify_site_backup(archive)
    except BackupError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        "备份验证通过："
        f"format={manifest.get('format')}, app_version={manifest.get('app_version', 'unknown')}, "
        f"media_files={manifest.get('media_files', 0)}"
    )


@click.command("site-restore")
@click.argument("archive", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--yes", is_flag=True, help="确认覆盖当前数据库和媒体目录。")
@with_appcontext
def site_restore(archive: Path, yes: bool) -> None:
    """Restore an offline backup after creating a safety copy."""

    if not yes:
        raise click.ClickException("恢复会替换当前数据；确认后请增加--yes。")
    try:
        safety_copy = restore_site_backup(archive)
    except BackupError as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"恢复完成；恢复前安全副本：{safety_copy}")


@click.command("system-check")
@with_appcontext
def system_check() -> None:
    """Check migration state, storage writability and SQLite integrity."""

    try:
        integrity = check_database()
        revision = db.session.execute(
            db.text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one_or_none()
    except Exception as error:
        raise click.ClickException(f"系统检查失败：{error}") from error
    if current_app.config["ENV_NAME"] == "production" and not revision:
        raise click.ClickException("生产数据库缺少迁移版本，请先执行flask db upgrade。")
    expected_revision = migration_head()
    if current_app.config["ENV_NAME"] == "production" and revision != expected_revision:
        raise click.ClickException(
            f"生产数据库迁移版本不是代码head：current={revision}, head={expected_revision}。"
        )
    for name in ("data", "uploads", "logs", "backups", "tmp"):
        path = Path(current_app.instance_path) / name
        if not path.is_dir() or not os.access(path, os.W_OK):
            raise click.ClickException(f"实例目录不可写：{name}")
    click.echo(
        "系统检查通过："
        f"env={current_app.config['ENV_NAME']}, version={current_app.config['APP_VERSION']}, "
        f"migration={revision or 'unversioned-test'}, sqlite={integrity}"
    )


def _validate_credentials(username: str, password: str) -> str:
    try:
        normalized = normalize_admin_username(username)
        validate_admin_password(password, normalized)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    return normalized
