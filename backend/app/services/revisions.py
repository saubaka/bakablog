"""Version history of posts / pages / moments, and the single "autosave" draft of the editor."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Revision

KEEP = 20


def save(session: Session, entity_type: str, entity_id: int, snapshot: dict, *, keep: int = KEEP) -> Revision:
    last = session.scalar(
        select(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "save").order_by(Revision.id.desc())
    )
    if last is not None and last.snapshot == snapshot:
        return last  # nothing changed since the last saved version
    rev = Revision(entity_type=entity_type, entity_id=entity_id, kind="save", snapshot=snapshot)
    session.add(rev)
    session.flush()
    old = list(session.scalars(
        select(Revision.id).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "save")
        .order_by(Revision.id.desc()).offset(keep)
    ))
    if old:
        session.execute(delete(Revision).where(Revision.id.in_(old)))
    return rev


def history(session: Session, entity_type: str, entity_id: int) -> list[Revision]:
    return list(session.scalars(
        select(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "save").order_by(Revision.id.desc())
    ))


def get(session: Session, entity_type: str, entity_id: int, revision_id: int) -> Revision | None:
    rev = session.get(Revision, revision_id)
    if rev is None or rev.entity_type != entity_type or rev.entity_id != entity_id or rev.kind != "save":
        return None
    return rev


def put_autosave(session: Session, entity_type: str, entity_id: int, snapshot: dict) -> Revision:
    rev = session.scalar(select(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "autosave"))
    if rev is None:
        rev = Revision(entity_type=entity_type, entity_id=entity_id, kind="autosave", snapshot=snapshot)
        session.add(rev)
    else:
        rev.snapshot = snapshot
        from app.timeutil import utcnow

        rev.created_at = utcnow()
    session.flush()
    return rev


def get_autosave(session: Session, entity_type: str, entity_id: int) -> Revision | None:
    return session.scalar(select(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "autosave"))


def clear_autosave(session: Session, entity_type: str, entity_id: int) -> None:
    session.execute(delete(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id, Revision.kind == "autosave"))


def delete_all(session: Session, entity_type: str, entity_id: int) -> None:
    session.execute(delete(Revision).where(Revision.entity_type == entity_type, Revision.entity_id == entity_id))
