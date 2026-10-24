"""/api/admin — dashboard, statistics, recycle bin, audit log, system (status, backups, jobs), Markdown preview, helpers."""
from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Literal

from flask import Blueprint, current_app, jsonify, request, send_file
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app import paths
from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.config import cfg
from app.db import database, db
from app.errors import ApiError
from app.jobs import maintenance
from app.models import AuditLog, Category, Media, MediaRef, Moment, Page, Post, Series, Tag
from app.services import audit, backup, posts, settings, stats, system, transfer, trash
from app.services import markdown as md
from app.services.site import tz_name
from app.services.slug import is_valid_slug, slugify, unique_slug
from app.timeutil import iso, local, month_bounds, utcnow

bp = Blueprint("admin_system", __name__, url_prefix="/api/admin")
RESTORE_UPLOAD_MAX = 2 * 1024**3
IMPORT_UPLOAD_MAX = 600 * 1024**2


# ---- dashboard ---------------------------------------------------------------------------------------------------------------------
@bp.get("/dashboard")
@admin_required
def dashboard():
    session = db()
    now = utcnow()
    tz = tz_name(session)
    live = Post.deleted_at.is_(None)

    def n(*conds) -> int:
        return int(session.scalar(select(func.count()).select_from(Post).where(*conds)) or 0)

    month_start, month_end = month_bounds(local(now, tz).strftime("%Y-%m"), tz)
    moments_month = int(session.scalar(select(func.count()).select_from(Moment).where(
        Moment.deleted_at.is_(None), Moment.published_at >= month_start, Moment.published_at < month_end)) or 0)
    week = stats.summary(session, 7, tz)
    cfg_ = cfg()

    todo: list[dict] = []
    for p in session.scalars(select(Post).where(live, Post.status == "draft", Post.updated_at < now - timedelta(days=7)).order_by(Post.updated_at).limit(5)):
        todo.append({"kind": "stale_draft", "id": p.id, "title": p.title, "days": (now - p.updated_at).days, "admin_url": f"/admin/posts/{p.id}"})
    for p in session.scalars(select(Post).where(live, Post.status == "published", Post.published_at > now, Post.published_at < now + timedelta(days=7))
                             .order_by(Post.published_at).limit(5)):
        todo.append({"kind": "scheduled_soon", "id": p.id, "title": p.title, "at": iso(p.published_at), "admin_url": f"/admin/posts/{p.id}"})
    for p in session.scalars(select(Post).where(live, Post.status == "published", Post.cover_media_id.is_(None)).order_by(Post.published_at.desc()).limit(5)):
        todo.append({"kind": "missing_cover", "id": p.id, "title": p.title, "admin_url": f"/admin/posts/{p.id}"})
    for p in session.scalars(select(Post).where(live, Post.status == "published", Post.summary == "").limit(5)):
        todo.append({"kind": "missing_summary", "id": p.id, "title": p.title, "admin_url": f"/admin/posts/{p.id}"})
    no_alt = int(session.scalar(select(func.count()).select_from(Media).where(
        Media.deleted_at.is_(None), Media.alt == "", Media.kind == "image", select(MediaRef.id).where(MediaRef.media_id == Media.id).exists())) or 0)
    if no_alt:
        todo.append({"kind": "image_no_alt", "count": no_alt, "admin_url": "/admin/media?alt=missing"})

    status = system.status(session, cfg_, database())
    return jsonify({
        "stats": {
            "posts": {"published": n(live, Post.status == "published", Post.published_at <= now), "draft": n(live, Post.status == "draft"),
                      "scheduled": n(live, Post.status == "published", Post.published_at > now)},
            "moments_month": moments_month, "views_7d": week["total_views"], "uniques_7d": week["total_uniques"],
            "storage": {"media_bytes": status["media_bytes"], "db_bytes": status["db_bytes"], "backup_bytes": status["backup_bytes"]},
        },
        "views_series": week["series"],
        "todo": todo,
        "recent": [{"at": iso(a.at), "action": a.action, "actor": a.actor_name, "target_type": a.target_type, "target_id": a.target_id, "summary": a.summary}
                   for a in audit.recent(session, limit=10)],
        "health": {"version": status["version"], "build": status["build"], "db_bytes": status["db_bytes"], "disk_free": status["disk"]["free"],
                   "last_backup": status["last_backup"], "schema_ok": status["schema_revision"] == status["schema_head"]},
    })


# ---- statistics -----------------------------------------------------------------------------------------------------------------------
class StatsQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    days: int = 30

    @field_validator("days")
    @classmethod
    def _days(cls, v: int) -> int:
        if v not in (7, 30, 90):
            raise ValueError("只能是 7、30 或 90")
        return v


@bp.get("/stats")
@admin_required
def get_stats():
    q = query(StatsQuery)
    return jsonify(stats.summary(db(), q.days, tz_name(db())))


# ---- recycle bin --------------------------------------------------------------------------------------------------------------------------
class TrashRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["post", "moment", "page", "media"]
    id: int


@bp.get("/trash")
@admin_required
def get_trash():
    return jsonify({"items": trash.listing(db()), "retention_days": trash.RETENTION_DAYS})


@bp.post("/trash/restore")
@admin_required
def restore_trash():
    data = body(TrashRef)
    trash.restore(db(), data.type, data.id)
    return jsonify({"ok": True})


@bp.delete("/trash/<kind>/<int:item_id>")
@admin_required
def purge_trash(kind: str, item_id: int):
    trash.purge(db(), cfg(), kind, item_id)
    return jsonify({"ok": True})


@bp.delete("/trash")
@admin_required
def empty_trash():
    n = trash.empty(db(), cfg())
    audit.record(db(), "trash.empty", "trash", "", {"count": n})
    return jsonify({"purged": n})


# ---- audit log -------------------------------------------------------------------------------------------------------------------------------
class AuditQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: str | None = Field(default=None, max_length=48)
    target_type: str | None = Field(default=None, max_length=24)
    page: int = Field(default=1, ge=1, le=100000)
    per: int = Field(default=50, ge=1, le=200)


@bp.get("/audit")
@admin_required
def get_audit():
    q = query(AuditQuery)
    session = db()
    stmt = select(AuditLog)
    if q.action:
        stmt = stmt.where(AuditLog.action.like(f"{q.action}%"))
    if q.target_type:
        stmt = stmt.where(AuditLog.target_type == q.target_type)
    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = session.scalars(stmt.order_by(AuditLog.id.desc()).limit(q.per).offset((q.page - 1) * q.per))
    return jsonify({
        "items": [{"id": a.id, "at": iso(a.at), "actor": a.actor_name, "action": a.action, "target_type": a.target_type, "target_id": a.target_id,
                   "summary": a.summary, "ip_prefix": a.ip_prefix} for a in rows],
        **page_info(total, q.page, q.per),
    })


# ---- system ---------------------------------------------------------------------------------------------------------------------------------
@bp.get("/system/status")
@admin_required
def system_status():
    return jsonify(system.status(db(), cfg(), database()))


@bp.get("/system/backups")
@admin_required
def list_backups():
    return jsonify({"items": [b.as_dict() for b in backup.list_backups(cfg())]})


@bp.post("/system/backups")
@admin_required
def create_backup():
    info = backup.create(cfg(), database(), label="manual")
    audit.record(db(), "system.backup", "backup", info.name, {"bytes": info.bytes})
    response = jsonify(info.as_dict())
    response.status_code = 201
    return response


@bp.get("/system/backups/<name>/download")
@admin_required
def download_backup(name: str):
    path = backup.backup_path(cfg(), name)
    audit.record(db(), "system.backup_download", "backup", name)
    db().commit()
    return send_file(path, as_attachment=True, download_name=name, mimetype="application/gzip", max_age=0)


@bp.delete("/system/backups/<name>")
@admin_required
def delete_backup(name: str):
    backup.backup_path(cfg(), name).unlink()
    audit.record(db(), "system.backup_delete", "backup", name)
    return jsonify({"ok": True})


@bp.post("/system/restore")
@admin_required
def restore_backup():
    """Restore from a stored backup ({"name", "confirm": "restore"}) or an uploaded one (multipart: file, confirm=restore)."""
    request.max_content_length = RESTORE_UPLOAD_MAX
    tmp: Path | None = None
    if request.files.get("file") is not None:
        confirm = request.form.get("confirm")
        upload = request.files["file"]
        folder = cfg().backup_dir
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".upload-", suffix=".tar.gz", delete=False) as fh:
            upload.save(fh)
            tmp = Path(fh.name)
        archive = tmp
    else:
        data = request.get_json(silent=True) or {}
        confirm = data.get("confirm")
        archive = backup.backup_path(cfg(), str(data.get("name", "")))
    try:
        if confirm != "restore":
            raise ApiError(422, "confirm_required", "恢复会覆盖现在的全部数据，请确认。", fields={"confirm": "需要 restore"})
        db().commit()  # this request's own transaction must not hold the write lock while the database is replaced
        result = backup.restore(current_app._get_current_object(), archive)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    # the restored database replaced the one this request was using; record the event in the new one
    db().rollback()
    audit.record(db(), "system.restore", "backup", result["restored_from"], {"safety_backup": result["safety_backup"]})
    return jsonify(result)


@bp.get("/system/export")
@admin_required
def export_markdown():
    """Everything as Markdown files with front matter plus the pictures, in one zip (see services/transfer.py)."""
    session = db()
    out = transfer.export_zip(session, cfg(), tz_name(session))
    audit.record(session, "system.export", "system", "markdown")
    session.commit()                      # a GET runs in a read session that is not committed for us; this entry must be kept
    stamp = local(utcnow(), tz_name(session)).strftime("%Y%m%d-%H%M")
    return send_file(out, as_attachment=True, download_name=f"markdown-export-{stamp}.zip", mimetype="application/zip", max_age=0)


@bp.post("/system/import")
@admin_required
def import_markdown():
    """Import a zip of Markdown files (this site's export, or a Hexo / Hugo / Jekyll folder). Drafts unless `status=keep` is sent."""
    request.max_content_length = IMPORT_UPLOAD_MAX
    upload = request.files.get("file")
    if upload is None:
        raise ApiError(422, "invalid", "请选择一个 .zip 压缩包。", fields={"file": "必填"})
    keep = request.form.get("status") == "keep"
    session = db()
    with tempfile.TemporaryFile() as spool:
        upload.save(spool)
        spool.seek(0)
        result = transfer.import_zip(session, cfg(), spool, tz_name(session), keep_status=keep)
    audit.record(session, "system.import", "system", "markdown", {k: v for k, v in result.items() if k != "warnings"})
    return jsonify(result)


@bp.get("/system/jobs")
@admin_required
def get_jobs():
    return jsonify({"jobs": system.jobs(db()), "available": list(maintenance.JOBS)})


@bp.post("/system/jobs/<name>")
@admin_required
def run_job(name: str):
    if name not in maintenance.JOBS or name == "backup":
        raise ApiError(404)
    # the request transaction holds the write lock: finish it first so the job can use its own
    db().commit()
    result = maintenance.run_one(current_app._get_current_object(), name)
    audit.record(db(), f"system.job.{name}", "system", name, {k: v for k, v in result.items() if k != "ok"})
    return jsonify(result)


# ---- markdown preview and small helpers ---------------------------------------------------------------------------------------------------
class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(default="", max_length=400_000)
    profile: Literal["post", "moment"] = "post"


@bp.post("/markdown/preview")
@admin_required
def markdown_preview():
    """Rendered by the same pipeline as publishing, so the preview is exactly what visitors will get."""
    data = body(PreviewIn)
    result = md.render(data.text, session=db(), profile=data.profile, site_host=posts.site_host())
    return jsonify({"html": result.html, "toc": result.toc, "summary": result.summary, "word_count": result.word_count,
                    "reading_minutes": result.reading_minutes, "warnings": result.warnings, "media_ids": result.media_ids})


class SlugIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["post", "page", "category", "tag", "series"] = "post"
    exclude_id: int | None = None


@bp.post("/utils/slug")
@admin_required
def make_slug():
    data = body(SlugIn)
    model = {"post": Post, "page": Page, "category": Category, "tag": Tag, "series": Series}[data.kind]
    reserved = paths.RESERVED_PAGE_SLUGS if data.kind == "page" else frozenset()
    slug = unique_slug(db(), model, slugify(data.title), exclude_id=data.exclude_id, fallback=data.kind, reserved=reserved)
    return jsonify({"slug": slug, "valid": is_valid_slug(slug)})


_ = settings
