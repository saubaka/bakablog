"""System status for the admin: versions, sizes, last job results."""
from __future__ import annotations

import platform
import shutil
import sqlite3
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app import migrate
from app.config import Config
from app.db import Database
from app.services import backup, search, settings
from app.timeutil import iso, utcnow
from app.version import __version__, build_id

STARTED = time.time()
JOBS_KEY = "system.jobs"


def dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def record_job(session: Session, name: str, result: dict, ok: bool = True) -> None:
    jobs = dict(settings.get_raw(session, JOBS_KEY) or {})
    jobs[name] = {"at": iso(utcnow()), "ok": ok, "result": result}
    settings.set_raw(session, JOBS_KEY, jobs)


def jobs(session: Session) -> dict:
    return dict(settings.get_raw(session, JOBS_KEY) or {})


def status(session: Session, cfg: Config, database: Database) -> dict:
    disk = shutil.disk_usage(cfg.data_dir if cfg.data_dir.exists() else cfg.data_dir.parent)
    db_bytes = sum(p.stat().st_size for p in (cfg.db_path, Path(f"{cfg.db_path}-wal")) if p.exists())
    backups = backup.list_backups(cfg)
    last = backups[0] if backups else None
    return {
        "version": __version__,
        "build": build_id(),
        "env": cfg.env,
        "uptime_seconds": int(time.time() - STARTED),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "schema_revision": migrate.current_revision(database),
        "schema_head": migrate.head_revision(),
        "site_version": settings.site_version(session),
        "db_bytes": db_bytes,
        "media_bytes": dir_size(cfg.media_dir),
        "backup_bytes": sum(b.bytes for b in backups),
        "disk": {"total": disk.total, "free": disk.free},
        "search_rows": search.count(session),
        "last_backup": last.as_dict() if last else None,
        "backups": len(backups),
        "jobs": jobs(session),
        "site_url": cfg.site_url,
    }
