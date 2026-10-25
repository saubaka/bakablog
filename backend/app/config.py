"""Configuration, read from environment variables (prefix BLOG_). A production start refuses to run without a real secret."""
from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

ENVS = ("development", "production", "testing")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    env: str = "development"
    secret_key: str = ""
    data_dir: Path = BACKEND_DIR / "data"
    db_path: Path = BACKEND_DIR / "data" / "blog.sqlite"
    media_dir: Path = BACKEND_DIR / "data" / "media"
    backup_dir: Path = BACKEND_DIR / "data" / "backups"
    site_url: str = ""                      # canonical origin without trailing slash; empty = use the request's own host
    frontend_dist: Path | None = None       # built Vue app (public.html / admin.html); None = built-in placeholder shell
    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 50_000_000      # width * height; larger uploads are refused before they are decoded
    max_image_side: int = 12_000
    max_animation_frames: int = 200
    cookie_secure: bool = False
    trust_proxy: int = 0                    # how many reverse proxies set X-Forwarded-*
    setup_token: str | None = None          # preset one-time setup token (otherwise one is generated and printed once)
    scrypt_n: int = 2**15                   # password hashing cost; tests lower it
    session_days: int = 30
    login_max_failures: int = 5             # per user name, inside login_window_minutes
    login_ip_max_failures: int = 20         # per address prefix
    login_window_minutes: int = 15
    log_level: str = "INFO"
    http_fetch_timeout: float = 5.0         # link-card fetching
    extra: dict = field(default_factory=dict)

    @property
    def testing(self) -> bool:
        return self.env == "testing"

    @property
    def production(self) -> bool:
        return self.env == "production"

    def with_overrides(self, **kw) -> Config:
        return replace(self, **kw)


def load_env_file(path: Path, environ: dict | None = None) -> None:
    """Minimal KEY=VALUE reader for backend/.env. Real environment variables win."""
    target = os.environ if environ is None else environ
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in target:
            target[key] = value


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _dev_secret(data_dir: Path) -> str:
    """Development and tests get a stable random secret kept next to the data, so preview links survive restarts."""
    path = data_dir / ".dev-secret"
    try:
        value = path.read_text(encoding="utf-8").strip()
        if len(value) >= 32:
            return value
    except OSError:
        pass
    value = secrets.token_urlsafe(48)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        pass
    return value


def load_config(overrides: Mapping | None = None, environ: Mapping | None = None) -> Config:
    if environ is None:
        load_env_file(BACKEND_DIR / ".env")
        environ = os.environ
    get = environ.get
    env = (get("BLOG_ENV") or "development").strip().lower()
    if env not in ENVS:
        raise ConfigError(f"BLOG_ENV must be one of {ENVS}, got {env!r}")

    data_dir = Path(get("BLOG_DATA_DIR") or (BACKEND_DIR / "data")).expanduser().resolve()
    db_path = Path(get("BLOG_DB_PATH") or data_dir / "blog.sqlite").expanduser().resolve()

    secret = (get("BLOG_SECRET_KEY") or "").strip()
    if env == "production":
        if len(secret) < 32 or secret.lower() in ("change-me", "changeme"):
            raise ConfigError("BLOG_SECRET_KEY must be set to a random string of at least 32 characters in production")
    elif not secret:
        secret = "testing-secret-not-for-production-0123456789" if env == "testing" else _dev_secret(data_dir)

    site_url = (get("BLOG_SITE_URL") or "").strip().rstrip("/")
    if site_url and not site_url.startswith(("http://", "https://")):
        raise ConfigError("BLOG_SITE_URL must start with http:// or https://")
    if env == "production" and not site_url:
        raise ConfigError("BLOG_SITE_URL must be set in production (the sitemap and canonical links must not depend on the Host header)")

    dist = get("BLOG_FRONTEND_DIST")
    frontend_dist = Path(dist).expanduser().resolve() if dist else (REPO_DIR / "frontend" / "dist")
    if not frontend_dist.is_dir():
        frontend_dist = None

    try:
        upload_mb = float(get("BLOG_MAX_UPLOAD_MB") or 12)
    except ValueError as exc:
        raise ConfigError("BLOG_MAX_UPLOAD_MB must be a number") from exc

    cfg = Config(
        env=env,
        secret_key=secret,
        data_dir=data_dir,
        db_path=db_path,
        media_dir=data_dir / "media",
        backup_dir=data_dir / "backups",
        site_url=site_url,
        frontend_dist=frontend_dist,
        max_upload_bytes=int(upload_mb * 1024 * 1024),
        cookie_secure=_truthy(get("BLOG_COOKIE_SECURE"), default=env == "production"),
        trust_proxy=int(get("BLOG_TRUST_PROXY") or 0),
        setup_token=(get("BLOG_SETUP_TOKEN") or "").strip() or None,
        log_level=(get("BLOG_LOG_LEVEL") or ("WARNING" if env == "testing" else "INFO")).upper(),
    )
    if overrides:
        cfg = cfg.with_overrides(**dict(overrides))
    return cfg


def cfg() -> Config:
    """The configuration of the running app (inside a request or an app context)."""
    from flask import current_app

    return current_app.extensions["bb_config"]
