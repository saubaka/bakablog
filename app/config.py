"""Configuration profiles for baka blog."""

from __future__ import annotations

from datetime import timedelta


class BaseConfig:
    APP_VERSION = "1.48.0"  # Setup page: opening entrance for the right-hand blocks plus the scroll reveal.
    SYSTEM_NAME = "sau_bakaの博客"
    SYSTEM_NAME_EN = "baka blog"
    SITE_NAME = "sau_bakaの博客"
    SITE_TAGLINE = "记录代码、设计与生活"
    CURRENT_YEAR = 2026
    SITE_URL = "http://127.0.0.1:5000"
    ENV_NAME = "base"
    DEFAULT_SECRET_KEY = "development-only-change-me"
    SECRET_KEY = DEFAULT_SECRET_KEY
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 512 * 1024
    MAX_FORM_PARTS = 100
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_COOKIE_NAME = "cloudtrace_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = False
    REMEMBER_COOKIE_NAME = "cloudtrace_remember"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    SESSION_PROTECTION = "strong"
    SEND_FILE_MAX_AGE_DEFAULT = 3600
    TEMPLATES_AUTO_RELOAD = False
    JSON_AS_ASCII = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 5},
        "pool_pre_ping": True,
    }
    SQLITE_BUSY_TIMEOUT_MS = 5_000
    MAX_MEDIA_FILE_SIZE = 8 * 1024 * 1024
    MAX_IMAGE_PIXELS = 24_000_000
    MEDIA_THUMBNAIL_SIZE = (640, 640)
    POSTS_PER_PAGE = 8
    SEARCH_RESULTS_PER_PAGE = 8
    ADMIN_MEDIA_PER_PAGE = 40
    SITE_CONTEXT_CACHE_SECONDS = 30
    HOME_CONTENT_CACHE_SECONDS = 15
    TEXT_COMPRESSION_MIN_BYTES = 1024
    TEXT_COMPRESSION_ENABLED = True
    INTERACTION_RATE_LIMIT = 5
    INTERACTION_RATE_WINDOW_SECONDS = 600
    LOGIN_RATE_LIMIT = 5
    LOGIN_RATE_WINDOW_SECONDS = 900
    HUMAN_CHECK_TTL_SECONDS = 300
    COMMENT_AUTO_APPROVE = False
    SPAM_KEYWORDS = ("博彩", "代开发票", "免费赚钱", "色情", "casino")
    # Flask-WTF passes this value to itsdangerous as ``max_age``. Current
    # itsdangerous versions require seconds rather than ``timedelta`` here.
    WTF_CSRF_TIME_LIMIT = 2 * 60 * 60
    WTF_CSRF_SSL_STRICT = True
    # Access is open by default. Host allowlists and HTTPS enforcement are
    # stored in SQLite and can be changed from the administration panel.
    TRUSTED_HOSTS = None
    # While no active superadministrator exists every visitor is sent to the
    # first-superadmin guidance instead of the public site.
    SETUP_REDIRECT_ENABLED = True
    ACCESS_POLICY_CACHE_SECONDS = 5
    TRUST_PROXY_HEADERS = False
    LOG_TO_FILE = False
    LOG_LEVEL = "INFO"
    LOG_MAX_BYTES = 5 * 1024 * 1024
    LOG_BACKUP_COUNT = 5
    LOG_REQUESTS = False
    SLOW_REQUEST_MS = 750
    HSTS_MAX_AGE = 31_536_000
    MAX_BACKUP_UNCOMPRESSED_BYTES = 10 * 1024 * 1024 * 1024
    MAX_BACKUP_FILES = 100_000
    UPDATE_MANIFEST_URL = (
        "https://raw.githubusercontent.com/saubaka/bakablog/main/updates/stable.json"
    )


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0
    LOG_TO_FILE = True


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    SETUP_REDIRECT_ENABLED = False
    SECRET_KEY = "testing-secret-key"
    SERVER_NAME = "localhost"
    WTF_CSRF_ENABLED = False
    HUMAN_CHECK_TEST_ANSWER = "BAKA"


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    SEND_FILE_MAX_AGE_DEFAULT = 31_536_000
    LOG_TO_FILE = True
    LOG_REQUESTS = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
