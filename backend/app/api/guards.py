"""@admin_required: a valid session cookie, and for state-changing methods the CSRF token plus a same-origin check."""
from __future__ import annotations

from functools import wraps

from flask import Response, g, request

from app.config import cfg
from app.db import UNSAFE_METHODS, db, session_scope
from app.errors import ApiError
from app.security import safe_equal, same_origin
from app.services import auth


def set_session_cookie(response: Response, token: str) -> None:
    c = cfg()
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=c.session_days * 86400, path="/api/admin", httponly=True, samesite="Lax",
        secure=c.cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.set_cookie(auth.SESSION_COOKIE, "", max_age=0, path="/api/admin", httponly=True, samesite="Lax", secure=cfg().cookie_secure)


def check_same_origin() -> None:
    if not same_origin(request):
        raise ApiError(403, "cross_site", "请求来源不对。")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        found = auth.authenticate(db(), request.cookies.get(auth.SESSION_COOKIE))
        if found is None:
            raise ApiError(401, "unauthorized", "需要先登录。")
        if request.method in UNSAFE_METHODS:
            check_same_origin()
            sent = request.headers.get("X-CSRF-Token", "")
            if not sent or not safe_equal(sent, found.session.csrf_token):
                raise ApiError(403, "csrf", "页面已过期，请刷新后再试。")
        if auth.needs_touch(found.session):
            if request.method in UNSAFE_METHODS:
                auth.touch(db(), found.session.id)  # same transaction, already writing
            else:
                with session_scope() as s:  # a reading request must not hold the write lock: a short transaction of its own
                    auth.touch(s, found.session.id)
        g.admin = found.user
        g.admin_session = found.session
        return fn(*args, **kwargs)

    return wrapper
