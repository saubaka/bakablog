from __future__ import annotations

import pytest

from tests.conftest import make_moment, make_post

T = "/api/admin/taxonomy"


# ---- categories ----------------------------------------------------------------------------------------------------------------------
def test_category_crud_and_slugs(admin):
    a = admin.post(f"{T}/categories", {"name": "代码"}).get_json()
    b = admin.post(f"{T}/categories", {"name": "代码"}).get_json()
    assert a["slug"] == "dai-ma" and b["slug"] == "dai-ma-2" and a["sort_order"] < b["sort_order"]
    explicit = admin.post(f"{T}/categories", {"name": "日常", "slug": "daily", "description": "生活", "sticker": "smile", "show_on_shelf": False})
    assert explicit.status_code == 201 and explicit.get_json()["slug"] == "daily" and explicit.get_json()["sticker"] == "smile"
    assert admin.post(f"{T}/categories", {"name": "x", "slug": "daily"}).status_code == 409
    assert admin.post(f"{T}/categories", {"name": "x", "slug": "Bad Slug"}).status_code == 422
    assert admin.post(f"{T}/categories", {"name": "x", "sticker": "not-an-icon"}).status_code == 422
    assert admin.post(f"{T}/categories", {"description": "no name"}).status_code == 422
    c = explicit.get_json()
    u = admin.patch(f"{T}/categories/{c['id']}", {"name": "日常记录", "sticker": None}).get_json()
    assert u["name"] == "日常记录" and u["sticker"] is None and u["description"] == "生活"
    assert [x["slug"] for x in admin.get(f"{T}/categories").get_json()["items"]] == ["dai-ma", "dai-ma-2", "daily"]


def test_category_slug_change_redirects_and_reorder(admin, api):
    a = admin.post(f"{T}/categories", {"name": "甲", "slug": "alpha"}).get_json()
    b = admin.post(f"{T}/categories", {"name": "乙", "slug": "beta"}).get_json()
    make_post(admin, "有分类", category_id=a["id"])
    admin.patch(f"{T}/categories/{a['id']}", {"slug": "alpha-new"})
    r = api.get("/category/alpha")
    assert r.status_code == 301 and r.headers["Location"] == "/category/alpha-new"
    admin.post(f"{T}/categories/reorder", {"ids": [b["id"], a["id"]]})
    assert [x["slug"] for x in admin.get(f"{T}/categories").get_json()["items"]] == ["beta", "alpha-new"]


def test_deleting_a_category_needs_a_new_home_for_its_posts(admin, api):
    a = admin.post(f"{T}/categories", {"name": "要删"}).get_json()
    b = admin.post(f"{T}/categories", {"name": "接收"}).get_json()
    p = make_post(admin, "里面的文章", category_id=a["id"])
    r = admin.delete(f"{T}/categories/{a['id']}")
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "has_posts" and r.get_json()["error"]["post_count"] == 1
    assert admin.delete(f"{T}/categories/{a['id']}?reassign_to={a['id']}").status_code == 422
    assert admin.delete(f"{T}/categories/{a['id']}?reassign_to=424242").status_code == 404
    moved = admin.delete(f"{T}/categories/{a['id']}?reassign_to={b['id']}").get_json()
    assert moved == {"ok": True, "moved": 1}
    assert admin.get(f"/api/admin/posts/{p['id']}").get_json()["category"]["id"] == b["id"]
    empty = admin.post(f"{T}/categories", {"name": "空的"}).get_json()
    assert admin.delete(f"{T}/categories/{empty['id']}").status_code == 200  # nothing to move


def test_category_counts_split_public_and_admin(admin, api):
    a = admin.post(f"{T}/categories", {"name": "统计"}).get_json()
    make_post(admin, "公开", category_id=a["id"])
    make_post(admin, "草稿", category_id=a["id"], status="draft")
    make_post(admin, "私密", category_id=a["id"], status="private")
    row = admin.get(f"{T}/categories").get_json()["items"][0]
    assert row["count"] == 3 and row["public_count"] == 1
    assert [c["count"] for c in api.get("/api/taxonomy").get_json()["categories"]] == [1]


def test_empty_categories_are_not_shown_publicly_and_the_shelf_switch_works(admin, api):
    a = admin.post(f"{T}/categories", {"name": "有文章"}).get_json()
    admin.post(f"{T}/categories", {"name": "没文章"})
    make_post(admin, "x", category_id=a["id"])
    cats = api.get("/api/taxonomy").get_json()["categories"]
    assert [c["name"] for c in cats] == ["有文章"] and cats[0]["show_on_shelf"] is True
    shelf = lambda: next(b for b in api.get("/api/home").get_json()["blocks"] if b["type"] == "shelf")["data"]["categories"]  # noqa: E731
    assert [c["name"] for c in shelf()] == ["有文章"]
    admin.patch(f"{T}/categories/{a['id']}", {"show_on_shelf": False})
    assert shelf() == [] and [c["name"] for c in api.get("/api/taxonomy").get_json()["categories"]] == ["有文章"]


# ---- tags ---------------------------------------------------------------------------------------------------------------------------
def test_tag_listing_create_rename_and_validation(admin):
    make_post(admin, "一", tags=["Flask", "SQLite"])
    make_moment(admin, "m #SQLite")
    items = {t["name"]: t for t in admin.get(f"{T}/tags").get_json()["items"]}
    assert (items["SQLite"]["post_count"], items["SQLite"]["moment_count"], items["SQLite"]["count"]) == (1, 1, 2)
    c = admin.post(f"{T}/tags", {"name": "#新建", "color": "rose", "sticker": "heart"})
    assert c.status_code == 201 and c.get_json()["name"] == "新建" and c.get_json()["color"] == "rose" and c.get_json()["sticker"] == "heart"
    tag = items["Flask"]
    assert admin.patch(f"{T}/tags/{tag['id']}", {"color": "purple"}).status_code == 422
    assert admin.patch(f"{T}/tags/{tag['id']}", {"name": "SQLite"}).status_code == 409
    assert admin.patch(f"{T}/tags/{tag['id']}", {"name": "sqlITE"}).status_code == 409  # names are unique ignoring case
    r = admin.patch(f"{T}/tags/{tag['id']}", {"name": "Flask 框架", "color": "mist", "description": "说明"})
    assert r.get_json()["name"] == "Flask 框架" and r.get_json()["color"] == "mist" and r.get_json()["slug"] == tag["slug"]  # the address stays
    assert admin.post(f"{T}/tags", {"name": "   "}).status_code == 422


def test_renaming_a_tag_updates_search(admin, api):
    p = make_post(admin, "有标签", tags=["旧名字"], content_md="正文")
    tag = admin.get(f"{T}/tags").get_json()["items"][0]
    assert [x["slug"] for x in api.get("/api/search?q=旧名字").get_json()["groups"]["posts"]] == [p["slug"]]
    admin.patch(f"{T}/tags/{tag['id']}", {"name": "新名字"})
    assert api.get("/api/search?q=旧名字").get_json()["groups"]["posts"] == []
    assert [x["slug"] for x in api.get("/api/search?q=新名字").get_json()["groups"]["posts"]] == [p["slug"]]


def test_tag_slug_change_redirects(admin, api):
    make_post(admin, "x", tags=["Python"])
    tag = admin.get(f"{T}/tags").get_json()["items"][0]
    admin.patch(f"{T}/tags/{tag['id']}", {"slug": "py"})
    assert api.get(f"/tag/{tag['slug']}").headers["Location"] == "/tag/py"
    assert api.get("/api/posts?tag=py").status_code == 200 and api.get(f"/api/posts?tag={tag['slug']}").status_code == 404


def test_merge_tags_moves_everything_and_removes_the_sources(admin, api):
    a = make_post(admin, "甲", tags=["js", "前端"])
    b = make_post(admin, "乙", tags=["javascript"])
    c = make_post(admin, "丙", tags=["js", "javascript"])  # carries both: must not end up with the target twice
    m = make_moment(admin, "动态 #js")
    tags = {t["name"]: t for t in admin.get(f"{T}/tags").get_json()["items"]}
    r = admin.post(f"{T}/tags/merge", {"source_ids": [tags["js"]["id"]], "target_id": tags["javascript"]["id"]})
    assert r.status_code == 200 and r.get_json()["moved"] == 2  # post a and the moment; c already had the target
    left = {t["name"]: t for t in admin.get(f"{T}/tags").get_json()["items"]}
    assert set(left) == {"javascript", "前端"} and left["javascript"]["post_count"] == 3 and left["javascript"]["moment_count"] == 1
    assert [t["name"] for t in admin.get(f"/api/admin/posts/{c['id']}").get_json()["tags"]] == ["javascript"]
    assert api.get(f"/tag/{tags['js']['slug']}").headers["Location"] == f"/tag/{tags['javascript']['slug']}"
    assert sorted(p["id"] for p in api.get("/api/posts?tag=" + tags["javascript"]["slug"]).get_json()["items"]) == sorted([a["id"], b["id"], c["id"]])
    assert [x["id"] for x in api.get("/api/moments?tag=" + tags["javascript"]["slug"]).get_json()["items"]] == [m["id"]]
    assert admin.post(f"{T}/tags/merge", {"source_ids": [999], "target_id": tags["javascript"]["id"]}).status_code == 404
    assert admin.post(f"{T}/tags/merge", {"source_ids": [], "target_id": 1}).status_code == 422


def test_delete_and_cleanup_tags(admin):
    p = make_post(admin, "x", tags=["用着", "闲着"])
    admin.patch(f"/api/admin/posts/{p['id']}", {"tags": ["用着"]})
    tags = {t["name"]: t for t in admin.get(f"{T}/tags").get_json()["items"]}
    assert tags["闲着"]["count"] == 0
    assert admin.post(f"{T}/tags/cleanup", {}).get_json() == {"deleted": 1}
    assert [t["name"] for t in admin.get(f"{T}/tags").get_json()["items"]] == ["用着"]
    assert admin.delete(f"{T}/tags/{tags['用着']['id']}").status_code == 200
    assert admin.get(f"/api/admin/posts/{p['id']}").get_json()["tags"] == []
    assert admin.delete(f"{T}/tags/{tags['用着']['id']}").status_code == 404


def test_public_tag_counts_only_include_public_content(admin, api):
    make_post(admin, "公开", tags=["计数"])
    make_post(admin, "草稿", tags=["计数"], status="draft")
    make_moment(admin, "私密 #计数", visibility="private")
    make_moment(admin, "公开 #计数")
    pub = api.get("/api/taxonomy").get_json()["tags"][0]
    assert (pub["name"], pub["count"], pub["moment_count"]) == ("计数", 1, 1)
    adm = admin.get(f"{T}/tags").get_json()["items"][0]
    assert (adm["post_count"], adm["moment_count"]) == (2, 2)


# ---- series -------------------------------------------------------------------------------------------------------------------------
def test_series_crud_order_and_public_page(admin, api):
    s = admin.post(f"{T}/series", {"title": "把博客做成自己喜欢的样子", "description": "连载"}).get_json()
    assert s["status"] == "ongoing" and s["slug"].startswith("ba-bo-ke")
    a = make_post(admin, "第一篇", series_id=s["id"], published_at="2026-01-03T00:00:00Z")
    b = make_post(admin, "第二篇", series_id=s["id"], published_at="2026-01-02T00:00:00Z")  # earlier date, later order
    c = make_post(admin, "第三篇", series_id=s["id"], published_at="2026-01-01T00:00:00Z")
    assert [x["series_order"] for x in (a, b, c)] == [1, 2, 3]
    listing = api.get(f"/api/posts?series={s['slug']}").get_json()
    assert [p["title"] for p in listing["items"]] == ["第一篇", "第二篇", "第三篇"]  # a series reads in its own order, not by date
    assert listing["filters"]["series"]["title"] == s["title"]
    r = admin.put(f"{T}/series/{s['id']}/order", {"post_ids": [c["id"], a["id"]]})
    assert r.status_code == 200
    assert [p["id"] for p in admin.get(f"{T}/series/{s['id']}/posts").get_json()["items"]] == [c["id"], a["id"], b["id"]]
    assert admin.put(f"{T}/series/{s['id']}/order", {"post_ids": [c["id"], 424242]}).status_code == 422
    nav = api.get(f"/api/posts/{a['slug']}").get_json()["series_nav"]
    assert nav["total"] == 3 and nav["index"] == 2 and [i["slug"] for i in nav["items"]] == [c["slug"], a["slug"], b["slug"]]
    assert [i["current"] for i in nav["items"]] == [False, True, False] and nav["status"] == "ongoing"
    u = admin.patch(f"{T}/series/{s['id']}", {"status": "finished", "title": "完结了"}).get_json()
    assert u["status"] == "finished" and u["title"] == "完结了"
    assert admin.patch(f"{T}/series/{s['id']}", {"status": "paused"}).status_code == 422
    assert admin.get(f"{T}/series").get_json()["items"][0]["count"] == 3
    assert admin.delete(f"{T}/series/{s['id']}").get_json() == {"ok": True, "posts": 3}
    assert admin.get(f"/api/admin/posts/{a['id']}").get_json()["series_id"] is None


def test_series_with_cover_and_validation(admin, png):
    mid = admin.upload("/api/admin/media", png(100, 100)).get_json()["id"]
    s = admin.post(f"{T}/series", {"title": "有封面", "cover_media_id": mid}).get_json()
    assert s["cover"]["id"] == mid
    assert admin.post(f"{T}/series", {"description": "x"}).status_code == 422
    assert admin.post(f"{T}/series", {"title": "x", "slug": "BAD"}).status_code == 422
    cleared = admin.patch(f"{T}/series/{s['id']}", {"cover_media_id": None}).get_json()
    assert cleared["cover"] is None
    p = admin.post("/api/admin/posts", {"title": "x", "series_id": 4242})
    assert p.status_code == 404


def test_moving_a_post_between_series_renumbers(admin):
    s1 = admin.post(f"{T}/series", {"title": "一"}).get_json()
    s2 = admin.post(f"{T}/series", {"title": "二"}).get_json()
    a = make_post(admin, "a", series_id=s1["id"])
    b = make_post(admin, "b", series_id=s1["id"])
    moved = admin.patch(f"/api/admin/posts/{a['id']}", {"series_id": s2["id"]}).get_json()
    assert moved["series_order"] == 1
    explicit = admin.patch(f"/api/admin/posts/{b['id']}", {"series_order": 7}).get_json()
    assert explicit["series_order"] == 7
    gone = admin.patch(f"/api/admin/posts/{b['id']}", {"series_id": None}).get_json()
    assert gone["series_id"] is None and gone["series_order"] is None


@pytest.mark.parametrize("path", ["categories", "tags", "series"])
def test_taxonomy_needs_admin(api, path):
    assert api.get(f"{T}/{path}").status_code == 401
