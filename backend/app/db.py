"""SQLite engine and per-request sessions.

- WAL, foreign keys on, a busy timeout. Python's sqlite3 module is told not to manage transactions itself
  (isolation_level=None) and SQLAlchemy emits BEGIN, so SAVEPOINTs and DDL behave.
- Requests that write (POST / PUT / PATCH / DELETE) start with BEGIN IMMEDIATE: with several gunicorn workers a deferred
  transaction that tries to upgrade to a write can fail at once with "database is locked", an immediate one waits its turn.
- One unit of work per request: a write request commits when the handler finishes with a status below 400, otherwise it
  rolls back (see init_app).
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from pathlib import Path

from flask import Flask, current_app, g, has_request_context, request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def make_engine(db_path: Path, echo: bool = False) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=echo, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        immediate = conn.get_execution_options().get("sqlite_immediate", False)
        conn.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine


class Database:
    """Holds the engine and the two session factories (read = deferred transactions, write = immediate)."""

    def __init__(self, db_path: Path, echo: bool = False):
        self.engine = make_engine(db_path, echo=echo)
        self.read = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.write = sessionmaker(bind=self.engine.execution_options(sqlite_immediate=True), expire_on_commit=False)

    def dispose(self) -> None:
        self.engine.dispose()


def database() -> Database:
    return current_app.extensions["bb_db"]


def db() -> Session:
    """The session of the current request (created on first use)."""
    session = g.get("_db")
    if session is None:
        d = database()
        factory = d.write if has_request_context() and request.method in UNSAFE_METHODS else d.read
        session = g._db = factory()
    return session


@contextlib.contextmanager
def session_scope(app: Flask | None = None, *, write: bool = True) -> Iterator[Session]:
    """A session outside a request (CLI, maintenance jobs, tests): commits on success, rolls back on error."""
    app = app or current_app._get_current_object()
    d: Database = app.extensions["bb_db"]
    session = (d.write if write else d.read)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def init_app(app: Flask, db_path: Path, echo: bool = False) -> Database:
    database_ = Database(db_path, echo=echo)
    app.extensions["bb_db"] = database_

    @app.after_request
    def _commit(response):
        session = g.get("_db")
        if session is not None and request.method in UNSAFE_METHODS:
            if response.status_code < 400:
                try:
                    session.commit()
                except Exception:  # noqa: BLE001 - turn a failed commit into a clean 500 instead of a half-written response
                    log.exception("commit failed")
                    session.rollback()
                    from app.errors import error_response

                    return error_response(500, "commit_failed", "保存失败，改动没有生效。")
                for callback in g.pop("_after_commit", []):
                    try:
                        callback()
                    except Exception:  # noqa: BLE001 - cleanup must never turn a saved request into an error
                        log.exception("after-commit callback failed")
            else:
                session.rollback()
        return response

    @app.teardown_appcontext
    def _close(_exc):
        session = g.pop("_db", None)
        if session is not None:
            session.rollback()
            session.close()

    return database_


def after_commit(callback) -> None:
    """Run `callback()` once this request's transaction has been committed (e.g. delete the files of a replaced picture)."""
    g.setdefault("_after_commit", []).append(callback)
