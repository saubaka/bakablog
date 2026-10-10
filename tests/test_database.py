from __future__ import annotations

import threading
import time

from app.extensions import db


def test_sqlite_pragmas_are_enabled(app):
    with app.app_context():
        connection = db.engine.raw_connection()
        try:
            cursor = connection.cursor()
            assert cursor.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert cursor.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert cursor.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        finally:
            connection.close()


def test_waiting_writer_succeeds_without_data_loss(app):
    with app.app_context():
        engine = db.engine
        first = engine.raw_connection()
        first.execute("CREATE TABLE IF NOT EXISTS concurrency_probe (value INTEGER NOT NULL)")
        first.commit()
        first.execute("BEGIN IMMEDIATE")
        first.execute("INSERT INTO concurrency_probe(value) VALUES (1)")
        outcome: list[str] = []

        def second_writer() -> None:
            second = engine.raw_connection()
            try:
                second.execute("INSERT INTO concurrency_probe(value) VALUES (2)")
                second.commit()
                outcome.append("committed")
            finally:
                second.close()

        thread = threading.Thread(target=second_writer)
        thread.start()
        time.sleep(0.12)
        first.commit()
        thread.join(timeout=3)
        first.close()

        assert outcome == ["committed"]
        values = (
            db.session.execute(db.text("SELECT value FROM concurrency_probe ORDER BY value"))
            .scalars()
            .all()
        )
        assert values == [1, 2]
