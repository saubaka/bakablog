"""Server-side sessions for administrator authentication."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app, request, session

from app.extensions import db
from app.models import GatewayIdentitySession, User, UserSession, utc_now

SESSION_KEY = "user_session_token"
AUTH_SOURCE_KEY = "user_session_source"
GATEWAY_SESSION_ID_KEY = "user_session_gateway_id"
AUTH_SOURCE_GATEWAY = "gateway"
AUTH_SOURCE_RECOVERY = "local_recovery"
AUTH_SOURCE_TESTING = "testing"
VALID_AUTH_SOURCES = {
    AUTH_SOURCE_GATEWAY,
    AUTH_SOURCE_RECOVERY,
    AUTH_SOURCE_TESTING,
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def establish_user_session(
    user: User,
    *,
    source: str,
    gateway_session_id: int | None = None,
) -> UserSession:
    if source not in VALID_AUTH_SOURCES:
        raise ValueError("Unsupported administrator session source.")
    if source == AUTH_SOURCE_GATEWAY and (
        not isinstance(gateway_session_id, int) or gateway_session_id <= 0
    ):
        raise ValueError("Gateway administrator sessions require a gateway session id.")
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
    if source == AUTH_SOURCE_GATEWAY:
        session[GATEWAY_SESSION_ID_KEY] = gateway_session_id
    else:
        session.pop(GATEWAY_SESSION_ID_KEY, None)
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


def linked_gateway_session_id() -> int | None:
    value = session.get(GATEWAY_SESSION_ID_KEY)
    return value if isinstance(value, int) and value > 0 else None


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
    """Revoke every local and gateway identity session linked to a user."""

    now = utc_now()
    db.session.execute(
        db.update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.session.execute(
        db.update(GatewayIdentitySession)
        .where(
            GatewayIdentitySession.linked_user_id == user_id,
            GatewayIdentitySession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
