"""RSS (posts, moments), sitemap.xml and robots.txt."""
from __future__ import annotations

import re
from email.utils import format_datetime
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import defaults, paths
from app.db import db
from app.models import Category, Moment, Page, Post, Series, Tag
from app.services import markdown as md
from app.services import queries, settings, site
from app.services import visibility as vis
from app.timeutil import as_utc, iso, utcnow

bp = Blueprint("seo_feeds", __name__)

_ABS_ATTR = re.compile(r'(\s(?:src|href|data-full)=")(/(?!/))')
_ABS_SRCSET = re.compile(r'(\ssrcset=")([^"]*)"')


def absolutize(html: str, origin: str) -> str:
    """Feed readers show the HTML elsewhere: site-relative links and pictures must become absolute."""
    def srcset(m: re.Match) -> str:
        parts = [(origin + p.strip() if p.strip().startswith("/") else p.strip()) for p in m.group(2).split(",")]
        return f'{m.group(1)}{", ".join(parts)}"'

    html = _ABS_ATTR.sub(lambda m: f"{m.group(1)}{origin}{m.group(2)}", html)
    return _ABS_SRCSET.sub(srcset, html)


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _rfc822(value) -> str:
    return format_datetime(as_utc(value))


def _xml(body: str, mimetype: str = "application/rss+xml") -> Response:
    response = Response(body, mimetype=mimetype)
    response.headers["Cache-Control"] = "public, max-age=300"
    response.headers["Content-Type"] = f"{mimetype}; charset=utf-8"
    return response


def _channel(title: str, description: str, link: str, self_url: str, language: str, items: str, updated) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">\n<channel>\n'
        f"<title>{escape(title)}</title>\n<link>{escape(link)}</link>\n<description>{escape(description)}</description>\n"
        f"<language>{escape(language)}</language>\n<lastBuildDate>{_rfc822(updated)}</lastBuildDate>\n"
        f'<atom:link href="{escape(self_url)}" rel="self" type="application/rss+xml"/>\n<generator>{escape(defaults.SITE_NAME_EN)}</generator>\n'
        f"{items}</channel>\n</rss>\n"
    )


@bp.get("/feed/posts.xml")
def posts_feed():
    session = db()
    s = site.payload(session)
    conf = settings.group(session, "seo")["rss"]
    origin = s["origin"]
    rows = list(session.scalars(select(Post).where(vis.post_listed()).options(selectinload(Post.tags), selectinload(Post.category))
                                .order_by(Post.published_at.desc(), Post.id.desc()).limit(conf["items"])))
    items = []
    for p in rows:
        link = f"{origin}{paths.post(p.slug)}"
        cats = ([p.category.name] if p.category else []) + [t.name for t in p.tags]
        body = (f"<content:encoded>{_cdata(absolutize(p.content_html, origin))}</content:encoded>\n" if conf["full_text"] else "")
        items.append(
            f"<item>\n<title>{escape(p.title)}</title>\n<link>{escape(link)}</link>\n<guid isPermaLink=\"true\">{escape(link)}</guid>\n"
            f"<pubDate>{_rfc822(p.published_at)}</pubDate>\n<description>{escape(p.summary)}</description>\n{body}"
            + "".join(f"<category>{escape(c)}</category>\n" for c in cats) + "</item>\n"
        )
    updated = rows[0].updated_at if rows else utcnow()
    return _xml(_channel(f"{s['name']} · 文章", s["description"], origin + "/", f"{origin}/feed/posts.xml", s["language"], "".join(items), updated))


@bp.get("/feed/moments.xml")
def moments_feed():
    session = db()
    s = site.payload(session)
    origin = s["origin"]
    rows = queries.latest_moments(session, settings.group(session, "seo")["rss"]["items"])
    items = []
    for m in rows:
        text = md.html_to_text(m.content_html)
        title = (text[:40] + ("…" if len(text) > 40 else "")) or ("（图片）" if m.media else (m.link_card or {}).get("title", "动态"))
        link = f"{origin}{paths.moment(m.id)}"
        pictures = "".join(f'<p><img src="{origin}{paths.media(i.image.hash, 960)}" alt="{escape(i.alt or i.image.alt, {chr(34): "&quot;"})}"></p>' for i in m.media if i.image)
        card = f'<p><a href="{escape((m.link_card or {}).get("url", ""))}">{escape((m.link_card or {}).get("title", ""))}</a></p>' if m.link_card else ""
        items.append(
            f"<item>\n<title>{escape(title)}</title>\n<link>{escape(link)}</link>\n<guid isPermaLink=\"true\">{escape(link)}</guid>\n"
            f"<pubDate>{_rfc822(m.published_at)}</pubDate>\n<description>{_cdata(absolutize(m.content_html, origin) + pictures + card)}</description>\n</item>\n"
        )
    updated = rows[0].updated_at if rows else utcnow()
    return _xml(_channel(f"{s['name']} · 动态", s["description"], f"{origin}/moments", f"{origin}/feed/moments.xml", s["language"], "".join(items), updated))


@bp.get("/sitemap.xml")
def sitemap():
    session = db()
    origin = site.origin()
    conf = settings.group(session, "seo")["sitemap"]
    urls: list[tuple[str, str | None]] = [(origin + p, None) for p in ("/", "/blog", "/moments", "/archive")]
    for post in session.scalars(select(Post).where(vis.post_listed()).order_by(Post.published_at.desc())):
        urls.append((origin + paths.post(post.slug), iso(post.updated_at)))
    if conf["pages"]:
        for page in session.scalars(select(Page).where(vis.page_listed())):
            urls.append((origin + paths.page(page.slug), iso(page.updated_at)))
    if conf["moments"]:
        for moment in session.scalars(select(Moment).where(vis.moment_listed()).order_by(Moment.published_at.desc()).limit(5000)):
            urls.append((origin + paths.moment(moment.id), iso(moment.updated_at)))
    if conf["taxonomy"]:
        public = queries.public_taxonomy(session)
        urls += [(origin + paths.category(c["slug"]), None) for c in public["categories"]]
        urls += [(origin + paths.tag(t["slug"]), None) for t in public["tags"] if t["count"]]
        urls += [(origin + paths.series(s["slug"]), None) for s in public["series"]]
    body = ['<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n']
    for loc, lastmod in urls:
        body.append(f"<url><loc>{escape(loc)}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "") + "</url>\n")
    body.append("</urlset>\n")
    return _xml("".join(body), "application/xml")


@bp.get("/robots.txt")
def robots():
    session = db()
    extra = settings.group(session, "seo")["robots_extra"]
    lines = ["User-agent: *", "Allow: /", "Disallow: /api/", "Disallow: /admin"]
    if extra:
        lines += extra.splitlines()
    lines += ["", f"Sitemap: {site.origin()}/sitemap.xml", ""]
    response = Response("\n".join(lines), mimetype="text/plain")
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


_ = (Category, Series, Tag, request)
