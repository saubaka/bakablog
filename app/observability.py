"""Local rotating logs and request-level observability."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, g, has_request_context


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = str(g.get("request_id", "-")) if has_request_context() else "-"
        return True


def configure_logging(app: Flask) -> None:
    level = getattr(logging, str(app.config["LOG_LEVEL"]).upper(), logging.INFO)
    # Flask applications created in one process share the import-name logger.
    # Click's isolated CLI runner may leave that logger disabled after a command.
    app.logger.disabled = False
    app.logger.setLevel(level)
    for handler in list(app.logger.handlers):
        if getattr(handler, "cloud_diary_file_handler", False):
            app.logger.removeHandler(handler)
            handler.close()

    if not app.config.get("LOG_TO_FILE"):
        return

    log_path = Path(app.instance_path) / "logs" / "cloud-diary.log"
    handler = RotatingFileHandler(
        log_path,
        maxBytes=int(app.config["LOG_MAX_BYTES"]),
        backupCount=int(app.config["LOG_BACKUP_COUNT"]),
        encoding="utf-8",
    )
    handler.cloud_diary_file_handler = True  # type: ignore[attr-defined]
    handler.setLevel(level)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s request_id=%(request_id)s %(name)s %(message)s"
        )
    )
    app.logger.addHandler(handler)
    app.logger.info("application logging initialized env=%s", app.config["ENV_NAME"])
