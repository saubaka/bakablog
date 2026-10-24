"""Site-wide facts the public API and the SEO shell share: names, navigation, theme, footer, canonical origin."""
from __future__ import annotations

from flask import has_request_context, request
from sqlalchemy.orm import Session

from app import defaults
from app.config import cfg
from app.models import Media
from app.services import nav, settings
from app.services.out import media_out
from app.timeutil import local, utcnow
from app.version import __version__, build_id


def origin() -> str:
    """Canonical origin: BLOG_SITE_URL when configured, otherwise the address this request came to."""
    if cfg().site_url:
        return cfg().site_url
    return request.host_url.rstrip("/") if has_request_context() else ""


def absolute(path: str) -> str:
    return f"{origin()}{path}" if path.startswith("/") else path


def _media(session: Session, media_id: int | None):
    if not media_id:
        return None
    media = session.get(Media, media_id)
    return media_out(media) if media is not None and media.deleted_at is None else None


def tz_name(session: Session) -> str:
    return settings.group(session, "site")["timezone"]


def payload(session: Session) -> dict:
    groups = settings.all_groups(session)
    site, author, look, seo, footer = groups["site"], groups["author"], groups["appearance"], groups["seo"], groups["footer"]
    year = local(utcnow(), site["timezone"]).year
    copyright_text = footer["copyright"] or f"© {year} {author['name']} · {site['name_en'] or site['name']}"
    return {
        "name": site["name"],
        "name_en": site["name_en"],
        "tagline": site["tagline"],
        "description": site["description"],
        "language": site["language"],
        "timezone": site["timezone"],
        "logo": _media(session, site["logo_media_id"]),
        "favicon": _media(session, site["favicon_media_id"]),
        "author": {"name": author["name"], "bio": author["bio"], "avatar": _media(session, author["avatar_media_id"]), "links": author["links"]},
        "theme": look["theme"],
        "decor": look["decor"],
        "motion": look["motion"],
        "code_theme": look["code_theme"],
        "texts": look["texts"],
        "seo": {"title": seo["title"], "description": seo["description"], "keywords": seo["keywords"], "share_image": _media(session, seo["share_image_media_id"])},
        "footer": {"icp": footer["icp"], "copyright": copyright_text, "text": footer["text"]},
        "nav": {region: nav.resolve(session, region) for region in defaults.NAV_REGIONS},
        "features": {"stats": groups["stats"]["enabled"], "search": True, "rss": True},
        "moods": [{"id": k, "label": v} for k, v in defaults.MOODS.items()],
        "origin": origin(),
        "version": __version__,
        "build": build_id(),
        "site_version": settings.site_version(session),
    }
