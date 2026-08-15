"""Small concurrency-safe in-memory TTL cache for external service data."""

"""It safely caches Roblox data for a short time and makes simultaneous requests for the same player share one API call—important for fast role syncing in larger servers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from ..core.config import Config
    from ..core.container import ServiceContainer


T = TypeVar("T")


@dataclass(slots=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class CacheService:
    """A bounded in-memory cache that avoids duplicate async API requests.

    This cache is intentionally local to one bot process.  If the project later
    runs across multiple machines, this class can be replaced by Redis without
    changing the Roblox or guild business logic that calls it.
    """

    def __init__(self, *, maximum_entries: int = 5_000) -> None:
        if maximum_entries < 1:
            raise ValueError("maximum_entries must be at least 1.")
        self._maximum_entries = maximum_entries
        self._entries: dict[Hashable, _CacheEntry[object]] = {}
        self._locks: dict[Hashable, asyncio.Lock] = {}

    @classmethod
    async def create(cls, _: Config, __: ServiceContainer) -> CacheService:
        """Factory used by ``ServiceManager`` during startup."""
        return cls()

    def get(self, key: Hashable) -> T | None:
        """Return a non-expired value, if present."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return None
        return entry.value  # type: ignore[return-value]

    def set(self, key: Hashable, value: T, *, ttl_seconds: float) -> T:
        """Store a value for a positive lifetime and return it for convenience."""
        if ttl_seconds <= 0:
            raise ValueError("Cache lifetime must be greater than zero.")
        self._evict_if_needed()
        self._entries[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl_seconds)
        return value

    async def get_or_set(
        self,
        key: Hashable,
        loader: Callable[[], Awaitable[T]],
        *,
        ttl_seconds: float,
    ) -> T:
        """Return cached data or run one shared loader call for the key.

        Concurrent requests for the same key wait for the first request instead
        of all sending a duplicate request to Roblox.
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                cached = self.get(key)
                if cached is not None:
                    return cached
                value = await loader()
                return self.set(key, value, ttl_seconds=ttl_seconds)
        finally:
            # The last caller removes its per-key lock; this prevents an
            # unbounded lock dictionary when the bot sees many unique users.
            if not lock.locked() and self._locks.get(key) is lock:
                self._locks.pop(key, None)

    def invalidate(self, key: Hashable) -> None:
        """Remove one cached value, for example after an explicit user refresh."""
        self._entries.pop(key, None)

    def clear(self) -> None:
        """Remove every cached value."""
        self._entries.clear()
        self._locks.clear()

    async def close(self) -> None:
        """Release held references during shutdown."""
        self.clear()

    def _evict_if_needed(self) -> None:
        now = time.monotonic()
        expired_keys = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired_keys:
            self._entries.pop(key, None)

        if len(self._entries) < self._maximum_entries:
            return
        # With a small bounded cache, evicting the soonest-expiring item is
        # simple and avoids adding a heavier caching dependency at this stage.
        oldest_key = min(self._entries, key=lambda key: self._entries[key].expires_at)
        self._entries.pop(oldest_key, None)
