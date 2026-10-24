"""Turning rows into the JSON the API sends. One function per shape, shared by the public and the admin API."""
from __future__ import annotations

from sqlalchemy.orm import object_session

from app import paths
from app.models import Category, Media, Series, Tag
from app.timeutil import iso, iso_precise


def _variant(media: Media, want: int = 960) -> dict | None:
    variants = sorted(media.variants or [], key=lambda v: v["size"])
    if not variants:
        return None
    return next((v for v in variants if v["size"] >= want), variants[-1])


def media_out(media: Media | None, *, admin: bool = False, usage_count: int | None = None) -> dict | None:
    if media is None:
        return None
    variants = sorted(media.variants or [], key=lambda v: v["size"])
    main = _variant(media)
    out = {
        "id": media.id,
        "alt": media.alt,
        "caption": media.caption,
        "width": main["w"] if main else media.width,
        "height": main["h"] if main else media.height,
        "color": media.color,
        "animated": media.animated,
        "src": paths.media(media.hash, main["size"] if main else 960),
        "srcset": ", ".join(f"{paths.media(media.hash, v['size'])} {v['w']}w" for v in variants),
        "full": paths.media(media.hash, variants[-1]["size"]) if variants else paths.media(media.hash, 960),
        "variants": [{"size": v["size"], "w": v["w"], "h": v["h"], "url": paths.media(media.hash, v["size"])} for v in variants],
    }
    if admin:
        out.update(
            hash=media.hash, filename=media.filename, kind=media.kind, mime=media.mime, bytes=media.bytes, orig_width=media.width,
            orig_height=media.height, created_at=iso(media.created_at), updated_at=iso(media.updated_at), deleted_at=iso(media.deleted_at),
            usage_count=usage_count,
        )
    return out


def tag_out(tag: Tag, count: int | None = None) -> dict:
    out = {"id": tag.id, "slug": tag.slug, "name": tag.name, "color": tag.color, "sticker": tag.sticker, "url": paths.tag(tag.slug)}
    if count is not None:
        out["count"] = count
    return out


def category_out(category: Category | None, count: int | None = None, *, admin: bool = False) -> dict | None:
    if category is None:
        return None
    out = {"id": category.id, "slug": category.slug, "name": category.name, "description": category.description, "sticker": category.sticker,
           "url": paths.category(category.slug)}
    if count is not None:
        out["count"] = count
    if admin:
        out.update(sort_order=category.sort_order, show_on_shelf=category.show_on_shelf)
    return out


def series_out(series: Series | None, count: int | None = None, *, admin: bool = False) -> dict | None:
    if series is None:
        return None
    out = {"id": series.id, "slug": series.slug, "title": series.title, "description": series.description, "status": series.status,
           "cover": media_out(series.cover), "url": paths.series(series.slug)}
    if count is not None:
        out["count"] = count
    if admin:
        out.update(sort_order=series.sort_order)
    return out


# ---- posts ----------------------------------------------------------------------------------------------------------------------------
def _mood_out(mood: str | None) -> dict | None:
    from app import defaults

    if not mood:
        return None
    return {"id": mood, "label": defaults.MOODS.get(mood, mood)}


def post_card(post, *, admin: bool = False) -> dict:
    """The compact shape used by lists, cards, feeds and search results."""
    out = {
        "id": post.id,
        "slug": post.slug,
        "url": paths.post(post.slug),
        "title": post.title,
        "summary": post.summary,
        "cover": media_out(post.cover),
        "cover_alt": post.cover_alt,
        "cover_focus": {"x": post.cover_focus_x, "y": post.cover_focus_y},
        "category": category_out(post.category),
        "tags": [tag_out(t) for t in post.tags],
        "series": ({"id": post.series.id, "slug": post.series.slug, "title": post.series.title, "order": post.series_order}
                   if post.series is not None else None),
        "pinned": post.pinned,
        "featured": post.featured,
        "card_style": post.card_style,
        "published_at": iso(post.published_at),
        "updated_at": iso(post.updated_at),
        "reading_minutes": post.reading_minutes,
        "word_count": post.word_count,
    }
    if admin:
        out.update(status=post.status, view_count=post.view_count, created_at=iso(post.created_at), deleted_at=iso(post.deleted_at),
                   updated_at=iso_precise(post.updated_at))
    return out


def post_mini(post) -> dict:
    """Previous / next / related entries."""
    return {"id": post.id, "slug": post.slug, "url": paths.post(post.slug), "title": post.title, "summary": post.summary,
            "cover": media_out(post.cover), "published_at": iso(post.published_at), "category": category_out(post.category),
            "reading_minutes": post.reading_minutes}


def moment_out(moment, *, admin: bool = False) -> dict:
    from app.services import markdown as md

    media = []
    for item in moment.media:
        m = media_out(item.image)
        if m is not None:
            if item.alt:
                m = {**m, "alt": item.alt}
            media.append(m)
    card = None
    if moment.link_card:
        card = {k: moment.link_card.get(k, "") for k in ("url", "title", "description", "domain")}
        icon_id = moment.link_card.get("icon_media_id")
        session = object_session(moment)
        card["icon"] = media_out(session.get(Media, icon_id)) if icon_id and session is not None else None
    out = {
        "id": moment.id,
        "url": paths.moment(moment.id),
        "html": moment.content_html,
        "text": md.html_to_text(moment.content_html),
        "mood": _mood_out(moment.mood),
        "tags": [tag_out(t) for t in moment.tags],
        "media": media,
        "link_card": card,
        "pinned": moment.pinned,
        "published_at": iso(moment.published_at),
    }
    if admin:
        out.update(visibility=moment.visibility, markdown=moment.content_md, updated_at=iso(moment.updated_at), deleted_at=iso(moment.deleted_at),
                   view_count=moment.view_count, created_at=iso(moment.created_at))
    return out
