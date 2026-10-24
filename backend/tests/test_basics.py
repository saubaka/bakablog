from sqlalchemy import text

from app import migrate
from app.db import database
from app.migrate import head_revision
from app.models import Base


def test_health_and_version_headers(api):
    r = api.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True and data["version"] and data["build"]
    assert r.headers["Cache-Control"] == "no-store"
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert h["X-Frame-Options"] == "DENY"


def test_json_errors_have_one_shape(api):
    r = api.get("/api/nope")
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"
    r = api.post("/api/health", {})
    assert r.status_code == 405
    assert r.get_json()["error"]["code"] == "method_not_allowed"


def test_schema_matches_the_migration(app):
    """No drift: the models and `alembic upgrade head` describe the same database."""
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.migrate import include_object

    with app.app_context(), database().engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "include_object": include_object})
        diff = compare_metadata(ctx, Base.metadata)
        assert diff == [], diff
        assert migrate.current_revision(database()) == head_revision()


def test_database_pragmas(app):
    with app.app_context(), database().engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() >= 5000
        assert conn.execute(text("select count(*) from search_fts")).scalar() == 0


def test_no_comment_like_tables(app):
    """The site has no visitor input: no tables for comments, guestbooks, likes or visitor accounts."""
    forbidden = ("comment", "guestbook", "message", "like", "reaction", "visitor_account", "subscriber")
    for name in Base.metadata.tables:
        assert not any(word in name for word in forbidden), name
