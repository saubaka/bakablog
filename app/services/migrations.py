"""Read-only helpers for comparing a database revision with the code head."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def migration_head() -> str:
    project_root = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(project_root / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise RuntimeError("代码中没有可用的数据库迁移head。")
    return head
