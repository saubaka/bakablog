from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.extensions import db
from app.models import AuditLog, LoginLog, SiteSetting, User


def test_admin_api_uses_uniform_response(logged_in_client):
    response = logged_in_client.get("/admin/api/status/")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["database"] == "sqlite"
    assert payload["data"]["version"] == "1.49.0"


def test_system_status_is_available_to_administrator(logged_in_client):
    response = logged_in_client.get("/admin/system/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "系统状态" in body
    assert "1.49.0" in body
    assert "实时资源占用" in body
    assert "data-runtime-metrics" in body

    metrics_response = logged_in_client.get("/admin/system/runtime-metrics/")
    assert metrics_response.status_code == 200
    assert metrics_response.headers["Cache-Control"] == "no-store"
    payload = metrics_response.get_json()
    assert payload["ok"] is True
    assert set(payload["data"]["resources"]) == {"cpu", "memory", "disk", "network"}
    for resource in payload["data"]["resources"].values():
        assert 0 <= resource["percent"] <= 100
        assert resource["current"]
        assert resource["total"]


def test_system_about_confirms_cloudtrace_identity(logged_in_client):
    response = logged_in_client.get("/admin/system/about/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "关于" in body
    assert "sau_bakaの博客" in body
    assert "baka blog" in body
    assert "sau_baka" in body
    assert "宿主机系统" in body
    assert "https://github.com/saubaka/bakablog" in body
    assert "版本发布时间" in body
    assert "安全更新" in body
    assert "应用框架" not in body
    assert "Local SQLite" not in body
    assert "中英文名称草案" not in body
    for old_name in ("云屿手记", "星糖日记", "月屿手账", "Cloud Isle Notes"):
        assert old_name not in body


def test_admin_shell_uses_current_brand_identity(logged_in_client):
    response = logged_in_client.get("/admin/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-admin-brand-name' in body
    assert "sau_bakaの博客" in body
    assert "baka blog" in body
    legacy_name = "小" + "屿"
    assert legacy_name not in body
    assert legacy_name + "日记" not in body


def test_audit_log_filters_retention_storage_and_delete(app, logged_in_client, admin_user):
    with app.app_context():
        db.session.add(
            AuditLog(
                actor_id=admin_user,
                action="profile.update",
                target_type="user",
                target_id=str(admin_user),
                summary="更新个人资料",
                request_id="audit-test",
                ip_address="test-fingerprint",
                created_at=datetime.now(UTC) - timedelta(days=90),
            )
        )
        db.session.commit()

    page = logged_in_client.get(
        f"/admin/audit-logs/?user={admin_user}&function=profile"
        "&date_from=2020-01-01&date_to=2099-12-31"
    )
    body = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "更新个人资料" in body
    assert "估算占用" in body
    assert "完整信息" in body

    retained = logged_in_client.post(
        "/admin/audit-logs/retention/",
        data={
            "retention_mode": "days",
            "retention_count": "5000",
            "retention_days": "30",
        },
        follow_redirects=True,
    )
    assert "日志保留策略已保存" in retained.get_data(as_text=True)
    with app.app_context():
        assert (
            db.session.scalar(db.select(AuditLog).where(AuditLog.request_id == "audit-test"))
            is None
        )
        settings = {
            item.setting_key: item.setting_value
            for item in db.session.scalars(
                db.select(SiteSetting).where(
                    SiteSetting.setting_key.in_(
                        {
                            "audit_retention_mode",
                            "audit_retention_count",
                            "audit_retention_days",
                        }
                    )
                )
            )
        }
        assert settings["audit_retention_mode"] == "days"

    deleted = logged_in_client.post("/admin/audit-logs/delete/", follow_redirects=True)
    assert "已删除" in deleted.get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(AuditLog)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(LoginLog)) == 0


def test_non_administrator_cannot_sign_in(app, client):
    with app.app_context():
        user = User(username="viewer", display_name="访客管理员")
        user.set_password("viewer-password-123")
        db.session.add(user)
        db.session.commit()
    client.post(
        "/bakaadmin",
        data={"username": "viewer", "password": "viewer-password-123"},
    )
    response = client.get("/admin/", headers={"Accept": "application/json"})
    assert response.status_code == 302
    assert "/bakaadmin" in response.headers["Location"]
