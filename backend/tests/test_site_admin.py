from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from app import defaults
from app.services import settings
from app.timeutil import iso, utcnow
from tests.conftest import make_moment, make_page, make_post, png_bytes

A = "/api/admin"


# =====================================================================================================================================
# pages
# =====================================================================================================================================
def test_page_lifecycle_and_public_read(admin, api):
    p = make_page(admin, "关于", slug="about", content_md="## 你好\n\n我是 sau_baka。", template="sidebar")
    assert p["slug"] == "about" and p["url"] == "/about" and p["template"] == "sidebar" and p["toc"][0]["text"] == "你好"
    pub = api.get("/api/pages/about").get_json()
    assert pub["title"] == "关于" and "我是 sau_baka" in pub["html"] and pub["template"] == "sidebar" and pub["seo"]["noindex"] is False
    html = api.get("/about")
    assert html.status_code == 200 and "<title>关于 · " in html.get_data(as_text=True)
    updated = admin.patch(f"{A}/pages/{p['id']}", {"title": "关于我", "content_md": "新内容", "status": "draft"}).get_json()
    assert updated["title"] == "关于我"
    assert api.get("/api/pages/about").status_code == 404 and api.get("/about").status_code == 404
    admin.delete(f"{A}/pages/{p['id']}")
    assert admin.get(f"{A}/pages?trashed=1").get_json()["total"] == 1
    assert admin.post(f"{A}/pages/{p['id']}/restore", {}).status_code == 200
    admin.delete(f"{A}/pages/{p['id']}")
    assert admin.delete(f"{A}/pages/{p['id']}/purge").status_code == 200


def test_page_slugs_cannot_shadow_the_site(admin):
    for slug in ("blog", "moments", "api", "admin", "media", "search", "archive", "tag", "category", "series", "sitemap.xml", "assets"):
        r = admin.post(f"{A}/pages", {"title": "x", "slug": slug})
        assert r.status_code in (422,), slug
    auto = make_page(admin, "博客")  # pinyin of the title would be "bo-ke", fine; a title that slugifies to a reserved word is renamed
    assert auto["slug"] == "bo-ke"
    clash = make_page(admin, "Search")
    assert clash["slug"] != "search" and clash["slug"].startswith("search")
    a = make_page(admin, "同名", slug="same")
    assert admin.post(f"{A}/pages", {"title": "x", "slug": "same"}).status_code == 409
    assert a["id"]


def test_page_options_validation_and_seo(admin, api, png):
    mid = admin.upload(f"{A}/media", png(300, 200)).get_json()["id"]
    p = make_page(admin, "有 SEO", slug="seo-page", seo_title="自定义标题", seo_description="自定义描述", seo_image_media_id=mid)
    assert p["seo"]["title"] == "自定义标题" and p["seo"]["image"]["id"] == mid
    html = api.get("/seo-page").get_data(as_text=True)
    assert "<title>自定义标题 · " in html and 'content="自定义描述"' in html and "og:image" in html
    assert admin.post(f"{A}/pages", {"title": "x", "template": "weird"}).status_code == 422
    assert admin.post(f"{A}/pages", {"title": "x", "seo_image_media_id": 4242}).status_code == 422
    unlisted = make_page(admin, "仅链接", status="unlisted")
    assert api.get(f"/{unlisted['slug']}").status_code == 200 and "noindex" in api.get(f"/{unlisted['slug']}").get_data(as_text=True)
    assert unlisted["slug"] not in api.get("/sitemap.xml").get_data(as_text=True)


def test_page_slug_change_redirects_and_nav_follows(admin, api):
    p = make_page(admin, "友链", slug="links", in_nav=True)
    admin.patch(f"{A}/pages/{p['id']}", {"slug": "friends"})
    assert api.get("/links").headers["Location"] == "/friends"
    top = api.get("/api/site").get_json()["nav"]["top"]
    assert [i["url"] for i in top if i["label"] == "友链"] == ["/friends"]


def test_page_nav_switches_materialise_the_default_menu_and_follow_the_page(admin, api):
    p = make_page(admin, "使用说明", slug="guide")
    assert (p["in_nav"], p["in_footer"]) == (False, False)
    on = admin.patch(f"{A}/pages/{p['id']}", {"in_nav": True, "in_footer": True}).get_json()
    assert (on["in_nav"], on["in_footer"]) == (True, True)
    site = api.get("/api/site").get_json()["nav"]
    assert [i["label"] for i in site["top"]] == ["首页", "博客", "动态", "归档", "使用说明"]  # "关于" stays hidden until that page exists
    assert [i["label"] for i in admin.get(f"{A}/nav").get_json()["top"]["items"]] == ["首页", "博客", "动态", "归档", "关于", "使用说明"]
    assert site["footer"][-1]["url"] == "/guide"
    off = admin.patch(f"{A}/pages/{p['id']}", {"in_nav": False}).get_json()
    assert (off["in_nav"], off["in_footer"]) == (False, True)
    admin.patch(f"{A}/pages/{p['id']}", {"status": "draft"})
    assert "/guide" not in [i["url"] for i in api.get("/api/site").get_json()["nav"]["footer"]]  # not public: not linked
    admin.delete(f"{A}/pages/{p['id']}")
    admin.delete(f"{A}/pages/{p['id']}/purge")
    assert all(i["target"] != "guide" for i in admin.get(f"{A}/nav").get_json()["footer"]["items"])


def test_page_revisions_and_conflicts(admin):
    p = make_page(admin, "历史", content_md="v1")
    admin.patch(f"{A}/pages/{p['id']}", {"content_md": "v2"})
    items = admin.get(f"{A}/pages/{p['id']}/revisions").get_json()["items"]
    assert len(items) == 2
    old = admin.get(f"{A}/pages/{p['id']}/revisions/{items[1]['id']}").get_json()
    assert old["snapshot"]["content_md"] == "v1" and admin.get(f"{A}/pages/{p['id']}/revisions/999999").status_code == 404
    back = admin.post(f"{A}/pages/{p['id']}/revisions/{items[1]['id']}/restore", {}).get_json()
    assert back["content_md"] == "v1" and len(admin.get(f"{A}/pages/{p['id']}/revisions").get_json()["items"]) == 3
    admin.patch(f"{A}/pages/{p['id']}", {"content_md": "v2"})
    fresh = admin.get(f"{A}/pages/{p['id']}").get_json()
    assert admin.patch(f"{A}/pages/{p['id']}", {"title": "甲", "expected_updated_at": fresh["updated_at"]}).status_code == 200
    assert admin.patch(f"{A}/pages/{p['id']}", {"title": "乙", "expected_updated_at": fresh["updated_at"]}).status_code == 409


# =====================================================================================================================================
# navigation
# =====================================================================================================================================
def test_default_navigation_is_resolved_for_visitors(api):
    nav = api.get("/api/site").get_json()["nav"]
    assert [(i["label"], i["url"]) for i in nav["top"]] == [("首页", "/"), ("博客", "/blog"), ("动态", "/moments"), ("归档", "/archive")]  # 关于 hidden: no such page yet
    assert [(i["label"], i["url"], i["action"]) for i in nav["mobile"]] == [
        ("首页", "/", None), ("博客", "/blog", None), ("动态", "/moments", None), ("搜索", None, "search"), ("更多", None, "more")]
    assert [(i["label"], i["url"]) for i in nav["footer"]] == [("首页", "/"), ("博客", "/blog"), ("动态", "/moments"), ("归档", "/archive")]


def test_the_about_item_appears_once_the_page_exists(admin, api):
    make_page(admin, "关于", slug="about")
    assert "/about" in [i["url"] for i in api.get("/api/site").get_json()["nav"]["top"]]


def test_navigation_editing(admin, api):
    got = admin.get(f"{A}/nav").get_json()
    assert got["mobile_max"] == 5 and got["top"]["customized"] is False and len(got["top"]["items"]) == 5
    cat = admin.post(f"{A}/taxonomy/categories", {"name": "代码", "slug": "code"}).get_json()
    items = [
        {"label": "首页", "kind": "route", "target": "/", "sticker": "home"},
        {"label": "代码", "kind": "category", "target": "code"},
        {"label": "隐藏的", "kind": "route", "target": "/blog", "enabled": False},
        {"label": "GitHub", "kind": "link", "target": "https://github.com/someone"},
        {"label": "写信", "kind": "link", "target": "mailto:me@example.com"},
    ]
    r = admin.put(f"{A}/nav/top", {"items": items})
    assert r.status_code == 200 and r.get_json()["customized"] is True
    top = api.get("/api/site").get_json()["nav"]["top"]
    assert [(i["label"], i["url"], i["external"]) for i in top] == [
        ("首页", "/", False), ("代码", f"/category/{cat['slug']}", False), ("GitHub", "https://github.com/someone", True), ("写信", "mailto:me@example.com", False)]
    assert api.get("/api/site").get_json()["nav"]["mobile"][0]["label"] == "首页"  # other regions keep their defaults
    reset = admin.post(f"{A}/nav/top/reset", {}).get_json()
    assert reset["customized"] is False and len(reset["items"]) == 5


@pytest.mark.parametrize("item,field", [
    ({"label": "", "kind": "route", "target": "/"}, "label"),
    ({"label": "x", "kind": "route", "target": "/nowhere"}, "target"),
    ({"label": "x", "kind": "page", "target": "missing"}, "target"),
    ({"label": "x", "kind": "category", "target": "missing"}, "target"),
    ({"label": "x", "kind": "link", "target": "javascript:alert(1)"}, "target"),
    ({"label": "x", "kind": "link", "target": "ftp://example.com"}, "target"),
    ({"label": "x", "kind": "action", "target": "explode"}, "target"),
    ({"label": "x", "kind": "route", "target": "/", "sticker": "no-such-icon"}, "sticker"),
])
def test_navigation_item_validation(admin, item, field):
    r = admin.put(f"{A}/nav/top", {"items": [item]})
    assert r.status_code == 422 and f"items.0.{field}" in (r.get_json()["error"].get("fields") or {}), r.get_json()


def test_mobile_bar_has_five_slots_at_most(admin):
    six = [{"label": f"项{i}", "kind": "route", "target": "/"} for i in range(6)]
    r = admin.put(f"{A}/nav/mobile", {"items": six})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "too_many" and "5" in r.get_json()["error"]["fields"]["items"]
    assert admin.put(f"{A}/nav/mobile", {"items": six[:5]}).status_code == 200
    assert admin.put(f"{A}/nav/sidebar", {"items": []}).status_code == 404
    assert admin.put(f"{A}/nav/top", {"items": [{"label": "x", "kind": "route", "target": "/", "colour": "red"}]}).status_code == 422


# =====================================================================================================================================
# home page
# =====================================================================================================================================
def block(api, kind):
    return next((b for b in api.get("/api/home").get_json()["blocks"] if b["type"] == kind), None)


def test_default_home_layout(api):
    types = [b["type"] for b in api.get("/api/home").get_json()["blocks"]]
    assert types == ["hero", "latest_posts", "latest_moments"]  # notice and featured are off by default; the shelf, the about card and the now note are gone
    hero = block(api, "hero")
    assert [b["url"] for b in hero["config"]["buttons"]] == ["/blog", "/moments"]
    assert "title_lines" not in hero["config"] and "polaroid" not in hero["config"]   # the big title is the site's name now, and there is no photo card


def test_home_shows_latest_content(admin, api):
    for i in range(8):
        make_post(admin, f"文章{i}", published_at=f"2026-03-0{i + 1}T00:00:00Z")
    for i in range(5):
        make_moment(admin, f"动态{i}", published_at=f"2026-03-0{i + 1}T00:00:00Z")
    posts = block(api, "latest_posts")["data"]["posts"]
    assert [p["title"] for p in posts] == ["文章7", "文章6", "文章5", "文章4", "文章3", "文章2"]
    assert [m["text"] for m in block(api, "latest_moments")["data"]["moments"]] == ["动态4", "动态3", "动态2"]


def test_home_customisation_validation_and_reset(admin, api, png):
    got = admin.get(f"{A}/home").get_json()
    assert got["customized"] is False and [b["type"] for b in got["blocks"]][0] == "hero" and got["blocks"][0]["id"] is None
    blocks = [{k: b[k] for k in ("type", "enabled", "config")} for b in got["blocks"]]
    latest = next(b for b in blocks if b["type"] == "latest_posts")
    latest["config"]["count"] = 2
    latest["config"]["title"] = "新标题"
    blocks.remove(latest)
    blocks.insert(0, latest)  # latest_posts first
    blocks = [b for b in blocks if b["type"] != "latest_moments"]
    saved = admin.put(f"{A}/home", {"blocks": blocks})
    assert saved.status_code == 200 and saved.get_json()["customized"] is True
    assert [b["type"] for b in api.get("/api/home").get_json()["blocks"]][:2] == ["latest_posts", "hero"] and block(api, "latest_moments") is None
    assert block(api, "latest_posts")["config"]["title"] == "新标题"
    again = admin.get(f"{A}/home").get_json()
    assert again["customized"] is True and all(b["id"] for b in again["blocks"])
    reset = admin.post(f"{A}/home/reset", {}).get_json()
    assert reset["customized"] is False and block(api, "latest_moments") is not None and block(api, "hero") is not None


@pytest.mark.parametrize("blocks,needle", [
    ([{"type": "hero", "config": {"title_lines": ["a"]}}], "blocks.0.config.title_lines"),
    ([{"type": "hero", "config": {"polaroid": {"media_id": None}}}], "blocks.0.config.polaroid"),
    ([{"type": "hero", "config": {"buttons": [{"label": "a", "url": "/x"}] * 4}}], "blocks.0.config.buttons"),
    ([{"type": "hero", "config": {"buttons": [{"label": "a", "url": "javascript:alert(1)"}]}}], "blocks.0.config.buttons.0.url"),
    ([{"type": "hero", "config": {"doodles": ["skull"]}}], "blocks.0.config.doodles.0"),
    ([{"type": "latest_posts", "config": {"count": 99}}], "blocks.0.config.count"),
    ([{"type": "latest_posts", "config": {"layout": "masonry"}}], "blocks.0.config.layout"),
    ([{"type": "notice", "config": {"text": "x", "starts_at": "yesterday"}}], "blocks.0.config.starts_at"),
    ([{"type": "latest_posts", "config": {"colour": "pink"}}], "blocks.0.config.colour"),
])
def test_home_block_validation(admin, blocks, needle):
    r = admin.put(f"{A}/home", {"blocks": blocks})
    assert r.status_code == 422 and needle in r.get_json()["error"]["fields"], r.get_json()


def test_home_rejects_duplicates_and_unknown_types(admin):
    assert admin.put(f"{A}/home", {"blocks": [{"type": "hero"}, {"type": "hero"}]}).get_json()["error"]["code"] == "duplicate"
    assert admin.put(f"{A}/home", {"blocks": [{"type": "comments"}]}).status_code == 422
    for retired in ("shelf", "about", "now"):      # the modules that were taken off the home page cannot come back by a save either
        assert admin.put(f"{A}/home", {"blocks": [{"type": retired}]}).status_code == 422


def test_stored_rows_of_retired_modules_are_ignored(admin, api, app):
    """A home page customised before the shelf, the about card and the now note were removed: those rows never show, never reach the editor, and the next save drops them."""
    from app.db import session_scope
    from app.models import HomeBlock
    with session_scope(app) as session:
        session.add_all([HomeBlock(type="hero", enabled=True, config={}, sort_order=0), HomeBlock(type="shelf", enabled=True, config={"title": "书架"}, sort_order=1),
                         HomeBlock(type="about", enabled=True, config={"title": "关于我"}, sort_order=2), HomeBlock(type="now", enabled=True, config={"title": "近况"}, sort_order=3)])
    assert [b["type"] for b in api.get("/api/home").get_json()["blocks"]] == ["hero"]
    got = admin.get(f"{A}/home").get_json()
    assert got["customized"] is True and [b["type"] for b in got["blocks"]] == ["hero"]
    assert admin.put(f"{A}/home", {"blocks": [{"type": b["type"], "enabled": b["enabled"], "config": b["config"]} for b in got["blocks"]]}).status_code == 200


def test_a_hero_stored_before_the_redesign_is_read_in_its_current_shape(admin, api, app):
    """The photo card, the typed title and the RSS button were retired: an old stored hero opens without them and saves again."""
    from app.db import session_scope
    from app.models import HomeBlock

    old = {"note": "n", "title_lines": ["你好"], "intro": "", "polaroid": {"media_id": None, "caption": "c", "bubble": "b"}, "doodles": ["star", "cloud"],
           "buttons": [{"label": "读", "url": "/blog", "style": "fill"}, {"label": "订阅 RSS", "url": "/feed/posts.xml", "style": "link"}]}
    with session_scope(app) as s:
        s.add(HomeBlock(type="hero", enabled=True, config=old, sort_order=0))
        settings.bump_site_version(s)
    config = block(api, "hero")["config"]
    assert set(config) == {"note", "intro", "buttons", "doodles"} and config["doodles"] == ["star"] and [b["url"] for b in config["buttons"]] == ["/blog"]
    saved = [{k: v for k, v in b.items() if k != "id"} for b in admin.get(f"{A}/home").get_json()["blocks"]]
    assert admin.put(f"{A}/home", {"blocks": saved}).status_code == 200


def test_rss_leftovers_in_stored_settings_and_navigation_are_ignored(admin, api, app):
    """Retired RSS data: the author's subscribe link, the footer entries and their icon do not reach visitors and do not block the next save."""
    from app.db import session_scope
    from app.models import NavItem

    with session_scope(app) as s:
        settings.set_raw(s, "cfg.author", {"links": [{"label": "订阅", "kind": "rss", "url": "/feed/posts.xml"}, {"label": "邮件", "kind": "mail", "url": "mailto:a@b.example"}]})
        settings.set_raw(s, "cfg.seo", {"rss": {"full_text": True, "items": 20}, "title": "t"})
        s.add(NavItem(region="footer", sort_order=0, label="文章 RSS", kind="link", target="/feed/posts.xml", sticker="rss", enabled=True))
        s.add(NavItem(region="footer", sort_order=1, label="首页", kind="route", target="/", sticker="rss", enabled=True))
        settings.bump_site_version(s)
    assert [link["kind"] for link in api.get("/api/site").get_json()["author"]["links"]] == ["mail"]
    assert [(i["label"], i["sticker"]) for i in api.get("/api/site").get_json()["nav"]["footer"]] == [("首页", None)]
    assert "rss" not in admin.get(f"{A}/settings").get_json()["groups"]["seo"]
    items = [{k: v for k, v in i.items() if k not in ("id", "region")} for i in admin.get(f"{A}/nav").get_json()["footer"]["items"]]
    assert admin.put(f"{A}/nav/footer", {"items": items}).status_code == 200
    assert admin.patch(f"{A}/settings/author", {"links": [{"label": "邮件", "kind": "mail", "url": "mailto:a@b.example"}]}).status_code == 200


def test_featured_block_auto_and_manual(admin, api):
    a = make_post(admin, "精选一", featured=True, published_at="2026-04-01T00:00:00Z")
    b = make_post(admin, "普通", published_at="2026-04-02T00:00:00Z")
    c = make_post(admin, "精选二", featured=True, published_at="2026-04-03T00:00:00Z")
    admin.put(f"{A}/home", {"blocks": [{"type": "featured", "config": {"count": 3}}]})
    assert [p["title"] for p in block(api, "featured")["data"]["posts"]] == ["精选二", "精选一"]
    admin.put(f"{A}/home", {"blocks": [{"type": "featured", "config": {"mode": "manual", "post_ids": [b["id"], a["id"]]}}]})
    assert [p["title"] for p in block(api, "featured")["data"]["posts"]] == ["普通", "精选一"]
    admin.patch(f"{A}/posts/{b['id']}", {"status": "draft"})
    assert [p["title"] for p in block(api, "featured")["data"]["posts"]] == ["精选一"]  # a draft cannot be featured
    admin.put(f"{A}/home", {"blocks": [{"type": "featured", "config": {"mode": "manual", "post_ids": []}}]})
    assert block(api, "featured") is None  # nothing to show: the block disappears
    assert c["id"]


def test_notice_only_shows_inside_its_time_window(admin, api):
    def put(**cfg):
        admin.put(f"{A}/home", {"blocks": [{"type": "notice", "config": {"text": "停机维护", **cfg}}]})
    put()
    assert block(api, "notice")["config"]["text"] == "停机维护"
    put(starts_at=iso(utcnow() + timedelta(hours=1)))
    assert block(api, "notice") is None
    put(ends_at=iso(utcnow() - timedelta(hours=1)))
    assert block(api, "notice") is None
    put(starts_at=iso(utcnow() - timedelta(hours=1)), ends_at=iso(utcnow() + timedelta(hours=1)))
    assert block(api, "notice") is not None
    admin.put(f"{A}/home", {"blocks": [{"type": "notice", "config": {"text": ""}}]})
    assert block(api, "notice") is None


def test_unsaved_layout_preview(admin, api):
    make_post(admin, "只是预览")
    preview = admin.post(f"{A}/home/preview", {"blocks": [{"type": "latest_posts", "config": {"count": 1, "title": "预览标题"}}]})
    assert preview.status_code == 200 and preview.get_json()["blocks"][0]["config"]["title"] == "预览标题"
    assert preview.get_json()["blocks"][0]["data"]["posts"][0]["title"] == "只是预览"
    assert block(api, "latest_posts")["config"]["title"] == "最近的文章"  # nothing was saved
    assert admin.post(f"{A}/home/preview", {"blocks": [{"type": "latest_posts", "config": {"count": 99}}]}).status_code == 422


# =====================================================================================================================================
# settings
# =====================================================================================================================================
def test_settings_expose_groups_defaults_and_vocabulary(admin):
    d = admin.get(f"{A}/settings").get_json()
    assert set(d["groups"]) == {"site", "author", "appearance", "seo", "footer", "stats", "backup"}
    assert d["groups"]["site"]["name"] == defaults.SITE_NAME == "saubakaの博客" and d["groups"]["site"]["name_en"] == "Baka Blog"
    assert d["groups"]["author"]["name"] == "sau_baka" and d["groups"]["site"]["tagline"] == "不是笨蛋！！"
    assert d["customized"] == [] and d["defaults"]["site"]["name"] == defaults.SITE_NAME
    v = d["vocab"]
    assert v["themes"] == ["default", "sky", "sakura", "fog"] and "full" in v["motion"] and len(v["moods"]) == 10 and v["mobile_nav_max"] == 5


def test_settings_patch_merges_and_changes_the_public_site(admin, api):
    r = admin.patch(f"{A}/settings/site", {"name": "新的站名", "tagline": "新的简介"})
    assert r.status_code == 200 and r.get_json()["values"]["name"] == "新的站名" and r.get_json()["values"]["name_en"] == "Baka Blog"
    site = api.get("/api/site").get_json()
    assert site["name"] == "新的站名" and site["tagline"] == "新的简介" and site["name_en"] == "Baka Blog"
    assert "<title>新的站名 · 新的简介</title>" in api.get("/").get_data(as_text=True)
    admin.patch(f"{A}/settings/appearance", {"theme": "sakura", "decor": {"doodles": False}})
    look = api.get("/api/site").get_json()
    assert look["theme"] == "sakura" and look["decor"] == {"tape": True, "doodles": False}
    assert admin.get(f"{A}/settings").get_json()["customized"] == ["site", "appearance"]
    back = admin.post(f"{A}/settings/site/reset", {}).get_json()
    assert back["values"]["name"] == defaults.SITE_NAME and api.get("/api/site").get_json()["name"] == defaults.SITE_NAME


@pytest.mark.parametrize("group,payload,field", [
    ("site", {"timezone": "Mars/Olympus"}, "timezone"), ("site", {"name": ""}, "name"), ("site", {"name": "x" * 61}, "name"),
    ("site", {"language": "klingon!"}, "language"), ("site", {"colour": "red"}, "colour"),
    ("appearance", {"theme": "midnight"}, "theme"), ("appearance", {"motion": "turbo"}, "motion"), ("appearance", {"code_theme": "dark"}, "code_theme"),
    ("author", {"links": [{"label": "x", "kind": "link", "url": "javascript:alert(1)"}]}, "links.0.url"),
    ("author", {"links": [{"label": "x", "kind": "fax", "url": "https://x.com"}]}, "links.0.kind"),
    ("seo", {"robots_extra": "Delete: everything"}, "robots_extra"),
    ("seo", {"rss": {"full_text": True, "items": 20}}, "rss"), ("author", {"links": [{"label": "x", "kind": "rss", "url": "/feed/posts.xml"}]}, "links.0.kind"),
    ("backup", {"hour": 24}, "hour"), ("backup", {"keep": 0}, "keep"), ("stats", {"enabled": "maybe"}, "enabled"),
])
def test_settings_validation(admin, group, payload, field):
    r = admin.patch(f"{A}/settings/{group}", payload)
    assert r.status_code == 422 and field in r.get_json()["error"]["fields"], r.get_json()


def test_settings_unknown_group_and_bad_body(admin):
    assert admin.patch(f"{A}/settings/comments", {"enabled": True}).status_code == 404
    assert admin.post(f"{A}/settings/comments/reset", {}).status_code == 404
    assert admin.patch(f"{A}/settings/site", ["not", "an", "object"]).status_code == 400


def test_settings_pictures_must_exist_and_are_tracked(admin, api, png):
    assert admin.patch(f"{A}/settings/site", {"logo_media_id": 4242}).status_code == 422
    logo = admin.upload(f"{A}/media", png(200, 200)).get_json()
    fav = admin.upload(f"{A}/media", png(64, 64, (1, 2, 3))).get_json()
    avatar = admin.upload(f"{A}/media", png(300, 300, (3, 2, 1))).get_json()
    admin.patch(f"{A}/settings/site", {"logo_media_id": logo["id"], "favicon_media_id": fav["id"]})
    admin.patch(f"{A}/settings/author", {"avatar_media_id": avatar["id"]})
    admin.patch(f"{A}/settings/seo", {"share_image_media_id": logo["id"]})
    site = api.get("/api/site").get_json()
    assert site["logo"]["id"] == logo["id"] and site["favicon"]["id"] == fav["id"] and site["author"]["avatar"]["id"] == avatar["id"]
    assert site["seo"]["share_image"]["id"] == logo["id"]
    assert f'<link rel="icon" href="{site["favicon"]["src"]}">' in api.get("/").get_data(as_text=True)
    assert 'property="og:image"' in api.get("/").get_data(as_text=True)
    assert any(u["type"] == "setting" for u in admin.get(f"{A}/media/{logo['id']}").get_json()["usage"])
    admin.patch(f"{A}/settings/site", {"logo_media_id": None})
    assert api.get("/api/site").get_json()["logo"] is None
    assert admin.get(f"{A}/media/{logo['id']}").get_json()["usage"][0]["type"] == "setting"  # still the share image


def test_a_deleted_logo_disappears_from_the_public_site(admin, api, png):
    logo = admin.upload(f"{A}/media", png(100, 100)).get_json()
    admin.patch(f"{A}/settings/site", {"logo_media_id": logo["id"]})
    admin.delete(f"{A}/media/{logo['id']}?force=1")
    assert api.get("/api/site").get_json()["logo"] is None


def test_footer_default_copyright_uses_the_names(admin, api):
    year = utcnow().year
    assert api.get("/api/site").get_json()["footer"]["copyright"] == f"© {year} sau_baka · Baka Blog"
    admin.patch(f"{A}/settings/footer", {"copyright": "自定义版权", "icp": "京ICP备00000000号"})
    assert api.get("/api/site").get_json()["footer"] == {"icp": "京ICP备00000000号", "copyright": "自定义版权", "text": defaults.SITE_DESCRIPTION}


def test_names_and_default_copy_live_in_one_file():
    """The site name, the author and the tagline are written down once (defaults.py); everything else reads them from settings."""
    root = Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "defaults.py":
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("saubaka", "Baka Blog", "不是笨蛋"):
            if needle in text:
                offenders.append(f"{path.relative_to(root)}: {needle}")
    assert offenders == []


# =====================================================================================================================================
# redirects
# =====================================================================================================================================
R = f"{A}/redirects"


def test_redirect_crud_and_application(admin, api):
    r = admin.post(R, {"source": "/old-page/", "target": "/about", "status_code": 302})
    assert r.status_code == 201 and r.get_json()["source"] == "/old-page" and r.get_json()["status_code"] == 302 and r.get_json()["auto"] is False
    rid = r.get_json()["id"]
    hit = api.get("/old-page")
    assert hit.status_code == 302 and hit.headers["Location"] == "/about"
    assert api.get("/old-page/").status_code == 301  # trailing slash: normalised first
    assert admin.get(R).get_json()["items"][0]["hits"] >= 1
    external = admin.post(R, {"source": "/away", "target": "https://example.com/x"}).get_json()
    assert api.get("/away").headers["Location"] == "https://example.com/x" and external["status_code"] == 301
    upd = admin.patch(f"{R}/{rid}", {"target": "/blog", "status_code": 301}).get_json()
    assert upd["target"] == "/blog" and api.get("/old-page").status_code == 301
    assert admin.delete(f"{R}/{rid}").status_code == 200 and api.get("/old-page").status_code == 404
    assert admin.delete(f"{R}/{rid}").status_code == 404


@pytest.mark.parametrize("payload", [
    {"source": "no-slash", "target": "/x"}, {"source": "//evil.example", "target": "/x"}, {"source": "/a", "target": "javascript:alert(1)"},
    {"source": "/a", "target": "relative"}, {"source": "/a", "target": "/a"}, {"source": "/", "target": "/x"}, {"source": "/api/health", "target": "/x"},
    {"source": "/admin/users", "target": "/x"}, {"source": "/media/abc/960.webp", "target": "/x"},
    {"source": "/has space", "target": "/x"}, {"source": "/a", "target": "/x", "status_code": 307}, {"source": "/a"},
])
def test_redirect_validation(admin, payload):
    assert admin.post(R, payload).status_code == 422


def test_redirect_loops_and_duplicates_are_refused(admin):
    admin.post(R, {"source": "/a", "target": "/b"})
    admin.post(R, {"source": "/b", "target": "/c"})
    loop = admin.post(R, {"source": "/c", "target": "/a"})
    assert loop.status_code == 422 and loop.get_json()["error"]["code"] == "loop"
    assert admin.post(R, {"source": "/a", "target": "/z"}).status_code == 409


def test_redirect_chains_resolve_to_the_final_target(admin, api):
    admin.post(R, {"source": "/one", "target": "/two"})
    admin.post(R, {"source": "/two", "target": "/three"})
    admin.post(R, {"source": "/three", "target": "/blog"})
    assert api.get("/one").headers["Location"] == "/blog"


def test_redirect_listing_search_and_sort(admin, api):
    admin.post(R, {"source": "/a1", "target": "/x1"})
    admin.post(R, {"source": "/b2", "target": "/y2"})
    api.get("/b2")
    api.get("/b2")
    assert [r["source"] for r in admin.get(f"{R}?sort=hits").get_json()["items"]] == ["/b2", "/a1"]
    assert [r["source"] for r in admin.get(f"{R}?q=a1").get_json()["items"]] == ["/a1"]
    assert [r["source"] for r in admin.get(R).get_json()["items"]] == ["/b2", "/a1"]  # newest first


_ = png_bytes


def test_retired_setting_keys_and_doodles_in_stored_data_do_not_break_reads_or_saves(admin, session):
    """The mascot switch and the "cloud" doodle were removed. Rows saved earlier may still carry them: they must be ignored, not turn the next save into a 422."""
    from app.services import settings

    settings.set_raw(session, "cfg.appearance", {"decor": {"tape": True, "doodles": True, "mascot": False}, "theme": "sky"})
    session.commit()
    look = admin.get(f"{A}/settings").get_json()["groups"]["appearance"]
    assert look["decor"] == {"tape": True, "doodles": True} and look["theme"] == "sky"
    assert admin.patch(f"{A}/settings/appearance", {"motion": "soft"}).status_code == 200
    home = admin.get(f"{A}/home").get_json()
    hero = next(b for b in home["blocks"] if b["type"] == "hero")
    assert "cloud" not in hero["config"]["doodles"]
    blocks = [{"type": b["type"], "enabled": b["enabled"], "config": b["config"]} for b in home["blocks"]]
    hero_in = next(b for b in blocks if b["type"] == "hero")
    hero_in["config"] = {**hero_in["config"], "doodles": ["star", "cloud"]}
    assert admin.put(f"{A}/home", {"blocks": blocks}).status_code == 422          # not in the vocabulary any more
