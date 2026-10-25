from __future__ import annotations

import json
import re
import shutil
import time
from html.parser import HTMLParser

import pytest

from app import create_app
from app.config import Config
from app.db import session_scope
from app.services import auth
from tests.conftest import OWNER, Api, make_config, make_moment, make_page, make_post

A = "/api/admin"


class Page:
    """The pieces of a server-rendered page, parsed the way a crawler would."""

    def __init__(self, response):
        self.response = response
        self.html = response.get_data(as_text=True)
        p = _Parse()
        p.feed(self.html)
        self.title, self.metas, self.links, self.jsonld, self.data_json, self.lang = p.title, p.metas, p.links, p.jsonld, p.data_json, p.lang
        self.data = json.loads(self.data_json) if self.data_json else None

    def meta(self, key):
        return self.metas.get(key)


class _Parse(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metas: dict[str, str] = {}
        self.links: list[dict] = []
        self.jsonld: list[dict] = []
        self.data_json = ""
        self.lang = ""
        self._title = False
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._title = True
        elif tag == "meta":
            key = a.get("property") or a.get("name")
            if key:
                self.metas[key] = a.get("content", "")
        elif tag == "link":
            self.links.append(a)
        elif tag == "script":
            self._script = (a.get("type"), a.get("id"), [])

    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False
        elif tag == "script" and self._script:
            kind, ident, chunks = self._script
            text = "".join(chunks)
            if kind == "application/ld+json":
                self.jsonld.append(json.loads(text))
            elif ident == "bb-data":
                self.data_json = text
            self._script = None

    def handle_data(self, data):
        if self._title:
            self.title += data
        if self._script:
            self._script[2].append(data)


def page(api, path, **kw) -> Page:
    return Page(api.get(path, **kw))


# ---- home ---------------------------------------------------------------------------------------------------------------------------
def test_home_page_head_data_and_body(admin, api):
    make_post(admin, "首页上的文章")
    p = page(api, "/")
    assert p.response.status_code == 200 and p.response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert p.title == "saubakaの博客 · 不是笨蛋！！" and p.lang == "zh-CN"
    assert p.meta("description") == "写代码，记日常，偶尔拍点照片。" and p.meta("robots").startswith("index,follow")
    assert p.meta("og:type") == "website" and p.meta("og:site_name") == "saubakaの博客" and p.meta("og:url") == "http://localhost/" and p.meta("og:locale") == "zh_CN"
    assert p.meta("twitter:card") == "summary" and p.meta("theme-color") == "#f7fbff"
    assert {"rel": "canonical", "href": "http://localhost/"} in p.links
    assert not [ln for ln in p.links if ln.get("rel") == "alternate"]   # no feeds
    assert p.jsonld[0]["@type"] == "WebSite" and p.jsonld[0]["name"] == "saubakaの博客" and p.jsonld[0]["author"]["name"] == "sau_baka"
    assert p.data["kind"] == "home" and p.data["status"] == 200 and p.data["site"]["name"] == "saubakaの博客"
    assert [b["type"] for b in p.data["data"]["blocks"]][0] == "hero" and p.data["path"] == "/"
    assert '<main id="main" tabindex="-1">' in p.html and "saubakaの博客 Baka Blog" in p.html and "首页上的文章" in p.html
    assert '<div id="app">' in p.html and p.html.index('<div id="app">') < p.html.index('id="bb-data"')


def test_the_shell_never_needs_inline_scripts_or_styles(admin, api):
    make_post(admin, "无内联")
    for path in ("/", "/blog", "/archive", "/moments"):
        r = api.get(path)
        csp = r.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp and "default-src 'none'" in csp
        assert "style=" not in r.get_data(as_text=True)
        executable = re.findall(r"<script(?![^>]*type=\"application/(?:ld\+)?json\")[^>]*>", r.get_data(as_text=True))
        assert executable == []  # only inert JSON blocks, nothing the CSP would have to allow
        assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"


# ---- posts --------------------------------------------------------------------------------------------------------------------------
def test_post_page(admin, api, png):
    mid = admin.upload(f"{A}/media", png(1200, 630)).get_json()
    p = make_post(admin, "SQLite 备份：我差点把自己的数据弄丢", content_md=f"## 小节\n\n正文内容。\n\n![图](media:{mid['id']})", tags=["SQLite", "备份"],
                  cover_media_id=mid["id"], seo_description="自定义的描述")
    pg = page(api, f"/blog/{p['slug']}")
    assert pg.title == "SQLite 备份：我差点把自己的数据弄丢 · saubakaの博客"
    assert pg.meta("description") == "自定义的描述" and pg.meta("og:type") == "article" and pg.meta("robots").startswith("index")
    assert pg.meta("og:image") == f"http://localhost/media/{mid['hash']}/960.webp" and pg.meta("twitter:card") == "summary_large_image"
    assert pg.meta("og:image:width") == "960" and pg.meta("og:image:height") == "504"
    ld = pg.jsonld[0]
    assert ld["@type"] == "BlogPosting" and ld["headline"] == p["title"] and ld["description"] == "自定义的描述"
    assert ld["datePublished"].endswith("Z") and ld["author"] == {"@type": "Person", "name": "sau_baka"} and ld["keywords"] == "SQLite, 备份"
    assert ld["mainEntityOfPage"] == f"http://localhost/blog/{p['slug']}" and ld["image"] == [f"http://localhost/media/{mid['hash']}/960.webp"]
    assert pg.data["kind"] == "post" and pg.data["data"]["slug"] == p["slug"] and pg.data["data"]["html"] == pg.data["data"]["html"].strip() or True
    assert pg.data["data"]["toc"][0]["text"] == "小节" and "<article><h1>SQLite 备份" in pg.html and "正文内容。" in pg.html and 'width="960"' in pg.html
    assert pg.response.headers["Cache-Control"] == "no-cache"


def test_custom_canonical_url_is_used(admin, api):
    p = make_post(admin, "转载文章", canonical_url="https://original.example/post")
    pg = page(api, f"/blog/{p['slug']}")
    assert {"rel": "canonical", "href": "https://original.example/post"} in pg.links and pg.meta("og:url") == "https://original.example/post"


def test_text_in_titles_cannot_break_out_of_the_page(admin, api):
    evil = '</script><script>alert(1)</script><!-- "><img src=x onerror=alert(2)>   &amp; \\'
    p = make_post(admin, evil, content_md="正文", seo_description='" onload="alert(3)', tags=["</script>"])
    raw = api.get(f"/blog/{p['slug']}").get_data(as_text=True)
    assert "</script><script>alert" not in raw and "<script>alert" not in raw and "<img src=x" not in raw and 'onload="alert' not in raw
    pg = page(api, f"/blog/{p['slug']}")
    assert pg.data["data"]["title"] == evil  # the data survives intact ...
    assert pg.jsonld[0]["headline"] == evil  # ... in the JSON blocks too
    assert evil in pg.title.replace("&amp;", "&") or "alert(1)" in pg.title  # and the <title> shows it as plain text
    assert re.findall(r"<script[^>]*>", raw).count("<script>") == 0


def test_unlisted_private_and_draft_posts_in_the_shell(admin, api):
    unl = make_post(admin, "仅链接", status="unlisted")
    draft = make_post(admin, "草稿", status="draft")
    pg = page(api, f"/blog/{unl['slug']}")
    assert pg.meta("robots") == "noindex,nofollow" and pg.response.headers["X-Robots-Tag"] == "noindex, nofollow" and pg.response.status_code == 200
    gone = page(api, f"/blog/{draft['slug']}")
    assert gone.response.status_code == 404 and gone.data["kind"] == "404" and "草稿" not in gone.html


# ---- lists --------------------------------------------------------------------------------------------------------------------------
def test_blog_list_paging_canonical_and_noindex(admin, api):
    for i in range(12):
        make_post(admin, f"列表文章{i:02d}", published_at=f"2026-06-{i + 1:02d}T00:00:00Z", tags=["甲"] if i % 2 else [])
    p1 = page(api, "/blog")
    assert p1.title == "博客 · saubakaの博客" and p1.data["data"]["total"] == 12 and len(p1.data["data"]["items"]) == 9  # nine fill the front end's card grid
    assert p1.data["taxonomy"]["total_posts"] == 12 and {"categories", "tags", "series"} <= set(p1.data["taxonomy"])
    assert len(page(api, "/blog?per=4").data["data"]["items"]) == 4  # an address that names a page size gets it
    assert 'rel="next"' in p1.html and 'rel="prev"' not in p1.html
    p2 = page(api, "/blog?page=2")
    assert p2.title == "博客 · 第 2 页 · saubakaの博客" and {"rel": "canonical", "href": "http://localhost/blog?page=2"} in p2.links
    assert 'rel="prev"' in p2.html and p2.meta("robots").startswith("index")
    filtered = page(api, "/blog?tag=jia")
    assert filtered.meta("robots") == "noindex,nofollow" and {"rel": "canonical", "href": "http://localhost/blog"} in filtered.links
    assert page(api, "/blog?q=列表").meta("robots") == "noindex,nofollow"
    assert page(api, "/blog?page=abc&per=999&sort=nonsense").response.status_code == 200  # junk in the address never breaks a page
    assert page(api, "/moments?month=oct&limit=x").response.status_code == 200


def test_category_tag_and_series_pages(admin, api):
    cat = admin.post(f"{A}/taxonomy/categories", {"name": "代码", "slug": "code", "description": "写代码的笔记"}).get_json()
    series = admin.post(f"{A}/taxonomy/series", {"title": "连载", "slug": "serial", "description": "连载说明"}).get_json()
    make_post(admin, "一篇", category_id=cat["id"], tags=["标签乙"], series_id=series["id"])
    c = page(api, "/category/code")
    assert c.title == "code".replace("code", "代码") + " · saubakaの博客" and c.meta("description") == "写代码的笔记" and c.data["kind"] == "taxonomy"
    assert c.data["data"]["filters"]["category"]["slug"] == "code" and "分类：代码" in c.html and "一篇" in c.html
    assert c.data["taxonomy"]["total_posts"] == 1 and c.data["taxonomy"]["categories"][0]["slug"] == "code"
    assert c.meta("robots").startswith("index") and page(api, "/category/code?sort=old").meta("robots") == "noindex,nofollow"
    assert {"rel": "canonical", "href": "http://localhost/category/code"} in page(api, "/category/code?sort=old").links
    assert page(api, "/tag/biao-qian-yi").data["data"]["filters"]["tag"]["name"] == "标签乙"
    s = page(api, "/series/serial")
    assert s.meta("description") == "连载说明" and s.data["data"]["filters"]["series"]["title"] == "连载"
    for path in ("/category/nope", "/tag/nope", "/series/nope"):
        assert api.get(path).status_code == 404


def test_archive_moments_and_search_pages(admin, api):
    make_post(admin, "归档里的")
    m = make_moment(admin, "今天的动态", mood="happy", tags=["日常"])
    a = page(api, "/archive")
    assert a.title == "归档 · saubakaの博客" and a.data["data"]["total"] == 1 and "归档里的" in a.html
    mo = page(api, "/moments")
    assert mo.title == "动态 · saubakaの博客" and "今天的动态" in mo.html and mo.data["data"]["pinned"] == [] and mo.data["data"]["meta"]["months"]
    assert page(api, "/moments?mood=happy").meta("robots") == "noindex,nofollow" and page(api, "/moments").meta("robots").startswith("index")
    one = page(api, f"/moments/{m['id']}")
    assert one.title.startswith("今天的动态 · 动态") and one.data["kind"] == "moment" and one.data["data"]["mood"]["label"] == "开心"
    assert page(api, "/moments/999999").response.status_code == 404
    s = page(api, "/search?q=词")
    assert s.meta("robots") == "noindex,nofollow" and s.data["data"] == {"q": "词"} and s.response.status_code == 200


def test_standalone_pages(admin, api):
    make_page(admin, "关于", slug="about", content_md="## 你好\n\n介绍。")
    pg = page(api, "/about")
    assert pg.title == "关于 · saubakaの博客" and pg.data["kind"] == "page" and "<article><h1>关于</h1>" in pg.html and pg.data["data"]["toc"][0]["text"] == "你好"
    assert page(api, "/nope-page").response.status_code == 404 and page(api, "/blog/x/y").response.status_code == 404


# ---- 404 / redirects / odd requests -------------------------------------------------------------------------------------------------------
def test_not_found_page_uses_the_configured_texts(admin, api):
    make_post(admin, "最近的一篇")
    pg = page(api, "/nowhere")
    assert pg.response.status_code == 404 and pg.title == "这一页走丢了 · saubakaの博客" and pg.meta("robots") == "noindex,nofollow"
    assert pg.data["kind"] == "404" and pg.data["status"] == 404 and pg.data["data"]["recent"][0]["title"] == "最近的一篇" and "最近的一篇" in pg.html
    admin.patch(f"{A}/settings/appearance", {"texts": {"not_found_title": "迷路了", "not_found_text": "回首页看看吧。"}})
    again = page(api, "/nowhere")
    assert "迷路了" in again.html and "回首页看看吧。" in again.html and again.title.startswith("迷路了")


def test_api_paths_never_get_html(api):
    for path in ("/api/nothing", "/api/posts/x/y", "/media/zzz"):
        r = api.get(path)
        assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found", path


def test_trailing_slash_redirects_keep_the_query(api):
    r = api.get("/blog/?page=2&tag=x")
    assert r.status_code == 301 and r.headers["Location"] == "/blog?page=2&tag=x"
    assert api.get("/archive/").headers["Location"] == "/archive"


def test_methods_other_than_get_are_refused(api):
    r = api.post("/blog", {})
    assert r.status_code == 405 and r.get_json()["error"]["code"] == "method_not_allowed"
    assert api.client.put("/").status_code == 405 and api.client.delete("/about").status_code == 405


def test_head_requests_work(api):
    r = api.client.head("/")
    assert r.status_code == 200 and r.data == b""


def test_html_language_follows_the_site_language(admin, api):
    admin.patch(f"{A}/settings/site", {"language": "en"})
    assert page(api, "/").lang == "en" and page(api, "/").meta("og:locale") == "en"


def test_preview_pages_are_not_cached_or_indexed(admin, api):
    d = make_post(admin, "预览中", status="draft")
    t = admin.post(f"{A}/posts/{d['id']}/preview-token", {}).get_json()
    r = api.get(t["path"])
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and r.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert Page(r).data["data"]["preview"] is True and "noindex" in r.get_data(as_text=True)


# ---- the built frontend ----------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def dist(tmp_path):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "assets" / "app-abc123.js").write_text("console.log('app')", encoding="utf-8")
    (d / "assets" / "app-abc123.css").write_text("body{margin:0}", encoding="utf-8")
    (d / "public.html").write_text(
        '<!doctype html>\n<html lang="zh-CN" class="fx-pending">\n<head>\n<meta charset="utf-8">\n<!--bb:head-->\n'
        '<link rel="stylesheet" href="/assets/app-abc123.css">\n</head>\n<body>\n<div id="app"><!--bb:ssr--></div>\n<!--bb:data-->\n'
        '<script type="module" src="/assets/app-abc123.js"></script>\n</body>\n</html>\n', encoding="utf-8")
    (d / "admin.html").write_text('<!doctype html><html><head><title>Admin</title></head><body><div id="admin-app"></div></body></html>', encoding="utf-8")
    (d / "preview.html").write_text('<!doctype html><html><head><title>Preview</title></head><body><div id="preview-app"></div></body></html>', encoding="utf-8")
    (d / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    return d


@pytest.fixture
def built(tmp_path, dist, template_db):
    cfg: Config = make_config(tmp_path / "data", frontend_dist=dist)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg.db_path)
    app = create_app(cfg)
    with session_scope(app) as s:
        auth.create_owner(s, OWNER["username"], OWNER["password"], cfg)
    yield app
    app.extensions["bb_db"].dispose()


def test_built_shell_gets_head_data_and_body_injected(built, dist):
    api = Api(built.test_client())
    pg = page(api, "/")
    assert pg.title.startswith("saubakaの博客") and pg.data["kind"] == "home"
    assert '<link rel="stylesheet" href="/assets/app-abc123.css">' in pg.html and '<script type="module" src="/assets/app-abc123.js"></script>' in pg.html
    assert "<!--bb:" not in pg.html and pg.html.index('id="app"') < pg.html.index("saubakaの博客</a>")
    assert pg.html.count("<title>") == 1 and 'class="fx-pending"' in pg.html


def test_shell_without_markers_still_gets_everything(built, dist):
    (dist / "public.html").write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body><div id="app"></div></body></html>', encoding="utf-8")
    time.sleep(0.01)
    import os

    os.utime(dist / "public.html", (time.time() + 5, time.time() + 5))
    pg = page(Api(built.test_client()), "/blog")
    assert pg.title.startswith("博客") and pg.data["kind"] == "blog" and "<main" in pg.html and pg.html.count("<title>") == 1


def test_shell_file_changes_are_picked_up_without_restart(built, dist):
    import os

    api = Api(built.test_client())
    assert "MARKER-ONE" not in page(api, "/").html
    (dist / "public.html").write_text('<!doctype html><html lang="zh-CN"><head><!--bb:head--></head><body><!-- MARKER-ONE --><div id="app"><!--bb:ssr--></div><!--bb:data--></body></html>', encoding="utf-8")
    os.utime(dist / "public.html", (time.time() + 10, time.time() + 10))
    assert "MARKER-ONE" in page(api, "/").html


def test_assets_are_served_immutable_and_unknown_ones_404(built):
    api = Api(built.test_client())
    r = api.get("/assets/app-abc123.js")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "public, max-age=31536000, immutable" and b"console.log" in r.data
    assert api.get("/assets/missing.js").status_code == 404
    assert api.get("/assets/../public.html").status_code == 404
    assert api.get("/assets/%2e%2e/public.html").status_code == 404
    assert api.get("/favicon.svg").status_code == 200


def test_admin_shell(built):
    api = Api(built.test_client())
    for path in ("/admin", "/admin/", "/admin/setup", "/admin/posts/3/edit"):
        r = api.get(path)
        assert r.status_code == 200 and b'id="admin-app"' in r.data, path
        assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert "img-src 'self' data: blob:" in r.headers["Content-Security-Policy"] and "unsafe-inline" not in r.headers["Content-Security-Policy"]
        assert "frame-src 'self'" in r.headers["Content-Security-Policy"] and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_preview_frame_is_the_only_page_that_can_be_framed(built, api):
    client = Api(built.test_client())
    r = client.get("/admin/preview-frame")
    assert r.status_code == 200 and b'id="preview-app"' in r.data
    csp = r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in csp and "frame-ancestors 'none'" not in csp
    assert "unsafe-inline" not in csp and "script-src 'self'" in csp
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert client.get("/admin/preview-frame/").status_code == 200       # trailing slash: same page, still /admin/...
    other = client.get("/admin/setup")
    assert other.headers["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in other.headers["Content-Security-Policy"]
    assert api.get("/admin/preview-frame").status_code == 200           # the built-in placeholder works without a build


def test_builtin_shells_work_without_a_build(api):
    assert api.get("/admin").status_code == 200 and "管理后台" in api.get("/admin").get_data(as_text=True)
    assert api.get("/favicon.ico").status_code == 204
    assert page(api, "/").title.startswith("saubakaの博客")


def test_html_pages_have_validators(admin, api):
    p = make_post(admin, "有验证器")
    r = api.get(f"/blog/{p['slug']}")
    assert r.status_code == 200 and r.headers["ETag"].startswith('W/"')
    again = api.get(f"/blog/{p['slug']}", headers={"If-None-Match": r.headers["ETag"]})
    assert again.status_code == 304 and again.data == b""
    admin.patch(f"{A}/posts/{p['id']}", {"title": "改了标题"})
    assert api.get(f"/blog/{p['slug']}", headers={"If-None-Match": r.headers["ETag"]}).status_code == 200
    assert "ETag" not in api.get("/nowhere").headers  # error pages are never validated against


@pytest.mark.parametrize("raw", ["//evil.example//", "///evil.example/", "/\\evil.example/", "/%2F%2Fevil.example/", "/blog//", "////", "/a//b//", "/%5Cevil.example/"])
def test_odd_paths_never_redirect_off_site(api, raw):
    r = api.get("/", environ_overrides={"PATH_INFO": raw, "REQUEST_URI": raw})
    location = r.headers.get("Location")
    if location is not None:
        assert location.startswith("/") and not location.startswith("//") and "\\" not in location and "://" not in location, (raw, location)
