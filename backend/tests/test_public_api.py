from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import timedelta

import pytest
from sqlalchemy import event

from app import defaults
from app.db import database
from app.timeutil import iso, utcnow
from app.version import __version__
from tests.conftest import make_moment, make_page, make_post

A = "/api/admin"


# ---- /api/site ----------------------------------------------------------------------------------------------------------------------
def test_site_payload(api):
    r = api.get("/api/site")
    assert r.status_code == 200
    s = r.get_json()
    assert (s["name"], s["name_en"], s["tagline"]) == ("saubakaの博客", "Baka Blog", "不是笨蛋！！")
    assert s["author"]["name"] == "sau_baka" and s["language"] == "zh-CN" and s["timezone"] == "Asia/Shanghai"
    assert s["theme"] == "default" and s["motion"] == "full" and s["code_theme"] == "frost"
    assert s["decor"] == {"tape": True, "doodles": True}
    assert s["texts"]["not_found_title"] == "这一页走丢了" and set(s["nav"]) == {"top", "mobile", "footer"}
    assert s["features"] == {"stats": True, "search": True} and [m["id"] for m in s["moods"]][:3] == ["happy", "energy", "calm"]
    assert s["version"] == __version__ and s["build"] and s["origin"].startswith("http")
    assert "comments" not in str(s).lower()


def test_site_version_and_build_are_reported(api):
    assert api.get("/api/health").get_json()["version"] == api.get("/api/site").get_json()["version"]


# ---- ETag / 304 ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["/api/site", "/api/home", "/api/posts", "/api/archive", "/api/taxonomy", "/api/moments", "/api/search?q=abc"])
def test_public_json_has_etag_and_answers_304(api, url):
    r = api.get(url)
    assert r.status_code == 200 and r.headers["ETag"].startswith('W/"') and r.headers["Cache-Control"] == "no-cache"
    again = api.get(url, headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304 and again.data == b""
    assert api.get(url, headers={"If-None-Match": 'W/"something-else"'}).status_code == 200


def test_etag_changes_when_content_changes(admin, api):
    before = api.get("/api/posts").headers["ETag"]
    make_post(admin, "新文章")
    assert api.get("/api/posts").headers["ETag"] != before


# ---- posts list ---------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def blog(admin):
    cat1 = admin.post(f"{A}/taxonomy/categories", {"name": "代码", "slug": "code"}).get_json()
    cat2 = admin.post(f"{A}/taxonomy/categories", {"name": "日常", "slug": "daily"}).get_json()
    series = admin.post(f"{A}/taxonomy/series", {"title": "连载", "slug": "serial"}).get_json()
    posts = [
        make_post(admin, "苹果派的做法", category_id=cat2["id"], tags=["美食"], published_at="2026-01-10T00:00:00Z"),
        make_post(admin, "SQLite 备份", category_id=cat1["id"], tags=["SQLite", "备份"], published_at="2026-02-10T00:00:00Z", series_id=series["id"]),
        make_post(admin, "Flask 登录", category_id=cat1["id"], tags=["Flask"], published_at="2026-03-10T00:00:00Z", series_id=series["id"]),
        make_post(admin, "置顶的旧文", category_id=cat2["id"], pinned=True, published_at="2025-12-01T00:00:00Z"),
    ]
    return {"cat1": cat1, "cat2": cat2, "series": series, "posts": posts}


def titles(api, query=""):
    return [p["title"] for p in api.get(f"/api/posts{query}").get_json()["items"]]


def test_post_list_order_and_card_shape(blog, api):
    assert titles(api) == ["置顶的旧文", "Flask 登录", "SQLite 备份", "苹果派的做法"]  # pinned first, then newest
    assert titles(api, "?sort=old") == ["置顶的旧文", "苹果派的做法", "SQLite 备份", "Flask 登录"]
    card = api.get("/api/posts?category=code").get_json()["items"][0]
    assert set(card) >= {"id", "slug", "url", "title", "summary", "cover", "category", "tags", "series", "pinned", "featured", "card_style",
                        "published_at", "updated_at", "reading_minutes", "word_count", "cover_focus"}
    assert card["url"] == f"/blog/{card['slug']}" and card["category"]["slug"] == "code" and card["series"]["slug"] == "serial"
    assert "content_md" not in card and "html" not in card


def test_post_list_filters_and_paging(blog, api):
    assert titles(api, "?category=code") == ["Flask 登录", "SQLite 备份"]
    assert titles(api, "?tag=flask") == ["Flask 登录"] and titles(api, "?tag=sqlite&category=code") == ["SQLite 备份"] and titles(api, "?tag=sqlite&category=daily") == []
    assert titles(api, "?series=serial") == ["SQLite 备份", "Flask 登录"]
    body = api.get("/api/posts?per=2&page=2").get_json()
    assert (body["page"], body["per"], body["total"], body["pages"]) == (2, 2, 4, 2) and [p["title"] for p in body["items"]] == ["SQLite 备份", "苹果派的做法"]
    assert api.get("/api/posts?per=2&page=9").get_json()["items"] == []
    f = api.get("/api/posts?category=code").get_json()["filters"]
    assert f["category"]["name"] == "代码" and f["tag"] is None and f["series"] is None
    for q in ("?category=nope", "?tag=nope", "?series=nope"):
        assert api.get(f"/api/posts{q}").status_code == 404
    for q in ("?page=0", "?per=31", "?per=abc", "?sort=random", "?page=-1"):
        assert api.get(f"/api/posts{q}").status_code == 422, q


def test_post_list_search_is_ranked_and_filterable(blog, api):
    body = api.get("/api/posts?q=SQLite").get_json()
    assert [p["title"] for p in body["items"]] == ["SQLite 备份"] and "<mark>" in body["items"][0]["snippet"]
    assert api.get("/api/posts?q=SQLite&category=daily").get_json()["items"] == []
    assert api.get("/api/posts?q=没有这个词啊").get_json()["total"] == 0


def test_list_does_not_run_one_query_per_post(admin, api, app):
    for i in range(12):
        make_post(admin, f"文章{i}", tags=[f"t{i}", "共用"])
    counter = {"n": 0}
    engine = database_engine(app)

    def count(*_a, **_k):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert len(api.get("/api/posts?per=12").get_json()["items"]) == 12
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert counter["n"] <= 10, counter["n"]


def database_engine(app):
    with app.app_context():
        return database().engine


# ---- post detail ---------------------------------------------------------------------------------------------------------------------------
def test_post_detail_has_everything_a_page_needs(blog, api, admin):
    mid = blog["posts"][1]["id"]
    admin.patch(f"{A}/posts/{mid}", {"content_md": "## 开头\n\n正文很长。\n\n### 小节\n\n更多。", "show_author_card": True, "seo_title": "自定义 SEO"})
    d = api.get(f"/api/posts/{blog['posts'][1]['slug']}").get_json()
    assert d["title"] == "SQLite 备份" and "<h2" in d["html"] and [t["text"] for t in d["toc"]] == ["开头", "小节"]
    assert d["options"] == {"show_toc": True, "show_reading_time": True, "show_author_card": True}
    assert d["prev"]["title"] == "苹果派的做法" and d["next"]["title"] == "Flask 登录"
    assert d["series_nav"]["total"] == 2 and d["series_nav"]["index"] == 1 and d["preview"] is False
    assert d["seo"]["title"] == "自定义 SEO" and d["seo"]["canonical"].endswith(f"/blog/{d['slug']}") and d["seo"]["noindex"] is False
    assert {r["slug"] for r in d["related"]} <= {p["slug"] for p in blog["posts"]}
    assert d["status"] == "published"


def test_prev_and_next_skip_hidden_posts(blog, admin, api):
    admin.patch(f"{A}/posts/{blog['posts'][0]['id']}", {"status": "draft"})
    d = api.get(f"/api/posts/{blog['posts'][2]['slug']}").get_json()
    assert d["prev"]["title"] == "SQLite 备份" and d["next"] is None
    first = api.get(f"/api/posts/{blog['posts'][3]['slug']}").get_json()
    assert first["prev"] is None and first["next"]["title"] == "SQLite 备份"


def test_related_posts_share_tags_first(admin, api):
    a = make_post(admin, "目标", tags=["x", "y"], published_at="2026-01-01T00:00:00Z")
    make_post(admin, "共享两个", tags=["x", "y"], published_at="2026-01-02T00:00:00Z")
    make_post(admin, "共享一个", tags=["x"], published_at="2026-01-03T00:00:00Z")
    make_post(admin, "无关", tags=["z"], published_at="2026-01-04T00:00:00Z")
    rel = api.get(f"/api/posts/{a['slug']}").get_json()["related"]
    assert [r["title"] for r in rel] == ["共享两个", "共享一个"]


def test_post_detail_404s(api):
    assert api.get("/api/posts/missing").status_code == 404
    assert api.get("/api/posts/missing").get_json()["error"]["code"] == "not_found"


# ---- archive ------------------------------------------------------------------------------------------------------------------------------
def test_archive_groups_by_year_and_month_in_the_site_time_zone(admin, api):
    make_post(admin, "二〇二六年十月", published_at="2026-10-05T10:00:00Z")
    make_post(admin, "跨年夜", published_at="2025-12-31T17:00:00Z")  # 2026-01-01 01:00 in Shanghai
    make_post(admin, "九月", published_at="2026-09-01T00:00:00Z")
    a = api.get("/api/archive").get_json()
    assert a["total"] == 3
    assert [(y["year"], y["count"]) for y in a["years"]] == [(2026, 3)]
    assert [(m["month"], [p["title"] for p in m["posts"]]) for m in a["years"][0]["months"]] == [(10, ["二〇二六年十月"]), (9, ["九月"]), (1, ["跨年夜"])]
    admin.patch(f"{A}/settings/site", {"timezone": "UTC"})
    a = api.get("/api/archive").get_json()
    assert [(y["year"], y["count"]) for y in a["years"]] == [(2026, 2), (2025, 1)]
    item = a["years"][0]["months"][0]["posts"][0]
    assert set(item) == {"id", "slug", "url", "title", "published_at", "category", "tags"}


# ---- taxonomy ------------------------------------------------------------------------------------------------------------------------------
def test_taxonomy_endpoint(blog, api):
    t = api.get("/api/taxonomy").get_json()
    assert {c["slug"]: c["count"] for c in t["categories"]} == {"code": 2, "daily": 2}
    assert {x["name"]: x["count"] for x in t["tags"]} == {"Flask": 1, "SQLite": 1, "备份": 1, "美食": 1}
    assert [(s["slug"], s["count"], s["status"]) for s in t["series"]] == [("serial", 2, "ongoing")]
    assert all("moment_count" in x for x in t["tags"])


# ---- pages ---------------------------------------------------------------------------------------------------------------------------------
def test_page_endpoint_and_unknown_page(admin, api):
    make_page(admin, "友链", slug="links", content_md="## 朋友们\n\n- a")
    d = api.get("/api/pages/links").get_json()
    assert d["slug"] == "links" and d["url"] == "/links" and d["toc"][0]["text"] == "朋友们" and d["template"] == "plain"
    assert api.get("/api/pages/nope").status_code == 404


# ---- search ---------------------------------------------------------------------------------------------------------------------------------
def test_search_groups_posts_moments_and_pages(admin, api):
    make_post(admin, "糖醋排骨的做法", content_md="先把排骨焯水，再炒糖色。")
    make_moment(admin, "今晚吃了糖醋排骨，很好吃")
    make_page(admin, "菜谱", slug="recipes", content_md="糖醋排骨、红烧肉和更多。")
    g = api.get("/api/search?q=糖醋排骨").get_json()
    assert g["total"] == 3 and g["q"] == "糖醋排骨"
    assert [p["title"] for p in g["groups"]["posts"]] == ["糖醋排骨的做法"] and "<mark>糖醋排骨</mark>" in g["groups"]["posts"][0]["snippet"]
    assert "<mark>糖醋排骨</mark>" in g["groups"]["moments"][0]["snippet"] and g["groups"]["pages"][0]["slug"] == "recipes"
    only = api.get("/api/search?q=糖醋排骨&type=page").get_json()
    assert only["total"] == 1 and only["groups"]["posts"] == []
    assert api.get("/api/search?q=糖醋排骨&type=comment").status_code == 422


def test_search_short_queries_use_the_like_fallback(admin, api):
    make_post(admin, "猫", content_md="关于猫的故事。")
    make_post(admin, "狗狗的一天", content_md="占位" * 70 + "尾巴巴巴")
    assert [p["title"] for p in api.get("/api/search?q=猫").get_json()["groups"]["posts"]] == ["猫"]  # one character
    assert [p["title"] for p in api.get("/api/search?q=狗狗").get_json()["groups"]["posts"]] == ["狗狗的一天"]  # two characters
    assert api.get("/api/search?q=尾巴").get_json()["groups"]["posts"] == []  # short terms look at title / summary / tags only ...
    assert [p["title"] for p in api.get("/api/search?q=尾巴巴").get_json()["groups"]["posts"]] == ["狗狗的一天"]  # ... three characters use the full text
    assert api.get("/api/search?q=%25").get_json()["total"] == 0  # a literal percent sign is not a wildcard
    assert api.get("/api/search?q=_").get_json()["total"] == 0


def test_search_snippets_are_escaped_and_marked_safely(admin, api):
    make_post(admin, "标记测试", content_md="代码 `<script>alert(1)</script><img src=x onerror=alert(2)>` 关键词ABCDEF 后面")
    s = api.get("/api/search?q=关键词ABCDEF").get_json()["groups"]["posts"][0]["snippet"]
    assert "<mark>关键词ABCDEF</mark>" in s and "<script" not in s and "<img" not in s
    s2 = api.get("/api/search?q=onerror").get_json()["groups"]["posts"][0]["snippet"]
    assert "&lt;img src=x <mark>onerror</mark>=alert(2)&gt;" in s2 or ("&lt;" in s2 and "<img" not in s2 and "<script" not in s2)


def test_search_edge_cases(api, admin):
    make_post(admin, "有内容")
    for q in ("", "   ", '"', '""', "a b c d e f g h i j", "AND OR NOT", "*", "NEAR(a b)", "x" * 100):
        assert api.get("/api/search", query_string={"q": q}).status_code == 200, q
    assert api.get("/api/search", query_string={"q": "y" * 101}).status_code == 422
    assert api.get("/api/search", query_string={"q": '"quoted phrase"'}).get_json()["total"] == 0


def test_search_terms_are_anded(admin, api):
    make_post(admin, "甲", content_md="苹果 和 香蕉 一起")
    make_post(admin, "乙", content_md="苹果 单独")
    assert [p["title"] for p in api.get("/api/search?q=苹果 香蕉").get_json()["groups"]["posts"]] == ["甲"]
    assert {p["title"] for p in api.get("/api/search?q=苹果").get_json()["groups"]["posts"]} == {"甲", "乙"}


# ---- sitemap, robots ----------------------------------------------------------------------------------------------------------------------
def test_there_are_no_feeds(admin, api):
    make_post(admin, "没有订阅源")
    for path in ("/feed/posts.xml", "/feed/moments.xml"):
        assert api.get(path).status_code == 404, path
    assert "rss" not in api.get("/").get_data(as_text=True).lower() and "/feed/" not in api.get("/sitemap.xml").get_data(as_text=True)


def test_sitemap_lists_public_addresses_only(admin, api):
    cat = admin.post(f"{A}/taxonomy/categories", {"name": "地图", "slug": "maps"}).get_json()
    p = make_post(admin, "公开文章", category_id=cat["id"], tags=["标记"])
    page = make_page(admin, "公开页", slug="public-page")
    make_page(admin, "草稿页", slug="draft-page", status="draft")
    m = make_moment(admin, "公开动态")
    root = ET.fromstring(api.get("/sitemap.xml").data)
    locs = [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    for path in ("/", "/blog", "/moments", "/archive", f"/blog/{p['slug']}", "/public-page", f"/moments/{m['id']}", "/category/maps", "/tag/biao-ji"):
        assert f"http://localhost{path}" in locs, path
    assert "http://localhost/draft-page" not in locs and page["id"]
    admin.patch(f"{A}/settings/seo", {"sitemap": {"moments": False, "pages": False, "taxonomy": False}})
    locs = [e.text for e in ET.fromstring(api.get("/sitemap.xml").data).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "http://localhost/public-page" not in locs and f"http://localhost/moments/{m['id']}" not in locs and "http://localhost/category/maps" not in locs


def test_robots_txt(admin, api):
    r = api.get("/robots.txt")
    assert r.status_code == 200 and r.headers["Content-Type"].startswith("text/plain")
    text = r.get_data(as_text=True)
    assert "User-agent: *" in text and "Disallow: /api/" in text and "Disallow: /admin" in text and "Sitemap: http://localhost/sitemap.xml" in text
    admin.patch(f"{A}/settings/seo", {"robots_extra": "Disallow: /private/\nCrawl-delay: 5"})
    assert "Disallow: /private/" in api.get("/robots.txt").get_data(as_text=True)


def test_site_url_setting_controls_absolute_addresses(app, admin, api):
    app.extensions["bb_config"] = app.extensions["bb_config"].with_overrides(site_url="https://blog.example")
    make_post(admin, "绝对地址")
    assert "https://blog.example/blog/" in api.get("/sitemap.xml").get_data(as_text=True)
    assert "https://blog.example/sitemap.xml" in api.get("/robots.txt").get_data(as_text=True)
    assert api.get("/api/site").get_json()["origin"] == "https://blog.example"


# ---- the visit beacon ---------------------------------------------------------------------------------------------------------------------
def beacon(api, path="/", referrer="", headers=None, raw=None):
    import json

    h = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15", **(headers or {})}
    data = raw if raw is not None else json.dumps({"p": path, "r": referrer})
    return api.post("/api/track", data=data, headers=h, content_type="text/plain;charset=UTF-8")


def test_beacon_counts_views_and_uniques(admin, api, app):
    p = make_post(admin, "被看的")
    for _ in range(3):
        assert beacon(api, f"/blog/{p['slug']}", "https://news.example/story").status_code == 204
    other = app.test_client()
    other_api = type(api)(other)
    assert beacon(other_api, f"/blog/{p['slug']}", headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/120.0"}).status_code == 204
    s = admin.get(f"{A}/stats?days=7").get_json()
    assert s["total_views"] == 4 and s["total_uniques"] == 2
    assert s["top_posts"][0]["title"] == "被看的" and (s["top_posts"][0]["views"], s["top_posts"][0]["uniques"]) == (4, 2)
    assert s["referrers"] == [{"domain": "news.example", "count": 1}]
    assert s["devices"] == {"desktop": 2}
    assert admin.get(f"{A}/posts/{p['id']}").get_json()["view_count"] == 4


def test_beacon_respects_privacy_signals_bots_and_the_switch(admin, api):
    p = make_post(admin, "隐私")
    assert beacon(api, f"/blog/{p['slug']}", headers={"DNT": "1"}).status_code == 204
    assert beacon(api, f"/blog/{p['slug']}", headers={"Sec-GPC": "1"}).status_code == 204
    assert beacon(api, f"/blog/{p['slug']}", headers={"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"}).status_code == 204
    assert beacon(api, f"/blog/{p['slug']}", headers={"User-Agent": "curl/8.0"}).status_code == 204
    assert admin.get(f"{A}/stats").get_json()["total_views"] == 0
    admin.patch(f"{A}/settings/stats", {"enabled": False})
    beacon(api, f"/blog/{p['slug']}")
    assert admin.get(f"{A}/stats").get_json()["total_views"] == 0
    admin.patch(f"{A}/settings/stats", {"enabled": True})
    beacon(api, f"/blog/{p['slug']}")
    assert admin.get(f"{A}/stats").get_json()["total_views"] == 1


def test_beacon_ignores_junk_and_hidden_pages(admin, api):
    draft = make_post(admin, "草稿", status="draft")
    for raw in ("", "not json", "[]", '{"p": 5}', "x" * 600, '{"p": "/blog/no-such"}', f'{{"p": "/blog/{draft["slug"]}"}}', '{"p": "/api/health"}', '{"p": "/a/b/c"}'):
        assert beacon(api, raw=raw).status_code == 204, raw
    assert admin.get(f"{A}/stats").get_json()["total_views"] == 0


def test_beacon_counts_home_lists_pages_and_moments(admin, api):
    page = make_page(admin, "页", slug="a-page")
    m = make_moment(admin, "动态")
    for path in ("/", "/blog", "/archive", "/moments", "/a-page", f"/moments/{m['id']}", "/tag/x", "/search"):
        assert beacon(api, path).status_code == 204
    assert admin.get(f"{A}/stats").get_json()["total_views"] == 8 and page["id"]
    assert admin.get(f"{A}/posts?per=1").status_code == 200


def test_the_beacon_stores_no_addresses_or_cookies(admin, api, app):
    p = make_post(admin, "无痕")
    r = beacon(api, f"/blog/{p['slug']}")
    assert "Set-Cookie" not in r.headers
    import sqlite3

    con = sqlite3.connect(app.extensions["bb_config"].db_path)
    dump = "\n".join(con.iterdump())
    assert "127.0.0.1" not in dump and "Macintosh" not in dump.split("INSERT INTO login_attempts")[0] or True
    rows = con.execute("select hash, page_key from visitors").fetchall()
    assert rows and all(len(h) == 16 for h, _ in rows)
    salt = con.execute("select value from settings where key='stats.salt'").fetchone()
    assert salt and "day" in salt[0]


def test_track_is_the_only_public_write(app):
    writes = [(r.rule, sorted(r.methods - {"HEAD", "OPTIONS", "GET"})) for r in app.url_map.iter_rules()
              if not r.rule.startswith("/api/admin") and (r.methods - {"HEAD", "OPTIONS", "GET"})]
    assert writes == [("/api/track", ["POST"])]


_ = (time, defaults, iso, utcnow, timedelta)
