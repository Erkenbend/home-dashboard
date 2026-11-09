"""Calendar widget logic: the coming days, grouped by day, coloured by person."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import CalendarConfig
from home_dashboard.formatting import format_short_date, format_time
from home_dashboard.widgets.calendar.source import CalendarSource, Event

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tag:
    name: str
    color: str


@dataclass(frozen=True)
class EventRow:
    title: str
    time_label: str
    tags: list[Tag]
    everyone: bool
    recurring: bool
    all_day: bool
    past: bool


@dataclass
class Day:
    day: date
    label: str
    is_today: bool
    rows: list[EventRow] = field(default_factory=list)


@dataclass
class CalendarView:
    days: list[Day] = field(default_factory=list)
    legend: list[Tag] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Case-insensitive whole-word match ('Ben' must not match 'Benefizlauf')."""
    prefix = r"(?<!\w)" if re.match(r"\w", keyword) else ""
    suffix = r"(?!\w)" if re.search(r"\w$", keyword) else ""
    return re.compile(prefix + re.escape(keyword) + suffix, re.IGNORECASE)


class _PersonMatcher:
    def __init__(self, config: CalendarConfig) -> None:
        self._people = [
            (Tag(person.name, person.color), [_keyword_pattern(k) for k in person.match])
            for person in config.people
        ]
        self._everyone_tag = Tag(config.everyone.label, config.everyone.color)
        self._everyone = [_keyword_pattern(k) for k in config.everyone.match]

    @property
    def legend(self) -> list[Tag]:
        return [tag for tag, _ in self._people] + [self._everyone_tag]

    def tags(self, title: str) -> tuple[list[Tag], bool]:
        """Tags for an event title and whether it concerns everyone."""
        if any(pattern.search(title) for pattern in self._everyone):
            return [self._everyone_tag], True
        people = [tag for tag, patterns in self._people if any(p.search(title) for p in patterns)]
        if not people:
            return [self._everyone_tag], True
        return people, False


class CalendarService:
    def __init__(
        self,
        config: CalendarConfig,
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
        self._matcher = _PersonMatcher(config)

    def view(self) -> CalendarView:
        now = self._clock.now().astimezone(self._tz)
        today = now.date()
        days = [today + timedelta(days=offset) for offset in range(self._config.days)]
        window_start = self._midnight(days[0])
        window_end = self._midnight(days[-1] + timedelta(days=1))

        view = CalendarView(legend=self._matcher.legend)
        try:
            cached = self._cache.get(
                ("calendar", today),
                fetch_interval(self._config.fetch_seconds),
                lambda: self._source.events(window_start, window_end),
            )
        except Exception:
            log.exception("calendar not available")
            view.unavailable = True
            return view

        view.fetched_at = cached.fetched_at
        view.stale = cached.stale
        for day in days:
            rows = [
                self._row(event, day, now)
                for event in sorted(cached.value, key=self._sort_key)
                if self._occurs_on(event, day)
            ]
            if rows or day == today:
                view.days.append(Day(day, self._day_label(day, today), day == today, rows))
        return view

    def _midnight(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self._tz)

    def _sort_key(self, event: Event) -> tuple[int, datetime]:
        start = event.start if not event.all_day else self._midnight(event.start)
        return (0 if event.all_day else 1, start)

    def _occurs_on(self, event: Event, day: date) -> bool:
        if event.all_day:
            return event.start <= day < event.end
        day_start, day_end = self._midnight(day), self._midnight(day + timedelta(days=1))
        if event.start == event.end:
            return day_start <= event.start < day_end
        return event.start < day_end and event.end > day_start

    @staticmethod
    def _day_label(day: date, today: date) -> str:
        if day == today:
            return "Heute"
        if day == today + timedelta(days=1):
            return "Morgen"
        return format_short_date(day)

    def _row(self, event: Event, day: date, now: datetime) -> EventRow:
        tags, everyone = self._matcher.tags(event.title)
        return EventRow(
            title=event.title,
            time_label=self._time_label(event, day),
            tags=tags,
            everyone=everyone,
            recurring=event.recurring,
            all_day=event.all_day,
            past=not event.all_day and event.end <= now,
        )

    def _time_label(self, event: Event, day: date) -> str:
        if event.all_day:
            total = (event.end - event.start).days
            if total > 1:
                return f"Tag {(day - event.start).days + 1}/{total}"
            return "ganztägig"
        starts_today = event.start.date() == day
        ends_today = event.end <= self._midnight(day + timedelta(days=1))
        if starts_today and ends_today:
            if event.start == event.end:
                return format_time(event.start)
            return f"{format_time(event.start)}–{format_time(event.end)}"
        if starts_today:
            return f"ab {format_time(event.start)}"
        if ends_today:
            return f"bis {format_time(event.end)}"
        return "ganztägig"
