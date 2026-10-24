from __future__ import annotations

import logging
import re
import shutil

import pytest

from app import create_app, migrate
from app.config import Config, ConfigError, load_config, load_env_file
from app.db import Database, session_scope
from app.services import auth
from tests.conftest import make_config


# ---- configuration -----------------------------------------------------------------------------------------------------------------------
def test_production_refuses_to_start_without_a_real_secret(tmp_path):
    base = {"BLOG_ENV": "production", "BLOG_DATA_DIR": str(tmp_path), "BLOG_SITE_URL": "https://blog.example"}
    for bad in ("", "short", "change-me", "x" * 31):
        with pytest.raises(ConfigError, match="BLOG_SECRET_KEY"):
            load_config({}, {**base, "BLOG_SECRET_KEY": bad})
    cfg = load_config({}, {**base, "BLOG_SECRET_KEY": "s" * 40})
    assert cfg.production and cfg.cookie_secure is True and cfg.secret_key == "s" * 40


def test_production_needs_the_canonical_address(tmp_path):
    """Feeds, the sitemap and canonical links must not depend on the Host header a visitor sends."""
    with pytest.raises(ConfigError, match="BLOG_SITE_URL"):
        load_config({}, {"BLOG_ENV": "production", "BLOG_DATA_DIR": str(tmp_path), "BLOG_SECRET_KEY": "s" * 40})


def test_defaults_per_environment(tmp_path):
    dev = load_config({}, {"BLOG_DATA_DIR": str(tmp_path / "dev")})
    assert dev.env == "development" and dev.cookie_secure is False and len(dev.secret_key) >= 32
    assert load_config({}, {"BLOG_DATA_DIR": str(tmp_path / "dev")}).secret_key == dev.secret_key  # the dev secret is stable between starts
    assert (tmp_path / "dev" / ".dev-secret").stat().st_mode & 0o777 == 0o600
    test = load_config({}, {"BLOG_ENV": "testing", "BLOG_DATA_DIR": str(tmp_path / "t")})
    assert test.testing and test.log_level == "WARNING"


def test_config_values_are_validated(tmp_path):
    env = {"BLOG_ENV": "testing", "BLOG_DATA_DIR": str(tmp_path)}
    with pytest.raises(ConfigError):
        load_config({}, {**env, "BLOG_ENV": "staging"})
    with pytest.raises(ConfigError, match="BLOG_SITE_URL"):
        load_config({}, {**env, "BLOG_SITE_URL": "blog.example"})
    with pytest.raises(ConfigError, match="BLOG_MAX_UPLOAD_MB"):
        load_config({}, {**env, "BLOG_MAX_UPLOAD_MB": "lots"})
    cfg = load_config({}, {**env, "BLOG_SITE_URL": "https://blog.example/", "BLOG_MAX_UPLOAD_MB": "2.5", "BLOG_TRUST_PROXY": "2", "BLOG_SETUP_TOKEN": " abc "})
    assert cfg.site_url == "https://blog.example" and cfg.max_upload_bytes == int(2.5 * 1024 * 1024) and cfg.trust_proxy == 2 and cfg.setup_token == "abc"
    assert cfg.db_path == tmp_path.resolve() / "blog.sqlite" and cfg.media_dir == tmp_path.resolve() / "media" and cfg.backup_dir == tmp_path.resolve() / "backups"
    assert load_config({}, {**env, "BLOG_DB_PATH": str(tmp_path / "x" / "other.db")}).db_path == tmp_path / "x" / "other.db"
    assert isinstance(cfg, Config) and cfg.with_overrides(trust_proxy=0).trust_proxy == 0


def test_env_file_loader_never_overrides_the_real_environment(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nBLOG_ENV=production\nBLOG_SITE_URL='https://from-file.example'\n\nNOT A LINE\nBLOG_LOG_LEVEL = debug \n", encoding="utf-8")
    env = {"BLOG_ENV": "development"}
    load_env_file(f, env)
    assert env == {"BLOG_ENV": "development", "BLOG_SITE_URL": "https://from-file.example", "BLOG_LOG_LEVEL": "debug"}
    load_env_file(tmp_path / "missing.env", env)  # no file: nothing happens


# ---- start-up ------------------------------------------------------------------------------------------------------------------------------
def test_development_start_creates_and_migrates_the_database(tmp_path, caplog):
    cfg = load_config({}, {"BLOG_ENV": "development", "BLOG_DATA_DIR": str(tmp_path)}).with_overrides(scrypt_n=2**10)
    assert not cfg.db_path.exists()
    with caplog.at_level(logging.INFO):
        app = create_app(cfg)
    assert cfg.db_path.exists() and migrate.current_revision(app.extensions["bb_db"]) == migrate.head_revision()
    assert app.test_client().get("/api/health").status_code == 200
    app.extensions["bb_db"].dispose()


def test_the_setup_token_is_printed_once_and_stops_when_an_owner_exists(tmp_path, caplog):
    cfg = load_config({}, {"BLOG_ENV": "development", "BLOG_DATA_DIR": str(tmp_path)}).with_overrides(scrypt_n=2**10)
    with caplog.at_level(logging.WARNING):
        app = create_app(cfg)
    printed = re.findall(r"setup token.*: (\S+)", caplog.text)
    assert len(printed) == 1 and len(printed[0]) >= 20
    token_file = tmp_path / "setup-token.txt"  # development only: also kept in a private file, so no one has to dig it out of a log
    assert token_file.read_text(encoding="utf-8").strip() == printed[0] and token_file.stat().st_mode & 0o777 == 0o600
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        second = create_app(cfg)  # another worker / a restart: the token already exists, nothing is printed
    assert "setup token" not in caplog.text
    api = app.test_client()
    r = api.post("/api/admin/auth/setup", json={"token": printed[0], "username": "first_owner", "password": "correct horse battery"})
    assert r.status_code == 201
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        third = create_app(cfg)
    assert "setup token" not in caplog.text and not token_file.exists()  # once an owner exists the token file goes away
    for a in (app, second, third):
        a.extensions["bb_db"].dispose()


def test_production_start_does_not_migrate_and_does_not_crash_without_tables(tmp_path, caplog):
    cfg = load_config({}, {"BLOG_ENV": "production", "BLOG_SECRET_KEY": "k" * 40, "BLOG_DATA_DIR": str(tmp_path), "BLOG_SITE_URL": "https://blog.example"}).with_overrides(scrypt_n=2**10)
    with caplog.at_level(logging.WARNING):
        app = create_app(cfg)
    assert "not initialised" in caplog.text
    assert migrate.current_revision(app.extensions["bb_db"]) is None  # production leaves migrations to the deploy script
    app.extensions["bb_db"].dispose()


# ---- CLI -----------------------------------------------------------------------------------------------------------------------------------
def test_cli_init_db_and_setup_token(tmp_path):
    cfg = make_config(tmp_path)
    app = create_app(cfg)
    runner = app.test_cli_runner()
    r = runner.invoke(args=["init-db"])
    assert r.exit_code == 0 and "0001" in r.output
    r = runner.invoke(args=["setup-token"])
    assert r.exit_code == 0 and r.output.startswith("setup token: ")
    token = r.output.split(": ")[1].strip()
    with session_scope(app) as s:
        assert auth.check_setup_token(s, token)
        auth.create_owner(s, "cli_owner", "correct horse battery", cfg)
    refused = runner.invoke(args=["setup-token"])
    assert refused.exit_code != 0 and "already exists" in refused.output
    app.extensions["bb_db"].dispose()


def test_cli_backup_maintenance_and_routes(app, cfg):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["backup"])
    assert r.exit_code == 0 and "backup-" in r.output and list(cfg.backup_dir.glob("backup-*-manual.tar.gz"))
    r = runner.invoke(args=["backup", "--label", "pre-deploy"])
    assert r.exit_code == 0 and "-pre-deploy.tar.gz" in r.output and list(cfg.backup_dir.glob("backup-*-pre-deploy.tar.gz"))
    r = runner.invoke(args=["maintenance"])
    assert r.exit_code == 0 and '"backup"' in r.output
    r = runner.invoke(args=["maintenance", "--job", "reindex"])
    assert r.exit_code == 0 and '"post": 0' in r.output
    r = runner.invoke(args=["maintenance", "--job", "backup", "--force"])
    assert r.exit_code == 0 and "-manual.tar.gz" in r.output
    r = runner.invoke(args=["routes-table"])
    assert r.exit_code == 0 and "/api/posts" in r.output and "/api/admin/posts" in r.output


def test_cli_restore_replaces_the_data_and_keeps_a_way_back(app, cfg, admin, tmp_path):
    from tests.conftest import make_post

    make_post(admin, "备份时有的")
    runner = app.test_cli_runner()
    name = runner.invoke(args=["backup"]).output.split()[0]
    make_post(admin, "备份之后才有的")
    assert admin.get("/api/admin/posts").get_json()["total"] == 2
    r = runner.invoke(args=["restore", str(cfg.backup_dir / name)], input="n\n")
    assert r.exit_code != 0 and admin.get("/api/admin/posts").get_json()["total"] == 2          # asked, and "no" changed nothing
    r = runner.invoke(args=["restore", str(cfg.backup_dir / name), "--yes"])
    assert r.exit_code == 0 and "pre-restore" in r.output, r.output
    with session_scope(app, write=False) as s:
        from sqlalchemy import func, select

        from app.models import Post

        assert s.scalar(select(func.count()).select_from(Post)) == 1
    assert list(cfg.backup_dir.glob("*-pre-restore.tar.gz"))
    bad = tmp_path / "bad.tar.gz"
    bad.write_bytes(b"not a backup")
    r = runner.invoke(args=["restore", str(bad), "--yes"])
    assert r.exit_code != 0 and "备份" in r.output


def test_cli_doctor_passes_on_a_good_install_and_names_what_is_wrong(tmp_path, template_db):
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in ("public.html", "admin.html", "preview.html"):
        (dist / name).write_text("<!doctype html>", encoding="utf-8")
    cfg = make_config(tmp_path / "site", frontend_dist=dist)
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_db, cfg.db_path)
    app = create_app(cfg)
    try:
        runner = app.test_cli_runner()
        r = runner.invoke(args=["doctor"])
        assert r.exit_code == 0 and "all good" in r.output and "database is at the latest revision" in r.output, r.output
        assert "administrator: not yet" in r.output
        (dist / "preview.html").unlink()
        r = runner.invoke(args=["doctor"])
        assert r.exit_code != 0 and "preview.html" in r.output and "FAIL" in r.output
    finally:
        app.extensions["bb_db"].dispose()
    behind = make_config(tmp_path / "behind", frontend_dist=dist)          # a database nobody migrated
    app2 = create_app(behind)
    try:
        r = app2.test_cli_runner().invoke(args=["doctor"])
        assert r.exit_code != 0 and "latest revision" in r.output
    finally:
        app2.extensions["bb_db"].dispose()


# ---- migrations -----------------------------------------------------------------------------------------------------------------------------
def test_migrations_can_go_down_and_up_again(tmp_path):
    db = Database(tmp_path / "m.sqlite")
    try:
        migrate.upgrade(db)
        assert migrate.current_revision(db) == "0001"
        with db.engine.connect() as c:
            tables = {r[0] for r in c.exec_driver_sql("select name from sqlite_master where type in ('table','trigger')")}
        assert {"posts", "moments", "search_fts", "audit_logs_no_update", "audit_logs_keep_year"} <= tables
        migrate.downgrade(db)
        with db.engine.connect() as c:
            left = {r[0] for r in c.exec_driver_sql("select name from sqlite_master where type in ('table','trigger')")}
        assert left == {"alembic_version"}
        migrate.upgrade(db)
        assert migrate.current_revision(db) == "0001"
    finally:
        db.dispose()


def test_migration_files_do_not_depend_on_application_code():
    from pathlib import Path

    for path in (Path(__file__).resolve().parent.parent / "migrations" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+app\b", text, re.M), path.name


def test_template_copy_is_independent(template_db, tmp_path):
    copy = tmp_path / "x.sqlite"
    shutil.copyfile(template_db, copy)
    db = Database(copy)
    try:
        assert migrate.current_revision(db) == migrate.head_revision()
    finally:
        db.dispose()
