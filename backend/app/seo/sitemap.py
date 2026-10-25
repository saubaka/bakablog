"""sitemap.xml and robots.txt."""
from __future__ import annotations

from xml.sax.saxutils import escape

from flask import Blueprint, Response
from sqlalchemy import select

from app import paths
from app.db import db
from app.models import Moment, Page, Post
from app.services import queries, settings, site
from app.services import visibility as vis
from app.timeutil import iso

bp = Blueprint("seo_sitemap", __name__)


def _xml(body: str, mimetype: str = "application/xml") -> Response:
    response = Response(body, mimetype=mimetype)
    response.headers["Cache-Control"] = "public, max-age=300"
    response.headers["Content-Type"] = f"{mimetype}; charset=utf-8"
    return response


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
    return _xml("".join(body))


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

