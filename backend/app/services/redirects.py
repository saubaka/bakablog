"""301 / 302 redirects. A slug change registers one automatically, so old links keep working."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Redirect
from app.timeutil import utcnow

_PROTECTED = ("/api/", "/admin", "/media/")
MAX_HOPS = 5


def normalize_source(path: str) -> str:
    """A site path: starts with "/", no query or fragment, no trailing slash (except the root)."""
    path = (path or "").strip()
    if not path.startswith("/") or path.startswith("//"):
        raise ApiError(422, "invalid", "来源必须是站内路径，以 / 开头。", fields={"source": "以 / 开头的站内路径"})
    path = urlsplit(path).path
    if len(path) > 1:
        path = path.rstrip("/")
    if len(path) > 300 or re.search(r"[\x00-\x1f\s]", path):
        raise ApiError(422, "invalid", "来源路径不合规。", fields={"source": "不能包含空白字符，最长 300 个字符"})
    return path or "/"


def normalize_target(target: str) -> str:
    target = (target or "").strip()
    if target.startswith("/") and not target.startswith("//"):
        return target
    parts = urlsplit(target)
    if parts.scheme in ("http", "https") and parts.netloc:
        return target
    raise ApiError(422, "invalid", "目标必须是站内路径或 http(s) 链接。", fields={"target": "站内路径或 http(s) 链接"})


def _check(source: str, target: str) -> None:
    if source == target:
        raise ApiError(422, "invalid", "来源和目标不能相同。", fields={"target": "不能和来源相同"})
    if source == "/" or source.startswith(_PROTECTED):
        raise ApiError(422, "invalid", "这个路径不能设置重定向。", fields={"source": "不能是首页、/api、/admin 或 /media 下的路径"})


def create(session: Session, source: str, target: str, status_code: int = 301, *, auto: bool = False) -> Redirect:
    source, target = normalize_source(source), normalize_target(target)
    _check(source, target)
    existing = session.scalar(select(Redirect).where(Redirect.source == source))
    if existing is not None:
        raise ApiError(409, "exists", "这个来源已经有重定向了。", fields={"source": "已存在"})
    _ensure_no_loop(session, source, target)
    row = Redirect(source=source, target=target, status_code=status_code, auto=auto)
    session.add(row)
    session.flush()
    return row


def update_row(session: Session, row: Redirect, *, source: str | None = None, target: str | None = None, status_code: int | None = None) -> Redirect:
    new_source = normalize_source(source) if source is not None else row.source
    new_target = normalize_target(target) if target is not None else row.target
    _check(new_source, new_target)
    if new_source != row.source and session.scalar(select(Redirect.id).where(Redirect.source == new_source)):
        raise ApiError(409, "exists", "这个来源已经有重定向了。", fields={"source": "已存在"})
    _ensure_no_loop(session, new_source, new_target, ignore_id=row.id)
    row.source, row.target = new_source, new_target
    if status_code is not None:
        row.status_code = status_code
    row.auto = False
    session.flush()
    return row


def _ensure_no_loop(session: Session, source: str, target: str, ignore_id: int | None = None) -> None:
    seen = {source}
    current = target
    for _ in range(MAX_HOPS * 4):
        if not current.startswith("/"):
            return
        if current in seen:
            raise ApiError(422, "loop", "这条重定向会形成循环。", fields={"target": "会形成循环"})
        seen.add(current)
        stmt = select(Redirect).where(Redirect.source == current)
        if ignore_id is not None:
            stmt = stmt.where(Redirect.id != ignore_id)
        nxt = session.scalar(stmt)
        if nxt is None:
            return
        current = nxt.target


def move(session: Session, old_path: str, new_path: str) -> None:
    """Content moved from old_path to new_path (slug changed): redirect it, keep older redirects pointing at the final place."""
    if old_path == new_path:
        return
    # a redirect that sits where the content now lives would hide it
    session.query(Redirect).filter(Redirect.source == new_path).delete()
    session.execute(update(Redirect).where(Redirect.target == old_path).values(target=new_path))
    existing = session.scalar(select(Redirect).where(Redirect.source == old_path))
    if existing is None:
        session.add(Redirect(source=old_path, target=new_path, status_code=301, auto=True))
    else:
        existing.target, existing.status_code, existing.auto = new_path, 301, True
    session.flush()


def resolve(session: Session, path: str) -> tuple[str, int, int] | None:
    """(final target, status code, id of the first redirect hit) for a request path, following chains; None if there is no redirect."""
    path = normalize_source(path) if path else "/"
    first = session.scalar(select(Redirect).where(Redirect.source == path))
    if first is None:
        return None
    row, hops, seen = first, 0, {path}
    while hops < MAX_HOPS:
        target = row.target
        if not target.startswith("/") or target in seen:
            return target, first.status_code, first.id
        nxt = session.scalar(select(Redirect).where(Redirect.source == target))
        if nxt is None:
            return target, first.status_code, first.id
        seen.add(target)
        row, hops = nxt, hops + 1
    return row.target, first.status_code, first.id


def record_hit(session: Session, redirect_id: int) -> None:
    session.execute(update(Redirect).where(Redirect.id == redirect_id).values(hits=Redirect.hits + 1, last_hit_at=utcnow()))
