"""Cloudgate login, callback, account and logout routes."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import (
    Response,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from app.blueprints.gateway import gateway_bp
from app.extensions import db
from app.models import LoginLog, User
from app.security import record_audit, request_fingerprint
from app.services.auth import current_user_session, establish_user_session
from app.services.gateway import (
    GATEWAY_SESSION_KEY,
    GatewayError,
    begin_authorization,
    complete_authorization,
    establish_gateway_session,
    gateway_intent_is_allowed,
    gateway_is_enabled,
    gateway_picture_url_is_safe,
    gateway_portal_url,
    safe_local_target,
    terminate_gateway_session,
)
from app.services.local_recovery import (
    claim_local_recovery_token,
    request_is_loopback,
)


@gateway_bp.get("/recovery/local/<token>/")
def local_recovery(token: str):
    if not request_is_loopback() or not claim_local_recovery_token(token):
        abort(404)
    user = next(
        (
            item
            for item in db.session.scalars(db.select(User)).all()
            if item.can_login and item.has_permission("admin.access")
        ),
        None,
    )
    if user is None:
        abort(409)
    session.clear()
    session.permanent = True
    login_user(user, remember=False, fresh=True)
    establish_user_session(user)
    user.last_login_at = datetime.now(UTC)
    db.session.add(
        LoginLog(
            user_id=user.id,
            username="local-recovery",
            success=True,
            ip_address=request_fingerprint("login"),
            user_agent=request.user_agent.string[:255],
        )
    )
    record_audit(
        "admin.local_recovery",
        "user",
        str(user.id),
        "本机一次性恢复入口建立临时管理员会话",
    )
    db.session.commit()
    flash("本机恢复会话已经建立，请及时检查管理员账号安全。", "info")
    return redirect(url_for("admin.dashboard"))


@gateway_bp.get("/login/")
def login():
    intent = request.args.get("intent", "frontend")
    if intent not in {"frontend", "admin", "link_admin"}:
        abort(400)
    if not gateway_intent_is_allowed(intent):
        abort(404)
    next_target = safe_local_target(request.args.get("next"), "/")
    if intent == "link_admin" and not current_user.is_authenticated:
        abort(403)
    if intent == "link_admin" and not current_user.has_permission("admin.access"):
        abort(403)
    if intent == "admin" and current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if intent == "frontend" and g.get("gateway_session") is not None:
        return redirect(url_for("gateway.account"))
    return render_template(
        "gateway/waiting.html",
        continue_url=url_for(
            "gateway.login_continue",
            intent=intent,
            next=next_target,
        ),
    )


@gateway_bp.get("/login/continue/")
def login_continue():
    intent = request.args.get("intent", "frontend")
    if intent not in {"frontend", "admin", "link_admin"}:
        abort(400)
    if not gateway_intent_is_allowed(intent):
        abort(404)
    next_target = safe_local_target(request.args.get("next"), "/")
    if intent == "link_admin" and (
        not current_user.is_authenticated
        or not current_user.has_permission("admin.access")
    ):
        abort(403)
    try:
        return redirect(begin_authorization(intent, next_target))
    except GatewayError as error:
        flash(str(error), "error")
        return redirect(
            url_for("admin.gateway_settings")
            if intent == "link_admin"
            else url_for("public.home")
        )


@gateway_bp.get("/callback/")
def callback():
    try:
        flow, tokens, userinfo = complete_authorization()
        if not gateway_intent_is_allowed(str(flow.get("intent", ""))):
            raise GatewayError("这个云门登录入口已经由管理员关闭。")
        gateway_session = establish_gateway_session(tokens, userinfo)
    except GatewayError as error:
        db.session.rollback()
        flash(str(error), "error")
        return redirect(url_for("public.home"))

    intent = str(flow["intent"])
    next_target = safe_local_target(str(flow.get("next") or ""), "/")
    if intent == "link_admin":
        if not current_user.is_authenticated or not current_user.has_permission("admin.access"):
            db.session.rollback()
            abort(403)
        conflict = db.session.scalar(
            db.select(User).where(
                User.gateway_subject == gateway_session.gateway_subject,
                User.id != current_user.id,
            )
        )
        if conflict is not None:
            db.session.rollback()
            flash("这个云门账号已经绑定到另一位管理员。", "error")
            return redirect(url_for("admin.gateway_settings"))
        current_user.gateway_subject = gateway_session.gateway_subject
        gateway_session.linked_user_id = current_user.id
        record_audit(
            "gateway.identity.link",
            "user",
            str(current_user.id),
            f"绑定云门账号 {gateway_session.preferred_username}",
        )
        db.session.commit()
        from app.services.cache import site_context_cache

        site_context_cache.clear()
        flash("云门账号已经与当前博客管理员安全绑定。", "success")
        return redirect(url_for("admin.gateway_settings"))

    if intent == "admin":
        user = db.session.scalar(
            db.select(User).where(User.gateway_subject == gateway_session.gateway_subject)
        )
        success = bool(user and user.can_login and user.has_permission("admin.access"))
        db.session.add(
            LoginLog(
                user_id=user.id if user else None,
                username=f"gateway:{gateway_session.preferred_username}"[:80],
                success=success,
                ip_address=request_fingerprint("login"),
                user_agent=request.user_agent.string[:255],
            )
        )
        if not success or user is None:
            db.session.commit()
            flash("这个云门账号尚未绑定博客管理员，不能进入后台。", "error")
            return redirect(url_for("public.home"))
        raw_gateway_session = session.get(GATEWAY_SESSION_KEY)
        session.clear()
        if raw_gateway_session:
            session[GATEWAY_SESSION_KEY] = raw_gateway_session
        session.permanent = True
        login_user(user, remember=False)
        establish_user_session(user)
        gateway_session.linked_user_id = user.id
        user.last_login_at = datetime.now(UTC)
        db.session.commit()
        flash("云门身份验证完成，欢迎回到博客后台。", "success")
        return redirect(
            next_target if next_target.startswith("/admin/") else url_for("admin.dashboard")
        )

    linked_admin = db.session.scalar(
        db.select(User).where(User.gateway_subject == gateway_session.gateway_subject)
    )
    if (
        linked_admin is not None
        and linked_admin.can_login
        and linked_admin.has_permission("admin.access")
    ):
        raw_gateway_session = session.get(GATEWAY_SESSION_KEY)
        session.clear()
        if raw_gateway_session:
            session[GATEWAY_SESSION_KEY] = raw_gateway_session
        session.permanent = True
        login_user(linked_admin, remember=False)
        establish_user_session(linked_admin)
        gateway_session.linked_user_id = linked_admin.id
        linked_admin.last_login_at = datetime.now(UTC)
        db.session.add(
            LoginLog(
                user_id=linked_admin.id,
                username=f"gateway:{gateway_session.preferred_username}"[:80],
                success=True,
                ip_address=request_fingerprint("login"),
                user_agent=request.user_agent.string[:255],
            )
        )
    db.session.commit()
    flash(f"云门身份验证完成，欢迎回来，{gateway_session.display_name}。", "success")
    return redirect(next_target)


@gateway_bp.get("/account/")
def account():
    identity = g.get("gateway_session")
    if identity is None:
        return redirect(url_for("gateway.login", next=request.path))
    return redirect(gateway_portal_url())


@gateway_bp.get("/portal/")
def portal():
    if not gateway_is_enabled():
        abort(404)
    return redirect(gateway_portal_url())


@gateway_bp.get("/avatar/")
def avatar():
    identity = g.get("gateway_session")
    if (
        identity is None
        or not identity.avatar_url
        or not gateway_picture_url_is_safe(identity.avatar_url)
    ):
        abort(404)
    outbound = Request(
        identity.avatar_url,
        headers={
            "Accept": "image/png,image/jpeg,image/webp",
            "User-Agent": "Cloudtrace-Avatar-Proxy",
        },
    )
    try:
        with urlopen(outbound, timeout=4) as upstream:  # noqa: S310
            content_type = upstream.headers.get_content_type()
            if content_type not in {"image/png", "image/jpeg", "image/webp"}:
                abort(404)
            payload = upstream.read(2 * 1024 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        abort(404)
    if len(payload) > 2 * 1024 * 1024:
        abort(404)
    response = Response(payload, content_type=content_type)
    response.cache_control.private = True
    response.cache_control.max_age = 300
    return response


@gateway_bp.post("/logout/")
def logout():
    identity = g.get("gateway_session")
    terminate_gateway_session(identity)
    local_session = current_user_session() if current_user.is_authenticated else None
    if local_session is not None:
        local_session.revoked_at = datetime.now(UTC)
        db.session.commit()
    logout_user()
    session.clear()
    flash("已经退出博客与本次云门授权。", "info")
    return redirect(url_for("public.home"))


@gateway_bp.get("/status/")
def status():
    identity = g.get("gateway_session")
    enabled = gateway_is_enabled()
    response = jsonify(
        {
            "ok": True,
            "enabled": enabled,
            "capabilities": {
                "frontend_login": enabled,
                "registration": False,
                "admin_login": enabled,
            },
            "authenticated": identity is not None,
            "identity": (
                {
                    "sub": identity.gateway_subject,
                    "preferred_username": identity.preferred_username,
                    "name": identity.display_name,
                    "email": identity.email,
                    "email_verified": identity.email_verified,
                    "picture": identity.avatar_url,
                    "linked_admin": identity.linked_user_id is not None,
                }
                if identity is not None
                else None
            ),
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response
