from __future__ import annotations

import re

from app import create_app
from app.cli import create_or_update_admin
from app.extensions import db
from app.models import LoginLog, SiteSetting, User, UserSession
from app.services.admin_bootstrap import reset_superadmin_credentials


def test_login_and_logout(client, admin_user):
    response = client.post(
        "/bakaadmin?next=/admin/posts/",
        data={"username": "admin", "password": "very-secure-password"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/posts/")

    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200
    assert "测试管理员" in dashboard.get_data(as_text=True)

    response = client.post("/admin/logout/", follow_redirects=True)
    assert response.status_code == 200
    assert "登录后台 · sau_bakaの博客" in response.get_data(as_text=True)


def test_empty_site_can_create_the_only_superadmin(app, client):
    page = client.get("/bakaadmin")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "创建唯一管理员" in body
    response = client.post(
        "/bakaadmin",
        data={
            "username": "owner",
            "display_name": "站点主人",
            "password": "an-independent-password-2026",
            "password_confirm": "an-independent-password-2026",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "管理员已创建" in response.get_data(as_text=True)
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == "owner"))
        assert user is not None and user.can_login


def test_reset_preserves_owner_row_and_invalidates_old_credentials(app, client, admin_user):
    with app.app_context():
        archive, _code = reset_superadmin_credentials()
        assert archive.is_file()
        slot = db.session.get(User, admin_user)
        assert slot is not None
        assert slot.is_active is False
        assert slot.is_superadmin is False
        assert slot.username.startswith("bootstrap-pending-")
        assert db.session.scalar(db.select(db.func.count(UserSession.id))) == 0
        assert db.session.scalar(db.select(db.func.count(LoginLog.id))) == 0
        state = db.session.scalar(
            db.select(SiteSetting.setting_value).where(
                SiteSetting.setting_key == "admin_bootstrap_state"
            )
        )
        assert state == "setup-required"
    old_login = client.post(
        "/bakaadmin",
        data={"username": "admin", "password": "very-secure-password"},
    )
    assert old_login.status_code == 200
    assert "创建唯一管理员" in old_login.get_data(as_text=True)
    assert "管理员初始化步骤" in old_login.get_data(as_text=True)
    assert "之前的管理员凭证已经不能用了" in old_login.get_data(as_text=True)


def test_admin_login_requires_themed_human_check(client, admin_user):
    page = client.get("/bakaadmin")
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "data-human-check" in body
    assert 'name="human_nonce"' in body
    rejected = client.post(
        "/bakaadmin",
        data={
            "username": "admin",
            "password": "very-secure-password",
            "human_answer": "FAIL",
        },
    )
    assert rejected.status_code == 200
    assert "字符不匹配" in rejected.get_data(as_text=True)


def test_legacy_and_public_account_routes_do_not_exist(client):
    for path in ("/admin/login/", "/auth/login/", "/auth/register/", "/auth/account/"):
        assert client.get(path).status_code == 404


def test_failed_login_is_recorded(app, client, admin_user):
    response = client.post(
        "/bakaadmin",
        data={"username": "missing", "password": "incorrect-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "用户名或密码不正确" in response.get_data(as_text=True)
    with app.app_context():
        log = db.session.scalar(db.select(LoginLog).where(LoginLog.username == "missing"))
        assert log is not None
        assert log.success is False


def test_external_next_url_is_rejected(client, admin_user):
    response = client.post(
        "/bakaadmin?next=https://example.invalid/steal",
        data={"username": "admin", "password": "very-secure-password"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")


def test_inactive_user_cannot_login(app, client, admin_user):
    with app.app_context():
        user = db.session.get(User, admin_user)
        user.is_active = False
        db.session.commit()
    response = client.post(
        "/bakaadmin",
        data={"username": "admin", "password": "very-secure-password"},
    )
    assert response.status_code == 200


def test_login_rate_limit_uses_hashed_identity(app, client, admin_user):
    for _ in range(5):
        response = client.post(
            "/bakaadmin", data={"username": "admin", "password": "incorrect-password"}
        )
        assert response.status_code == 200

    blocked = client.post(
        "/bakaadmin", data={"username": "admin", "password": "very-secure-password"}
    )
    assert blocked.status_code == 429
    assert "尝试次数过多" in blocked.get_data(as_text=True)
    with app.app_context():
        logs = db.session.scalars(
            db.select(LoginLog).where(LoginLog.username == "admin").order_by(LoginLog.id)
        ).all()
        assert len(logs) == 5
        assert all(log.ip_address != "127.0.0.1" for log in logs)
        assert all(len(log.ip_address) == 64 for log in logs)


def test_login_failures_cannot_lock_same_username_for_another_requester(
    client,
    admin_user,
):
    for _ in range(5):
        response = client.post(
            "/bakaadmin",
            data={"username": "admin", "password": "incorrect-password"},
            environ_overrides={"REMOTE_ADDR": "198.51.100.10"},
        )
        assert response.status_code == 200

    allowed = client.post(
        "/bakaadmin",
        data={"username": "admin", "password": "very-secure-password"},
        environ_overrides={"REMOTE_ADDR": "198.51.100.11"},
    )
    assert allowed.status_code == 302


def test_admin_password_reset_revokes_local_sessions(app, client, admin_user):
    response = client.post(
        "/bakaadmin",
        data={"username": "admin", "password": "very-secure-password"},
    )
    assert response.status_code == 302
    with app.app_context():
        create_or_update_admin("admin", "new-very-secure-password", "测试管理员")

        local_sessions = db.session.scalars(
            db.select(UserSession).where(UserSession.user_id == admin_user)
        ).all()
        assert local_sessions and all(item.revoked_at is not None for item in local_sessions)

    assert client.get("/admin/", follow_redirects=False).status_code == 302


def test_login_clears_preexisting_session_state(client, admin_user):
    with client.session_transaction() as session:
        session["attacker-controlled"] = "remove-me"
    response = client.post(
        "/bakaadmin", data={"username": "admin", "password": "very-secure-password"}
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "attacker-controlled" not in session
        assert session.get("_user_id") == str(admin_user)


def test_login_with_real_csrf_validation(tmp_path):
    csrf_app = create_app(
        "testing",
        test_config={"WTF_CSRF_ENABLED": True},
        instance_path=str(tmp_path / "csrf-instance"),
    )
    with csrf_app.app_context():
        db.create_all()
        create_or_update_admin("admin", "very-secure-password", "CSRF管理员")
    client = csrf_app.test_client()
    login_page = client.get("/bakaadmin")
    token_match = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"',
        login_page.get_data(as_text=True),
    )
    assert token_match is not None

    response = client.post(
        "/bakaadmin?next=/admin/",
        data={
            "csrf_token": token_match.group(1),
            "username": "admin",
            "password": "very-secure-password",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")


def test_setup_page_is_the_simple_three_step_form(client):
    body = client.get("/bakaadmin").get_data(as_text=True)
    # One h1, three plainly named groups, and the same required form fields as before.
    assert body.count("<h1") == 1 and "创建唯一管理员" in body
    assert 'aria-label="管理员初始化步骤"' in body
    for group in ("account", "password", "verify"):
        assert f'data-setup-group="{group}"' in body
    for name in ("username", "display_name", "password", "password_confirm", "human_answer"):
        assert f'name="{name}"' in body
    assert "styles/setup.css" in body and "scripts/setup.js" in body
    # No English eyebrow, no retired guide block, no leftover login chrome.
    assert "ADMIN</span>" not in body and "setup-guide" not in body
    assert 'name="remember"' not in body
    assert '<meta name="cloudtrace-navigation" content="native">' in body


def test_setup_page_validation_errors_stay_next_to_their_fields(client):
    response = client.post(
        "/bakaadmin",
        data={
            "username": "owner",
            "display_name": "站点主人",
            "password": "an-independent-password-2026",
            "password_confirm": "something-else-entirely-2026",
            "human_answer": "ZZZZ",
        },
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "两次输入的密码不一致。" in body
    assert 'class="setup-field has-error"' in body
    # The typed username is kept; passwords are never echoed back.
    assert 'value="owner"' in body
    assert "an-independent-password-2026" not in body
    assert 'value="ZZZZ"' not in body


def test_setup_page_only_asks_for_the_code_when_required(client, monkeypatch):
    assert "初始化口令" not in client.get("/bakaadmin").get_data(as_text=True)
    monkeypatch.setattr("app.blueprints.admin.routes.setup_code_required", lambda: True)
    body = client.get("/bakaadmin").get_data(as_text=True)
    assert "一次性初始化口令" in body and "issue-admin-setup-code" in body
