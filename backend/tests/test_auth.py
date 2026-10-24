from __future__ import annotations

from datetime import timedelta

import pyotp
import pytest
from sqlalchemy import select

from app.db import session_scope
from app.models import AdminSession, LoginAttempt
from app.services import auth, settings
from app.timeutil import utcnow
from tests.conftest import OWNER, Api, make_config

BASE = "/api/admin/auth"


def _setup_token(app, token="setup-token-for-tests"):
    with session_scope(app) as s:
        return auth.issue_setup_token(s, token)


# ---- first-run setup --------------------------------------------------------------------------------------------------------
def test_status_before_and_after_setup(api, app):
    assert api.get(f"{BASE}/status").get_json() == {"setup_required": True, "authenticated": False}
    token = _setup_token(app)
    r = api.post(f"{BASE}/setup", {"token": token, "username": "baka_owner", "password": OWNER["password"]})
    assert r.status_code == 201
    assert api.get(f"{BASE}/status").get_json() == {"setup_required": False, "authenticated": True}


def test_setup_needs_the_token_and_closes_forever(api, app):
    token = _setup_token(app)
    bad = api.post(f"{BASE}/setup", {"token": "nope", "username": "owner1", "password": OWNER["password"]})
    assert bad.status_code == 403 and bad.get_json()["error"]["code"] == "bad_setup_token"
    ok = api.post(f"{BASE}/setup", {"token": token, "username": "owner1", "password": OWNER["password"], "email": "me@example.com"})
    assert ok.status_code == 201
    body = ok.get_json()
    assert body["user"]["username"] == "owner1" and body["user"]["role"] == "owner" and body["csrf_token"]
    # the one-time token is gone and the page is closed (even with the right token)
    again = api.post(f"{BASE}/setup", {"token": token, "username": "owner2", "password": OWNER["password"]})
    assert again.status_code == 404
    with session_scope(app) as s:
        assert settings.get_raw(s, auth.SETUP_KEY) is None
        author = settings.group(s, "author")
    assert {"label": "发邮件", "kind": "mail", "url": "mailto:me@example.com"} in author["links"]


def test_setup_token_attempts_are_rate_limited(api, app):
    _setup_token(app)
    codes = [api.post(f"{BASE}/setup", {"token": f"guess{i}", "username": "owner1", "password": OWNER["password"]}).status_code for i in range(7)]
    assert codes[:5] == [403] * 5 and codes[5] == 429


def test_ensure_setup_token_generates_once(app, cfg):
    with session_scope(app) as s:
        first = auth.ensure_setup_token(s, cfg)
    assert first and len(first) >= 20
    with session_scope(app) as s:
        assert auth.ensure_setup_token(s, cfg) is None  # already issued, not printed again
        assert auth.check_setup_token(s, first)
        assert not auth.check_setup_token(s, "something else")


def test_preset_setup_token_from_config(app, tmp_path):
    cfg2 = make_config(tmp_path, setup_token="preset-token-123")
    with session_scope(app) as s:
        assert auth.ensure_setup_token(s, cfg2) is None
        assert auth.check_setup_token(s, "preset-token-123")


@pytest.mark.parametrize("password,field_hint", [
    ("short", "10"), ("a" * 5 + "baka_owner" + "xyz", "用户名"), ("aaaaaaaaaaaa", "容易"), ("password", "10"),
])
def test_password_rules(api, app, password, field_hint):
    token = _setup_token(app)
    r = api.post(f"{BASE}/setup", {"token": token, "username": "baka_owner", "password": password})
    assert r.status_code == 422
    assert field_hint in r.get_json()["error"]["fields"]["password"]


@pytest.mark.parametrize("username", ["ab", "has space", "名字", "a" * 40, "semi;colon"])
def test_username_rules(api, app, username):
    token = _setup_token(app)
    r = api.post(f"{BASE}/setup", {"token": token, "username": username, "password": OWNER["password"]})
    assert r.status_code == 422 and "username" in r.get_json()["error"]["fields"]


# ---- login ------------------------------------------------------------------------------------------------------------------
def test_login_success_sets_a_hardened_cookie(app, owner):
    c = app.test_client()
    r = c.post(f"{BASE}/login", json={"username": owner["username"].upper(), "password": owner["password"]})  # user names are case-insensitive
    assert r.status_code == 200
    cookie = next(v for k, v in r.headers if k == "Set-Cookie")
    assert cookie.startswith("bb_session=") and "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Path=/api/admin" in cookie
    assert "Secure" not in cookie  # testing config: plain http
    data = r.get_json()
    assert data["csrf_token"] and data["user"]["username"] == owner["username"]
    # only the hash of the token is stored
    token = cookie.split("=", 1)[1].split(";", 1)[0]
    with session_scope(app) as s:
        rows = list(s.scalars(select(AdminSession)))
        assert len(rows) == 1 and rows[0].token_hash != token and len(rows[0].token_hash) == 64


def test_secure_cookie_in_production_like_config(app, owner, tmp_path):
    app.extensions["bb_config"] = app.extensions["bb_config"].with_overrides(cookie_secure=True)
    r = app.test_client().post(f"{BASE}/login", json=owner)
    cookie = next(v for k, v in r.headers if k == "Set-Cookie")
    assert "Secure" in cookie
    assert "Strict-Transport-Security" in r.headers


def test_login_errors_do_not_reveal_which_part_was_wrong(api, owner):
    wrong_pw = api.post(f"{BASE}/login", {"username": owner["username"], "password": "x" * 12})
    unknown = api.post(f"{BASE}/login", {"username": "nobody_here", "password": "x" * 12})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json() == unknown.get_json()


def test_login_requires_json(app, owner):
    r = app.test_client().post(f"{BASE}/login", data={"username": owner["username"], "password": owner["password"]})
    assert r.status_code == 400


def test_login_rejects_cross_site_requests(app, owner):
    c = app.test_client()
    r = c.post(f"{BASE}/login", json=owner, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "cross_site"
    r = c.post(f"{BASE}/login", json=owner, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = c.post(f"{BASE}/login", json=owner, headers={"Origin": "http://localhost", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_lockout_after_repeated_failures_and_reset_by_success(app, owner):
    c = app.test_client()
    bad = {"username": owner["username"], "password": "wrong password"}
    for _ in range(4):
        assert c.post(f"{BASE}/login", json=bad).status_code == 401
    # a success clears the counter ...
    assert c.post(f"{BASE}/login", json=owner).status_code == 200
    for _ in range(4):
        assert c.post(f"{BASE}/login", json=bad).status_code == 401
    # ... five failures in a row lock the account, even for the right password
    assert c.post(f"{BASE}/login", json=bad).status_code == 401
    locked = c.post(f"{BASE}/login", json=owner)
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0 and locked.get_json()["error"]["code"] == "locked"
    # the failures were committed although the requests failed
    with session_scope(app) as s:
        assert len(list(s.scalars(select(LoginAttempt).where(LoginAttempt.success.is_(False))))) >= 9


def test_lockout_expires(app, owner):
    c = app.test_client()
    for _ in range(5):
        c.post(f"{BASE}/login", json={"username": owner["username"], "password": "wrong password"})
    assert c.post(f"{BASE}/login", json=owner).status_code == 429
    with session_scope(app) as s:
        for row in s.scalars(select(LoginAttempt)):
            row.at = utcnow() - timedelta(minutes=16)
    assert c.post(f"{BASE}/login", json=owner).status_code == 200


def test_ip_prefix_lockout_covers_guessing_many_user_names(app, owner):
    c = app.test_client()
    for i in range(20):
        c.post(f"{BASE}/login", json={"username": f"user{i}", "password": "wrong password"}, environ_overrides={"REMOTE_ADDR": "203.0.113.9"})
    r = c.post(f"{BASE}/login", json=owner, environ_overrides={"REMOTE_ADDR": "203.0.113.77"})  # same /24
    assert r.status_code == 429
    assert c.post(f"{BASE}/login", json=owner, environ_overrides={"REMOTE_ADDR": "198.51.100.5"}).status_code == 200
    with session_scope(app) as s:
        assert all(a.ip_prefix in ("203.0.113.0/24", "198.51.100.0/24") for a in s.scalars(select(LoginAttempt)))  # never a full address


# ---- sessions, CSRF, logout ----------------------------------------------------------------------------------------------------
def test_admin_routes_need_a_session(api):
    assert api.get(f"{BASE}/me").status_code == 401
    assert api.get(f"{BASE}/sessions").status_code == 401
    assert api.post(f"{BASE}/logout", {}).status_code == 401


def test_csrf_is_required_for_changes_but_not_for_reads(app, admin):
    assert admin.get(f"{BASE}/me").status_code == 200
    csrf = admin.csrf
    admin.csrf = None
    r = admin.post(f"{BASE}/sessions/revoke-others", {})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "csrf"
    admin.csrf = "wrong-token"
    assert admin.post(f"{BASE}/sessions/revoke-others", {}).status_code == 403
    admin.csrf = csrf
    assert admin.post(f"{BASE}/sessions/revoke-others", {}).status_code == 200


def test_cross_site_post_with_a_valid_token_is_still_refused(admin):
    r = admin.post(f"{BASE}/sessions/revoke-others", {}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "cross_site"


def test_logout_revokes_the_session(app, admin):
    assert admin.post(f"{BASE}/logout", {}).status_code == 200
    assert admin.get(f"{BASE}/me").status_code == 401
    with session_scope(app) as s:
        assert s.scalar(select(AdminSession)).revoked_at is not None


def test_expired_sessions_stop_working(app, admin):
    with session_scope(app) as s:
        s.scalar(select(AdminSession)).expires_at = utcnow() - timedelta(seconds=1)
    assert admin.get(f"{BASE}/me").status_code == 401


def test_sessions_list_and_revoke(app, owner, admin):
    other = Api(app.test_client())
    r = other.post(f"{BASE}/login", {**owner}, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1"})
    other.csrf = r.get_json()["csrf_token"]
    items = admin.get(f"{BASE}/sessions").get_json()["items"]
    assert len(items) == 2 and sum(i["current"] for i in items) == 1
    assert any("iPhone" in i["device"] for i in items)
    victim = next(i for i in items if not i["current"])
    assert admin.delete(f"{BASE}/sessions/{victim['id']}").status_code == 200
    assert other.get(f"{BASE}/me").status_code == 401
    assert admin.delete(f"{BASE}/sessions/999999").status_code == 404
    assert len(admin.get(f"{BASE}/sessions").get_json()["items"]) == 1


def test_password_change(app, owner, admin):
    other = Api(app.test_client())
    other.post(f"{BASE}/login", {**owner})
    wrong = admin.post(f"{BASE}/password", {"current_password": "not it at all", "new_password": "a brand new password"})
    assert wrong.status_code == 422
    weak = admin.post(f"{BASE}/password", {"current_password": owner["password"], "new_password": "short"})
    assert weak.status_code == 422
    ok = admin.post(f"{BASE}/password", {"current_password": owner["password"], "new_password": "a brand new password"})
    assert ok.status_code == 200
    assert other.get(f"{BASE}/me").status_code == 401  # the other session was signed out
    assert admin.get(f"{BASE}/me").status_code == 200  # this one stays
    fresh = app.test_client()
    assert fresh.post(f"{BASE}/login", json=owner).status_code == 401
    assert fresh.post(f"{BASE}/login", json={"username": owner["username"], "password": "a brand new password"}).status_code == 200


def test_username_change_needs_the_password(admin, owner):
    assert admin.patch(f"{BASE}/me", {"username": "renamed_owner", "password": "bad bad bad bad"}).status_code == 422
    r = admin.patch(f"{BASE}/me", {"username": "renamed_owner", "password": owner["password"]})
    assert r.status_code == 200 and r.get_json()["user"]["username"] == "renamed_owner"


def test_login_history(admin, owner):
    items = admin.get(f"{BASE}/logins").get_json()["items"]
    assert items and items[0]["success"] is True


# ---- two-factor ---------------------------------------------------------------------------------------------------------------
def test_totp_flow_with_replay_protection_and_recovery_codes(app, owner, admin):
    begin = admin.post(f"{BASE}/totp/begin", {}).get_json()
    secret = begin["secret"]
    assert begin["uri"].startswith("otpauth://totp/") and "Baka" in begin["uri"]
    totp = pyotp.TOTP(secret)
    assert admin.post(f"{BASE}/totp/enable", {"code": "000000"}).status_code == 422
    enabled = admin.post(f"{BASE}/totp/enable", {"code": totp.now()})
    assert enabled.status_code == 200
    codes = enabled.get_json()["recovery_codes"]
    assert len(codes) == 10 and enabled.get_json()["user"]["totp_enabled"] is True

    c = app.test_client()
    need = c.post(f"{BASE}/login", json=owner)
    assert need.status_code == 401 and need.get_json()["error"]["code"] == "totp_required"
    # the code that enabled it cannot be used again (replay) ...
    assert c.post(f"{BASE}/login", json={**owner, "code": totp.now()}).get_json()["error"]["code"] == "bad_code"
    # ... the next 30-second code works, once
    from datetime import datetime
    nxt = totp.at(datetime.now() + timedelta(seconds=30))
    assert c.post(f"{BASE}/login", json={**owner, "code": nxt}).status_code == 200
    assert c.post(f"{BASE}/login", json={**owner, "code": nxt}).status_code == 401
    # a recovery code works exactly once
    assert c.post(f"{BASE}/login", json={**owner, "code": codes[0]}).status_code == 200
    assert c.post(f"{BASE}/login", json={**owner, "code": codes[0]}).status_code == 401

    assert admin.post(f"{BASE}/totp/disable", {"password": "wrong wrong wrong"}).status_code == 422
    assert admin.post(f"{BASE}/totp/disable", {"password": owner["password"]}).status_code == 200
    assert app.test_client().post(f"{BASE}/login", json=owner).status_code == 200


def test_wrong_totp_counts_towards_lockout(app, owner, admin):
    totp = pyotp.TOTP(admin.post(f"{BASE}/totp/begin", {}).get_json()["secret"])
    admin.post(f"{BASE}/totp/enable", {"code": totp.now()})
    c = app.test_client()
    for _ in range(5):
        assert c.post(f"{BASE}/login", json={**owner, "code": "123456"}).status_code == 401
    assert c.post(f"{BASE}/login", json={**owner, "code": "123456"}).status_code == 429


def test_audit_trail_of_account_events(app, owner, admin):
    from app.models import AuditLog

    admin.post(f"{BASE}/password", {"current_password": owner["password"], "new_password": "a brand new password"})
    with session_scope(app) as s:
        actions = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert "auth.login" in actions and "auth.password_changed" in actions
