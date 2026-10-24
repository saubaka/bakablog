"""The recycle bin: posts, moments, pages and pictures that were deleted stay here for 30 days."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.errors import ApiError
from app.models import Media, MediaRef, Moment, Page, Post
from app.services import audit, moments, pages, posts, refs, settings
from app.services import media as media_service
from app.timeutil import iso, utcnow

RETENTION_DAYS = 30
TYPES = ("post", "moment", "page", "media")


def _title(kind: str, item: Any) -> str:
    if kind == "post" or kind == "page":
        return item.title
    if kind == "moment":
        return (item.content_md or "（只有图片或链接的动态）")[:60]
    return item.filename or f"图片 {item.id}"


def _model(kind: str):
    return {"post": Post, "moment": Moment, "page": Page, "media": Media}[kind]


def listing(session: Session) -> list[dict]:
    out = []
    for kind in TYPES:
        model = _model(kind)
        for item in session.scalars(select(model).where(model.deleted_at.is_not(None)).order_by(model.deleted_at.desc())):
            expires = item.deleted_at + timedelta(days=RETENTION_DAYS)
            out.append({"type": kind, "id": item.id, "title": _title(kind, item), "deleted_at": iso(item.deleted_at), "expires_at": iso(expires),
                        "days_left": max(0, (expires - utcnow()).days)})
    out.sort(key=lambda r: r["deleted_at"], reverse=True)
    return out


def _get(session: Session, kind: str, item_id: int):
    if kind not in TYPES:
        raise ApiError(404)
    item = session.get(_model(kind), item_id)
    if item is None or item.deleted_at is None:
        raise ApiError(404, "not_found", "回收站里没有这一项。")
    return item


def restore(session: Session, kind: str, item_id: int) -> None:
    item = _get(session, kind, item_id)
    if kind == "post":
        posts.restore(session, item)
    elif kind == "moment":
        moments.restore(session, item)
    elif kind == "page":
        pages.restore(session, item)
    else:
        item.deleted_at = None
        audit.record(session, "media.restore", "media", item.id)
    settings.bump_site_version(session)


def _purge_media(session: Session, cfg: Config, media: Media) -> None:
    pairs = [(r.entity_type, r.entity_id) for r in session.scalars(select(MediaRef).where(MediaRef.media_id == media.id))]
    old_hash, media_id = media.hash, media.id
    media_service.purge(session, cfg, media)
    refs.rerender_entities(session, pairs)
    audit.record(session, "media.purge", "media", media_id, {"hash": old_hash, "was_used": len(pairs)})


def purge(session: Session, cfg: Config, kind: str, item_id: int) -> None:
    item = _get(session, kind, item_id)
    if kind == "post":
        posts.purge(session, item)
    elif kind == "moment":
        moments.purge(session, item)
    elif kind == "page":
        pages.purge(session, item)
    else:
        _purge_media(session, cfg, item)
    settings.bump_site_version(session)


def empty(session: Session, cfg: Config) -> int:
    n = 0
    for row in listing(session):
        purge(session, cfg, row["type"], row["id"])
        n += 1
    return n


def purge_expired(session: Session, cfg: Config) -> dict[str, int]:
    cutoff = utcnow() - timedelta(days=RETENTION_DAYS)
    counts = dict.fromkeys(TYPES, 0)
    for kind in TYPES:
        model = _model(kind)
        for item in list(session.scalars(select(model).where(model.deleted_at.is_not(None), model.deleted_at < cutoff))):
            purge(session, cfg, kind, item.id)
            counts[kind] += 1
    return counts
