"""The home page: an ordered list of blocks (hero, latest posts, latest moments ...). No rows at all = the default layout."""
from __future__ import annotations

import copy

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import defaults
from app.errors import ApiError, friendly_validation
from app.models import HomeBlock
from app.schemas.home import CONFIG_MODELS, parse_time
from app.services import queries, refs, settings
from app.services.out import moment_out, post_card
from app.timeutil import iso, utcnow


def customized(session: Session) -> bool:
    return session.scalar(select(HomeBlock.id).where(HomeBlock.type.notin_(defaults.RETIRED_HOME_BLOCKS)).limit(1)) is not None


def _current(block_type: str, config: dict) -> dict:
    """A stored config as it is understood today: what was retired (the photo card and the typed title of the hero, a doodle that left the vocabulary,
    the RSS button) is dropped instead of failing the next save or showing a dead link. (Whole modules that were retired are left out by `admin_blocks`.)"""
    if block_type != "hero":
        return config
    out = {k: v for k, v in config.items() if k not in ("polaroid", "title_lines")}
    if isinstance(out.get("doodles"), list):
        out["doodles"] = [d for d in out["doodles"] if d in defaults.DOODLES]
    if isinstance(out.get("buttons"), list):
        out["buttons"] = [b for b in out["buttons"] if not str(b.get("url", "")).startswith("/feed/")]
    return out


def admin_blocks(session: Session) -> list[dict]:
    rows = list(session.scalars(select(HomeBlock).where(HomeBlock.type.notin_(defaults.RETIRED_HOME_BLOCKS)).order_by(HomeBlock.sort_order, HomeBlock.id)))
    if not rows:
        return [{"id": None, "type": b["type"], "enabled": b["enabled"], "config": copy.deepcopy(b["config"])} for b in defaults.DEFAULT_HOME_BLOCKS]
    return [{"id": r.id, "type": r.type, "enabled": r.enabled, "config": _current(r.type, r.config)} for r in rows]


def validate_config(block_type: str, config: dict, index: int) -> dict:
    model = CONFIG_MODELS[block_type]
    try:
        return model.model_validate(config).model_dump(mode="json")
    except ValidationError as exc:
        fields = {f"blocks.{index}.config.{k}": v for k, v in friendly_validation(exc).items()}
        raise ApiError(422, "invalid", f"「{block_type}」模块的设置有问题。", fields=fields) from exc


def replace(session: Session, blocks: list[dict]) -> list[dict]:
    types = [b["type"] for b in blocks]
    if len(set(types)) != len(types):
        raise ApiError(422, "duplicate", "每种模块只能出现一次。", fields={"blocks": "有重复的模块"})
    clean = []
    for i, block in enumerate(blocks):
        config = validate_config(block["type"], block.get("config") or {}, i)
        clean.append({"type": block["type"], "enabled": bool(block.get("enabled", True)), "config": config})
    for old in session.scalars(select(HomeBlock)):
        refs.clear(session, "home_block", old.id)
    session.execute(delete(HomeBlock))
    for position, block in enumerate(clean):
        session.add(HomeBlock(type=block["type"], enabled=block["enabled"], config=block["config"], sort_order=position))
    session.flush()
    settings.bump_site_version(session)
    return admin_blocks(session)


def reset(session: Session) -> list[dict]:
    for old in session.scalars(select(HomeBlock)):
        refs.clear(session, "home_block", old.id)
    session.execute(delete(HomeBlock))
    session.flush()
    settings.bump_site_version(session)
    return admin_blocks(session)


def _active_notice(config: dict) -> bool:
    if not (config.get("text") or "").strip():
        return False
    now = utcnow()
    start, end = parse_time(config.get("starts_at")), parse_time(config.get("ends_at"))
    return (start is None or start <= now) and (end is None or now <= end)


def resolve_public(session: Session, blocks: list[dict] | None = None) -> list[dict]:
    """The home page as visitors get it: enabled blocks in order, each with the data it needs, in one response."""
    blocks = blocks if blocks is not None else admin_blocks(session)
    out = []
    for block in blocks:
        if not block["enabled"]:
            continue
        kind, config = block["type"], copy.deepcopy(block["config"])
        data: dict = {}
        if kind == "notice":
            if not _active_notice(config):
                continue
        elif kind == "featured":
            if config.get("mode") == "manual":
                posts = queries.posts_by_ids(session, config.get("post_ids", []))
            else:
                posts = queries.featured_posts(session, config.get("count", 3))
            if not posts:
                continue
            data["posts"] = [post_card(p) for p in posts]
        elif kind == "latest_posts":
            data["posts"] = [post_card(p) for p in queries.latest_posts(session, config.get("count", 6))]
        elif kind == "latest_moments":
            data["moments"] = [moment_out(m) for m in queries.latest_moments(session, config.get("count", 3))]
        out.append({"type": kind, "id": block.get("id"), "config": config, "data": data})
    return out


_ = iso
