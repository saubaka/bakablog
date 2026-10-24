"""The read-only public API (/api/site, /api/home, /api/posts, ...). Visitors can read; nothing here accepts content from them,
the only write is the anonymous visit beacon."""
from __future__ import annotations

import json
from typing import Literal

from flask import Blueprint, Response, request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import paths
from app.api.helpers import etag_json, page_info, query
from app.config import cfg
from app.db import db
from app.errors import ApiError
from app.models import Category, Page, Post, Series, Tag
from app.security import client_prefix
from app.services import home, queries, redirects, search, settings, site, stats, taxonomy
from app.services import posts as posts_service
from app.services import visibility as vis
from app.services.out import category_out, media_out, moment_out, post_card, post_mini, series_out, tag_out
from app.timeutil import as_utc, iso, month_bounds, utcnow

bp = Blueprint("public", __name__, url_prefix="/api")


# ---- helpers --------------------------------------------------------------------------------------------------------------------
def _seo(session, *, title: str, description: str, image, path: str, canonical: str = "", noindex: bool = False) -> dict:
    return {"title": title, "description": (description or "")[:300], "image": image, "canonical": canonical or site.absolute(path), "noindex": noindex}


def _share_image(session):
    return site.payload(session)["seo"]["share_image"]


# ---- site and home ---------------------------------------------------------------------------------------------------------------
@bp.get("/site")
def get_site():
    return etag_json(site.payload(db()))


@bp.get("/home")
def get_home():
    session = db()
    return etag_json({"blocks": home.resolve_public(session), "site_version": settings.site_version(session)})


# ---- posts -----------------------------------------------------------------------------------------------------------------------
class PostsQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=10, ge=1, le=30)
    category: str | None = Field(default=None, max_length=80)
    tag: str | None = Field(default=None, max_length=80)
    series: str | None = Field(default=None, max_length=80)
    q: str | None = Field(default=None, max_length=100)
    sort: Literal["new", "old", "views"] = "new"

    @field_validator("category", "tag", "series", "q", mode="before")
    @classmethod
    def _blank(cls, v):
        return v or None


def posts_list_payload(session, q: PostsQuery) -> dict:
    """The body of GET /api/posts (also the first-screen data the SEO shell inlines)."""
    filters: dict = {"category": None, "tag": None, "series": None, "q": q.q}
    if q.category:
        c = session.scalar(select(Category).where(Category.slug == q.category))
        if c is None:
            raise ApiError(404, "not_found", "没有这个分类。")
        filters["category"] = category_out(c)
    if q.tag:
        t = session.scalar(select(Tag).where(Tag.slug == q.tag))
        if t is None:
            raise ApiError(404, "not_found", "没有这个标签。")
        filters["tag"] = tag_out(t)
    if q.series:
        s = session.scalar(select(Series).where(Series.slug == q.series))
        if s is None:
            raise ApiError(404, "not_found", "没有这个系列。")
        filters["series"] = series_out(s)
    if q.q:
        hits = search.search(session, q.q, kinds=("post",), limit=200)
        ranked = [h.ref_id for h in hits]
        rows, _ = queries.list_posts(session, page=1, per=200, category=q.category, tag=q.tag, series=q.series, ids=ranked)
        by_id = {p.id: p for p in rows}
        snippets = {h.ref_id: h.snippet for h in hits}
        ordered = [by_id[i] for i in ranked if i in by_id]
        total = len(ordered)
        window = ordered[(q.page - 1) * q.per: q.page * q.per]
        items = [{**post_card(p), "snippet": snippets.get(p.id, "")} for p in window]
    else:
        rows, total = queries.list_posts(session, page=q.page, per=q.per, category=q.category, tag=q.tag, series=q.series, sort=q.sort)
        items = [post_card(p) for p in rows]
    return {"items": items, **page_info(total, q.page, q.per), "filters": filters}


@bp.get("/posts")
def list_posts():
    return etag_json(posts_list_payload(db(), query(PostsQuery)))


def _post_detail(session, post: Post, *, preview: bool) -> dict:
    prev, nxt = queries.adjacent(session, post)
    detail = {
        **post_card(post),
        "html": post.content_html,
        "toc": post.toc,
        "options": {"show_toc": post.show_toc, "show_reading_time": post.show_reading_time, "show_author_card": post.show_author_card},
        "prev": post_mini(prev) if prev else None,
        "next": post_mini(nxt) if nxt else None,
        "related": [post_mini(p) for p in queries.related(session, post)],
        "series_nav": queries.series_nav(session, post),
        "status": post.status if preview else "published",
        "preview": preview,
    }
    image = media_out(post.seo_image) or media_out(post.cover) or _share_image(session)
    detail["seo"] = _seo(
        session, title=post.seo_title or post.title, description=post.seo_description or post.summary, image=image, path=paths.post(post.slug),
        canonical=post.canonical_url, noindex=preview or post.status != "published",
    )
    return detail


@bp.get("/posts/<slug>")
def get_post(slug: str):
    session = db()
    preview_id = None
    token = request.args.get("preview")
    if token:
        preview_id = posts_service.verify_preview_token(token)
    post = queries.post_by_slug(session, slug, preview_id=preview_id)
    if post is None:
        moved = redirects.resolve(session, paths.post(slug))
        if moved is not None and moved[0].startswith("/"):
            raise ApiError(404, "moved", "这篇文章换了地址。", extra={"location": moved[0]})
        raise ApiError(404, "not_found", "没有这篇文章。")
    is_preview = preview_id is not None and (post.status != "published" or (post.published_at and as_utc(post.published_at) > utcnow()))
    data = _post_detail(session, post, preview=is_preview)
    if is_preview:
        response = etag_json(data, cache="no-store")
        response.headers["X-Robots-Tag"] = "noindex"
        return response
    return etag_json(data)


# ---- archive and taxonomy ----------------------------------------------------------------------------------------------------------
@bp.get("/archive")
def get_archive():
    session = db()
    years = queries.archive(session, site.tz_name(session))
    return etag_json({"years": years, "total": sum(y["count"] for y in years)})


@bp.get("/taxonomy")
def get_taxonomy():
    return etag_json(queries.public_taxonomy(db()))


# ---- moments ---------------------------------------------------------------------------------------------------------------------
class MomentsQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=10, ge=1, le=30)
    tag: str | None = Field(default=None, max_length=80)
    mood: str | None = Field(default=None, max_length=16)
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @field_validator("cursor", "tag", "mood", "month", mode="before")
    @classmethod
    def _blank(cls, v):
        return v or None


@bp.get("/moments")
def list_moments():
    q = query(MomentsQuery)
    session = db()
    tz = site.tz_name(session)
    month_range = month_bounds(q.month, tz) if q.month else None
    rows, next_cursor = queries.moments_page(session, cursor=q.cursor, limit=q.limit, tag=q.tag, mood=q.mood, month_range=month_range)
    body: dict = {"items": [moment_out(m) for m in rows], "next_cursor": next_cursor}
    if not q.cursor:
        body["pinned"] = [moment_out(m) for m in queries.pinned_moments(session)]
        body["meta"] = queries.moments_meta(session, tz)
    return etag_json(body)


@bp.get("/moments/<int:moment_id>")
def get_moment(moment_id: int):
    session = db()
    moment = queries.moment_by_id(session, moment_id)
    if moment is None:
        raise ApiError(404, "not_found", "没有这条动态。")
    data = moment_out(moment)
    text = data["text"] or ("（图片）" if data["media"] else data["link_card"]["title"] if data["link_card"] else "")
    first_image = data["media"][0] if data["media"] else None
    data["seo"] = _seo(session, title=f"{text[:40]} · 动态", description=text[:160], image=first_image or _share_image(session), path=paths.moment(moment.id),
                       noindex=moment.visibility != "public")
    return etag_json(data)


# ---- pages -----------------------------------------------------------------------------------------------------------------------
@bp.get("/pages/<slug>")
def get_page(slug: str):
    session = db()
    page = queries.page_by_slug(session, slug)
    if page is None:
        moved = redirects.resolve(session, paths.page(slug))
        if moved is not None and moved[0].startswith("/"):
            raise ApiError(404, "moved", "这个页面换了地址。", extra={"location": moved[0]})
        raise ApiError(404, "not_found", "没有这个页面。")
    image = media_out(page.seo_image) or _share_image(session)
    return etag_json({
        "id": page.id, "slug": page.slug, "url": paths.page(page.slug), "title": page.title, "html": page.content_html, "toc": page.toc,
        "template": page.template, "updated_at": iso(page.updated_at),
        "seo": _seo(session, title=page.seo_title or page.title, description=page.seo_description or "", image=image, path=paths.page(page.slug),
                    noindex=page.status != "published"),
    })


# ---- search ----------------------------------------------------------------------------------------------------------------------
class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    q: str = Field(default="", max_length=100)
    type: Literal["all", "post", "moment", "page"] = "all"


@bp.get("/search")
def do_search():
    q = query(SearchQuery)
    session = db()
    kinds = ("post", "moment", "page") if q.type == "all" else (q.type,)
    hits = search.search(session, q.q, kinds=kinds)
    groups: dict[str, list] = {"posts": [], "moments": [], "pages": []}
    by_kind: dict[str, list] = {"post": [], "moment": [], "page": []}
    for h in hits:
        by_kind[h.kind].append(h)
    if by_kind["post"]:
        rows = {p.id: p for p in session.scalars(select(Post).where(Post.id.in_([h.ref_id for h in by_kind["post"]]), vis.post_listed())
                                                  .options(*queries.POST_LOADS))}
        groups["posts"] = [{**post_card(rows[h.ref_id]), "snippet": h.snippet} for h in by_kind["post"] if h.ref_id in rows]
    if by_kind["moment"]:
        from app.models import Moment

        rows_m = {m.id: m for m in session.scalars(select(Moment).where(Moment.id.in_([h.ref_id for h in by_kind["moment"]]), vis.moment_listed())
                                                    .options(*queries.MOMENT_LOADS))}
        groups["moments"] = [{**moment_out(rows_m[h.ref_id]), "snippet": h.snippet} for h in by_kind["moment"] if h.ref_id in rows_m]
    if by_kind["page"]:
        rows_p = {p.id: p for p in session.scalars(select(Page).where(Page.id.in_([h.ref_id for h in by_kind["page"]]), vis.page_listed()))}
        groups["pages"] = [{"id": p.id, "slug": p.slug, "url": paths.page(p.slug), "title": p.title, "snippet": h.snippet}
                           for h in by_kind["page"] if (p := rows_p.get(h.ref_id))]
    total = sum(len(v) for v in groups.values())
    return etag_json({"q": q.q, "type": q.type, "total": total, "groups": groups}, cache="no-cache")


# ---- the visit beacon --------------------------------------------------------------------------------------------------------------
@bp.post("/track")
def track():
    """navigator.sendBeacon from the page: {"p": "/blog/slug", "r": "https://referrer/"}. Always answers 204."""
    done = Response(status=204, headers={"Cache-Control": "no-store"})
    if request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1":
        return done
    raw = request.get_data(cache=False)
    if not raw or len(raw) > 512:
        return done
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
        path, referrer = str(data.get("p", ""))[:300], str(data.get("r", ""))[:300]
    except (ValueError, AttributeError):
        return done
    session = db()
    try:
        stats.record(session, path=path, referrer=referrer or None, user_agent=request.headers.get("User-Agent"), ip_prefix=client_prefix(),
                     tz_name=site.tz_name(session), site_host=_host())
    except OperationalError:  # busy database: a lost visit is better than a slow page
        session.rollback()
    return done


def _host() -> str:
    from urllib.parse import urlsplit

    return (urlsplit(cfg().site_url).hostname or request.host.split(":")[0]).lower()


_ = (taxonomy,)
