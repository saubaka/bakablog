"""Server-side sessions for administrator authentication."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, request, session

from app.extensions import db
from app.models import User, UserSession, utc_now

SESSION_KEY = "user_session_token"
AUTH_SOURCE_KEY = "user_session_source"
AUTH_SOURCE_TESTING = "testing"
AUTH_SOURCE_LOCAL = "local"
VALID_AUTH_SOURCES = {
    AUTH_SOURCE_TESTING,
    AUTH_SOURCE_LOCAL,
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def establish_user_session(
    user: User,
    *,
    source: str,
) -> UserSession:
    if source not in VALID_AUTH_SOURCES:
        raise ValueError("Unsupported administrator session source.")
    raw = secrets.token_urlsafe(32)
    now = utc_now()
    lifetime = current_app.permanent_session_lifetime
    item = UserSession(
        user_id=user.id,
        token_hash=_hash_token(raw),
        user_agent=request.user_agent.string[:255],
        expires_at=now + lifetime,
    )
    db.session.add(item)
    session[SESSION_KEY] = raw
    session[AUTH_SOURCE_KEY] = source
    return item


def current_user_session() -> UserSession | None:
    raw = session.get(SESSION_KEY)
    if not isinstance(raw, str) or not raw:
        return None
    return db.session.scalar(
        db.select(UserSession).where(UserSession.token_hash == _hash_token(raw))
    )


def current_user_session_source() -> str:
    value = session.get(AUTH_SOURCE_KEY)
    return value if isinstance(value, str) else ""


def session_is_valid(item: UserSession) -> bool:
    if item.revoked_at is not None:
        return False
    expires_at = item.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > datetime.now(UTC)


def touch_user_session(item: UserSession) -> bool:
    last_seen = item.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    if datetime.now(UTC) - last_seen < timedelta(minutes=10):
        return False
    item.last_seen_at = utc_now()
    return True


def revoke_all_user_sessions(user_id: int) -> None:
    """Revoke every local administrator session linked to a user."""

    now = utc_now()
    db.session.execute(
        db.update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
