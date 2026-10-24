"""Moments (动态): short posts with up to nine pictures, a mood sticker, a link card and #tags."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import defaults, paths
from app.errors import ApiError
from app.models import Media, Moment, MomentMedia
from app.services import audit, refs, search, settings, taxonomy
from app.services import markdown as md
from app.timeutil import as_utc, utcnow

MAX_MEDIA = 9
TEXT_MAX = 5000

_MASK = re.compile(r"`[^`\n]*`|https?://\S+|\[[^\]\n]*\]\([^)\n]*\)")
_TAG_CHAR = r"[^\s#＃.,;:!?，。；：！？、（）()\[\]{}<>\"'“”‘’`]"
_HASHTAG = re.compile(rf"(?<![A-Za-z0-9_&#/])[#＃]({_TAG_CHAR}{{1,30}})(?!{_TAG_CHAR})")  # a run longer than 30 characters is not a tag


def extract_hashtags(text: str) -> tuple[str, list[str]]:
    """"今天写了 #设计 #CSS" -> ("今天写了", ["设计", "CSS"]). Code spans, links and URLs are left alone."""
    masked: list[str] = []

    def hide(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00{len(masked) - 1}\x00"

    work = _MASK.sub(hide, text)
    tags: list[str] = []

    def take(m: re.Match) -> str:
        tags.append(m.group(1))
        return ""

    work = _HASHTAG.sub(take, work)
    work = re.sub(r"[ \t]{2,}", " ", work)
    work = re.sub(r"[ \t]+\n", "\n", work).strip()
    out = re.sub(r"\x00(\d+)\x00", lambda m: masked[int(m.group(1))], work)
    return out, tags


def by_id(session: Session, moment_id: int) -> Moment:
    moment = session.get(Moment, moment_id)
    if moment is None:
        raise ApiError(404, "not_found", "没有这条动态。")
    return moment


def clean_link_card(session: Session, card: dict | None) -> dict | None:
    if not card:
        return None
    url = str(card.get("url") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ApiError(422, "invalid", "链接卡片的网址不对。", fields={"link_card.url": "需要 http(s) 链接"})
    icon_id = card.get("icon_media_id")
    if icon_id is not None:
        media = session.get(Media, int(icon_id))
        if media is None:
            icon_id = None
    domain = (parts.hostname or "").lower().removeprefix("www.")
    return {
        "url": url[:500], "title": str(card.get("title") or domain)[:200], "description": str(card.get("description") or "")[:300],
        "domain": domain, "icon_media_id": icon_id,
    }


def _render(session: Session, moment: Moment) -> md.RenderResult:
    result = md.render(moment.content_md, session=session, profile="moment", site_host="")
    moment.content_html = result.html
    return result


def _sync_refs(session: Session, moment: Moment) -> None:
    ids = [m.media_id for m in moment.media]
    if moment.link_card and moment.link_card.get("icon_media_id"):
        ids.append(moment.link_card["icon_media_id"])
    refs.sync(session, "moment", moment.id, ids)


def index(session: Session, moment: Moment) -> None:
    if moment.deleted_at is None and moment.visibility == "public":
        text = md.html_to_text(moment.content_html)
        search.upsert(session, "moment", moment.id, title="", summary=text[:160], body=text, tags=[t.name for t in moment.tags])
    else:
        search.remove(session, "moment", moment.id)


def _set_media(session: Session, moment: Moment, items: list[dict]) -> None:
    if len(items) > MAX_MEDIA:
        raise ApiError(422, "too_many_images", f"一条动态最多 {MAX_MEDIA} 张图片。", fields={"media": f"最多 {MAX_MEDIA} 张"})
    seen: set[int] = set()
    rows: list[MomentMedia] = []
    for position, item in enumerate(items):
        mid = int(item["media_id"])
        if mid in seen:
            continue
        seen.add(mid)
        media = session.get(Media, mid)
        if media is None or media.deleted_at is not None:
            raise ApiError(422, "invalid", "媒体库里没有这张图片。", fields={f"media.{position}": "图片不存在"})
        rows.append(MomentMedia(position=len(rows), media_id=mid, alt=str(item.get("alt") or "")[:300]))
    moment.media = rows


def _apply(session: Session, moment: Moment, data: dict) -> list[str]:
    changed: list[str] = []
    if "text" in data:
        text = (data["text"] or "")[:TEXT_MAX]
        tags = list(data.get("tags") or [])
        if data.get("auto_tags", True):
            text, found = extract_hashtags(text)
            tags += found
            data = {**data, "tags": tags}
        if text != moment.content_md:
            moment.content_md = text
            changed.append("text")
    if "mood" in data:
        mood = data["mood"]
        if mood is not None and mood not in defaults.MOODS:
            raise ApiError(422, "invalid", "没有这种心情。", fields={"mood": "只能是 " + " / ".join(defaults.MOODS)})
        moment.mood = mood
        changed.append("mood")
    if "visibility" in data:
        if data["visibility"] not in defaults.MOMENT_VISIBILITIES:
            raise ApiError(422, "invalid", "取值不对。", fields={"visibility": "只能是 " + " / ".join(defaults.MOMENT_VISIBILITIES)})
        moment.visibility = data["visibility"]
        changed.append("visibility")
    if "pinned" in data:
        moment.pinned = bool(data["pinned"])
        changed.append("pinned")
    if "published_at" in data and data["published_at"] is not None:
        moment.published_at = as_utc(data["published_at"])
        changed.append("published_at")
    if "link_card" in data:
        moment.link_card = clean_link_card(session, data["link_card"])
        changed.append("link_card")
    if "media" in data:
        _set_media(session, moment, data["media"] or [])
        changed.append("media")
    if "tags" in data:
        moment.tags = taxonomy.resolve_tags(session, data["tags"] or [])
        changed.append("tags")
    return changed


def _require_content(moment: Moment) -> None:
    if not (moment.content_md or moment.media or moment.link_card):
        raise ApiError(422, "empty", "写点什么，或者放一张图片、一个链接。", fields={"text": "内容不能为空"})


def create(session: Session, data: dict) -> Moment:
    moment = Moment(published_at=utcnow(), content_md="", visibility="public", pinned=False, view_count=0)
    session.add(moment)
    session.flush()
    _apply(session, moment, {"auto_tags": True, **data})
    _require_content(moment)
    _render(session, moment)
    session.flush()
    _sync_refs(session, moment)
    index(session, moment)
    settings.bump_site_version(session)
    audit.record(session, "moment.create", "moment", moment.id, {"visibility": moment.visibility})
    return moment


def update(session: Session, moment: Moment, data: dict) -> Moment:
    changed = _apply(session, moment, {"auto_tags": True, **data})
    _require_content(moment)
    _render(session, moment)
    moment.updated_at = utcnow()
    session.flush()
    _sync_refs(session, moment)
    index(session, moment)
    settings.bump_site_version(session)
    audit.record(session, "moment.update", "moment", moment.id, {"fields": changed})
    return moment


def rerender(session: Session, moment: Moment) -> None:
    updated = moment.updated_at
    _render(session, moment)
    _sync_refs(session, moment)
    index(session, moment)
    moment.updated_at = updated
    session.flush()


def trash(session: Session, moment: Moment) -> None:
    if moment.deleted_at is None:
        moment.deleted_at = utcnow()
        search.remove(session, "moment", moment.id)
        settings.bump_site_version(session)
        audit.record(session, "moment.trash", "moment", moment.id)


def restore(session: Session, moment: Moment) -> None:
    if moment.deleted_at is not None:
        moment.deleted_at = None
        index(session, moment)
        settings.bump_site_version(session)
        audit.record(session, "moment.restore", "moment", moment.id)


def purge(session: Session, moment: Moment) -> None:
    moment_id = moment.id
    refs.clear(session, "moment", moment_id)
    search.remove(session, "moment", moment_id)
    session.delete(moment)
    session.flush()
    settings.bump_site_version(session)
    audit.record(session, "moment.purge", "moment", moment_id)


def duplicate(session: Session, moment: Moment) -> Moment:
    return create(session, {
        "text": moment.content_md, "auto_tags": False, "mood": moment.mood, "tags": [t.name for t in moment.tags],
        "media": [{"media_id": m.media_id, "alt": m.alt} for m in moment.media], "link_card": moment.link_card, "visibility": "private",
    })


def admin_list(session: Session, *, visibility: str | None = None, tag: str | None = None, mood: str | None = None,
               month_range: tuple[datetime, datetime] | None = None, q: str = "", trashed: bool = False, page: int = 1, per: int = 20):
    stmt = select(Moment)
    stmt = stmt.where(Moment.deleted_at.is_not(None) if trashed else Moment.deleted_at.is_(None))
    if visibility:
        stmt = stmt.where(Moment.visibility == visibility)
    if mood:
        stmt = stmt.where(Moment.mood == mood)
    if tag:
        from app.models import Tag

        stmt = stmt.where(Moment.tags.any(Tag.slug == tag))
    if month_range:
        stmt = stmt.where(Moment.published_at >= month_range[0], Moment.published_at < month_range[1])
    if q:
        stmt = stmt.where(Moment.content_md.like(f"%{q.replace('%', '').replace('_', '')}%"))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(
        stmt.options(selectinload(Moment.tags), selectinload(Moment.media).selectinload(MomentMedia.image))
        .order_by(Moment.pinned.desc(), Moment.published_at.desc(), Moment.id.desc()).limit(per).offset((page - 1) * per)
    ))
    return rows, int(total)


def moment_url(moment: Moment) -> str:
    return paths.moment(moment.id)


_ = Any
