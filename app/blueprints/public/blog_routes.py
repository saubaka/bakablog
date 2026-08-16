"""Public blog discovery, reading and machine-readable feeds."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from flask import Response, abort, current_app, redirect, render_template, request, url_for

from app.blueprints.public import public_bp
from app.extensions import db
from app.forms import CommentForm, EmptyForm
from app.models import (
    Album,
    Category,
    Comment,
    CustomPage,
    Moment,
    Post,
    Project,
    Tag,
)
from app.services.blog import apply_search, public_post_condition
from app.services.content import public_moment_condition, public_project_condition


def _base_statement():
    return db.select(Post).where(public_post_condition())


@public_bp.get("/blog/")
def blog():
    query = request.args.get("q", "").strip()[:100]
    category_slug = request.args.get("category", "").strip()
    tag_slug = request.args.get("tag", "").strip()
    statement = _base_statement()
    category = None
    tag = None
    used_fts = None
    if category_slug:
        category = db.session.scalar(db.select(Category).where(Category.slug == category_slug))
        if category is None:
            abort(404)
        statement = statement.where(Post.category_id == category.id)
    if tag_slug:
        tag = db.session.scalar(db.select(Tag).where(Tag.slug == tag_slug))
        if tag is None:
            abort(404)
        statement = statement.where(Post.tags.any(Tag.id == tag.id))
    if query:
        statement, used_fts = apply_search(statement, query)
    statement = statement.order_by(Post.is_pinned.desc(), Post.published_at.desc())
    page = db.paginate(
        statement,
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["POSTS_PER_PAGE"],
        error_out=False,
    )
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    tags = db.session.scalars(db.select(Tag).order_by(Tag.name).limit(24)).all()
    return render_template(
        "blog/list.html",
        page=page,
        posts=page.items,
        categories=categories,
        tags=tags,
        selected_category=category,
        selected_tag=tag,
        query=query,
        used_fts=used_fts,
    )


@public_bp.get("/blog/category/<slug>/")
def blog_category(slug: str):
    return redirect(url_for("public.blog", category=slug), code=302)


@public_bp.get("/blog/tag/<slug>/")
def blog_tag(slug: str):
    return redirect(url_for("public.blog", tag=slug), code=302)


@public_bp.get("/blog/archive/")
def blog_archive():
    posts = db.session.scalars(_base_statement().order_by(Post.published_at.desc())).all()
    grouped: dict[str, list[Post]] = {}
    for post in posts:
        key = post.published_at.strftime("%Y年%m月")
        grouped.setdefault(key, []).append(post)
    return render_template("blog/archive.html", grouped=grouped, year=None, month=None)


@public_bp.get("/blog/archive/<int:year>/<int:month>/")
def blog_archive_month(year: int, month: int):
    if not 1 <= month <= 12:
        abort(404)
    statement = _base_statement().where(
        db.func.strftime("%Y", Post.published_at) == str(year),
        db.func.strftime("%m", Post.published_at) == f"{month:02d}",
    )
    posts = db.session.scalars(statement.order_by(Post.published_at.desc())).all()
    return render_template(
        "blog/archive.html", grouped={f"{year}年{month:02d}月": posts}, year=year, month=month
    )


@public_bp.get("/blog/<slug>/")
def article(slug: str):
    post = db.session.scalar(_base_statement().where(Post.slug == slug))
    if post is None:
        abort(404)
    previous_post = db.session.scalar(
        _base_statement()
        .where(Post.published_at < post.published_at)
        .order_by(Post.published_at.desc())
        .limit(1)
    )
    next_post = db.session.scalar(
        _base_statement()
        .where(Post.published_at > post.published_at)
        .order_by(Post.published_at.asc())
        .limit(1)
    )
    related_statement = _base_statement().where(Post.id != post.id)
    if post.category_id:
        related_statement = related_statement.where(Post.category_id == post.category_id)
    related_posts = db.session.scalars(
        related_statement.order_by(Post.published_at.desc()).limit(3)
    ).all()
    comments = db.session.scalars(
        db.select(Comment)
        .where(
            Comment.post_id == post.id,
            Comment.parent_id.is_(None),
            Comment.status == "approved",
        )
        .order_by(Comment.is_pinned.desc(), Comment.created_at.asc())
    ).all()
    comment_form = CommentForm()
    return render_template(
        "blog/article.html",
        post=post,
        preview=False,
        previous_post=previous_post,
        next_post=next_post,
        related_posts=related_posts,
        comments=comments,
        comment_form=comment_form,
        action_form=EmptyForm(),
    )


@public_bp.get("/feed.xml")
def feed():
    from app.services.seo import get_seo_settings

    if not get_seo_settings().enable_feed:
        abort(404)
    posts = db.session.scalars(_base_statement().order_by(Post.published_at.desc()).limit(20)).all()
    # Keep an empty feed stable during its cache window so conditional requests
    # can reuse the representation instead of receiving a fresh ETag each time.
    generated_at = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    xml = render_template("blog/feed.xml", posts=posts, generated_at=generated_at)
    return _conditional_xml_response(xml, "application/atom+xml; charset=utf-8")


@public_bp.get("/sitemap.xml")
def sitemap():
    from app.services.seo import get_seo_settings

    if not get_seo_settings().enable_sitemap:
        abort(404)
    posts = db.session.scalars(_base_statement().order_by(Post.updated_at.desc())).all()
    projects = db.session.scalars(
        db.select(Project).where(public_project_condition()).order_by(Project.updated_at.desc())
    ).all()
    moments = db.session.scalars(
        db.select(Moment).where(public_moment_condition()).order_by(Moment.updated_at.desc())
    ).all()
    pages = db.session.scalars(
        db.select(CustomPage)
        .where(CustomPage.status == "published")
        .order_by(CustomPage.updated_at.desc())
    ).all()
    albums = db.session.scalars(
        db.select(Album).where(Album.status == "published").order_by(Album.updated_at.desc())
    ).all()
    xml = render_template(
        "blog/sitemap.xml",
        posts=posts,
        projects=projects,
        moments=moments,
        pages=pages,
        albums=albums,
    )
    return _conditional_xml_response(xml, "application/xml; charset=utf-8")


def _conditional_xml_response(xml: str, content_type: str) -> Response:
    response = Response(xml, content_type=content_type)
    response.set_etag(hashlib.sha256(xml.encode()).hexdigest())
    response.cache_control.public = True
    response.cache_control.max_age = 300
    response.cache_control.stale_while_revalidate = 600
    response.make_conditional(request)
    return response
