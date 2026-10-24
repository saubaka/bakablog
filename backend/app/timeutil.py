"""Time helpers. Everything is stored and sent as UTC; "which day / month is this" is answered in the site time zone."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Asia/Shanghai"


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC, convert an aware one."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso(value: datetime | None) -> str | None:
    """ISO 8601 in UTC with a trailing Z, seconds precision: 2026-10-18T09:30:00Z."""
    if value is None:
        return None
    return as_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_precise(value: datetime | None) -> str | None:
    """Like iso() but keeps microseconds: the admin uses it as an edit token (detect that someone saved in between)."""
    if value is None:
        return None
    return as_utc(value).isoformat().replace("+00:00", "Z")


def parse_iso(text: str) -> datetime:
    """Accepts 2026-10-18T09:30:00Z, an offset, or a naive value (read as UTC)."""
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return as_utc(value)


@lru_cache(maxsize=16)
def zone(name: str | None) -> tzinfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def local(value: datetime, tz_name: str | None) -> datetime:
    return as_utc(value).astimezone(zone(tz_name))


def month_bounds(month: str, tz_name: str | None) -> tuple[datetime, datetime]:
    """"2026-10" -> [start, end) in UTC, where the month is the one the visitor sees in the site time zone."""
    year_s, month_s = month.split("-")
    year, mon = int(year_s), int(month_s)
    if not (1970 <= year <= 2200 and 1 <= mon <= 12):
        raise ValueError("bad month")
    tz = zone(tz_name)
    start = datetime(year, mon, 1, tzinfo=tz)
    end = datetime(year + (mon == 12), 1 if mon == 12 else mon + 1, 1, tzinfo=tz)
    return start.astimezone(UTC), end.astimezone(UTC)


def day_key(value: datetime, tz_name: str | None) -> date:
    return local(value, tz_name).date()


def today_utc() -> date:
    return utcnow().date()


def days_ago(n: int) -> datetime:
    return utcnow() - timedelta(days=n)
