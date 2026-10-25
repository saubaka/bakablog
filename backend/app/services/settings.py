"""Settings: key -> JSON in the settings table, merged over the defaults in app/defaults.py.

Only what the admin changed is stored. "Reset to default" is deleting the row. site_version is bumped by every content write; caches
(and ETags) are keyed on it.
"""
from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import defaults
from app.models import Setting

_VERSION_KEY = "site_version"


def _merge(base: Any, over: Any) -> Any:
    """Dicts merge key by key; everything else (lists, scalars) is replaced as a whole."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = {k: copy.deepcopy(v) for k, v in base.items()}
        for key, value in over.items():
            out[key] = _merge(base[key], value) if key in base else copy.deepcopy(value)
        return out
    return copy.deepcopy(over)


def _prune(base: Any, merged: Any) -> Any:
    """Drop stored keys the defaults no longer have (a setting that was retired): fixed-shape groups must not keep stale keys, they would fail validation."""
    if isinstance(base, dict) and isinstance(merged, dict):
        return {k: _prune(base[k], v) for k, v in merged.items() if k in base}
    return merged


def _rows(session: Session) -> dict[str, Any]:
    cache = session.info.get("settings_rows")
    if cache is None:
        cache = {row.key: row.value for row in session.scalars(select(Setting))}
        session.info["settings_rows"] = cache
    return cache


def invalidate(session: Session) -> None:
    session.info.pop("settings_rows", None)


def get_raw(session: Session, key: str, default: Any = None) -> Any:
    return _rows(session).get(key, default)


def set_raw(session: Session, key: str, value: Any) -> None:
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    session.flush()
    invalidate(session)


def delete_raw(session: Session, key: str) -> None:
    row = session.get(Setting, key)
    if row is not None:
        session.delete(row)
        session.flush()
    invalidate(session)


def group(session: Session, name: str) -> dict:
    """The effective values of one group (defaults + what was stored)."""
    base = defaults.DEFAULT_SETTINGS[name]
    stored = get_raw(session, f"cfg.{name}")
    out = _prune(base, _merge(base, stored)) if isinstance(stored, dict) else copy.deepcopy(base)
    if name == "author":   # the RSS link kind was retired: a stored one would fail the next save and point nowhere
        out["links"] = [link for link in out["links"] if link.get("kind") != "rss"]
    return out


def all_groups(session: Session) -> dict[str, dict]:
    return {name: group(session, name) for name in defaults.DEFAULT_SETTINGS}


def set_group(session: Session, name: str, value: dict) -> dict:
    """Store a complete, already validated group value."""
    set_raw(session, f"cfg.{name}", value)
    return group(session, name)


def reset_group(session: Session, name: str) -> dict:
    delete_raw(session, f"cfg.{name}")
    return group(session, name)


# ---- site version ------------------------------------------------------------------------------------------------------------
def site_version(session: Session) -> int:
    return int(get_raw(session, _VERSION_KEY, 0) or 0)


def bump_site_version(session: Session) -> int:
    value = site_version(session) + 1
    set_raw(session, _VERSION_KEY, value)
    return value
