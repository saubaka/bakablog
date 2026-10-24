from __future__ import annotations

import gzip
import io
import json
import sqlite3
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.db import session_scope
from app.jobs import maintenance
from app.models import (
    AdminSession,
    AuditLog,
    DeviceStat,
    LoginAttempt,
    Media,
    Moment,
    Page,
    PageView,
    Post,
    Referrer,
    Visitor,
)
from app.services import backup
from app.timeutil import iso, utcnow
from app.version import __version__
from tests.conftest import make_moment, make_page, make_post, png_bytes

A = "/api/admin"
S = f"{A}/system"


# =====================================================================================================================================
# backups
# =====================================================================================================================================
def create_backup(admin) -> dict:
    r = admin.post(f"{S}/backups", {})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def read_archive(cfg, name: str) -> dict[str, bytes]:
    out = {}
    with tarfile.open(cfg.backup_dir / name, "r:gz") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            out[m.name] = f.read() if f else b""
    return out


def test_backup_archive_contents(admin, cfg, png):
    mid = admin.upload(f"{A}/media", png(900, 600)).get_json()
    make_post(admin, "要备份的", content_md=f"![x](media:{mid['id']})")
    make_moment(admin, "一条动态")
    info = create_backup(admin)
    assert info["name"].startswith("backup-") and info["name"].endswith("-manual.tar.gz") and info["bytes"] > 1000
    files = read_archive(cfg, info["name"])
    manifest = json.loads(files["manifest.json"])
    assert manifest["counts"] == {"posts": 1, "moments": 1, "pages": 0, "media": 1, "admins": 1} and manifest["app_version"] == __version__
    assert manifest["media_files"] == len(mid["variants"]) == 2 and manifest["schema_revision"] == "0001" and manifest["db_sha256"]
    assert {n for n in files if n.startswith("media/")} == {f"media/{mid['hash'][:2]}/{mid['hash']}/{v['size']}.webp" for v in mid["variants"]}
    con = sqlite3.connect(":memory:")
    con.deserialize(files["db.sqlite"])
    assert con.execute("select count(*) from posts").fetchone()[0] == 1 and con.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert admin.get(f"{S}/backups").get_json()["items"][0]["name"] == info["name"]


def test_download_and_delete_backup(admin, cfg):
    info = create_backup(admin)
    r = admin.get(f"{S}/backups/{info['name']}/download")
    assert r.status_code == 200 and r.headers["Content-Disposition"].startswith("attachment") and r.data[:2] == b"\x1f\x8b"
    with tarfile.open(fileobj=io.BytesIO(r.data), mode="r:gz") as tar:
        assert tar.getnames()[0] == "manifest.json"
    assert admin.delete(f"{S}/backups/{info['name']}").status_code == 200
    assert admin.get(f"{S}/backups").get_json()["items"] == [] and admin.get(f"{S}/backups/{info['name']}/download").status_code == 404


@pytest.mark.parametrize("name", ["../../etc/passwd", "backup-x.tar.gz", "backup-20260101-000000-manual.tar.gz.bak", "..%2f..%2fetc%2fpasswd", "a/b", ".work-x"])
def test_backup_names_are_validated(admin, name):
    # names with slashes or dot segments never reach the handler (404 / 405); the others are refused by the name check (404)
    assert admin.get(f"{S}/backups/{name}/download").status_code in (404, 405)
    assert admin.delete(f"{S}/backups/{name}").status_code in (404, 405)


def test_backups_need_admin(api):
    for method, url in (("get", f"{S}/backups"), ("post", f"{S}/backups"), ("get", f"{S}/status"), ("post", f"{S}/restore")):
        assert getattr(api, method)(url).status_code == 401


def test_restore_round_trip(admin, app, cfg, png):
    keep_img = admin.upload(f"{A}/media", png(700, 500, (1, 2, 3))).get_json()
    kept = make_post(admin, "备份时就在的", content_md=f"独一无二的内容QWERTZ ![x](media:{keep_img['id']})", tags=["旧标签"])
    make_moment(admin, "备份时的动态")
    admin.patch(f"{A}/settings/site", {"name": "备份时的站名"})
    info = create_backup(admin)
    # ... then the site changes a lot
    doomed_img = admin.upload(f"{A}/media", png(700, 500, (9, 9, 9))).get_json()
    new_post = make_post(admin, "备份之后才写的")
    admin.delete(f"{A}/posts/{kept['id']}")
    admin.delete(f"{A}/posts/{kept['id']}/purge")
    admin.patch(f"{A}/settings/site", {"name": "之后改的站名"})
    admin.delete(f"{A}/media/{keep_img['id']}?force=1")
    admin.delete(f"{A}/media/{keep_img['id']}/purge")
    assert not (cfg.media_dir / keep_img["hash"][:2] / keep_img["hash"] / "960.webp").exists()
    assert (cfg.media_dir / doomed_img["hash"][:2] / doomed_img["hash"] / "960.webp").exists()

    r = admin.post(f"{S}/restore", {"name": info["name"], "confirm": "restore"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["restored_from"] == info["name"] and body["safety_backup"].endswith("-pre-restore.tar.gz") and body["manifest"]["counts"]["posts"] == 1
    # content, settings, search, pictures: all as they were
    api = type(admin)(app.test_client())
    assert [p["title"] for p in api.get("/api/posts").get_json()["items"]] == ["备份时就在的"]
    assert api.get("/api/site").get_json()["name"] == "备份时的站名"
    assert [p["title"] for p in api.get("/api/search?q=QWERTZ").get_json()["groups"]["posts"]] == ["备份时就在的"]
    assert api.get(keep_img["src"]).status_code == 200 and api.get(doomed_img["src"]).status_code == 404
    assert not (cfg.media_dir / doomed_img["hash"][:2]).exists() or not (cfg.media_dir / doomed_img["hash"][:2] / doomed_img["hash"]).exists()
    assert all(p.name == "media" or not p.name.startswith("media.old") for p in cfg.data_dir.iterdir())
    # the safety backup holds the state from just before the restore, so the restore itself can be undone
    safety = read_archive(cfg, body["safety_backup"])
    con = sqlite3.connect(":memory:")
    con.deserialize(safety["db.sqlite"])
    assert {t for (t,) in con.execute("select title from posts")} == {"备份之后才写的"} and new_post["id"]
    assert admin.get(f"{A}/auth/me").status_code == 200  # the administrator was there when the backup was made: still signed in
    actions = [a["action"] for a in admin.get(f"{A}/audit").get_json()["items"]]
    assert "system.restore" in actions


def test_restore_from_an_uploaded_file(admin, app, cfg):
    make_post(admin, "上传恢复的")
    info = create_backup(admin)
    make_post(admin, "之后的")
    raw = (cfg.backup_dir / info["name"]).read_bytes()
    no_confirm = admin.post(f"{S}/restore", data={"file": (io.BytesIO(raw), "b.tar.gz")}, content_type="multipart/form-data")
    assert no_confirm.status_code == 422 and no_confirm.get_json()["error"]["code"] == "confirm_required"
    ok = admin.post(f"{S}/restore", data={"file": (io.BytesIO(raw), "b.tar.gz"), "confirm": "restore"}, content_type="multipart/form-data")
    assert ok.status_code == 200
    assert [p["title"] for p in type(admin)(app.test_client()).get("/api/posts").get_json()["items"]] == ["上传恢复的"]
    assert not list(cfg.backup_dir.glob(".upload-*"))  # the temporary copy is gone


def test_restore_requires_confirmation_and_a_known_backup(admin):
    info = create_backup(admin)
    assert admin.post(f"{S}/restore", {"name": info["name"]}).status_code == 422
    assert admin.post(f"{S}/restore", {"name": info["name"], "confirm": "yes"}).status_code == 422
    assert admin.post(f"{S}/restore", {"name": "backup-20200101-000000-manual.tar.gz", "confirm": "restore"}).status_code == 404
    assert admin.post(f"{S}/restore", {"confirm": "restore"}).status_code == 404


def _rewrite(src: Path, dst: Path, mutate) -> Path:
    """Copy an archive member by member through `mutate(name, data) -> list[(TarInfo, bytes)]`."""
    with tarfile.open(src, "r:gz") as tin, tarfile.open(dst, "w:gz") as tout:
        for m in tin.getmembers():
            data = tin.extractfile(m).read()
            for info, payload in mutate(m.name, data, m):
                tout.addfile(info, io.BytesIO(payload) if payload is not None else None)
    return dst


def _same(name, data, m):
    return [(m, data)]


def _bad_archives(valid: Path, tmp_path: Path) -> dict[str, Path]:
    out = {}

    def tinfo(name, size=0, kind=tarfile.REGTYPE, link=""):
        t = tarfile.TarInfo(name)
        t.size, t.type, t.linkname = size, kind, link
        return t

    def add(label, extra):
        def mutate(name, data, m):
            return [(m, data)] + extra
        out[label] = _rewrite(valid, tmp_path / f"{label}.tar.gz", mutate)

    add("traversal", [(tinfo("../../evil.txt", 4), b"evil")])
    add("absolute", [(tinfo("/etc/cron.d/evil", 4), b"evil")])
    add("symlink", [(tinfo("media/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/480.webp", 0, tarfile.SYMTYPE, "/etc/passwd"), None)])
    add("hardlink", [(tinfo("media/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/960.webp", 0, tarfile.LNKTYPE, "db.sqlite"), None)])
    add("stranger", [(tinfo("backdoor.py", 11), b"import os;;;")])
    add("bad_media_name", [(tinfo("media/aa/not-a-hash/480.webp", 3), b"abc")])
    add("media_wrong_size", [(tinfo("media/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/9999.webp", 3), b"abc")])
    add("directory", [(tinfo("media/", 0, tarfile.DIRTYPE), None)])

    def drop_manifest(name, data, m):
        return [] if name == "manifest.json" else [(m, data)]
    out["no_manifest"] = _rewrite(valid, tmp_path / "no_manifest.tar.gz", drop_manifest)

    def bad_sum(name, data, m):
        if name != "manifest.json":
            return [(m, data)]
        manifest = json.loads(data)
        manifest["db_sha256"] = "0" * 64
        raw = json.dumps(manifest).encode()
        m.size = len(raw)
        return [(m, raw)]
    out["bad_checksum"] = _rewrite(valid, tmp_path / "bad_checksum.tar.gz", bad_sum)

    def newer(name, data, m):
        if name != "manifest.json":
            return [(m, data)]
        manifest = json.loads(data)
        manifest["schema_revision"] = "9999"
        raw = json.dumps(manifest).encode()
        m.size = len(raw)
        return [(m, raw)]
    out["newer_schema"] = _rewrite(valid, tmp_path / "newer.tar.gz", newer)

    def corrupt_db(name, data, m):
        if name == "db.sqlite":
            data = data[:2000] + b"\x00" * 500 + data[2500:]
        if name == "manifest.json":
            import hashlib
            manifest = json.loads(data)
            manifest["db_sha256"] = hashlib.sha256(b"x").hexdigest()
            data = json.dumps(manifest).encode()
            m.size = len(data)
        return [(m, data)]
    out["corrupt_db"] = _rewrite(valid, tmp_path / "corrupt.tar.gz", corrupt_db)

    plain = tmp_path / "plain.tar.gz"
    plain.write_bytes(b"this is not an archive at all")
    out["not_gzip"] = plain
    cut = tmp_path / "cut.tar.gz"
    cut.write_bytes(valid.read_bytes()[: valid.stat().st_size // 3])
    out["truncated"] = cut
    empty = tmp_path / "empty.tar.gz"
    empty.write_bytes(gzip.compress(b""))
    out["empty"] = empty
    return out


def test_hostile_or_broken_archives_are_refused_without_touching_the_site(admin, app, cfg, tmp_path):
    make_post(admin, "必须原样保留")
    info = create_backup(admin)
    cases = _bad_archives(cfg.backup_dir / info["name"], tmp_path)
    before = sorted(p.name for p in cfg.backup_dir.iterdir())
    for label, path in cases.items():
        r = admin.post(f"{S}/restore", data={"file": (io.BytesIO(path.read_bytes()), f"{label}.tar.gz"), "confirm": "restore"}, content_type="multipart/form-data")
        assert r.status_code == 422, (label, r.status_code, r.get_json())
        assert r.get_json()["error"]["code"] in ("bad_backup", "newer_backup"), (label, r.get_json())
    assert sorted(p.name for p in cfg.backup_dir.iterdir()) == before  # no safety backup was made: nothing was attempted
    assert not (cfg.data_dir.parent / "evil.txt").exists() and not Path("/etc/cron.d/evil").exists()
    assert [p["title"] for p in type(admin)(app.test_client()).get("/api/posts").get_json()["items"]] == ["必须原样保留"]
    assert not list(cfg.data_dir.glob(".restore-*"))


def test_prune_only_removes_old_automatic_backups(cfg, app):
    cfg.backup_dir.mkdir(parents=True, exist_ok=True)
    for n, label in enumerate(["auto", "auto", "auto", "manual", "pre-restore"]):
        (cfg.backup_dir / f"backup-2026010{n + 1}-000000-{label}.tar.gz").write_bytes(b"x")
    assert backup.prune(cfg, keep=2) == 1
    assert sorted(b.name for b in backup.list_backups(cfg)) == [
        "backup-20260102-000000-auto.tar.gz", "backup-20260103-000000-auto.tar.gz", "backup-20260104-000000-manual.tar.gz", "backup-20260105-000000-pre-restore.tar.gz"]


# =====================================================================================================================================
# scheduled jobs
# =====================================================================================================================================
def test_daily_backup_runs_once_at_the_configured_hour(app, cfg, monkeypatch):
    fixed = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)  # 18:00 in Shanghai
    monkeypatch.setattr(maintenance, "utcnow", lambda: fixed)
    monkeypatch.setattr(backup, "utcnow", lambda: fixed)  # the file name carries the same (fixed) day, so "already done today" holds on any real date
    with session_scope(app) as s:
        from app.services import settings
        settings.set_group(s, "backup", {"enabled": False, "hour": 3, "keep": 14})
    assert maintenance.job_backup(app) == {"skipped": "disabled"}
    with session_scope(app) as s:
        settings.set_group(s, "backup", {"enabled": True, "hour": 19, "keep": 14})
    assert maintenance.job_backup(app) == {"skipped": "not yet"}
    with session_scope(app) as s:
        settings.set_group(s, "backup", {"enabled": True, "hour": 18, "keep": 2})
    first = maintenance.job_backup(app)
    assert first["created"].endswith("-auto.tar.gz")
    assert maintenance.job_backup(app) == {"skipped": "already done today"}
    assert maintenance.job_backup(app, force=True)["created"].endswith("-manual.tar.gz")


def test_run_scheduled_records_results_and_runs_housekeeping_daily(app, admin):
    first = maintenance.run_scheduled(app)
    assert set(first) == {"backup", "housekeeping", "trash"}
    jobs = admin.get(f"{S}/jobs").get_json()
    assert "housekeeping" in jobs["jobs"] and jobs["jobs"]["housekeeping"]["ok"] is True and "backup" in jobs["available"]
    again = maintenance.run_scheduled(app)
    assert set(again) == {"backup"}  # housekeeping and trash ran less than a day ago


def test_the_trash_is_emptied_after_thirty_days(admin, app, cfg, png):
    old_img = admin.upload(f"{A}/media", png(200, 200, (1, 1, 1))).get_json()
    new_img = admin.upload(f"{A}/media", png(200, 200, (2, 2, 2))).get_json()
    old_post = make_post(admin, "旧垃圾")
    new_post = make_post(admin, "新垃圾")
    old_moment = make_moment(admin, "旧动态垃圾")
    old_page = make_page(admin, "旧页面", slug="old-page")
    for kind, item in (("posts", old_post), ("posts", new_post), ("moments", old_moment), ("pages", old_page), ("media", old_img), ("media", new_img)):
        admin.delete(f"{A}/{kind}/{item['id']}" + ("?force=1" if kind == "media" else ""))
    with session_scope(app) as s:
        s.get(Post, old_post["id"]).deleted_at = utcnow() - timedelta(days=31)
        s.get(Post, new_post["id"]).deleted_at = utcnow() - timedelta(days=29)
        s.get(Moment, old_moment["id"]).deleted_at = utcnow() - timedelta(days=45)
        s.get(Page, old_page["id"]).deleted_at = utcnow() - timedelta(days=40)
        s.get(Media, old_img["id"]).deleted_at = utcnow() - timedelta(days=33)
        s.get(Media, new_img["id"]).deleted_at = utcnow() - timedelta(days=1)
    listing = admin.get(f"{A}/trash").get_json()
    assert listing["retention_days"] == 30 and len(listing["items"]) == 6
    assert next(i for i in listing["items"] if i["id"] == new_post["id"] and i["type"] == "post")["days_left"] in (0, 1)
    result = maintenance.job_trash(app)
    assert result == {"post": 1, "moment": 1, "page": 1, "media": 1}
    left = {(i["type"], i["id"]) for i in admin.get(f"{A}/trash").get_json()["items"]}
    assert left == {("post", new_post["id"]), ("media", new_img["id"])}
    assert not (cfg.media_dir / old_img["hash"][:2] / old_img["hash"]).exists() and (cfg.media_dir / new_img["hash"][:2] / new_img["hash"]).exists()


def test_trash_api(admin, api):
    p = make_post(admin, "进回收站")
    m = make_moment(admin, "动态进回收站")
    pg = make_page(admin, "页面进回收站")
    mid = admin.upload(f"{A}/media", png_bytes(50, 50)).get_json()["id"]
    admin.delete(f"{A}/posts/{p['id']}")
    admin.delete(f"{A}/moments/{m['id']}")
    admin.delete(f"{A}/pages/{pg['id']}")
    admin.delete(f"{A}/media/{mid}")
    items = admin.get(f"{A}/trash").get_json()["items"]
    assert {i["type"] for i in items} == {"post", "moment", "page", "media"}
    assert admin.post(f"{A}/trash/restore", {"type": "post", "id": p["id"]}).status_code == 200
    assert api.get(f"/api/posts/{p['slug']}").status_code == 200
    assert admin.post(f"{A}/trash/restore", {"type": "post", "id": p["id"]}).status_code == 404  # no longer in the trash
    assert admin.post(f"{A}/trash/restore", {"type": "comment", "id": 1}).status_code == 422
    assert admin.delete(f"{A}/trash/moment/{m['id']}").status_code == 200
    assert admin.delete(f"{A}/trash/nonsense/1").status_code == 404
    assert admin.delete(f"{A}/trash").get_json() == {"purged": 2}
    assert admin.get(f"{A}/trash").get_json()["items"] == []


def test_housekeeping_prunes_old_operational_data(app, admin):
    with session_scope(app) as s:
        s.add(LoginAttempt(username="old", ip_prefix="1.2.3.0/24", at=utcnow() - timedelta(days=100), success=False, reason="bad_password"))
        s.add(LoginAttempt(username="recent", ip_prefix="1.2.3.0/24", at=utcnow() - timedelta(days=5), success=False, reason="bad_password"))
        s.add(Visitor(day=(utcnow() - timedelta(days=2)).date(), hash="a" * 16, page_key="*"))
        s.add(Visitor(day=utcnow().date() + timedelta(days=1), hash="b" * 16, page_key="*"))  # tomorrow in UTC terms, never today's yet
        s.add(PageView(day=(utcnow() - timedelta(days=800)).date(), kind="site", ref_id=0, views=1, uniques=1))
        s.add(Referrer(day=(utcnow() - timedelta(days=800)).date(), domain="old.example", count=1))
        s.add(DeviceStat(day=(utcnow() - timedelta(days=800)).date(), device="phone", count=1))
        s.add(AdminSession(user_id=1, token_hash="e" * 64, csrf_token="x", expires_at=utcnow() - timedelta(days=30)))
    result = maintenance.job_housekeeping(app)
    assert result["auth"] == {"sessions": 1, "login_attempts": 1} and result["stats"]["visitors"] >= 1 and result["stats"]["page_views"] == 1
    with session_scope(app) as s:
        assert [a.username for a in s.scalars(select(LoginAttempt).where(LoginAttempt.success.is_(False)))] == ["recent"]
        assert s.scalar(select(Referrer)) is None and s.scalar(select(DeviceStat)) is None


def test_reindex_job_rebuilds_search_from_the_content(admin, api, app):
    make_post(admin, "能被找回的", content_md="独特词语ZXCVB")
    make_moment(admin, "动态也能找回 独特动态词QAZWSX")
    make_page(admin, "页面也要", content_md="页面独特词EDCRFV")
    with session_scope(app) as s:
        s.execute(text("DELETE FROM search_fts"))
    assert api.get("/api/search?q=ZXCVB").get_json()["total"] == 0
    r = admin.post(f"{S}/jobs/reindex", {})
    assert r.status_code == 200 and r.get_json()["post"] == 1 and r.get_json()["moment"] == 1 and r.get_json()["page"] == 1
    assert api.get("/api/search?q=ZXCVB").get_json()["total"] == 1 and api.get("/api/search?q=QAZWSX").get_json()["total"] == 1
    assert api.get("/api/search?q=EDCRFV").get_json()["total"] == 1
    assert admin.get(f"{S}/status").get_json()["search_rows"] == 3


def test_thumbnail_job_restores_missing_sizes(admin, cfg, png):
    d = admin.upload(f"{A}/media", png(1400, 900)).get_json()
    small = cfg.media_dir / d["hash"][:2] / d["hash"] / "480.webp"
    small.unlink()
    r = admin.post(f"{S}/jobs/thumbnails", {})
    assert r.get_json()["regenerated"] == 1 and small.exists()


def test_vacuum_and_cache_jobs(admin, api):
    r = admin.post(f"{S}/jobs/vacuum", {})
    assert r.status_code == 200 and r.get_json()["after"] > 0
    before = api.get("/api/health").get_json()["site_version"]
    assert admin.post(f"{S}/jobs/cache", {}).get_json()["site_version"] > before
    assert admin.post(f"{S}/jobs/explode", {}).status_code == 404 and admin.post(f"{S}/jobs/backup", {}).status_code == 404


def test_a_failing_job_is_reported_not_fatal(app, admin, monkeypatch):
    monkeypatch.setitem(maintenance.JOBS, "vacuum", lambda a: (_ for _ in ()).throw(RuntimeError("disk on fire")))
    r = admin.post(f"{S}/jobs/vacuum", {})
    assert r.status_code == 200 and r.get_json()["ok"] is False and "disk on fire" in r.get_json()["error"]
    assert admin.get(f"{S}/jobs").get_json()["jobs"]["vacuum"]["ok"] is False


# =====================================================================================================================================
# status, dashboard, audit, statistics
# =====================================================================================================================================
def test_system_status(admin, cfg):
    s = admin.get(f"{S}/status").get_json()
    assert s["version"] == __version__ and s["env"] == "testing" and s["schema_revision"] == s["schema_head"] == "0001"
    assert s["db_bytes"] > 0 and s["disk"]["free"] > 0 and s["python"].startswith("3.") and s["sqlite"]
    assert s["last_backup"] is None and s["backups"] == 0 and s["uptime_seconds"] >= 0
    create_backup(admin)
    s2 = admin.get(f"{S}/status").get_json()
    assert s2["last_backup"]["label"] == "manual" and s2["backups"] == 1 and s2["backup_bytes"] > 0


def test_dashboard(admin, app, png):
    stale = make_post(admin, "放了很久的草稿", status="draft")
    make_post(admin, "已发布没封面")
    make_post(admin, "定时的", published_at=iso(utcnow() + timedelta(days=2)))
    make_moment(admin, "这个月的动态")
    mid = admin.upload(f"{A}/media", png(100, 100)).get_json()["id"]
    make_post(admin, "有图没 alt", content_md=f"![](media:{mid})")
    with session_scope(app) as s:
        s.get(Post, stale["id"]).updated_at = utcnow() - timedelta(days=9)
    d = admin.get(f"{A}/dashboard").get_json()
    assert d["stats"]["posts"] == {"published": 2, "draft": 1, "scheduled": 1} and d["stats"]["moments_month"] == 1
    assert d["stats"]["storage"]["media_bytes"] > 0 and len(d["views_series"]) == 7
    kinds = {t["kind"] for t in d["todo"]}
    assert {"stale_draft", "scheduled_soon", "missing_cover", "image_no_alt"} <= kinds
    assert next(t for t in d["todo"] if t["kind"] == "stale_draft")["days"] == 9
    assert d["recent"][0]["action"].startswith("post.") or d["recent"][0]["action"].startswith("moment.") or d["recent"][0]["action"].startswith("media.")
    assert d["health"]["version"] == __version__ and d["health"]["schema_ok"] is True


def test_audit_log_listing_and_filters(admin):
    p = make_post(admin, "有记录")
    make_moment(admin, "有记录的动态")
    admin.patch(f"{A}/posts/{p['id']}", {"title": "改了"})
    body = admin.get(f"{A}/audit").get_json()
    assert body["total"] >= 4 and body["items"][0]["actor"] == "baka_owner" and body["items"][0]["ip_prefix"] == "127.0.0.0/24"
    assert [a["action"] for a in admin.get(f"{A}/audit?action=post.").get_json()["items"]] == ["post.update", "post.create"]
    assert [a["action"] for a in admin.get(f"{A}/audit?target_type=moment").get_json()["items"]] == ["moment.create"]
    assert len(admin.get(f"{A}/audit?per=2").get_json()["items"]) == 2 and admin.get(f"{A}/audit?per=999").status_code == 422
    assert all(a["actor"] == "baka_owner" for a in body["items"] if a["action"].startswith(("post", "moment")))


def test_audit_log_is_append_only(app, admin):
    make_post(admin, "触发审计")
    con = sqlite3.connect(app.extensions["bb_config"].db_path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE audit_logs SET action = 'tampered'")
    with pytest.raises(sqlite3.DatabaseError, match="younger than a year"):
        con.execute("DELETE FROM audit_logs")
    old = (utcnow() - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
    con.execute("INSERT INTO audit_logs(at, actor_name, action, target_type, target_id, summary, ip_prefix) VALUES (?, 'x', 'old.thing', '', '', '{}', '')", (old,))
    con.commit()
    assert con.execute("DELETE FROM audit_logs WHERE action = 'old.thing'").rowcount == 1  # a year-old entry may be retired
    con.commit()
    with session_scope(app) as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "tampered")) is None


def test_stats_endpoint_shapes_and_validation(admin):
    s = admin.get(f"{A}/stats?days=30").get_json()
    assert s["days"] == 30 and len(s["series"]) == 30 and s["total_views"] == 0 and s["top_posts"] == [] and s["devices"] == {}
    assert [x["day"] for x in s["series"]] == sorted(x["day"] for x in s["series"])
    assert admin.get(f"{A}/stats?days=5").status_code == 422 and admin.get(f"{A}/stats?days=abc").status_code == 422
    assert admin.get(f"{A}/stats").get_json()["days"] == 30


def test_visitor_salt_rotates_daily(admin, api, app):
    from app.services import settings, stats

    p = make_post(admin, "盐")
    ua = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15"}
    api.post("/api/track", data=json.dumps({"p": f"/blog/{p['slug']}"}), headers=ua, content_type="text/plain")
    with session_scope(app) as s:
        first = settings.get_raw(s, stats.SALT_KEY)
        settings.set_raw(s, stats.SALT_KEY, {**first, "day": "2000-01-01"})  # pretend it is from long ago
    api.post("/api/track", data=json.dumps({"p": f"/blog/{p['slug']}"}), headers=ua, content_type="text/plain")
    with session_scope(app) as s:
        second = settings.get_raw(s, stats.SALT_KEY)
    assert second["salt"] != first["salt"] and second["day"] != "2000-01-01"


# =====================================================================================================================================
# editor helpers
# =====================================================================================================================================
def test_markdown_preview_matches_what_gets_published(admin, api, png):
    mid = admin.upload(f"{A}/media", png(800, 500)).get_json()["id"]
    source = f"## 小节\n\n正文 **粗** [外链](https://example.com)\n\n![图](media:{mid} \"说明\")\n\n```python title=a.py\nprint(1)\n```\n\n::: tip\n提示\n:::\n"
    pv = admin.post(f"{A}/markdown/preview", {"text": source}).get_json()
    post = make_post(admin, "对照", content_md=source)
    published = api.get(f"/api/posts/{post['slug']}").get_json()
    assert pv["html"] == published["html"] and pv["toc"] == published["toc"] and pv["media_ids"] == [mid]
    assert pv["word_count"] > 0 and pv["reading_minutes"] == 1 and pv["summary"].startswith("正文 粗")


def test_markdown_preview_warnings_profiles_and_limits(admin):
    r = admin.post(f"{A}/markdown/preview", {"text": "![远程](https://evil.example/x.png)\n\n![](media:424242)"}).get_json()
    assert len(r["warnings"]) == 2 and "外链图片" in r["warnings"][0]
    moment = admin.post(f"{A}/markdown/preview", {"text": "# 不是标题\n\n**粗**", "profile": "moment"}).get_json()
    assert "<h1" not in moment["html"] and "<strong>粗</strong>" in moment["html"]
    assert admin.post(f"{A}/markdown/preview", {"text": "x" * 400_001}).status_code == 422
    assert admin.post(f"{A}/markdown/preview", {"text": "x", "profile": "page"}).status_code == 422
    assert admin.post(f"{A}/markdown/preview", {"text": "<script>alert(1)</script>"}).get_json()["html"] == ""


def test_slug_helper(admin):
    make_post(admin, "已占用的标题")
    r = admin.post(f"{A}/utils/slug", {"title": "已占用的标题", "kind": "post"}).get_json()
    assert r == {"slug": "yi-zhan-yong-de-biao-ti-2", "valid": True}
    first = admin.get(f"{A}/posts").get_json()["items"][0]
    assert admin.post(f"{A}/utils/slug", {"title": "已占用的标题", "kind": "post", "exclude_id": first["id"]}).get_json()["slug"] == "yi-zhan-yong-de-biao-ti"
    assert admin.post(f"{A}/utils/slug", {"title": "Search", "kind": "page"}).get_json()["slug"] == "search-2"
    assert admin.post(f"{A}/utils/slug", {"title": "标签名", "kind": "tag"}).get_json()["slug"] == "biao-qian-ming"
    assert admin.post(f"{A}/utils/slug", {"title": "!!!", "kind": "post"}).get_json()["slug"] == "post"
    assert admin.post(f"{A}/utils/slug", {"title": "x", "kind": "comment"}).status_code == 422


_ = (Media,)
