from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import Post, Redirect, Revision
from app.services import posts as posts_service
from app.timeutil import iso, utcnow
from tests.conftest import make_post

P = "/api/admin/posts"


def public_slugs(api, path="/api/posts"):
    return [p["slug"] for p in api.get(path).get_json()["items"]]


# ---- create -------------------------------------------------------------------------------------------------------------------------
def test_create_renders_markdown_and_fills_the_derived_fields(admin):
    p = make_post(admin, "SQLite 备份：我差点把自己的数据弄丢", content_md="## 事情是这样的\n\n先说结论：**别用 cp**。\n\n### 细节\n\n正文。")
    assert p["slug"].startswith("sqlite-bei-fen-wo-cha-dian")
    assert p["status"] == "published" and p["published_at"] and p["scheduled"] is False
    assert [t["text"] for t in p["toc"]] == ["事情是这样的", "细节"]
    assert p["summary"].startswith("先说结论：别用 cp。") and p["summary_auto"] is True
    assert p["reading_minutes"] == 1 and p["word_count"] > 10
    assert p["content_md"].startswith("## 事情是这样的")
    assert p["tags"] == [] and p["category"] is None and p["cover"] is None


def test_slugs_are_unique_and_explicit_ones_are_validated(admin):
    a = make_post(admin, "同名文章")
    b = make_post(admin, "同名文章")
    assert a["slug"] == "tong-ming-wen-zhang" and b["slug"] == "tong-ming-wen-zhang-2"
    ok = make_post(admin, "手写别名", slug="my-own-slug")
    assert ok["slug"] == "my-own-slug"
    taken = admin.post(P, {"title": "x", "slug": "my-own-slug"})
    assert taken.status_code == 409 and taken.get_json()["error"]["fields"] == {"slug": "已占用"}
    for bad in ("Has Caps", "中文", "-lead", "trail-", "a--b", "x" * 81):
        assert admin.post(P, {"title": "x", "slug": bad}).status_code in (422,), bad


def test_title_is_required_and_unknown_fields_are_refused(admin):
    assert admin.post(P, {"content_md": "x"}).status_code == 422
    r = admin.post(P, {"title": "  "})
    assert r.status_code == 422 and "title" in r.get_json()["error"]["fields"]
    r = admin.post(P, {"title": "x", "views": 99, "comments_enabled": True})
    assert r.status_code == 422 and r.get_json()["error"]["fields"]["views"] == "不认识这个字段"
    r = admin.post(P, {"title": "x", "status": "weird"})
    assert r.status_code == 422 and "status" in r.get_json()["error"]["fields"]
    assert admin.post(P, {"title": "x" * 201}).status_code == 422
    assert admin.post(P, {"title": "x", "cover_focus_x": 150}).status_code == 422
    assert admin.post(P, {"title": "x", "category_id": 4242}).status_code == 404
    assert admin.post(P, {"title": "x", "cover_media_id": 4242}).status_code == 422


def test_summary_is_automatic_until_the_author_writes_one(admin):
    p = make_post(admin, "摘要", content_md="第一段内容。\n\n第二段内容。")
    assert p["summary"] == "第一段内容。 第二段内容。"
    p = admin.patch(f"{P}/{p['id']}", {"summary": "我自己写的摘要"}).get_json()
    assert p["summary"] == "我自己写的摘要" and p["summary_auto"] is False
    p = admin.patch(f"{P}/{p['id']}", {"content_md": "换了正文。"}).get_json()
    assert p["summary"] == "我自己写的摘要"  # a written summary is never overwritten
    p = admin.patch(f"{P}/{p['id']}", {"summary": ""}).get_json()
    assert p["summary"] == "换了正文。" and p["summary_auto"] is True


def test_tags_are_created_on_the_fly_and_match_case_insensitively(admin):
    a = make_post(admin, "一", tags=["Flask", "#备份", " SQLite "])
    assert [t["name"] for t in a["tags"]] == ["Flask", "SQLite", "备份"]
    b = make_post(admin, "二", tags=["flask", "FLASK", "新标签"])
    assert [t["name"] for t in b["tags"]] == ["Flask", "新标签"]  # same tag, no duplicate
    tags = admin.get("/api/admin/taxonomy/tags").get_json()["items"]
    assert sorted(t["name"] for t in tags) == ["Flask", "SQLite", "备份", "新标签"]
    assert all(t["color"] in ("sky", "rose", "mist", "white") for t in tags)
    c = admin.patch(f"{P}/{a['id']}", {"tags": ["Flask"]}).get_json()
    assert [t["name"] for t in c["tags"]] == ["Flask"]


# ---- who can see what ------------------------------------------------------------------------------------------------------------------
def test_visibility_matrix(admin, api):
    pub = make_post(admin, "公开")
    draft = make_post(admin, "草稿", status="draft")
    private = make_post(admin, "私密", status="private")
    unlisted = make_post(admin, "仅链接", status="unlisted")
    future = make_post(admin, "定时", published_at=iso(utcnow() + timedelta(days=3)))
    trashed = make_post(admin, "回收站里")
    admin.delete(f"{P}/{trashed['id']}")
    assert future["scheduled"] is True

    assert public_slugs(api) == [pub["slug"]]
    for p in (draft, private, future, trashed):
        assert api.get(f"/api/posts/{p['slug']}").status_code == 404, p["title"]
        assert api.get(f"/blog/{p['slug']}").status_code == 404
    unl = api.get(f"/api/posts/{unlisted['slug']}")
    assert unl.status_code == 200 and unl.get_json()["seo"]["noindex"] is True
    assert api.get(f"/blog/{unlisted['slug']}").status_code == 200
    assert 'content="noindex,nofollow"' in api.get(f"/blog/{unlisted['slug']}").get_data(as_text=True)

    # nothing but the one public post shows up in the other public places
    assert [p["slug"] for y in api.get("/api/archive").get_json()["years"] for m in y["months"] for p in m["posts"]] == [pub["slug"]]
    feed = api.get("/feed/posts.xml").get_data(as_text=True)
    sitemap = api.get("/sitemap.xml").get_data(as_text=True)
    for hidden in (draft, private, unlisted, future, trashed):
        assert hidden["slug"] not in feed and hidden["slug"] not in sitemap
    assert pub["slug"] in feed and pub["slug"] in sitemap
    for title in ("草稿", "私密", "仅链接", "定时", "回收站里"):
        assert api.get(f"/api/search?q={title}正文").get_json()["groups"]["posts"] == []


def test_a_scheduled_post_appears_when_its_time_comes(admin, api, app):
    p = make_post(admin, "定时发布", published_at=iso(utcnow() + timedelta(hours=2)))
    assert api.get(f"/api/posts/{p['slug']}").status_code == 404
    with session_scope(app) as s:
        s.get(Post, p["id"]).published_at = utcnow() - timedelta(seconds=1)
    assert api.get(f"/api/posts/{p['slug']}").status_code == 200
    assert public_slugs(api) == [p["slug"]]


def test_status_and_date_rules(admin):
    d = make_post(admin, "草稿", status="draft")
    assert d["published_at"] is None
    pub = admin.patch(f"{P}/{d['id']}", {"status": "published"}).get_json()
    assert pub["published_at"]
    back = admin.patch(f"{P}/{d['id']}", {"status": "draft"}).get_json()
    assert back["published_at"] == pub["published_at"]  # un-publishing keeps the original date
    old = admin.patch(f"{P}/{d['id']}", {"status": "published", "published_at": "2020-01-02T03:04:05Z"}).get_json()
    assert old["published_at"] == "2020-01-02T03:04:05Z"


# ---- slug changes keep old links alive -----------------------------------------------------------------------------------------------------
def test_changing_a_slug_registers_a_301_for_pages_and_a_moved_answer_for_the_api(admin, api, app):
    p = make_post(admin, "改名", slug="old-name")
    r = admin.patch(f"{P}/{p['id']}", {"slug": "new-name"})
    assert r.status_code == 200 and r.get_json()["slug"] == "new-name"
    moved = api.get("/api/posts/old-name")
    assert moved.status_code == 404 and moved.get_json()["error"]["code"] == "moved" and moved.get_json()["error"]["location"] == "/blog/new-name"
    html = api.get("/blog/old-name")
    assert html.status_code == 301 and html.headers["Location"] == "/blog/new-name"
    with session_scope(app) as s:
        row = s.scalar(select(Redirect).where(Redirect.source == "/blog/old-name"))
        assert row.hits == 1 and row.auto is True
    # renaming again keeps the first redirect pointing at the final address
    admin.patch(f"{P}/{p['id']}", {"slug": "newest"})
    assert api.get("/blog/old-name").headers["Location"] == "/blog/newest"
    assert api.get("/blog/new-name").headers["Location"] == "/blog/newest"
    # going back removes the redirect that would hide the post
    admin.patch(f"{P}/{p['id']}", {"slug": "old-name"})
    assert api.get("/blog/old-name").status_code == 200


def test_a_draft_that_was_never_public_leaves_no_redirect(admin, app):
    p = make_post(admin, "草稿", status="draft", slug="draft-a")
    admin.patch(f"{P}/{p['id']}", {"slug": "draft-b"})
    with session_scope(app) as s:
        assert s.scalar(select(Redirect)) is None


# ---- editor features -------------------------------------------------------------------------------------------------------------------------
def test_revisions_list_restore_and_keep_the_last_twenty(admin):
    p = make_post(admin, "版本", content_md="v0")
    for i in range(1, 25):
        admin.patch(f"{P}/{p['id']}", {"content_md": f"v{i}"})
    items = admin.get(f"{P}/{p['id']}/revisions").get_json()["items"]
    assert len(items) == 20
    newest = admin.get(f"{P}/{p['id']}/revisions/{items[0]['id']}").get_json()
    assert newest["snapshot"]["content_md"] == "v24"
    older = admin.get(f"{P}/{p['id']}/revisions/{items[5]['id']}").get_json()
    assert older["snapshot"]["content_md"] == "v19"
    restored = admin.post(f"{P}/{p['id']}/revisions/{items[5]['id']}/restore", {}).get_json()
    assert restored["content_md"] == "v19" and "v19" in restored["summary"]
    assert admin.get(f"{P}/{p['id']}/revisions/999999").status_code == 404


def test_saving_without_changes_does_not_add_a_revision(admin):
    p = make_post(admin, "不变", content_md="same")
    admin.patch(f"{P}/{p['id']}", {"content_md": "same"})
    admin.patch(f"{P}/{p['id']}", {"content_md": "same"})
    assert len(admin.get(f"{P}/{p['id']}/revisions").get_json()["items"]) == 1


def test_autosave_keeps_text_aside_until_the_next_real_save(admin, app):
    p = make_post(admin, "自动保存", content_md="已发布的正文")
    assert admin.get(f"{P}/{p['id']}").get_json()["autosave"] is None
    r = admin.put(f"{P}/{p['id']}/autosave", {"content_md": "还没保存的新正文", "title": "新标题"})
    assert r.status_code == 200
    after = admin.get(f"{P}/{p['id']}").get_json()
    assert after["content_md"] == "已发布的正文" and after["title"] == "自动保存"  # the post itself is untouched
    assert after["autosave"]["snapshot"]["content_md"] == "还没保存的新正文"
    admin.put(f"{P}/{p['id']}/autosave", {"content_md": "再改一次"})
    with session_scope(app) as s:
        assert len(list(s.scalars(select(Revision).where(Revision.kind == "autosave")))) == 1
    admin.patch(f"{P}/{p['id']}", {"content_md": "正式保存"})
    assert admin.get(f"{P}/{p['id']}").get_json()["autosave"] is None


def test_preview_links_show_drafts_until_they_expire(admin, api, app):
    draft = make_post(admin, "未发布的草稿", status="draft")
    other = make_post(admin, "另一篇草稿", status="draft")
    t = admin.post(f"{P}/{draft['id']}/preview-token", {}).get_json()
    assert t["path"] == f"/blog/{draft['slug']}?preview={t['token']}" and t["url"].endswith(t["path"]) and t["expires_in_days"] == 7
    r = api.get(f"/api/posts/{draft['slug']}?preview={t['token']}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["preview"] is True and body["seo"]["noindex"] is True and body["status"] == "draft"
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Robots-Tag"] == "noindex"
    page = api.get(t["path"])
    assert page.status_code == 200 and "noindex" in page.get_data(as_text=True) and page.headers["Cache-Control"] == "no-store"
    # the token is bound to its post and must be genuine
    assert api.get(f"/api/posts/{other['slug']}?preview={t['token']}").status_code == 404
    assert api.get(f"/api/posts/{draft['slug']}?preview={t['token']}x").status_code == 404
    assert api.get(f"/api/posts/{draft['slug']}?preview=garbage").status_code == 404
    with app.app_context():
        assert posts_service.verify_preview_token(t["token"]) == draft["id"]
        assert posts_service.verify_preview_token(t["token"], max_age=-1) is None  # expired


def test_duplicate_makes_a_private_draft_copy(admin):
    p = make_post(admin, "原文", tags=["a", "b"], content_md="内容", pinned=True)
    c = admin.post(f"{P}/{p['id']}/duplicate", {}).get_json()
    assert c["id"] != p["id"] and c["title"] == "原文（副本）" and c["status"] == "draft" and c["published_at"] is None
    assert [t["name"] for t in c["tags"]] == ["a", "b"] and c["content_md"] == "内容" and c["pinned"] is False


def test_concurrent_edit_is_detected(admin):
    p = make_post(admin, "冲突")
    ok = admin.patch(f"{P}/{p['id']}", {"title": "甲改", "expected_updated_at": p["updated_at"]})
    assert ok.status_code == 200
    stale = admin.patch(f"{P}/{p['id']}", {"title": "乙改", "expected_updated_at": p["updated_at"]})
    assert stale.status_code == 409 and stale.get_json()["error"]["code"] == "conflict"
    assert admin.get(f"{P}/{p['id']}").get_json()["title"] == "甲改"


# ---- trash ----------------------------------------------------------------------------------------------------------------------------------
def test_trash_restore_purge(admin, api):
    p = make_post(admin, "要删的")
    assert admin.delete(f"{P}/{p['id']}/purge").status_code == 409  # must be in the trash first
    assert admin.delete(f"{P}/{p['id']}").status_code == 200
    assert api.get(f"/api/posts/{p['slug']}").status_code == 404
    assert admin.get(f"{P}?status=trashed").get_json()["total"] == 1 and admin.get(P).get_json()["total"] == 0
    assert admin.post(f"{P}/{p['id']}/restore", {}).status_code == 200
    assert api.get(f"/api/posts/{p['slug']}").status_code == 200
    admin.delete(f"{P}/{p['id']}")
    assert admin.delete(f"{P}/{p['id']}/purge").status_code == 200
    assert admin.get(f"{P}/{p['id']}").status_code == 404


# ---- list, filters, batch ----------------------------------------------------------------------------------------------------------------------
def test_list_tabs_filters_sorting_and_paging(admin):
    cat = admin.post("/api/admin/taxonomy/categories", {"name": "代码"}).get_json()
    series = admin.post("/api/admin/taxonomy/series", {"title": "系列甲"}).get_json()
    a = make_post(admin, "苹果", tags=["水果"], category_id=cat["id"], published_at="2026-01-01T00:00:00Z")
    b = make_post(admin, "香蕉", tags=["水果", "黄色"], series_id=series["id"], published_at="2026-02-01T00:00:00Z")
    c = make_post(admin, "草稿一", status="draft")
    d = make_post(admin, "定时一", published_at=iso(utcnow() + timedelta(days=2)))
    e = make_post(admin, "私密一", status="private")
    listing = admin.get(P).get_json()
    assert listing["counts"] == {"all": 5, "draft": 1, "published": 2, "scheduled": 1, "unlisted": 0, "private": 1, "trashed": 0}
    ids = lambda q: [x["id"] for x in admin.get(f"{P}?{q}").get_json()["items"]]  # noqa: E731
    assert ids("status=draft") == [c["id"]] and ids("status=scheduled") == [d["id"]] and ids("status=private") == [e["id"]]
    assert set(ids("status=published")) == {a["id"], b["id"]}
    assert ids(f"category={cat['id']}") == [a["id"]] and ids(f"series={series['id']}") == [b["id"]]
    assert set(ids("tag=shui-guo")) == {a["id"], b["id"]} and ids("tag=huang-se") == [b["id"]]
    assert ids("q=香蕉") == [b["id"]] and ids("q=不存在的词") == []
    assert ids("status=published&sort=published")[0] == b["id"] and ids("status=published&sort=title")[0] in (a["id"], b["id"])
    assert ids("status=published&from=2026-01-15T00:00:00Z") == [b["id"]]
    assert ids("status=published&to=2026-01-15T00:00:00Z") == [a["id"]]
    page2 = admin.get(f"{P}?per=2&page=2").get_json()
    assert page2["page"] == 2 and page2["pages"] == 3 and len(page2["items"]) == 2
    assert admin.get(f"{P}?status=nonsense").status_code == 422
    row = admin.get(f"{P}?status=scheduled").get_json()["items"][0]
    assert row["scheduled"] is True and row["status"] == "published"


def test_batch_regenerate_summary_replaces_a_hand_written_one_with_the_text_lead(admin):
    p = make_post(admin, "摘要", content_md="第一段正文，会被截成摘要。\n\n第二段。", summary="手写的摘要", status="draft")
    assert admin.get(f"{P}/{p['id']}").get_json()["summary"] == "手写的摘要"
    r = admin.post(f"{P}/batch", {"ids": [p["id"]], "action": "regenerate_summary"}).get_json()
    assert r["done"] == 1
    got = admin.get(f"{P}/{p['id']}").get_json()
    assert got["summary"].startswith("第一段正文") and got["summary_auto"] is True


def test_batch_actions(admin, api):
    cat = admin.post("/api/admin/taxonomy/categories", {"name": "批量"}).get_json()
    a = make_post(admin, "甲", status="draft", tags=["x"])
    b = make_post(admin, "乙", status="draft")
    ids = [a["id"], b["id"], 424242]
    r = admin.post(f"{P}/batch", {"ids": ids, "action": "publish"}).get_json()
    assert r == {"done": 2, "missing": [424242]}
    assert len(public_slugs(api)) == 2
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "category", "category_id": cat["id"]})
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "add_tags", "tags": ["新", "旧"]})
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "remove_tags", "tags": ["旧", "x"]})
    got = {p["id"]: p for p in admin.get(P).get_json()["items"]}
    assert all(p["category"]["id"] == cat["id"] for p in got.values())
    assert [t["name"] for t in got[a["id"]]["tags"]] == ["新"]
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "pin"})
    admin.post(f"{P}/batch", {"ids": ids[:1], "action": "feature"})
    assert api.get("/api/posts").get_json()["items"][0]["pinned"] is True
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "draft"})
    assert public_slugs(api) == []
    admin.post(f"{P}/batch", {"ids": ids[:2], "action": "trash"})
    assert admin.get(f"{P}?status=trashed").get_json()["total"] == 2
    assert admin.post(f"{P}/batch", {"ids": ids[:2], "action": "purge"}).get_json()["done"] == 2
    assert admin.post(f"{P}/batch", {"ids": [], "action": "pin"}).status_code == 422
    assert admin.post(f"{P}/batch", {"ids": [1], "action": "explode"}).status_code == 422
    assert admin.post(f"{P}/batch", {"ids": [1], "action": "add_tags"}).status_code == 422


# ---- the side effects of saving --------------------------------------------------------------------------------------------------------------
def test_search_index_follows_the_post(admin, api):
    p = make_post(admin, "索引测试", content_md="独一无二的关键词ZQXJ在正文里", tags=["标签词语"])
    hit = lambda q: [x["slug"] for x in api.get(f"/api/search?q={q}").get_json()["groups"]["posts"]]  # noqa: E731
    assert hit("ZQXJ") == [p["slug"]] and hit("标签词语") == [p["slug"]] and hit("索引测试") == [p["slug"]]
    admin.patch(f"{P}/{p['id']}", {"content_md": "全新的内容WWWK"})
    assert hit("ZQXJ") == [] and hit("WWWK") == [p["slug"]]
    admin.patch(f"{P}/{p['id']}", {"status": "draft"})
    assert hit("WWWK") == []
    admin.patch(f"{P}/{p['id']}", {"status": "published"})
    assert hit("WWWK") == [p["slug"]]
    admin.delete(f"{P}/{p['id']}")
    assert hit("WWWK") == []
    admin.post(f"{P}/{p['id']}/restore", {})
    assert hit("WWWK") == [p["slug"]]


def test_every_content_change_bumps_the_site_version(admin, api):
    before = api.get("/api/health").get_json()["site_version"]
    p = make_post(admin, "版本号")
    mid = api.get("/api/health").get_json()["site_version"]
    admin.patch(f"{P}/{p['id']}", {"title": "改"})
    after = api.get("/api/health").get_json()["site_version"]
    assert before < mid < after


def test_audit_log_records_post_actions(admin):
    p = make_post(admin, "留痕")
    admin.patch(f"{P}/{p['id']}", {"title": "留痕2"})
    admin.delete(f"{P}/{p['id']}")
    actions = [a["action"] for a in admin.get("/api/admin/audit?target_type=post").get_json()["items"]]
    assert actions[:3] == ["post.trash", "post.update", "post.create"]


@pytest.mark.parametrize("field,value", [("pinned", True), ("featured", True), ("card_style", "quote"), ("show_toc", False), ("show_author_card", True),
                                          ("cover_alt", "封面说明"), ("seo_title", "SEO 标题"), ("seo_description", "SEO 描述"),
                                          ("canonical_url", "https://example.com/original")])
def test_option_fields_round_trip(admin, field, value):
    p = make_post(admin, "选项")
    updated = admin.patch(f"{P}/{p['id']}", {field: value}).get_json()
    shown = updated.get(field, updated.get("seo", {}).get(field.removeprefix("seo_")) if field.startswith("seo_") else None)
    if field == "canonical_url":
        shown = updated["seo"]["canonical_url"]
    assert shown == value


def test_canonical_must_be_a_full_link(admin):
    p = make_post(admin, "c")
    assert admin.patch(f"{P}/{p['id']}", {"canonical_url": "/relative"}).status_code == 422
