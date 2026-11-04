"""TTL cache that retains expired values briefly for stale-if-error responses."""

from dataclasses import dataclass
from time import monotonic
from typing import Any

from cachetools import TTLCache


@dataclass
class CacheEntry:
    """Cached value and the point at which it becomes stale."""

    value: Any
    fresh_until: float


class ResponseCache:
    """In-memory cache with per-key freshness windows and stale retention."""

    def __init__(self) -> None:
        self._entries: TTLCache[str, CacheEntry] = TTLCache(maxsize=2048, ttl=86400)

    def get_fresh(self, key: str) -> Any | None:
        """Return a fresh value, or None when missing/stale."""
        entry = self._entries.get(key)
        if entry is None or monotonic() >= entry.fresh_until:
            return None
        return entry.value

    def get_stale(self, key: str) -> Any | None:
        """Return any retained value, whether fresh or stale."""
        entry = self._entries.get(key)
        return entry.value if entry is not None else None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store a value with its own freshness duration."""
        self._entries[key] = CacheEntry(value, monotonic() + ttl_seconds)


response_cache = ResponseCache()
