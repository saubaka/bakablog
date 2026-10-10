"""Site pages, navigation, footer and administration-layout settings."""

from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from flask import url_for

from app.extensions import db
from app.models import CustomPage
from app.services.blog import render_markdown
from app.services.content import get_setting, safe_content_url, set_setting

MANAGED_PAGES_SETTING = "managed_pages_config"
PRIMARY_MENU_SETTING = "primary_menu_config"
FOOTER_CONTENT_SETTING = "footer_content_config"
ADMIN_NAVIGATION_SETTING = "admin_navigation_layout"

SYSTEM_PAGES: tuple[dict[str, Any], ...] = (
    {
        "key": "home",
        "label": "首页",
        "endpoint": "public.home",
        "title": "在代码、设计和日常之间",
        "subtitle": "这里放着我正在做的项目、读过的东西，还有偶尔写下的几句。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "blog",
        "label": "博客",
        "endpoint": "public.blog",
        "title": "博客手记",
        "subtitle": "从最近写下的内容里，挑一页慢慢读。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "projects",
        "label": "项目",
        "endpoint": "public.projects",
        "title": "项目作品",
        "subtitle": "把正在想的东西做成可以使用的小工具。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "moments",
        "label": "动态",
        "endpoint": "public.moments",
        "title": "生活动态",
        "subtitle": "几句近况、一个念头，或者今天遇到的好天气。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "links",
        "label": "友链",
        "endpoint": "public.links",
        "title": "常去的站点",
        "subtitle": "几处值得收藏、偶尔会再打开的地方。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "gallery",
        "label": "相册",
        "endpoint": "public.gallery",
        "title": "照片",
        "subtitle": "把窗边、街角和路上遇到的画面留在这里。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "guestbook",
        "label": "留言",
        "endpoint": "public.guestbook",
        "title": "留言簿",
        "subtitle": "如果刚好有话想说，可以留在这里。",
        "enabled": True,
        "nav": True,
    },
    {
        "key": "about",
        "label": "关于",
        "endpoint": "public.about",
        "title": "关于我和这个站点",
        "subtitle": "白天写代码，晚上做一点设计，也整理自己的长期项目。",
        "enabled": True,
        "nav": True,
    },
)

PRIMARY_MENU_DEFAULTS: tuple[dict[str, Any], ...] = tuple(
    {
        "id": f"system-{page['key']}",
        "label": page["label"],
        "target_type": "system",
        "target": page["key"],
        "url": "",
        "visible": True,
        "open_new_tab": False,
        "roles": [],
        "sort_order": index * 10,
    }
    for index, page in enumerate(SYSTEM_PAGES, 1)
)

FOOTER_DEFAULTS = {
    "description": "记录代码、设计与生活",
    "copyright": "使用 Flask 与本地资源搭建",
    "columns": [
        {
            "id": "explore",
            "title": "继续看看",
            "links": [
                {"label": "文章归档", "url": "/blog/archive/"},
                {"label": "Atom订阅", "url": "/feed.xml"},
            ],
        },
    ],
}

ADMIN_NAVIGATION_DEFAULTS = {
    "parents": [
        "dashboard",
        "articles",
        "taxonomy",
        "moments",
        "comments",
        "media",
        "albums",
        "pages",
        "menu",
        "site",
        "projects",
        "appearance",
        "system",
    ],
    "children": {
        "dashboard": [],
        "articles": [
            "article-all",
            "article-published",
            "article-drafts",
            "article-trash",
            "article-create",
        ],
        "taxonomy": ["category-list", "category-create", "tag-list", "tag-create"],
        "moments": ["moment-all", "moment-published", "moment-drafts", "moment-create"],
        "comments": [],
        "media": ["media-library"],
        "albums": ["album-list", "album-create"],
        "pages": ["front-pages", "home-management"],
        "menu": ["primary-menu", "admin-menu-editor"],
        "site": [
            "site-identity",
            "site-seo",
            "site-footer",
            "site-external-links",
            "site-addresses",
            "site-security",
        ],
        "projects": ["projects"],
        "appearance": ["font", "hints", "transitions", "dialogs", "components"],
        "system": ["status", "audit", "about"],
    },
}


def _json_setting(key: str, default: Any, raw: str | None = None) -> Any:
    if raw is None:
        raw = get_setting(key, "")
    if not raw:
        return deepcopy(default)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return deepcopy(default)
    return value


def _save_json(key: str, value: Any) -> None:
    set_setting(key, json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def load_managed_pages(raw: str | None = None) -> list[dict[str, Any]]:
    supplied = _json_setting(MANAGED_PAGES_SETTING, [], raw)
    by_key = (
        {
            str(item.get("key")): item
            for item in supplied
            if isinstance(item, dict) and item.get("key")
        }
        if isinstance(supplied, list)
        else {}
    )
    result = []
    for default in SYSTEM_PAGES:
        stored = by_key.get(default["key"], {})
        blocks = []
        for index, block in enumerate(stored.get("blocks", [])):
            if not isinstance(block, dict):
                continue
            blocks.append(
                {
                    "id": str(block.get("id") or f"block-{index + 1}")[:80],
                    "title": str(block.get("title", ""))[:160],
                    "content": str(block.get("content", ""))[:100_000],
                    "style": str(block.get("style", "card"))
                    if str(block.get("style", "card")) in {"card", "note", "wide", "quote"}
                    else "card",
                    "enabled": bool(block.get("enabled", True)),
                    "sort_order": int(block.get("sort_order", index * 10)),
                }
            )
        result.append(
            {
                **default,
                "title": str(stored.get("title", default["title"]))[:180] or default["title"],
                "subtitle": str(stored.get("subtitle", default["subtitle"]))[:500],
                "label": str(stored.get("label", default["label"]))[:80] or default["label"],
                "enabled": bool(stored.get("enabled", default["enabled"])),
                "nav": bool(stored.get("nav", default["nav"])),
                "customized": bool(stored),
                "blocks": sorted(blocks, key=lambda item: item["sort_order"]),
            }
        )
    return result


def save_managed_pages(pages: list[dict[str, Any]]) -> None:
    allowed = {item["key"] for item in SYSTEM_PAGES}
    compact = []
    for page in pages:
        if page.get("key") not in allowed:
            continue
        compact.append(
            {
                key: page[key]
                for key in ("key", "label", "title", "subtitle", "enabled", "nav", "blocks")
            }
        )
    _save_json(MANAGED_PAGES_SETTING, compact)


def managed_page(key: str) -> dict[str, Any] | None:
    return next((item for item in load_managed_pages() if item["key"] == key), None)


def public_page_customizations(
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for page in pages or load_managed_pages():
        rendered_blocks = []
        for block in page["blocks"]:
            if not block["enabled"]:
                continue
            html, _, _ = render_markdown(block["content"])
            rendered_blocks.append(SimpleNamespace(**block, html=html))
        page_context = {**page, "blocks": tuple(rendered_blocks)}
        result[page["key"]] = SimpleNamespace(**page_context)
    return result


def enabled_page_shortcuts(
    pages: list[dict[str, Any]] | None = None,
    custom_pages: list[CustomPage] | None = None,
) -> tuple[Any, ...]:
    shortcuts = [
        SimpleNamespace(key=page["key"], label=page["label"], system=True, item_id=None)
        for page in (pages if pages is not None else load_managed_pages())
        if page["enabled"]
    ]
    shortcuts.extend(
        SimpleNamespace(key=page.slug, label=page.title, system=False, item_id=page.id)
        for page in (
            custom_pages
            if custom_pages is not None
            else db.session.scalars(
                db.select(CustomPage)
                .where(CustomPage.status == "published")
                .order_by(CustomPage.sort_order, CustomPage.title)
            ).all()
        )
    )
    return tuple(shortcuts)


def load_primary_menu(raw: str | None = None) -> list[dict[str, Any]]:
    supplied = _json_setting(PRIMARY_MENU_SETTING, list(PRIMARY_MENU_DEFAULTS), raw)
    if not isinstance(supplied, list):
        supplied = list(PRIMARY_MENU_DEFAULTS)
    result = []
    seen: set[str] = set()
    for index, item in enumerate(supplied):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or f"menu-{index + 1}")[:80]
        if item_id in seen:
            continue
        seen.add(item_id)
        target_type = str(item.get("target_type", "url"))
        if target_type not in {"system", "page", "url"}:
            target_type = "url"
        result.append(
            {
                "id": item_id,
                "label": str(item.get("label", "菜单项"))[:80] or "菜单项",
                "target_type": target_type,
                "target": str(item.get("target", ""))[:180],
                "url": str(item.get("url", ""))[:500],
                "visible": bool(item.get("visible", True)),
                "open_new_tab": bool(item.get("open_new_tab", False)),
                "roles": [],
                "sort_order": int(item.get("sort_order", index * 10)),
            }
        )
    return sorted(result, key=lambda item: item["sort_order"])


def save_primary_menu(items: list[dict[str, Any]]) -> None:
    for item in items:
        item["roles"] = []
    _save_json(PRIMARY_MENU_SETTING, items)


def build_primary_navigation(
    items: list[dict[str, Any]] | None = None,
    managed_pages: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    custom_pages: list[Any] | tuple[Any, ...] | None = None,
) -> tuple[Any, ...]:
    page_source = managed_pages if managed_pages is not None else load_managed_pages()
    pages = {item["key"]: item for item in page_source}
    custom_pages_by_id = {
        str(item.id): item
        for item in (
            custom_pages
            if custom_pages is not None
            else db.session.scalars(
                db.select(CustomPage).where(CustomPage.status == "published")
            ).all()
        )
    }
    output = []
    for item in items or load_primary_menu():
        if not item["visible"]:
            continue
        endpoint = ""
        summary = ""
        if item["target_type"] == "system":
            page = pages.get(item["target"])
            if not page or not page["enabled"]:
                continue
            endpoint = page["endpoint"]
            url = url_for(endpoint)
            summary = page["subtitle"]
        elif item["target_type"] == "page":
            page = custom_pages_by_id.get(item["target"])
            if page is None:
                continue
            endpoint = "public.custom_page"
            url = url_for(endpoint, slug=page.slug)
            summary = page.summary
        else:
            url = item["url"] or "/"
        navigation_item = {
            **item,
            "url": url,
            "endpoint": endpoint,
            "summary": summary,
        }
        output.append(SimpleNamespace(**navigation_item))
    return tuple(output)


def load_footer_content(raw: str | None = None) -> dict[str, Any]:
    supplied = _json_setting(FOOTER_CONTENT_SETTING, FOOTER_DEFAULTS, raw)
    if not isinstance(supplied, dict):
        supplied = deepcopy(FOOTER_DEFAULTS)
    columns = []
    for index, column in enumerate(supplied.get("columns", [])):
        if not isinstance(column, dict):
            continue
        links = []
        for link in column.get("links", []):
            if isinstance(link, dict) and str(link.get("label", "")).strip():
                try:
                    link_url = safe_content_url(str(link.get("url", "/")), allow_empty=False)
                except ValueError:
                    continue
                links.append({"label": str(link["label"])[:80], "url": link_url})
        columns.append(
            {
                "id": str(column.get("id", f"column-{index + 1}"))[:80],
                "title": str(column.get("title", "链接"))[:80],
                "links": links,
            }
        )
    return {
        "description": str(supplied.get("description", FOOTER_DEFAULTS["description"]))[:300],
        "copyright": str(supplied.get("copyright", FOOTER_DEFAULTS["copyright"]))[:255],
        "columns": columns,
    }


def save_footer_content(value: dict[str, Any]) -> None:
    _save_json(FOOTER_CONTENT_SETTING, value)


def load_admin_navigation(raw: str | None = None) -> dict[str, Any]:
    supplied = _json_setting(ADMIN_NAVIGATION_SETTING, ADMIN_NAVIGATION_DEFAULTS, raw)
    parents = supplied.get("parents", []) if isinstance(supplied, dict) else []
    children = supplied.get("children", {}) if isinstance(supplied, dict) else {}
    known_parents = ADMIN_NAVIGATION_DEFAULTS["parents"]
    normalized_parents = [key for key in parents if key in known_parents]
    for index, key in enumerate(known_parents):
        if key in normalized_parents:
            continue
        following = next(
            (
                candidate
                for candidate in known_parents[index + 1 :]
                if candidate in normalized_parents
            ),
            None,
        )
        if following is None:
            normalized_parents.append(key)
        else:
            normalized_parents.insert(normalized_parents.index(following), key)
    normalized_children = {}
    for parent, defaults in ADMIN_NAVIGATION_DEFAULTS["children"].items():
        stored = children.get(parent, []) if isinstance(children, dict) else []
        ordered = [key for key in stored if key in defaults]
        ordered.extend(key for key in defaults if key not in ordered)
        normalized_children[parent] = ordered
    return {"parents": normalized_parents, "children": normalized_children}


def save_admin_navigation(value: dict[str, Any]) -> None:
    _save_json(ADMIN_NAVIGATION_SETTING, value)
