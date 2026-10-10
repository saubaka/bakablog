"""Safe, one-time superadministrator bootstrap and credential reset."""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, request

from app.extensions import db
from app.models import (
    LoginLog,
    Role,
    SiteSetting,
    User,
    UserSession,
)
from app.security import normalize_admin_username, validate_admin_password
from app.services.backup import check_database, create_site_backup, verify_site_backup

STATE_KEY = "admin_bootstrap_state"
SLOT_KEY = "admin_bootstrap_slot_id"
TOKEN_HASH_KEY = "admin_bootstrap_token_hash"
TOKEN_EXPIRES_KEY = "admin_bootstrap_token_expires_at"


class AdminBootstrapError(RuntimeError):
    """Raised when setup is unavailable or supplied credentials are unsafe."""


def active_superadmin_count() -> int:
    return int(
        db.session.scalar(
            db.select(db.func.count(db.distinct(User.id)))
            .select_from(User)
            .join(User.roles)
            .where(User.is_active.is_(True), Role.code == "superadmin")
        )
        or 0
    )


def setup_required() -> bool:
    return active_superadmin_count() == 0


def _invalidate_setup_cache() -> None:
    """Drop the cached ``setup_required`` answer after the state changes."""

    from app.services.cache import setup_state_cache

    setup_state_cache.clear()


def setup_code_required() -> bool:
    """Keep loopback development simple while protecting remote/production setup."""

    if current_app.config.get("TESTING"):
        return False
    if str(current_app.config.get("ENV_NAME", "development")) == "production":
        return True
    try:
        return not ipaddress.ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return True


def issue_setup_code(*, lifetime_minutes: int = 30) -> str:
    if not setup_required():
        raise AdminBootstrapError("已有可登录管理员，不能签发初始化口令。")
    raw = secrets.token_urlsafe(18)
    _set(STATE_KEY, "setup-required")
    _set(TOKEN_HASH_KEY, _hash(raw))
    _set(TOKEN_EXPIRES_KEY, (datetime.now(UTC) + timedelta(minutes=lifetime_minutes)).isoformat())
    db.session.commit()
    return raw


def initialize_superadmin(
    username: str,
    display_name: str,
    password: str,
    *,
    setup_code: str = "",
    require_code: bool,
) -> User:
    """Atomically claim the inactive slot and restore the single administrator."""

    normalized = normalize_admin_username(username)
    validate_admin_password(password, normalized)
    if not display_name.strip():
        raise AdminBootstrapError("显示名称不能为空。")

    # A harmless write takes SQLite's writer lock before the invariant is checked.
    _set(STATE_KEY, "initializing")
    db.session.flush()
    if not setup_required():
        db.session.rollback()
        raise AdminBootstrapError("管理员已经完成初始化，请直接登录。")
    if require_code and not _valid_code(setup_code):
        db.session.rollback()
        raise AdminBootstrapError("初始化口令无效或已经过期。")

    from app.cli import ensure_permissions

    role = ensure_permissions(commit=False)
    slot = _bootstrap_slot()
    conflict = db.session.scalar(
        db.select(User).where(User.username == normalized, User.id != slot.id)
    )
    if conflict is not None:
        db.session.rollback()
        raise AdminBootstrapError("该用户名已经存在，请更换后重试。")
    slot.username = normalized
    slot.display_name = display_name.strip()[:80]
    slot.is_active = True
    slot.set_password(password)
    slot.last_login_at = None
    slot.roles = [role]
    db.session.execute(db.delete(UserSession))
    _set(STATE_KEY, "ready")
    _set(TOKEN_HASH_KEY, "")
    _set(TOKEN_EXPIRES_KEY, "")
    db.session.commit()
    _invalidate_setup_cache()
    return slot


def reset_superadmin_credentials() -> tuple[object, str]:
    """Back up the site and revoke every administrator credential.

    Ordinary member rows are never repurposed or removed.  Former
    administrators stay as inactive, anonymised rows so every historical
    foreign key remains valid, while one dedicated row becomes the bootstrap
    slot used by the first-run guide.
    """

    archive = create_site_backup()
    verify_site_backup(archive)

    users = list(db.session.scalars(db.select(User).order_by(User.id)))
    administrators = [user for user in users if user.is_superadmin]
    stored_slot_id = _get(SLOT_KEY)
    slot = (
        next((user for user in users if stored_slot_id.isdigit() and user.id == int(stored_slot_id)), None)
        or next(iter(administrators), None)
    )
    if slot is None:
        slot = User(
            username=f"bootstrap-pending-{secrets.token_hex(6)}",
            display_name="待初始化管理员",
            is_active=False,
        )
        slot.set_password(secrets.token_urlsafe(48))
        db.session.add(slot)
        db.session.flush()

    administrator_ids = {user.id for user in administrators}
    administrator_ids.add(slot.id)
    db.session.execute(db.delete(LoginLog).where(LoginLog.user_id.in_(administrator_ids)))
    db.session.execute(db.delete(UserSession).where(UserSession.user_id.in_(administrator_ids)))
    _delete_optional_credentials(administrator_ids)

    for user in administrators:
        user.roles = []
        user.username = f"retired-admin-{user.id}-{secrets.token_hex(5)}"
        user.display_name = "已停用管理员"
        user.is_active = False
        user.set_password(secrets.token_urlsafe(48))
        user.last_login_at = None
        _clear_extended_identity(user)

    slot.roles = []
    slot.username = f"bootstrap-pending-{slot.id}-{secrets.token_hex(5)}"
    slot.display_name = "待初始化管理员"
    slot.is_active = False
    slot.set_password(secrets.token_urlsafe(48))
    slot.last_login_at = None
    _clear_extended_identity(slot)
    _set(SLOT_KEY, str(slot.id))
    _set(STATE_KEY, "setup-required")
    db.session.commit()
    _invalidate_setup_cache()
    raw_code = issue_setup_code()
    check_database()
    return archive, raw_code


def _bootstrap_slot() -> User:
    slot_id = _get(SLOT_KEY)
    slot = db.session.get(User, int(slot_id)) if slot_id.isdigit() else None
    if slot is None:
        slot = User(
            username=f"bootstrap-pending-{secrets.token_hex(6)}",
            display_name="待初始化管理员",
            is_active=False,
        )
        slot.set_password(secrets.token_urlsafe(48))
        db.session.add(slot)
        db.session.flush()
        _set(SLOT_KEY, str(slot.id))
    return slot


def _delete_optional_credentials(user_ids: set[int]) -> None:
    """Remove credential tables that exist only in the multi-user edition."""

    if not user_ids:
        return
    existing_tables = set(db.inspect(db.engine).get_table_names())
    ids = ",".join(str(int(user_id)) for user_id in sorted(user_ids))
    for table_name in ("user_tokens", "user_recovery_codes"):
        if table_name in existing_tables:
            db.session.execute(db.text(f"DELETE FROM {table_name} WHERE user_id IN ({ids})"))


def _clear_extended_identity(user: User) -> None:
    """Clear multi-user login factors without importing edition-only models."""

    for attribute in ("email", "email_verified_at", "totp_seed", "totp_enabled_at"):
        if hasattr(user, attribute):
            setattr(user, attribute, None)
    if hasattr(user, "status"):
        user.status = "active"
    if hasattr(user, "suspended_until"):
        user.suspended_until = None
    if hasattr(user, "status_reason"):
        user.status_reason = ""
    if hasattr(user, "deleted_at"):
        user.deleted_at = None


def _valid_code(raw: str) -> bool:
    stored = _get(TOKEN_HASH_KEY)
    expires = _get(TOKEN_EXPIRES_KEY)
    if not stored or not expires or not secrets.compare_digest(stored, _hash(raw.strip())):
        return False
    try:
        expiry = datetime.fromisoformat(expires)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
    except ValueError:
        return False
    return expiry > datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _get(key: str) -> str:
    row = db.session.scalar(db.select(SiteSetting).where(SiteSetting.setting_key == key))
    return row.setting_value if row else ""


def _set(key: str, value: str) -> None:
    row = db.session.scalar(db.select(SiteSetting).where(SiteSetting.setting_key == key))
    if row is None:
        db.session.add(SiteSetting(setting_key=key, setting_value=value))
    else:
        row.setting_value = value
