from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from PIL import Image

from app import create_app, migrate
from app.config import Config, load_config
from app.db import Database, session_scope
from app.services import auth

OWNER = {"username": "baka_owner", "password": "correct horse battery"}


@pytest.fixture(autouse=True)
def _no_test_hangs():
    """A deadlock (two SQLite connections waiting for each other) must fail the test, not freeze the run."""
    import signal

    def boom(signum, frame):
        raise TimeoutError("test took longer than 60 seconds")

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(60)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    """The schema is built once by Alembic (so every test also exercises the migration); tests get a copy of the file."""
    folder = tmp_path_factory.mktemp("template")
    path = folder / "template.sqlite"
    database = Database(path)
    migrate.upgrade(database)
    with database.engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    database.dispose()
    return path


def make_config(tmp_path: Path, **overrides) -> Config:
    env = {"BLOG_ENV": "testing", "BLOG_DATA_DIR": str(tmp_path)}
    cfg = load_config({}, env).with_overrides(scrypt_n=2**10, frontend_dist=None)
    return cfg.with_overrides(**overrides) if overrides else cfg


@pytest.fixture
def cfg(tmp_path) -> Config:
    return make_config(tmp_path)


@pytest.fixture
def app(cfg, template_db):
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg.db_path)
    application = create_app(cfg)
    yield application
    application.extensions["bb_db"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session(app):
    """A write session for arranging data directly (committed on exit)."""
    with session_scope(app) as s:
        yield s


class Api:
    """A thin wrapper around the Flask test client: JSON in and out, and the CSRF header once logged in."""

    def __init__(self, client):
        self.client = client
        self.csrf: str | None = None

    def _call(self, method: str, url: str, **kw):
        headers = dict(kw.pop("headers", {}) or {})
        if self.csrf and method != "get":
            headers.setdefault("X-CSRF-Token", self.csrf)
        return getattr(self.client, method)(url, headers=headers, **kw)

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, json=None, **kw):
        return self._call("post", url, json=json, **kw) if "data" not in kw else self._call("post", url, **kw)

    def put(self, url, json=None, **kw):
        return self._call("put", url, json=json, **kw)

    def patch(self, url, json=None, **kw):
        return self._call("patch", url, json=json, **kw)

    def delete(self, url, **kw):
        return self._call("delete", url, **kw)

    def upload(self, url, data: bytes, filename="pic.png", mimetype="image/png", fields=None, **kw):
        form = {"file": (io.BytesIO(data), filename, mimetype)}
        form.update(fields or {})
        return self._call("post", url, data=form, content_type="multipart/form-data", **kw)


@pytest.fixture
def owner(app) -> dict:
    with session_scope(app) as s:
        auth.create_owner(s, OWNER["username"], OWNER["password"], app.extensions["bb_config"])
    return OWNER


@pytest.fixture
def api(client) -> Api:
    """Anonymous API client."""
    return Api(client)


@pytest.fixture
def admin(app, owner) -> Api:
    """API client logged in as the owner (cookie + CSRF header)."""
    client = app.test_client()
    a = Api(client)
    r = a.post("/api/admin/auth/login", {"username": owner["username"], "password": owner["password"]})
    assert r.status_code == 200, r.get_json()
    a.csrf = r.get_json()["csrf_token"]
    return a


def png_bytes(width: int = 64, height: int = 48, color=(120, 170, 220), mode: str = "RGB", fmt: str = "PNG", **save_kw) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (width, height), color).save(buf, format=fmt, **save_kw)
    return buf.getvalue()


@pytest.fixture
def png():
    return png_bytes


def make_post(admin: Api, title: str = "第一篇", **fields) -> dict:
    """Create a post through the admin API (published unless told otherwise) and return its admin JSON."""
    fields.setdefault("status", "published")
    fields.setdefault("content_md", f"{title}的正文。")
    r = admin.post("/api/admin/posts", {"title": title, **fields})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def make_moment(admin: Api, text: str = "一句话", **fields) -> dict:
    r = admin.post("/api/admin/moments", {"text": text, **fields})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def make_page(admin: Api, title: str = "关于", **fields) -> dict:
    fields.setdefault("status", "published")
    fields.setdefault("content_md", "关于我。")
    r = admin.post("/api/admin/pages", {"title": title, **fields})
    assert r.status_code == 201, r.get_json()
    return r.get_json()
