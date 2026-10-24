"""Where pictures are used (media_refs), kept in step with the content that uses them."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import paths
from app.models import HomeBlock, Media, MediaRef, Moment, Page, Post, Series


def sync(session: Session, entity_type: str, entity_id: int, media_ids: Iterable[int | None]) -> None:
    """Make the references of one entity exactly `media_ids`."""
    wanted = {int(m) for m in media_ids if m}
    if wanted:  # ignore ids that do not exist (deleted pictures, typos)
        wanted &= set(session.scalars(select(Media.id).where(Media.id.in_(wanted))))
    have = {r.media_id: r for r in session.scalars(select(MediaRef).where(MediaRef.entity_type == entity_type, MediaRef.entity_id == entity_id))}
    for media_id, row in have.items():
        if media_id not in wanted:
            session.delete(row)
    for media_id in wanted - set(have):
        session.add(MediaRef(media_id=media_id, entity_type=entity_type, entity_id=entity_id))
    session.flush()


def clear(session: Session, entity_type: str, entity_id: int) -> None:
    session.execute(delete(MediaRef).where(MediaRef.entity_type == entity_type, MediaRef.entity_id == entity_id))


def usage(session: Session, media_id: int) -> list[dict]:
    """Human-readable list of the places a picture is used (the "使用位置" in the media drawer)."""
    out: list[dict] = []
    for ref in session.scalars(select(MediaRef).where(MediaRef.media_id == media_id).order_by(MediaRef.entity_type, MediaRef.entity_id)):
        item = {"type": ref.entity_type, "id": ref.entity_id, "title": "", "url": "", "admin_url": ""}
        if ref.entity_type == "post" and (post := session.get(Post, ref.entity_id)):
            item.update(title=post.title, url=paths.post(post.slug), admin_url=f"/admin/posts/{post.id}", trashed=post.deleted_at is not None)
        elif ref.entity_type == "moment" and (moment := session.get(Moment, ref.entity_id)):
            item.update(title=(moment.content_md or "（只有图片的动态）")[:40], url=paths.moment(moment.id), admin_url=f"/admin/moments/{moment.id}",
                        trashed=moment.deleted_at is not None)
        elif ref.entity_type == "page" and (page := session.get(Page, ref.entity_id)):
            item.update(title=page.title, url=paths.page(page.slug), admin_url=f"/admin/pages/{page.id}", trashed=page.deleted_at is not None)
        elif ref.entity_type == "series" and (series := session.get(Series, ref.entity_id)):
            item.update(title=f"系列：{series.title}", url=paths.series(series.slug), admin_url="/admin/series")
        elif ref.entity_type == "home_block" and (block := session.get(HomeBlock, ref.entity_id)):
            item.update(title=f"首页模块：{block.type}", admin_url="/admin/home")
        elif ref.entity_type == "setting":
            item.update(title="站点设置（标志、头像、分享图等）", admin_url="/admin/appearance")
        else:
            continue
        out.append(item)
    return out


def rerender_entities(session: Session, pairs: Iterable[tuple[str, int]]) -> int:
    """Re-render posts / pages / moments (their pictures changed: replaced, alt text edited, purged). Returns how many were touched."""
    from app.services import moments, pages, posts

    count = 0
    for entity_type, entity_id in dict.fromkeys(pairs):
        if entity_type == "post" and (post := session.get(Post, entity_id)):
            posts.rerender(session, post)
            count += 1
        elif entity_type == "page" and (page := session.get(Page, entity_id)):
            pages.rerender(session, page)
            count += 1
        elif entity_type == "moment" and (moment := session.get(Moment, entity_id)):
            moments.rerender(session, moment)
            count += 1
    return count


def rerender_users(session: Session, media_id: int) -> int:
    pairs = [(r.entity_type, r.entity_id) for r in session.scalars(select(MediaRef).where(MediaRef.media_id == media_id))]
    return rerender_entities(session, pairs)
