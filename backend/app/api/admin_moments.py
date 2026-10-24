"""/api/admin/moments — publish box, timeline list, link-card preview."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from flask import Blueprint, jsonify
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app import defaults
from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.config import cfg
from app.db import db
from app.errors import ApiError
from app.models import Moment
from app.services import audit, linkcard, moments, settings
from app.services import media as media_service
from app.services.out import media_out, moment_out
from app.services.site import tz_name
from app.timeutil import month_bounds, utcnow

bp = Blueprint("admin_moments", __name__, url_prefix="/api/admin/moments")


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: int
    alt: str = Field(default="", max_length=300)


class LinkCardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=500)
    title: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=300)
    icon_media_id: int | None = None


class MomentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=moments.TEXT_MAX)
    mood: str | None = Field(default=None, max_length=16)
    tags: list[str] | None = Field(default=None, max_length=20)
    auto_tags: bool = True
    media: list[MediaItem] | None = Field(default=None, max_length=moments.MAX_MEDIA)
    link_card: LinkCardIn | None = None
    pinned: bool | None = None
    visibility: Literal["public", "unlisted", "private"] | None = None
    published_at: datetime | None = None

    @field_validator("mood")
    @classmethod
    def _mood(cls, v: str | None) -> str | None:
        if v and v not in defaults.MOODS:
            raise ValueError("没有这种心情")
        return v or None

    def changes(self) -> dict:
        out = {}
        for key in self.model_fields_set:
            value = getattr(self, key)
            if key == "media" and value is not None:
                value = [m.model_dump() for m in value]
            elif key == "link_card" and value is not None:
                value = value.model_dump()
            out[key] = value
        return out


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: Literal["public", "unlisted", "private"] | None = None
    tag: str | None = Field(default=None, max_length=80)
    mood: str | None = Field(default=None, max_length=16)
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    q: str = Field(default="", max_length=100)
    trashed: bool = False
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=20, ge=1, le=100)

    @field_validator("visibility", "tag", "mood", "month", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if v == "" else v


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["trash", "restore", "purge", "public", "unlisted", "private"]


class PreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=500)
    fetch_icon: bool = True


def moment_admin_out(moment: Moment) -> dict:
    out = moment_out(moment, admin=True)
    out["scheduled"] = moment.published_at > utcnow()
    for item, row in zip(out["media"], moment.media, strict=False):
        item["alt_override"] = row.alt
    return out


def _get(moment_id: int) -> Moment:
    return moments.by_id(db(), moment_id)


@bp.get("")
@admin_required
def list_moments():
    q = query(ListQuery)
    session = db()
    month_range = month_bounds(q.month, tz_name(session)) if q.month else None
    rows, total = moments.admin_list(session, visibility=q.visibility, tag=q.tag, mood=q.mood, month_range=month_range, q=q.q, trashed=q.trashed,
                                     page=q.page, per=q.per)
    counts = {
        "all": int(session.scalar(select(func.count()).select_from(Moment).where(Moment.deleted_at.is_(None))) or 0),
        "trashed": int(session.scalar(select(func.count()).select_from(Moment).where(Moment.deleted_at.is_not(None))) or 0),
    }
    return jsonify({"items": [moment_admin_out(m) for m in rows], **page_info(total, q.page, q.per), "counts": counts})


@bp.post("")
@admin_required
def create():
    moment = moments.create(db(), body(MomentIn).changes())
    response = jsonify(moment_admin_out(moment))
    response.status_code = 201
    return response


@bp.get("/<int:moment_id>")
@admin_required
def read(moment_id: int):
    return jsonify(moment_admin_out(_get(moment_id)))


@bp.patch("/<int:moment_id>")
@admin_required
def update(moment_id: int):
    moment = moments.update(db(), _get(moment_id), body(MomentIn).changes())
    return jsonify(moment_admin_out(moment))


@bp.delete("/<int:moment_id>")
@admin_required
def trash(moment_id: int):
    moment = _get(moment_id)
    moments.trash(db(), moment)
    return jsonify(moment_admin_out(moment))


@bp.post("/<int:moment_id>/restore")
@admin_required
def restore(moment_id: int):
    moment = _get(moment_id)
    moments.restore(db(), moment)
    return jsonify(moment_admin_out(moment))


@bp.delete("/<int:moment_id>/purge")
@admin_required
def purge(moment_id: int):
    moment = _get(moment_id)
    if moment.deleted_at is None:
        raise ApiError(409, "not_in_trash", "先移到回收站，才能永久删除。")
    moments.purge(db(), moment)
    return jsonify({"ok": True})


@bp.post("/<int:moment_id>/duplicate")
@admin_required
def duplicate(moment_id: int):
    copy = moments.duplicate(db(), _get(moment_id))
    response = jsonify(moment_admin_out(copy))
    response.status_code = 201
    return response


@bp.post("/batch")
@admin_required
def batch():
    data = body(BatchIn)
    session = db()
    done = 0
    for moment in session.scalars(select(Moment).where(Moment.id.in_(data.ids))):
        if data.action == "trash":
            moments.trash(session, moment)
        elif data.action == "restore":
            moments.restore(session, moment)
        elif data.action == "purge":
            if moment.deleted_at is None:
                continue
            moments.purge(session, moment)
        else:
            moments.update(session, moment, {"visibility": data.action})
        done += 1
    audit.record(session, "moment.batch", "moment", "", {"action": data.action, "count": done})
    settings.bump_site_version(session)
    return jsonify({"done": done})


@bp.post("/link-preview")
@admin_required
def link_preview():
    """Paste a URL in the publish box: title, description and icon are fetched by the server (SSRF-guarded)."""
    data = body(PreviewIn)
    result = linkcard.preview(data.url)
    icon = None
    if data.fetch_icon and result.icon_url:
        raw = linkcard.fetch_icon(result.icon_url)
        if raw:
            try:
                media, _ = media_service.create(db(), cfg(), raw, f"{result.domain}-icon", alt=f"{result.domain} 的图标", kind="icon")
                icon = media
            except ApiError:
                icon = None
    return jsonify({
        "url": result.url, "title": result.title, "description": result.description, "domain": result.domain, "site_name": result.site_name,
        "icon_media_id": icon.id if icon else None, "icon": media_out(icon) if icon else None,
    })
