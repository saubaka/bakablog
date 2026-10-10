from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.extensions import db
from app.models import User
from app.services.backup import (
    BackupError,
    check_database,
    create_site_backup,
    restore_site_backup,
    verify_site_backup,
)


def test_database_check_and_combined_backup(app, admin_user):
    with app.app_context():
        assert check_database() == "ok"
        archive = create_site_backup()
        assert archive.is_file()
        with ZipFile(archive) as bundle:
            assert "database/site.db" in bundle.namelist()
            manifest = json.loads(bundle.read("manifest.json"))
            assert manifest["format"] == "cloud-diary-backup-v2"
            assert manifest["app_version"] == "1.48.0"
            assert len(manifest["database_sha256"]) == 64
        verified = verify_site_backup(archive)
        assert verified["format"] == "cloud-diary-backup-v2"


def test_combined_backup_can_restore_database_and_media(app, admin_user):
    with app.app_context():
        user = db.session.get(User, admin_user)
        user.display_name = "备份中的名称"
        db.session.commit()
        upload = Path(app.instance_path) / "uploads"
        marker = upload / "restore-marker.txt"
        marker.write_text("backup-content", encoding="utf-8")
        archive = create_site_backup()

        user = db.session.get(User, admin_user)
        user.display_name = "备份之后的名称"
        db.session.commit()
        marker.write_text("changed-content", encoding="utf-8")

        safety_copy = restore_site_backup(archive)
        assert safety_copy.is_file()
        restored = db.session.get(User, admin_user)
        assert restored.display_name == "备份中的名称"
        assert marker.read_text(encoding="utf-8") == "backup-content"


@pytest.mark.parametrize("unsafe_name", ["../outside.txt", "..\\outside.txt", "C:/outside.txt"])
def test_restore_rejects_unsafe_archive_paths(app, unsafe_name):
    archive = Path(app.instance_path) / "tmp" / "unsafe.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"format": "cloud-diary-backup-v1"}))
        bundle.writestr("database/site.db", b"not-used")
        bundle.writestr(unsafe_name, b"blocked")
    with app.app_context(), pytest.raises(BackupError, match="不安全路径"):
        restore_site_backup(archive)


def test_backup_verification_rejects_tampered_media(app, admin_user):
    with app.app_context():
        marker = Path(app.instance_path) / "uploads" / "tamper-probe.txt"
        marker.write_text("original", encoding="utf-8")
        archive = create_site_backup()
        tampered = Path(app.instance_path) / "tmp" / "tampered.zip"
        with ZipFile(archive) as source, ZipFile(tampered, "w") as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "uploads/tamper-probe.txt":
                    data = b"changed"
                target.writestr(info, data)
        with pytest.raises(BackupError, match="哈希校验失败"):
            verify_site_backup(tampered)
