"""Markdown export / import: the front matter dialect, a round trip through this site's own export, Hexo / Hugo folders, and hostile archives."""
from __future__ import annotations

import io
import json
import shutil
import zipfile

from app import create_app
from app.db import session_scope
from app.services import auth, transfer
from tests.conftest import OWNER, Api, make_config, make_moment, make_page, make_post

S = "/api/admin/system"


def zip_of(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def do_import(admin, files: dict[str, bytes | str], **fields):
    return admin.upload(f"{S}/import", zip_of(files), filename="in.zip", mimetype="application/zip", fields=fields)


def export(admin) -> zipfile.ZipFile:
    r = admin.get(f"{S}/export")
    assert r.status_code == 200 and r.mimetype == "application/zip" and "attachment" in r.headers["Content-Disposition"]
    return zipfile.ZipFile(io.BytesIO(r.data))


# ---- the front matter dialect ---------------------------------------------------------------------------------------------------
def test_front_matter_round_trips_strings_lists_and_flags():
    meta = {"title": '含 "引号" 和: 冒号 # 井号', "tags": ["a b", "中文", 'q"x'], "pinned": True, "n": 3, "empty": "", "none": None, "summary": "第一行\n第二行"}
    text = transfer.dump_front_matter(meta) + "\n\n正文\n"
    parsed, body = transfer.split_front_matter(text)
    assert parsed == {"title": meta["title"], "tags": meta["tags"], "pinned": True, "n": 3, "summary": "第一行\n第二行"}
    assert body.strip() == "正文"


def test_yaml_as_hexo_and_jekyll_write_it():
    text = """---
title: Hello World   # a comment
date: 2026-10-23 08:30:00
tags:
  - Flask
  - "Vue 3"
categories:
- Dev
draft: false
description: >
  folded text
  continues here
excerpt: |
  line one
  line two
cover: 'it''s.png'
empty:
inline: [a, "b, c", d]
---
# not a heading to strip here
Body
"""
    meta, body = transfer.split_front_matter(text)
    assert meta["title"] == "Hello World" and meta["date"] == "2026-10-23 08:30:00" and meta["tags"] == ["Flask", "Vue 3"] and meta["categories"] == ["Dev"]
    assert meta["draft"] is False and meta["description"] == "folded text continues here" and meta["excerpt"] == "line one\nline two"
    assert meta["cover"] == "it's.png" and meta["empty"] is None and meta["inline"] == ["a", "b, c", "d"]
    assert body.startswith("# not a heading")


def test_toml_as_hugo_writes_it_and_broken_front_matter_does_not_stop_the_file():
    meta, body = transfer.split_front_matter('+++\ntitle = "T"\ntags = ["x", "y"]\ndraft = true\n+++\ntext')
    assert meta == {"title": "T", "tags": ["x", "y"], "draft": True} and body == "text"
    warnings: list[str] = []
    meta, body = transfer.split_front_matter("+++\ntitle = \n+++\ntext", warnings, "a.md")
    assert meta == {} and body == "text" and warnings and "a.md" in warnings[0]
    assert transfer.split_front_matter("no front matter here") == ({}, "no front matter here")
    assert transfer.split_front_matter("---\nnever closed") == ({}, "---\nnever closed")
    assert transfer.split_front_matter("﻿---\r\ntitle: bom\r\n---\r\nx")[0] == {"title": "bom"}


# ---- export -----------------------------------------------------------------------------------------------------------------
def test_export_has_the_three_kinds_the_pictures_and_a_manifest(admin, png):
    pic = admin.upload("/api/admin/media", png(), filename="云.png").get_json()
    cat = admin.post("/api/admin/taxonomy/categories", {"name": "代码"}).get_json()
    make_post(admin, "有图的文章", content_md=f"开头\n\n![一朵云](media:{pic['id']})\n", category_id=cat["id"], tags=["x", "y"], cover_media_id=pic["id"], summary="手写摘要", pinned=True)
    make_post(admin, "草稿", status="draft")
    gone = make_post(admin, "已删除")
    admin.delete(f"/api/admin/posts/{gone['id']}")
    make_page(admin, "关于", slug="about")
    make_moment(admin, "一条动态", tags=["日常"], mood="happy", media=[{"media_id": pic["id"], "alt": "云"}])
    z = export(admin)
    names = z.namelist()
    assert "README.md" in names and "media/manifest.json" in names
    assert sum(n.startswith("posts/") for n in names) == 2 and "pages/about.md" in names and sum(n.startswith("moments/") for n in names) == 1
    assert not any("yi-shan-chu" in n for n in names), "a trashed post must not be exported"
    post_file = next(n for n in names if n.startswith("posts/") and "you-tu" in n)
    text = z.read(post_file).decode()
    meta, body = transfer.split_front_matter(text)
    assert meta["title"] == "有图的文章" and meta["category"] == "代码" and meta["tags"] == ["x", "y"] and meta["pinned"] is True and meta["summary"] == "手写摘要"
    assert meta["status"] == "published" and meta["date"].endswith("Z")
    assert f"../media/{pic['id']}-" in body and "media:" not in body and meta["cover"].startswith("../media/")
    manifest = json.loads(z.read("media/manifest.json"))
    assert len(manifest) == 1 and manifest[0]["filename"] == "云.png" and z.read(manifest[0]["file"])[:4] == b"RIFF"
    moment_meta, moment_body = transfer.split_front_matter(z.read(next(n for n in names if n.startswith("moments/"))).decode())
    assert moment_meta["mood"] == "happy" and moment_meta["tags"] == ["日常"] and moment_meta["images"] and moment_body.strip() == "一条动态"
    actions = [a["action"] for a in admin.get("/api/admin/audit").get_json()["items"]]
    assert "system.export" in actions


def test_export_requires_a_login(api):
    assert api.get(f"{S}/export").status_code == 401
    assert api.upload(f"{S}/import", b"x").status_code == 401


# ---- round trip -------------------------------------------------------------------------------------------------------------
def test_a_site_exported_and_imported_into_a_fresh_one_comes_back(admin, png, tmp_path, template_db):
    pic = admin.upload("/api/admin/media", png(), filename="a.png", fields={"alt": "云"}).get_json()
    cat = admin.post("/api/admin/taxonomy/categories", {"name": "代码"}).get_json()
    ser = admin.post("/api/admin/taxonomy/series", {"title": "系列甲"}).get_json()
    make_post(admin, "第一篇", content_md=f"## 小标题\n\n正文 ![云](media:{pic['id']})\n", category_id=cat["id"], series_id=ser["id"], series_order=3,
              tags=["x", "y"], cover_media_id=pic["id"], summary="手写", featured=True, published_at="2026-01-02T03:04:05Z")
    make_page(admin, "关于", slug="about", template="wide")
    make_moment(admin, "晴天 #天气", mood="happy", media=[{"media_id": pic["id"], "alt": "云"}], published_at="2026-02-03T04:05:06Z")
    raw = admin.get(f"{S}/export").data

    cfg2 = make_config(tmp_path / "second")
    cfg2.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg2.db_path)
    app2 = create_app(cfg2)
    with session_scope(app2) as s:
        auth.create_owner(s, OWNER["username"], OWNER["password"], cfg2)
    try:
        other = Api(app2.test_client())
        other.csrf = other.post("/api/admin/auth/login", {"username": OWNER["username"], "password": OWNER["password"]}).get_json()["csrf_token"]
        r = other.upload(f"{S}/import", raw, filename="x.zip", mimetype="application/zip", fields={"status": "keep"})
        out = r.get_json()
        assert r.status_code == 200 and (out["posts"], out["pages"], out["moments"], out["media"]) == (1, 1, 1, 1), out
        post = other.get("/api/admin/posts").get_json()["items"][0]
        assert post["title"] == "第一篇" and post["status"] == "published" and post["category"]["name"] == "代码" and post["series"]["title"] == "系列甲" and post["series"]["order"] == 3
        assert [t["name"] for t in post["tags"]] == ["x", "y"] and post["featured"] is True and post["published_at"] == "2026-01-02T03:04:05Z" and post["cover"] is not None
        detail = other.get(f"/api/admin/posts/{post['id']}").get_json()
        assert "![云](media:" in detail["content_md"] and detail["summary"] == "手写" and detail["summary_auto"] is False
        page = other.get("/api/admin/pages").get_json()["items"][0]
        assert page["slug"] == "about" and page["template"] == "wide"
        moment = other.get("/api/admin/moments").get_json()["items"][0]
        assert moment["markdown"] == "晴天" and moment["mood"]["id"] == "happy" and [t["name"] for t in moment["tags"]] == ["天气"] and len(moment["media"]) == 1
        assert moment["published_at"] == "2026-02-03T04:05:06Z" and moment["visibility"] == "public"
        assert other.get(f"/api/posts/{post['slug']}").status_code == 200
    finally:
        app2.extensions["bb_db"].dispose()


def test_import_without_keep_makes_drafts_and_private_moments(admin):
    z = {"posts/a.md": "---\ntitle: A\nstatus: published\n---\nbody", "moments/2026-01-01-1.md": "---\nvisibility: public\n---\nhello"}
    out = do_import(admin, z).get_json()
    assert out["posts"] == 1 and out["moments"] == 1
    assert admin.get("/api/admin/posts").get_json()["items"][0]["status"] == "draft"
    assert admin.get("/api/admin/moments").get_json()["items"][0]["visibility"] == "private"
    assert admin.get("/api/posts").get_json()["total"] == 0


# ---- other people's folders -----------------------------------------------------------------------------------------------
def test_hexo_and_jekyll_style_files(admin, png):
    files = {
        "source/_posts/2024-05-06-hello-world.md": "---\ntitle: 你好，世界\ndate: 2024-05-06 08:00:00\ntags: [Flask, Vue]\ncategories:\n  - 随笔\nphoto: x\n---\n![封面](images/cover.png)\n\n正文\n<!-- more -->\n更多",
        "source/_posts/images/cover.png": png(),
        "source/_posts/no-front-matter.md": "# 没有属性头\n\n只有正文。",
        "source/_posts/draft.md": "---\ntitle: 草稿\ndraft: true\n---\nx",
    }
    out = do_import(admin, files, status="keep").get_json()
    assert (out["posts"], out["media"], out["skipped"]) == (3, 1, 0), out
    got = {p["title"]: p for p in admin.get("/api/admin/posts?per=50").get_json()["items"]}
    hello = got["你好，世界"]
    assert hello["slug"] == "hello-world" and hello["status"] == "published" and hello["category"]["name"] == "随笔" and {t["name"] for t in hello["tags"]} == {"Flask", "Vue"}
    assert hello["published_at"] == "2024-05-06T00:00:00Z"            # 08:00 in the site's own time zone (Asia/Shanghai)
    assert "![封面](media:" in admin.get(f"/api/admin/posts/{hello['id']}").get_json()["content_md"]
    assert "没有属性头" in got and got["没有属性头"]["status"] == "published"
    assert got["草稿"]["status"] == "draft"
    assert admin.get(f"/api/admin/posts/{got['没有属性头']['id']}").get_json()["content_md"].strip() == "只有正文。"


def test_hugo_toml_folder_with_a_wrapping_directory_and_static_images(admin, png):
    files = {
        "mysite/content/posts/first.md": '+++\ntitle = "First"\ndate = 2025-01-02T03:04:05Z\ndraft = false\ntags = ["go"]\nimage = "/img/a.png"\n+++\n![x](/img/a.png)\n',
        "mysite/content/posts/_index.md": '+++\ntitle = "Section"\n+++\n',
        "mysite/content/about.md": '---\ntype: page\ntitle: About\n---\nme',
        "mysite/static/img/a.png": png(),
        "mysite/themes/x/readme.md": "not a post but a markdown file",
    }
    out = do_import(admin, files, status="keep").get_json()
    assert out["pages"] == 1 and out["media"] == 1 and out["skipped"] == 1       # the section index is skipped on purpose
    first = next(p for p in admin.get("/api/admin/posts").get_json()["items"] if p["title"] == "First")
    assert first["cover"] is not None and first["published_at"] == "2025-01-02T03:04:05Z"
    assert admin.get("/api/admin/pages").get_json()["items"][0]["title"] == "About"


def test_duplicate_slugs_are_renamed_and_the_existing_content_is_untouched(admin):
    make_post(admin, "已有", slug="same", content_md="original")
    out = do_import(admin, {"a/same.md": "---\ntitle: 另一篇\n---\nnew", "b/same.md": "---\ntitle: 再一篇\n---\nnewer"}).get_json()
    assert out["posts"] == 2
    slugs = sorted(p["slug"] for p in admin.get("/api/admin/posts").get_json()["items"])
    assert slugs == ["same", "same-2", "same-3"]
    assert admin.get(f"/api/admin/posts/{next(p['id'] for p in admin.get('/api/admin/posts').get_json()['items'] if p['slug'] == 'same')}").get_json()["content_md"] == "original"


def test_a_missing_picture_is_a_warning_and_a_bad_file_does_not_stop_the_others(admin):
    files = {"ok.md": "---\ntitle: OK\n---\n![](gone.png)\n", "bad.md": "---\ntitle: Bad\nstatus: published\ncanonical: not-a-url\ncategory: x\n---\nbody", "moments/m.md": "   "}
    out = do_import(admin, files).get_json()
    assert out["posts"] == 2 and out["skipped"] == 1                    # the empty moment is refused, the rest went in
    assert any("gone.png" in w for w in out["warnings"]) and any("moments/m.md" in w for w in out["warnings"])


# ---- hostile and broken archives --------------------------------------------------------------------------------------------
def test_unsafe_names_are_ignored_and_nothing_is_written_by_path(admin, app, tmp_path):
    out = do_import(admin, {"../../evil.md": "---\ntitle: Evil\n---\nx", "/abs/evil2.md": "---\ntitle: Evil2\n---\nx", "__MACOSX/._a.md": "junk", "fine.md": "---\ntitle: Fine\n---\nok"}).get_json()
    titles = [p["title"] for p in admin.get("/api/admin/posts").get_json()["items"]]
    assert "Evil" not in titles and "Fine" in titles and out["posts"] >= 1
    assert not (tmp_path.parent / "evil.md").exists()


def test_not_a_zip_nothing_to_import_and_missing_file_are_clear_errors(admin):
    r = admin.upload(f"{S}/import", b"this is not a zip", filename="x.zip", mimetype="application/zip")
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "bad_archive"
    r = do_import(admin, {"readme.txt": "hi"})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "nothing_to_import"
    assert admin.post(f"{S}/import", data={}, content_type="multipart/form-data").status_code == 422


def test_a_zip_bomb_is_refused(admin):
    r = do_import(admin, {"big.md": "---\ntitle: bomb\n---\n" + "a" * (3 * 1024 * 1024)})      # 3 MB of text packs to a few KB
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "archive_unsafe"


def test_too_many_files_are_refused(admin, monkeypatch):
    monkeypatch.setattr(transfer, "MAX_FILES", 3)
    r = do_import(admin, {f"{i}.md": "x" for i in range(5)})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "too_many_files"


def test_import_is_recorded_in_the_log(admin):
    do_import(admin, {"a.md": "---\ntitle: A\n---\nx"})
    items = admin.get("/api/admin/audit").get_json()["items"]
    row = next(a for a in items if a["action"] == "system.import")
    assert row["summary"]["posts"] == 1
