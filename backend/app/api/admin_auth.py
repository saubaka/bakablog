"""/api/admin/auth: first-run setup, login, logout, account, TOTP, sessions."""
from __future__ import annotations

import re
from typing import Any

from flask import Blueprint, g, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import defaults
from app.api.guards import admin_required, check_same_origin, clear_session_cookie, set_session_cookie
from app.api.helpers import body
from app.config import cfg
from app.db import db
from app.errors import ApiError
from app.models import AdminSession, AdminUser
from app.security import client_prefix
from app.services import auth, settings
from app.timeutil import iso

bp = Blueprint("admin_auth", __name__, url_prefix="/api/admin/auth")

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}$")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class SetupIn(_In):
    token: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if v and not _EMAIL.match(v):
            raise ValueError("邮箱格式不对")
        return v or None


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=32)


class PasswordIn(_In):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class UsernameIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class CodeIn(_In):
    code: str = Field(min_length=1, max_length=32)


class PasswordOnlyIn(_In):
    password: str = Field(min_length=1, max_length=200)


def user_out(user: AdminUser) -> dict[str, Any]:
    return {
        "id": user.id, "username": user.username, "role": user.role, "totp_enabled": bool(user.totp_enabled),
        "created_at": iso(user.created_at), "last_login_at": iso(user.last_login_at),
    }


def session_out(row: AdminSession, current_id: int | None = None) -> dict[str, Any]:
    return {
        "id": row.id, "device": row.device, "ip_prefix": row.ip_prefix, "created_at": iso(row.created_at),
        "last_seen_at": iso(row.last_seen_at), "expires_at": iso(row.expires_at), "current": row.id == current_id,
    }


def _logged_in_response(result: auth.LoginResult, status: int = 200):
    response = jsonify({"user": user_out(result.user), "csrf_token": result.session.csrf_token, "session": session_out(result.session, result.session.id)})
    response.status_code = status
    set_session_cookie(response, result.token)
    return response


@bp.get("/status")
def status():
    session = db()
    found = auth.authenticate(session, request.cookies.get(auth.SESSION_COOKIE))
    return jsonify({"setup_required": not auth.owner_exists(session), "authenticated": found is not None})


@bp.post("/setup")
def setup():
    check_same_origin()
    session = db()
    if auth.owner_exists(session):
        raise ApiError(404)  # closed for good
    data = body(SetupIn)
    prefix = client_prefix()
    wait = auth.lockout_seconds(session, "__setup__", prefix, cfg())
    if wait:
        raise ApiError(429, "locked", "尝试次数太多，请稍后再试。", headers={"Retry-After": str(wait)}, extra={"retry_after": wait})
    if not auth.check_setup_token(session, data.token):
        auth._attempt(session, "__setup__", prefix, request.headers.get("User-Agent", ""), False, "bad_token")
        raise ApiError(403, "bad_setup_token", "安装口令不对。口令在服务器启动日志里，或运行 flask setup-token 重新生成。", fields={"token": "不对"})
    user = auth.create_owner(session, data.username, data.password, cfg())
    if data.email:
        author = settings.group(session, "author")
        links = [lk for lk in author.get("links", []) if lk.get("kind") != "mail"]
        links.insert(0, {"label": "发邮件", "kind": "mail", "url": f"mailto:{data.email}"})
        settings.set_group(session, "author", {**author, "links": links})
    result = auth.login_after_setup(session, user, request.headers.get("User-Agent", ""), prefix, cfg())
    settings.bump_site_version(session)
    return _logged_in_response(result, 201)


@bp.post("/login")
def login():
    check_same_origin()
    data = body(LoginIn)
    result = auth.login(db(), data.username, data.password, data.code, request.headers.get("User-Agent", ""), client_prefix(), cfg())
    return _logged_in_response(result)


@bp.post("/logout")
@admin_required
def logout():
    auth.logout(db(), g.admin_session)
    response = jsonify({"ok": True})
    clear_session_cookie(response)
    return response


@bp.get("/me")
@admin_required
def me():
    return jsonify({"user": user_out(g.admin), "csrf_token": g.admin_session.csrf_token, "session": session_out(g.admin_session, g.admin_session.id)})


@bp.patch("/me")
@admin_required
def change_username():
    data = body(UsernameIn)
    auth.change_username(db(), g.admin, data.username, data.password)
    return jsonify({"user": user_out(g.admin)})


@bp.post("/password")
@admin_required
def change_password():
    data = body(PasswordIn)
    auth.change_password(db(), g.admin, data.current_password, data.new_password, g.admin_session.id, cfg())
    return jsonify({"ok": True})


@bp.post("/totp/begin")
@admin_required
def totp_begin():
    site = settings.group(db(), "site")
    return jsonify(auth.totp_begin(db(), g.admin, site.get("name_en") or defaults.SITE_NAME_EN))


@bp.post("/totp/enable")
@admin_required
def totp_enable():
    codes = auth.totp_enable(db(), g.admin, body(CodeIn).code)
    return jsonify({"user": user_out(g.admin), "recovery_codes": codes})


@bp.post("/totp/disable")
@admin_required
def totp_disable():
    auth.totp_disable(db(), g.admin, body(PasswordOnlyIn).password)
    return jsonify({"user": user_out(g.admin)})


@bp.get("/sessions")
@admin_required
def sessions():
    rows = auth.list_sessions(db(), g.admin)
    return jsonify({"items": [session_out(r, g.admin_session.id) for r in rows]})


@bp.delete("/sessions/<int:session_id>")
@admin_required
def revoke(session_id: int):
    if not auth.revoke_session(db(), g.admin, session_id):
        raise ApiError(404)
    return jsonify({"ok": True, "self": session_id == g.admin_session.id})


@bp.post("/sessions/revoke-others")
@admin_required
def revoke_others():
    return jsonify({"revoked": auth.revoke_others(db(), g.admin, g.admin_session.id)})


@bp.get("/logins")
@admin_required
def logins():
    rows = auth.login_history(db(), g.admin)
    return jsonify({"items": [
        {"at": iso(r.at), "success": r.success, "reason": r.reason, "ip_prefix": r.ip_prefix, "user_agent": r.user_agent} for r in rows
    ]})

