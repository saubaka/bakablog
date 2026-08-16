"""Public guest interactions, friend links and galleries."""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

from app.blueprints.public import public_bp
from app.extensions import db
from app.forms import CommentForm, EmptyForm, FriendApplicationForm, GuestbookForm
from app.models import (
    Album,
    Comment,
    CommentReaction,
    FriendLink,
    GuestbookMessage,
    Post,
)
from app.services.blog import public_post_condition
from app.services.friends import FriendCheckError, validate_public_http_url
from app.services.interaction import (
    InteractionError,
    create_notification,
    enforce_rate_limit,
    normalize_plain_text,
    spam_status,
    visitor_hash,
)


@public_bp.route("/links/", methods=["GET", "POST"])
def links():
    form = FriendApplicationForm()
    application_code = None
    if form.validate_on_submit():
        identity = visitor_hash()
        try:
            enforce_rate_limit(FriendLink, identity)
            link_url = validate_public_http_url(form.url.data, resolve=False)
            avatar_url = (
                validate_public_http_url(form.avatar_url.data, resolve=False)
                if form.avatar_url.data
                else ""
            )
        except (InteractionError, FriendCheckError) as error:
            form.url.errors.append(str(error))
        else:
            existing = db.session.scalar(db.select(FriendLink).where(FriendLink.url == link_url))
            if existing:
                form.url.errors.append("这个网站已经提交过，可以使用申请编号查询状态。")
            else:
                status = spam_status(form.description.data, form.website.data or "")
                link = FriendLink(
                    name=form.name.data.strip(),
                    url=link_url,
                    description=normalize_plain_text(form.description.data),
                    avatar_url=avatar_url,
                    applicant_email=(form.applicant_email.data or "").strip(),
                    ip_hash=identity,
                    status="rejected" if status == "spam" else "pending",
                )
                db.session.add(link)
                db.session.flush()
                create_notification("friend_link", link.id, f"新的友链申请：{link.name}")
                db.session.commit()
                application_code = link.application_code
                form = FriendApplicationForm(formdata=None)
    friend_links = db.session.scalars(
        db.select(FriendLink)
        .where(FriendLink.status == "approved")
        .order_by(FriendLink.is_featured.desc(), FriendLink.sort_order, FriendLink.name)
    ).all()
    return render_template(
        "public/links.html",
        form=form,
        application_code=application_code,
        friend_links=friend_links,
    )


@public_bp.get("/links/application/<code>/")
def friend_application_status(code: str):
    link = db.session.scalar(db.select(FriendLink).where(FriendLink.application_code == code))
    if link is None:
        abort(404)
    return render_template("public/friend_status.html", link=link)


@public_bp.get("/links/status/")
def friend_status_lookup():
    code = request.args.get("code", "").strip()
    if not code:
        return redirect(url_for("public.links"))
    return redirect(url_for("public.friend_application_status", code=code))


@public_bp.get("/gallery/")
def gallery():
    albums = db.session.scalars(
        db.select(Album)
        .where(Album.status == "published")
        .order_by(Album.sort_order, Album.created_at.desc())
    ).all()
    return render_template("public/gallery.html", albums=albums)


@public_bp.get("/gallery/<slug>/")
def album_detail(slug: str):
    album = db.session.scalar(
        db.select(Album).where(Album.slug == slug, Album.status == "published")
    )
    if album is None:
        abort(404)
    return render_template("public/album_detail.html", album=album)


@public_bp.route("/guestbook/", methods=["GET", "POST"])
def guestbook():
    form = GuestbookForm()
    if form.validate_on_submit():
        identity = visitor_hash()
        try:
            enforce_rate_limit(GuestbookMessage, identity)
        except InteractionError as error:
            form.content.errors.append(str(error))
        else:
            status = spam_status(form.content.data, form.website.data or "")
            message = GuestbookMessage(
                author_name=form.author_name.data.strip(),
                email=(form.email.data or "").strip(),
                content=normalize_plain_text(form.content.data),
                status=status,
                ip_hash=identity,
                user_agent=request.user_agent.string[:255],
            )
            db.session.add(message)
            db.session.flush()
            create_notification("guestbook", message.id, f"新留言：{message.author_name}")
            db.session.commit()
            flash("留言已收到，通过审核后会出现在这里。", "success")
            return redirect(url_for("public.guestbook"))
    messages = db.session.scalars(
        db.select(GuestbookMessage)
        .where(GuestbookMessage.status == "approved")
        .order_by(GuestbookMessage.is_pinned.desc(), GuestbookMessage.created_at.desc())
        .limit(100)
    ).all()
    return render_template("public/guestbook.html", form=form, messages=messages)


@public_bp.post("/blog/<slug>/comments/")
def create_comment(slug: str):
    post = db.session.scalar(db.select(Post).where(public_post_condition(), Post.slug == slug))
    if post is None:
        abort(404)
    form = CommentForm()
    if not form.validate_on_submit():
        flash("评论填写不完整，请检查后重试。", "error")
        return redirect(url_for("public.article", slug=slug, _anchor="comments"))
    identity = visitor_hash()
    try:
        enforce_rate_limit(Comment, identity)
        website = (
            validate_public_http_url(form.website.data, resolve=False) if form.website.data else ""
        )
    except (InteractionError, FriendCheckError) as error:
        flash(str(error), "error")
        return redirect(url_for("public.article", slug=slug, _anchor="comments"))
    parent = None
    if form.parent_id.data and form.parent_id.data.isdigit():
        parent = db.session.scalar(
            db.select(Comment).where(
                Comment.id == int(form.parent_id.data),
                Comment.post_id == post.id,
                Comment.status == "approved",
            )
        )
        if parent and parent.parent_id:
            parent = parent.parent
    status = spam_status(form.content.data, form.contact.data or "")
    comment = Comment(
        post_id=post.id,
        parent_id=parent.id if parent else None,
        author_type="visitor",
        author_name=form.author_name.data.strip(),
        email=(form.email.data or "").strip(),
        website=website,
        content=normalize_plain_text(form.content.data),
        status=status,
        ip_hash=identity,
        user_agent=request.user_agent.string[:255],
    )
    db.session.add(comment)
    db.session.flush()
    create_notification("comment", comment.id, f"文章《{post.title}》有新评论")
    db.session.commit()
    flash("评论已提交，通过审核后会公开。", "success")
    return redirect(url_for("public.article", slug=slug, _anchor="comments"))


@public_bp.post("/comments/<int:comment_id>/like/")
def like_comment(comment_id: int):
    _empty_form()
    comment = db.session.scalar(
        db.select(Comment).where(Comment.id == comment_id, Comment.status == "approved")
    )
    if comment is None:
        abort(404)
    identity = visitor_hash()
    existing = db.session.scalar(
        db.select(CommentReaction).where(
            CommentReaction.comment_id == comment.id,
            CommentReaction.visitor_hash == identity,
        )
    )
    if existing is None:
        db.session.add(
            CommentReaction(comment_id=comment.id, visitor_hash=identity)
        )
        comment.like_count += 1
    db.session.commit()
    return redirect(url_for("public.article", slug=comment.post.slug, _anchor="comments"))


def _empty_form() -> None:
    if not EmptyForm().validate_on_submit():
        abort(400)
