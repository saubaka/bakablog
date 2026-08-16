"""Stage-seven friend, gallery and moderation administration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import (
    AdminReplyForm,
    AlbumForm,
    EmptyForm,
    FriendAdminForm,
    FriendCategoryForm,
    PhotoBatchUploadForm,
)
from app.models import (
    Album,
    Comment,
    FriendCategory,
    FriendLink,
    GuestbookMessage,
    Media,
    ModerationNotification,
    Photo,
)
from app.security import permission_required, record_audit
from app.services.content import unique_slug
from app.services.friends import FriendCheckError, check_friend_url, validate_public_http_url
from app.services.media import MediaValidationError, delete_stored_image, store_image


def _moderation_return_view(default: str, allowed: set[str]) -> str:
    """Keep administrator actions in the moderation pane they came from."""

    candidates = [request.form.get("next_view"), request.args.get("view")]
    if request.referrer:
        candidates.extend(parse_qs(urlsplit(request.referrer).query).get("view", []))
    return next((item for item in candidates if item in allowed), default)


def _friend_choices(form: FriendAdminForm) -> None:
    categories = db.session.scalars(
        db.select(FriendCategory).order_by(FriendCategory.sort_order, FriendCategory.name)
    ).all()
    form.category_id.choices = [(0, "未分类"), *((item.id, item.name) for item in categories)]


@admin_bp.get("/friends/")
@permission_required("friends.view")
def friends():
    links = db.session.scalars(db.select(FriendLink).order_by(FriendLink.created_at.desc())).all()
    categories = db.session.scalars(
        db.select(FriendCategory).order_by(FriendCategory.sort_order, FriendCategory.name)
    ).all()
    return render_template(
        "admin/interactions/friends.html",
        links=links,
        categories=categories,
        action_form=EmptyForm(),
        category_form=FriendCategoryForm(),
    )


@admin_bp.route("/friends/edit/", defaults={"item_id": None}, methods=["GET", "POST"])
@admin_bp.route("/friends/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("friends.manage")
def edit_friend(item_id: int | None):
    link = db.get_or_404(FriendLink, item_id) if item_id else FriendLink()
    form = FriendAdminForm(obj=link)
    _friend_choices(form)
    if form.validate_on_submit():
        try:
            link.url = validate_public_http_url(form.url.data, resolve=False)
            link.avatar_url = (
                validate_public_http_url(form.avatar_url.data, resolve=False)
                if form.avatar_url.data
                else ""
            )
        except FriendCheckError as error:
            form.url.errors.append(str(error))
        else:
            duplicate = db.session.scalar(
                db.select(FriendLink.id).where(
                    FriendLink.url == link.url, FriendLink.id != (link.id or -1)
                )
            )
            if duplicate:
                form.url.errors.append("这个网站地址已经存在。")
                return render_template(
                    "admin/interactions/friend_editor.html",
                    form=form,
                    link=link if item_id else None,
                )
            link.name = form.name.data.strip()
            link.description = form.description.data.strip()
            link.category_id = form.category_id.data or None
            link.status = form.status.data
            link.sort_order = form.sort_order.data or 0
            link.is_featured = bool(form.is_featured.data)
            db.session.add(link)
            db.session.flush()
            record_audit("friend.save", "friend_link", str(link.id), link.name)
            db.session.commit()
            flash("友链已经保存。", "success")
            return redirect(url_for("admin.friends"))
    return render_template(
        "admin/interactions/friend_editor.html", form=form, link=link if item_id else None
    )


@admin_bp.post("/friends/categories/")
@permission_required("friends.manage")
def create_friend_category():
    form = FriendCategoryForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if db.session.scalar(db.select(FriendCategory.id).where(FriendCategory.name == name)):
            flash("这个分类名称已经存在。", "error")
            return redirect(url_for("admin.friends"))
        item = FriendCategory(
            name=name,
            slug=unique_slug(FriendCategory, form.slug.data or form.name.data),
            description=(form.description.data or "").strip(),
            sort_order=form.sort_order.data or 0,
        )
        db.session.add(item)
        db.session.flush()
        record_audit("friend_category.create", "friend_category", str(item.id), item.name)
        db.session.commit()
        flash("友链分类已经创建。", "success")
    else:
        flash("分类信息不完整或名称重复。", "error")
    return redirect(url_for("admin.friends"))


@admin_bp.post("/friends/categories/<int:item_id>/delete/")
@permission_required("friends.manage")
def delete_friend_category(item_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    item = db.get_or_404(FriendCategory, item_id)
    record_audit("friend_category.delete", "friend_category", str(item.id), item.name)
    db.session.delete(item)
    db.session.commit()
    flash("友链分类已删除，原有友链已移到未分类。", "success")
    return redirect(url_for("admin.friends"))


@admin_bp.post("/friends/<int:item_id>/<action>/")
@permission_required("friends.manage")
def friend_action(item_id: int, action: str):
    if not EmptyForm().validate_on_submit():
        abort(400)
    link = db.get_or_404(FriendLink, item_id)
    if action in {"approve", "reject", "disable"}:
        link.status = {"approve": "approved", "reject": "rejected", "disable": "disabled"}[action]
    elif action == "check":
        try:
            result = check_friend_url(link.url)
        except FriendCheckError as error:
            link.health_status, link.health_message, link.last_status_code = (
                "error",
                str(error),
                None,
            )
        else:
            link.health_status = "ok" if result.ok else "error"
            link.health_message, link.last_status_code = result.message, result.status_code
        link.last_checked_at = datetime.now(UTC)
    elif action == "delete":
        db.session.delete(link)
    else:
        abort(404)
    record_audit(f"friend.{action}", "friend_link", str(link.id), link.name)
    db.session.commit()
    flash("友链操作已完成。", "success")
    return redirect(url_for("admin.friends"))


@admin_bp.get("/albums/")
@permission_required("albums.view")
def albums():
    items = db.session.scalars(
        db.select(Album).order_by(Album.sort_order, Album.created_at.desc())
    ).all()
    return render_template("admin/interactions/albums.html", albums=items, action_form=EmptyForm())


@admin_bp.route("/albums/edit/", defaults={"item_id": None}, methods=["GET", "POST"])
@admin_bp.route("/albums/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("albums.manage")
def edit_album(item_id: int | None):
    album = db.get_or_404(Album, item_id) if item_id else Album()
    form = AlbumForm(obj=album)
    if form.validate_on_submit():
        album.title = form.title.data.strip()
        album.slug = unique_slug(Album, form.slug.data or album.title, album.id)
        album.description = (form.description.data or "").strip()
        album.status = form.status.data
        album.sort_order = form.sort_order.data or 0
        db.session.add(album)
        db.session.flush()
        record_audit("album.save", "album", str(album.id), album.title)
        db.session.commit()
        flash("相册已经保存。", "success")
        return redirect(url_for("admin.edit_album", item_id=album.id))
    return render_template(
        "admin/interactions/album_editor.html",
        form=form,
        album=album if item_id else None,
        upload_form=PhotoBatchUploadForm(),
        action_form=EmptyForm(),
    )


@admin_bp.post("/albums/<int:item_id>/photos/")
@permission_required("albums.manage")
def upload_album_photos(item_id: int):
    album = db.get_or_404(Album, item_id)
    form = PhotoBatchUploadForm()
    if not form.validate_on_submit():
        flash("请选择至少一张图片。", "error")
        return redirect(url_for("admin.edit_album", item_id=album.id))
    stored_files = []
    try:
        base_order = max((photo.sort_order for photo in album.photos), default=-1) + 1
        for offset, upload in enumerate(form.images.data):
            stored = store_image(upload)
            stored_files.append(stored)
            media = Media(
                filename=stored.filename,
                thumbnail_filename=stored.thumbnail_filename,
                original_filename=Path(upload.filename).name[:255],
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                width=stored.width,
                height=stored.height,
                alt_text=album.title,
                created_by_id=current_user.id,
            )
            db.session.add(media)
            db.session.flush()
            db.session.add(
                Photo(album_id=album.id, media_id=media.id, sort_order=base_order + offset)
            )
        record_audit("album.photos.upload", "album", str(album.id), f"{len(stored_files)} photos")
        db.session.commit()
    except MediaValidationError as error:
        db.session.rollback()
        for stored in stored_files:
            delete_stored_image(stored.filename, stored.thumbnail_filename)
        flash(str(error), "error")
    except Exception:
        db.session.rollback()
        for stored in stored_files:
            delete_stored_image(stored.filename, stored.thumbnail_filename)
        raise
    else:
        flash(f"已上传 {len(stored_files)} 张照片。", "success")
    return redirect(url_for("admin.edit_album", item_id=album.id))


@admin_bp.post("/photos/<int:photo_id>/update/")
@permission_required("albums.manage")
def update_photo(photo_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    photo = db.get_or_404(Photo, photo_id)
    photo.caption = request.form.get("caption", "").strip()[:300]
    try:
        photo.sort_order = int(request.form.get("sort_order", photo.sort_order))
    except ValueError:
        abort(400)
    photo.is_featured = request.form.get("is_featured") == "1"
    db.session.commit()
    flash("照片信息已更新。", "success")
    return redirect(url_for("admin.edit_album", item_id=photo.album_id))


@admin_bp.post("/photos/<int:photo_id>/delete/")
@permission_required("albums.manage")
def delete_photo(photo_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    photo = db.get_or_404(Photo, photo_id)
    album_id = photo.album_id
    db.session.delete(photo)
    db.session.commit()
    flash("照片已从相册移除，原图仍保留在媒体库。", "success")
    return redirect(url_for("admin.edit_album", item_id=album_id))


@admin_bp.post("/albums/<int:item_id>/delete/")
@permission_required("albums.manage")
def delete_album(item_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    album = db.get_or_404(Album, item_id)
    record_audit("album.delete", "album", str(album.id), album.title)
    db.session.delete(album)
    db.session.commit()
    flash("相册已删除，图片仍保留在媒体库。", "success")
    return redirect(url_for("admin.albums"))


@admin_bp.route("/moderation/", methods=["GET", "POST"])
@permission_required("moderation.view")
def moderation():
    view_aliases = {
        "messages": "unread",
        "replies": "comments",
        "interactions": "comments",
    }
    requested_view = request.args.get("view", "unread")
    view = view_aliases.get(requested_view, requested_view)
    status_filter = request.args.get("status", "all")
    if view not in {"unread", "comments", "guestbook"}:
        view = "unread"
    if status_filter not in {"all", "pending", "approved", "spam", "blocked"}:
        status_filter = "all"
    can_moderate = current_user.has_permission("moderation.view")
    can_manage_moderation = current_user.has_permission("moderation.manage")
    comments: list[Comment] = []
    messages: list[GuestbookMessage] = []
    notifications: list[ModerationNotification] = []
    unread_targets: dict[str, set[int]] = {
        "comment": set(),
        "guestbook": set(),
    }
    summary = {
        "unread": 0,
        "comment_total": 0,
        "message_total": 0,
        "pending_comments": 0,
        "pending_messages": 0,
    }
    if can_moderate:
        comment_query = db.select(Comment)
        message_query = db.select(GuestbookMessage)
        if status_filter != "all":
            comment_query = comment_query.where(Comment.status == status_filter)
            message_query = message_query.where(GuestbookMessage.status == status_filter)
        if view == "comments":
            comments = db.session.scalars(
                comment_query.order_by(Comment.created_at.desc()).limit(200)
            ).all()
        if view == "guestbook":
            messages = db.session.scalars(
                message_query.order_by(GuestbookMessage.created_at.desc()).limit(200)
            ).all()
        notifications = db.session.scalars(
            db.select(ModerationNotification)
            .where(
                ModerationNotification.is_read.is_(False),
                ModerationNotification.target_type.in_(("comment", "guestbook")),
            )
            .order_by(ModerationNotification.created_at.desc())
            .limit(100)
        ).all()
        for notification in notifications:
            unread_targets[notification.target_type].add(notification.target_id)
        summary = {
            "unread": db.session.scalar(
                db.select(db.func.count(ModerationNotification.id)).where(
                    ModerationNotification.is_read.is_(False),
                    ModerationNotification.target_type.in_(("comment", "guestbook")),
                )
            )
            or 0,
            "comment_total": db.session.scalar(db.select(db.func.count(Comment.id))) or 0,
            "message_total": db.session.scalar(db.select(db.func.count(GuestbookMessage.id)))
            or 0,
            "pending_comments": db.session.scalar(
                db.select(db.func.count(Comment.id)).where(Comment.status == "pending")
            )
            or 0,
            "pending_messages": db.session.scalar(
                db.select(db.func.count(GuestbookMessage.id)).where(
                    GuestbookMessage.status == "pending"
                )
            )
            or 0,
        }
    return render_template(
        "admin/interactions/moderation.html",
        comments=comments,
        messages=messages,
        notifications=notifications,
        summary=summary,
        current_view=view,
        current_status=status_filter,
        action_form=EmptyForm(),
        reply_form=AdminReplyForm(),
        can_moderate=can_moderate,
        can_manage_moderation=can_manage_moderation,
        unread_targets=unread_targets,
    )


@admin_bp.post("/moderation/comments/<int:item_id>/<action>/")
@permission_required("moderation.manage")
def moderate_comment(item_id: int, action: str):
    if not EmptyForm().validate_on_submit():
        abort(400)
    item = db.get_or_404(Comment, item_id)
    if action in {"approve", "spam", "block"}:
        item.status = {"approve": "approved", "spam": "spam", "block": "blocked"}[action]
    elif action == "pin":
        item.is_pinned = not item.is_pinned
    elif action == "delete":
        db.session.execute(
            db.delete(ModerationNotification).where(
                ModerationNotification.target_type == "comment",
                ModerationNotification.target_id == item.id,
            )
        )
        db.session.delete(item)
    else:
        abort(404)
    record_audit(f"comment.{action}", "comment", str(item.id), item.author_name)
    db.session.commit()
    next_view = _moderation_return_view("comments", {"comments"})
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/comments/<int:item_id>/edit/")
@permission_required("moderation.manage")
def edit_moderated_comment(item_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    item = db.get_or_404(Comment, item_id)
    content = request.form.get("content", "").strip()
    next_view = _moderation_return_view("comments", {"comments"})
    if not 2 <= len(content) <= 3000:
        flash("评论内容需要保持在2到3000个字符之间。", "error")
        return redirect(url_for("admin.moderation", view=next_view))
    item.content = content
    record_audit("comment.edit", "comment", str(item.id), item.author_name)
    db.session.commit()
    flash("评论内容已保存。", "success")
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/comments/<int:item_id>/reply/")
@permission_required("moderation.manage")
def reply_comment(item_id: int):
    parent = db.get_or_404(Comment, item_id)
    form = AdminReplyForm()
    if not form.validate_on_submit():
        abort(400)
    root = parent.parent or parent
    reply = Comment(
        post_id=root.post_id,
        parent_id=root.id,
        admin_user_id=current_user.id,
        author_type="staff",
        author_name=current_user.display_name,
        content=form.content.data.strip(),
        status="approved",
    )
    db.session.add(reply)
    db.session.commit()
    flash("站长回复已发布。", "success")
    next_view = _moderation_return_view("comments", {"comments"})
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/messages/<int:item_id>/<action>/")
@permission_required("moderation.manage")
def moderate_message(item_id: int, action: str):
    if not EmptyForm().validate_on_submit():
        abort(400)
    item = db.get_or_404(GuestbookMessage, item_id)
    if action in {"approve", "spam", "block"}:
        item.status = {"approve": "approved", "spam": "spam", "block": "blocked"}[action]
    elif action == "pin":
        item.is_pinned = not item.is_pinned
    elif action == "delete":
        db.session.execute(
            db.delete(ModerationNotification).where(
                ModerationNotification.target_type == "guestbook",
                ModerationNotification.target_id == item.id,
            )
        )
        db.session.delete(item)
    else:
        abort(404)
    record_audit(f"guestbook.{action}", "guestbook_message", str(item.id), item.author_name)
    db.session.commit()
    next_view = _moderation_return_view("guestbook", {"guestbook"})
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/messages/<int:item_id>/edit/")
@permission_required("moderation.manage")
def edit_moderated_message(item_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    item = db.get_or_404(GuestbookMessage, item_id)
    content = request.form.get("content", "").strip()
    next_view = _moderation_return_view("guestbook", {"guestbook"})
    if not 2 <= len(content) <= 3000:
        flash("留言内容需要保持在2到3000个字符之间。", "error")
        return redirect(url_for("admin.moderation", view=next_view))
    item.content = content
    record_audit("guestbook.edit", "guestbook_message", str(item.id), item.author_name)
    db.session.commit()
    flash("留言内容已保存。", "success")
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/messages/<int:item_id>/reply/")
@permission_required("moderation.manage")
def reply_message(item_id: int):
    item = db.get_or_404(GuestbookMessage, item_id)
    form = AdminReplyForm()
    if not form.validate_on_submit():
        abort(400)
    item.admin_reply = form.content.data.strip()
    item.replied_at = datetime.now(UTC)
    db.session.commit()
    flash("站长回复已保存。", "success")
    next_view = _moderation_return_view("guestbook", {"guestbook"})
    return redirect(url_for("admin.moderation", view=next_view))


@admin_bp.post("/moderation/notifications/read-all/")
@permission_required("moderation.manage")
def read_all_notifications():
    if not EmptyForm().validate_on_submit():
        abort(400)
    db.session.execute(db.update(ModerationNotification).values(is_read=True))
    db.session.commit()
    return redirect(url_for("admin.moderation", view="unread"))


@admin_bp.get("/moderation/notifications/<int:notification_id>/open/")
@permission_required("moderation.view")
def open_moderation_notification(notification_id: int):
    """Mark a moderation notice read and route it to the actionable record."""

    item = db.get_or_404(ModerationNotification, notification_id)
    item.is_read = True
    db.session.commit()
    if item.target_type == "comment":
        target = db.session.get(Comment, item.target_id)
        if target is not None:
            return redirect(
                url_for("admin.moderation", view="comments", _anchor=f"moderation-comment-{target.id}")
            )
    if item.target_type == "guestbook":
        target = db.session.get(GuestbookMessage, item.target_id)
        if target is not None:
            return redirect(
                url_for("admin.moderation", view="guestbook", _anchor=f"moderation-message-{target.id}")
            )
    if item.target_type == "friend_link":
        return redirect(url_for("admin.friends"))
    return redirect(url_for("admin.moderation", view="unread"))
