"""Protected administration routes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import (
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import case, literal, union_all
from werkzeug.security import check_password_hash, generate_password_hash

from app.blueprints.admin import admin_auth_bp, admin_bp
from app.extensions import db
from app.forms import AccessSettingsForm, EmptyForm, LoginForm, MediaUploadForm, SuperadminSetupForm
from app.models import (
    Album,
    AuditLog,
    Comment,
    FriendLink,
    GuestbookMessage,
    LoginLog,
    Media,
    Moment,
    Photo,
    Post,
    Project,
    User,
)
from app.release import SYSTEM_AUTHOR, SYSTEM_RELEASED_AT, SYSTEM_REPOSITORY
from app.security import (
    login_is_rate_limited,
    permission_required,
    record_audit,
    request_fingerprint,
)
from app.services.admin_bootstrap import (
    AdminBootstrapError,
    initialize_superadmin,
    setup_code_required,
    setup_required,
)
from app.services.auth import current_user_session, establish_user_session
from app.services.backup import database_path
from app.services.content import get_setting, set_setting
from app.services.human_check import issue_human_check, verify_human_check
from app.services.media import MediaValidationError, delete_stored_image, store_image
from app.services.system_metrics import collect_runtime_metrics, host_snapshot
from app.services.system_update import (
    UpdateError,
    check_for_updates,
    queue_privileged_action,
    read_update_state,
    start_download,
)

DUMMY_PASSWORD_HASH = generate_password_hash("not-the-password-being-checked")


@admin_bp.before_request
def protect_admin():
    if current_user.is_authenticated and current_user.has_permission("admin.access"):
        return None
    if current_user.is_authenticated:
        abort(403)
    next_target = request.full_path if request.query_string else request.path
    return redirect(url_for("bakaadmin.login", next=next_target))


@admin_auth_bp.route("/bakaadmin", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if setup_required():
        form = SuperadminSetupForm()
        code_required = setup_code_required()
        form_valid = form.validate_on_submit()
        challenge_ok = False
        if form_valid:
            challenge_ok = verify_human_check(
                "admin-setup", "superadmin", form.human_nonce.data or "", form.human_answer.data
            )
            if not challenge_ok:
                form.human_answer.errors.append("字符不匹配，请按新图片重新输入。")
        if form_valid and challenge_ok:
            try:
                user = initialize_superadmin(
                    form.username.data,
                    form.display_name.data,
                    form.password.data,
                    setup_code=form.setup_code.data or "",
                    require_code=code_required,
                )
            except (AdminBootstrapError, ValueError) as error:
                flash(str(error), "error")
            else:
                session.clear()
                login_user(user, remember=False)
                establish_user_session(user, source="local")
                db.session.commit()
                flash("管理员已创建，后台可以使用了。", "success")
                return redirect(url_for("admin.dashboard"))
        challenge = issue_human_check("admin-setup", "superadmin")
        form.human_nonce.data = challenge.nonce
        # The picture changes on every render, so the old answer is stale.
        form.human_answer.data = ""
        return render_template(
            "admin/setup.html",
            form=form,
            human_challenge=challenge,
            setup_code_required=code_required,
        )
    form = LoginForm()
    form_valid = form.validate_on_submit()
    challenge_ok = False
    if form_valid:
        challenge_ok = verify_human_check(
            "admin-login", "superadmin", form.human_nonce.data or "", form.human_answer.data
        )
        if not challenge_ok:
            form.human_answer.errors.append("字符不匹配，请按新图片重新输入。")
    if form_valid and challenge_ok:
        username = form.username.data.strip().lower()
        if login_is_rate_limited(username):
            current_app.logger.warning("login rate limit reached username=%s", username[:80])
            flash("登录尝试次数过多，请稍后再试。", "error")
            challenge = issue_human_check("admin-login", "superadmin")
            form.human_nonce.data = challenge.nonce
            return render_template("admin/login.html", form=form, human_challenge=challenge), 429
        user = db.session.scalar(db.select(User).where(User.username == username))
        password_ok = (
            user.check_password(form.password.data)
            if user
            else check_password_hash(DUMMY_PASSWORD_HASH, form.password.data)
        )
        success = bool(
            user
            and user.can_login
            and user.is_superadmin
            and password_ok
            and user.has_permission("admin.access")
        )
        db.session.add(
            LoginLog(
                user_id=user.id if user else None,
                username=username[:80],
                success=success,
                ip_address=request_fingerprint("login"),
                user_agent=request.user_agent.string[:255],
            )
        )
        if success and user:
            user.last_login_at = datetime.now(UTC)
            db.session.commit()
            session.clear()
            session.permanent = bool(form.remember.data)
            login_user(user, remember=False)
            establish_user_session(user, source="local")
            db.session.commit()
            flash("欢迎回来，后台已经准备好了。", "success")
            return redirect(_safe_next_url(request.args.get("next")) or url_for("admin.dashboard"))
        db.session.commit()
        flash("用户名或密码不正确。", "error")
    challenge = issue_human_check("admin-login", "superadmin")
    form.human_nonce.data = challenge.nonce
    return render_template("admin/login.html", form=form, human_challenge=challenge)


@admin_auth_bp.get("/bakaadmin/human-check")
def refresh_login_human_check():
    scope = "admin-setup" if setup_required() else "admin-login"
    challenge = issue_human_check(scope, "superadmin")
    return jsonify(
        {"ok": True, "nonce": challenge.nonce, "image": challenge.image_data},
    )


@admin_bp.route("/access/", methods=["GET", "POST"])
@permission_required("system.maintain")
def access_settings():
    from app.services.access import (
        get_access_policy,
        host_is_allowed,
        request_hostname,
        save_access_policy,
        serialize_allowed_hosts,
    )

    policy = get_access_policy()
    form = AccessSettingsForm()
    if request.method == "GET":
        form.allowed_hosts.data = "\n".join(policy.allowed_hosts)
        form.require_https.data = policy.require_https
    if form.validate_on_submit():
        normalized = serialize_allowed_hosts(form.allowed_hosts.data or "")
        rules = tuple(normalized.splitlines()) if normalized else ()
        current_host = request_hostname(request.host)
        if rules and not host_is_allowed(current_host, rules):
            form.allowed_hosts.errors.append(
                f"当前访问地址 {current_host} 不在新白名单中；请把它也加入，避免保存后掉线。"
            )
        if form.require_https.data and not request.is_secure and not form.confirm_https.data:
            form.confirm_https.errors.append("从 HTTP 开启时必须先确认 HTTPS 已经可以访问。")
        if not form.allowed_hosts.errors and not form.confirm_https.errors:
            save_access_policy(normalized, bool(form.require_https.data))
            record_audit(
                "system.access.update",
                "site",
                "access",
                f"HTTPS={'required' if form.require_https.data else 'optional'}，"
                f"Host={normalized or 'any'}",
            )
            db.session.commit()
            flash("域名与协议设置已经保存。", "success")
            target = url_for("admin.access_settings", _external=True)
            if form.require_https.data:
                target = target.replace("http://", "https://", 1)
            return redirect(target)
    return render_template(
        "admin/access_settings.html",
        form=form,
        policy=policy,
        current_host=request_hostname(request.host),
    )


@admin_bp.post("/logout/")
def logout():
    item = current_user_session()
    if item is not None:
        item.revoked_at = datetime.now(UTC)
        db.session.commit()
    logout_user()
    session.clear()
    flash("已经安全退出后台。", "info")
    return redirect(url_for("bakaadmin.login"))


@admin_bp.get("/")
@permission_required("dashboard.view")
def dashboard():
    return render_template("admin/dashboard.html", **_dashboard_context())


def _dashboard_context() -> dict[str, object]:
    counts = {
        "posts": db.session.scalar(
            db.select(db.func.count()).select_from(Post).where(Post.deleted_at.is_(None))
        )
        or 0,
        "published": db.session.scalar(
            db.select(db.func.count())
            .select_from(Post)
            .where(Post.status == "published", Post.deleted_at.is_(None))
        )
        or 0,
        "drafts": db.session.scalar(
            db.select(db.func.count())
            .select_from(Post)
            .where(Post.status == "draft", Post.deleted_at.is_(None))
        )
        or 0,
        "projects": db.session.scalar(
            db.select(db.func.count()).select_from(Project).where(Project.deleted_at.is_(None))
        )
        or 0,
        "moments": db.session.scalar(
            db.select(db.func.count()).select_from(Moment).where(Moment.deleted_at.is_(None))
        )
        or 0,
        "media": db.session.scalar(db.select(db.func.count()).select_from(Media)) or 0,
        "audit": db.session.scalar(db.select(db.func.count()).select_from(AuditLog)) or 0,
        "failed_logins": db.session.scalar(
            db.select(db.func.count()).select_from(LoginLog).where(LoginLog.success.is_(False))
        )
        or 0,
        "friends_pending": db.session.scalar(
            db.select(db.func.count()).select_from(FriendLink).where(FriendLink.status == "pending")
        )
        or 0,
        "albums": db.session.scalar(db.select(db.func.count()).select_from(Album)) or 0,
        "moderation_pending": (
            db.session.scalar(
                db.select(db.func.count()).select_from(Comment).where(Comment.status == "pending")
            )
            or 0
        )
        + (
            db.session.scalar(
                db.select(db.func.count())
                .select_from(GuestbookMessage)
                .where(GuestbookMessage.status == "pending")
            )
            or 0
        ),
    }
    recent_logs = db.session.scalars(
        db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(5)
    ).all()
    counts["pending_total"] = counts["moderation_pending"] + counts["friends_pending"]
    counts["publish_percent"] = (
        round(counts["published"] / counts["posts"] * 100) if counts["posts"] else 0
    )
    return {"counts": counts, "recent_logs": recent_logs}


@admin_bp.route("/media/", methods=["GET", "POST"])
@permission_required("media.view")
def media_library():
    form = MediaUploadForm()
    if form.validate_on_submit():
        if not current_user.has_permission("media.manage"):
            return render_template("errors/403.html"), 403
        try:
            stored = store_image(form.image.data)
        except MediaValidationError as error:
            form.image.errors.append(str(error))
        else:
            media = Media(
                filename=stored.filename,
                thumbnail_filename=stored.thumbnail_filename,
                original_filename=Path(form.image.data.filename).name[:255],
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                width=stored.width,
                height=stored.height,
                alt_text=(form.alt_text.data or "").strip(),
                created_by_id=current_user.id,
            )
            try:
                db.session.add(media)
                db.session.flush()
                record_audit("media.upload", "media", str(media.id), media.original_filename)
                db.session.commit()
            except Exception:
                db.session.rollback()
                delete_stored_image(stored.filename, stored.thumbnail_filename)
                raise
            flash("图片已安全处理并保存到本地媒体库。", "success")
            return redirect(url_for("admin.media_library"))
    page = db.paginate(
        db.select(Media).order_by(Media.created_at.desc()),
        page=request.args.get("page", 1, type=int),
        per_page=current_app.config["ADMIN_MEDIA_PER_PAGE"],
        error_out=False,
    )
    delete_form = EmptyForm()
    return render_template(
        "admin/media.html",
        form=form,
        delete_form=delete_form,
        media_items=page.items,
        page=page,
    )


@admin_bp.post("/media/<int:media_id>/delete/")
@permission_required("media.manage")
def delete_media(media_id: int):
    form = EmptyForm()
    if not form.validate_on_submit():
        return render_template("errors/400.html", message="删除请求无效，请刷新后重试。"), 400
    media = db.get_or_404(Media, media_id)
    if get_setting("site_logo_media_id", "") == str(media.id):
        flash("这张图片仍是网站Logo，请先在站点标识中移除或更换。", "warning")
        return redirect(url_for("admin.media_library"))
    if db.session.scalar(db.select(Photo.id).where(Photo.media_id == media.id).limit(1)):
        flash("这张图片仍在相册中，请先从相册移除。", "warning")
        return redirect(url_for("admin.media_library"))
    if db.session.scalar(db.select(Post.id).where(Post.cover_media_id == media.id).limit(1)):
        flash("这张图片仍是文章封面，请先取消封面引用。", "warning")
        return redirect(url_for("admin.media_library"))
    filename = media.filename
    thumbnail_filename = media.thumbnail_filename
    record_audit("media.delete", "media", str(media.id), media.original_filename)
    db.session.delete(media)
    db.session.commit()
    try:
        delete_stored_image(filename, thumbnail_filename)
    except OSError:
        flash("数据库记录已删除，但文件正被占用；请稍后清理实例上传目录。", "warning")
    else:
        flash("媒体文件及缩略图已删除。", "success")
    return redirect(url_for("admin.media_library"))


@admin_bp.get("/audit-logs/")
@permission_required("audit.view")
def audit_logs():
    selected_user = request.args.get("user", "all")
    selected_function = request.args.get("function", "all")
    date_from = _parse_log_date(request.args.get("date_from"))
    date_to = _parse_log_date(request.args.get("date_to"))
    per_page = max(20, min(200, request.args.get("per_page", 50, type=int)))
    page_number = max(1, request.args.get("page", 1, type=int))

    audit_query = db.select(
        literal("audit").label("kind"),
        AuditLog.id.label("item_id"),
        AuditLog.created_at.label("created_at"),
        AuditLog.action.label("action"),
        AuditLog.actor_id.label("user_id"),
        db.func.coalesce(
            db.select(User.display_name).where(User.id == AuditLog.actor_id).scalar_subquery(),
            "系统",
        ).label("user_name"),
        (AuditLog.target_type + literal(" #") + AuditLog.target_id).label("target"),
        AuditLog.summary.label("summary"),
        (
            literal("请求 ") + AuditLog.request_id + literal(" · 地址指纹 ") + AuditLog.ip_address
        ).label("details"),
    )
    login_query = db.select(
        literal("login").label("kind"),
        LoginLog.id.label("item_id"),
        LoginLog.created_at.label("created_at"),
        case((LoginLog.success.is_(True), "login.success"), else_="login.failure").label("action"),
        LoginLog.user_id.label("user_id"),
        db.func.coalesce(User.display_name, LoginLog.username).label("user_name"),
        literal("登录会话").label("target"),
        LoginLog.username.label("summary"),
        (literal("地址指纹 ") + LoginLog.ip_address + literal(" · ") + LoginLog.user_agent).label(
            "details"
        ),
    ).outerjoin(User, User.id == LoginLog.user_id)

    if selected_user == "system":
        audit_query = audit_query.where(AuditLog.actor_id.is_(None))
        login_query = login_query.where(LoginLog.user_id.is_(None))
    elif selected_user.isdigit():
        user_id = int(selected_user)
        audit_query = audit_query.where(AuditLog.actor_id == user_id)
        login_query = login_query.where(LoginLog.user_id == user_id)
    if date_from:
        start_at = datetime.combine(date_from, time.min, tzinfo=UTC)
        audit_query = audit_query.where(AuditLog.created_at >= start_at)
        login_query = login_query.where(LoginLog.created_at >= start_at)
    if date_to:
        end_at = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        audit_query = audit_query.where(AuditLog.created_at < end_at)
        login_query = login_query.where(LoginLog.created_at < end_at)

    if selected_function == "login":
        combined = login_query.subquery()
    elif selected_function != "all":
        combined = audit_query.where(AuditLog.action.like(f"{selected_function}.%")).subquery()
    else:
        combined = union_all(audit_query, login_query).subquery()
    total = db.session.scalar(db.select(db.func.count()).select_from(combined)) or 0
    rows = db.session.execute(
        db.select(combined)
        .order_by(combined.c.created_at.desc(), combined.c.item_id.desc())
        .limit(per_page)
        .offset((page_number - 1) * per_page)
    ).all()
    pages = max(1, (total + per_page - 1) // per_page)
    log_page = SimpleNamespace(
        items=rows,
        total=total,
        page=page_number,
        pages=pages,
        has_prev=page_number > 1,
        has_next=page_number < pages,
        prev_num=page_number - 1,
        next_num=page_number + 1,
    )
    action_prefixes = sorted(
        {
            action.split(".", 1)[0]
            for action in db.session.scalars(db.select(AuditLog.action).distinct()).all()
            if action
        }
    )
    users = db.session.scalars(db.select(User).order_by(User.display_name, User.username)).all()
    retention = {
        "mode": get_setting("audit_retention_mode", "all"),
        "count": _bounded_setting_int("audit_retention_count", 5000, 100, 100000),
        "days": _bounded_setting_int("audit_retention_days", 365, 1, 3650),
    }
    storage = _log_storage_summary()
    return render_template(
        "admin/audit_logs.html",
        log_page=log_page,
        users=users,
        action_prefixes=action_prefixes,
        selected_user=selected_user,
        selected_function=selected_function,
        selected_from=request.args.get("date_from", ""),
        selected_to=request.args.get("date_to", ""),
        per_page=per_page,
        retention=retention,
        storage=storage,
        action_form=EmptyForm(),
    )


@admin_bp.post("/audit-logs/retention/")
@permission_required("audit.view")
def update_audit_retention():
    if not EmptyForm().validate_on_submit():
        abort(400)
    mode = request.form.get("retention_mode", "all")
    if mode not in {"all", "count", "days"}:
        abort(400)
    count = max(100, min(100000, request.form.get("retention_count", 5000, type=int)))
    days = max(1, min(3650, request.form.get("retention_days", 365, type=int)))
    set_setting("audit_retention_mode", mode)
    set_setting("audit_retention_count", str(count))
    set_setting("audit_retention_days", str(days))
    deleted = _apply_log_retention(mode, count, days)
    db.session.commit()
    flash(f"日志保留策略已保存，本次清理 {deleted} 条记录。", "success")
    return redirect(url_for("admin.audit_logs"))


@admin_bp.post("/audit-logs/delete/")
@permission_required("audit.view")
def delete_audit_logs():
    if not EmptyForm().validate_on_submit():
        abort(400)
    audit_count = db.session.execute(db.delete(AuditLog)).rowcount or 0
    login_count = db.session.execute(db.delete(LoginLog)).rowcount or 0
    db.session.commit()
    flash(f"已删除 {audit_count + login_count} 条操作与登录日志。", "success")
    return redirect(url_for("admin.audit_logs"))


@admin_bp.get("/system/")
@permission_required("system.maintain")
def system_status():
    instance_root = Path(current_app.instance_path)
    db_path = database_path()
    upload_files = [path for path in (instance_root / "uploads").rglob("*") if path.is_file()]
    backups = sorted(
        (path for path in (instance_root / "backups").glob("*.zip") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    revision = (
        db.session.execute(
            db.text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalar_one_or_none()
        if db.session.execute(
            db.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        ).scalar_one_or_none()
        else None
    )
    host = host_snapshot(current_app.config["ENV_NAME"])
    status = {
        "app_version": current_app.config["APP_VERSION"],
        "environment": current_app.config["ENV_NAME"],
        "python": host["python"],
        "host": host,
        "sqlite": sqlite3.sqlite_version,
        "migration": revision or "未记录",
        "database_size": _format_bytes(db_path.stat().st_size if db_path.exists() else 0),
        "wal_size": _format_bytes(
            Path(f"{db_path}-wal").stat().st_size if Path(f"{db_path}-wal").exists() else 0
        ),
        "media_count": len(upload_files),
        "media_size": _format_bytes(sum(path.stat().st_size for path in upload_files)),
        "latest_backup": backups[0].name if backups else "尚无备份",
        "latest_backup_size": _format_bytes(backups[0].stat().st_size) if backups else "0 B",
        "log_size": _format_bytes(
            (instance_root / "logs" / "cloud-diary.log").stat().st_size
            if (instance_root / "logs" / "cloud-diary.log").exists()
            else 0
        ),
    }
    return render_template(
        "admin/system.html",
        status=status,
        metrics=collect_runtime_metrics(current_app.instance_path),
    )


@admin_bp.get("/system/runtime-metrics/")
@permission_required("system.maintain")
def runtime_metrics():
    response = jsonify(
        {
            "ok": True,
            "data": collect_runtime_metrics(current_app.instance_path),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@admin_bp.get("/system/about/")
@permission_required("system.maintain")
def system_about():
    state = read_update_state(current_app.instance_path, current_app.config["APP_VERSION"])
    return render_template(
        "admin/system_about.html",
        host=host_snapshot(current_app.config["ENV_NAME"]),
        release={
            "author": SYSTEM_AUTHOR,
            "repository": SYSTEM_REPOSITORY,
            "released_at": SYSTEM_RELEASED_AT,
        },
        update_state=state,
    )


@admin_bp.get("/system/update/status/")
@permission_required("system.maintain")
def system_update_status():
    response = jsonify(
        {
            "ok": True,
            "data": read_update_state(current_app.instance_path, current_app.config["APP_VERSION"]),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@admin_bp.post("/system/update/check/")
@permission_required("system.maintain")
def system_update_check():
    if not EmptyForm().validate_on_submit():
        abort(400)
    state = check_for_updates(current_app.instance_path, current_app.config["APP_VERSION"])
    record_audit("system.update.check", "system", "update", state["message"])
    db.session.commit()
    return jsonify({"ok": state["status"] != "error", "data": state})


@admin_bp.post("/system/update/download/")
@permission_required("system.maintain")
def system_update_download():
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        state = start_download(current_app.instance_path, current_app.config["APP_VERSION"])
    except UpdateError as error:
        return jsonify({"ok": False, "message": str(error)}), 409
    record_audit("system.update.download", "system", "update", "开始下载并校验更新包")
    db.session.commit()
    return jsonify({"ok": True, "data": state}), 202


@admin_bp.post("/system/update/install/")
@permission_required("system.maintain")
def system_update_install():
    return _queue_system_update_action("install")


@admin_bp.post("/system/update/rollback/")
@permission_required("system.maintain")
def system_update_rollback():
    return _queue_system_update_action("rollback")


def _queue_system_update_action(action: str):
    if not EmptyForm().validate_on_submit():
        abort(400)
    try:
        state = queue_privileged_action(
            current_app.instance_path, current_app.config["APP_VERSION"], action
        )
    except UpdateError as error:
        return jsonify({"ok": False, "message": str(error)}), 409
    record_audit(
        f"system.update.{action}",
        "system",
        "update",
        "提交安装请求" if action == "install" else "提交完整回退请求",
    )
    db.session.commit()
    return jsonify({"ok": True, "data": state}), 202


@admin_bp.get("/api/status/")
@permission_required("dashboard.view")
def api_status():
    return jsonify(
        {
            "ok": True,
            "data": {
                "service": "cloudtrace-admin",
                "database": "sqlite",
                "version": current_app.config["APP_VERSION"],
                "user": current_user.username,
            },
        }
    )


def _safe_next_url(value: str | None) -> str | None:
    if not value:
        return None
    target = urlsplit(value)
    if target.scheme or target.netloc or not target.path.startswith("/"):
        return None
    return target.path + (f"?{target.query}" if target.query else "")


def _format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if amount < 1024 or unit == "GiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def _parse_log_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _bounded_setting_int(key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(get_setting(key, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _apply_log_retention(mode: str, count: int, days: int) -> int:
    if mode == "all":
        return 0
    deleted = 0
    if mode == "days":
        cutoff = datetime.now(UTC) - timedelta(days=days)
        deleted += (
            db.session.execute(db.delete(AuditLog).where(AuditLog.created_at < cutoff)).rowcount
            or 0
        )
        deleted += (
            db.session.execute(db.delete(LoginLog).where(LoginLog.created_at < cutoff)).rowcount
            or 0
        )
        return deleted
    audit_keep = db.select(AuditLog.id).order_by(AuditLog.created_at.desc()).limit(count)
    login_keep = db.select(LoginLog.id).order_by(LoginLog.created_at.desc()).limit(count)
    deleted += (
        db.session.execute(db.delete(AuditLog).where(AuditLog.id.not_in(audit_keep))).rowcount or 0
    )
    deleted += (
        db.session.execute(db.delete(LoginLog).where(LoginLog.id.not_in(login_keep))).rowcount or 0
    )
    return deleted


def _log_storage_summary() -> dict[str, object]:
    audit_count = db.session.scalar(db.select(db.func.count()).select_from(AuditLog)) or 0
    login_count = db.session.scalar(db.select(db.func.count()).select_from(LoginLog)) or 0
    audit_bytes = (
        db.session.scalar(
            db.select(
                db.func.coalesce(
                    db.func.sum(
                        db.func.coalesce(db.func.length(AuditLog.action), 0)
                        + db.func.coalesce(db.func.length(AuditLog.target_type), 0)
                        + db.func.coalesce(db.func.length(AuditLog.target_id), 0)
                        + db.func.coalesce(db.func.length(AuditLog.summary), 0)
                        + db.func.coalesce(db.func.length(AuditLog.request_id), 0)
                        + db.func.coalesce(db.func.length(AuditLog.ip_address), 0)
                        + 72
                    ),
                    0,
                )
            )
        )
        or 0
    )
    login_bytes = (
        db.session.scalar(
            db.select(
                db.func.coalesce(
                    db.func.sum(
                        db.func.coalesce(db.func.length(LoginLog.username), 0)
                        + db.func.coalesce(db.func.length(LoginLog.ip_address), 0)
                        + db.func.coalesce(db.func.length(LoginLog.user_agent), 0)
                        + 56
                    ),
                    0,
                )
            )
        )
        or 0
    )
    return {
        "audit_count": audit_count,
        "login_count": login_count,
        "total_count": audit_count + login_count,
        "estimated_bytes": audit_bytes + login_bytes,
        "estimated_size": _format_bytes(audit_bytes + login_bytes),
    }
