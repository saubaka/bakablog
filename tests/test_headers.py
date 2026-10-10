from __future__ import annotations


def test_response_security_headers(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Response-Time"].endswith("ms")


def test_admin_is_not_indexed_or_cached(client):
    response = client.get("/admin/")
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Cache-Control"] == "no-store"


def test_request_id_is_preserved(client):
    response = client.get("/", headers={"X-Request-ID": "local-test-request"})
    assert response.headers["X-Request-ID"] == "local-test-request"


def test_invalid_request_id_is_not_reflected(client):
    response = client.get("/", headers={"X-Request-ID": "invalid request id with spaces"})
    assert response.headers["X-Request-ID"] != "invalid request id with spaces"
    assert len(response.headers["X-Request-ID"]) == 32
