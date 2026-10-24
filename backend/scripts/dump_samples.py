"""Write real API responses (from a freshly seeded throw-away site) to docs/api-samples/*.json.

    .venv/bin/python scripts/dump_samples.py

The samples are what the front end is written against; regenerate them when an endpoint's shape changes.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.config import load_config  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.devseed import seed  # noqa: E402
from app.services import auth  # noqa: E402

PUBLIC = {
    "site": "/api/site", "home": "/api/home", "posts": "/api/posts?per=3", "post": "/api/posts/sqlite-backup", "archive": "/api/archive",
    "taxonomy": "/api/taxonomy", "moments": "/api/moments?limit=3", "page": "/api/pages/about", "search": "/api/search?q=SQLite", "health": "/api/health",
}
ADMIN = {
    "dashboard": "/api/admin/dashboard", "posts": "/api/admin/posts?per=3", "post": "/api/admin/posts/1", "moments": "/api/admin/moments?per=3",
    "media": "/api/admin/media?per=2", "categories": "/api/admin/taxonomy/categories", "tags": "/api/admin/taxonomy/tags",
    "series": "/api/admin/taxonomy/series", "settings": "/api/admin/settings", "home": "/api/admin/home", "nav": "/api/admin/nav",
    "redirects": "/api/admin/redirects", "trash": "/api/admin/trash", "audit": "/api/admin/audit?per=5", "stats": "/api/admin/stats?days=7",
    "system-status": "/api/admin/system/status", "auth-me": "/api/admin/auth/me", "auth-sessions": "/api/admin/auth/sessions",
}


def main() -> None:
    out = ROOT / "docs" / "api-samples"
    shutil.rmtree(out, ignore_errors=True)
    (out / "admin").mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="bb-samples-"))
    cfg = load_config({}, {"BLOG_ENV": "testing", "BLOG_DATA_DIR": str(work)}).with_overrides(scrypt_n=2**10, site_url="https://blog.example")
    app = create_app(cfg)
    from app import migrate

    migrate.upgrade(app.extensions["bb_db"])
    with app.app_context(), session_scope(app) as s:
        seed(s, cfg)
        auth.create_owner(s, "sample_owner", "correct horse battery", cfg)
    client = app.test_client()
    for name, url in PUBLIC.items():
        data = client.get(url).get_json()
        (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    login = client.post("/api/admin/auth/login", json={"username": "sample_owner", "password": "correct horse battery"})
    csrf = login.get_json()["csrf_token"]
    for name, url in ADMIN.items():
        data = client.get(url, headers={"X-CSRF-Token": csrf}).get_json()
        (out / "admin" / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    error = client.get("/api/posts/does-not-exist").get_json()
    (out / "error.json").write_text(json.dumps(error, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    invalid = client.post("/api/admin/posts", json={"title": "x" * 300, "oops": 1}, headers={"X-CSRF-Token": csrf}).get_json()
    (out / "error-validation.json").write_text(json.dumps(invalid, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    app.extensions["bb_db"].dispose()
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote {len(list(out.rglob('*.json')))} samples to {out}")


if __name__ == "__main__":
    main()
