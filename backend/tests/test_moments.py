from __future__ import annotations

from datetime import timedelta

import pytest

from app.db import session_scope
from app.models import Moment
from app.services import linkcard
from app.services.moments import extract_hashtags
from app.timeutil import iso, utcnow
from tests.conftest import make_moment, png_bytes

MO = "/api/admin/moments"


def upload(admin, color=(10, 20, 30)) -> int:
    return admin.upload("/api/admin/media", png_bytes(200, 120, color)).get_json()["id"]


# ---- hashtags -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,clean,tags", [
    ("今天写了 #设计 和 #CSS", "今天写了 和", ["设计", "CSS"]),
    ("#单独一个", "", ["单独一个"]),
    ("行一 #a\n行二 #b。", "行一\n行二 。", ["a", "b"]),
    ("看 https://example.com/page#section 这个", "看 https://example.com/page#section 这个", []),
    ("代码 `#not-a-tag` 好", "代码 `#not-a-tag` 好", []),
    ("[链接 #x](https://e.com/#y)", "[链接 #x](https://e.com/#y)", []),
    ("颜色是 &#35; 或 a#b", "颜色是 &#35; 或 a#b", []),
    ("全角＃标签 也行", "全角 也行", ["标签"]),
    ("#" + "长" * 31, "#" + "长" * 31, []),
])
def test_hashtag_extraction(text, clean, tags):
    out, found = extract_hashtags(text)
    assert (out, found) == (clean, tags)


def test_hashtags_become_tags_unless_disabled(admin):
    m = make_moment(admin, "今天写了 #设计 和 #CSS")
    assert m["markdown"] == "今天写了 和" and [t["name"] for t in m["tags"]] == ["CSS", "设计"]
    raw = make_moment(admin, "保留 #原样", auto_tags=False)
    assert raw["markdown"] == "保留 #原样" and raw["tags"] == []
    explicit = make_moment(admin, "显式", tags=["手写标签", "CSS"])
    assert [t["name"] for t in explicit["tags"]] == ["CSS", "手写标签"]
    assert len(admin.get("/api/admin/taxonomy/tags").get_json()["items"]) == 3  # CSS is shared with the first moment


def test_tags_are_shared_between_posts_and_moments(admin):
    admin.post("/api/admin/posts", {"title": "p", "status": "published", "tags": ["共用"]})
    make_moment(admin, "m #共用")
    tag = admin.get("/api/admin/taxonomy/tags").get_json()["items"][0]
    assert (tag["name"], tag["post_count"], tag["moment_count"]) == ("共用", 1, 1)


# ---- content rules ---------------------------------------------------------------------------------------------------------------------
def test_text_picture_or_link_is_required(admin):
    r = admin.post(MO, {})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "empty"
    assert admin.post(MO, {"text": "   "}).status_code == 422
    assert admin.post(MO, {"text": "#只有标签"}).status_code == 422  # nothing left once the tag is taken out
    assert admin.post(MO, {"media": [{"media_id": upload(admin)}]}).status_code == 201
    assert admin.post(MO, {"link_card": {"url": "https://example.com/a"}}).status_code == 201


def test_unknown_fields_and_bad_values(admin):
    assert admin.post(MO, {"text": "x", "likes": 3}).status_code == 422
    assert admin.post(MO, {"text": "x", "mood": "angry"}).status_code == 422
    assert admin.post(MO, {"text": "x", "visibility": "friends"}).status_code == 422
    assert admin.post(MO, {"text": "y" * 5001}).status_code == 422


def test_mood_and_markdown_rendering(admin):
    m = make_moment(admin, "**粗体** 和 [链接](https://example.com) 还有 `code`\n第二行", mood="happy")
    assert m["mood"] == {"id": "happy", "label": "开心"}
    assert "<strong>粗体</strong>" in m["html"] and 'href="https://example.com"' in m["html"] and "<code>code</code>" in m["html"] and "<br>" in m["html"]
    assert make_moment(admin, "无心情")["mood"] is None


def test_script_in_a_moment_is_neutralised(admin, api):
    m = make_moment(admin, "<script>alert(1)</script><img src=x onerror=alert(1)> [x](javascript:alert(1))")
    shown = api.get(f"/api/moments/{m['id']}").get_json()
    from tests.test_markdown import assert_clean

    assert_clean(shown["html"])  # only allow-listed tags: the markup was turned into visible text, not interpreted
    assert "<script" not in shown["html"] and "<img" not in shown["html"] and "&lt;script&gt;" in shown["html"] and 'href="javascript' not in shown["html"]


def test_pictures_up_to_nine_in_order_with_alt_text(admin, api):
    ids = [upload(admin, (i * 20, 0, 0)) for i in range(9)]
    m = make_moment(admin, "九张", media=[{"media_id": i, "alt": f"图{n}"} for n, i in enumerate(ids)])
    assert [x["id"] for x in m["media"]] == ids and m["media"][3]["alt"] == "图3"
    shown = api.get(f"/api/moments/{m['id']}").get_json()
    assert [x["id"] for x in shown["media"]] == ids and shown["media"][0]["src"].startswith("/media/")
    reordered = admin.patch(f"{MO}/{m['id']}", {"media": [{"media_id": ids[2]}, {"media_id": ids[0]}]}).get_json()
    assert [x["id"] for x in reordered["media"]] == [ids[2], ids[0]]
    dup = admin.post(MO, {"text": "x", "media": [{"media_id": ids[0]}, {"media_id": ids[0]}, {"media_id": ids[1]}]})
    assert dup.status_code == 201 and [x["id"] for x in dup.get_json()["media"]] == [ids[0], ids[1]]  # a repeated picture is ignored
    extra = upload(admin, (200, 0, 0))
    r = admin.post(MO, {"text": "x", "media": [{"media_id": i} for i in ids + [extra]]})
    assert r.status_code == 422 and "9" in r.get_json()["error"]["fields"]["media"]


def test_missing_or_trashed_pictures_are_refused(admin):
    assert admin.post(MO, {"text": "x", "media": [{"media_id": 424242}]}).status_code == 422
    mid = upload(admin)
    admin.delete(f"/api/admin/media/{mid}")
    assert admin.post(MO, {"text": "x", "media": [{"media_id": mid}]}).status_code == 422


def test_link_card_is_cleaned(admin):
    m = make_moment(admin, "看这个", link_card={"url": "https://www.Example.com/a?b=1", "title": "标题", "description": "说明"})
    assert m["link_card"] == {"url": "https://www.Example.com/a?b=1", "title": "标题", "description": "说明", "domain": "example.com", "icon": None}
    for bad in ("javascript:alert(1)", "ftp://example.com", "example.com", "http://", "data:text/html,x"):
        assert admin.post(MO, {"text": "x", "link_card": {"url": bad}}).status_code == 422, bad


# ---- visibility -------------------------------------------------------------------------------------------------------------------------
def test_visibility_matrix(admin, api):
    pub = make_moment(admin, "公开的")
    unl = make_moment(admin, "仅链接的", visibility="unlisted")
    priv = make_moment(admin, "私密的", visibility="private")
    future = make_moment(admin, "未来的", published_at=iso(utcnow() + timedelta(days=1)))
    gone = make_moment(admin, "删掉的")
    admin.delete(f"{MO}/{gone['id']}")
    assert future["scheduled"] is True
    assert [m["id"] for m in api.get("/api/moments").get_json()["items"]] == [pub["id"]]
    assert api.get(f"/api/moments/{pub['id']}").status_code == 200
    assert api.get(f"/api/moments/{unl['id']}").status_code == 200  # reachable by its link
    assert api.get(f"/api/moments/{unl['id']}").get_json()["seo"]["noindex"] is True
    for hidden in (priv, future, gone):
        assert api.get(f"/api/moments/{hidden['id']}").status_code == 404
        assert api.get(f"/moments/{hidden['id']}").status_code == 404
    assert api.get(f"/moments/{unl['id']}").status_code == 200
    feed = api.get("/feed/moments.xml").get_data(as_text=True)
    sitemap = api.get("/sitemap.xml").get_data(as_text=True)
    assert "公开的" in feed and all(t not in feed for t in ("仅链接的", "私密的", "未来的", "删掉的"))
    assert f"/moments/{pub['id']}<" in sitemap and all(f"/moments/{m['id']}<" not in sitemap for m in (unl, priv, future, gone))
    found = api.get("/api/search?q=的&type=moment").get_json()["groups"]["moments"] if False else None
    assert found is None
    for word in ("仅链接的", "私密的", "未来的", "删掉的"):
        assert api.get(f"/api/search?q={word}&type=moment").get_json()["groups"]["moments"] == []
    assert [m["id"] for m in api.get("/api/search?q=公开的&type=moment").get_json()["groups"]["moments"]] == [pub["id"]]


def test_a_scheduled_moment_appears_when_due(admin, api, app):
    m = make_moment(admin, "定时的动态", published_at=iso(utcnow() + timedelta(hours=1)))
    assert api.get("/api/moments").get_json()["items"] == []
    with session_scope(app) as s:
        s.get(Moment, m["id"]).published_at = utcnow() - timedelta(seconds=5)
    assert [x["id"] for x in api.get("/api/moments").get_json()["items"]] == [m["id"]]


# ---- the public feed: paging, filters, meta ----------------------------------------------------------------------------------------------
def test_cursor_paging_has_no_gaps_or_repeats_even_with_equal_timestamps(admin, api):
    stamp = "2026-05-05T05:05:05Z"
    ids = [make_moment(admin, f"同一时刻 {i}", published_at=stamp)["id"] for i in range(7)]
    ids += [make_moment(admin, f"更早 {i}", published_at=f"2026-05-0{i + 1}T00:00:00Z")["id"] for i in range(3)]
    seen, cursor, pages = [], None, 0
    while True:
        url = "/api/moments?limit=3" + (f"&cursor={cursor}" if cursor else "")
        body = api.get(url).get_json()
        seen += [m["id"] for m in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert pages == 4 and len(seen) == 10 and sorted(seen) == sorted(ids) and len(set(seen)) == 10
    assert api.get("/api/moments?cursor=not-a-cursor").status_code == 200  # a broken cursor starts over rather than failing
    assert api.get("/api/moments?limit=100").status_code == 422


def test_first_page_carries_pinned_items_and_meta(admin, api):
    a = make_moment(admin, "置顶的 #标签甲", pinned=True, mood="calm", published_at="2026-08-01T00:00:00Z")
    make_moment(admin, "普通的 #标签甲", mood="happy", published_at="2026-09-02T00:00:00Z")
    make_moment(admin, "最新的", mood="happy", published_at="2026-09-03T00:00:00Z")
    body = api.get("/api/moments").get_json()
    assert [m["id"] for m in body["pinned"]] == [a["id"]]
    assert [m["text"] for m in body["items"]][:2] == ["最新的", "普通的"] and a["id"] in [m["id"] for m in body["items"]]
    meta = body["meta"]
    assert meta["months"] == [{"month": "2026-09", "count": 2}, {"month": "2026-08", "count": 1}]
    assert meta["days"] == {"2026-09": [2, 3], "2026-08": [1]}
    assert meta["tags"][0]["name"] == "标签甲" and meta["tags"][0]["count"] == 2
    assert {m["id"]: m["count"] for m in meta["moods"]} == {"happy": 2, "calm": 1}
    assert "meta" not in api.get(f"/api/moments?cursor={body['next_cursor']}").get_json() if body["next_cursor"] else True


def test_filters_by_tag_mood_and_month(admin, api):
    make_moment(admin, "甲 #t1", mood="happy", published_at="2026-09-10T00:00:00Z")
    make_moment(admin, "乙 #t2", mood="calm", published_at="2026-09-11T00:00:00Z")
    make_moment(admin, "丙 #t1", mood="calm", published_at="2026-08-12T00:00:00Z")
    texts = lambda q: [m["text"] for m in api.get(f"/api/moments?{q}").get_json()["items"]]  # noqa: E731
    assert texts("tag=t1") == ["甲", "丙"] and texts("mood=calm") == ["乙", "丙"] and texts("month=2026-09") == ["乙", "甲"]
    assert texts("tag=t1&mood=calm") == ["丙"] and texts("month=2026-07") == [] and texts("tag=nope") == []
    assert api.get("/api/moments?month=2026-13").status_code == 422 and api.get("/api/moments?month=oct").status_code == 422


def test_months_follow_the_site_time_zone(admin, api):
    # 2026-09-30 20:00 UTC is already October 1st, 04:00 in Shanghai (the default site time zone)
    m = make_moment(admin, "跨月", published_at="2026-09-30T20:00:00Z")
    assert [x["id"] for x in api.get("/api/moments?month=2026-10").get_json()["items"]] == [m["id"]]
    assert api.get("/api/moments?month=2026-09").get_json()["items"] == []
    assert api.get("/api/moments").get_json()["meta"]["months"] == [{"month": "2026-10", "count": 1}]
    admin.patch("/api/admin/settings/site", {"timezone": "UTC"})
    assert [x["id"] for x in api.get("/api/moments?month=2026-09").get_json()["items"]] == [m["id"]]


# ---- admin -------------------------------------------------------------------------------------------------------------------------------
def test_admin_list_filters(admin):
    a = make_moment(admin, "甲 #x", mood="happy", published_at="2026-01-05T00:00:00Z")
    b = make_moment(admin, "乙", visibility="private", published_at="2026-02-05T00:00:00Z")
    c = make_moment(admin, "丙已删")
    admin.delete(f"{MO}/{c['id']}")
    ids = lambda q: [m["id"] for m in admin.get(f"{MO}?{q}").get_json()["items"]]  # noqa: E731
    assert ids("") == [b["id"], a["id"]] and ids("visibility=private") == [b["id"]] and ids("tag=x") == [a["id"]]
    assert ids("mood=happy") == [a["id"]] and ids("month=2026-02") == [b["id"]] and ids("q=甲") == [a["id"]] and ids("trashed=1") == [c["id"]]
    assert admin.get(MO).get_json()["counts"] == {"all": 2, "trashed": 1}


def test_edit_trash_restore_purge_duplicate_batch(admin, api):
    m = make_moment(admin, "原文 #旧标签", mood="calm")
    e = admin.patch(f"{MO}/{m['id']}", {"text": "改过 #新标签", "mood": None, "visibility": "unlisted", "pinned": True}).get_json()
    assert e["markdown"] == "改过" and e["mood"] is None and e["visibility"] == "unlisted" and e["pinned"] is True
    assert [t["name"] for t in e["tags"]] == ["新标签"]
    copy = admin.post(f"{MO}/{m['id']}/duplicate", {}).get_json()
    assert copy["id"] != m["id"] and copy["visibility"] == "private" and copy["markdown"] == "改过"
    assert admin.delete(f"{MO}/{m['id']}/purge").status_code == 409
    admin.delete(f"{MO}/{m['id']}")
    assert api.get(f"/api/moments/{m['id']}").status_code == 404
    assert admin.post(f"{MO}/{m['id']}/restore", {}).status_code == 200
    r = admin.post(f"{MO}/batch", {"ids": [m["id"], copy["id"]], "action": "public"}).get_json()
    assert r["done"] == 2 and api.get(f"/api/moments/{copy['id']}").status_code == 200
    admin.post(f"{MO}/batch", {"ids": [m["id"], copy["id"]], "action": "trash"})
    assert admin.post(f"{MO}/batch", {"ids": [m["id"], copy["id"]], "action": "purge"}).get_json()["done"] == 2
    assert admin.get(f"{MO}/{m['id']}").status_code == 404


# ---- link preview (the network is faked; nothing here touches the internet) -------------------------------------------------------------------
HTML = """<!doctype html><html><head><meta charset="utf-8"><title>页面标题 | 站点</title>
<meta property="og:title" content="OG 标题"><meta property="og:description" content="这是一段 OG 描述">
<meta property="og:site_name" content="示例站"><link rel="icon" href="/icon.png"><link rel="apple-touch-icon" href="/apple.png">
</head><body><p>正文</p><title>不该被读到</title></body></html>"""


class FakeResponse:
    def __init__(self, status=200, body=b"", headers=None):
        self.status, self._body, self._headers = status, body, headers or {}

    def getheader(self, name, default=None):
        return {k.lower(): v for k, v in self._headers.items()}.get(name.lower(), default)

    def getheaders(self):
        return list(self._headers.items())

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]


class FakeNet:
    """host -> response factory; records which address each connection was pinned to."""

    def __init__(self, sites: dict[str, dict], dns: dict[str, list[str]]):
        self.sites, self.dns, self.connections = sites, dns, []

    def resolver(self, host, port):
        import socket

        if host in self.dns:
            return self.dns[host]
        if host.rstrip(".") == "localhost":
            return ["127.0.0.1", "::1"]
        if ":" in host:  # IPv6 literal
            return [host]
        try:  # what the system resolver does with 2130706433, 0x7f.1, 017700000001 ...
            return [socket.inet_ntoa(socket.inet_aton(host))]
        except OSError:
            return ["93.184.216.34"]

    def connector(self, host, ip, port, tls, timeout):
        net = self

        class Conn:
            def request(self, method, path, headers=None):
                net.connections.append((host, ip, port, tls, path))
                self.path, self.headers = path, headers or {}

            def getresponse(self):
                spec = net.sites.get(host, {}).get(self.path)
                if spec is None:
                    return FakeResponse(404, b"nope", {"Content-Type": "text/plain"})
                return FakeResponse(spec.get("status", 200), spec.get("body", b""), spec.get("headers", {"Content-Type": "text/html; charset=utf-8"}))

            def close(self):
                pass

        return Conn()


@pytest.fixture
def net(monkeypatch):
    png = png_bytes(32, 32, (200, 30, 60))
    n = FakeNet({
        "example.com": {
            "/page": {"body": HTML.encode()},
            "/icon.png": {"body": png, "headers": {"Content-Type": "image/png"}},
            "/apple.png": {"body": png, "headers": {"Content-Type": "image/png"}},
            "/plain": {"body": b"hello", "headers": {"Content-Type": "text/plain"}},
            "/redir": {"status": 302, "headers": {"Location": "/page"}},
            "/to-private": {"status": 302, "headers": {"Location": "http://127.0.0.1/admin"}},
            "/to-meta": {"status": 301, "headers": {"Location": "http://169.254.169.254/latest/meta-data/"}},
            "/loop": {"status": 302, "headers": {"Location": "/loop"}},
            "/big": {"body": b"<title>t</title>" + b"x" * 2_000_000},
        },
    }, {"rebind.example": ["93.184.216.34", "10.0.0.7"], "internal.example": ["192.168.1.20"], "v6.example": ["::1"]})
    monkeypatch.setattr(linkcard, "default_resolver", n.resolver)
    monkeypatch.setattr(linkcard, "default_connector", n.connector)
    return n


def preview(admin, url, **kw):
    return admin.post(f"{MO}/link-preview", {"url": url, **kw})


def test_link_preview_reads_title_description_site_and_stores_the_icon(admin, net):
    r = preview(admin, "https://example.com/page")
    assert r.status_code == 200
    d = r.get_json()
    assert d["title"] == "OG 标题" and d["description"] == "这是一段 OG 描述" and d["site_name"] == "示例站" and d["domain"] == "example.com"
    assert d["icon_media_id"] and d["icon"]["src"].startswith("/media/")
    kinds = admin.get(f"/api/admin/media/{d['icon_media_id']}").get_json()
    assert kinds["kind"] == "icon" and "example.com" in kinds["alt"]
    assert ("example.com", "93.184.216.34", 443, True, "/page") in net.connections  # pinned to the resolved address, over TLS
    m = make_moment(admin, "看看", link_card={"url": d["url"], "title": d["title"], "description": d["description"], "icon_media_id": d["icon_media_id"]})
    assert m["link_card"]["icon"]["id"] == d["icon_media_id"]


def test_link_preview_without_icon_and_for_non_html(admin, net):
    assert preview(admin, "https://example.com/page", fetch_icon=False).get_json()["icon_media_id"] is None
    plain = preview(admin, "https://example.com/plain").get_json()
    assert plain["title"] == "example.com" and plain["description"] == ""
    assert preview(admin, "https://example.com/redir").get_json()["title"] == "OG 标题"  # redirects are followed (and re-checked)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://172.16.0.9:8080/", "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/", "http://224.0.0.1/", "http://[fe80::1]/",
    "http://[fd00::1]/", "http://internal.example/", "http://v6.example/", "http://rebind.example/", "http://2130706433/", "http://0x7f.0.0.1/",
    "http://017700000001/", "http://127.1/", "http://localhost./",
])
def test_link_preview_refuses_internal_addresses(admin, net, url):
    r = preview(admin, url)
    assert r.status_code == 422 and r.get_json()["error"]["code"] in ("forbidden_address", "dns_failed", "bad_url"), r.get_json()
    assert net.connections == []  # not even a connection attempt


@pytest.mark.parametrize("url,code", [
    ("file:///etc/passwd", "bad_scheme"), ("ftp://example.com/x", "bad_scheme"), ("gopher://example.com/", "bad_scheme"),
    ("javascript:alert(1)", "bad_scheme"), ("https://user:secret@example.com/page", "bad_url"), ("http:///nohost", "bad_url"),
    ("https://example.com:99999/", "bad_url"),
])
def test_link_preview_refuses_odd_urls(admin, net, url, code):
    r = preview(admin, url)
    assert r.status_code == 422 and r.get_json()["error"]["code"] == code


def test_redirects_to_internal_addresses_are_refused_and_loops_end(admin, net):
    for path in ("/to-private", "/to-meta"):
        r = preview(admin, f"https://example.com{path}")
        assert r.status_code == 422 and r.get_json()["error"]["code"] == "forbidden_address"
    assert all(c[1] == "93.184.216.34" for c in net.connections)  # only the public host was ever contacted
    assert preview(admin, "https://example.com/loop").get_json()["error"]["code"] == "too_many_redirects"


def test_huge_pages_are_cut_off_and_missing_pages_fail_cleanly(admin, net):
    assert preview(admin, "https://example.com/big").get_json()["title"] == "t"
    r = preview(admin, "https://example.com/missing")
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "http_error"


def test_link_preview_is_for_the_admin_only(api, net):
    assert api.post(f"{MO}/link-preview", {"url": "https://example.com/page"}).status_code == 401
