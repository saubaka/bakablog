"""Blog administration routes for the stage-five publishing workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from markupsafe import escape

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import EmptyForm, PostForm, TaxonomyForm
from app.models import Category, Media, Post, PostVersion, Tag
from app.security import permission_required, record_audit
from app.services.blog import (
    apply_post_form,
    create_taxonomy,
    create_version,
    render_markdown,
)
from app.services.media import MediaValidationError, delete_stored_image, store_image


@admin_bp.get("/posts/")
@permission_required("posts.view")
def posts():
    include_deleted = request.args.get("deleted") == "1"
    status_filter = request.args.get("status", "all")
    if status_filter not in {"all", "draft", "published", "scheduled"}:
        status_filter = "all"
    statement = db.select(Post).order_by(Post.updated_at.desc())
    statement = statement.where(
        Post.deleted_at.is_not(None) if include_deleted else Post.deleted_at.is_(None)
    )
    if not include_deleted and status_filter != "all":
        statement = statement.where(Post.status == status_filter)
    post_items = db.session.scalars(statement).all()
    return render_template(
        "admin/posts/list.html",
        post_items=post_items,
        include_deleted=include_deleted,
        current_status=status_filter,
        action_form=EmptyForm(),
    )


@admin_bp.route("/posts/new/", methods=["GET", "POST"])
@permission_required("posts.manage")
def create_post():
    form = PostForm()
    _configure_post_form(form)
    if form.validate_on_submit():
        _enforce_publish_permission(form.status.data)
        post = Post(author_id=current_user.id, title="", slug="")
        apply_post_form(post, form, current_user.id)
        db.session.add(post)
        db.session.flush()
        create_version(post, current_user.id)
        record_audit("post.create", "post", str(post.id), post.title)
        db.session.commit()
        flash("文章已保存，可以继续预览或编辑。", "success")
        return redirect(url_for("admin.edit_post", post_id=post.id))
    editor_content_html, _, _ = render_markdown(form.content_markdown.data or "")
    return render_template(
        "admin/posts/editor.html",
        form=form,
        post=None,
        editor_content_html=editor_content_html,
        editor_media=_recent_editor_media(),
    )


@admin_bp.route("/posts/<int:post_id>/edit/", methods=["GET", "POST"])
@permission_required("posts.manage")
def edit_post(post_id: int):
    post = db.get_or_404(Post, post_id)
    form = PostForm(obj=post)
    _configure_post_form(form)
    if request.method == "GET":
        form.tags.data = "，".join(tag.name for tag in post.tags)
        if post.published_at:
            form.published_at.data = post.published_at.replace(tzinfo=None)
    if form.validate_on_submit():
        _enforce_publish_permission(form.status.data)
        previous_status = post.status
        apply_post_form(post, form, current_user.id)
        create_version(post, current_user.id)
        record_audit(
            "post.update",
            "post",
            str(post.id),
            f"{post.title}（{previous_status}→{post.status}）",
        )
        db.session.commit()
        flash("文章与新版本已经保存。", "success")
        return redirect(url_for("admin.edit_post", post_id=post.id))
    editor_content_html, _, _ = render_markdown(form.content_markdown.data or "")
    return render_template(
        "admin/posts/editor.html",
        form=form,
        post=post,
        editor_content_html=editor_content_html,
        editor_media=_recent_editor_media(),
    )


@admin_bp.get("/posts/<int:post_id>/preview/")
@permission_required("posts.view")
def preview_post(post_id: int):
    post = db.get_or_404(Post, post_id)
    return render_template(
        "blog/article.html",
        post=post,
        preview=True,
        previous_post=None,
        next_post=None,
        related_posts=[],
        comments=[],
        comment_form=None,
        action_form=EmptyForm(),
    )


@admin_bp.post("/posts/<int:post_id>/delete/")
@permission_required("posts.manage")
def delete_post(post_id: int):
    _validate_action_form()
    post = db.get_or_404(Post, post_id)
    post.deleted_at = datetime.now(UTC)
    record_audit("post.delete", "post", str(post.id), post.title)
    db.session.commit()
    flash("文章已移入回收站，公开页面不会再显示。", "success")
    return redirect(url_for("admin.posts"))


@admin_bp.post("/posts/<int:post_id>/restore/")
@permission_required("posts.manage")
def restore_post(post_id: int):
    _validate_action_form()
    post = db.get_or_404(Post, post_id)
    post.deleted_at = None
    record_audit("post.restore", "post", str(post.id), post.title)
    db.session.commit()
    flash("文章已从回收站恢复。", "success")
    return redirect(url_for("admin.posts"))


@admin_bp.post("/posts/<int:post_id>/withdraw/")
@permission_required("posts.publish")
def withdraw_post(post_id: int):
    _validate_action_form()
    post = db.get_or_404(Post, post_id)
    post.status = "draft"
    post.published_at = None
    create_version(post, current_user.id)
    record_audit("post.withdraw", "post", str(post.id), post.title)
    db.session.commit()
    flash("文章已撤回为草稿。", "success")
    return redirect(url_for("admin.edit_post", post_id=post.id))


@admin_bp.get("/posts/<int:post_id>/versions/")
@permission_required("posts.view")
def post_versions(post_id: int):
    post = db.get_or_404(Post, post_id)
    versions = post.versions.all()
    return render_template(
        "admin/posts/versions.html", post=post, versions=versions, action_form=EmptyForm()
    )


@admin_bp.post("/posts/<int:post_id>/versions/<int:version_id>/restore/")
@permission_required("posts.manage")
def restore_post_version(post_id: int, version_id: int):
    _validate_action_form()
    post = db.get_or_404(Post, post_id)
    version = db.get_or_404(PostVersion, version_id)
    if version.post_id != post.id:
        abort(404)
    post.title = version.title
    post.summary = version.summary
    post.content_markdown = version.content_markdown
    post.content_html, post.toc_html, post.reading_minutes = render_markdown(
        version.content_markdown
    )
    post.status = "draft"
    post.published_at = None
    create_version(post, current_user.id)
    record_audit("post.version.restore", "post", str(post.id), f"恢复版本{version.version_number}")
    db.session.commit()
    flash(f"已恢复版本{version.version_number}并保存为新草稿版本。", "success")
    return redirect(url_for("admin.edit_post", post_id=post.id))


@admin_bp.post("/api/posts/<int:post_id>/autosave/")
@permission_required("posts.manage")
def autosave_post(post_id: int):
    post = db.get_or_404(Post, post_id)
    if post.deleted_at is not None:
        return jsonify(
            {"ok": False, "error": {"code": "deleted_post", "message": "回收站文章不能自动保存。"}}
        ), 409
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()[:180]
    content = str(payload.get("content_markdown", ""))
    if not title or not content or len(content) > 2_000_000:
        return jsonify(
            {"ok": False, "error": {"code": "invalid_post", "message": "标题和正文不能为空。"}}
        ), 400
    post.title = title
    post.summary = str(payload.get("summary", "")).strip()[:360]
    post.content_markdown = content
    post.content_html, post.toc_html, post.reading_minutes = render_markdown(content)
    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "data": {"saved_at": datetime.now(UTC).isoformat(), "post_id": post.id},
        }
    )


@admin_bp.post("/api/editor-image/")
def editor_image():
    if not (
        current_user.has_permission("posts.manage") or current_user.has_permission("pages.manage")
    ):
        abort(403)
    upload = request.files.get("image")
    if upload is None:
        return jsonify(
            {"ok": False, "error": {"code": "missing_image", "message": "请选择图片。"}}
        ), 400
    try:
        stored = store_image(upload)
    except MediaValidationError as error:
        return jsonify(
            {"ok": False, "error": {"code": "invalid_image", "message": str(error)}}
        ), 400
    media = Media(
        filename=stored.filename,
        thumbnail_filename=stored.thumbnail_filename,
        original_filename=Path(upload.filename or "image").name[:255],
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        width=stored.width,
        height=stored.height,
        alt_text=str(request.form.get("alt_text", "")).strip()[:160],
        created_by_id=current_user.id,
    )
    try:
        db.session.add(media)
        db.session.flush()
        record_audit("media.editor_upload", "media", str(media.id), media.original_filename)
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_stored_image(stored.filename, stored.thumbnail_filename)
        raise
    url = url_for("public.media_file", filename=media.filename)
    return jsonify(
        {
            "ok": True,
            "data": {
                "media_id": media.id,
                "url": url,
                "width": media.width,
                "height": media.height,
                "size_bytes": media.size_bytes,
                "alt_text": media.alt_text or media.original_filename,
                "markdown": (
                    f'<img src="{url}" alt="{escape(media.alt_text or media.original_filename)}" '
                    f'width="{media.width}" height="{media.height}" loading="lazy" '
                    'decoding="async">'
                ),
            },
        }
    )


def _recent_editor_media() -> list[Media]:
    """Return a bounded local media selection for the visual editor picker."""
    return list(
        db.session.scalars(db.select(Media).order_by(Media.created_at.desc()).limit(30)).all()
    )


@admin_bp.route("/taxonomy/", methods=["GET", "POST"])
@permission_required("taxonomy.manage")
def taxonomy():
    form = TaxonomyForm()
    current_type = request.args.get("type", "category")
    if request.method == "POST":
        current_type = form.taxonomy_type.data or current_type
    if current_type not in {"category", "tag"}:
        current_type = "category"
    if request.method == "GET":
        form.taxonomy_type.data = current_type
    if form.validate_on_submit():
        item, created = create_taxonomy(
            form.taxonomy_type.data,
            form.name.data.strip(),
            form.slug.data or "",
            form.description.data or "",
        )
        if created:
            db.session.flush()
            record_audit("taxonomy.create", form.taxonomy_type.data, str(item.id), item.name)
            db.session.commit()
            flash("分类或标签已经创建。", "success")
        else:
            flash("同名项目已经存在。", "warning")
        return redirect(url_for("admin.taxonomy", type=current_type))
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    tags = db.session.scalars(db.select(Tag).order_by(Tag.name)).all()
    return render_template(
        "admin/posts/taxonomy.html",
        form=form,
        categories=categories,
        tags=tags,
        current_type=current_type,
        action_form=EmptyForm(),
    )


@admin_bp.get("/taxonomy/categories/")
@permission_required("taxonomy.manage")
def category_list():
    return _render_taxonomy_list("category")


@admin_bp.route("/taxonomy/categories/new/", methods=["GET", "POST"])
@permission_required("taxonomy.manage")
def create_category():
    return _render_taxonomy_create("category")


@admin_bp.get("/taxonomy/tags/")
@permission_required("taxonomy.manage")
def tag_list():
    return _render_taxonomy_list("tag")


@admin_bp.route("/taxonomy/tags/new/", methods=["GET", "POST"])
@permission_required("taxonomy.manage")
def create_tag():
    return _render_taxonomy_create("tag")


@admin_bp.post("/taxonomy/<taxonomy_type>/<int:item_id>/delete/")
@permission_required("taxonomy.manage")
def delete_taxonomy(taxonomy_type: str, item_id: int):
    _validate_action_form()
    model = Category if taxonomy_type == "category" else Tag if taxonomy_type == "tag" else None
    if model is None:
        abort(404)
    item = db.get_or_404(model, item_id)
    name = item.name
    record_audit("taxonomy.delete", taxonomy_type, str(item.id), name)
    db.session.delete(item)
    db.session.commit()
    flash(f"“{name}”已删除，文章正文不受影响。", "success")
    return redirect(
        url_for("admin.category_list" if taxonomy_type == "category" else "admin.tag_list")
    )


def _render_taxonomy_list(taxonomy_type: str):
    model = Category if taxonomy_type == "category" else Tag
    items = db.session.scalars(db.select(model).order_by(model.name)).all()
    return render_template(
        "admin/posts/taxonomy_list.html",
        taxonomy_type=taxonomy_type,
        taxonomy_label="分类" if taxonomy_type == "category" else "标签",
        items=items,
        action_form=EmptyForm(),
    )


def _render_taxonomy_create(taxonomy_type: str):
    form = TaxonomyForm()
    form.taxonomy_type.data = taxonomy_type
    if form.validate_on_submit():
        item, created = create_taxonomy(
            taxonomy_type,
            form.name.data.strip(),
            form.slug.data or "",
            form.description.data or "",
        )
        if created:
            db.session.flush()
            record_audit("taxonomy.create", taxonomy_type, str(item.id), item.name)
            db.session.commit()
            flash(f"{'分类' if taxonomy_type == 'category' else '标签'}已经创建。", "success")
            return redirect(
                url_for("admin.category_list" if taxonomy_type == "category" else "admin.tag_list")
            )
        flash("同名项目已经存在。", "warning")
    return render_template(
        "admin/posts/taxonomy_form.html",
        form=form,
        taxonomy_type=taxonomy_type,
        taxonomy_label="分类" if taxonomy_type == "category" else "标签",
    )


def _configure_post_form(form: PostForm) -> None:
    categories = db.session.scalars(db.select(Category).order_by(Category.name)).all()
    form.category_id.choices = [(0, "无分类"), *((item.id, item.name) for item in categories)]


def _enforce_publish_permission(status: str) -> None:
    if status in {"published", "scheduled"} and not current_user.has_permission("posts.publish"):
        abort(403)


def _validate_action_form() -> None:
    if not EmptyForm().validate_on_submit():
        abort(400)
