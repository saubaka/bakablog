"""Single-page-app shell with server-side SEO.

Every public address gets the built Vue shell (frontend/dist/public.html) with
  <!--bb:head-->  replaced by the real <title>, description, canonical, Open Graph / Twitter tags, JSON-LD,
  <!--bb:data-->  replaced by the first-screen data as an inert JSON block (the app starts from it: no extra request),
  <!--bb:ssr-->   replaced by a semantic copy of the content (for crawlers, link previews and visitors without JavaScript).
Unknown addresses answer 404 with the same shell, so the app draws its own 404 page. Redirects (301 / 302) are applied first.
If no frontend has been built yet, a small built-in shell is used, which is also what the tests exercise.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

from flask import Blueprint, Response, redirect, request, send_from_directory
from pydantic import ValidationError
from sqlalchemy import select

from app import defaults, paths
from app.api import public as public_api
from app.config import cfg
from app.db import db
from app.errors import ApiError
from app.models import Category, Series, Tag
from app.security import CSP_ADMIN
from app.services import home, queries, redirects, settings, site
from app.services import posts as posts_service
from app.services.out import media_out, moment_out
from app.timeutil import iso, utcnow

bp = Blueprint("seo_spa", __name__)
esc = html_lib.escape

BUILTIN_SHELL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!--bb:head-->
</head>
<body>
<div id="app"><!--bb:ssr--></div>
<!--bb:data-->
</body>
</html>
"""
BUILTIN_ADMIN = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>管理后台</title></head>
<body><div id="app"><p>管理后台的前端还没有构建（阶段 P3）。API 已经可以使用：/api/admin/…</p></div></body></html>
"""
BUILTIN_PREVIEW = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>预览</title></head>
<body><p>预览页还没有构建。</p></body></html>
"""
PREVIEW_PATH = "/admin/preview-frame"
_shell_cache: dict[str, tuple[float, str]] = {}
# cards per page of the list pages: nine fill the front end's card grid in whole rows (frontend/src/public/data.ts PER_PAGE)
SHELL_PER_PAGE = 9


def _shell(name: str) -> str:
    dist: Path | None = cfg().frontend_dist
    if dist is not None:
        path = dist / f"{name}.html"
        if path.is_file():
            mtime = path.stat().st_mtime
            cached = _shell_cache.get(str(path))
            if cached is None or cached[0] != mtime:
                _shell_cache[str(path)] = (mtime, path.read_text(encoding="utf-8"))
            return _shell_cache[str(path)][1]
    return {"public": BUILTIN_SHELL, "preview": BUILTIN_PREVIEW}.get(name, BUILTIN_ADMIN)


# ---- the description of one public route ----------------------------------------------------------------------------------------------
@dataclass
class Page:
    kind: str
    title: str
    description: str = ""
    path: str = "/"
    status: int = 200
    noindex: bool = False
    og_type: str = "website"
    image: dict | None = None
    canonical: str = ""
    jsonld: list[dict] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)     # more first-screen keys next to "data" (the list pages inline the taxonomy)
    body: str = ""            # semantic HTML for <main>
    no_store: bool = False


def _json_script(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f'<script id="bb-data" type="application/json">{payload}</script>'


def _abs_image(image: dict | None) -> tuple[str, int, int]:
    if not image:
        return "", 0, 0
    return site.absolute(image["src"]), image.get("width", 0), image.get("height", 0)


def _head(s: dict, page: Page) -> str:
    name = s["name"]
    title = page.title if page.kind == "home" else f"{page.title} · {name}"
    canonical = page.canonical or site.absolute(page.path)
    desc = (page.description or s["seo"]["description"] or s["description"])[:300]
    image = page.image or s["seo"]["share_image"]
    img_url, img_w, img_h = _abs_image(image)
    favicon = s["favicon"]["src"] if s["favicon"] else "/favicon.svg"
    tags = [
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(desc, quote=True)}">',
        f'<link rel="canonical" href="{esc(canonical, quote=True)}">',
        '<meta name="robots" content="noindex,nofollow">' if page.noindex else '<meta name="robots" content="index,follow,max-image-preview:large">',
        f'<meta property="og:type" content="{page.og_type}">',
        f'<meta property="og:site_name" content="{esc(name, quote=True)}">',
        f'<meta property="og:title" content="{esc(title, quote=True)}">',
        f'<meta property="og:description" content="{esc(desc, quote=True)}">',
        f'<meta property="og:url" content="{esc(canonical, quote=True)}">',
        f'<meta property="og:locale" content="{esc(s["language"].replace("-", "_"), quote=True)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if img_url else "summary"}">',
        f'<meta name="twitter:title" content="{esc(title, quote=True)}">',
        f'<meta name="twitter:description" content="{esc(desc, quote=True)}">',
    ]
    if img_url:
        tags += [f'<meta property="og:image" content="{esc(img_url, quote=True)}">', f'<meta name="twitter:image" content="{esc(img_url, quote=True)}">']
        if img_w and img_h:
            tags += [f'<meta property="og:image:width" content="{img_w}">', f'<meta property="og:image:height" content="{img_h}">']
    tags += [
        f'<link rel="icon" href="{esc(favicon, quote=True)}">',
        '<meta name="theme-color" content="#f7fbff">',
    ]
    for block in page.jsonld:
        text = json.dumps(block, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        tags.append(f'<script type="application/ld+json">{text}</script>')
    return "\n".join(tags)


def _frame(s: dict, body: str) -> str:
    links = "".join(f'<li><a href="{esc(i["url"], quote=True)}">{esc(i["label"])}</a></li>' for i in s["nav"]["top"] if i["url"])
    return (f'<header><a href="/">{esc(s["name"])}</a><nav aria-label="主导航"><ul>{links}</ul></nav></header>'
            f'<main id="main" tabindex="-1">{body}</main><footer><p>{esc(s["footer"]["copyright"])}</p></footer>')


def _render(page: Page) -> Response:
    session = db()
    s = site.payload(session)
    shell = _shell("public")
    head = _head(s, page)
    data = _json_script({"path": page.path, "kind": page.kind, "status": page.status, "site": s, "data": page.data, **page.extra})
    ssr = _frame(s, page.body)
    if "<!--bb:head-->" in shell:
        shell = shell.replace("<!--bb:head-->", head)
    else:
        shell = shell.replace("</head>", head + "\n</head>", 1)
    if "<!--bb:ssr-->" in shell:
        shell = shell.replace("<!--bb:ssr-->", ssr)
    else:
        shell = re.sub(r'(<div id="app">)(\s*)(</div>)', lambda m: m.group(1) + ssr + m.group(3), shell, count=1)
    if "<!--bb:data-->" in shell:
        shell = shell.replace("<!--bb:data-->", data)
    else:
        shell = shell.replace("</body>", data + "\n</body>", 1)
    shell = re.sub(r"<html\b([^>]*?)\blang=\"[^\"]*\"", lambda m: f'<html{m.group(1)}lang="{esc(s["language"], quote=True)}"', shell, count=1)
    response = Response(shell, status=page.status, mimetype="text/html")
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store" if page.no_store else "no-cache"
    if page.status == 200 and not page.no_store:
        tag = hashlib.blake2b(shell.encode("utf-8"), digest_size=10).hexdigest()
        response.headers["ETag"] = f'W/"{tag}"'
        if request.if_none_match.contains_weak(tag):
            response = Response(status=304, headers={"ETag": f'W/"{tag}"', "Cache-Control": "no-cache"})
    if page.noindex:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ---- body builders (semantic HTML copies) -----------------------------------------------------------------------------------------------------
def _li_post(p: dict) -> str:
    return (f'<li><a href="{esc(p["url"], quote=True)}"><strong>{esc(p["title"])}</strong></a>'
            f'<p>{esc(p["summary"])}</p><time datetime="{esc(p["published_at"] or "")}">{esc((p["published_at"] or "")[:10])}</time></li>')


def _post_list(items: list[dict]) -> str:
    return "<ul>" + "".join(_li_post(p) for p in items) + "</ul>" if items else "<p>这里还没有文章。</p>"


def _pager(data: dict, base: str, extra: dict) -> str:
    links = []
    for label, n in (("上一页", data["page"] - 1), ("下一页", data["page"] + 1)):
        if 1 <= n <= data["pages"] and n != data["page"]:
            qs = urlencode({**extra, **({"page": n} if n > 1 else {})})
            links.append(f'<a href="{base}{"?" + qs if qs else ""}" rel="{"prev" if n < data["page"] else "next"}">{label}</a>')
    return "<nav aria-label=\"分页\">" + " ".join(links) + "</nav>" if links else ""


def _moment_li(m: dict) -> str:
    text = esc(m["text"]) or ("（图片）" if m["media"] else "")
    pics = "".join(f'<img src="{esc(i["src"], quote=True)}" alt="{esc(i["alt"], quote=True)}" width="{i["width"]}" height="{i["height"]}">' for i in m["media"][:3])
    return f'<li><a href="{esc(m["url"], quote=True)}"><time datetime="{esc(m["published_at"] or "")}">{esc((m["published_at"] or "")[:10])}</time></a><p>{text}</p>{pics}</li>'


# ---- routing ------------------------------------------------------------------------------------------------------------------------------------
def _query(model):
    """Query string of an HTML page: values that do not validate are ignored (a page should still open), unlike the JSON API."""
    data = request.args.to_dict()
    for _ in range(6):
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            for err in exc.errors():
                data.pop(str(err["loc"][0]) if err["loc"] else "", None)
    return model.model_validate({})


def _not_found(texts: dict | None = None, path: str | None = None) -> Page:
    session = db()
    texts = texts or settings.group(session, "appearance")["texts"]
    body = (f"<h1>{esc(texts['not_found_title'])}</h1><p>{esc(texts['not_found_text'])}</p><h2>最近的文章</h2>"
            + _post_list([public_api.post_card(p) for p in queries.latest_posts(session, 5)]))
    return Page("404", texts["not_found_title"], texts["not_found_text"], path or request.path, status=404, noindex=True, body=body,
                data={"not_found": True, "recent": [public_api.post_card(p) for p in queries.latest_posts(session, 3)]})


def not_found_page() -> Response:
    """Called for 404s of HTML requests (errors.py)."""
    return _render(_not_found())


def server_error_page() -> Response:
    texts = settings.group(db(), "appearance")["texts"]
    page = Page("500", texts["error_title"], texts["error_text"], request.path, status=500, noindex=True,
                body=f"<h1>{esc(texts['error_title'])}</h1><p>{esc(texts['error_text'])}</p>", no_store=True)
    try:
        return _render(page)
    except Exception:  # noqa: BLE001 - the error page itself must never fail
        return Response(f"<!doctype html><meta charset=utf-8><title>{esc(texts['error_title'])}</title><h1>{esc(texts['error_title'])}</h1>",
                        status=500, mimetype="text/html")


def _home(s: dict) -> Page:
    session = db()
    blocks = home.resolve_public(session)
    hero = next((b for b in blocks if b["type"] == "hero"), None)
    lines = f"{s['name']} {s['name_en']}".strip() if hero else s["name"]
    latest = next((b for b in blocks if b["type"] == "latest_posts"), None)
    moments_block = next((b for b in blocks if b["type"] == "latest_moments"), None)
    body = f"<h1>{esc(lines)}</h1>" + (f"<p>{esc(hero['config'].get('intro', ''))}</p>" if hero else "")
    if latest:
        body += f"<h2>{esc(latest['config'].get('title', '最近的文章'))}</h2>" + _post_list(latest["data"]["posts"])
    if moments_block:
        body += f"<h2>{esc(moments_block['config'].get('title', '最近的动态'))}</h2><ul>" + "".join(_moment_li(m) for m in moments_block["data"]["moments"]) + "</ul>"
    title = f"{s['name']} · {s['tagline']}" if s["tagline"] else s["name"]
    jsonld = [{"@context": "https://schema.org", "@type": "WebSite", "name": s["name"], "url": s["origin"] + "/", "description": s["description"],
               "inLanguage": s["language"], "author": {"@type": "Person", "name": s["author"]["name"]}}]
    return Page("home", title, s["seo"]["description"] or s["description"], "/", jsonld=jsonld, data={"blocks": blocks}, body=body)


def _list_query(**force) -> public_api.PostsQuery:
    """The list pages' query: lenient like every HTML page, the front end's page size unless the address names one."""
    q = _query(public_api.PostsQuery)
    update = dict(force)
    if "per" not in request.args:
        update["per"] = SHELL_PER_PAGE
    return q.model_copy(update=update)


def _blog(s: dict) -> Page:
    session = db()
    q = _list_query()
    payload = public_api.posts_list_payload(session, q)
    filtered = bool(q.q or q.sort != "new" or q.category or q.tag or q.series)
    extra = {k: v for k, v in (("category", q.category), ("tag", q.tag), ("series", q.series), ("q", q.q), ("sort", q.sort if q.sort != "new" else None)) if v}
    title = "博客" + (f" · 第 {payload['page']} 页" if payload["page"] > 1 else "")
    path = "/blog" + ("?" + urlencode({**extra, "page": payload["page"]}) if payload["page"] > 1 or extra else "")
    body = f"<h1>博客</h1>{_post_list(payload['items'])}{_pager(payload, '/blog', extra)}"
    return Page("blog", title, "代码、设计、日常。", "/blog", canonical=site.absolute(path if not filtered else "/blog"), noindex=filtered,
                data=payload, body=body, extra={"taxonomy": queries.public_taxonomy(session)})


def _taxonomy_page(kind: str, slug: str) -> Page:
    session = db()
    model = {"category": Category, "tag": Tag, "series": Series}[kind]
    row = session.scalar(select(model).where(model.slug == slug))
    if row is None:
        return _not_found()
    q = _list_query(**{kind: slug, "q": None})
    page = q.page
    payload = public_api.posts_list_payload(session, q)
    name = row.title if kind == "series" else row.name
    description = (getattr(row, "description", "") or "") or f"“{name}”下的文章"
    label = {"category": "分类", "tag": "标签", "series": "系列"}[kind]
    base = {"category": paths.category, "tag": paths.tag, "series": paths.series}[kind](slug)
    body = f"<h1>{label}：{esc(name)}</h1><p>{esc(description)}</p>{_post_list(payload['items'])}{_pager(payload, base, {})}"
    title = f"{name}" + (f" · 第 {page} 页" if page > 1 else "")
    sorted_ = q.sort != "new"
    return Page("taxonomy", title, description, base, canonical=site.absolute(base + (f"?page={page}" if page > 1 and not sorted_ else "")), noindex=sorted_,
                data={**payload, "kind": kind}, body=body, extra={"taxonomy": queries.public_taxonomy(session)})


def _post(slug: str) -> Page:
    session = db()
    token = request.args.get("preview")
    preview_id = posts_service.verify_preview_token(token) if token else None
    post = queries.post_by_slug(session, slug, preview_id=preview_id)
    if post is None:
        return _not_found()
    is_preview = preview_id is not None and (post.status != "published" or (post.published_at is not None and post.published_at > utcnow()))
    detail = public_api._post_detail(session, post, preview=is_preview)
    seo = detail["seo"]
    body = (f"<article><h1>{esc(post.title)}</h1><p><time datetime=\"{esc(detail['published_at'] or '')}\">{esc((detail['published_at'] or '')[:10])}</time>"
            f" · {post.reading_minutes} 分钟</p>{post.content_html}</article>")
    jsonld = [{
        "@context": "https://schema.org", "@type": "BlogPosting", "headline": post.title, "description": seo["description"],
        "datePublished": detail["published_at"], "dateModified": detail["updated_at"], "inLanguage": site.payload(session)["language"],
        "mainEntityOfPage": seo["canonical"], "author": {"@type": "Person", "name": site.payload(session)["author"]["name"]},
        **({"image": [site.absolute(seo["image"]["src"])]} if seo["image"] else {}),
        **({"keywords": ", ".join(t.name for t in post.tags)} if post.tags else {}),
    }]
    return Page("post", seo["title"], seo["description"], paths.post(post.slug), noindex=seo["noindex"], og_type="article", image=seo["image"],
                canonical=seo["canonical"], jsonld=jsonld, data=detail, body=body, no_store=is_preview)


def _archive() -> Page:
    session = db()
    years = queries.archive(session, site.tz_name(session))
    body = "<h1>归档</h1>" + "".join(
        f"<h2>{y['year']}</h2>" + "".join(f"<h3>{m['month']} 月</h3><ul>" + "".join(
            f'<li><a href="{esc(p["url"], quote=True)}">{esc(p["title"])}</a></li>' for p in m["posts"]) + "</ul>" for m in y["months"]) for y in years)
    return Page("archive", "归档", "按年月看所有文章。", "/archive", data={"years": years, "total": sum(y["count"] for y in years)}, body=body)


def _moments() -> Page:
    session = db()
    q = _query(public_api.MomentsQuery)
    tz = site.tz_name(session)
    from app.timeutil import month_bounds

    rows, next_cursor = queries.moments_page(session, cursor=q.cursor, limit=q.limit, tag=q.tag, mood=q.mood,
                                             month_range=month_bounds(q.month, tz) if q.month else None)
    data = {"items": [moment_out(m) for m in rows], "next_cursor": next_cursor}
    if not q.cursor:
        data["pinned"] = [moment_out(m) for m in queries.pinned_moments(session)]
        data["meta"] = queries.moments_meta(session, tz)
    filtered = bool(q.tag or q.mood or q.month or q.cursor)
    body = "<h1>碎碎念</h1><ul>" + "".join(_moment_li(m) for m in data["items"]) + "</ul>"
    return Page("moments", "动态", "想到什么发什么：一句话、几张照片、一个链接。", "/moments", noindex=filtered, canonical=site.absolute("/moments"), data=data, body=body)


def _moment(moment_id: int) -> Page:
    session = db()
    moment = queries.moment_by_id(session, moment_id)
    if moment is None:
        return _not_found()
    data = moment_out(moment)
    text = data["text"] or ("（图片）" if data["media"] else (data["link_card"] or {}).get("title", "动态"))
    image = data["media"][0] if data["media"] else None
    return Page("moment", f"{text[:40]} · 动态", text[:160], paths.moment(moment.id), noindex=moment.visibility != "public", og_type="article", image=image,
                data=data, body=f"<article>{_moment_li(data)}</article>")


def _page(slug: str) -> Page:
    session = db()
    page = queries.page_by_slug(session, slug)
    if page is None:
        return _not_found()
    seo = {"title": page.seo_title or page.title, "description": page.seo_description or "", "image": media_out(page.seo_image)}
    data = {"id": page.id, "slug": page.slug, "url": paths.page(page.slug), "title": page.title, "html": page.content_html, "toc": page.toc,
            "template": page.template, "updated_at": iso(page.updated_at), "seo": seo}
    return Page("page", seo["title"], seo["description"] or page.title, paths.page(page.slug), noindex=page.status != "published", image=seo["image"],
                data=data, body=f"<article><h1>{esc(page.title)}</h1>{page.content_html}</article>")


_SIMPLE = {"/": "home", "/blog": "blog", "/archive": "archive", "/moments": "moments", "/search": "search"}


def resolve(path: str) -> Page:
    session = db()
    s = site.payload(session)
    if path == "/":
        return _home(s)
    parts = path.strip("/").split("/")
    head = parts[0]
    if path == "/blog":
        return _blog(s)
    if path == "/archive":
        return _archive()
    if path == "/moments":
        return _moments()
    if path == "/search":
        return Page("search", "搜索", "在文章、动态和页面里找东西。", "/search", noindex=True, body="<h1>搜索</h1>",
                    data={"q": request.args.get("q", "")[:100]})
    if head == "blog" and len(parts) == 2:
        return _post(parts[1])
    if head in ("category", "tag", "series") and len(parts) == 2:
        return _taxonomy_page(head, parts[1])
    if head == "moments" and len(parts) == 2 and parts[1].isdigit():
        return _moment(int(parts[1]))
    if len(parts) == 1 and head not in paths.RESERVED_PAGE_SLUGS:
        return _page(head)
    return _not_found(path=path)


# ---- Flask routes -------------------------------------------------------------------------------------------------------------------------------
def _clean(path: str) -> str:
    """"/a//b/" -> "/a/b". Only non-empty segments are kept, so the result always starts with exactly one "/"."""
    return "/" + "/".join(seg for seg in path.split("/") if seg)


@bp.get("/", defaults={"path": ""})
@bp.get("/<path:path>")
def public_page(path: str):
    if path.startswith(("api/", "media/")) or path in ("api", "media"):
        raise ApiError(404)
    raw = "/" + path
    full = _clean(path)
    if full == PREVIEW_PATH:
        return preview_shell()
    if full == "/admin" or full.startswith("/admin/"):
        return admin_shell()
    if raw != full:  # a trailing slash or doubled slashes: one canonical address, rebuilt from segments so it can never start with "//"
        return redirect(full + (f"?{request.query_string.decode()}" if request.query_string else ""), code=301)
    session = db()
    moved = redirects.resolve(session, full)
    if moved is not None:
        target, status, redirect_id = moved
        redirects.record_hit(session, redirect_id)
        session.commit()
        return redirect(target, code=status)
    return _render(resolve(full))


def admin_shell() -> Response:
    response = Response(_shell("admin"), mimetype="text/html")
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def preview_shell() -> Response:
    """The page the admin's "preview" frames show (a real public page fed by postMessage). The only page that may be framed, and only by this site."""
    response = Response(_shell("preview"), mimetype="text/html")
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = CSP_ADMIN.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
    return response


_STATIC_ROOT = {"favicon.ico", "favicon.svg", "apple-touch-icon.png", "manifest.webmanifest", "site.webmanifest"}


@bp.get("/assets/<path:filename>")
def assets(filename: str):
    dist = cfg().frontend_dist
    if dist is None or not (dist / "assets").is_dir():
        raise ApiError(404)
    response = send_from_directory(dist / "assets", filename, max_age=31536000)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@bp.get("/<name>")
def root_static(name: str):
    if name in _STATIC_ROOT:
        dist = cfg().frontend_dist
        if dist is not None and (dist / name).is_file():
            response = send_from_directory(dist, name, max_age=86400)
            return response
        if name == "favicon.ico":
            return Response(status=204)
    return public_page(name)


_ = (defaults, media_out)
