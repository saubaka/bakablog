"""Backup and restore: one .tar.gz holding a consistent copy of the database, every picture file and a manifest.

- The database is copied with SQLite's online backup API (consistent even while the site is being written), then checked with
  PRAGMA integrity_check; a copy that fails the check is never published as a backup.
- Restore validates the archive first (only expected member names, no links, no path tricks, checksum, integrity, schema not newer than
  this build), takes a safety backup of the current state, then copies the database back through the same backup API and swaps the
  media folder.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import Flask

from app import migrate
from app.config import Config
from app.db import Database
from app.errors import ApiError
from app.timeutil import UTC, iso, utcnow
from app.version import __version__

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^backup-(\d{8})-(\d{6})-([a-z\-]{1,20})\.tar\.gz$")
_MEDIA_MEMBER = re.compile(r"^media/[0-9a-f]{2}/[0-9a-f]{16,64}/(?:480|960|1600)\.webp$")
MAX_DB_BYTES = 4 * 1024**3
MAX_MEMBERS = 200_000
MAX_MANIFEST_BYTES = 16 * 1024**2


@dataclass
class BackupInfo:
    name: str
    bytes: int
    created_at: datetime
    label: str

    def as_dict(self) -> dict:
        return {"name": self.name, "bytes": self.bytes, "created_at": iso(self.created_at), "label": self.label}


def _info(path: Path) -> BackupInfo | None:
    m = NAME_RE.match(path.name)
    if not m:
        return None
    created = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return BackupInfo(path.name, path.stat().st_size, created, m.group(3))


def list_backups(cfg: Config) -> list[BackupInfo]:
    if not cfg.backup_dir.is_dir():
        return []
    out = [i for p in cfg.backup_dir.iterdir() if p.is_file() and (i := _info(p))]
    return sorted(out, key=lambda i: i.created_at, reverse=True)


def backup_path(cfg: Config, name: str) -> Path:
    if not NAME_RE.match(name):
        raise ApiError(404)
    path = cfg.backup_dir / name
    if not path.is_file():
        raise ApiError(404, "not_found", "没有这份备份。")
    return path


def _counts(path: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {key: con.execute(query).fetchone()[0]
                for key, query in (("posts", "SELECT count(*) FROM posts"), ("moments", "SELECT count(*) FROM moments"),
                                   ("pages", "SELECT count(*) FROM pages"), ("media", "SELECT count(*) FROM media"),
                                   ("admins", "SELECT count(*) FROM admin_users"))}
    finally:
        con.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_db(src_path: Path, dst_path: Path) -> None:
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")  # the copy is one self-contained file, no -wal / -shm beside it
    finally:
        dst.close()
        src.close()


def _integrity_ok(path: Path) -> bool:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def create(cfg: Config, database: Database, *, label: str = "manual") -> BackupInfo:
    label = re.sub(r"[^a-z\-]", "", label.lower())[:20] or "manual"
    cfg.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow()
    name = f"backup-{stamp:%Y%m%d-%H%M%S}-{label}.tar.gz"
    final = cfg.backup_dir / name
    with tempfile.TemporaryDirectory(dir=cfg.backup_dir, prefix=".work-") as work_s:
        work = Path(work_s)
        db_copy = work / "db.sqlite"
        _copy_db(cfg.db_path, db_copy)
        if not _integrity_ok(db_copy):
            raise ApiError(500, "backup_failed", "备份出的数据库没有通过完整性检查，已放弃。")
        media_files = []
        for path in cfg.media_dir.rglob("*.webp") if cfg.media_dir.is_dir() else []:
            rel = f"media/{path.relative_to(cfg.media_dir).as_posix()}"
            if not _MEDIA_MEMBER.fullmatch(rel):
                continue
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            media_files.append(target)
        snapshot = sqlite3.connect(f"file:{db_copy}?mode=ro", uri=True)
        try:
            revision = snapshot.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            snapshot.close()
        manifest = {
            "app_version": __version__, "schema_revision": revision, "created_at": iso(stamp),
            "db_sha256": _sha256(db_copy), "db_bytes": db_copy.stat().st_size, "media_files": len(media_files),
            "media_bytes": sum(p.stat().st_size for p in media_files), "counts": _counts(db_copy),
            "media_sha256": {p.relative_to(work).as_posix(): _sha256(p) for p in media_files},
        }
        tmp_tar = work / name
        with tarfile.open(tmp_tar, "w:gz") as tar:
            data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            info = tarfile.TarInfo("manifest.json")
            info.size, info.mtime = len(data), int(stamp.timestamp())
            tar.addfile(info, io.BytesIO(data))
            tar.add(db_copy, arcname="db.sqlite")
            for path in media_files:
                rel = path.relative_to(work / "media").as_posix()
                if _MEDIA_MEMBER.match(f"media/{rel}"):
                    tar.add(path, arcname=f"media/{rel}", recursive=False)
        os.replace(tmp_tar, final)
    return _info(final)  # type: ignore[return-value]


def prune(cfg: Config, keep: int) -> int:
    """Keep the newest `keep` automatic backups (manual ones and safety backups are never removed by this)."""
    auto = [b for b in list_backups(cfg) if b.label == "auto"]
    removed = 0
    for old in auto[keep:]:
        (cfg.backup_dir / old.name).unlink(missing_ok=True)
        removed += 1
    return removed


# ---- restore ---------------------------------------------------------------------------------------------------------------------
def _safe_extract(tar: tarfile.TarFile, dest: Path) -> dict:
    members = tar.getmembers()
    if len(members) > MAX_MEMBERS:
        raise ApiError(422, "bad_backup", "备份文件里的内容太多，不像是这个站点的备份。")
    names = {m.name for m in members}
    if len(names) != len(members):
        raise ApiError(422, "bad_backup", "备份里有重复的文件名。")
    if "manifest.json" not in names or "db.sqlite" not in names:
        raise ApiError(422, "bad_backup", "这不是有效的备份文件（缺少 manifest.json 或 db.sqlite）。")
    for m in members:
        if not m.isfile():
            raise ApiError(422, "bad_backup", "备份里有不允许的内容类型。")
        if m.name in ("manifest.json", "db.sqlite"):
            if m.size > (MAX_MANIFEST_BYTES if m.name == "manifest.json" else MAX_DB_BYTES):
                raise ApiError(422, "bad_backup", "数据库太大。")
            continue
        if not _MEDIA_MEMBER.match(m.name):
            raise ApiError(422, "bad_backup", f"备份里有不认识的文件：{m.name[:60]}")
    for m in members:
        target = dest / m.name
        target.parent.mkdir(parents=True, exist_ok=True)
        src = tar.extractfile(m)
        if src is None:
            continue
        with src, target.open("wb") as out:
            shutil.copyfileobj(src, out, 1024 * 1024)
    try:
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        return manifest
    except (ValueError, OSError) as exc:
        raise ApiError(422, "bad_backup", "manifest.json 读不出来。") from exc


def restore(app: Flask, archive: Path) -> dict:
    cfg: Config = app.extensions["bb_config"]
    database: Database = app.extensions["bb_db"]
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cfg.data_dir, prefix=".restore-") as work_s:
        work = Path(work_s)
        try:
            with tarfile.open(archive, "r:gz") as tar:
                manifest = _safe_extract(tar, work)
        except (tarfile.TarError, OSError, EOFError) as exc:
            raise ApiError(422, "bad_backup", "备份文件无法读取，可能已损坏。") from exc
        db_file = work / "db.sqlite"
        if _sha256(db_file) != manifest.get("db_sha256") or db_file.stat().st_size != manifest.get("db_bytes"):
            raise ApiError(422, "bad_backup", "校验和不对，备份文件可能被改动或损坏。")
        _validate_database(db_file, manifest, work)
        _validate_media(db_file, manifest, work)
        safety = create(cfg, database, label="pre-restore")
        original = work / "original.sqlite"
        _copy_db(cfg.db_path, original)
        try:
            _restore_db(db_file, cfg.db_path)
            database.dispose()
            _swap_media(cfg, work / "media")
        except Exception:
            # Validation and migrations have already finished on the isolated copy. If the final switch fails,
            # retain the live database's pre-switch contents as well as the untouched original media directory.
            try:
                _restore_db(original, cfg.db_path)
                database.dispose()
            except Exception:
                recovery = cfg.data_dir / f"restore-recovery-{work.name.removeprefix('.restore-')}.sqlite"
                shutil.copyfile(original, recovery)
                log.exception("restore rollback failed; database copy retained at %s; safety backup %s", recovery, safety.name)
                raise
            raise
    return {"restored_from": archive.name, "safety_backup": safety.name, "manifest": manifest}


def _known_revisions() -> list[str]:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate._alembic_config())
    return [r.revision for r in script.walk_revisions()]


def _schema(path: Path) -> dict[tuple[str, str], str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {(kind, name): " ".join(sql.split())
                for kind, name, sql in con.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}
    finally:
        con.close()


def _validate_database(path: Path, manifest: dict, work: Path) -> None:
    staged = Database(path)
    reference = Database(work / "reference.sqlite")
    try:
        if not _integrity_ok(path):
            raise ValueError("integrity check failed")
        revision = migrate.current_revision(staged)
        claimed = manifest.get("schema_revision")
        if claimed and claimed not in _known_revisions():
            raise ApiError(422, "newer_backup", "这份备份来自更新版本的程序，请先升级程序再恢复。")
        if not revision or revision != claimed or revision not in _known_revisions():
            raise ValueError("database revision does not match the manifest")
        migrate.upgrade(reference, revision)
        if _schema(path) != _schema(work / "reference.sqlite"):
            raise ValueError("database schema does not match its revision")
        if _counts(path) != manifest.get("counts"):
            raise ValueError("database counts do not match the manifest")
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if con.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("foreign key check failed")
        finally:
            con.close()
        migrate.upgrade(staged)  # an older backup is upgraded before the live database is touched
        with staged.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "bad_backup", "备份里的数据库结构、数据或迁移检查没有通过。") from exc
    finally:
        staged.dispose()
        reference.dispose()


def _validate_media(path: Path, manifest: dict, work: Path) -> None:
    files = {p.relative_to(work).as_posix(): p for p in (work / "media").rglob("*.webp")}
    if manifest.get("media_files") != len(files) or manifest.get("media_bytes") != sum(p.stat().st_size for p in files.values()):
        raise ApiError(422, "bad_backup", "备份里的图片数量或大小与清单不一致。")
    checksums = manifest.get("media_sha256")
    # Older archives have counts and database variant sizes, but no per-file checksum inventory.
    if checksums is not None and (not isinstance(checksums, dict) or set(checksums) != set(files)
                                  or any(_sha256(p) != checksums[name] for name, p in files.items())):
        raise ApiError(422, "bad_backup", "备份里的图片校验和不对。")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for media_hash, variants in con.execute("SELECT hash, variants FROM media"):
            variants = json.loads(variants)
            if not isinstance(variants, list) or not variants:
                raise ValueError("missing variants")
            for variant in variants:
                name = f"media/{media_hash[:2]}/{media_hash}/{variant['size']}.webp"
                if name not in files or files[name].stat().st_size != variant["bytes"]:
                    raise ValueError("missing or damaged media variant")
    except (ValueError, TypeError, KeyError) as exc:
        raise ApiError(422, "bad_backup", "备份缺少数据库记录的图片，或图片大小不对。") from exc
    finally:
        con.close()


def _restore_db(source: Path, target: Path) -> None:
    # Keep the same database file so other workers' SQLite connections still refer to it (including WAL).
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target, timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _swap_media(cfg: Config, new_media: Path) -> None:
    old = cfg.media_dir.with_name(f"media.old-{new_media.parent.name.removeprefix('.restore-')}")
    had_media = cfg.media_dir.exists()
    new_media.mkdir(parents=True, exist_ok=True)
    if had_media:
        cfg.media_dir.rename(old)
    try:
        shutil.move(str(new_media), str(cfg.media_dir))
    except Exception:
        if had_media:
            old.rename(cfg.media_dir)
        raise
    shutil.rmtree(old, ignore_errors=True)
    # On rollback failure the original directory stays outside the temporary work tree for manual recovery.
