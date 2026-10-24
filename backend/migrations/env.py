"""Alembic environment: the database is the one the app is configured for (or -x db=PATH, or a connection handed in by code)."""
from logging.config import fileConfig
from pathlib import Path

from alembic import context

from app.config import load_config
from app.db import make_engine
from app.migrate import include_object, render_item
from app.models import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError("offline mode is not supported (SQLite needs a live connection for batch migrations)")


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    engine = None
    if connection is None:
        override = context.get_x_argument(as_dictionary=True).get("db")
        path = Path(override) if override else load_config().db_path
        engine = make_engine(path)
        connection = engine.connect()
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_item=render_item,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        if engine is not None:
            connection.commit()
    finally:
        if engine is not None:
            connection.close()
            engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
