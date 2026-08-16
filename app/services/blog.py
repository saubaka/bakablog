"""Blog rendering, versioning, publication and local search services."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from uuid import uuid4

import bleach
from bleach.css_sanitizer import CSSSanitizer
from markdown import Markdown
from sqlalchemy import false, or_, text
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import Category, Post, PostVersion, Tag

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p",
    "pre",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "br",
    "img",
    "figure",
    "figcaption",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "div",
    "span",
    "dl",
    "dt",
    "dd",
    "u",
    "s",
    "mark",
    "font",
}
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": lambda tag, name, value: (
        value.startswith("/media/")
        if name == "src"
        else name in {"alt", "title", "width", "height", "loading", "decoding", "class"}
    ),
    "figure": ["class", "style"],
    "figcaption": ["class"],
    "font": ["size", "color"],
    "code": ["class"],
    "pre": ["class"],
    "div": ["class", "style"],
    "span": ["class", "style"],
    "p": ["style"],
    "blockquote": ["style"],
    "table": ["style"],
    "th": ["style"],
    "td": ["style"],
    "h1": ["id", "style"],
    "h2": ["id", "style"],
    "h3": ["id", "style"],
    "h4": ["id", "style"],
    "h5": ["id", "style"],
    "h6": ["id", "style"],
}
EDITOR_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties={"background-color", "color", "text-align", "width"}
)


def render_markdown(content: str) -> tuple[str, str, int]:
    renderer = Markdown(
        extensions=["extra", "admonition", "codehilite", "toc", "sane_lists"],
        extension_configs={
            "codehilite": {"css_class": "codehilite", "guess_lang": False},
            "toc": {"permalink": False, "toc_depth": "2-4"},
        },
        output_format="html5",
    )
    unsafe_html = renderer.convert(content)
    unsafe_html = re.sub(r"<img\b[^>]*>", _add_image_loading_hints, unsafe_html)
    clean_html = bleach.clean(
        unsafe_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        css_sanitizer=EDITOR_CSS_SANITIZER,
        strip=True,
    )
    clean_toc = bleach.clean(
        renderer.toc,
        tags={"div", "ul", "li", "a", "span"},
        attributes={"div": ["class"], "ul": ["class"], "li": ["class"], "a": ["href"]},
        strip=True,
    )
    character_count = len(re.sub(r"\s+", "", content))
    reading_minutes = max(1, round(character_count / 500))
    return clean_html, clean_toc, reading_minutes


def _add_image_loading_hints(match: re.Match[str]) -> str:
    tag = match.group(0)
    if " loading=" not in tag:
        tag = tag.replace("<img", '<img loading="lazy"', 1)
    if " decoding=" not in tag:
        tag = tag.replace("<img", '<img decoding="async"', 1)
    return tag


def make_slug(value: str, fallback_prefix: str = "post") -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[\s_]+", "-", normalized)
    normalized = re.sub(r"[^\w\-\u4e00-\u9fff]", "", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:160] or f"{fallback_prefix}-{uuid4().hex[:10]}"


def unique_post_slug(value: str, post_id: int | None = None) -> str:
    base = make_slug(value)
    candidate = base
    counter = 2
    while db.session.scalar(
        db.select(Post.id).where(Post.slug == candidate, Post.id != (post_id or -1))
    ):
        candidate = f"{base[:150]}-{counter}"
        counter += 1
    return candidate


def sync_tags(raw_tags: str) -> list[Tag]:
    names = [part.strip() for part in re.split(r"[,，]", raw_tags) if part.strip()]
    result: list[Tag] = []
    for name in dict.fromkeys(names[:12]):
        tag = db.session.scalar(db.select(Tag).where(db.func.lower(Tag.name) == name.lower()))
        if tag is None:
            base_slug = make_slug(name, "tag")
            slug = _unique_taxonomy_slug(Tag, base_slug)
            tag = Tag(name=name[:50], slug=slug)
            db.session.add(tag)
        result.append(tag)
    return result


def apply_post_form(post: Post, form, actor_id: int) -> None:  # type: ignore[no-untyped-def]
    html, toc, minutes = render_markdown(form.content_markdown.data)
    post.title = form.title.data.strip()
    post.slug = unique_post_slug(form.slug.data or post.title, post.id)
    post.summary = (form.summary.data or "").strip()
    post.content_markdown = form.content_markdown.data
    post.content_html = html
    post.toc_html = toc
    post.reading_minutes = minutes
    post.category_id = form.category_id.data or None
    post.tags = sync_tags(form.tags.data or "")
    post.is_pinned = bool(form.is_pinned.data)
    post.is_featured = bool(form.is_featured.data)
    post.seo_title = (form.seo_title.data or "").strip()
    post.seo_description = (form.seo_description.data or "").strip()
    post.status = form.status.data
    if post.status == "published":
        post.published_at = form.published_at.data or post.published_at or datetime.now(UTC)
    elif post.status == "scheduled":
        scheduled = form.published_at.data
        post.published_at = (
            scheduled.replace(tzinfo=UTC) if scheduled and not scheduled.tzinfo else scheduled
        )
    else:
        post.published_at = None
    post.author_id = post.author_id or actor_id


def create_version(post: Post, actor_id: int) -> PostVersion:
    latest = db.session.scalar(
        db.select(db.func.max(PostVersion.version_number)).where(PostVersion.post_id == post.id)
    )
    version = PostVersion(
        post_id=post.id,
        version_number=(latest or 0) + 1,
        title=post.title,
        summary=post.summary,
        content_markdown=post.content_markdown,
        status=post.status,
        created_by_id=actor_id,
    )
    db.session.add(version)
    return version


def public_post_condition(now: datetime | None = None):  # type: ignore[no-untyped-def]
    current = now or datetime.now(UTC)
    return db.and_(
        Post.deleted_at.is_(None),
        Post.published_at.is_not(None),
        Post.published_at <= current,
        Post.status.in_(("published", "scheduled")),
    )


def search_post_ids(query: str) -> tuple[list[int] | None, bool]:
    terms = " ".join(part for part in re.split(r"\s+", query.strip()) if part)
    if not terms:
        return None, True
    try:
        rows = db.session.execute(
            text(
                "SELECT rowid FROM posts_fts WHERE posts_fts MATCH :query ORDER BY bm25(posts_fts)"
            ),
            {"query": terms},
        ).scalars()
        return list(rows), True
    except OperationalError:
        db.session.rollback()
        return None, False


def apply_search(statement, query: str):  # type: ignore[no-untyped-def]
    ids, used_fts = search_post_ids(query)
    if ids is not None:
        return statement.where(Post.id.in_(ids) if ids else false()), used_fts
    pattern = f"%{query.strip()}%"
    return statement.where(
        or_(
            Post.title.ilike(pattern),
            Post.summary.ilike(pattern),
            Post.content_markdown.ilike(pattern),
        )
    ), used_fts


def create_taxonomy(taxonomy_type: str, name: str, slug_value: str, description: str = ""):
    model = Category if taxonomy_type == "category" else Tag
    slug = _unique_taxonomy_slug(model, make_slug(slug_value or name, taxonomy_type))
    existing = db.session.scalar(db.select(model).where(db.func.lower(model.name) == name.lower()))
    if existing:
        return existing, False
    values = {"name": name, "slug": slug}
    if model is Category:
        values["description"] = description
    item = model(**values)
    db.session.add(item)
    return item, True


def _unique_taxonomy_slug(model, base: str) -> str:  # type: ignore[no-untyped-def]
    candidate = base
    counter = 2
    while db.session.scalar(db.select(model.id).where(model.slug == candidate)):
        candidate = f"{base[:90]}-{counter}"
        counter += 1
    return candidate
