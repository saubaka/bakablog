"""Categories, tags (shared by posts and moments) and series."""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import defaults
from app.errors import ApiError
from app.models import Category, Moment, Post, Series, Tag, moment_tags, post_tags
from app.paths import RESERVED_PAGE_SLUGS
from app.paths import category as category_path
from app.paths import series as series_path
from app.paths import tag as tag_path
from app.services import redirects, search
from app.services import visibility as vis
from app.services.slug import is_valid_slug, slugify, unique_slug

TAG_NAME_MAX = 40
MAX_TAGS_PER_ITEM = 20


# ---- tags -------------------------------------------------------------------------------------------------------------------------
def normalize_tag_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip().lstrip("#＃").strip())
    return name[:TAG_NAME_MAX]


def color_for(name: str) -> str:
    """A new tag gets one of the four colours, picked from its name so it is stable."""
    digest = hashlib.sha1(name.lower().encode("utf-8"), usedforsecurity=False).digest()
    return defaults.TAG_COLORS[digest[0] % len(defaults.TAG_COLORS)]


def get_or_create_tag(session: Session, name: str) -> Tag | None:
    name = normalize_tag_name(name)
    if not name:
        return None
    tag = session.scalar(select(Tag).where(Tag.name == name))  # NOCASE collation: "Flask" finds "flask"
    if tag is not None:
        return tag
    slug = unique_slug(session, Tag, slugify(name), fallback="tag")
    tag = Tag(name=name, slug=slug, color=color_for(name))
    session.add(tag)
    session.flush()
    return tag


def resolve_tags(session: Session, names: list[str]) -> list[Tag]:
    out: list[Tag] = []
    seen: set[int] = set()
    for name in names[:MAX_TAGS_PER_ITEM]:
        tag = get_or_create_tag(session, name)
        if tag is not None and tag.id not in seen:
            seen.add(tag.id)
            out.append(tag)
    return sorted(out, key=lambda t: t.name.casefold())  # same order the relationship loads them in


def tag_by_id(session: Session, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise ApiError(404, "not_found", "没有这个标签。")
    return tag


def update_tag(session: Session, tag: Tag, *, name: str | None = None, slug: str | None = None, color: str | None = None,
               sticker: str | None = None, description: str | None = None, clear_sticker: bool = False) -> Tag:
    if name is not None:
        name = normalize_tag_name(name)
        if not name:
            raise ApiError(422, "invalid", "标签名不能为空。", fields={"name": "不能为空"})
        other = session.scalar(select(Tag).where(Tag.name == name, Tag.id != tag.id))
        if other is not None:
            raise ApiError(409, "exists", f"已经有叫「{other.name}」的标签了，可以用“合并”。", fields={"name": "已存在"})
        tag.name = name
    if slug is not None and slug != tag.slug:
        if not is_valid_slug(slug):
            raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
        if session.scalar(select(Tag.id).where(Tag.slug == slug, Tag.id != tag.id)):
            raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
        redirects.move(session, tag_path(tag.slug), tag_path(slug))
        tag.slug = slug
    if color is not None:
        tag.color = color
    if clear_sticker:
        tag.sticker = None
    elif sticker is not None:
        tag.sticker = sticker or None
    if description is not None:
        tag.description = description
    session.flush()
    reindex_tag_users(session, [tag.id])
    return tag


def merge_tags(session: Session, source_ids: list[int], target_id: int) -> int:
    """Move everything tagged with the sources to the target, then delete the sources. Returns how many items changed tag."""
    target = tag_by_id(session, target_id)
    moved = 0
    for sid in dict.fromkeys(source_ids):
        if sid == target.id:
            continue
        source = tag_by_id(session, sid)
        for table, key in ((post_tags, "post_id"), (moment_tags, "moment_id")):
            item_ids = list(session.scalars(select(table.c[key]).where(table.c.tag_id == source.id)))
            have = set(session.scalars(select(table.c[key]).where(table.c.tag_id == target.id)))
            for item_id in item_ids:
                if item_id not in have:
                    session.execute(table.insert().values({key: item_id, "tag_id": target.id}))
                    moved += 1
            session.execute(table.delete().where(table.c.tag_id == source.id))
        redirects.move(session, tag_path(source.slug), tag_path(target.slug))
        session.delete(source)
    session.flush()
    reindex_tag_users(session, [target.id])
    return moved


def delete_tag(session: Session, tag: Tag) -> None:
    ids = _items_of_tag(session, tag.id)
    session.delete(tag)
    session.flush()
    _reindex_items(session, *ids)


def delete_unused_tags(session: Session) -> int:
    used_p = select(post_tags.c.tag_id)
    used_m = select(moment_tags.c.tag_id)
    unused = list(session.scalars(select(Tag).where(Tag.id.not_in(used_p), Tag.id.not_in(used_m))))
    for tag in unused:
        session.delete(tag)
    session.flush()
    return len(unused)


def _items_of_tag(session: Session, tag_id: int) -> tuple[list[int], list[int]]:
    return (list(session.scalars(select(post_tags.c.post_id).where(post_tags.c.tag_id == tag_id))),
            list(session.scalars(select(moment_tags.c.moment_id).where(moment_tags.c.tag_id == tag_id))))


def _reindex_items(session: Session, post_ids: list[int], moment_ids: list[int]) -> None:
    from app.services import moments, posts

    for post in session.scalars(select(Post).where(Post.id.in_(post_ids))) if post_ids else []:
        posts.index(session, post)
    for moment in session.scalars(select(Moment).where(Moment.id.in_(moment_ids))) if moment_ids else []:
        moments.index(session, moment)


def reindex_tag_users(session: Session, tag_ids: list[int]) -> None:
    posts_, moments_ = [], []
    for tid in tag_ids:
        p, m = _items_of_tag(session, tid)
        posts_ += p
        moments_ += m
    _reindex_items(session, list(set(posts_)), list(set(moments_)))


def tag_counts(session: Session, *, public: bool) -> dict[int, tuple[int, int]]:
    """tag id -> (posts, moments). With public=True only what visitors can see is counted."""
    post_q = select(post_tags.c.tag_id, func.count()).select_from(post_tags).join(Post, Post.id == post_tags.c.post_id).group_by(post_tags.c.tag_id)
    moment_q = select(moment_tags.c.tag_id, func.count()).select_from(moment_tags).join(Moment, Moment.id == moment_tags.c.moment_id).group_by(moment_tags.c.tag_id)
    post_q = post_q.where(vis.post_listed() if public else Post.deleted_at.is_(None))
    moment_q = moment_q.where(vis.moment_listed() if public else Moment.deleted_at.is_(None))
    out: dict[int, list[int]] = {}
    for tid, n in session.execute(post_q):
        out.setdefault(tid, [0, 0])[0] = n
    for tid, n in session.execute(moment_q):
        out.setdefault(tid, [0, 0])[1] = n
    return {k: (v[0], v[1]) for k, v in out.items()}


# ---- categories -----------------------------------------------------------------------------------------------------------------
def category_by_id(session: Session, category_id: int) -> Category:
    category = session.get(Category, category_id)
    if category is None:
        raise ApiError(404, "not_found", "没有这个分类。")
    return category


def create_category(session: Session, name: str, *, slug: str | None = None, description: str = "", sticker: str | None = None,
                    show_on_shelf: bool = True) -> Category:
    name = name.strip()
    if not name:
        raise ApiError(422, "invalid", "分类名不能为空。", fields={"name": "不能为空"})
    if slug:
        if not is_valid_slug(slug):
            raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
        if session.scalar(select(Category.id).where(Category.slug == slug)):
            raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
    else:
        slug = unique_slug(session, Category, slugify(name), fallback="category")
    order = (session.scalar(select(func.max(Category.sort_order))) or 0) + 1
    category = Category(name=name, slug=slug, description=description, sticker=sticker, show_on_shelf=show_on_shelf, sort_order=order)
    session.add(category)
    session.flush()
    return category


def update_category(session: Session, category: Category, *, name: str | None = None, slug: str | None = None, description: str | None = None,
                    sticker: str | None = None, clear_sticker: bool = False, show_on_shelf: bool | None = None) -> Category:
    if name is not None:
        if not name.strip():
            raise ApiError(422, "invalid", "分类名不能为空。", fields={"name": "不能为空"})
        category.name = name.strip()
    if slug is not None and slug != category.slug:
        if not is_valid_slug(slug):
            raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
        if session.scalar(select(Category.id).where(Category.slug == slug, Category.id != category.id)):
            raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
        redirects.move(session, category_path(category.slug), category_path(slug))
        category.slug = slug
    if description is not None:
        category.description = description
    if clear_sticker:
        category.sticker = None
    elif sticker is not None:
        category.sticker = sticker or None
    if show_on_shelf is not None:
        category.show_on_shelf = show_on_shelf
    session.flush()
    return category


def delete_category(session: Session, category: Category, reassign_to: int | None) -> int:
    """Posts of the category move to `reassign_to` (or become uncategorised when None). Returns how many moved."""
    n = session.scalar(select(func.count()).select_from(Post).where(Post.category_id == category.id)) or 0
    if n and reassign_to is None:
        raise ApiError(409, "has_posts", f"这个分类下有 {n} 篇文章，请选择把它们移到哪里。", extra={"post_count": n})
    if reassign_to is not None:
        if reassign_to == category.id:
            raise ApiError(422, "invalid", "不能移到它自己。", fields={"reassign_to": "不能是它自己"})
        category_by_id(session, reassign_to)
        session.execute(update(Post).where(Post.category_id == category.id).values(category_id=reassign_to))
    session.delete(category)
    session.flush()
    return int(n)


def reorder_categories(session: Session, ids: list[int]) -> None:
    for position, cid in enumerate(ids):
        session.execute(update(Category).where(Category.id == cid).values(sort_order=position))


def category_counts(session: Session, *, public: bool) -> dict[int, int]:
    q = select(Post.category_id, func.count()).where(Post.category_id.is_not(None)).group_by(Post.category_id)
    q = q.where(vis.post_listed() if public else Post.deleted_at.is_(None))
    return {cid: n for cid, n in session.execute(q)}


# ---- series ----------------------------------------------------------------------------------------------------------------------
def series_by_id(session: Session, series_id: int) -> Series:
    series = session.get(Series, series_id)
    if series is None:
        raise ApiError(404, "not_found", "没有这个系列。")
    return series


def create_series(session: Session, title: str, *, slug: str | None = None, description: str = "", status: str = "ongoing",
                  cover_media_id: int | None = None) -> Series:
    title = title.strip()
    if not title:
        raise ApiError(422, "invalid", "系列标题不能为空。", fields={"title": "不能为空"})
    if slug:
        if not is_valid_slug(slug):
            raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
        if session.scalar(select(Series.id).where(Series.slug == slug)):
            raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
    else:
        slug = unique_slug(session, Series, slugify(title), fallback="series")
    order = (session.scalar(select(func.max(Series.sort_order))) or 0) + 1
    series = Series(title=title, slug=slug, description=description, status=status, cover_media_id=cover_media_id, sort_order=order)
    session.add(series)
    session.flush()
    return series


def update_series(session: Session, series: Series, *, title: str | None = None, slug: str | None = None, description: str | None = None,
                  status: str | None = None, cover_media_id: int | None = None, clear_cover: bool = False) -> Series:
    if title is not None:
        if not title.strip():
            raise ApiError(422, "invalid", "系列标题不能为空。", fields={"title": "不能为空"})
        series.title = title.strip()
    if slug is not None and slug != series.slug:
        if not is_valid_slug(slug):
            raise ApiError(422, "invalid", "别名只能用小写字母、数字和短横线。", fields={"slug": "格式不对"})
        if session.scalar(select(Series.id).where(Series.slug == slug, Series.id != series.id)):
            raise ApiError(409, "exists", "这个别名已被占用。", fields={"slug": "已占用"})
        redirects.move(session, series_path(series.slug), series_path(slug))
        series.slug = slug
    if description is not None:
        series.description = description
    if status is not None:
        series.status = status
    if clear_cover:
        series.cover_media_id = None
    elif cover_media_id is not None:
        series.cover_media_id = cover_media_id
    session.flush()
    return series


def delete_series(session: Session, series: Series) -> int:
    n = session.scalar(select(func.count()).select_from(Post).where(Post.series_id == series.id)) or 0
    session.execute(update(Post).where(Post.series_id == series.id).values(series_id=None, series_order=None))
    session.delete(series)
    session.flush()
    return int(n)


def reorder_series_posts(session: Session, series: Series, post_ids: list[int]) -> None:
    members = set(session.scalars(select(Post.id).where(Post.series_id == series.id)))
    unknown = [pid for pid in post_ids if pid not in members]
    if unknown:
        raise ApiError(422, "invalid", "顺序里有不属于这个系列的文章。", fields={"post_ids": f"{unknown[:3]} 不在系列里"})
    for position, pid in enumerate(post_ids, start=1):
        session.execute(update(Post).where(Post.id == pid).values(series_order=position))
    rest = [pid for pid in members if pid not in post_ids]
    for offset, pid in enumerate(rest, start=len(post_ids) + 1):
        session.execute(update(Post).where(Post.id == pid).values(series_order=offset))


def series_counts(session: Session, *, public: bool) -> dict[int, int]:
    q = select(Post.series_id, func.count()).where(Post.series_id.is_not(None)).group_by(Post.series_id)
    q = q.where(vis.post_listed() if public else Post.deleted_at.is_(None))
    return {sid: n for sid, n in session.execute(q)}


_ = (RESERVED_PAGE_SLUGS, search)
