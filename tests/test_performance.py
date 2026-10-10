from __future__ import annotations

import gzip
from pathlib import Path

from sqlalchemy import event

from app.extensions import db
from app.services.blog import render_markdown
from app.services.cache import home_content_cache, site_context_cache


def test_site_context_cache_removes_repeated_chrome_queries(app, client):
    with app.app_context():
        query_count = 0

        def count_query(*args):  # type: ignore[no-untyped-def]
            nonlocal query_count
            query_count += 1

        event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            site_context_cache.clear()
            client.get("/guestbook/")
            cold_queries = query_count
            query_count = 0
            client.get("/guestbook/")
            warm_queries = query_count
        finally:
            event.remove(db.engine, "before_cursor_execute", count_query)
    assert cold_queries - warm_queries == 5
    assert warm_queries == 1


def test_home_content_uses_short_ttl_cache(app, client):
    with app.app_context():
        query_count = 0

        def count_query(*args):  # type: ignore[no-untyped-def]
            nonlocal query_count
            query_count += 1

        event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            site_context_cache.clear()
            home_content_cache.clear()
            response = client.get("/")
            assert response.status_code == 200
            cold_queries = query_count
            query_count = 0
            response = client.get("/")
            assert response.status_code == 200
            warm_queries = query_count
        finally:
            event.remove(db.engine, "before_cursor_execute", count_query)
    assert cold_queries >= 10
    assert warm_queries <= 1


def test_text_gzip_and_immutable_static_cache(client):
    plain = client.get("/static/styles/app.css?v=0.8.0")
    compressed = client.get("/static/styles/app.css?v=0.8.0", headers={"Accept-Encoding": "gzip"})
    assert compressed.headers["Content-Encoding"] == "gzip"
    assert "immutable" in compressed.headers["Cache-Control"]
    assert gzip.decompress(compressed.data) == plain.data
    assert len(compressed.data) < len(plain.data) * 0.4


def test_media_delivery_is_query_free_cacheable_and_conditional(app, client):
    filename = "thumbnails/" + "a" * 32 + ".webp"
    path = Path(app.instance_path) / "uploads" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF-local-test-webp")
    with app.app_context():
        query_count = 0

        def count_query(*args):  # type: ignore[no-untyped-def]
            nonlocal query_count
            query_count += 1

        event.listen(db.engine, "before_cursor_execute", count_query)
        try:
            response = client.get(f"/media/{filename}")
        finally:
            event.remove(db.engine, "before_cursor_execute", count_query)
    assert response.status_code == 200
    assert query_count == 1
    assert response.cache_control.max_age == 31_536_000
    conditional = client.get(
        f"/media/{filename}", headers={"If-None-Match": response.headers["ETag"]}
    )
    assert conditional.status_code == 304
    assert client.get("/media/../data/site.db").status_code == 404


def test_feed_etag_supports_conditional_request(client):
    response = client.get("/feed.xml")
    assert response.status_code == 200
    assert response.headers["ETag"]
    assert response.cache_control.max_age == 300
    conditional = client.get("/feed.xml", headers={"If-None-Match": response.headers["ETag"]})
    assert conditional.status_code == 304


def test_markdown_images_are_local_lazy_and_async():
    local = "/media/originals/" + "b" * 32 + ".png"
    html, _, _ = render_markdown(f"![远程](https://example.com/a.png)\n\n![本地]({local})")
    assert "https://example.com/a.png" not in html
    assert local in html
    assert 'loading="lazy"' in html
    assert 'decoding="async"' in html


def test_database_optimize_command(app):
    result = app.test_cli_runner().invoke(args=["db-optimize"])
    assert result.exit_code == 0, result.output
    assert "mode=passive" in result.output
    assert "busy=0" in result.output

    truncate_result = app.test_cli_runner().invoke(args=["db-optimize", "--truncate"])
    assert truncate_result.exit_code == 0, truncate_result.output
    assert "mode=truncate" in truncate_result.output
    assert "busy=0" in truncate_result.output
