from __future__ import annotations

import pytest

from app import create_app


def test_factory_uses_testing_config(app):
    assert app.config["TESTING"] is True
    assert app.config["ENV_NAME"] == "testing"


def test_production_rejects_default_secret(monkeypatch):
    monkeypatch.delenv("CLOUD_DIARY_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="unique 32-byte CLOUD_DIARY_SECRET_KEY"):
        create_app("production")


def test_production_accepts_unique_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUD_DIARY_SECRET_KEY", "a-unique-production-secret-for-testing")
    monkeypatch.setenv("CLOUD_DIARY_SITE_URL", "https://diary.example")
    app = create_app("production", instance_path=str(tmp_path / "production"))
    assert app.config["ENV_NAME"] == "production"
    assert app.config["SECRET_KEY"] == "a-unique-production-secret-for-testing"
    assert app.config["TRUSTED_HOSTS"] is None
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["PREFERRED_URL_SCHEME"] == "https"


def test_production_rejects_invalid_site_url(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUD_DIARY_SECRET_KEY", "a-unique-production-secret-for-testing")
    monkeypatch.setenv("CLOUD_DIARY_SITE_URL", "http://diary.example")
    with pytest.raises(RuntimeError, match="HTTPS"):
        create_app("production", instance_path=str(tmp_path / "production-invalid"))


def test_url_map_contains_public_and_admin(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/" in rules
    assert "/blog/" in rules
    assert "/components/" in rules
    assert "/admin/" in rules
    assert "/healthz" in rules
    assert "/readyz" in rules
    assert "/robots.txt" in rules
