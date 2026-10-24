"""Damaged backups must be rejected before touching live data; final switch failures must undo themselves."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile

import pytest

from app.errors import ApiError
from app.services import backup
from tests.conftest import make_post
from tests.test_system import A, S, create_backup, read_archive


def write_archive(path, files):
    with tarfile.open(path, 'w:gz') as tar:
        for name, raw in files:
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return path


def pictures(cfg):
    return {p.relative_to(cfg.media_dir).as_posix(): p.read_bytes() for p in cfg.media_dir.rglob('*.webp')}


@pytest.mark.parametrize('damage', ['missing-media', 'false-empty-media', 'media-bytes', 'media-checksum', 'wrong-revision', 'missing-table', 'missing-trigger', 'missing-index', 'bad-manifest', 'duplicate'])
def test_invalid_restore_preserves_live_database_and_pictures(admin, app, cfg, png, tmp_path, damage):
    admin.upload(f'{A}/media', png(700, 500))
    make_post(admin, 'backup version')
    info = create_backup(admin)
    files = read_archive(cfg, info['name'])
    manifest = json.loads(files['manifest.json'])
    if damage in ('missing-media', 'false-empty-media'):
        files = {name: raw for name, raw in files.items() if not name.startswith('media/')}
        if damage == 'false-empty-media':
            manifest.update(media_files=0, media_bytes=0, media_sha256={})
    elif damage in ('media-bytes', 'media-checksum'):
        name = next(name for name in files if name.startswith('media/'))
        files[name] = b'x' * len(files[name]) if damage == 'media-checksum' else b'x'
    elif damage in ('wrong-revision', 'missing-table', 'missing-trigger', 'missing-index'):
        path = tmp_path / 'tampered.sqlite'
        path.write_bytes(files['db.sqlite'])
        con = sqlite3.connect(path)
        if damage == 'wrong-revision':
            con.execute("UPDATE alembic_version SET version_num='unknown'")
        elif damage == 'missing-table':
            con.execute('DROP TABLE posts')
        else:
            kind = 'trigger' if damage == 'missing-trigger' else 'index'
            name = con.execute('SELECT name FROM sqlite_master WHERE type=? AND sql IS NOT NULL LIMIT 1', (kind,)).fetchone()[0]
            con.execute(f'DROP {kind} "{name}"')  # noqa: S608 - SQLite's own schema name in this isolated fixture
        con.commit()
        con.close()
        files['db.sqlite'] = path.read_bytes()
        manifest.update(db_sha256=hashlib.sha256(files['db.sqlite']).hexdigest(), db_bytes=len(files['db.sqlite']))
    files['manifest.json'] = json.dumps([] if damage == 'bad-manifest' else manifest).encode()
    entries = list(files.items())
    if damage == 'duplicate':
        entries.append(('db.sqlite', files['db.sqlite']))
    archive = write_archive(tmp_path / 'invalid.tar.gz', entries)
    # The live state differs from the backup, so replacing it and then raising is detectable.
    make_post(admin, 'must survive')
    before = pictures(cfg)
    backups = {p.name for p in cfg.backup_dir.iterdir()}
    r = admin.post(f'{S}/restore', data={'file': (io.BytesIO(archive.read_bytes()), 'invalid.tar.gz'), 'confirm': 'restore'}, content_type='multipart/form-data')
    assert r.status_code == 422, r.get_json()
    assert pictures(cfg) == before
    assert {p.name for p in cfg.backup_dir.iterdir()} == backups
    assert {p['title'] for p in admin.get(f'{A}/posts').get_json()['items']} == {'backup version', 'must survive'}
    assert not list(cfg.data_dir.glob('.restore-*'))


def test_legacy_backup_without_media_checksums_remains_restorable(admin, app, cfg, png, tmp_path):
    admin.upload(f'{A}/media', png(700, 500))
    make_post(admin, 'legacy')
    files = read_archive(cfg, create_backup(admin)['name'])
    manifest = json.loads(files['manifest.json'])
    del manifest['media_sha256']
    files['manifest.json'] = json.dumps(manifest).encode()
    archive = write_archive(tmp_path / 'legacy.tar.gz', files.items())
    make_post(admin, 'later')
    backup.restore(app, archive)
    assert [p['title'] for p in admin.get(f'{A}/posts').get_json()['items']] == ['legacy']


def test_media_switch_failure_restores_current_database_and_media(admin, app, cfg, png, monkeypatch):
    admin.upload(f'{A}/media', png(700, 500, (1, 2, 3)))
    make_post(admin, 'backup version')
    archive = cfg.backup_dir / create_backup(admin)['name']
    make_post(admin, 'live version')
    admin.upload(f'{A}/media', png(700, 500, (8, 9, 10)))
    before = pictures(cfg)

    def fail_move(*args, **kwargs):
        raise OSError('injected failure after original media directory was renamed')

    monkeypatch.setattr(backup.shutil, 'move', fail_move)
    with pytest.raises(OSError, match='injected failure'):
        backup.restore(app, archive)
    assert pictures(cfg) == before
    assert {p['title'] for p in admin.get(f'{A}/posts').get_json()['items']} == {'backup version', 'live version'}
    assert any(b.label == 'pre-restore' for b in backup.list_backups(cfg))


def test_migration_failure_happens_only_in_staging(admin, app, cfg, monkeypatch):
    make_post(admin, 'backup version')
    archive = cfg.backup_dir / create_backup(admin)['name']
    make_post(admin, 'live version')
    real_upgrade = backup.migrate.upgrade

    def fail_staged(database, revision='head'):
        if revision == 'head':
            raise RuntimeError('injected migration failure')
        return real_upgrade(database, revision)

    monkeypatch.setattr(backup.migrate, 'upgrade', fail_staged)
    with pytest.raises(ApiError) as caught:
        backup.restore(app, archive)
    assert caught.value.code == 'bad_backup'
    assert {p['title'] for p in admin.get(f'{A}/posts').get_json()['items']} == {'backup version', 'live version'}
    assert not any(b.label == 'pre-restore' for b in backup.list_backups(cfg))


def test_database_switch_failure_restores_live_contents(admin, app, cfg, monkeypatch):
    make_post(admin, 'backup version')
    archive = cfg.backup_dir / create_backup(admin)['name']
    make_post(admin, 'live version')
    original_copy = backup._restore_db
    calls = 0

    def fail_after_copy(source, target):
        nonlocal calls
        original_copy(source, target)
        calls += 1
        if calls == 1:
            raise OSError('injected failure after database copy')

    monkeypatch.setattr(backup, '_restore_db', fail_after_copy)
    with pytest.raises(OSError, match='injected failure'):
        backup.restore(app, archive)
    assert calls == 2
    assert {p['title'] for p in admin.get(f'{A}/posts').get_json()['items']} == {'backup version', 'live version'}


def test_backup_metadata_describes_the_database_snapshot(admin, app, cfg, monkeypatch):
    make_post(admin, 'in snapshot')
    original_copy = backup._copy_db

    def copy_then_write(source, target):
        original_copy(source, target)
        make_post(admin, 'written after snapshot')

    monkeypatch.setattr(backup, '_copy_db', copy_then_write)
    info = backup.create(cfg, app.extensions['bb_db'])
    manifest = json.loads(read_archive(cfg, info.name)['manifest.json'])
    assert manifest['counts']['posts'] == 1
    assert len(admin.get(f'{A}/posts').get_json()['items']) == 2


def test_failed_media_rollback_keeps_original_pictures_outside_temporary_work(admin, app, cfg, png, monkeypatch):
    from pathlib import Path

    admin.upload(f'{A}/media', png(700, 500))
    archive = cfg.backup_dir / create_backup(admin)['name']
    before = pictures(cfg)
    original_rename = Path.rename

    def refuse_undo(path, target):
        if path.name.startswith('media.old-'):
            raise OSError('injected failure undoing media rename')
        return original_rename(path, target)

    def refuse_move(*args, **kwargs):
        raise OSError('injected media switch failure')

    monkeypatch.setattr(Path, 'rename', refuse_undo)
    monkeypatch.setattr(backup.shutil, 'move', refuse_move)
    with pytest.raises(OSError, match='undoing media rename'):
        backup.restore(app, archive)
    retained = list(cfg.data_dir.glob('media.old-*'))
    assert len(retained) == 1
    assert {p.relative_to(retained[0]).as_posix(): p.read_bytes() for p in retained[0].rglob('*.webp')} == before
    assert not list(cfg.data_dir.glob('.restore-*'))
