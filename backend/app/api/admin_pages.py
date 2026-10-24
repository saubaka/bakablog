"""/api/admin/pages — standalone pages (about, links, ...)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from flask import Blueprint, jsonify
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app import paths
from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.db import db
from app.errors import ApiError
from app.models import Page
from app.services import nav, pages, revisions
from app.services.out import media_out
from app.timeutil import iso, iso_precise

bp = Blueprint("admin_pages", __name__, url_prefix="/api/admin/pages")


class PageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    content_md: str | None = Field(default=None, max_length=400_000)
    template: Literal["plain", "wide", "sidebar"] | None = None
    status: Literal["draft", "published", "unlisted", "private"] | None = None
    seo_title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, max_length=400)
    seo_image_media_id: int | None = None
    published_at: datetime | None = None
    in_nav: bool | None = None
    in_footer: bool | None = None
    expected_updated_at: datetime | None = None

    def changes(self) -> dict:
        return {k: getattr(self, k) for k in self.model_fields_set if k not in ("in_nav", "in_footer", "expected_updated_at")}


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["draft", "published", "unlisted", "private"] | None = None
    q: str = Field(default="", max_length=100)
    trashed: bool = False
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=50, ge=1, le=100)


def page_admin_out(page: Page, *, full: bool = False) -> dict:
    flags = nav.page_flags(db(), page.slug)
    out = {
        "id": page.id, "slug": page.slug, "url": paths.page(page.slug), "title": page.title, "status": page.status, "template": page.template,
        "published_at": iso(page.published_at), "created_at": iso(page.created_at), "updated_at": iso_precise(page.updated_at),
        "deleted_at": iso(page.deleted_at), **flags,
    }
    if full:
        out.update(content_md=page.content_md, toc=page.toc,
                   seo={"title": page.seo_title, "description": page.seo_description, "image": media_out(page.seo_image)})
    return out


def _get(page_id: int) -> Page:
    return pages.by_id(db(), page_id)


@bp.get("")
@admin_required
def list_pages():
    q = query(ListQuery)
    rows, total = pages.admin_list(db(), status=q.status, q=q.q, trashed=q.trashed, page=q.page, per=q.per)
    trashed = int(db().scalar(select(func.count()).select_from(Page).where(Page.deleted_at.is_not(None))) or 0)
    return jsonify({"items": [page_admin_out(p) for p in rows], **page_info(total, q.page, q.per), "counts": {"trashed": trashed}})


@bp.post("")
@admin_required
def create():
    data = body(PageIn)
    page = pages.create(db(), data.changes())
    nav.set_page_flags(db(), page, in_nav=data.in_nav, in_footer=data.in_footer)
    response = jsonify(page_admin_out(page, full=True))
    response.status_code = 201
    return response


@bp.get("/<int:page_id>")
@admin_required
def read(page_id: int):
    return jsonify(page_admin_out(_get(page_id), full=True))


@bp.patch("/<int:page_id>")
@admin_required
def update(page_id: int):
    data = body(PageIn)
    page = pages.update(db(), _get(page_id), data.changes(), expected_updated_at=data.expected_updated_at)
    nav.set_page_flags(db(), page, in_nav=data.in_nav, in_footer=data.in_footer)
    return jsonify(page_admin_out(page, full=True))


@bp.delete("/<int:page_id>")
@admin_required
def trash(page_id: int):
    page = _get(page_id)
    pages.trash(db(), page)
    return jsonify(page_admin_out(page))


@bp.post("/<int:page_id>/restore")
@admin_required
def restore(page_id: int):
    page = _get(page_id)
    pages.restore(db(), page)
    return jsonify(page_admin_out(page))


@bp.delete("/<int:page_id>/purge")
@admin_required
def purge(page_id: int):
    page = _get(page_id)
    if page.deleted_at is None:
        raise ApiError(409, "not_in_trash", "先移到回收站，才能永久删除。")
    pages.purge(db(), page)
    return jsonify({"ok": True})


@bp.get("/<int:page_id>/revisions")
@admin_required
def list_revisions(page_id: int):
    page = _get(page_id)
    return jsonify({"items": [{"id": r.id, "created_at": iso(r.created_at), "title": r.snapshot.get("title", "")} for r in revisions.history(db(), "page", page.id)]})


@bp.get("/<int:page_id>/revisions/<int:revision_id>")
@admin_required
def read_revision(page_id: int, revision_id: int):
    page = _get(page_id)
    rev = revisions.get(db(), "page", page.id, revision_id)
    if rev is None:
        raise ApiError(404)
    return jsonify({"id": rev.id, "created_at": iso(rev.created_at), "snapshot": rev.snapshot})


@bp.post("/<int:page_id>/revisions/<int:revision_id>/restore")
@admin_required
def restore_revision(page_id: int, revision_id: int):
    page = _get(page_id)
    rev = revisions.get(db(), "page", page.id, revision_id)
    if rev is None:
        raise ApiError(404)
    pages.restore_revision(db(), page, rev)
    return jsonify(page_admin_out(page, full=True))
