from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime
from app.timeutil import utcnow


class Revision(Base):
    """Snapshots of posts / pages / moments. kind "save" = one per saved change (last 20 kept), "autosave" = the single editor draft."""

    __tablename__ = "revisions"
    __table_args__ = (Index("ix_revisions_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(12))
    entity_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="save")
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    """Append-only: triggers (see the first migration) refuse UPDATE and refuse DELETE of anything younger than a year."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_at", "at"), Index("ix_audit_logs_action", "action"))

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor_id: Mapped[int | None] = mapped_column(Integer)  # no foreign key: the log outlives the account
    actor_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(48))
    target_type: Mapped[str] = mapped_column(String(24), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_prefix: Mapped[str] = mapped_column(String(64), default="")
