"""Posts: create / edit / publish / trash, with rendering, tags, series, search index, picture references and history in one place.

Every write goes through create() / update() so that nothing can forget a step: Markdown is rendered once at save time (content_html is
what visitors get), the search index, the picture references, the version history, the redirect for a changed address and the site
version are all kept in step.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import defaults, paths
from app.config import cfg
from app.errors import ApiError
from app.models import Category, Media, Post, Series
from app.services import audit, redirects, refs, revisions, search, settings, taxonomy
from app.services import markdown as md
from app.services.slug import is_valid_slug, slugify, unique_slug
from app.timeutil import as_utc, iso_precise, utcnow

SCALARS = ("title", "content_md", "status", "pinned", "featured", "card_style", "show_toc", "show_reading_time", "show_author_card",
           "seo_title", "seo_description", "canonical_url", "cover_alt", "cover_focus_x", "cover_focus_y")


def site_host() -> str:
    return (urlsplit(cfg().site_url).hostname or "").lower()


def by_id(session: Session, post_id: int, *, include_trashed: bool = True) -> Post:
    post = session.get(Post, post_id)
    if post is None or (post.deleted_at is not None and not include_trashed):
        raise ApiError(404, "not_found", "没有这篇文章。")
    return post


# ---- snapshots and rendering --------------------------------------------------------------------------------------------------------
def snapshot(post: Post) -> dict[str, Any]:
    return {
        "title": post.title, "slug": post.slug, "summary": post.summary, "summary_auto": post.summary_auto, "content_md": post.content_md,
        "status": post.status, "category_id": post.category_id, "tags": [t.name for t in post.tags], "series_id": post.series_id,
        "series_order": post.series_order, "cover_media_id": post.cover_media_id,
    }


def _render(session: Session, post: Post) -> md.RenderResult:
    result = md.render(post.content_md, session=session, profile="post", site_host=site_host())
    post.content_html = result.html
    post.toc = result.toc
    post.word_count = result.word_count
    post.reading_minutes = result.reading_minutes
    if post.summary_auto:
        post.summary = result.summary
    return result


def _sync_refs(session: Session, post: Post, media_ids: list[int]) -> None:
    refs.sync(session, "post", post.id, [*media_ids, post.cover_media_id, post.seo_image_media_id])


def rerender(session: Session, post: Post) -> None:
    """Pictures changed somewhere: build the HTML again (no history entry, no change of the update time)."""
    updated = post.updated_at
    result = _render(session, post)
    _sync_refs(session, post, result.media_ids)
    index(session, post)
    post.updated_at = updated
    session.flush()


def index(session: Session, post: Post) -> None:
    if post.deleted_at is None and post.status == "published":
        search.upsert(session, "post", post.id, title=post.title, summary=post.summary, body=md.html_to_text(post.content_html),
                      tags=[t.name for t in post.tags])
    else:
        search.remove(session, "post", post.id)


# ---- validation helpers -------------------------------------------------------------------------------------------------------------
def _media_ok(session: Session, media_id: int | None, field: str) -> None:
    if media_id is None:
        return
    media = session.get(Media, media_id)
    if media is None or media.deleted_at is not None:
        raise ApiError(422, "invalid", "媒体库里没有这张图片。", fields={field: "图片不存在"})


def _check_enum(value: str, allowed: tuple[str, ...], field: str) -> None:
    if value not in allowed:
        raise ApiError(422, "invalid", "取值不对。", fields={field: "只能是 " + " / ".join(allowed)})


def _apply_relations(session: Session, post: Post, data: dict) -> None:
    if "category_id" in data:
        cid = data["category_id"]
        if cid is not None:
            taxonomy.category_by_id(session, cid)
        post.category_id = cid
    if "cover_media_id" in data:
        _media_ok(session, data["cover_media_id"], "cover_media_id")
        post.cover_media_id = data["cover_media_id"]
    if "seo_image_media_id" in data:
        _media_ok(session, data["seo_image_media_id"], "seo_image_media_id")
        post.seo_image_media_id = data["seo_image_media_id"]
    if "series_id" in data or "series_order" in data:
        sid = data.get("series_id", post.series_id)
        if sid is None:
            post.series_id, post.series_order = None, None
        else:
            taxonomy.series_by_id(session, sid)
            moved = sid != post.series_id
            post.series_id = sid
            order = data.get("series_order")
            if order is not None:
                post.series_order = order
            elif moved or post.series_order is None:
                post.series_order = (session.scalar(select(func.max(Post.series_order)).where(Post.series_id == sid, Post.id != post.id)) or 0) + 1
    if "tags" in data:
        post.tags = taxonomy.resolve_tags(session, data["tags"] or [])


def _apply_slug(session: Session, post: Post, slug: str | None, title: str) -> None:
    if post.id is None or post.slug is None:  # new post
        if slug:
            if not is_valid_slug(slug):
                raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
            if session.scalar(select(Post.id).where(Post.slug == slug)):
                raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
            post.slug = slug
        else:
            post.slug = unique_slug(session, Post, slugify(title), fallback=f"post-{utcnow():%Y%m%d%H%M%S}")
        return
    if slug is None or slug == post.slug:
        return
    if not is_valid_slug(slug):
        raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
    if session.scalar(select(Post.id).where(Post.slug == slug, Post.id != post.id)):
        raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
    if post.published_at is not None or post.status != "draft":  # it has had a public address: keep old links alive
        redirects.move(session, paths.post(post.slug), paths.post(slug))
    post.slug = slug


def _apply_status_and_date(post: Post, data: dict) -> None:
    if "status" in data:
        _check_enum(data["status"], defaults.POST_STATUSES, "status")
    if "published_at" in data:
        value = data["published_at"]
        post.published_at = as_utc(value) if value is not None else None
    if post.status in ("published", "unlisted") and post.published_at is None:
        post.published_at = utcnow()


# ---- create / update ---------------------------------------------------------------------------------------------------------------
def _same_instant(a: datetime, b: datetime) -> bool:
    return abs((as_utc(a) - as_utc(b)).total_seconds()) < 0.001


def create(session: Session, data: dict) -> Post:
    title = (data.get("title") or "").strip()
    if not title:
        raise ApiError(422, "invalid", "标题不能为空。", fields={"title": "必填"})
    post = Post(
        title=title, content_md=data.get("content_md", ""), status=data.get("status", "draft"), card_style="auto", summary_auto=True, pinned=False,
        featured=False, show_toc=True, show_reading_time=True, show_author_card=False, cover_focus_x=50.0, cover_focus_y=50.0, view_count=0,
        seo_title="", seo_description="", canonical_url="", cover_alt="",
    )
    for name in SCALARS:
        if name in data and name not in ("title",):
            setattr(post, name, data[name])
    post.title = title
    _check_enum(post.status, defaults.POST_STATUSES, "status")
    _check_enum(post.card_style, defaults.CARD_STYLES, "card_style")
    _apply_slug(session, post, data.get("slug"), title)
    summary = (data.get("summary") or "").strip()
    post.summary_auto = not summary
    post.summary = summary
    _apply_status_and_date(post, data)
    session.add(post)
    session.flush()
    _apply_relations(session, post, data)
    result = _render(session, post)
    session.flush()
    _sync_refs(session, post, result.media_ids)
    index(session, post)
    revisions.save(session, "post", post.id, snapshot(post))
    settings.bump_site_version(session)
    audit.record(session, "post.create", "post", post.id, {"title": post.title, "status": post.status})
    return post


def update(session: Session, post: Post, data: dict, *, expected_updated_at: datetime | None = None) -> Post:
    if expected_updated_at is not None and not _same_instant(expected_updated_at, post.updated_at):
        raise ApiError(409, "conflict", "这篇文章在别处被改过了，请刷新后再保存。", extra={"updated_at": iso_precise(post.updated_at)})
    before_status = post.status
    changed: list[str] = []
    for name in SCALARS:
        if name in data and getattr(post, name) != data[name]:
            if name == "title" and not (data[name] or "").strip():
                raise ApiError(422, "invalid", "标题不能为空。", fields={"title": "不能为空"})
            setattr(post, name, data[name].strip() if name == "title" else data[name])
            changed.append(name)
    _check_enum(post.status, defaults.POST_STATUSES, "status")
    _check_enum(post.card_style, defaults.CARD_STYLES, "card_style")
    if "slug" in data and data["slug"] and data["slug"] != post.slug:
        _apply_slug(session, post, data["slug"], post.title)
        changed.append("slug")
    if "summary" in data:
        summary = (data["summary"] or "").strip()
        post.summary_auto = not summary
        post.summary = summary
        changed.append("summary")
    _apply_status_and_date(post, data)
    session.flush()
    _apply_relations(session, post, data)
    result = _render(session, post)
    session.flush()
    _sync_refs(session, post, result.media_ids)
    index(session, post)
    post.updated_at = utcnow()
    revisions.save(session, "post", post.id, snapshot(post))
    revisions.clear_autosave(session, "post", post.id)
    settings.bump_site_version(session)
    action = "post.publish" if before_status != "published" and post.status == "published" else "post.update"
    audit.record(session, action, "post", post.id, {"title": post.title, "fields": changed[:12]})
    session.flush()
    return post


def autosave(session: Session, post: Post, data: dict) -> None:
    """The editor's pause-to-save: keeps the typed text aside without touching the post (a published post stays as published)."""
    snap = {k: data[k] for k in ("title", "summary", "content_md", "tags") if k in data}
    revisions.put_autosave(session, "post", post.id, snap)


# ---- trash / duplicate / history -----------------------------------------------------------------------------------------------------
def trash(session: Session, post: Post) -> None:
    if post.deleted_at is None:
        post.deleted_at = utcnow()
        search.remove(session, "post", post.id)
        settings.bump_site_version(session)
        audit.record(session, "post.trash", "post", post.id, {"title": post.title})


def restore(session: Session, post: Post) -> None:
    if post.deleted_at is not None:
        post.deleted_at = None
        index(session, post)
        settings.bump_site_version(session)
        audit.record(session, "post.restore", "post", post.id, {"title": post.title})


def purge(session: Session, post: Post) -> None:
    post_id, title = post.id, post.title
    refs.clear(session, "post", post_id)
    revisions.delete_all(session, "post", post_id)
    search.remove(session, "post", post_id)
    session.delete(post)
    session.flush()
    settings.bump_site_version(session)
    audit.record(session, "post.purge", "post", post_id, {"title": title})


def duplicate(session: Session, post: Post) -> Post:
    data = {
        "title": f"{post.title}（副本）", "content_md": post.content_md, "summary": "" if post.summary_auto else post.summary,
        "status": "draft", "category_id": post.category_id, "tags": [t.name for t in post.tags], "cover_media_id": post.cover_media_id,
        "cover_alt": post.cover_alt, "card_style": post.card_style, "show_toc": post.show_toc, "show_reading_time": post.show_reading_time,
        "show_author_card": post.show_author_card, "seo_title": post.seo_title, "seo_description": post.seo_description,
        "cover_focus_x": post.cover_focus_x, "cover_focus_y": post.cover_focus_y,
    }
    return create(session, data)


def restore_revision(session: Session, post: Post, revision: Any) -> Post:
    snap = revision.snapshot
    data = {k: snap[k] for k in ("title", "content_md", "tags", "category_id") if k in snap}
    data["summary"] = "" if snap.get("summary_auto", True) else snap.get("summary", "")
    updated = update(session, post, data)
    audit.record(session, "post.revision_restore", "post", post.id, {"revision": revision.id})
    return updated


# ---- preview links ---------------------------------------------------------------------------------------------------------------------
def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(cfg().secret_key, salt="bb-preview")


def preview_token(post: Post) -> str:
    return _signer().dumps({"p": post.id})


def verify_preview_token(token: str, max_age: int = 7 * 86400) -> int | None:
    try:
        data = _signer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return int(data["p"]) if isinstance(data, dict) and "p" in data else None


# ---- admin list -------------------------------------------------------------------------------------------------------------------------
def admin_list(session: Session, *, status: str | None = None, category_id: int | None = None, tag: str | None = None, series_id: int | None = None,
               q: str = "", date_from: datetime | None = None, date_to: datetime | None = None, sort: str = "updated", page: int = 1, per: int = 20):
    """status: draft | published | scheduled | unlisted | private | trashed | all(None). Returns (rows, total)."""
    now = utcnow()
    stmt = select(Post)
    if status == "trashed":
        stmt = stmt.where(Post.deleted_at.is_not(None))
    else:
        stmt = stmt.where(Post.deleted_at.is_(None))
        if status == "scheduled":
            stmt = stmt.where(Post.status == "published", Post.published_at > now)
        elif status == "published":
            stmt = stmt.where(Post.status == "published", Post.published_at <= now)
        elif status in ("draft", "unlisted", "private"):
            stmt = stmt.where(Post.status == status)
    if category_id is not None:
        stmt = stmt.where(Post.category_id == category_id)
    if series_id is not None:
        stmt = stmt.where(Post.series_id == series_id)
    if tag:
        from app.models import Tag

        stmt = stmt.where(Post.tags.any(Tag.slug == tag))
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Post.title.like(like), Post.summary.like(like), Post.slug.like(like), Post.content_md.like(like)))
    if date_from is not None:
        stmt = stmt.where(Post.published_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Post.published_at < date_to)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {
        "updated": Post.updated_at.desc(), "published": Post.published_at.desc(), "created": Post.created_at.desc(),
        "title": func.lower(Post.title), "views": Post.view_count.desc(),
    }.get(sort, Post.updated_at.desc())
    rows = list(session.scalars(
        stmt.options(selectinload(Post.tags), selectinload(Post.category), selectinload(Post.cover), selectinload(Post.series))
        .order_by(order, Post.id.desc()).limit(per).offset((page - 1) * per)
    ))
    return rows, int(total)


def is_scheduled(post: Post, now: datetime | None = None) -> bool:
    return post.status == "published" and post.published_at is not None and as_utc(post.published_at) > (now or utcnow())


_ = (Category, Series)
