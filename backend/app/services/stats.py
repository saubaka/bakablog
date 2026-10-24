"""Anonymous visit statistics. No cookies, no addresses stored.

A visit is counted from a beacon the page sends. "Unique" is estimated from sha256(daily random salt + address prefix + browser);
the salt and those hashes are deleted when the day ends. Do Not Track / Global Privacy Control, bots and the admin switch are respected.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import DeviceStat, Moment, Page, PageView, Post, Referrer, Visitor
from app.security import device_class, looks_like_bot
from app.services import settings
from app.services import visibility as vis
from app.timeutil import local, utcnow

SALT_KEY = "stats.salt"
MAX_REFERRER = 120


def today(tz_name: str | None) -> date:
    return local(utcnow(), tz_name).date()


def _salt(session: Session, day: date) -> str:
    stored = settings.get_raw(session, SALT_KEY)
    if isinstance(stored, dict) and stored.get("day") == day.isoformat():
        return stored["salt"]
    salt = secrets.token_hex(16)
    settings.set_raw(session, SALT_KEY, {"day": day.isoformat(), "salt": salt})  # yesterday's salt is gone: yesterday's hashes cannot be matched again
    return salt


def classify_path(session: Session, path: str) -> tuple[str, int] | None:
    """Which page does this address belong to? ("post", id) | ("moment", id) | ("page", id) | ("home", 0) | ("list", 0) | None."""
    path = "/" + path.strip().split("?", 1)[0].split("#", 1)[0].strip("/")
    if path == "/":
        return "home", 0
    parts = path.strip("/").split("/")
    if parts[0] == "blog" and len(parts) == 2:
        post = session.scalar(select(Post.id).where(Post.slug == parts[1], vis.post_accessible()))
        return ("post", post) if post else None
    if parts[0] == "moments" and len(parts) == 2 and parts[1].isdigit():
        moment = session.scalar(select(Moment.id).where(Moment.id == int(parts[1]), vis.moment_accessible()))
        return ("moment", moment) if moment else None
    if parts[0] in ("blog", "moments", "archive", "search", "category", "tag", "series") and len(parts) <= 2:
        return "list", 0
    if len(parts) == 1:
        page = session.scalar(select(Page.id).where(Page.slug == parts[0], vis.page_accessible()))
        return ("page", page) if page else None
    return None


def _bump(session: Session, day: date, kind: str, ref_id: int, *, views: int, uniques: int) -> None:
    stmt = sqlite_insert(PageView).values(day=day, kind=kind, ref_id=ref_id, views=views, uniques=uniques)
    stmt = stmt.on_conflict_do_update(
        index_elements=["day", "kind", "ref_id"],
        set_={"views": PageView.views + views, "uniques": PageView.uniques + uniques},
    )
    session.execute(stmt)


def _first_today(session: Session, day: date, visitor: str, page_key: str) -> bool:
    stmt = sqlite_insert(Visitor).values(day=day, hash=visitor, page_key=page_key).on_conflict_do_nothing()
    return (session.execute(stmt).rowcount or 0) > 0


def record(session: Session, *, path: str, referrer: str | None, user_agent: str | None, ip_prefix: str, tz_name: str | None, site_host: str) -> bool:
    """Count one visit. Returns False when nothing was recorded."""
    if not settings.group(session, "stats")["enabled"] or looks_like_bot(user_agent):
        return False
    target = classify_path(session, path)
    if target is None:
        return False
    kind, ref_id = target
    day = today(tz_name)
    visitor = hashlib.sha256(f"{_salt(session, day)}|{ip_prefix}|{user_agent or ''}".encode()).hexdigest()[:16]
    new_site = _first_today(session, day, visitor, "*")
    _bump(session, day, "site", 0, views=1, uniques=1 if new_site else 0)
    new_page = _first_today(session, day, visitor, f"{kind}:{ref_id}")
    _bump(session, day, kind, ref_id, views=1, uniques=1 if new_page else 0)
    if kind == "post":
        session.execute(update(Post).where(Post.id == ref_id).values(view_count=Post.view_count + 1))
    elif kind == "moment":
        session.execute(update(Moment).where(Moment.id == ref_id).values(view_count=Moment.view_count + 1))
    if new_site:
        device = device_class(user_agent)
        session.execute(sqlite_insert(DeviceStat).values(day=day, device=device, count=1).on_conflict_do_update(
            index_elements=["day", "device"], set_={"count": DeviceStat.count + 1}))
        domain = referrer_domain(referrer, site_host)
        if domain:
            session.execute(sqlite_insert(Referrer).values(day=day, domain=domain, count=1).on_conflict_do_update(
                index_elements=["day", "domain"], set_={"count": Referrer.count + 1}))
    return True


def referrer_domain(referrer: str | None, site_host: str) -> str:
    if not referrer:
        return ""
    host = (urlsplit(referrer).hostname or "").lower().removeprefix("www.")
    if not host or host == site_host.lower().removeprefix("www.") or host in ("localhost", "127.0.0.1"):
        return ""
    return host[:MAX_REFERRER]


def prune(session: Session, tz_name: str | None) -> dict[str, int]:
    """Visitor hashes older than today go away; very old daily counters are summarised away after two years."""
    day = today(tz_name)
    v = session.execute(delete(Visitor).where(Visitor.day < day))
    old = day - timedelta(days=730)
    p = session.execute(delete(PageView).where(PageView.day < old))
    r = session.execute(delete(Referrer).where(Referrer.day < old))
    d = session.execute(delete(DeviceStat).where(DeviceStat.day < old))
    return {"visitors": int(v.rowcount or 0), "page_views": int(p.rowcount or 0), "referrers": int(r.rowcount or 0), "devices": int(d.rowcount or 0)}


def summary(session: Session, days: int, tz_name: str | None) -> dict:
    end = today(tz_name)
    start = end - timedelta(days=days - 1)
    site = {row.day: row for row in session.scalars(select(PageView).where(PageView.kind == "site", PageView.day >= start))}
    series = []
    for offset in range(days):
        d = start + timedelta(days=offset)
        row = site.get(d)
        series.append({"day": d.isoformat(), "views": row.views if row else 0, "uniques": row.uniques if row else 0})
    top = session.execute(
        select(PageView.ref_id, func.sum(PageView.views).label("v"), func.sum(PageView.uniques).label("u"))
        .where(PageView.kind == "post", PageView.day >= start).group_by(PageView.ref_id).order_by(func.sum(PageView.views).desc()).limit(10)
    ).all()
    titles = {p.id: p for p in session.scalars(select(Post).where(Post.id.in_([r.ref_id for r in top] or [0])))}
    from app import paths

    top_posts = [{"id": r.ref_id, "title": titles[r.ref_id].title, "url": paths.post(titles[r.ref_id].slug), "views": int(r.v), "uniques": int(r.u)}
                 for r in top if r.ref_id in titles]
    referrers = [{"domain": r.domain, "count": int(r.n)} for r in session.execute(
        select(Referrer.domain, func.sum(Referrer.count).label("n")).where(Referrer.day >= start).group_by(Referrer.domain)
        .order_by(func.sum(Referrer.count).desc()).limit(10))]
    devices = {r.device: int(r.n) for r in session.execute(
        select(DeviceStat.device, func.sum(DeviceStat.count).label("n")).where(DeviceStat.day >= start).group_by(DeviceStat.device))}
    return {
        "days": days, "series": series, "total_views": sum(s["views"] for s in series), "total_uniques": sum(s["uniques"] for s in series),
        "top_posts": top_posts, "referrers": referrers, "devices": devices,
    }
