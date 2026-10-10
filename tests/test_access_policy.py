from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.services.access import get_access_policy, save_access_policy
from app.services.cache import site_context_cache


def test_host_allowlist_and_https_are_enforced(app, client):
    with app.app_context():
        save_access_policy("diary.example\n*.friends.example", True)
        db.session.commit()

    rejected = client.get("/", base_url="http://evil.example")
    assert rejected.status_code == 400

    redirected = client.get("/blog/?page=2", base_url="http://diary.example")
    assert redirected.status_code == 308
    assert redirected.headers["Location"] == "https://diary.example/blog/?page=2"

    secure = client.get("/", base_url="https://notes.friends.example")
    assert secure.status_code == 200
    assert "upgrade-insecure-requests" in secure.headers["Content-Security-Policy"]
    assert secure.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_configure_deployment_domain_cli_binds_exact_https_origin(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["configure-deployment-domain", "Blog.Example.COM."])
    assert result.exit_code == 0

    with app.app_context():
        from app.services.access import get_access_policy

        policy = get_access_policy()
        assert policy.allowed_hosts == ("blog.example.com",)
        assert policy.bound_urls == ("https://blog.example.com",)
        assert policy.require_https is True

    rejected = runner.invoke(args=["configure-deployment-domain", "127.0.0.1"])
    assert rejected.exit_code != 0


def test_admin_access_settings_guard_against_current_host_lockout(logged_in_client):
    response = logged_in_client.post(
        "/admin/access/",
        data={"allowed_hosts": "other.example"},
    )
    assert response.status_code == 200
    assert "当前访问地址 localhost 不在新白名单中" in response.get_data(as_text=True)

    response = logged_in_client.post(
        "/admin/access/",
        data={"allowed_hosts": "localhost\nother.example"},
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_access_policy_database_failure_restricts_to_configured_origin(
    app,
    client,
    monkeypatch,
):
    def fail_to_load(_defaults):  # type: ignore[no-untyped-def]
        raise SQLAlchemyError("simulated settings failure")

    monkeypatch.setattr("app.services.access.get_settings", fail_to_load)
    with app.app_context():
        site_context_cache.clear()
        policy = get_access_policy()
        assert policy.allowed_hosts == ("127.0.0.1",)
        assert policy.bound_urls == ("http://127.0.0.1:5000",)

    allowed = client.get("/", base_url="http://127.0.0.1:5000")
    rejected = client.get("/", base_url="http://evil.example")
    assert allowed.status_code == 200
    assert rejected.status_code == 400
