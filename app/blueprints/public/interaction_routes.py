"""Public guest interactions, friend links and galleries."""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from app.blueprints.public import public_bp
from app.extensions import db
from app.forms import CommentForm, EmptyForm, FriendApplicationForm, GuestbookForm
from app.models import (
    Album,
    Comment,
    CommentReaction,
    FriendLink,
    GuestbookMessage,
    Moment,
    Post,
)
from app.services.blog import public_post_condition
from app.services.content import public_moment_condition
from app.services.friends import FriendCheckError, validate_public_http_url
from app.services.human_check import issue_human_check, verify_human_check
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
    if not post.allow_comments:
        abort(404)
    return _create_comment(post=post)


@public_bp.post("/moments/<int:item_id>/comments/")
def create_moment_comment(item_id: int):
    moment = db.session.scalar(
        db.select(Moment).where(public_moment_condition(), Moment.id == item_id)
    )
    if moment is None or not moment.allow_comments:
        abort(404)
    return _create_comment(moment=moment)


@public_bp.get("/human-check/comments/<target_type>/<int:item_id>/")
def refresh_comment_human_check(target_type: str, item_id: int):
    if target_type == "post":
        target = db.session.scalar(
            db.select(Post).where(public_post_condition(), Post.id == item_id)
        )
    elif target_type == "moment":
        target = db.session.scalar(
            db.select(Moment).where(public_moment_condition(), Moment.id == item_id)
        )
    else:
        abort(404)
    if target is None or not target.allow_comments:
        abort(404)
    challenge = issue_human_check(f"comment-{target_type}", str(item_id))
    return jsonify({"ok": True, "nonce": challenge.nonce, "image": challenge.image_data})


def _create_comment(*, post: Post | None = None, moment: Moment | None = None):
    target = post or moment
    if target is None:
        abort(404)
    target_type = "post" if post is not None else "moment"
    target_id = target.id
    redirect_target = (
        url_for("public.article", slug=post.slug, _anchor="comments")
        if post is not None
        else url_for("public.moment_detail", item_id=moment.id, _anchor="comments")
    )
    form = CommentForm()
    if not form.validate_on_submit():
        flash("评论填写不完整，请检查后重试。", "error")
        return redirect(redirect_target)
    if not verify_human_check(
        f"comment-{target_type}", str(target_id), form.human_nonce.data or "", form.human_answer.data
    ):
        flash("人机验证字符不匹配，请重新输入。", "error")
        return redirect(redirect_target)
    identity = visitor_hash()
    try:
        enforce_rate_limit(Comment, identity)
        website = (
            validate_public_http_url(form.website.data, resolve=False) if form.website.data else ""
        )
    except (InteractionError, FriendCheckError) as error:
        flash(str(error), "error")
        return redirect(redirect_target)
    parent = None
    if form.parent_id.data and form.parent_id.data.isdigit():
        parent = db.session.scalar(
            db.select(Comment).where(
                Comment.id == int(form.parent_id.data),
                Comment.post_id == post.id if post is not None else Comment.moment_id == moment.id,
                Comment.status == "approved",
            )
        )
        if parent and parent.parent_id:
            parent = parent.parent
    status = spam_status(form.content.data, form.contact.data or "")
    comment = Comment(
        post_id=post.id if post is not None else None,
        moment_id=moment.id if moment is not None else None,
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
    target_title = f"文章《{post.title}》" if post is not None else f"动态 #{moment.id}"
    create_notification("comment", comment.id, f"{target_title}有新评论")
    db.session.commit()
    flash("评论已提交，通过审核后会公开。", "success")
    return redirect(redirect_target)


@public_bp.post("/comments/<int:comment_id>/like/")
def like_comment(comment_id: int):
    _empty_form()
    comment = db.session.scalar(
        db.select(Comment).where(Comment.id == comment_id, Comment.status == "approved")
    )
    if comment is None:
        abort(404)
    if (comment.post_id and not comment.post.allow_comments) or (
        comment.moment_id and not comment.moment.allow_comments
    ):
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
    if comment.post_id:
        return redirect(url_for("public.article", slug=comment.post.slug, _anchor="comments"))
    return redirect(url_for("public.moment_detail", item_id=comment.moment_id, _anchor="comments"))


def _empty_form() -> None:
    if not EmptyForm().validate_on_submit():
        abort(400)
