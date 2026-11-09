"""Injectable clock, so tests can freeze time."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware."""
        ...


class SystemClock:
    def __init__(self, timezone: str) -> None:
        self._tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self._tz)


class FixedClock:
    """Clock returning a settable instant; used in tests."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self.instant = instant

    def now(self) -> datetime:
        return self.instant
