"""Birthdays widget logic: upcoming events of a separate calendar (birthdays, anniversaries, ...),
one line each, soonest first. The events come through the calendar widget's CalendarSource, what
they are about is read by parsing.py."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import BirthdaysConfig
from home_dashboard.i18n import Translator
from home_dashboard.widgets.birthdays.parsing import Kind, parse
from home_dashboard.widgets.calendar.source import CalendarSource, Event

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Occasion:
    day: date
    label: str
    """'Heute', 'Morgen', 'Sa, 05.12.'"""
    kind: Kind
    name: str
    """Who or what it is about ("Mia", "Max Muster", the title of an unknown event)."""
    contact: str | None
    """Contact it is stored with (a child's birthday: the parent), None for the contact's own."""
    years: str
    """'wird 3' (birthday), '13 Jahre' (anniversary and others), empty without a known year."""
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
        translator: Translator,
    ) -> None:
        self._config = config
        self._source = source
        self._clock = clock
        self._cache = cache
        self._tz = ZoneInfo(timezone)
        self._t = translator

    def view(self) -> BirthdaysView:
        today = self._clock.now().astimezone(self._tz).date()
        window_start = self._midnight(today)
        window_end = self._midnight(today + timedelta(days=self._config.days))

        view = BirthdaysView(title=self._config.title or self._t.t("birthdays.title"))
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
        view.occasions = sorted(occasions, key=lambda o: (o.day, o.time, o.name.casefold()))
        return view

    def _midnight(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self._tz)

    def _occasion(self, event: Event, today: date) -> Occasion:
        start = event.start if event.all_day else event.start.date()
        day = max(start, today)  # an event that started before today (several days) counts today
        parsed = parse(event, self._config.ignore_contacts)
        return Occasion(
            day=day,
            label=self._t.day_label(day, today),
            kind=parsed.kind,
            name=parsed.name,
            contact=parsed.contact,
            years=self._years(parsed.kind, start.year - parsed.year if parsed.year else 0),
            time="" if event.all_day else self._t.time(event.start),
            is_today=day == today,
        )

    def _years(self, kind: Kind, years: int) -> str:
        if years <= 0:  # unknown year, or the year it happened
            return ""
        if kind is Kind.BIRTHDAY:
            return self._t.t("birthdays.turns", years=years)
        key = "birthdays.years_one" if years == 1 else "birthdays.years_other"
        return self._t.t(key, years=years)
