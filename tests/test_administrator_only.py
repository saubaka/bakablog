from __future__ import annotations

from app.extensions import db
from app.models import Role, User
from app.services.cache import setup_state_cache


def test_member_routes_are_absent_and_admin_has_one_canonical_entry(client):
    removed_paths = (
        "/login/",
        "/register/",
        "/account/",
        "/account/security/",
        "/account/notifications/",
        "/admin/users/",
        "/admin/roles/",
        "/admin/registration/",
        "/admin/site/human-verification/",
        "/admin/menu/permissions/",
        "/auth/login/",
        "/auth/register/",
        "/auth/account/",
        "/admin/login/",
    )
    for path in removed_paths:
        assert client.get(path).status_code == 404
    assert client.get("/bakaadmin").status_code == 200


def test_public_navigation_has_no_account_or_admin_entrance(client):
    body = client.get("/").get_data(as_text=True)
    for retired_label in ("登录", "注册", "创建账号", "个人中心", "退出个人中心", "管理后台"):
        assert retired_label not in body


def test_only_administrator_role_is_seeded(app, admin_user):
    with app.app_context():
        role_codes = set(db.session.scalars(db.select(Role.code)))
        assert role_codes == {"superadmin"}
        users = list(db.session.scalars(db.select(User)))
        assert users
        assert all(user.is_superadmin and user.has_permission("admin.access") for user in users)


def test_uninitialised_project_redirects_visitors_to_superadmin_guidance(app, client):
    app.config["SETUP_REDIRECT_ENABLED"] = True
    with app.app_context():
        setup_state_cache.clear()

    for path in ("/", "/blog/", "/links/"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302, path
        assert "/bakaadmin" in response.headers["Location"]

    guidance = client.get("/bakaadmin")
    assert guidance.status_code == 200
    body = guidance.get_data(as_text=True)
    assert 'name="display_name"' in body
    assert "创建管理员并进入后台" in body
    assert "尚未初始化" in body
    assert client.get("/healthz").status_code == 200


def test_initialised_project_stops_redirecting_visitors(app, client, admin_user):
    app.config["SETUP_REDIRECT_ENABLED"] = True
    with app.app_context():
        setup_state_cache.clear()

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200


def test_setup_guidance_completes_without_redirect_loop(app, client):
    app.config["SETUP_REDIRECT_ENABLED"] = True
    with app.app_context():
        setup_state_cache.clear()

    assert client.get("/", follow_redirects=False).status_code == 302

    created = client.post(
        "/bakaadmin",
        data={
            "username": "owner",
            "display_name": "站点主人",
            "password": "Setup-Guidance-2026",
            "password_confirm": "Setup-Guidance-2026",
            "human_answer": "BAKA",
        },
        follow_redirects=False,
    )
    assert created.status_code == 302
    assert created.headers["Location"] == "/admin/"
    assert client.get("/admin/").status_code == 200

    with app.app_context():
        from app.services.admin_bootstrap import setup_required

        assert setup_required() is False
    assert client.get("/", follow_redirects=False).status_code == 200
