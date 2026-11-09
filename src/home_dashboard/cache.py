"""Small TTL cache that falls back to the last good value when the upstream fails."""

from __future__ import annotations

import logging
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from home_dashboard.clock import Clock

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Cached[T]:
    value: T
    fetched_at: datetime
    stale: bool = False
    """True if the last refresh failed and this is the last good value."""


@dataclass
class _Entry:
    attempted_at: datetime
    cached: Cached[Any] | None = None
    error: Exception | None = None


class TtlCache:
    """Loads at most once per TTL and key, also after failures (no hammering a broken upstream)."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._entries: dict[Hashable, _Entry] = {}

    def get[T](self, key: Hashable, ttl: timedelta, load: Callable[[], T]) -> Cached[T]:
        """Return the cached or freshly loaded value.

        On load errors the last good value is returned (marked stale); without one the error is
        raised - also for calls within the TTL after the failure.
        """
        now = self._clock.now()
        entry = self._entries.get(key)
        if entry is None or now - entry.attempted_at >= ttl:
            entry = self._load(key, load, now, previous=entry)
            self._entries[key] = entry
        if entry.cached is None:
            assert entry.error is not None
            raise entry.error
        return entry.cached

    @staticmethod
    def _load(key: Hashable, load: Callable[[], Any], now: datetime, previous: _Entry | None):
        try:
            return _Entry(attempted_at=now, cached=Cached(value=load(), fetched_at=now))
        except Exception as error:
            last_good = previous.cached if previous else None
            if last_good is None:
                return _Entry(attempted_at=now, error=error)
            log.warning(
                "refresh of %r failed (%s), serving data from %s", key, error, last_good.fetched_at
            )
            stale = Cached(value=last_good.value, fetched_at=last_good.fetched_at, stale=True)
            return _Entry(attempted_at=now, cached=stale)
