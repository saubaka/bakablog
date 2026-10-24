"""Audit log: who did what, when. Append-only (database triggers enforce it)."""
from __future__ import annotations

from typing import Any

from flask import g, has_request_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security import client_prefix


def record(session: Session, action: str, target_type: str = "", target_id: Any = "", summary: dict | None = None,
           actor: Any = None) -> AuditLog:
    if actor is None and has_request_context():
        actor = g.get("admin")
    entry = AuditLog(
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id not in (None, "") else "",
        summary=summary or {},
        actor_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "username", "") or ("system" if actor is None else ""),
        ip_prefix=client_prefix() if has_request_context() else "",
    )
    session.add(entry)
    session.flush()
    return entry


def recent(session: Session, *, limit: int = 50, offset: int = 0, action: str | None = None, target_type: str | None = None):
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    if target_type:
        q = q.where(AuditLog.target_type == target_type)
    return list(session.scalars(q.limit(limit).offset(offset)))
