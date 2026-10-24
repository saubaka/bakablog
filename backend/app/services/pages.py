"""Standalone pages (关于, 友链, 使用说明 ...): top-level addresses like /about."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import defaults, paths
from app.errors import ApiError
from app.models import Media, Page
from app.services import audit, redirects, refs, revisions, search, settings
from app.services import markdown as md
from app.services.posts import site_host
from app.services.slug import is_reserved_page_slug, is_valid_slug, slugify, unique_slug
from app.timeutil import as_utc, utcnow


def by_id(session: Session, page_id: int) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise ApiError(404, "not_found", "没有这个页面。")
    return page


def snapshot(page: Page) -> dict[str, Any]:
    return {"title": page.title, "slug": page.slug, "content_md": page.content_md, "template": page.template, "status": page.status}


def _render(session: Session, page: Page) -> md.RenderResult:
    result = md.render(page.content_md, session=session, profile="post", site_host=site_host())
    page.content_html = result.html
    page.toc = result.toc
    return result


def _sync_refs(session: Session, page: Page, media_ids: list[int]) -> None:
    refs.sync(session, "page", page.id, [*media_ids, page.seo_image_media_id])


def index(session: Session, page: Page) -> None:
    if page.deleted_at is None and page.status == "published":
        text = md.html_to_text(page.content_html)
        search.upsert(session, "page", page.id, title=page.title, summary=page.seo_description or md.summarize(text), body=text, tags=[])
    else:
        search.remove(session, "page", page.id)


def _check_slug(session: Session, slug: str, exclude_id: int | None = None) -> None:
    if not is_valid_slug(slug):
        raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
    if is_reserved_page_slug(slug):
        raise ApiError(422, "reserved", "这个别名是站点自己用的路径，换一个。", fields={"slug": "已被站点占用"})
    q = select(Page.id).where(Page.slug == slug)
    if exclude_id is not None:
        q = q.where(Page.id != exclude_id)
    if session.scalar(q):
        raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})


def _apply(session: Session, page: Page, data: dict) -> list[str]:
    changed: list[str] = []
    for name in ("title", "content_md", "status", "template", "seo_title", "seo_description"):
        if name in data and getattr(page, name) != data[name]:
            setattr(page, name, data[name])
            changed.append(name)
    if "status" in data and data["status"] not in defaults.POST_STATUSES:
        raise ApiError(422, "invalid", "取值不对。", fields={"status": "只能是 " + " / ".join(defaults.POST_STATUSES)})
    if page.template not in defaults.PAGE_TEMPLATES:
        raise ApiError(422, "invalid", "取值不对。", fields={"template": "只能是 " + " / ".join(defaults.PAGE_TEMPLATES)})
    if "seo_image_media_id" in data:
        mid = data["seo_image_media_id"]
        if mid is not None:
            media = session.get(Media, mid)
            if media is None or media.deleted_at is not None:
                raise ApiError(422, "invalid", "媒体库里没有这张图片。", fields={"seo_image_media_id": "图片不存在"})
        page.seo_image_media_id = mid
    if "published_at" in data and data["published_at"] is not None:
        page.published_at = as_utc(data["published_at"])
    if page.status in ("published", "unlisted") and page.published_at is None:
        page.published_at = utcnow()
    return changed


def create(session: Session, data: dict) -> Page:
    title = (data.get("title") or "").strip()
    if not title:
        raise ApiError(422, "invalid", "标题不能为空。", fields={"title": "必填"})
    slug = data.get("slug")
    if slug:
        _check_slug(session, slug)
    else:
        slug = unique_slug(session, Page, slugify(title), fallback="page", reserved=paths.RESERVED_PAGE_SLUGS)
    page = Page(slug=slug, title=title, content_md="", status="draft", template="plain", seo_title="", seo_description="")
    session.add(page)
    _apply(session, page, {**data, "title": title})
    session.flush()
    result = _render(session, page)
    session.flush()
    _sync_refs(session, page, result.media_ids)
    index(session, page)
    revisions.save(session, "page", page.id, snapshot(page))
    settings.bump_site_version(session)
    audit.record(session, "page.create", "page", page.id, {"title": page.title, "slug": page.slug})
    return page


def update(session: Session, page: Page, data: dict, *, expected_updated_at: datetime | None = None) -> Page:
    if expected_updated_at is not None and abs((as_utc(expected_updated_at) - as_utc(page.updated_at)).total_seconds()) >= 0.001:
        raise ApiError(409, "conflict", "这个页面在别处被改过了，请刷新后再保存。")
    if "title" in data and not (data["title"] or "").strip():
        raise ApiError(422, "invalid", "标题不能为空。", fields={"title": "不能为空"})
    if data.get("slug") and data["slug"] != page.slug:
        _check_slug(session, data["slug"], page.id)
        if page.published_at is not None:
            redirects.move(session, paths.page(page.slug), paths.page(data["slug"]))
        _retarget_nav(session, page.slug, data["slug"])
        page.slug = data["slug"]
    changed = _apply(session, page, data)
    result = _render(session, page)
    session.flush()
    _sync_refs(session, page, result.media_ids)
    index(session, page)
    page.updated_at = utcnow()
    revisions.save(session, "page", page.id, snapshot(page))
    settings.bump_site_version(session)
    audit.record(session, "page.update", "page", page.id, {"fields": changed[:10]})
    return page


def _retarget_nav(session: Session, old_slug: str, new_slug: str) -> None:
    from app.models import NavItem

    for item in session.scalars(select(NavItem).where(NavItem.kind == "page", NavItem.target == old_slug)):
        item.target = new_slug


def rerender(session: Session, page: Page) -> None:
    updated = page.updated_at
    result = _render(session, page)
    _sync_refs(session, page, result.media_ids)
    index(session, page)
    page.updated_at = updated
    session.flush()


def trash(session: Session, page: Page) -> None:
    if page.deleted_at is None:
        page.deleted_at = utcnow()
        search.remove(session, "page", page.id)
        settings.bump_site_version(session)
        audit.record(session, "page.trash", "page", page.id, {"title": page.title})


def restore(session: Session, page: Page) -> None:
    if page.deleted_at is not None:
        page.deleted_at = None
        index(session, page)
        settings.bump_site_version(session)
        audit.record(session, "page.restore", "page", page.id, {"title": page.title})


def purge(session: Session, page: Page) -> None:
    page_id, title, slug = page.id, page.title, page.slug
    refs.clear(session, "page", page_id)
    revisions.delete_all(session, "page", page_id)
    search.remove(session, "page", page_id)
    from app.models import NavItem

    for item in session.scalars(select(NavItem).where(NavItem.kind == "page", NavItem.target == slug)):
        session.delete(item)
    session.delete(page)
    session.flush()
    settings.bump_site_version(session)
    audit.record(session, "page.purge", "page", page_id, {"title": title})


def restore_revision(session: Session, page: Page, revision) -> Page:
    snap = revision.snapshot
    data = {k: snap[k] for k in ("title", "content_md", "template") if k in snap}
    updated = update(session, page, data)
    audit.record(session, "page.revision_restore", "page", page.id, {"revision": revision.id})
    return updated


def admin_list(session: Session, *, status: str | None = None, q: str = "", trashed: bool = False, page: int = 1, per: int = 50):
    stmt = select(Page).where(Page.deleted_at.is_not(None) if trashed else Page.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Page.status == status)
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Page.title.like(like), Page.slug.like(like)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.order_by(Page.updated_at.desc(), Page.id.desc()).limit(per).offset((page - 1) * per)))
    return rows, int(total)
