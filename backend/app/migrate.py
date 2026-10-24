"""Run Alembic from code (CLI, development start-up, tests, restore)."""
from __future__ import annotations

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.config import BACKEND_DIR
from app.db import Database


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["configure_logging"] = False
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(_alembic_config()).get_current_head() or ""


def current_revision(database: Database) -> str | None:
    with database.engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def upgrade(database: Database, revision: str = "head") -> None:
    cfg = _alembic_config()
    with database.engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, revision)


def downgrade(database: Database, revision: str = "base") -> None:
    cfg = _alembic_config()
    with database.engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, revision)


def ensure_current(database: Database) -> bool:
    """Upgrade when the database is behind (development convenience; production runs migrations in the deploy script)."""
    if current_revision(database) == head_revision():
        return False
    upgrade(database)
    return True


# ---- hooks shared by migrations/env.py and the "no schema drift" test -------------------------------------------------------
def include_object(obj, name, type_, reflected, compare_to):
    """The FTS5 virtual table and its shadow tables are created by hand in the first migration."""
    return not (type_ == "table" and name.startswith("search_fts"))


def render_item(type_, obj, autogen_context):
    """Migrations stay independent of application code: the custom UTC type is stored as a plain DATETIME."""
    from app.models import UTCDateTime

    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False
