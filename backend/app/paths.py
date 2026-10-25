"""Public URL scheme, defined once. The sitemap, search results, navigation and the Vue router all follow it."""
from __future__ import annotations

# Slugs a standalone page may not use: they are real routes or prefixes of the app.
RESERVED_PAGE_SLUGS = frozenset({
    "blog", "moments", "archive", "search", "category", "tag", "series", "admin", "api", "media", "assets",
    "static", "sitemap.xml", "robots.txt", "favicon.ico", "setup", "login", "logout", "404", "500", "index", "p",
})


def home() -> str:
    return "/"


def post(slug: str) -> str:
    return f"/blog/{slug}"


def moment(moment_id: int) -> str:
    return f"/moments/{moment_id}"


def page(slug: str) -> str:
    return f"/{slug}"


def category(slug: str) -> str:
    return f"/category/{slug}"


def tag(slug: str) -> str:
    return f"/tag/{slug}"


def series(slug: str) -> str:
    return f"/series/{slug}"


def media(media_hash: str, size: int | str) -> str:
    return f"/media/{media_hash}/{size}.webp"
