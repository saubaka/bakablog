"""Stage-six personal content and site configuration administration."""

from __future__ import annotations

from datetime import UTC, datetime

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.blueprints.admin import admin_bp
from app.extensions import db
from app.forms import (
    CustomPageForm,
    DialogAppearanceForm,
    EmptyForm,
    InterfaceAppearanceForm,
    MomentForm,
    NavigationForm,
    ProfileForm,
    ProfileItemForm,
    ProjectForm,
    SeoSettingsForm,
    SiteLogoUploadForm,
    SiteSettingsForm,
    TransitionSettingsForm,
)
from app.models import (
    CustomPage,
    Experience,
    HomeModule,
    Media,
    Moment,
    NavigationItem,
    PersonalGoal,
    PersonalSkill,
    Project,
    SiteProfile,
    SocialLink,
)
from app.security import permission_required, record_audit
from app.services.blog import render_markdown
from app.services.content import (
    COMPONENT_MOTION_DEFAULTS,
    COMPONENT_MOTION_SOFTNESS_CHOICES,
    COMPONENT_MOTION_SOFTNESS_VALUES,
    COMPONENT_MOTION_STYLE_CHOICES,
    COMPONENT_MOTION_STYLE_VALUES,
    DIALOG_APPEARANCE_DEFAULTS,
    DIALOG_SHADOW_CHOICES,
    DIALOG_SHADOW_VALUES,
    GLOBAL_FONT_CHOICES,
    GLOBAL_FONT_VALUES,
    HOME_MODULE_ADMIN_META,
    HOME_MODULE_LABELS,
    HOME_SETTING_DEFAULTS,
    NOTIFICATION_MOTION_FIELDS,
    NOTIFICATION_MOTION_PRESETS,
    NOTIFICATION_MOTION_SETTING,
    NOTIFICATION_STACK_RANGE,
    NOTIFICATION_TYPE_LABELS,
    NOTIFICATION_TYPES,
    OVERLAY_REVISION_SETTING,
    PAGE_TRANSITION_CHOICES,
    PAGE_TRANSITION_COLOR_DEFAULTS,
    PAGE_TRANSITION_VALUES,
    apply_moment_form,
    apply_page_form,
    apply_project_form,
    get_setting,
    normalize_component_motion_style,
    notification_motion_from_form,
    notification_motion_json,
    parse_notification_motion,
    resolve_color_setting,
    safe_content_url,
    set_setting,
    sync_default_home_modules,
)
from app.services.media import MediaValidationError, delete_stored_image, store_image
from app.services.seo import (
    SEO_DEFAULTS,
    SEO_SCHEMA_CHOICES,
    SEO_TWITTER_CARD_CHOICES,
    get_seo_values,
    save_seo_values,
)
from app.services.site_management import load_managed_pages

SITE_LOGO_MEDIA_SETTING = "site_logo_media_id"


def _site_logo_media() -> Media | None:
    value = get_setting(SITE_LOGO_MEDIA_SETTING, "")
    if not value.isdigit():
        return None
    return db.session.get(Media, int(value))


@admin_bp.route("/profile/", methods=["GET", "POST"])
@permission_required("profile.manage")
def profile():
    profile_item = db.session.scalar(db.select(SiteProfile).limit(1))
    if profile_item is None:
        profile_item = SiteProfile()
        db.session.add(profile_item)
        db.session.flush()
    form = ProfileForm(obj=profile_item)
    media = db.session.scalars(db.select(Media).order_by(Media.created_at.desc())).all()
    form.avatar_media_id.choices = [
        (0, "使用文字头像"),
        *((item.id, item.original_filename) for item in media),
    ]
    if form.validate_on_submit():
        try:
            resume_url = safe_content_url(form.resume_url.data or "")
        except ValueError as error:
            form.resume_url.errors.append(str(error))
        else:
            html, _, _ = render_markdown(form.bio_markdown.data or "")
            form.populate_obj(profile_item)
            profile_item.resume_url = resume_url
            profile_item.avatar_media_id = form.avatar_media_id.data or None
            profile_item.bio_html = html
            record_audit(
                "profile.update", "site_profile", str(profile_item.id), profile_item.display_name
            )
            db.session.commit()
            flash("个人资料已经保存。", "success")
            return redirect(url_for("admin.profile"))
    return render_template(
        "admin/content/profile.html",
        form=form,
        profile=profile_item,
        item_form=ProfileItemForm(),
        skills=db.session.scalars(
            db.select(PersonalSkill).order_by(PersonalSkill.sort_order)
        ).all(),
        experiences=db.session.scalars(db.select(Experience).order_by(Experience.sort_order)).all(),
        goals=db.session.scalars(db.select(PersonalGoal).order_by(PersonalGoal.sort_order)).all(),
        socials=db.session.scalars(db.select(SocialLink).order_by(SocialLink.sort_order)).all(),
        action_form=EmptyForm(),
    )


@admin_bp.post("/profile/items/")
@permission_required("profile.manage")
def create_profile_item():
    form = ProfileItemForm()
    if not form.validate_on_submit():
        flash("个人内容填写不完整。", "error")
        return redirect(url_for("admin.profile"))
    values = {
        "sort_order": form.sort_order.data or 0,
        "is_visible": bool(form.is_visible.data),
    }
    if form.item_type.data == "skill":
        item = PersonalSkill(
            name=form.title.data.strip(),
            group_name=(form.subtitle.data or "技能").strip(),
            level=form.level.data or 80,
            **values,
        )
    elif form.item_type.data == "experience":
        item = Experience(
            title=form.title.data.strip(),
            organization=(form.subtitle.data or "").strip(),
            period=(form.period.data or "").strip(),
            description=(form.description.data or "").strip(),
            **values,
        )
    elif form.item_type.data == "goal":
        item = PersonalGoal(
            title=form.title.data.strip(),
            description=(form.description.data or "").strip(),
            **values,
        )
    else:
        try:
            url = safe_content_url(form.subtitle.data or "", allow_empty=False)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin.profile"))
        item = SocialLink(label=form.title.data.strip(), url=url, **values)
    db.session.add(item)
    db.session.flush()
    record_audit("profile.item.create", form.item_type.data, str(item.id), form.title.data)
    db.session.commit()
    flash("个人内容已经添加。", "success")
    return redirect(url_for("admin.profile"))


@admin_bp.route("/profile/items/<item_type>/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("profile.manage")
def edit_profile_item(item_type: str, item_id: int):
    models = {
        "skill": PersonalSkill,
        "experience": Experience,
        "goal": PersonalGoal,
        "social": SocialLink,
    }
    model = models.get(item_type)
    if model is None:
        abort(404)
    item = db.get_or_404(model, item_id)
    form = ProfileItemForm()
    if request.method == "GET":
        form.item_type.data = item_type
        form.title.data = getattr(item, "name", getattr(item, "title", getattr(item, "label", "")))
        form.subtitle.data = getattr(
            item, "group_name", getattr(item, "organization", getattr(item, "url", ""))
        )
        form.period.data = getattr(item, "period", "")
        form.description.data = getattr(item, "description", "")
        form.level.data = getattr(item, "level", 80)
        form.sort_order.data = item.sort_order
        form.is_visible.data = item.is_visible
    if form.validate_on_submit():
        link_error = False
        if item_type == "skill":
            item.name = form.title.data.strip()
            item.group_name = (form.subtitle.data or "技能").strip()
            item.level = form.level.data or 80
        elif item_type == "experience":
            item.title = form.title.data.strip()
            item.organization = (form.subtitle.data or "").strip()
            item.period = (form.period.data or "").strip()
            item.description = (form.description.data or "").strip()
        elif item_type == "goal":
            item.title = form.title.data.strip()
            item.description = (form.description.data or "").strip()
        else:
            try:
                item.url = safe_content_url(form.subtitle.data or "", allow_empty=False)
            except ValueError as error:
                form.subtitle.errors.append(str(error))
                link_error = True
            else:
                item.label = form.title.data.strip()
        if not link_error:
            item.sort_order = form.sort_order.data or 0
            item.is_visible = bool(form.is_visible.data)
            record_audit("profile.item.update", item_type, str(item.id), form.title.data)
            db.session.commit()
            flash("个人内容已经更新。", "success")
            return redirect(url_for("admin.profile"))
    return render_template(
        "admin/content/profile_item_editor.html", form=form, item=item, item_type=item_type
    )


@admin_bp.post("/profile/items/<item_type>/<int:item_id>/delete/")
@permission_required("profile.manage")
def delete_profile_item(item_type: str, item_id: int):
    _action_form()
    models = {
        "skill": PersonalSkill,
        "experience": Experience,
        "goal": PersonalGoal,
        "social": SocialLink,
    }
    model = models.get(item_type)
    if model is None:
        abort(404)
    item = db.get_or_404(model, item_id)
    db.session.delete(item)
    record_audit("profile.item.delete", item_type, str(item_id), "")
    db.session.commit()
    return redirect(url_for("admin.profile"))


@admin_bp.get("/projects/")
@permission_required("projects.view")
def projects():
    include_deleted = request.args.get("deleted") == "1"
    condition = Project.deleted_at.is_not(None) if include_deleted else Project.deleted_at.is_(None)
    items = db.session.scalars(
        db.select(Project).where(condition).order_by(Project.sort_order, Project.updated_at.desc())
    ).all()
    return render_template(
        "admin/content/projects.html",
        projects=items,
        include_deleted=include_deleted,
        action_form=EmptyForm(),
    )


@admin_bp.route("/projects/new/", methods=["GET", "POST"])
@admin_bp.route("/projects/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("projects.manage")
def edit_project(item_id: int | None = None):
    project = db.get_or_404(Project, item_id) if item_id else Project(title="", slug="")
    form = ProjectForm(obj=project)
    _media_choices(form.cover_media_id)
    if form.validate_on_submit():
        _publish_permission(form.status.data, "projects.publish")
        try:
            apply_project_form(project, form)
        except ValueError as error:
            form.project_url.errors.append(str(error))
        else:
            db.session.add(project)
            db.session.flush()
            record_audit("project.save", "project", str(project.id), project.title)
            db.session.commit()
            flash("项目作品已经保存。", "success")
            return redirect(url_for("admin.edit_project", item_id=project.id))
    return render_template(
        "admin/content/project_editor.html", form=form, project=project if item_id else None
    )


@admin_bp.post("/projects/<int:item_id>/<action>/")
@permission_required("projects.manage")
def project_action(item_id: int, action: str):
    _action_form()
    project = db.get_or_404(Project, item_id)
    if action == "delete":
        project.deleted_at = datetime.now(UTC)
    elif action == "restore":
        _publish_permission(project.status, "projects.publish")
        project.deleted_at = None
    else:
        abort(404)
    record_audit(f"project.{action}", "project", str(project.id), project.title)
    db.session.commit()
    return redirect(url_for("admin.projects", deleted=0))


@admin_bp.get("/moments/")
@permission_required("moments.view")
def moments():
    status_filter = request.args.get("status", "all")
    if status_filter not in {"all", "draft", "published"}:
        status_filter = "all"
    statement = (
        db.select(Moment).where(Moment.deleted_at.is_(None)).order_by(Moment.updated_at.desc())
    )
    if status_filter != "all":
        statement = statement.where(Moment.status == status_filter)
    items = db.session.scalars(statement).all()
    return render_template(
        "admin/content/moments.html",
        moments=items,
        current_status=status_filter,
        action_form=EmptyForm(),
    )


@admin_bp.route("/moments/new/", methods=["GET", "POST"])
@admin_bp.route("/moments/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("moments.manage")
def edit_moment(item_id: int | None = None):
    moment = (
        db.get_or_404(Moment, item_id) if item_id else Moment(content_markdown="", content_html="")
    )
    form = MomentForm(obj=moment)
    if form.validate_on_submit():
        _publish_permission(form.status.data, "moments.publish")
        apply_moment_form(moment, form)
        db.session.add(moment)
        db.session.flush()
        record_audit("moment.save", "moment", str(moment.id), moment.mood)
        db.session.commit()
        flash("动态已经保存。", "success")
        return redirect(url_for("admin.edit_moment", item_id=moment.id))
    return render_template(
        "admin/content/moment_editor.html", form=form, moment=moment if item_id else None
    )


@admin_bp.post("/moments/<int:item_id>/delete/")
@permission_required("moments.manage")
def delete_moment(item_id: int):
    _action_form()
    moment = db.get_or_404(Moment, item_id)
    moment.deleted_at = datetime.now(UTC)
    record_audit("moment.delete", "moment", str(moment.id), moment.mood)
    db.session.commit()
    return redirect(url_for("admin.moments"))


@admin_bp.route("/site-content/", methods=["GET", "POST"])
@permission_required("site.manage")
def site_content():
    site_section = request.args.get("section", "content")
    if site_section not in {"content", "navigation"}:
        site_section = "content"
    form = SiteSettingsForm()
    if request.method == "GET":
        for name, default in HOME_SETTING_DEFAULTS.items():
            getattr(form, name).data = get_setting(name, default)
    if form.validate_on_submit():
        clean_urls: dict[str, str] = {}
        urls_valid = True
        for name in (
            "hero_primary_url",
            "hero_secondary_url",
            "hero_explore_url",
            "cta_button_url",
        ):
            try:
                clean_urls[name] = safe_content_url(getattr(form, name).data or "")
            except ValueError as error:
                getattr(form, name).errors.append(str(error))
                urls_valid = False
        if urls_valid:
            for name in HOME_SETTING_DEFAULTS:
                value = clean_urls.get(name, getattr(form, name).data or "")
                set_setting(name, value)
            record_audit("site.settings.update", "site", "settings", "首页2.0与页脚配置")
            db.session.commit()
            flash("首页叙事与站点文字已经保存。", "success")
            return redirect(url_for("admin.site_content", section="content"))
    modules = sync_default_home_modules()
    return render_template(
        "admin/content/site_content.html",
        form=form,
        modules=modules,
        navigation_form=NavigationForm(),
        navigation=db.session.scalars(
            db.select(NavigationItem).order_by(NavigationItem.sort_order)
        ).all(),
        action_form=EmptyForm(),
        module_labels=HOME_MODULE_LABELS,
        module_meta=HOME_MODULE_ADMIN_META,
        site_section=site_section,
    )


@admin_bp.route("/pages/home/", methods=["GET", "POST"])
@permission_required("site.manage")
def home_management():
    """A page-management entry point for the homepage editor.

    The underlying editor is shared so its existing module controls remain a
    single source of truth rather than duplicating the home settings form.
    """
    return site_content()


@admin_bp.route("/appearance/transitions/", methods=["GET", "POST"])
@permission_required("site.manage")
def transition_settings():
    form = TransitionSettingsForm()
    form.transition_style.choices = list(PAGE_TRANSITION_CHOICES)
    form.component_motion_style.choices = list(COMPONENT_MOTION_STYLE_CHOICES)
    form.component_motion_softness.choices = list(COMPONENT_MOTION_SOFTNESS_CHOICES)
    if request.method == "GET":
        current_style = get_setting("page_transition_style", "stretch")
        form.transition_style.data = (
            current_style if current_style in PAGE_TRANSITION_VALUES else "stretch"
        )
        try:
            form.transition_duration.data = max(
                300, min(2400, int(get_setting("page_transition_duration", "720")))
            )
        except (TypeError, ValueError):
            form.transition_duration.data = 720
        for name, default in PAGE_TRANSITION_COLOR_DEFAULTS.items():
            getattr(form, name.removeprefix("page_")).data = resolve_color_setting(
                name, get_setting(name, default), default
            )
        try:
            form.component_motion_duration.data = max(
                520,
                min(
                    1100,
                    int(
                        get_setting(
                            "component_motion_duration",
                            COMPONENT_MOTION_DEFAULTS["component_motion_duration"],
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            form.component_motion_duration.data = 760
        component_style = get_setting(
            "component_motion_style", COMPONENT_MOTION_DEFAULTS["component_motion_style"]
        )
        form.component_motion_style.data = normalize_component_motion_style(component_style)
        component_softness = get_setting(
            "component_motion_softness",
            COMPONENT_MOTION_DEFAULTS["component_motion_softness"],
        )
        form.component_motion_softness.data = (
            component_softness if component_softness in COMPONENT_MOTION_SOFTNESS_VALUES else "soft"
        )
        form.component_motion_color.data = resolve_color_setting(
            "component_motion_color",
            get_setting("component_motion_color", COMPONENT_MOTION_DEFAULTS["component_motion_color"]),
            COMPONENT_MOTION_DEFAULTS["component_motion_color"],
        )
    if form.validate_on_submit():
        style = form.transition_style.data
        if style not in PAGE_TRANSITION_VALUES:
            abort(400)
        set_setting("page_transition_style", style)
        duration = max(300, min(2400, int(form.transition_duration.data)))
        set_setting("page_transition_duration", str(duration))
        for name in PAGE_TRANSITION_COLOR_DEFAULTS:
            field_name = name.removeprefix("page_")
            set_setting(name, getattr(form, field_name).data.lower())
        component_style = form.component_motion_style.data
        component_softness = form.component_motion_softness.data
        if component_style not in COMPONENT_MOTION_STYLE_VALUES:
            abort(400)
        if component_softness not in COMPONENT_MOTION_SOFTNESS_VALUES:
            abort(400)
        component_duration = max(520, min(1100, int(form.component_motion_duration.data)))
        set_setting("component_motion_duration", str(component_duration))
        set_setting("component_motion_style", component_style)
        set_setting("component_motion_color", form.component_motion_color.data.lower())
        set_setting("component_motion_softness", component_softness)
        record_audit(
            "site.transition.update",
            "site",
            "transitions",
            f"{style} / {duration}ms / 组件{component_duration}ms / {component_style}",
        )
        db.session.commit()
        flash("全站页面过渡方式已经更新。", "success")
        return redirect(url_for("admin.transition_settings"))
    return render_template(
        "admin/content/transitions.html",
        form=form,
        transition_choices=PAGE_TRANSITION_CHOICES,
        component_motion_styles=COMPONENT_MOTION_STYLE_CHOICES,
        component_motion_softness_choices=COMPONENT_MOTION_SOFTNESS_CHOICES,
    )


@admin_bp.route("/appearance/dialogs/", methods=["GET", "POST"])
@permission_required("site.manage")
def dialog_appearance():
    form = DialogAppearanceForm()
    form.dialog_shadow.choices = list(DIALOG_SHADOW_CHOICES)
    color_fields = (
        "dialog_accent", "toast_background", "toast_text", "toast_accent",
        "toast_success", "toast_warning", "toast_error",
    )
    metric_fields = (
        ("dialog_radius", 14, 42),
        ("dialog_width", 360, 720),
        ("dialog_backdrop_blur", 0, 30),
        ("toast_radius", 12, 32),
        ("toast_duration", 2000, 12000),
    )
    try:
        current_revision = int(get_setting(OVERLAY_REVISION_SETTING, "0"))
    except ValueError:
        current_revision = 0
    notice_motion = parse_notification_motion(get_setting(NOTIFICATION_MOTION_SETTING, ""))
    status = 200
    if request.method == "GET":
        current_shadow = get_setting("dialog_shadow", DIALOG_APPEARANCE_DEFAULTS["dialog_shadow"])
        form.dialog_shadow.data = current_shadow if current_shadow in DIALOG_SHADOW_VALUES else "soft"
        for name in color_fields:
            getattr(form, name).data = resolve_color_setting(
                name,
                get_setting(name, DIALOG_APPEARANCE_DEFAULTS[name]),
                DIALOG_APPEARANCE_DEFAULTS[name],
            )
        for name, minimum, maximum in metric_fields:
            try:
                value = int(get_setting(name, DIALOG_APPEARANCE_DEFAULTS[name]))
            except (TypeError, ValueError):
                value = int(DIALOG_APPEARANCE_DEFAULTS[name])
            getattr(form, name).data = max(minimum, min(maximum, value))
        form.revision.data = str(current_revision)
    elif form.validate_on_submit():
        if form.dialog_shadow.data not in DIALOG_SHADOW_VALUES:
            abort(400)
        submitted_motion, motion_errors = notification_motion_from_form(request.form)
        try:
            submitted_revision = int(form.revision.data or "-1")
        except ValueError:
            submitted_revision = -1
        notice_motion = submitted_motion
        if motion_errors:
            for message in motion_errors:
                flash(message, "error")
            status = 400
        elif submitted_revision != current_revision:
            # Keep the draft on screen; the next save is made against the
            # revision the administrator has now been shown.
            flash("这些设置刚刚在别处更新过。页面保留了你的修改，请核对后再保存一次。", "warning")
            form.revision.data = str(current_revision)
            status = 409
        else:
            for name in color_fields:
                set_setting(name, getattr(form, name).data.lower())
            set_setting("dialog_shadow", form.dialog_shadow.data)
            for name, _minimum, _maximum in metric_fields:
                set_setting(name, str(getattr(form, name).data))
            set_setting(NOTIFICATION_MOTION_SETTING, notification_motion_json(submitted_motion))
            set_setting(OVERLAY_REVISION_SETTING, str(current_revision + 1))
            record_audit(
                "site.dialog.update",
                "site",
                "dialogs",
                f"r{current_revision + 1} / {form.dialog_width.data}px / {form.dialog_shadow.data}",
            )
            db.session.commit()
            flash("全站弹窗与通知设置已经更新。", "success")
            return redirect(url_for("admin.dialog_appearance"))
    elif request.method == "POST":
        notice_motion, _errors = notification_motion_from_form(request.form)
        status = 400
    return render_template(
        "admin/content/dialogs.html",
        form=form,
        dialog_shadow_choices=DIALOG_SHADOW_CHOICES,
        notice_motion=notice_motion,
        notice_types=[(kind, NOTIFICATION_TYPE_LABELS[kind]) for kind in NOTIFICATION_TYPES],
        notice_fields=NOTIFICATION_MOTION_FIELDS,
        notice_stack_range=NOTIFICATION_STACK_RANGE,
        notice_presets=NOTIFICATION_MOTION_PRESETS,
    ), status


@admin_bp.route("/appearance/interface/", methods=["GET", "POST"])
@permission_required("site.manage")
def interface_appearance():
    section = request.args.get("section", "font")
    if section not in {"font", "hints"}:
        section = "font"
    if section == "hints" and request.method == "POST":
        action_form = EmptyForm()
        if not action_form.validate_on_submit():
            abort(400)
        hint_settings = {
            "admin_menu_subtitles_visible": request.form.get("admin_menu_subtitles_visible") == "y",
            "panel_descriptions_visible": request.form.get("panel_descriptions_visible") == "y",
            "card_descriptions_visible": request.form.get("card_descriptions_visible") == "y",
            "field_descriptions_visible": request.form.get("field_descriptions_visible") == "y",
        }
        for key, visible in hint_settings.items():
            set_setting(key, "true" if visible else "false")
        record_audit(
            "site.interface.hints",
            "site",
            "interface",
            ", ".join(key for key, visible in hint_settings.items() if visible) or "全部关闭",
        )
        db.session.commit()
        flash("提示与说明的显示范围已经更新。", "success")
        return redirect(url_for("admin.interface_appearance", section="hints"))
    form = InterfaceAppearanceForm()
    form.font_style.choices = list(GLOBAL_FONT_CHOICES)
    if request.method == "GET":
        current_font = get_setting("global_font_style", "cloud-rounded")
        form.font_style.data = (
            current_font if current_font in GLOBAL_FONT_VALUES else "cloud-rounded"
        )
    if form.validate_on_submit():
        if form.font_style.data not in GLOBAL_FONT_VALUES:
            abort(400)
        set_setting("global_font_style", form.font_style.data)
        record_audit("site.interface.update", "site", "interface", form.font_style.data)
        db.session.commit()
        flash("全局字体已经更新。", "success")
        return redirect(url_for("admin.interface_appearance", section="font"))
    hint_defaults = {
        "admin_menu_subtitles_visible": "true",
        "panel_descriptions_visible": "true",
        "card_descriptions_visible": "true",
        "field_descriptions_visible": "true",
    }
    hint_settings = {
        key: get_setting(key, default).strip().lower() in {"1", "true", "yes", "on"}
        for key, default in hint_defaults.items()
    }
    return render_template(
        "admin/content/interface.html",
        form=form,
        font_choices=GLOBAL_FONT_CHOICES,
        subtitles_visible=hint_settings["admin_menu_subtitles_visible"],
        hint_settings=hint_settings,
        action_form=EmptyForm(),
        interface_section=section,
    )


@admin_bp.route("/appearance/seo/", methods=["GET", "POST"])
@permission_required("site.manage")
def seo_settings():
    form = SeoSettingsForm()
    form.schema_type.choices = list(SEO_SCHEMA_CHOICES)
    form.twitter_card.choices = list(SEO_TWITTER_CARD_CHOICES)
    values = get_seo_values()
    field_map = {key.removeprefix("seo_"): key for key in SEO_DEFAULTS}
    boolean_fields = {
        "index_site",
        "follow_links",
        "index_archives",
        "index_taxonomies",
        "enable_sitemap",
        "enable_feed",
        "enable_structured_data",
    }
    if request.method == "GET":
        for field_name, setting_key in field_map.items():
            value = values[setting_key]
            getattr(form, field_name).data = (
                value.strip().lower() in {"1", "true", "yes", "on"}
                if field_name in boolean_fields
                else value
            )
    if form.validate_on_submit():
        image_url = (form.default_og_image.data or "").strip()
        try:
            clean_image_url = safe_content_url(image_url) if image_url else ""
        except ValueError as error:
            form.default_og_image.errors.append(str(error))
        else:
            robots_lines = []
            for line in (form.robots_disallow.data or "").splitlines():
                path = line.strip()
                if not path:
                    continue
                if not path.startswith("/") or "\x00" in path:
                    form.robots_disallow.errors.append("每条禁止路径必须以 / 开头。")
                    break
                robots_lines.append(path[:300])
            if not form.robots_disallow.errors:
                submitted: dict[str, str] = {}
                for field_name, setting_key in field_map.items():
                    if field_name == "default_og_image":
                        value = clean_image_url
                    elif field_name == "robots_disallow":
                        value = "\n".join(dict.fromkeys(robots_lines))
                    elif field_name in boolean_fields:
                        value = str(bool(getattr(form, field_name).data)).lower()
                    else:
                        value = str(getattr(form, field_name).data or "").strip()
                    submitted[setting_key] = value
                save_seo_values(submitted)
                record_audit("site.seo.update", "site", "seo", "搜索与分享外观")
                db.session.commit()
                flash("SEO、社交分享与抓取设置已经保存。", "success")
                return redirect(url_for("admin.seo_settings"))
    return render_template(
        "admin/content/seo.html",
        form=form,
        schema_choices=SEO_SCHEMA_CHOICES,
        card_choices=SEO_TWITTER_CARD_CHOICES,
    )


@admin_bp.route("/site/logo/", methods=["GET", "POST"])
@permission_required("site.manage")
def site_logo():
    form = SiteLogoUploadForm()
    current_logo = _site_logo_media()
    if request.method == "GET":
        return redirect(url_for("admin.site_identity"))
    if form.validate_on_submit():
        try:
            stored = store_image(form.logo.data)
        except MediaValidationError as error:
            form.logo.errors.append(str(error))
        else:
            extension = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }[stored.mime_type]
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
                set_setting(SITE_LOGO_MEDIA_SETTING, str(media.id))
                record_audit("site.logo.update", "media", str(media.id), "网站Logo")
                db.session.commit()
            except Exception:
                db.session.rollback()
                delete_stored_image(stored.filename, stored.thumbnail_filename)
                raise
            flash("网站Logo已经更新。", "success")
            return redirect(url_for("admin.site_identity"))
    return render_template(
        "admin/content/site_logo.html",
        form=form,
        current_logo=current_logo,
        remove_form=EmptyForm(),
    )


@admin_bp.post("/site/logo/remove/")
@permission_required("site.manage")
def remove_site_logo():
    if not EmptyForm().validate_on_submit():
        abort(400)
    current_logo = _site_logo_media()
    set_setting(SITE_LOGO_MEDIA_SETTING, "")
    record_audit(
        "site.logo.remove",
        "media",
        str(current_logo.id) if current_logo else "",
        "网站Logo",
    )
    db.session.commit()
    flash("网站Logo已经移除，站点恢复默认图标。", "success")
    return redirect(url_for("admin.site_identity"))


@admin_bp.post("/appearance/interface/menu-subtitles/")
@permission_required("site.manage")
def toggle_admin_menu_subtitles():
    if not EmptyForm().validate_on_submit():
        abort(400)
    visible = get_setting("admin_menu_subtitles_visible", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    set_setting("admin_menu_subtitles_visible", "false" if visible else "true")
    record_audit(
        "site.interface.menu_subtitles",
        "site",
        "interface",
        "hidden" if visible else "visible",
    )
    db.session.commit()
    flash("后台菜单小标题已关闭。" if visible else "后台菜单小标题已显示。", "success")
    return redirect(url_for("admin.interface_appearance", section="hints"))


@admin_bp.post("/site-content/modules/<int:item_id>/")
@permission_required("site.manage")
def update_home_module(item_id: int):
    if not EmptyForm().validate_on_submit():
        abort(400)
    module = db.get_or_404(HomeModule, item_id)
    module.title = request.form.get("title", module.title).strip()[:100] or module.title
    module.sort_order = request.form.get("sort_order", module.sort_order, type=int)
    module.item_limit = max(1, min(12, request.form.get("item_limit", module.item_limit, type=int)))
    style_variant = request.form.get("style_variant", module.style_variant)
    allowed_styles = HOME_MODULE_ADMIN_META.get(module.module_key, {}).get("styles", ())
    if style_variant in {value for value, _ in allowed_styles}:
        module.style_variant = style_variant
    module.is_enabled = request.form.get("is_enabled") == "y"
    record_audit("site.module.update", "home_module", str(module.id), module.module_key)
    db.session.commit()
    flash("首页模块已经更新。", "success")
    return redirect(url_for("admin.site_content", section="content", _anchor="home-modules"))


@admin_bp.post("/site-content/navigation/")
@permission_required("site.manage")
def create_navigation():
    form = NavigationForm()
    if form.validate_on_submit():
        try:
            url = safe_content_url(form.url.data, allow_empty=False)
        except ValueError as error:
            flash(str(error), "error")
        else:
            item = NavigationItem(
                label=form.label.data.strip(),
                url=url,
                location=form.location.data,
                sort_order=form.sort_order.data or 0,
                is_visible=bool(form.is_visible.data),
                open_new_tab=bool(form.open_new_tab.data),
            )
            db.session.add(item)
            db.session.commit()
            flash("导航链接已经添加。", "success")
    else:
        first_error = next(
            (message for messages in form.errors.values() for message in messages),
            "请检查名称、链接和显示位置。",
        )
        flash(f"导航链接未添加：{first_error}", "error")
    return redirect(url_for("admin.site_content", section="navigation", _anchor="home-navigation"))


@admin_bp.post("/site-content/navigation/<int:item_id>/delete/")
@permission_required("site.manage")
def delete_navigation(item_id: int):
    _action_form()
    db.session.delete(db.get_or_404(NavigationItem, item_id))
    db.session.commit()
    return redirect(url_for("admin.site_content", section="navigation", _anchor="home-navigation"))


@admin_bp.post("/site-content/navigation/<int:item_id>/")
@permission_required("site.manage")
def update_navigation(item_id: int):
    _action_form()
    item = db.get_or_404(NavigationItem, item_id)
    try:
        item.url = safe_content_url(request.form.get("url", ""), allow_empty=False)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(
            url_for("admin.site_content", section="navigation", _anchor="home-navigation")
        )
    label = request.form.get("label", item.label).strip()[:80]
    if not label:
        flash("导航名称不能为空。", "error")
        return redirect(
            url_for("admin.site_content", section="navigation", _anchor="home-navigation")
        )
    item.label = label
    item.location = request.form.get("location", item.location)
    if item.location not in {"header", "footer", "both"}:
        abort(400)
    item.sort_order = request.form.get("sort_order", item.sort_order, type=int)
    item.is_visible = request.form.get("is_visible") == "y"
    item.open_new_tab = request.form.get("open_new_tab") == "y"
    record_audit("navigation.update", "navigation", str(item.id), item.label)
    db.session.commit()
    flash("导航链接已经更新。", "success")
    return redirect(url_for("admin.site_content", section="navigation", _anchor="home-navigation"))


@admin_bp.get("/pages/")
@permission_required("pages.manage")
def pages():
    custom_pages = db.session.scalars(
        db.select(CustomPage).order_by(CustomPage.sort_order, CustomPage.updated_at.desc())
    ).all()
    return render_template(
        "admin/content/pages.html",
        system_pages=load_managed_pages(),
        custom_pages=custom_pages,
        action_form=EmptyForm(),
    )


@admin_bp.route("/pages/new/", methods=["GET", "POST"])
@admin_bp.route("/pages/<int:item_id>/edit/", methods=["GET", "POST"])
@permission_required("pages.manage")
def edit_page(item_id: int | None = None):
    page = db.get_or_404(CustomPage, item_id) if item_id else CustomPage(title="", slug="")
    form = CustomPageForm(obj=page)
    if form.validate_on_submit():
        apply_page_form(page, form)
        db.session.add(page)
        db.session.flush()
        record_audit("page.save", "page", str(page.id), page.title)
        db.session.commit()
        flash("独立页面已经保存。", "success")
        return redirect(url_for("admin.edit_page", item_id=page.id))
    editor_content_html, _, _ = render_markdown(form.content_markdown.data or "")
    return render_template(
        "admin/content/page_editor.html",
        form=form,
        page=page if item_id else None,
        editor_content_html=editor_content_html,
        editor_media=db.session.scalars(
            db.select(Media).order_by(Media.created_at.desc()).limit(30)
        ).all(),
    )


@admin_bp.post("/api/pages/<int:item_id>/autosave/")
@permission_required("pages.manage")
def autosave_page(item_id: int):
    page = db.get_or_404(CustomPage, item_id)
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "")).strip()[:180]
    content = str(payload.get("content_markdown", ""))
    if not title or not content or len(content) > 2_000_000:
        return jsonify(
            {
                "ok": False,
                "error": {"code": "invalid_page", "message": "标题和正文不能为空。"},
            }
        ), 400
    page.title = title
    page.summary = str(payload.get("summary", "")).strip()[:300]
    page.content_markdown = content
    page.content_html, _, _ = render_markdown(content)
    db.session.commit()
    return jsonify(
        {
            "ok": True,
            "data": {"saved_at": datetime.now(UTC).isoformat(), "page_id": page.id},
        }
    )


@admin_bp.post("/pages/<int:item_id>/delete/")
@permission_required("pages.manage")
def delete_page(item_id: int):
    _action_form()
    db.session.delete(db.get_or_404(CustomPage, item_id))
    db.session.commit()
    return redirect(url_for("admin.pages"))


def _media_choices(field) -> None:  # type: ignore[no-untyped-def]
    media = db.session.scalars(db.select(Media).order_by(Media.created_at.desc())).all()
    field.choices = [(0, "无封面"), *((item.id, item.original_filename) for item in media)]


def _publish_permission(status: str, permission: str) -> None:
    if status == "published" and not current_user.has_permission(permission):
        abort(403)


def _action_form() -> None:
    if not EmptyForm().validate_on_submit():
        abort(400)
