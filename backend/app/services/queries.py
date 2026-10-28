"""The reading side: everything the public API asks the database. All of it goes through the visibility predicates."""
from __future__ import annotations

import base64
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Category, Moment, MomentMedia, Page, Post, Series, Tag
from app.services import taxonomy
from app.services import visibility as vis
from app.timeutil import as_utc, iso, local, utcnow

POST_LOADS = (selectinload(Post.tags), selectinload(Post.category), selectinload(Post.cover), selectinload(Post.series))


# ---- posts -----------------------------------------------------------------------------------------------------------------------------
def list_posts(session: Session, *, page: int = 1, per: int = 10, category: str | None = None, tag: str | None = None, series: str | None = None,
               ids: list[int] | None = None, sort: str = "new") -> tuple[list[Post], int]:
    stmt = select(Post).where(vis.post_listed())
    if category:
        stmt = stmt.where(Post.category.has(Category.slug == category))
    if tag:
        stmt = stmt.where(Post.tags.any(Tag.slug == tag))
    if series:
        stmt = stmt.where(Post.series.has(Series.slug == series))
    if ids is not None:
        stmt = stmt.where(Post.id.in_(ids))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if series:
        order = [Post.series_order.asc(), Post.published_at.asc(), Post.id.asc()]  # a series reads in its own order
    elif sort == "old":
        order = [Post.published_at.asc(), Post.id.asc()]
    elif sort == "views":
        order = [Post.view_count.desc(), Post.published_at.desc(), Post.id.desc()]
    else:
        order = [Post.pinned.desc(), Post.published_at.desc(), Post.id.desc()]
    rows = list(session.scalars(stmt.options(*POST_LOADS).order_by(*order).limit(per).offset((page - 1) * per)))
    return rows, int(total)


def latest_posts(session: Session, limit: int) -> list[Post]:
    return list(session.scalars(select(Post).where(vis.post_listed()).options(*POST_LOADS)
                                .order_by(Post.pinned.desc(), Post.published_at.desc(), Post.id.desc()).limit(limit)))


def featured_posts(session: Session, limit: int) -> list[Post]:
    return list(session.scalars(select(Post).where(vis.post_listed(), Post.featured.is_(True)).options(*POST_LOADS)
                                .order_by(Post.published_at.desc(), Post.id.desc()).limit(limit)))


def posts_by_ids(session: Session, ids: list[int]) -> list[Post]:
    if not ids:
        return []
    rows = {p.id: p for p in session.scalars(select(Post).where(vis.post_listed(), Post.id.in_(ids)).options(*POST_LOADS))}
    return [rows[i] for i in ids if i in rows]


def post_by_slug(session: Session, slug: str, *, preview_id: int | None = None) -> Post | None:
    stmt = select(Post).where(Post.slug == slug).options(*POST_LOADS)
    post = session.scalar(stmt)
    if post is None:
        return None
    if preview_id is not None and post.id == preview_id and post.deleted_at is None:
        return post  # a valid preview link shows drafts, private and scheduled posts
    now = utcnow()
    if post.status in ("published", "unlisted") and post.published_at is not None and as_utc(post.published_at) <= now and post.deleted_at is None:
        return post
    return None


def adjacent(session: Session, post: Post) -> tuple[Post | None, Post | None]:
    """(previous = older, next = newer) among listed posts."""
    if post.published_at is None or post.status != "published":
        return None, None
    key_before = or_(Post.published_at < post.published_at, and_(Post.published_at == post.published_at, Post.id < post.id))
    key_after = or_(Post.published_at > post.published_at, and_(Post.published_at == post.published_at, Post.id > post.id))
    prev = session.scalar(select(Post).where(vis.post_listed(), key_before).options(*POST_LOADS).order_by(Post.published_at.desc(), Post.id.desc()).limit(1))
    nxt = session.scalar(select(Post).where(vis.post_listed(), key_after).options(*POST_LOADS).order_by(Post.published_at.asc(), Post.id.asc()).limit(1))
    return prev, nxt


def related(session: Session, post: Post, limit: int = 3) -> list[Post]:
    """Posts sharing the most tags with this one (then the same category, then newest)."""
    tag_ids = [t.id for t in post.tags]
    if not tag_ids and post.category_id is None:
        return []
    from app.models import post_tags

    shared = (
        select(post_tags.c.post_id, func.count().label("n")).where(post_tags.c.tag_id.in_(tag_ids)).group_by(post_tags.c.post_id).subquery()
        if tag_ids else None
    )
    stmt = select(Post).where(vis.post_listed(), Post.id != post.id).options(*POST_LOADS)
    if shared is not None:
        stmt = stmt.outerjoin(shared, shared.c.post_id == Post.id)
        same_cat = (Post.category_id == post.category_id) if post.category_id is not None else Post.id < 0
        stmt = stmt.where(or_(shared.c.n.is_not(None), same_cat))
        order = [func.coalesce(shared.c.n, 0).desc(), Post.published_at.desc()]
    else:
        stmt = stmt.where(Post.category_id == post.category_id)
        order = [Post.published_at.desc()]
    return list(session.scalars(stmt.order_by(*order).limit(limit)))


def series_nav(session: Session, post: Post) -> dict | None:
    if post.series is None:
        return None
    items = list(session.scalars(
        select(Post).where(vis.post_listed(), Post.series_id == post.series_id).order_by(Post.series_order.asc(), Post.published_at.asc(), Post.id.asc())
    ))
    if not any(i.id == post.id for i in items):  # a preview of a draft that belongs to the series
        items.append(post)
        items.sort(key=lambda p: (p.series_order or 0, as_utc(p.published_at) if p.published_at else utcnow()))
    return {
        "id": post.series.id, "slug": post.series.slug, "title": post.series.title, "status": post.series.status,
        "total": len(items), "index": next((n for n, i in enumerate(items, start=1) if i.id == post.id), 0),
        "items": [{"slug": i.slug, "title": i.title, "order": n, "current": i.id == post.id} for n, i in enumerate(items, start=1)],
    }


def archive(session: Session, tz_name: str) -> list[dict]:
    rows = list(session.scalars(select(Post).where(vis.post_listed()).options(selectinload(Post.tags), selectinload(Post.category))
                                .order_by(Post.published_at.desc(), Post.id.desc())))
    years: dict[int, dict[int, list[Post]]] = defaultdict(lambda: defaultdict(list))
    for post in rows:
        d = local(post.published_at, tz_name)
        years[d.year][d.month].append(post)
    out = []
    for year in sorted(years, reverse=True):
        months = []
        for month in sorted(years[year], reverse=True):
            months.append({"month": month, "count": len(years[year][month]), "posts": [_archive_item(p) for p in years[year][month]]})
        out.append({"year": year, "count": sum(m["count"] for m in months), "months": months})
    return out


def _archive_item(post: Post) -> dict:
    from app import paths

    return {
        "id": post.id, "slug": post.slug, "url": paths.post(post.slug), "title": post.title, "published_at": iso(post.published_at),
        "category": {"slug": post.category.slug, "name": post.category.name} if post.category else None,
        "tags": [{"slug": t.slug, "name": t.name, "color": t.color} for t in post.tags],
    }


# ---- taxonomy --------------------------------------------------------------------------------------------------------------------------
def public_taxonomy(session: Session) -> dict:
    from app.services.out import category_out, series_out, tag_out

    cat_counts = taxonomy.category_counts(session, public=True)
    tag_counts = taxonomy.tag_counts(session, public=True)
    ser_counts = taxonomy.series_counts(session, public=True)
    categories = [category_out(c, cat_counts.get(c.id, 0)) for c in session.scalars(select(Category).order_by(Category.sort_order, Category.id))]
    categories = [{**c, "show_on_shelf": True} for c in categories if c["count"] > 0]
    shelf_ids = {c.id for c in session.scalars(select(Category).where(Category.show_on_shelf.is_(True)))}
    for c in categories:
        c["show_on_shelf"] = c["id"] in shelf_ids
    tags = []
    for t in session.scalars(select(Tag).order_by(Tag.name)):
        posts_n, moments_n = tag_counts.get(t.id, (0, 0))
        if posts_n or moments_n:
            tags.append({**tag_out(t, posts_n), "moment_count": moments_n})
    series = [series_out(s, ser_counts.get(s.id, 0)) for s in session.scalars(select(Series).options(selectinload(Series.cover))
                                                                                   .order_by(Series.sort_order, Series.id))]
    series = [s for s in series if s["count"] > 0]
    total = session.scalar(select(func.count()).select_from(Post).where(vis.post_listed())) or 0
    return {"categories": categories, "tags": tags, "series": series, "total_posts": int(total)}


# ---- moments ---------------------------------------------------------------------------------------------------------------------------
MOMENT_LOADS = (selectinload(Moment.tags), selectinload(Moment.media).selectinload(MomentMedia.image))


def encode_cursor(moment: Moment) -> str:
    raw = json.dumps([iso(moment.published_at), moment.id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        stamp, moment_id = json.loads(raw)
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")), int(moment_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def moments_page(session: Session, *, cursor: str | None = None, limit: int = 10, tag: str | None = None, mood: str | None = None,
                 month_range: tuple[datetime, datetime] | None = None) -> tuple[list[Moment], str | None]:
    stmt = select(Moment).where(vis.moment_listed())
    if tag:
        stmt = stmt.where(Moment.tags.any(Tag.slug == tag))
    if mood:
        stmt = stmt.where(Moment.mood == mood)
    if month_range:
        stmt = stmt.where(Moment.published_at >= month_range[0], Moment.published_at < month_range[1])
    if cursor:
        decoded = decode_cursor(cursor)
        if decoded is not None:
            stamp, mid = decoded
            stmt = stmt.where(or_(Moment.published_at < stamp, and_(Moment.published_at == stamp, Moment.id < mid)))
    rows = list(session.scalars(stmt.options(*MOMENT_LOADS).order_by(Moment.published_at.desc(), Moment.id.desc()).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(rows[-1])
    return rows, next_cursor


def pinned_moments(session: Session) -> list[Moment]:
    return list(session.scalars(select(Moment).where(vis.moment_listed(), Moment.pinned.is_(True)).options(*MOMENT_LOADS)
                                .order_by(Moment.published_at.desc(), Moment.id.desc()).limit(5)))


def latest_moments(session: Session, limit: int) -> list[Moment]:
    return list(session.scalars(select(Moment).where(vis.moment_listed()).options(*MOMENT_LOADS)
                                .order_by(Moment.published_at.desc(), Moment.id.desc()).limit(limit)))


def moment_by_id(session: Session, moment_id: int, *, allow_unlisted: bool = True) -> Moment | None:
    cond = vis.moment_accessible() if allow_unlisted else vis.moment_listed()
    return session.scalar(select(Moment).where(Moment.id == moment_id, cond).options(*MOMENT_LOADS))


def moments_meta(session: Session, tz_name: str) -> dict:
    """What the moments page needs besides the stream: month index, mini-calendar days, tags and moods in use."""
    rows = list(session.execute(select(Moment.published_at, Moment.mood).where(vis.moment_listed())))
    months: dict[str, int] = defaultdict(int)
    days: dict[str, set[int]] = defaultdict(set)
    moods: dict[str, int] = defaultdict(int)
    for stamp, mood in rows:
        d = local(stamp, tz_name)
        key = f"{d.year:04d}-{d.month:02d}"
        months[key] += 1
        days[key].add(d.day)
        if mood:
            moods[mood] += 1
    from app import defaults
    from app.services.out import tag_out

    tag_counts = taxonomy.tag_counts(session, public=True)
    tags = []
    for t in session.scalars(select(Tag).order_by(Tag.name)):
        n = tag_counts.get(t.id, (0, 0))[1]
        if n:
            tags.append(tag_out(t, n))
    return {
        "months": [{"month": k, "count": months[k]} for k in sorted(months, reverse=True)],
        "days": {k: sorted(v) for k, v in days.items()},
        "tags": tags,
        "moods": [{"id": k, "label": defaults.MOODS.get(k, k), "count": v} for k, v in sorted(moods.items(), key=lambda kv: -kv[1])],
    }


# ---- pages -----------------------------------------------------------------------------------------------------------------------------
def page_by_slug(session: Session, slug: str, *, preview_ok: bool = False) -> Page | None:
    page = session.scalar(select(Page).where(Page.slug == slug).options(selectinload(Page.seo_image)))
    if page is None or page.deleted_at is not None:
        return None
    if page.status in ("published", "unlisted") or preview_ok:
        return page
    return None
