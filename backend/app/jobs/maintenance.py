"""Background chores, run by `flask --app app maintenance` (a systemd timer calls it every 5 minutes) or by the admin's buttons.

Everything is idempotent and cheap when there is nothing to do: the daily backup only runs once a day at the configured hour,
the trash is purged once per run of the "daily" group, and so on.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import timedelta

from flask import Flask
from sqlalchemy import delete, select

from app.config import Config
from app.db import Database, session_scope
from app.models import AuditLog, Media
from app.services import auth, backup, search, settings, stats, system, trash
from app.services import media as media_service
from app.timeutil import local, utcnow

log = logging.getLogger(__name__)
NAMES = ("backup", "housekeeping", "trash", "reindex", "thumbnails", "vacuum", "cache")


def _cfg(app: Flask) -> Config:
    return app.extensions["bb_config"]


def _db(app: Flask) -> Database:
    return app.extensions["bb_db"]


def job_backup(app: Flask, *, force: bool = False) -> dict:
    cfg = _cfg(app)
    with session_scope(app, write=False) as s:
        conf = settings.group(s, "backup")
        tz = settings.group(s, "site")["timezone"]
    if not force:
        if not conf["enabled"]:
            return {"skipped": "disabled"}
        now_local = local(utcnow(), tz)
        if now_local.hour < conf["hour"]:
            return {"skipped": "not yet"}
        done_today = any(local(b.created_at, tz).date() == now_local.date() and b.label == "auto" for b in backup.list_backups(cfg))
        if done_today:
            return {"skipped": "already done today"}
    info = backup.create(cfg, _db(app), label="auto" if not force else "manual")
    removed = backup.prune(cfg, conf["keep"])
    return {"created": info.name, "bytes": info.bytes, "pruned": removed}


def job_trash(app: Flask) -> dict:
    with session_scope(app) as s:
        return trash.purge_expired(s, _cfg(app))


def job_housekeeping(app: Flask) -> dict:
    with session_scope(app) as s:
        tz = settings.group(s, "site")["timezone"]
        out = {"auth": auth.prune(s), "stats": stats.prune(s, tz)}
        cutoff = utcnow() - timedelta(days=365)
        out["audit"] = int(s.execute(delete(AuditLog).where(AuditLog.at < cutoff - timedelta(days=1))).rowcount or 0)
        return out


def job_reindex(app: Flask) -> dict:
    with session_scope(app) as s:
        return search.rebuild(s)


def job_thumbnails(app: Flask) -> dict:
    cfg = _cfg(app)
    done = failed = 0
    with session_scope(app) as s:
        for media in s.scalars(select(Media)):
            try:
                if media_service.regenerate_variants(s, cfg, media):
                    done += 1
            except Exception:  # noqa: BLE001
                log.exception("thumbnails failed for media %s", media.id)
                failed += 1
    return {"regenerated": done, "failed": failed}


def job_vacuum(app: Flask) -> dict:
    cfg = _cfg(app)
    before = cfg.db_path.stat().st_size if cfg.db_path.exists() else 0
    con = sqlite3.connect(cfg.db_path, timeout=30, isolation_level=None)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
        con.execute("PRAGMA optimize")
    finally:
        con.close()
    after = cfg.db_path.stat().st_size if cfg.db_path.exists() else 0
    return {"before": before, "after": after}


def job_cache(app: Flask) -> dict:
    """Nothing is cached across requests except what browsers hold (ETags); bumping the site version refreshes those."""
    with session_scope(app) as s:
        return {"site_version": settings.bump_site_version(s)}


JOBS = {"backup": job_backup, "housekeeping": job_housekeeping, "trash": job_trash, "reindex": job_reindex, "thumbnails": job_thumbnails,
        "vacuum": job_vacuum, "cache": job_cache}


def run_one(app: Flask, name: str, **kw) -> dict:
    """Run one job and remember its result for the system page."""
    if name not in JOBS:
        raise KeyError(name)
    try:
        result = JOBS[name](app, **kw) if name == "backup" else JOBS[name](app)
        ok = True
    except Exception as exc:  # noqa: BLE001 - a failing job must be visible on the system page, not kill the timer
        log.exception("job %s failed", name)
        result, ok = {"error": str(exc)[:300]}, False
    if not (isinstance(result, dict) and result.get("skipped")):
        with session_scope(app) as s:
            system.record_job(s, name, result, ok)
    return {"ok": ok, **result}


def run_scheduled(app: Flask) -> dict[str, dict]:
    """What the timer runs: the daily backup (when due), the daily housekeeping and trash purge."""
    out = {"backup": run_one(app, "backup")}
    with session_scope(app, write=False) as s:
        last = system.jobs(s).get("housekeeping")
    due = last is None or (utcnow() - _parse(last["at"])) > timedelta(hours=23)
    if due:
        out["housekeeping"] = run_one(app, "housekeeping")
        out["trash"] = run_one(app, "trash")
    return out


def _parse(text: str):
    from app.timeutil import parse_iso

    return parse_iso(text)
