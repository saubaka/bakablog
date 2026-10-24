"""/api/admin — settings groups, home page modules, navigation, redirects."""
from __future__ import annotations

from typing import Literal

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select

from app import defaults
from app.api.guards import admin_required
from app.api.helpers import body, page_info, query
from app.db import db
from app.errors import ApiError, friendly_validation
from app.models import Media, Redirect
from app.schemas.home import BlockIn
from app.schemas.settings import MEDIA_FIELDS, MODELS
from app.services import audit, home, nav, redirects, refs, settings
from app.timeutil import iso

bp = Blueprint("admin_site", __name__, url_prefix="/api/admin")


# ---- settings -----------------------------------------------------------------------------------------------------------------------
def _vocab() -> dict:
    return {
        "themes": list(defaults.THEMES), "motion": list(defaults.MOTION_LEVELS), "code_themes": list(defaults.CODE_THEMES),
        "doodles": list(defaults.DOODLES), "icons": list(defaults.ICONS), "moods": defaults.MOODS, "tag_colors": list(defaults.TAG_COLORS),
        "nav_regions": list(defaults.NAV_REGIONS), "nav_kinds": list(defaults.NAV_KINDS), "nav_actions": list(defaults.NAV_ACTIONS),
        "routes": list(defaults.ROUTES), "home_block_types": list(defaults.HOME_BLOCK_TYPES), "mobile_nav_max": defaults.MOBILE_NAV_MAX,
        "post_statuses": list(defaults.POST_STATUSES), "card_styles": list(defaults.CARD_STYLES), "page_templates": list(defaults.PAGE_TEMPLATES),
    }


@bp.get("/settings")
@admin_required
def get_settings():
    session = db()
    return jsonify({"groups": settings.all_groups(session), "defaults": defaults.DEFAULT_SETTINGS, "vocab": _vocab(),
                    "customized": [g for g in defaults.DEFAULT_SETTINGS if settings.get_raw(session, f"cfg.{g}") is not None]})


def _setting_media_ids(session) -> list[int]:
    ids: list[int] = []
    for group, fields in MEDIA_FIELDS.items():
        values = settings.group(session, group)
        ids += [values.get(f) for f in fields]
    return [i for i in ids if i]


@bp.patch("/settings/<group>")
@admin_required
def patch_settings(group: str):
    if group not in MODELS:
        raise ApiError(404)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(400, "bad_json", "请求内容必须是 JSON 对象。")
    session = db()
    merged = settings._merge(settings.group(session, group), payload)
    try:
        clean = MODELS[group].model_validate(merged).model_dump(mode="json")
    except ValidationError as exc:
        raise ApiError(422, "invalid", "设置有问题。", fields=friendly_validation(exc)) from exc
    for field in MEDIA_FIELDS.get(group, ()):
        mid = clean.get(field)
        if mid is not None:
            media = session.get(Media, mid)
            if media is None or media.deleted_at is not None:
                raise ApiError(422, "invalid", "媒体库里没有这张图片。", fields={field: "图片不存在"})
    settings.set_group(session, group, clean)
    refs.sync(session, "setting", 0, _setting_media_ids(session))
    settings.bump_site_version(session)
    audit.record(session, "settings.update", "settings", group, {"fields": sorted(payload)})
    return jsonify({"group": group, "values": settings.group(session, group)})


@bp.post("/settings/<group>/reset")
@admin_required
def reset_settings(group: str):
    if group not in MODELS:
        raise ApiError(404)
    session = db()
    values = settings.reset_group(session, group)
    refs.sync(session, "setting", 0, _setting_media_ids(session))
    settings.bump_site_version(session)
    audit.record(session, "settings.reset", "settings", group)
    return jsonify({"group": group, "values": values})


# ---- home page modules --------------------------------------------------------------------------------------------------------------
class HomeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[BlockIn] = Field(max_length=len(defaults.HOME_BLOCK_TYPES))

    def as_dicts(self) -> list[dict]:
        return [b.model_dump() for b in self.blocks]


@bp.get("/home")
@admin_required
def get_home():
    session = db()
    return jsonify({"blocks": home.admin_blocks(session), "customized": home.customized(session), "types": list(defaults.HOME_BLOCK_TYPES)})


@bp.put("/home")
@admin_required
def put_home():
    blocks = home.replace(db(), body(HomeIn).as_dicts())
    audit.record(db(), "home.update", "home", "", {"blocks": [b["type"] for b in blocks]})
    return jsonify({"blocks": blocks, "customized": True})


@bp.post("/home/reset")
@admin_required
def reset_home():
    audit.record(db(), "home.reset", "home")
    return jsonify({"blocks": home.reset(db()), "customized": False})


@bp.post("/home/preview")
@admin_required
def preview_home():
    """The home page for a layout that has not been saved yet (the live preview next to the form)."""
    data = body(HomeIn)
    session = db()
    blocks = []
    for i, b in enumerate(data.as_dicts()):
        blocks.append({"id": None, "type": b["type"], "enabled": b["enabled"], "config": home.validate_config(b["type"], b["config"], i)})
    return jsonify({"blocks": home.resolve_public(session, blocks)})


# ---- navigation -----------------------------------------------------------------------------------------------------------------------
class NavItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=40)
    kind: Literal["route", "page", "category", "tag", "series", "link", "action"]
    target: str = Field(default="", max_length=300)
    sticker: str | None = Field(default=None, max_length=32)
    enabled: bool = True


class NavIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[NavItemIn] = Field(max_length=30)


@bp.get("/nav")
@admin_required
def get_nav():
    session = db()
    return jsonify({r: {"items": nav.admin_items(session, r), "customized": nav.customized(session, r)} for r in defaults.NAV_REGIONS} | {
        "mobile_max": defaults.MOBILE_NAV_MAX})


@bp.put("/nav/<region>")
@admin_required
def put_nav(region: str):
    items = nav.replace_region(db(), region, [i.model_dump() for i in body(NavIn).items])
    audit.record(db(), "nav.update", "nav", region, {"count": len(items)})
    return jsonify({"region": region, "items": items, "customized": True})


@bp.post("/nav/<region>/reset")
@admin_required
def reset_nav(region: str):
    items = nav.reset_region(db(), region)
    audit.record(db(), "nav.reset", "nav", region)
    return jsonify({"region": region, "items": items, "customized": False})


# ---- redirects --------------------------------------------------------------------------------------------------------------------------
class RedirectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = Field(default=None, max_length=300)
    target: str | None = Field(default=None, max_length=500)
    status_code: Literal[301, 302] | None = None


class RedirectQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")
    q: str = Field(default="", max_length=100)
    sort: Literal["new", "hits"] = "new"
    page: int = Field(default=1, ge=1, le=10000)
    per: int = Field(default=50, ge=1, le=200)


def redirect_out(r: Redirect) -> dict:
    return {"id": r.id, "source": r.source, "target": r.target, "status_code": r.status_code, "hits": r.hits, "last_hit_at": iso(r.last_hit_at),
            "auto": r.auto, "created_at": iso(r.created_at)}


@bp.get("/redirects")
@admin_required
def list_redirects():
    q = query(RedirectQuery)
    session = db()
    stmt = select(Redirect)
    if q.q:
        like = f"%{q.q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(or_(Redirect.source.like(like), Redirect.target.like(like)))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = Redirect.hits.desc() if q.sort == "hits" else Redirect.id.desc()
    rows = list(session.scalars(stmt.order_by(order).limit(q.per).offset((q.page - 1) * q.per)))
    return jsonify({"items": [redirect_out(r) for r in rows], **page_info(int(total), q.page, q.per)})


@bp.post("/redirects")
@admin_required
def create_redirect():
    data = body(RedirectIn)
    if not data.source or not data.target:
        raise ApiError(422, "invalid", "来源和目标都要填。", fields={"source": "必填" if not data.source else "", "target": "必填" if not data.target else ""})
    row = redirects.create(db(), data.source, data.target, data.status_code or 301)
    audit.record(db(), "redirect.create", "redirect", row.id, {"source": row.source, "target": row.target})
    response = jsonify(redirect_out(row))
    response.status_code = 201
    return response


@bp.patch("/redirects/<int:redirect_id>")
@admin_required
def update_redirect(redirect_id: int):
    row = db().get(Redirect, redirect_id)
    if row is None:
        raise ApiError(404)
    data = body(RedirectIn)
    redirects.update_row(db(), row, source=data.source, target=data.target, status_code=data.status_code)
    audit.record(db(), "redirect.update", "redirect", row.id, {"source": row.source})
    return jsonify(redirect_out(row))


@bp.delete("/redirects/<int:redirect_id>")
@admin_required
def delete_redirect(redirect_id: int):
    row = db().get(Redirect, redirect_id)
    if row is None:
        raise ApiError(404)
    audit.record(db(), "redirect.delete", "redirect", row.id, {"source": row.source})
    db().delete(row)
    return jsonify({"ok": True})
