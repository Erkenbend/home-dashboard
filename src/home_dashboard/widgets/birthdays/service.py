"""Birthdays widget logic: upcoming events of a separate calendar (birthdays, anniversaries, ...),
one line each, soonest first. The events come through the calendar widget's CalendarSource."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import BirthdaysConfig
from home_dashboard.formatting import format_day_label, format_time
from home_dashboard.widgets.calendar.source import CalendarSource, Event

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Occasion:
    day: date
    label: str
    """'Heute', 'Morgen', 'Sa, 05.12.'"""
    title: str
    time: str
    """Start time of timed events, empty for all-day ones (the usual case)."""
    is_today: bool


@dataclass
class BirthdaysView:
    title: str
    occasions: list[Occasion] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


class BirthdaysService:
    def __init__(
        self,
        config: BirthdaysConfig,
        source: CalendarSource,
        clock: Clock,
        cache: TtlCache,
        timezone: str,
    ) -> None:
        self._config = config
        self._source = source
        self._clock = clock
        self._cache = cache
        self._tz = ZoneInfo(timezone)

    def view(self) -> BirthdaysView:
        today = self._clock.now().astimezone(self._tz).date()
        window_start = self._midnight(today)
        window_end = self._midnight(today + timedelta(days=self._config.days))

        view = BirthdaysView(title=self._config.title)
        try:
            cached = self._cache.get(
                ("birthdays", today),
                fetch_interval(self._config.fetch_seconds),
                lambda: self._source.events(window_start, window_end),
            )
        except Exception:
            log.exception("birthdays calendar not available")
            view.unavailable = True
            return view

        view.fetched_at = cached.fetched_at
        view.stale = cached.stale
        occasions = [self._occasion(event, today) for event in cached.value]
        view.occasions = sorted(occasions, key=lambda o: (o.day, o.time, o.title.casefold()))
        return view

    def _midnight(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self._tz)

    @staticmethod
    def _occasion(event: Event, today: date) -> Occasion:
        start = event.start if event.all_day else event.start.date()
        day = max(start, today)  # an event that started before today (several days) counts today
        return Occasion(
            day=day,
            label=format_day_label(day, today),
            title=event.title,
            time="" if event.all_day else format_time(event.start),
            is_today=day == today,
        )
