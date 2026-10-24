"""/api/admin/posts — the post list, the editor's save / autosave / preview, history, batch actions."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from flask import Blueprint, jsonify
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from app import defaults, paths
from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.db import db
from app.errors import ApiError
from app.models import Category, Post, Series
from app.services import audit, posts, revisions, settings, taxonomy
from app.services.out import category_out, media_out, post_card, series_out, tag_out
from app.services.site import absolute
from app.timeutil import iso, utcnow

bp = Blueprint("admin_posts", __name__, url_prefix="/api/admin/posts")


class PostIn(BaseModel):
    """Create and update share this shape. Only the fields that are sent are changed."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=1000)
    content_md: str | None = Field(default=None, max_length=400_000)
    status: Literal["draft", "published", "unlisted", "private"] | None = None
    published_at: datetime | None = None
    category_id: int | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    series_id: int | None = None
    series_order: int | None = Field(default=None, ge=1, le=100000)
    cover_media_id: int | None = None
    cover_alt: str | None = Field(default=None, max_length=300)
    cover_focus_x: float | None = Field(default=None, ge=0, le=100)
    cover_focus_y: float | None = Field(default=None, ge=0, le=100)
    pinned: bool | None = None
    featured: bool | None = None
    card_style: Literal["auto", "cover", "side", "note", "quote"] | None = None
    show_toc: bool | None = None
    show_reading_time: bool | None = None
    show_author_card: bool | None = None
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=400)
    seo_image_media_id: int | None = None
    canonical_url: str | None = Field(default=None, max_length=500)
    expected_updated_at: datetime | None = None

    @field_validator("canonical_url")
    @classmethod
    def _canonical(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("需要完整的 http(s) 链接")
        return v

    def changes(self) -> dict:
        return {k: getattr(self, k) for k in self.model_fields_set if k != "expected_updated_at"}


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["all", "draft", "published", "scheduled", "unlisted", "private", "trashed"] = "all"
    category: int | None = None
    tag: str | None = Field(default=None, max_length=80)
    series: int | None = None
    q: str = Field(default="", max_length=100)
    date_from: datetime | None = Field(default=None, alias="from")
    date_to: datetime | None = Field(default=None, alias="to")
    sort: Literal["updated", "published", "created", "title", "views"] = "updated"
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=20, ge=1, le=100)

    @field_validator("category", "series", "tag", "date_from", "date_to", mode="before")
    @classmethod
    def _blank(cls, v):
        return None if v == "" else v


class BatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[int] = Field(min_length=1, max_length=200)
    action: Literal["publish", "draft", "category", "add_tags", "remove_tags", "pin", "unpin", "feature", "unfeature", "trash", "restore", "purge", "regenerate_summary"]
    category_id: int | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class AutosaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    content_md: str | None = Field(default=None, max_length=400_000)
    tags: list[str] | None = Field(default=None, max_length=20)

    def changes(self) -> dict:
        return {k: getattr(self, k) for k in self.model_fields_set}


# ---- output --------------------------------------------------------------------------------------------------------------------------
def post_admin_out(post: Post, *, full: bool = False) -> dict:
    out = {
        **post_card(post, admin=True),
        "scheduled": posts.is_scheduled(post),
        "summary_auto": post.summary_auto,
        "category_id": post.category_id,
        "series_id": post.series_id,
        "series_order": post.series_order,
        "preview_path": f"{paths.post(post.slug)}",
    }
    if full:
        session = db()
        out.update(
            content_md=post.content_md,
            show_toc=post.show_toc,
            show_reading_time=post.show_reading_time,
            show_author_card=post.show_author_card,
            seo={"title": post.seo_title, "description": post.seo_description, "image": media_out(post.seo_image), "canonical_url": post.canonical_url},
            toc=post.toc,
            category=category_out(post.category, admin=True),
            series_info=series_out(post.series, admin=True),
        )
        auto = revisions.get_autosave(session, "post", post.id)
        out["autosave"] = ({"saved_at": iso(auto.created_at), "snapshot": auto.snapshot}
                           if auto is not None and auto.created_at > post.updated_at else None)
        out["tags"] = [tag_out(t) for t in post.tags]
    return out


def _get(post_id: int) -> Post:
    return posts.by_id(db(), post_id)


def _counts(session) -> dict[str, int]:
    now = utcnow()
    live = Post.deleted_at.is_(None)

    def n(*conds) -> int:
        return int(session.scalar(select(func.count()).select_from(Post).where(*conds)) or 0)

    return {
        "all": n(live), "draft": n(live, Post.status == "draft"), "published": n(live, Post.status == "published", Post.published_at <= now),
        "scheduled": n(live, Post.status == "published", Post.published_at > now), "unlisted": n(live, Post.status == "unlisted"),
        "private": n(live, Post.status == "private"), "trashed": n(Post.deleted_at.is_not(None)),
    }


# ---- list / create / read -------------------------------------------------------------------------------------------------------------
@bp.get("")
@admin_required
def list_posts():
    q = query(ListQuery)
    session = db()
    rows, total = posts.admin_list(
        session, status=None if q.status == "all" else q.status, category_id=q.category, tag=q.tag, series_id=q.series, q=q.q,
        date_from=q.date_from, date_to=q.date_to, sort=q.sort, page=q.page, per=q.per,
    )
    return jsonify({"items": [post_admin_out(p) for p in rows], **page_info(total, q.page, q.per), "counts": _counts(session)})


@bp.post("")
@admin_required
def create():
    data = body(PostIn)
    post = posts.create(db(), data.changes())
    response = jsonify(post_admin_out(post, full=True))
    response.status_code = 201
    return response


@bp.get("/<int:post_id>")
@admin_required
def read(post_id: int):
    return jsonify(post_admin_out(_get(post_id), full=True))


@bp.patch("/<int:post_id>")
@admin_required
def update(post_id: int):
    data = body(PostIn)
    post = posts.update(db(), _get(post_id), data.changes(), expected_updated_at=data.expected_updated_at)
    return jsonify(post_admin_out(post, full=True))


@bp.delete("/<int:post_id>")
@admin_required
def trash(post_id: int):
    post = _get(post_id)
    posts.trash(db(), post)
    return jsonify(post_admin_out(post))


@bp.post("/<int:post_id>/restore")
@admin_required
def restore(post_id: int):
    post = _get(post_id)
    posts.restore(db(), post)
    return jsonify(post_admin_out(post))


@bp.delete("/<int:post_id>/purge")
@admin_required
def purge(post_id: int):
    post = _get(post_id)
    if post.deleted_at is None:
        raise ApiError(409, "not_in_trash", "先移到回收站，才能永久删除。")
    posts.purge(db(), post)
    return jsonify({"ok": True})


@bp.post("/<int:post_id>/duplicate")
@admin_required
def duplicate(post_id: int):
    copy = posts.duplicate(db(), _get(post_id))
    response = jsonify(post_admin_out(copy, full=True))
    response.status_code = 201
    return response


# ---- editor support --------------------------------------------------------------------------------------------------------------------
@bp.put("/<int:post_id>/autosave")
@admin_required
def autosave(post_id: int):
    data = body(AutosaveIn)
    post = _get(post_id)
    posts.autosave(db(), post, data.changes())
    return jsonify({"saved_at": iso(utcnow())})


@bp.post("/<int:post_id>/preview-token")
@admin_required
def preview_token(post_id: int):
    post = _get(post_id)
    token = posts.preview_token(post)
    path = f"{paths.post(post.slug)}?preview={token}"
    return jsonify({"token": token, "path": path, "url": absolute(path), "expires_in_days": 7})


@bp.get("/<int:post_id>/revisions")
@admin_required
def list_revisions(post_id: int):
    post = _get(post_id)
    items = revisions.history(db(), "post", post.id)
    return jsonify({"items": [{"id": r.id, "created_at": iso(r.created_at), "title": r.snapshot.get("title", ""),
                               "length": len(r.snapshot.get("content_md", ""))} for r in items]})


@bp.get("/<int:post_id>/revisions/<int:revision_id>")
@admin_required
def read_revision(post_id: int, revision_id: int):
    post = _get(post_id)
    rev = revisions.get(db(), "post", post.id, revision_id)
    if rev is None:
        raise ApiError(404)
    return jsonify({"id": rev.id, "created_at": iso(rev.created_at), "snapshot": rev.snapshot})


@bp.post("/<int:post_id>/revisions/<int:revision_id>/restore")
@admin_required
def restore_revision(post_id: int, revision_id: int):
    post = _get(post_id)
    rev = revisions.get(db(), "post", post.id, revision_id)
    if rev is None:
        raise ApiError(404)
    posts.restore_revision(db(), post, rev)
    return jsonify(post_admin_out(post, full=True))


# ---- batch -------------------------------------------------------------------------------------------------------------------------------
@bp.post("/batch")
@admin_required
def batch():
    data = body(BatchIn)
    session = db()
    found = {p.id: p for p in session.scalars(select(Post).where(Post.id.in_(data.ids)))}
    missing = [i for i in data.ids if i not in found]
    if data.action == "category" and data.category_id is not None:
        taxonomy.category_by_id(session, data.category_id)
    if data.action in ("add_tags", "remove_tags") and not data.tags:
        raise ApiError(422, "invalid", "请选择标签。", fields={"tags": "必填"})
    done = 0
    for post in found.values():
        if data.action == "trash":
            posts.trash(session, post)
        elif data.action == "restore":
            posts.restore(session, post)
        elif data.action == "purge":
            if post.deleted_at is None:
                continue
            posts.purge(session, post)
        elif data.action == "publish":
            posts.update(session, post, {"status": "published"})
        elif data.action == "draft":
            posts.update(session, post, {"status": "draft"})
        elif data.action == "category":
            posts.update(session, post, {"category_id": data.category_id})
        elif data.action == "add_tags":
            posts.update(session, post, {"tags": list(dict.fromkeys([t.name for t in post.tags] + data.tags))})
        elif data.action == "remove_tags":
            drop = {t.lower() for t in data.tags}
            posts.update(session, post, {"tags": [t.name for t in post.tags if t.name.lower() not in drop]})
        elif data.action in ("pin", "unpin"):
            posts.update(session, post, {"pinned": data.action == "pin"})
        elif data.action in ("feature", "unfeature"):
            posts.update(session, post, {"featured": data.action == "feature"})
        elif data.action == "regenerate_summary":
            post.summary_auto = True       # back to "cut from the text"; hand-written summaries are replaced on purpose, the author asked for it
            posts.rerender(session, post)
        done += 1
    audit.record(session, "post.batch", "post", "", {"action": data.action, "count": done})
    settings.bump_site_version(session)
    return jsonify({"done": done, "missing": missing})


_ = (Category, Series, defaults)
