"""Administration routes for pages, menus and site-level configuration."""

from __future__ import annotations

import json
from uuid import uuid4

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import EmptyForm, SiteLogoUploadForm
from app.models import CustomPage, ExternalLinkRule, Media
from app.security import permission_required, record_audit
from app.services.access import (
    get_access_policy,
    parse_bound_urls,
    request_hostname,
    save_bound_urls,
    save_security_policy,
)
from app.services.cache import site_context_cache
from app.services.content import get_setting, safe_content_url, set_setting
from app.services.external_links import (
    LINK_CLASSIFICATIONS,
    ExternalLinkError,
    normalize_hostname,
)
from app.services.media import MediaValidationError, delete_stored_image, store_image
from app.services.site_management import (
    ADMIN_NAVIGATION_DEFAULTS,
    SYSTEM_PAGES,
    load_admin_navigation,
    load_footer_content,
    load_managed_pages,
    load_primary_menu,
    save_admin_navigation,
    save_footer_content,
    save_managed_pages,
    save_primary_menu,
)


def _commit_setting(action: str, target: str, summary: str, message: str) -> None:
    record_audit(action, "site", target, summary)
    db.session.commit()
    site_context_cache.clear()
    flash(message, "success")


@admin_bp.route("/pages/front/", methods=["GET", "POST"])
@permission_required("pages.manage")
def front_pages():
    """Edit the visible heading copy for pages currently exposed in the primary navigation."""
    pages = load_managed_pages()
    visible_targets = {
        item["target"]
        for item in load_primary_menu()
        if item["visible"] and item["target_type"] == "system"
    }
    navigation_pages = [
        page for page in pages if page["enabled"] and page["key"] in visible_targets
    ]

    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        page_key = request.form.get("page_key", "").strip()
        page = next((item for item in navigation_pages if item["key"] == page_key), None)
        if page is None:
            abort(404)
        page["title"] = request.form.get("title", "").strip()[:180] or page["title"]
        page["subtitle"] = request.form.get("subtitle", "").strip()[:500]
        save_managed_pages(pages)
        _commit_setting(
            "page.navigation_copy.update",
            page_key,
            page["title"],
            "前台页面的标题与副标题已经保存。",
        )
        return redirect(url_for("admin.front_pages"))

    return render_template("admin/site/front_pages.html", pages=navigation_pages)


@admin_bp.route("/pages/system/<key>/", methods=["GET", "POST"])
@permission_required("pages.manage")
def edit_system_page(key: str):
    pages = load_managed_pages()
    page = next((item for item in pages if item["key"] == key), None)
    if page is None:
        abort(404)
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        page["label"] = request.form.get("label", page["label"]).strip()[:80] or page["label"]
        page["title"] = request.form.get("title", page["title"]).strip()[:180] or page["title"]
        page["subtitle"] = request.form.get("subtitle", "").strip()[:500]
        page["enabled"] = request.form.get("enabled") == "y"
        page["nav"] = request.form.get("nav") == "y"
        blocks = []
        titles = request.form.getlist("block_title")
        contents = request.form.getlist("block_content")
        styles = request.form.getlist("block_style")
        enabled = set(request.form.getlist("block_enabled"))
        block_ids = request.form.getlist("block_id")
        for index, title in enumerate(titles):
            block_id = (block_ids[index] if index < len(block_ids) else uuid4().hex)[:80]
            content = contents[index] if index < len(contents) else ""
            style = styles[index] if index < len(styles) else "card"
            if style not in {"card", "note", "wide", "quote"}:
                style = "card"
            if not title.strip() and not content.strip():
                continue
            blocks.append(
                {
                    "id": block_id,
                    "title": title.strip()[:160],
                    "content": content[:100_000],
                    "style": style,
                    "enabled": block_id in enabled,
                    "sort_order": index * 10,
                }
            )
        page["blocks"] = blocks
        save_managed_pages(pages)
        _commit_setting(
            "page.system.update",
            key,
            page["title"],
            "页面文字、板块和显示状态已经保存。",
        )
        return redirect(url_for("admin.edit_system_page", key=key))
    return render_template("admin/site/system_page_editor.html", page=page)


@admin_bp.post("/pages/system/<key>/toggle/")
@permission_required("pages.manage")
def toggle_system_page(key: str):
    if not EmptyForm().validate_on_submit():
        abort(400)
    pages = load_managed_pages()
    page = next((item for item in pages if item["key"] == key), None)
    if page is None:
        abort(404)
    page["enabled"] = not page["enabled"]
    save_managed_pages(pages)
    _commit_setting(
        "page.system.toggle",
        key,
        "enabled" if page["enabled"] else "disabled",
        "页面已经启用。" if page["enabled"] else "页面已经停用。",
    )
    return redirect(url_for("admin.pages"))


@admin_bp.route("/menu/primary/", methods=["GET", "POST"])
@permission_required("site.manage")
def primary_menu():
    items = load_primary_menu()
    pages = db.session.scalars(db.select(CustomPage).order_by(CustomPage.title)).all()
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        actions = request.form.getlist("action")
        action = actions[-1] if actions else "save"
        item_id = request.form.get("item_id", "")
        if action == "create":
            item_id = f"custom-{uuid4().hex[:12]}"
            items.append(
                {
                    "id": item_id,
                    "label": "新菜单项",
                    "target_type": "url",
                    "target": "",
                    "url": "/",
                    "visible": True,
                    "open_new_tab": False,
                    "roles": [],
                    "sort_order": len(items) * 10 + 10,
                }
            )
        elif action == "delete":
            items = [item for item in items if item["id"] != item_id]
        elif action == "reorder":
            try:
                order = json.loads(request.form.get("menu_order", "[]"))
            except ValueError:
                order = []
            positions = {str(value): index for index, value in enumerate(order)}
            items.sort(key=lambda item: positions.get(item["id"], len(items)))
            for index, item in enumerate(items):
                item["sort_order"] = index * 10
        else:
            item = next((entry for entry in items if entry["id"] == item_id), None)
            if item is None:
                abort(404)
            target_type = request.form.get("target_type", "url")
            if target_type not in {"system", "page", "url"}:
                abort(400)
            item["label"] = request.form.get("label", "").strip()[:80] or item["label"]
            item["target_type"] = target_type
            item["target"] = request.form.get("target", "").strip()[:180]
            try:
                item["url"] = safe_content_url(
                    request.form.get("url", "") or "/", allow_empty=False
                )
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin.primary_menu"))
            item["visible"] = request.form.get("visible") == "y"
            item["open_new_tab"] = request.form.get("open_new_tab") == "y"
        save_primary_menu(items)
        _commit_setting("menu.primary.update", item_id, action, "前台菜单已经更新。")
        return redirect(url_for("admin.primary_menu"))
    return render_template(
        "admin/site/primary_menu.html",
        items=items,
        system_pages=SYSTEM_PAGES,
        pages=pages,
    )


@admin_bp.route("/menu/admin-layout/", methods=["GET", "POST"])
@permission_required("site.manage")
def admin_menu_editor():
    layout = load_admin_navigation()
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        try:
            supplied = json.loads(request.form.get("layout", "{}"))
        except ValueError:
            supplied = {}
        if not isinstance(supplied, dict):
            abort(400)
        save_admin_navigation(supplied)
        _commit_setting("menu.admin.update", "layout", "reordered", "后台菜单顺序已经保存。")
        return redirect(url_for("admin.admin_menu_editor"))
    return render_template(
        "admin/site/admin_menu_editor.html",
        layout=layout,
        catalogue=ADMIN_NAVIGATION_DEFAULTS,
    )


@admin_bp.route("/site/identity/", methods=["GET", "POST"])
@permission_required("site.manage")
def site_identity():
    logo_form = SiteLogoUploadForm()
    if request.method == "POST":
        action = request.form.get("action", "identity")
        if action == "logo":
            if not logo_form.validate_on_submit():
                flash("请选择可用的JPEG、PNG或WebP图片。", "error")
                return redirect(url_for("admin.site_identity"))
            try:
                stored = store_image(logo_form.logo.data)
            except MediaValidationError as error:
                flash(str(error), "error")
                return redirect(url_for("admin.site_identity"))
            extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[
                stored.mime_type
            ]
            media = Media(
                filename=stored.filename,
                thumbnail_filename=stored.thumbnail_filename,
                original_filename=f"site-logo{extension}",
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                width=stored.width,
                height=stored.height,
                alt_text="网站Logo",
                created_by_id=current_user.id,
            )
            try:
                db.session.add(media)
                db.session.flush()
                set_setting("site_logo_media_id", str(media.id))
                _commit_setting("site.logo.update", str(media.id), "网站Logo", "网站Logo已经更新。")
            except Exception:
                db.session.rollback()
                delete_stored_image(stored.filename, stored.thumbnail_filename)
                raise
            return redirect(url_for("admin.site_identity"))
        if not EmptyForm().validate_on_submit():
            abort(400)
        display_name = request.form.get("site_display_name", "").strip()[:100]
        tagline = request.form.get("site_display_tagline", "").strip()[:180]
        if not display_name:
            flash("网站主标题不能为空。", "error")
            return redirect(url_for("admin.site_identity"))
        set_setting("site_display_name", display_name)
        set_setting("site_display_tagline", tagline)
        _commit_setting("site.identity.update", "identity", display_name, "网站标题已经保存。")
        return redirect(url_for("admin.site_identity"))
    logo_id = get_setting("site_logo_media_id", "")
    logo = db.session.get(Media, int(logo_id)) if logo_id.isdigit() else None
    return render_template(
        "admin/site/site_identity.html",
        logo_form=logo_form,
        remove_form=EmptyForm(),
        current_logo=logo,
        display_name=get_setting("site_display_name", "sau_bakaの博客"),
        tagline=get_setting("site_display_tagline", "记录代码、设计与生活"),
    )


@admin_bp.route("/site/footer/", methods=["GET", "POST"])
@permission_required("site.manage")
def site_footer_settings():
    footer = load_footer_content()
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        try:
            columns = json.loads(request.form.get("footer_columns", "[]"))
        except ValueError:
            columns = []
        if not isinstance(columns, list):
            columns = []
        footer = {
            "description": request.form.get("description", "").strip()[:300],
            "copyright": request.form.get("copyright", "").strip()[:255],
            "columns": columns[:8],
        }
        save_footer_content(footer)
        set_setting("footer_text", footer["copyright"])
        _commit_setting("site.footer.update", "footer", "content", "页尾内容已经保存。")
        return redirect(url_for("admin.site_footer_settings"))
    return render_template("admin/site/footer_settings.html", footer=footer)


@admin_bp.route("/site/third-party-links/", methods=["GET", "POST"])
@permission_required("site.manage")
def third_party_links():
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        rule_id = request.form.get("rule_id", type=int)
        rule = db.session.get(ExternalLinkRule, rule_id) if rule_id else ExternalLinkRule()
        if rule_id and rule is None:
            abort(404)
        classification = request.form.get("classification", "unknown").strip().lower()
        try:
            hostname = normalize_hostname(request.form.get("hostname", ""))
            if classification not in LINK_CLASSIFICATIONS:
                raise ExternalLinkError("请选择安全站点或危险站点。")
        except ExternalLinkError as error:
            flash(str(error), "error")
        else:
            duplicate = db.session.scalar(
                db.select(ExternalLinkRule).where(
                    ExternalLinkRule.hostname == hostname,
                    ExternalLinkRule.id != (rule.id or 0),
                )
            )
            if duplicate is not None:
                flash("这个域名已经存在，请直接编辑原有规则。", "error")
            else:
                rule.hostname = hostname
                rule.classification = classification
                rule.display_name = request.form.get("display_name", "").strip()[:120]
                rule.note = request.form.get("note", "").strip()[:500]
                db.session.add(rule)
                try:
                    record_audit(
                        "site.external_link.save",
                        "external_link_rule",
                        str(rule.id or hostname),
                        f"{hostname}:{classification}",
                    )
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("这个域名已经存在，请直接编辑原有规则。", "error")
                else:
                    flash("第三方站点状态已经保存。", "success")
                    return redirect(url_for("admin.third_party_links"))
    selected = request.args.get("status", "all").strip().lower()
    query = request.args.get("q", "").strip()[:120]
    statement = db.select(ExternalLinkRule)
    if selected in LINK_CLASSIFICATIONS:
        statement = statement.where(ExternalLinkRule.classification == selected)
    else:
        selected = "all"
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            db.or_(
                ExternalLinkRule.hostname.ilike(pattern),
                ExternalLinkRule.display_name.ilike(pattern),
                ExternalLinkRule.note.ilike(pattern),
            )
        )
    page = db.paginate(
        statement.order_by(
            ExternalLinkRule.classification,
            ExternalLinkRule.hostname,
        ),
        page=request.args.get("page", 1, type=int),
        per_page=30,
        error_out=False,
    )
    counts = dict(
        db.session.execute(
            db.select(ExternalLinkRule.classification, db.func.count(ExternalLinkRule.id)).group_by(
                ExternalLinkRule.classification
            )
        ).all()
    )
    return render_template(
        "admin/site/third_party_links.html",
        rules=page.items,
        page=page,
        query=query,
        selected=selected,
        counts={key: int(counts.get(key, 0)) for key in LINK_CLASSIFICATIONS},
        form=EmptyForm(),
    )


@admin_bp.post("/site/third-party-links/<int:rule_id>/delete/")
@permission_required("site.manage")
def delete_third_party_link(rule_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    rule = db.get_or_404(ExternalLinkRule, rule_id)
    hostname = rule.hostname
    db.session.delete(rule)
    record_audit(
        "site.external_link.delete",
        "external_link_rule",
        str(rule_id),
        hostname,
    )
    db.session.commit()
    flash("规则已经删除，该站点会恢复为安全性未知。", "success")
    return redirect(url_for("admin.third_party_links"))


@admin_bp.route("/site/addresses/", methods=["GET", "POST"])
@permission_required("system.maintain")
def site_addresses():
    policy = get_access_policy()
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        raw = request.form.get("bound_urls", "")
        try:
            urls = parse_bound_urls(raw)
        except ValueError as error:
            flash(str(error), "error")
        else:
            current = f"{request.scheme}://{request.host}"
            if urls and current not in urls:
                flash(f"当前访问网址 {current} 必须完整保留在绑定列表中。", "error")
            else:
                save_bound_urls(raw)
                _commit_setting(
                    "site.addresses.update", "hosts", "\n".join(urls), "网站链接已经保存。"
                )
                return redirect(url_for("admin.site_addresses"))
    return render_template(
        "admin/site/site_addresses.html", policy=policy, current_host=request_hostname(request.host)
    )


@admin_bp.route("/site/security/", methods=["GET", "POST"])
@permission_required("system.maintain")
def site_security():
    policy = get_access_policy()
    try:
        login_max_failures = min(
            20, max(3, int(get_setting("admin_login_max_failures", "5")))
        )
        login_lock_minutes = min(
            180, max(1, int(get_setting("admin_login_lock_minutes", "15")))
        )
    except (TypeError, ValueError):
        login_max_failures, login_lock_minutes = 5, 15
    if request.method == "POST":
        if not EmptyForm().validate_on_submit():
            abort(400)
        require_https = request.form.get("require_https") == "y"
        hotlink = request.form.get("hotlink_protection") == "y"
        try:
            login_max_failures = min(
                20, max(3, int(request.form.get("admin_login_max_failures", "5")))
            )
            login_lock_minutes = min(
                180, max(1, int(request.form.get("admin_login_lock_minutes", "15")))
            )
        except ValueError:
            flash("登录限制必须填写整数。", "error")
            return render_template(
                "admin/site/site_security.html",
                policy=policy,
                login_max_failures=login_max_failures,
                login_lock_minutes=login_lock_minutes,
            ), 400
        if require_https and not request.is_secure and request.form.get("confirm_https") != "y":
            flash("请先确认HTTPS已经能够正常访问。", "error")
        else:
            save_security_policy(require_https, hotlink)
            set_setting("admin_login_max_failures", str(login_max_failures))
            set_setting("admin_login_lock_minutes", str(login_lock_minutes))
            _commit_setting(
                "site.security.update",
                "security",
                f"https={require_https},hotlink={hotlink}",
                "站点安全设置已经保存。",
            )
            target = url_for("admin.site_security", _external=True)
            return redirect(target.replace("http://", "https://", 1) if require_https else target)
    return render_template(
        "admin/site/site_security.html",
        policy=policy,
        login_max_failures=login_max_failures,
        login_lock_minutes=login_lock_minutes,
    )
