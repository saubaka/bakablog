"""Authorization and audit helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

from flask import abort, current_app, g, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog

REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,49}")


def permission_required(code: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not current_user.is_authenticated or not current_user.has_permission(code):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def record_audit(action: str, target_type: str, target_id: str = "", summary: str = "") -> None:
    actor_id = current_user.id if current_user.is_authenticated else None
    db.session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            summary=summary[:255],
            request_id=str(g.get("request_id", ""))[:64],
            ip_address=request_fingerprint("audit"),
        )
    )


def request_fingerprint(scope: str, *, include_user_agent: bool = False) -> str:
    """Return a scoped, irreversible request identity for local abuse controls and logs."""

    secret = str(current_app.config["SECRET_KEY"]).encode()
    parts = [scope, request.remote_addr or "unknown"]
    if include_user_agent:
        parts.append(request.user_agent.string[:120])
    return hmac.new(secret, "|".join(parts).encode(), hashlib.sha256).hexdigest()


def login_is_rate_limited(_username: str) -> bool:
    """Limit failures by requester without letting strangers lock a known account."""

    from app.models import LoginLog
    from app.services.content import get_setting

    try:
        limit = min(20, max(3, int(get_setting("admin_login_max_failures", "5"))))
        lock_minutes = min(180, max(1, int(get_setting("admin_login_lock_minutes", "15"))))
    except (TypeError, ValueError):
        limit = int(current_app.config["LOGIN_RATE_LIMIT"])
        lock_minutes = max(1, int(current_app.config["LOGIN_RATE_WINDOW_SECONDS"]) // 60)
    window = datetime.now(UTC) - timedelta(minutes=lock_minutes)
    identity = request_fingerprint("login")
    failed = db.session.scalar(
        db.select(db.func.count())
        .select_from(LoginLog)
        .where(
            LoginLog.success.is_(False),
            LoginLog.created_at >= window,
            LoginLog.ip_address == identity,
        )
    )
    return (failed or 0) >= limit


def sanitize_request_id(value: str | None) -> str | None:
    if not value or not REQUEST_ID_PATTERN.fullmatch(value):
        return None
    return value


def normalize_admin_username(value: str) -> str:
    username = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("管理员用户名需为3至50位小写字母、数字、点、下划线或连字符。")
    return username


def validate_admin_password(password: str, username: str = "") -> None:
    """Apply a length-focused local administrator password policy."""

    if len(password) < 14:
        raise ValueError("管理员密码至少需要14个字符。")
    lowered = password.casefold()
    if username and username.casefold() in lowered:
        raise ValueError("管理员密码不能包含用户名。")
    if lowered in {"passwordpassword", "administrator", "12345678901234"}:
        raise ValueError("管理员密码过于常见，请改用独立的长密码。")
