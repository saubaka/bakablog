"""Public personal profile, projects, moments, home modules and custom pages."""

from __future__ import annotations

from types import SimpleNamespace

from flask import abort, current_app, render_template, request

from app.blueprints.public import public_bp
from app.extensions import db
from app.models import (
    Album,
    CustomPage,
    Experience,
    FriendLink,
    GuestbookMessage,
    Moment,
    PersonalGoal,
    PersonalSkill,
    Post,
    Project,
    SiteProfile,
    SocialLink,
)
from app.services.blog import public_post_condition
from app.services.cache import home_content_cache
from app.services.content import (
    HOME_SETTING_DEFAULTS,
    get_home_modules,
    get_settings,
    public_moment_condition,
    public_project_condition,
)


@public_bp.get("/")
def home():
    payload = home_content_cache.get_or_set(
        f"home-content:{current_app.instance_path}",
        int(current_app.config["HOME_CONTENT_CACHE_SECONDS"]),
        _build_home_payload,
    )
    return render_template("public/home.html", **payload)


@public_bp.get("/privacy/")
def privacy():
    return render_template("public/privacy.html")


@public_bp.get("/terms/")
def service_terms():
    return render_template("public/service_terms.html")


def _build_home_payload() -> dict[str, object]:
    modules = get_home_modules()
    limits = {module.module_key: module.item_limit for module in modules}
    posts = db.session.scalars(
        db.select(Post)
        .where(public_post_condition())
        .order_by(Post.is_featured.desc(), Post.is_pinned.desc(), Post.published_at.desc())
        .limit(limits.get("posts", 3))
    ).all()
    projects = db.session.scalars(
        db.select(Project)
        .where(public_project_condition())
        .order_by(Project.is_featured.desc(), Project.sort_order, Project.published_at.desc())
        .limit(limits.get("projects", 3))
    ).all()
    moments = db.session.scalars(
        db.select(Moment)
        .where(public_moment_condition())
        .order_by(Moment.is_pinned.desc(), Moment.published_at.desc())
        .limit(limits.get("moments", 3))
    ).all()
    albums = db.session.scalars(
        db.select(Album)
        .where(Album.status == "published")
        .order_by(Album.sort_order, Album.updated_at.desc())
        .limit(12)
    ).all()
    gallery_items = [
        SimpleNamespace(photo=photo, album=album) for album in albums for photo in album.photos
    ][: limits.get("gallery", 6)]
    friend_links = db.session.scalars(
        db.select(FriendLink)
        .where(FriendLink.status == "approved")
        .order_by(FriendLink.is_featured.desc(), FriendLink.sort_order, FriendLink.name)
        .limit(limits.get("links", 6))
    ).all()
    guestbook_messages = db.session.scalars(
        db.select(GuestbookMessage)
        .where(GuestbookMessage.status == "approved")
        .order_by(GuestbookMessage.is_pinned.desc(), GuestbookMessage.created_at.desc())
        .limit(2)
    ).all()
    skills = db.session.scalars(
        db.select(PersonalSkill)
        .where(PersonalSkill.is_visible.is_(True))
        .order_by(PersonalSkill.sort_order)
        .limit(limits.get("about", 5))
    ).all()
    socials = db.session.scalars(
        db.select(SocialLink)
        .where(SocialLink.is_visible.is_(True))
        .order_by(SocialLink.sort_order)
        .limit(4)
    ).all()
    settings = get_settings(HOME_SETTING_DEFAULTS)
    settings = {
        key: (value.strip() if isinstance(value, str) and value.strip() else default)
        for key, default in HOME_SETTING_DEFAULTS.items()
        for value in [settings.get(key, default)]
    }
    hero_tags = [item.strip() for item in settings["hero_tags"].split("/") if item.strip()][:4]
    return {
        "modules": modules,
        "posts": posts,
        "projects": projects,
        "moments": moments,
        "gallery_items": gallery_items,
        "friend_links": friend_links,
        "guestbook_messages": guestbook_messages,
        "skills": skills,
        "socials": socials,
        "hero_tags": hero_tags,
        "home_settings": settings,
    }


@public_bp.get("/about/")
def about():
    profile = db.session.scalar(db.select(SiteProfile).limit(1))
    skills = db.session.scalars(
        db.select(PersonalSkill)
        .where(PersonalSkill.is_visible.is_(True))
        .order_by(PersonalSkill.sort_order)
    ).all()
    experiences = db.session.scalars(
        db.select(Experience).where(Experience.is_visible.is_(True)).order_by(Experience.sort_order)
    ).all()
    goals = db.session.scalars(
        db.select(PersonalGoal)
        .where(PersonalGoal.is_visible.is_(True))
        .order_by(PersonalGoal.sort_order)
    ).all()
    socials = db.session.scalars(
        db.select(SocialLink).where(SocialLink.is_visible.is_(True)).order_by(SocialLink.sort_order)
    ).all()
    return render_template(
        "public/about.html",
        profile=profile,
        skills=skills,
        experiences=experiences,
        goals=goals,
        socials=socials,
    )


@public_bp.get("/projects/")
def projects():
    query = request.args.get("q", "").strip()[:100]
    statement = db.select(Project).where(public_project_condition())
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            db.or_(
                Project.title.ilike(pattern),
                Project.summary.ilike(pattern),
                Project.tech_stack.ilike(pattern),
            )
        )
    page = db.paginate(
        statement.order_by(
            Project.is_featured.desc(), Project.sort_order, Project.published_at.desc()
        ),
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["POSTS_PER_PAGE"],
        error_out=False,
    )
    return render_template("public/projects.html", projects=page.items, page=page, query=query)


@public_bp.get("/projects/<slug>/")
def project_detail(slug: str):
    project = db.session.scalar(
        db.select(Project).where(public_project_condition(), Project.slug == slug)
    )
    if project is None:
        abort(404)
    related = db.session.scalars(
        db.select(Project)
        .where(public_project_condition(), Project.id != project.id)
        .order_by(Project.is_featured.desc(), Project.published_at.desc())
        .limit(3)
    ).all()
    return render_template("public/project_detail.html", project=project, related=related)


@public_bp.get("/moments/")
def moments():
    page = db.paginate(
        db.select(Moment)
        .where(public_moment_condition())
        .order_by(Moment.is_pinned.desc(), Moment.published_at.desc()),
        page=request.args.get("page", 1, type=int),
        per_page=10,
        error_out=False,
    )
    return render_template("public/moments.html", moments=page.items, page=page)


@public_bp.get("/moments/<int:item_id>/")
def moment_detail(item_id: int):
    moment = db.session.scalar(
        db.select(Moment).where(public_moment_condition(), Moment.id == item_id)
    )
    if moment is None:
        abort(404)
    return render_template("public/moment_detail.html", moment=moment)


@public_bp.get("/pages/<slug>/")
def custom_page(slug: str):
    page = db.session.scalar(
        db.select(CustomPage).where(CustomPage.slug == slug, CustomPage.status == "published")
    )
    if page is None:
        abort(404)
    return render_template("public/custom_page.html", page=page)
