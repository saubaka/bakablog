"""The blog application: Flask application factory."""
from __future__ import annotations

import logging

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config, load_config
from app.version import __version__, build_id

log = logging.getLogger("bakablog")


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=cfg.secret_key,
        MAX_CONTENT_LENGTH=cfg.max_upload_bytes + 2 * 1024 * 1024,  # the upload plus multipart overhead
        JSON_AS_ASCII=False,
    )
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.url_map.merge_slashes = False  # Werkzeug's "//x//" -> redirect would otherwise treat the first segment as a host name
    app.extensions["bb_config"] = cfg
    if cfg.trust_proxy:
        n = cfg.trust_proxy
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)  # type: ignore[method-assign]

    from app import db, errors, migrate, security

    database = db.init_app(app, cfg.db_path)
    errors.register(app)
    security.register(app, cfg)

    from app.api import register_blueprints

    register_blueprints(app)

    from app import cli

    cli.register(app)
    cli.register_more(app)

    if cfg.env == "development":
        try:
            if migrate.ensure_current(database):
                log.info("database upgraded to %s", migrate.head_revision())
        except Exception:  # noqa: BLE001
            log.exception("could not prepare the database")
    if not cfg.testing:
        _announce_setup(app, cfg)
    log.info("blog %s (%s) started in %s mode", __version__, build_id(), cfg.env)
    return app


def _announce_setup(app: Flask, cfg: Config) -> None:
    """First run: print the one-time setup token (once, by whichever worker creates it)."""
    from sqlalchemy.exc import OperationalError

    from app.db import session_scope
    from app.services import auth

    try:
        with session_scope(app) as session:
            token = auth.ensure_setup_token(session, cfg)
            has_owner = auth.owner_exists(session)
    except OperationalError:
        log.warning("database is not initialised yet: run `flask --app app init-db`")
        return
    if has_owner:
        remove_dev_token_file(cfg)
    if token:
        log.warning("=" * 72)
        log.warning("First run: open /admin/setup and create the administrator.")
        log.warning("One-time setup token (shown only now; `flask --app app setup-token` makes a new one): %s", token)
        log.warning("=" * 72)
        write_dev_token_file(cfg, token)


def _dev_token_file(cfg: Config):
    return cfg.data_dir / "setup-token.txt"


def write_dev_token_file(cfg: Config, token: str) -> None:
    """Development only: the token is also kept in a 0600 file next to the data, so it does not have to be fished out of a log."""
    if cfg.env != "development":
        return
    path = _dev_token_file(cfg)
    try:
        path.write_text(token + "\n", encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        log.warning("could not write %s", path)


def remove_dev_token_file(cfg: Config) -> None:
    _dev_token_file(cfg).unlink(missing_ok=True)
