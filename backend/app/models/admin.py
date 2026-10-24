from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64, collation="NOCASE"), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="owner")  # only "owner" exists today; every route goes through @admin_required
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int | None] = mapped_column(Integer)  # last accepted 30-second step: a code cannot be used twice
    recovery_hashes: Mapped[list | None] = mapped_column(JSON)  # sha256 of the unused one-time recovery codes
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    sessions: Mapped[list[AdminSession]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # the cookie holds the token, the database only its sha256
    csrf_token: Mapped[str] = mapped_column(String(64))
    device: Mapped[str] = mapped_column(String(160), default="")
    ip_prefix: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    user: Mapped[AdminUser] = relationship(back_populates="sessions")


class LoginAttempt(Base):
    """Login history and the data behind rate limiting / temporary lockout."""

    __tablename__ = "login_attempts"
    __table_args__ = (Index("ix_login_attempts_user_at", "username", "at"), Index("ix_login_attempts_ip_at", "ip_prefix", "at"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    ip_prefix: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(32), default="")  # ok | bad_password | unknown_user | locked | totp
