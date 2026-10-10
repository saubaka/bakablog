from __future__ import annotations

from pathlib import Path

import pytest

from app.extensions import db
from app.models import ExternalLinkRule
from app.services.external_links import (
    ExternalLinkError,
    linkify_external_html,
    normalize_destination,
    normalize_hostname,
)


def test_external_link_normalization_rejects_unsafe_destinations():
    assert normalize_hostname("https://例子.测试/path") == "xn--fsqu00a.xn--0zwm56d"
    assert normalize_destination("www.example.com/a") == "https://www.example.com/a"
    with pytest.raises(ExternalLinkError):
        normalize_destination("javascript:alert(1)")
    with pytest.raises(ExternalLinkError):
        normalize_destination("https://user:secret@example.com/")


def test_plain_and_existing_external_urls_use_local_gateway(app):
    with app.test_request_context("/article", base_url="http://localhost"):
        rendered = str(
            linkify_external_html(
                "正文 https://outside.example/path，"
                '<a href="https://linked.example/read">已有链接</a>'
            )
        )
    assert rendered.count("/out/?url=") == 2
    assert "external-text-link" in rendered
    assert "outside.example/path" in rendered and "outside.example/path%EF" not in rendered
    assert "target=" not in rendered
    assert "nofollow noopener noreferrer" in rendered


def test_unknown_safe_and_dangerous_notice_pages(app, client, logged_in_client):
    unknown = client.get("/out/", query_string={"url": "https://unknown.example/path"})
    assert unknown.status_code == 200
    assert "这个站点的安全性未知" in unknown.get_data(as_text=True)
    assert "no-store" in unknown.headers["Cache-Control"]
    assert unknown.headers["Referrer-Policy"] == "no-referrer"

    created = logged_in_client.post(
        "/admin/site/third-party-links/",
        data={
            "hostname": "safe.example",
            "classification": "safe",
            "display_name": "安全示例",
            "note": "这是管理员确认过的演示站点。",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert "第三方站点状态已经保存" in created.get_data(as_text=True)
    safe = client.get("/out/", query_string={"url": "https://safe.example/hello"})
    safe_body = safe.get_data(as_text=True)
    assert "这个站点已被标记为安全" in safe_body
    assert "安全示例" in safe_body

    with app.app_context():
        rule = db.session.scalar(
            db.select(ExternalLinkRule).where(ExternalLinkRule.hostname == "safe.example")
        )
        assert rule is not None
        rule_id = rule.id

    changed = logged_in_client.post(
        "/admin/site/third-party-links/",
        data={
            "rule_id": rule_id,
            "hostname": "danger.example",
            "classification": "dangerous",
            "display_name": "风险示例",
            "note": "请不要输入敏感信息。",
        },
        follow_redirects=True,
    )
    assert changed.status_code == 200
    dangerous = client.get("/out/", query_string={"url": "http://danger.example/suspicious"})
    assert "这个站点可能存在危险" in dangerous.get_data(as_text=True)

    removed = logged_in_client.post(
        f"/admin/site/third-party-links/{rule_id}/delete/", follow_redirects=True
    )
    assert removed.status_code == 200
    restored = client.get("/out/", query_string={"url": "https://danger.example/"})
    assert "这个站点的安全性未知" in restored.get_data(as_text=True)


def test_external_link_ui_contracts_cover_animation_and_overflow():
    root = Path(__file__).resolve().parents[1]
    script = (root / "app/static/scripts/external-links.js").read_text(encoding="utf-8")
    styles = (root / "app/static/styles/app.css").read_text(encoding="utf-8")
    admin = (root / "app/templates/layouts/admin.html").read_text(encoding="utf-8")
    assert "createTreeWalker" in script and "MutationObserver" in script
    assert "data-external-continue" in script and "is-leaving" in script
    assert "text-decoration: none" in styles
    assert ".external-jump__panel" in styles and "overflow-wrap: anywhere" in styles
    assert "@media (max-width: 680px)" in styles
    assert "site-external-links" in admin
