from __future__ import annotations

import pytest

from app import create_app
from app.cli import create_or_update_admin
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing", instance_path=str(tmp_path / "instance"))
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_user(app):
    with app.app_context():
        user = create_or_update_admin("admin", "very-secure-password", "测试管理员")
        user_id = user.id
    return user_id


@pytest.fixture()
def logged_in_client(client, admin_user):
    response = client.post(
        "/bakaadmin",
        data={"username": "admin", "password": "very-secure-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return client
