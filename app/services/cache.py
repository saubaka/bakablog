"""Small process-local TTL cache for stable public-site chrome data."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from time import monotonic
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = RLock()

    def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], Any]) -> Any:
        now = monotonic()
        with self._lock:
            cached = self._items.get(key)
            if cached and cached[0] > now:
                return cached[1]
        value = factory()
        with self._lock:
            self._items[key] = (now + max(1, ttl_seconds), value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


site_context_cache = TTLCache()
home_content_cache = TTLCache()
