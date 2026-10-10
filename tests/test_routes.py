from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", "sau_baka，正在做 Cloudtrace"),
        ("/blog/", "博客手记"),
        ("/about/", "你好，我是sau_baka"),
        ("/projects/", "项目作品"),
        ("/moments/", "生活动态"),
        ("/links/", "友链星球地图"),
        ("/components/", "预览"),
        ("/empty/", "这里还没有内容"),
        ("/privacy/", "隐私条款"),
        ("/terms/", "服务政策"),
    ],
)
def test_html_routes(client, path, expected):
    response = client.get(path)
    assert response.status_code == 200
    assert expected.encode() in response.data


def test_healthcheck(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {
        "service": "cloudtrace",
        "stage": 9,
        "status": "ok",
        "version": "1.48.0",
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_readiness_and_robots(client):
    readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.get_json()["status"] == "ready"
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /admin/" in robots.get_data(as_text=True)
    assert "Sitemap: http://127.0.0.1:5000/sitemap.xml" in robots.get_data(as_text=True)


def test_admin_requires_login(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/bakaadmin" in response.headers["Location"]


def test_not_found_uses_custom_page(client):
    response = client.get("/not-a-real-page")
    assert response.status_code == 404
    assert "这片云暂时飘走了".encode() in response.data


def test_unknown_article_is_not_found(client):
    response = client.get("/blog/missing/")
    assert response.status_code == 404
