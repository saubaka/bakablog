"""Consistent SQLite and local-media backup/restore services."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import stat
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from flask import current_app

from app.extensions import db


class BackupError(RuntimeError):
    """Raised when a backup archive is invalid or cannot be restored."""


def database_path() -> Path:
    uri = str(current_app.config["SQLALCHEMY_DATABASE_URI"])
    prefix = "sqlite:///"
    if not uri.startswith(prefix):
        raise BackupError("备份命令仅支持本地SQLite数据库。")
    return Path(uri.removeprefix(prefix)).resolve()


def check_database(path: Path | None = None) -> str:
    target = path or database_path()
    if not target.exists():
        raise BackupError("数据库文件不存在，请先运行迁移。")
    with closing(sqlite3.connect(target)) as connection:
        result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if result != "ok" or foreign_key_errors:
        raise BackupError(f"数据库完整性检查失败：{result}，外键错误{len(foreign_key_errors)}项。")
    return result


def create_site_backup(destination: Path | None = None) -> Path:
    source_db = database_path()
    check_database(source_db)
    backup_dir = Path(current_app.instance_path) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = (destination or backup_dir / f"cloud-diary-{timestamp}.zip").resolve()
    archive.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(dir=Path(current_app.instance_path) / "tmp") as temporary:
        snapshot = Path(temporary) / "site.db"
        db.session.remove()
        with (
            closing(sqlite3.connect(source_db)) as source,
            closing(sqlite3.connect(snapshot)) as target,
        ):
            source.execute("PRAGMA wal_checkpoint(PASSIVE)")
            source.backup(target)
        check_database(snapshot)

        uploads_root = Path(current_app.instance_path) / "uploads"
        files = sorted(path for path in uploads_root.rglob("*") if path.is_file())
        media_entries = [
            {
                "path": str(PurePosixPath("uploads") / path.relative_to(uploads_root)),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ]
        with closing(sqlite3.connect(snapshot)) as connection:
            migration_revision = (
                connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
                if _table_exists(connection, "alembic_version")
                else None
            )
        manifest = {
            "format": "cloud-diary-backup-v2",
            "created_at": datetime.now(UTC).isoformat(),
            "app_version": current_app.config["APP_VERSION"],
            "media_files": len(files),
            "migration_revision": migration_revision[0] if migration_revision else "",
            "database_sha256": _sha256(snapshot),
            "media": media_entries,
        }
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            bundle.write(snapshot, "database/site.db")
            for path in files:
                bundle.write(path, PurePosixPath("uploads") / path.relative_to(uploads_root))
    return archive


def verify_site_backup(archive: Path) -> dict[str, object]:
    """Validate archive paths, declared hashes and the contained SQLite snapshot."""

    archive = archive.resolve()
    if not archive.is_file():
        raise BackupError("指定的备份文件不存在。")
    instance_tmp = Path(current_app.instance_path) / "tmp"
    with TemporaryDirectory(dir=instance_tmp) as temporary:
        return _extract_and_verify(archive, Path(temporary))


def restore_site_backup(archive: Path) -> Path:
    archive = archive.resolve()
    if not archive.is_file():
        raise BackupError("指定的备份文件不存在。")

    instance_root = Path(current_app.instance_path)
    with TemporaryDirectory(dir=instance_root / "tmp") as temporary:
        extracted = Path(temporary)
        _extract_and_verify(archive, extracted)
        restored_db = extracted / "database" / "site.db"
        safety_timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safety_copy = create_site_backup(
            instance_root / "backups" / f"pre-restore-safety-{safety_timestamp}.zip"
        )

        db.session.remove()
        db.engine.dispose()
        live_db = database_path()
        live_db.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(f"{live_db}{suffix}").unlink(missing_ok=True)
        shutil.copy2(restored_db, live_db)

        restored_uploads = extracted / "uploads"
        live_uploads = instance_root / "uploads"
        staged_uploads = instance_root / "tmp" / "restored-uploads"
        if staged_uploads.exists():
            shutil.rmtree(staged_uploads)
        if restored_uploads.exists():
            shutil.copytree(restored_uploads, staged_uploads)
        else:
            staged_uploads.mkdir(parents=True)
        if live_uploads.exists():
            shutil.rmtree(live_uploads)
        staged_uploads.replace(live_uploads)
        check_database(live_db)
    return safety_copy


def _validate_archive_members(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        first_part = path.parts[0] if path.parts else ""
        if path.is_absolute() or ".." in path.parts or ":" in first_part:
            raise BackupError("备份中包含不安全路径。")


def _extract_and_verify(archive: Path, destination: Path) -> dict[str, object]:
    try:
        with ZipFile(archive) as bundle:
            infos = bundle.infolist()
            _validate_archive_infos(infos)
            names = [item.filename for item in infos]
            if "manifest.json" not in names or "database/site.db" not in names:
                raise BackupError("备份缺少清单或数据库快照。")
            try:
                manifest = json.loads(bundle.read("manifest.json"))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise BackupError("备份清单不是有效的JSON。") from error
            if manifest.get("format") not in {
                "cloud-diary-backup-v1",
                "cloud-diary-backup-v2",
            }:
                raise BackupError("备份格式不受支持。")
            bundle.extractall(destination)
    except BadZipFile as error:
        raise BackupError("备份文件不是有效的ZIP归档。") from error

    restored_db = destination / "database" / "site.db"
    check_database(restored_db)
    if manifest.get("format") == "cloud-diary-backup-v2":
        _verify_v2_manifest(manifest, destination, names)
    return manifest


def _validate_archive_infos(infos: list[ZipInfo]) -> None:
    if len(infos) > int(current_app.config["MAX_BACKUP_FILES"]):
        raise BackupError("备份文件数量超过安全限制。")
    names = [item.filename for item in infos]
    if len(names) != len(set(names)):
        raise BackupError("备份中包含重复路径。")
    _validate_archive_members(names)
    total_size = 0
    for info in infos:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.parts and path.parts[0] not in {"manifest.json", "database", "uploads"}:
            raise BackupError("备份中包含不受支持的文件路径。")
        if path.parts and path.parts[0] == "manifest.json" and len(path.parts) != 1:
            raise BackupError("备份清单路径无效。")
        if (
            path.parts
            and path.parts[0] == "database"
            and path.as_posix().rstrip("/")
            not in {
                "database",
                "database/site.db",
            }
        ):
            raise BackupError("备份数据库路径无效。")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise BackupError("备份中不允许符号链接。")
        if info.flag_bits & 0x1:
            raise BackupError("不支持加密的备份成员。")
        total_size += info.file_size
    if total_size > int(current_app.config["MAX_BACKUP_UNCOMPRESSED_BYTES"]):
        raise BackupError("备份解压后体积超过安全限制。")


def _verify_v2_manifest(
    manifest: dict[str, object], destination: Path, archive_names: list[str]
) -> None:
    database_hash = manifest.get("database_sha256")
    if not isinstance(database_hash, str) or database_hash != _sha256(
        destination / "database" / "site.db"
    ):
        raise BackupError("备份数据库哈希校验失败。")
    media = manifest.get("media")
    if not isinstance(media, list):
        raise BackupError("备份媒体清单无效。")
    declared: set[str] = set()
    for entry in media:
        if not isinstance(entry, dict):
            raise BackupError("备份媒体清单无效。")
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_size = entry.get("size")
        if not isinstance(relative, str) or not relative.startswith("uploads/"):
            raise BackupError("备份媒体路径无效。")
        if relative in declared:
            raise BackupError("备份媒体清单包含重复路径。")
        declared.add(relative)
        target = destination / PurePosixPath(relative)
        if (
            not target.is_file()
            or target.stat().st_size != expected_size
            or not isinstance(expected_hash, str)
            or _sha256(target) != expected_hash
        ):
            raise BackupError("备份媒体哈希校验失败。")
    archived_media = {name for name in archive_names if name.startswith("uploads/")}
    if archived_media != declared or manifest.get("media_files") != len(declared):
        raise BackupError("备份媒体清单与归档内容不一致。")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )
