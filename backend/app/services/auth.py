"""The owner account: first-run setup, login with limits, sessions, TOTP.

Rules worth knowing:
- Setup works once. A one-time token is printed to the server log (or preset with BLOG_SETUP_TOKEN); once an owner exists
  the token is deleted and /api/admin/auth/setup answers 404 for good.
- Failed logins are committed immediately (a failing request would otherwise roll its own record back, and rate limiting
  would count nothing).
- The cookie holds a random token, the database only its sha256. Every state-changing request must carry the session's CSRF
  token in X-CSRF-Token.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import pyotp
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import Config
from app.errors import ApiError
from app.models import AdminSession, AdminUser, LoginAttempt
from app.security import (
    device_label,
    dummy_verify,
    hash_password,
    needs_rehash,
    new_token,
    safe_equal,
    token_hash,
    verify_password,
)
from app.services import audit, settings
from app.timeutil import utcnow

log = logging.getLogger("bakablog.auth")

SESSION_COOKIE = "bb_session"
SETUP_KEY = "auth.setup_token_hash"
TOUCH_EVERY = timedelta(minutes=5)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_WEAK = {"password", "passw0rd", "1234567890", "12345678910", "qwertyuiop", "qwerty12345", "iloveyou123", "admin12345", "administrator"}


# ---- setup --------------------------------------------------------------------------------------------------------------------
def owner_exists(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(AdminUser)))


def issue_setup_token(session: Session, preset: str | None = None) -> str:
    token = preset or secrets.token_urlsafe(18)
    settings.set_raw(session, SETUP_KEY, token_hash(token))
    return token


def ensure_setup_token(session: Session, cfg: Config) -> str | None:
    """Called when the app starts. Returns a freshly generated token (to be printed once) or None."""
    if owner_exists(session):
        settings.delete_raw(session, SETUP_KEY)
        return None
    if cfg.setup_token:
        issue_setup_token(session, cfg.setup_token)
        return None
    if settings.get_raw(session, SETUP_KEY):
        return None
    return issue_setup_token(session)


def check_setup_token(session: Session, token: str) -> bool:
    stored = settings.get_raw(session, SETUP_KEY)
    return bool(stored) and safe_equal(token_hash(token.strip()), str(stored))


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise ApiError(422, "invalid", "用户名不合规。", fields={"username": "3–32 位，只能用字母、数字、下划线、点和短横线"})
    return username


def validate_password(password: str, username: str = "") -> None:
    problem = None
    if len(password) < 10:
        problem = "至少 10 个字符"
    elif len(password) > 200:
        problem = "最多 200 个字符"
    elif username and username.lower() in password.lower():
        problem = "不要把用户名放进密码里"
    elif password.lower() in _WEAK or len(set(password)) < 4:
        problem = "太容易被猜到了，换一个"
    if problem:
        raise ApiError(422, "weak_password", "密码不合规。", fields={"password": problem})


def create_owner(session: Session, username: str, password: str, cfg: Config) -> AdminUser:
    username = validate_username(username)
    validate_password(password, username)
    user = AdminUser(username=username, password_hash=hash_password(password, cfg.scrypt_n), role="owner", password_changed_at=utcnow())
    session.add(user)
    session.flush()
    settings.delete_raw(session, SETUP_KEY)
    audit.record(session, "auth.setup", "user", user.id, {"username": username}, actor=user)
    return user


# ---- login limits -------------------------------------------------------------------------------------------------------------
def _failures_since(session: Session, column, value: str, since: datetime) -> tuple[int, datetime | None]:
    row = session.execute(
        select(func.count(), func.min(LoginAttempt.at)).where(column == value, LoginAttempt.success.is_(False),
                                                              LoginAttempt.reason != "locked", LoginAttempt.at >= since)
    ).one()
    return int(row[0]), row[1]


def lockout_seconds(session: Session, username: str, prefix: str, cfg: Config) -> int:
    """0 when the login may proceed, otherwise how many seconds until the oldest counted failure leaves the window."""
    window = timedelta(minutes=cfg.login_window_minutes)
    now = utcnow()
    since = now - window
    last_ok = session.scalar(select(func.max(LoginAttempt.at)).where(LoginAttempt.username == username, LoginAttempt.success.is_(True)))
    user_since = max(since, last_ok) if last_ok else since
    wait = 0
    if username:
        count, oldest = _failures_since(session, LoginAttempt.username, username, user_since)
        if count >= cfg.login_max_failures and oldest:
            wait = max(wait, int((oldest + window - now).total_seconds()) + 1)
    if prefix:
        count, oldest = _failures_since(session, LoginAttempt.ip_prefix, prefix, since)
        if count >= cfg.login_ip_max_failures and oldest:
            wait = max(wait, int((oldest + window - now).total_seconds()) + 1)
    return max(wait, 0)


def _attempt(session: Session, username: str, prefix: str, ua: str, success: bool, reason: str) -> None:
    session.add(LoginAttempt(username=username[:64], ip_prefix=prefix, user_agent=(ua or "")[:200], success=success, reason=reason))
    session.commit()  # kept even when the request fails


# ---- login / sessions ---------------------------------------------------------------------------------------------------------
@dataclass
class LoginResult:
    user: AdminUser
    session: AdminSession
    token: str


def _open_session(session: Session, user: AdminUser, ua: str, prefix: str, cfg: Config) -> LoginResult:
    token = new_token()
    row = AdminSession(
        user_id=user.id, token_hash=token_hash(token), csrf_token=new_token(24), device=device_label(ua), ip_prefix=prefix,
        expires_at=utcnow() + timedelta(days=cfg.session_days),
    )
    session.add(row)
    user.last_login_at = utcnow()
    session.flush()
    return LoginResult(user=user, session=row, token=token)


def login_after_setup(session: Session, user: AdminUser, ua: str, prefix: str, cfg: Config) -> LoginResult:
    session.add(LoginAttempt(username=user.username, ip_prefix=prefix, user_agent=(ua or "")[:200], success=True, reason="ok"))
    return _open_session(session, user, ua, prefix, cfg)


def login(session: Session, username: str, password: str, code: str | None, ua: str, prefix: str, cfg: Config) -> LoginResult:
    username = username.strip()[:64]
    wait = lockout_seconds(session, username, prefix, cfg)
    if wait:
        _attempt(session, username, prefix, ua, False, "locked")
        raise ApiError(429, "locked", f"尝试次数太多，请 {max(1, wait // 60 + (1 if wait % 60 else 0))} 分钟后再试。",
                       headers={"Retry-After": str(wait)}, extra={"retry_after": wait})
    user = session.scalar(select(AdminUser).where(AdminUser.username == username))
    if user is None:
        dummy_verify(password, cfg.scrypt_n)
        _attempt(session, username, prefix, ua, False, "unknown_user")
        raise ApiError(401, "bad_credentials", "用户名或密码不对。")
    if not verify_password(password, user.password_hash):
        _attempt(session, username, prefix, ua, False, "bad_password")
        raise ApiError(401, "bad_credentials", "用户名或密码不对。")
    if user.totp_enabled:
        if not code:
            raise ApiError(401, "totp_required", "请输入二次验证码。")
        if not _check_second_factor(session, user, code):
            _attempt(session, username, prefix, ua, False, "totp")
            raise ApiError(401, "bad_code", "验证码不对或已过期。")
    if needs_rehash(user.password_hash, cfg.scrypt_n) and cfg.scrypt_n > 0:
        user.password_hash = hash_password(password, cfg.scrypt_n)
    session.add(LoginAttempt(username=username, ip_prefix=prefix, user_agent=(ua or "")[:200], success=True, reason="ok"))
    result = _open_session(session, user, ua, prefix, cfg)
    audit.record(session, "auth.login", "session", result.session.id, {"device": result.session.device}, actor=user)
    return result


@dataclass
class Authenticated:
    user: AdminUser
    session: AdminSession


def authenticate(session: Session, token: str | None) -> Authenticated | None:
    if not token:
        return None
    row = session.execute(
        select(AdminSession, AdminUser).join(AdminUser, AdminUser.id == AdminSession.user_id)
        .where(AdminSession.token_hash == token_hash(token), AdminSession.revoked_at.is_(None), AdminSession.expires_at > utcnow())
    ).first()
    if row is None:
        return None
    return Authenticated(user=row[1], session=row[0])


def needs_touch(row: AdminSession) -> bool:
    return utcnow() - row.last_seen_at > TOUCH_EVERY


def touch(session: Session, session_id: int) -> None:
    session.execute(update(AdminSession).where(AdminSession.id == session_id).values(last_seen_at=utcnow()))


def logout(session: Session, row: AdminSession) -> None:
    row.revoked_at = utcnow()
    audit.record(session, "auth.logout", "session", row.id)


def list_sessions(session: Session, user: AdminUser) -> list[AdminSession]:
    return list(session.scalars(
        select(AdminSession).where(AdminSession.user_id == user.id, AdminSession.revoked_at.is_(None), AdminSession.expires_at > utcnow())
        .order_by(AdminSession.last_seen_at.desc())
    ))


def revoke_session(session: Session, user: AdminUser, session_id: int) -> bool:
    row = session.get(AdminSession, session_id)
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    audit.record(session, "auth.session_revoked", "session", row.id, {"device": row.device})
    return True


def revoke_others(session: Session, user: AdminUser, keep_id: int) -> int:
    res = session.execute(
        update(AdminSession).where(AdminSession.user_id == user.id, AdminSession.id != keep_id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    audit.record(session, "auth.sessions_revoked", "user", user.id, {"count": res.rowcount})
    return int(res.rowcount or 0)


def login_history(session: Session, user: AdminUser, limit: int = 50) -> list[LoginAttempt]:
    return list(session.scalars(
        select(LoginAttempt).where(LoginAttempt.username == user.username).order_by(LoginAttempt.id.desc()).limit(limit)
    ))


# ---- account changes ----------------------------------------------------------------------------------------------------------
def change_password(session: Session, user: AdminUser, current: str, new: str, keep_session_id: int, cfg: Config) -> None:
    if not verify_password(current, user.password_hash):
        raise ApiError(422, "bad_password", "当前密码不对。", fields={"current_password": "不对"})
    validate_password(new, user.username)
    user.password_hash = hash_password(new, cfg.scrypt_n)
    user.password_changed_at = utcnow()
    revoke_others(session, user, keep_session_id)
    audit.record(session, "auth.password_changed", "user", user.id)


def change_username(session: Session, user: AdminUser, new_username: str, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise ApiError(422, "bad_password", "密码不对。", fields={"password": "不对"})
    new_username = validate_username(new_username)
    taken = session.scalar(select(AdminUser.id).where(AdminUser.username == new_username, AdminUser.id != user.id))
    if taken:
        raise ApiError(409, "username_taken", "这个用户名已经被占用。", fields={"username": "已被占用"})
    old, user.username = user.username, new_username
    audit.record(session, "auth.username_changed", "user", user.id, {"from": old, "to": new_username})


# ---- TOTP ---------------------------------------------------------------------------------------------------------------------
def _recovery_hash(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()


def totp_begin(session: Session, user: AdminUser, issuer: str) -> dict:
    if user.totp_enabled:
        raise ApiError(409, "totp_enabled", "已经开启了二次验证。")
    user.totp_secret = pyotp.random_base32()
    session.flush()
    return {"secret": user.totp_secret, "uri": pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.username, issuer_name=issuer)}


def _match_step(user: AdminUser, code: str) -> int | None:
    if not user.totp_secret or not re.fullmatch(r"\d{6}", code.strip()):
        return None
    totp = pyotp.TOTP(user.totp_secret)
    now = utcnow()
    base = int(now.timestamp() // 30)
    for offset in (0, -1, 1):
        if safe_equal(totp.at(now, counter_offset=offset), code.strip()):
            step = base + offset
            if user.totp_last_step is not None and step <= user.totp_last_step:
                return None  # the same code cannot be used twice
            return step
    return None


def _check_second_factor(session: Session, user: AdminUser, code: str) -> bool:
    step = _match_step(user, code)
    if step is not None:
        user.totp_last_step = step
        return True
    hashes = list(user.recovery_hashes or [])
    digest = _recovery_hash(code)
    if digest in hashes:
        hashes.remove(digest)
        user.recovery_hashes = hashes
        audit.record(session, "auth.recovery_code_used", "user", user.id, {"left": len(hashes)}, actor=user)
        return True
    return False


def totp_enable(session: Session, user: AdminUser, code: str) -> list[str]:
    if user.totp_enabled:
        raise ApiError(409, "totp_enabled", "已经开启了二次验证。")
    if not user.totp_secret:
        raise ApiError(409, "totp_not_started", "请先开始设置二次验证。")
    step = _match_step(user, code)
    if step is None:
        raise ApiError(422, "bad_code", "验证码不对。", fields={"code": "不对或已过期"})
    user.totp_enabled = True
    user.totp_last_step = step
    codes = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(10)]
    user.recovery_hashes = [_recovery_hash(c) for c in codes]
    audit.record(session, "auth.totp_enabled", "user", user.id)
    return codes


def totp_disable(session: Session, user: AdminUser, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise ApiError(422, "bad_password", "密码不对。", fields={"password": "不对"})
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = None
    user.recovery_hashes = None
    audit.record(session, "auth.totp_disabled", "user", user.id)


# ---- housekeeping -------------------------------------------------------------------------------------------------------------
def prune(session: Session) -> dict[str, int]:
    now = utcnow()
    s = session.execute(delete(AdminSession).where((AdminSession.expires_at < now - timedelta(days=7))
                                                   | (AdminSession.revoked_at < now - timedelta(days=7))))
    a = session.execute(delete(LoginAttempt).where(LoginAttempt.at < now - timedelta(days=90)))
    return {"sessions": int(s.rowcount or 0), "login_attempts": int(a.rowcount or 0)}
