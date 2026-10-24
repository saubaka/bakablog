"""Pictures: the public file route /media/<hash>/<size>.webp and the admin media library API."""
from __future__ import annotations

from typing import Literal

from flask import Blueprint, jsonify, request, send_file
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.config import cfg
from app.db import after_commit, db
from app.errors import ApiError
from app.models import Media, MediaRef
from app.services import audit, refs, settings
from app.services import media as media_service
from app.services.out import media_out
from app.timeutil import utcnow

public = Blueprint("media_public", __name__)
bp = Blueprint("admin_media", __name__, url_prefix="/api/admin/media")


# ---- public files -----------------------------------------------------------------------------------------------------------------
@public.get("/media/<media_hash>/<int:size>.webp")
def serve(media_hash: str, size: int):
    if not media_service.HASH_RE.match(media_hash) or size not in media_service.SIZES:
        raise ApiError(404)
    path = media_service.media_path(cfg(), media_hash, size)
    if not path.is_file():
        raise ApiError(404)
    response = send_file(path, mimetype="image/webp", conditional=True, max_age=31536000, etag=True)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"  # feed readers show these pictures from another origin
    response.headers.pop("Content-Security-Policy", None)
    return response


# ---- admin ------------------------------------------------------------------------------------------------------------------------
class ListQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    q: str = Field(default="", max_length=100)
    kind: Literal["image", "icon"] | None = None
    unused: bool = False
    alt: Literal["missing"] | None = None   # pictures that still need a description (the dashboard's to-do list links here)
    trashed: bool = False
    sort: Literal["new", "old", "name", "size"] = "new"
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=40, ge=1, le=100)


class PatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alt: str | None = Field(default=None, max_length=300)
    caption: str | None = Field(default=None, max_length=500)
    filename: str | None = Field(default=None, max_length=200)


def _read_upload() -> tuple[bytes, str]:
    upload = request.files.get("file")
    if upload is None:
        raise ApiError(422, "no_file", "没有收到文件。", fields={"file": "必填"})
    limit = cfg().max_upload_bytes
    data = upload.stream.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, "too_large", f"文件太大了（上限 {limit // (1024 * 1024)} MB）。")
    return data, upload.filename or ""


def _get(media_id: int) -> Media:
    media = db().get(Media, media_id)
    if media is None:
        raise ApiError(404)
    return media


def _out(media: Media, counts: dict[int, int] | None = None) -> dict:
    n = (counts or media_service.usage_counts(db(), [media.id])).get(media.id, 0)
    return media_out(media, admin=True, usage_count=n)


@bp.post("")
@admin_required
def upload():
    data, filename = _read_upload()
    alt = (request.form.get("alt") or "")[:300]
    caption = (request.form.get("caption") or "")[:500]
    media, created = media_service.create(db(), cfg(), data, filename, alt=alt, caption=caption)
    if created:
        audit.record(db(), "media.upload", "media", media.id, {"filename": media.filename, "bytes": media.bytes})
    response = jsonify({**_out(media), "duplicate": not created})
    response.status_code = 201 if created else 200
    return response


@bp.get("")
@admin_required
def list_media():
    q = query(ListQuery)
    session = db()
    stmt = select(Media).where(Media.deleted_at.is_not(None) if q.trashed else Media.deleted_at.is_(None))
    if q.kind:
        stmt = stmt.where(Media.kind == q.kind)
    if q.q:
        like = f"%{q.q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(Media.filename.like(like) | Media.alt.like(like) | Media.caption.like(like))
    if q.unused:
        stmt = stmt.where(~select(MediaRef.id).where(MediaRef.media_id == Media.id).exists())
    if q.alt == "missing":
        stmt = stmt.where(Media.kind == "image", Media.alt == "")
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"new": Media.id.desc(), "old": Media.id.asc(), "name": func.lower(Media.filename), "size": Media.bytes.desc()}[q.sort]
    rows = list(session.scalars(stmt.order_by(order).limit(q.per).offset((q.page - 1) * q.per)))
    counts = media_service.usage_counts(session, [m.id for m in rows])
    return jsonify({"items": [_out(m, counts) for m in rows], **page_info(total, q.page, q.per)})


@bp.get("/<int:media_id>")
@admin_required
def detail(media_id: int):
    media = _get(media_id)
    return jsonify({**_out(media), "usage": refs.usage(db(), media.id)})


@bp.get("/<int:media_id>/usage")
@admin_required
def usage(media_id: int):
    _get(media_id)
    return jsonify({"items": refs.usage(db(), media_id)})


@bp.patch("/<int:media_id>")
@admin_required
def patch(media_id: int):
    data = body(PatchIn)
    media = _get(media_id)
    changed = {}
    for field in ("alt", "caption", "filename"):
        value = getattr(data, field)
        if value is not None and value.strip() != getattr(media, field):
            setattr(media, field, media_service.clean_filename(value) if field == "filename" else value.strip())
            changed[field] = True
    if changed:
        db().flush()
        if "alt" in changed or "caption" in changed:
            refs.rerender_users(db(), media.id)
        settings.bump_site_version(db())
        audit.record(db(), "media.update", "media", media.id, {"fields": sorted(changed)})
    return jsonify(_out(media))


@bp.post("/<int:media_id>/replace")
@admin_required
def replace(media_id: int):
    media = _get(media_id)
    data, filename = _read_upload()
    old_hash = media_service.replace(db(), cfg(), media, data, filename)
    if old_hash != media.hash:
        config = cfg()
        after_commit(lambda: media_service.delete_files(config, old_hash))
        refs.rerender_users(db(), media.id)
        settings.bump_site_version(db())
        audit.record(db(), "media.replace", "media", media.id, {"filename": media.filename})
    return jsonify(_out(media))


@bp.delete("/<int:media_id>")
@admin_required
def trash(media_id: int):
    """Move to the trash. A picture that is still used needs ?force=1 (the pages keep pointing at it until it is purged)."""
    media = _get(media_id)
    used = media_service.usage_counts(db(), [media.id]).get(media.id, 0)
    if used and request.args.get("force") not in ("1", "true"):
        raise ApiError(409, "in_use", f"这张图片还在 {used} 处使用，确定要删除吗？", extra={"usage": refs.usage(db(), media.id)})
    media.deleted_at = media.deleted_at or utcnow()
    audit.record(db(), "media.trash", "media", media.id, {"filename": media.filename, "used": used})
    return jsonify(_out(media))


@bp.post("/<int:media_id>/restore")
@admin_required
def restore(media_id: int):
    media = _get(media_id)
    media.deleted_at = None
    audit.record(db(), "media.restore", "media", media.id)
    return jsonify(_out(media))


@bp.delete("/<int:media_id>/purge")
@admin_required
def purge(media_id: int):
    media = _get(media_id)
    users = list(db().scalars(select(MediaRef).where(MediaRef.media_id == media.id)))
    old_hash = media.hash
    entity_refs = [(r.entity_type, r.entity_id) for r in users]
    media_service.purge(db(), cfg(), media)  # files go now; fine, the row goes with this transaction
    refs.rerender_entities(db(), entity_refs)
    settings.bump_site_version(db())
    audit.record(db(), "media.purge", "media", media_id, {"hash": old_hash, "was_used": len(entity_refs)})
    return jsonify({"ok": True})

