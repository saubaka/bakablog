from __future__ import annotations

import re
from pathlib import Path

from app import create_app
from app.cli import create_or_update_admin
from app.extensions import db
from app.models import UserSession


def production_app(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CLOUD_DIARY_SECRET_KEY", "production-test-secret-that-is-long-enough")
    monkeypatch.setenv("CLOUD_DIARY_SITE_URL", "https://diary.example")
    return create_app(
        "production",
        test_config={"HUMAN_CHECK_TEST_MODE": True, "HUMAN_CHECK_TEST_ANSWER": "BAKA"},
        instance_path=str(tmp_path / "production-instance"),
    )


def test_production_forces_https_and_secure_headers(monkeypatch, tmp_path):
    app = production_app(monkeypatch, tmp_path)
    with app.app_context():
        from app.extensions import db

        db.create_all()
        # An uninitialised production instance intentionally opens on the
        # superadmin guidance, so initialise it before checking site headers.
        create_or_update_admin("admin", "known-local-password", "本地管理员")
    client = app.test_client()
    response = client.get("/", base_url="http://diary.example")
    assert response.status_code == 308
    assert response.headers["Location"].startswith("https://diary.example/")
    secure = client.get("/", base_url="https://diary.example")
    assert secure.status_code == 200
    assert "Strict-Transport-Security" in secure.headers
    assert "upgrade-insecure-requests" in secure.headers["Content-Security-Policy"]
    form_page = client.get("/links/", base_url="https://diary.example")
    session_cookies = [
        value
        for value in form_page.headers.getlist("Set-Cookie")
        if value.startswith("cloudtrace_session=")
    ]
    assert session_cookies
    assert all("Secure" in value and "HttpOnly" in value for value in session_cookies)
    assert client.get("/", base_url="https://evil.example").status_code == 200


def test_production_admin_password_post_uses_local_login(monkeypatch, tmp_path):
    app = production_app(monkeypatch, tmp_path)
    with app.app_context():
        db.create_all()
        create_or_update_admin("admin", "known-local-password", "本地管理员")
    client = app.test_client()
    public_form = client.get("/bakaadmin", base_url="https://diary.example")
    token_match = re.search(
        r'name="csrf_token"[^>]*value="([^"]+)"',
        public_form.get_data(as_text=True),
    )
    assert token_match is not None

    response = client.post(
        "/bakaadmin?next=/admin/",
        data={
            "csrf_token": token_match.group(1),
            "username": "admin",
            "password": "known-local-password",
            "human_answer": "BAKA",
        },
        base_url="https://diary.example",
        headers={"Referer": "https://diary.example/links/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")
    with app.app_context():
        assert db.session.scalar(db.select(UserSession)) is not None


def test_production_log_file_contains_request_id(monkeypatch, tmp_path):
    app = production_app(monkeypatch, tmp_path)
    client = app.test_client()
    response = client.get(
        "/healthz",
        base_url="https://diary.example",
        headers={"X-Request-ID": "production-log-test"},
    )
    assert response.status_code == 200
    for handler in app.logger.handlers:
        handler.flush()
    log_path = Path(app.instance_path) / "logs" / "cloud-diary.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "request_id=production-log-test" in log_text
    assert "path=/healthz status=200" in log_text


def test_text_compression_can_be_delegated_to_proxy(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUD_DIARY_TEXT_COMPRESSION", "0")
    app = production_app(monkeypatch, tmp_path)
    response = app.test_client().get(
        "/static/styles/app.css",
        base_url="https://diary.example",
        headers={"Accept-Encoding": "gzip"},
    )
    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers
