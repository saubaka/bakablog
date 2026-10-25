"""Navigation (top bar, phone bottom bar, footer). A region without rows shows its default; saving a region stores its rows."""
from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import defaults, paths
from app.errors import ApiError
from app.models import Category, NavItem, Page, Series, Tag
from app.services import settings
from app.services import visibility as vis
from app.services.posts import site_host


def region_rows(session: Session, region: str) -> list[NavItem]:
    return list(session.scalars(select(NavItem).where(NavItem.region == region).order_by(NavItem.sort_order, NavItem.id)))


def customized(session: Session, region: str) -> bool:
    return session.scalar(select(NavItem.id).where(NavItem.region == region).limit(1)) is not None


def _default_items(region: str) -> list[dict]:
    return [{"id": None, "region": region, "label": label, "kind": kind, "target": target, "sticker": sticker, "enabled": True}
            for label, kind, target, sticker in defaults.DEFAULT_NAV[region]]


def admin_items(session: Session, region: str) -> list[dict]:
    rows = region_rows(session, region)
    if not rows:
        return _default_items(region)
    return [{"id": r.id, "region": r.region, "label": r.label, "kind": r.kind, "target": r.target, "sticker": r.sticker if r.sticker in defaults.ICONS else None, "enabled": r.enabled}
            for r in rows if not r.target.startswith("/feed/")]   # the RSS entries are gone: no dead link, and the retired icon would fail the next save


def validate_item(session: Session, item: dict, *, check_targets: bool = True, index: int | None = None) -> dict:
    def key(name: str) -> str:
        return f"items.{index}.{name}" if index is not None else name

    kind, target = item["kind"], (item.get("target") or "").strip()
    label = (item.get("label") or "").strip()
    if not label:
        raise ApiError(422, "invalid", "名称不能为空。", fields={key("label"): "必填"})
    if item.get("sticker") and item["sticker"] not in defaults.ICONS:
        raise ApiError(422, "invalid", "没有这个贴纸图标。", fields={key("sticker"): "没有这个图标"})
    if kind == "route":
        if target not in defaults.ROUTES:
            raise ApiError(422, "invalid", "不是站点自带的页面。", fields={key("target"): "只能是 " + " ".join(defaults.ROUTES)})
    elif kind == "action":
        if target not in defaults.NAV_ACTIONS:
            raise ApiError(422, "invalid", "不认识这个动作。", fields={key("target"): "只能是 " + " / ".join(defaults.NAV_ACTIONS)})
    elif kind in ("page", "category", "tag", "series"):
        model = {"page": Page, "category": Category, "tag": Tag, "series": Series}[kind]
        if check_targets and session.scalar(select(model.id).where(model.slug == target)) is None:
            raise ApiError(422, "invalid", "目标不存在。", fields={key("target"): f"没有别名为 {target} 的{ {'page': '页面', 'category': '分类', 'tag': '标签', 'series': '系列'}[kind] }"})
    elif kind == "link":
        parts = urlsplit(target)
        ok = (target.startswith("/") and not target.startswith("//")) or (parts.scheme in ("http", "https") and parts.netloc) or \
            target.startswith(("mailto:", "tel:"))
        if not ok:
            raise ApiError(422, "invalid", "链接不对。", fields={key("target"): "需要 http(s) 链接、站内路径或 mailto:"})
    else:
        raise ApiError(422, "invalid", "不认识这种类型。", fields={key("kind"): "不对"})
    return {"label": label[:40], "kind": kind, "target": target[:300], "sticker": item.get("sticker") or None, "enabled": bool(item.get("enabled", True))}


def replace_region(session: Session, region: str, items: list[dict], *, check_targets: bool = True) -> list[dict]:
    if region not in defaults.NAV_REGIONS:
        raise ApiError(404)
    clean = [validate_item(session, i, check_targets=check_targets, index=n) for n, i in enumerate(items)]
    if region == "mobile" and len(clean) > defaults.MOBILE_NAV_MAX:
        raise ApiError(422, "too_many", f"手机底栏最多 {defaults.MOBILE_NAV_MAX} 格。", fields={"items": f"最多 {defaults.MOBILE_NAV_MAX} 项，现在有 {len(clean)} 项"})
    session.execute(delete(NavItem).where(NavItem.region == region))
    for position, item in enumerate(clean):
        session.add(NavItem(region=region, sort_order=position, **item))
    session.flush()
    settings.bump_site_version(session)
    return admin_items(session, region)


def reset_region(session: Session, region: str) -> list[dict]:
    if region not in defaults.NAV_REGIONS:
        raise ApiError(404)
    session.execute(delete(NavItem).where(NavItem.region == region))
    session.flush()
    settings.bump_site_version(session)
    return admin_items(session, region)


def resolve(session: Session, region: str) -> list[dict]:
    """What visitors get: urls resolved, entries whose target is gone or not public left out."""
    out = []
    host = site_host()
    for item in admin_items(session, region):
        if not item["enabled"]:
            continue
        kind, target = item["kind"], item["target"]
        url, action, external = None, None, False
        if kind == "route":
            url = target
        elif kind == "action":
            action = target
        elif kind == "page":
            page = session.scalar(select(Page).where(Page.slug == target, vis.page_accessible()))
            if page is None:
                continue
            url = paths.page(page.slug)
        elif kind == "category":
            if session.scalar(select(Category.id).where(Category.slug == target)) is None:
                continue
            url = paths.category(target)
        elif kind == "tag":
            if session.scalar(select(Tag.id).where(Tag.slug == target)) is None:
                continue
            url = paths.tag(target)
        elif kind == "series":
            if session.scalar(select(Series.id).where(Series.slug == target)) is None:
                continue
            url = paths.series(target)
        elif kind == "link":
            url = target
            external = target.startswith(("http://", "https://")) and (urlsplit(target).hostname or "").lower() != host
        out.append({"id": item["id"], "label": item["label"], "kind": kind, "url": url, "action": action, "sticker": item["sticker"], "external": external})
    return out


# ---- pages in the navigation ("show in nav / footer" switches of the page editor) ---------------------------------------------------
def page_flags(session: Session, slug: str) -> dict[str, bool]:
    def has(region: str) -> bool:
        return any(i["kind"] == "page" and i["target"] == slug and i["enabled"] for i in admin_items(session, region))

    return {"in_nav": has("top"), "in_footer": has("footer")}


def set_page_flags(session: Session, page: Page, *, in_nav: bool | None = None, in_footer: bool | None = None) -> None:
    for region, wanted in (("top", in_nav), ("footer", in_footer)):
        if wanted is None:
            continue
        items = admin_items(session, region)
        present = [i for i in items if i["kind"] == "page" and i["target"] == page.slug]
        if wanted and not any(i["enabled"] for i in present):
            if present:
                for i in present:
                    i["enabled"] = True
            else:
                items.append({"label": page.title[:40], "kind": "page", "target": page.slug, "sticker": None, "enabled": True})
        elif not wanted and present:
            items = [i for i in items if not (i["kind"] == "page" and i["target"] == page.slug)]
        else:
            continue
        replace_region(session, region, items, check_targets=False)  # defaults may point at pages that do not exist yet; visitors never see those
