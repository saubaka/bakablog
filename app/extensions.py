"""Application extension registry and SQLite connection policy."""

from __future__ import annotations

import sqlite3

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate(compare_type=True, render_as_batch=True)
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "admin.login"
login_manager.login_message = "请先登录，再进入管理后台。"
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    """Apply safety and concurrency pragmas to every SQLite connection."""

    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA cache_size=-8192")
    cursor.close()
