"""Interface between the calendar widget and a concrete calendar backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class Event:
    uid: str
    title: str
    start: datetime | date
    """datetime (timezone-aware) for timed events, date for all-day events."""
    end: datetime | date
    """Exclusive end, same type as start."""
    recurring: bool = False
    """Occurrence of a series (incl. moved single occurrences)."""
    description: str = ""

    @property
    def all_day(self) -> bool:
        return not isinstance(self.start, datetime)


class CalendarError(Exception):
    """The calendar backend could not deliver usable data."""


class CalendarSource(Protocol):
    def events(self, start: datetime, end: datetime) -> list[Event]:
        """All event occurrences overlapping [start, end), recurring events expanded."""
        ...
