"""/api/admin/taxonomy — categories, tags and series."""
from __future__ import annotations

from typing import Literal

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app import defaults
from app.api.guards import admin_required
from app.api.helpers import body
from app.db import db
from app.errors import ApiError
from app.models import Category, Post, Series, Tag
from app.services import audit, settings, taxonomy
from app.services.out import category_out, series_out, tag_out

bp = Blueprint("admin_taxonomy", __name__, url_prefix="/api/admin/taxonomy")


def _sticker(v: str | None) -> str | None:
    if v and v not in defaults.ICONS:
        raise ValueError("没有这个图标")
    return v or None


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryIn(_M):
    name: str | None = Field(default=None, max_length=60)
    slug: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    sticker: str | None = None
    show_on_shelf: bool | None = None

    _s = field_validator("sticker")(_sticker)


class TagIn(_M):
    name: str | None = Field(default=None, max_length=taxonomy.TAG_NAME_MAX)
    slug: str | None = Field(default=None, max_length=80)
    color: Literal["sky", "rose", "mist", "white"] | None = None
    sticker: str | None = None
    description: str | None = Field(default=None, max_length=300)

    _s = field_validator("sticker")(_sticker)


class SeriesIn(_M):
    title: str | None = Field(default=None, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    status: Literal["ongoing", "finished"] | None = None
    cover_media_id: int | None = None


class IdsIn(_M):
    ids: list[int] = Field(max_length=500)


class MergeIn(_M):
    source_ids: list[int] = Field(min_length=1, max_length=50)
    target_id: int


class OrderIn(_M):
    post_ids: list[int] = Field(max_length=500)


def _touch() -> None:
    settings.bump_site_version(db())


# ---- categories ----------------------------------------------------------------------------------------------------------------------
@bp.get("/categories")
@admin_required
def list_categories():
    session = db()
    counts = taxonomy.category_counts(session, public=False)
    public = taxonomy.category_counts(session, public=True)
    rows = session.scalars(select(Category).order_by(Category.sort_order, Category.id))
    return jsonify({"items": [{**category_out(c, counts.get(c.id, 0), admin=True), "public_count": public.get(c.id, 0)} for c in rows]})


@bp.post("/categories")
@admin_required
def create_category():
    data = body(CategoryIn)
    if not data.name:
        raise ApiError(422, "invalid", "分类名不能为空。", fields={"name": "必填"})
    category = taxonomy.create_category(db(), data.name, slug=data.slug, description=data.description or "", sticker=data.sticker,
                                        show_on_shelf=True if data.show_on_shelf is None else data.show_on_shelf)
    audit.record(db(), "category.create", "category", category.id, {"name": category.name})
    _touch()
    response = jsonify(category_out(category, 0, admin=True))
    response.status_code = 201
    return response


@bp.patch("/categories/<int:category_id>")
@admin_required
def update_category(category_id: int):
    data = body(CategoryIn)
    category = taxonomy.category_by_id(db(), category_id)
    sent = data.model_fields_set
    taxonomy.update_category(db(), category, name=data.name, slug=data.slug, description=data.description, sticker=data.sticker,
                             clear_sticker="sticker" in sent and not data.sticker, show_on_shelf=data.show_on_shelf)
    audit.record(db(), "category.update", "category", category.id, {"fields": sorted(sent)})
    _touch()
    return jsonify(category_out(category, taxonomy.category_counts(db(), public=False).get(category.id, 0), admin=True))


@bp.delete("/categories/<int:category_id>")
@admin_required
def delete_category(category_id: int):
    category = taxonomy.category_by_id(db(), category_id)
    reassign = request.args.get("reassign_to")
    moved = taxonomy.delete_category(db(), category, int(reassign) if reassign and reassign.isdigit() else None)
    audit.record(db(), "category.delete", "category", category_id, {"name": category.name, "moved": moved})
    _touch()
    return jsonify({"ok": True, "moved": moved})


@bp.post("/categories/reorder")
@admin_required
def reorder_categories():
    taxonomy.reorder_categories(db(), body(IdsIn).ids)
    _touch()
    return jsonify({"ok": True})


# ---- tags ------------------------------------------------------------------------------------------------------------------------------
@bp.get("/tags")
@admin_required
def list_tags():
    session = db()
    counts = taxonomy.tag_counts(session, public=False)
    items = []
    for t in session.scalars(select(Tag).order_by(Tag.name)):
        posts_n, moments_n = counts.get(t.id, (0, 0))
        items.append({**tag_out(t), "description": t.description, "post_count": posts_n, "moment_count": moments_n, "count": posts_n + moments_n})
    return jsonify({"items": items})


@bp.post("/tags")
@admin_required
def create_tag():
    data = body(TagIn)
    tag = taxonomy.get_or_create_tag(db(), data.name or "")
    if tag is None:
        raise ApiError(422, "invalid", "标签名不能为空。", fields={"name": "必填"})
    taxonomy.update_tag(db(), tag, slug=data.slug, color=data.color, sticker=data.sticker, description=data.description)
    audit.record(db(), "tag.create", "tag", tag.id, {"name": tag.name})
    _touch()
    response = jsonify({**tag_out(tag, 0), "description": tag.description})
    response.status_code = 201
    return response


@bp.patch("/tags/<int:tag_id>")
@admin_required
def update_tag(tag_id: int):
    data = body(TagIn)
    tag = taxonomy.tag_by_id(db(), tag_id)
    sent = data.model_fields_set
    taxonomy.update_tag(db(), tag, name=data.name, slug=data.slug, color=data.color, sticker=data.sticker, description=data.description,
                        clear_sticker="sticker" in sent and not data.sticker)
    audit.record(db(), "tag.update", "tag", tag.id, {"fields": sorted(sent)})
    _touch()
    return jsonify({**tag_out(tag), "description": tag.description})


@bp.post("/tags/merge")
@admin_required
def merge_tags():
    data = body(MergeIn)
    moved = taxonomy.merge_tags(db(), data.source_ids, data.target_id)
    audit.record(db(), "tag.merge", "tag", data.target_id, {"sources": data.source_ids, "moved": moved})
    _touch()
    return jsonify({"ok": True, "moved": moved})


@bp.delete("/tags/<int:tag_id>")
@admin_required
def delete_tag(tag_id: int):
    tag = taxonomy.tag_by_id(db(), tag_id)
    name = tag.name
    taxonomy.delete_tag(db(), tag)
    audit.record(db(), "tag.delete", "tag", tag_id, {"name": name})
    _touch()
    return jsonify({"ok": True})


@bp.post("/tags/cleanup")
@admin_required
def cleanup_tags():
    n = taxonomy.delete_unused_tags(db())
    audit.record(db(), "tag.cleanup", "tag", "", {"deleted": n})
    _touch()
    return jsonify({"deleted": n})


# ---- series ----------------------------------------------------------------------------------------------------------------------------
def _series_row(session, s: Series, counts: dict[int, int]) -> dict:
    return {**series_out(s, counts.get(s.id, 0), admin=True)}


@bp.get("/series")
@admin_required
def list_series():
    session = db()
    counts = taxonomy.series_counts(session, public=False)
    return jsonify({"items": [_series_row(session, s, counts) for s in session.scalars(select(Series).order_by(Series.sort_order, Series.id))]})


@bp.post("/series")
@admin_required
def create_series():
    data = body(SeriesIn)
    if not data.title:
        raise ApiError(422, "invalid", "系列标题不能为空。", fields={"title": "必填"})
    series = taxonomy.create_series(db(), data.title, slug=data.slug, description=data.description or "", status=data.status or "ongoing",
                                    cover_media_id=data.cover_media_id)
    audit.record(db(), "series.create", "series", series.id, {"title": series.title})
    _touch()
    response = jsonify(_series_row(db(), series, {}))
    response.status_code = 201
    return response


@bp.patch("/series/<int:series_id>")
@admin_required
def update_series(series_id: int):
    data = body(SeriesIn)
    series = taxonomy.series_by_id(db(), series_id)
    sent = data.model_fields_set
    taxonomy.update_series(db(), series, title=data.title, slug=data.slug, description=data.description, status=data.status,
                           cover_media_id=data.cover_media_id, clear_cover="cover_media_id" in sent and data.cover_media_id is None)
    audit.record(db(), "series.update", "series", series.id, {"fields": sorted(sent)})
    _touch()
    return jsonify(_series_row(db(), series, taxonomy.series_counts(db(), public=False)))


@bp.delete("/series/<int:series_id>")
@admin_required
def delete_series(series_id: int):
    series = taxonomy.series_by_id(db(), series_id)
    title = series.title
    freed = taxonomy.delete_series(db(), series)
    audit.record(db(), "series.delete", "series", series_id, {"title": title, "posts": freed})
    _touch()
    return jsonify({"ok": True, "posts": freed})


@bp.get("/series/<int:series_id>/posts")
@admin_required
def series_posts(series_id: int):
    series = taxonomy.series_by_id(db(), series_id)
    rows = db().scalars(select(Post).where(Post.series_id == series.id, Post.deleted_at.is_(None)).order_by(Post.series_order, Post.id))
    return jsonify({"items": [{"id": p.id, "title": p.title, "slug": p.slug, "status": p.status, "order": p.series_order} for p in rows]})


@bp.put("/series/<int:series_id>/order")
@admin_required
def order_series(series_id: int):
    series = taxonomy.series_by_id(db(), series_id)
    taxonomy.reorder_series_posts(db(), series, body(OrderIn).post_ids)
    _touch()
    return jsonify({"ok": True})
