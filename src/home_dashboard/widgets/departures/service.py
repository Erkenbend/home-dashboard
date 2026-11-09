"""Departures widget logic: which trams can I still catch when leaving now?"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from home_dashboard.cache import TtlCache
from home_dashboard.clock import Clock
from home_dashboard.config import DeparturesConfig, StopConfig
from home_dashboard.widgets.departures.provider import Departure, DepartureProvider

log = logging.getLogger(__name__)

CACHE_TTL = timedelta(seconds=45)
LOOKAHEAD_MINUTES = 60
DUPLICATE_WINDOW = timedelta(minutes=5)
CITY_PREFIX_SEPARATOR = ", "


@dataclass(frozen=True)
class DepartureRow:
    line: str
    direction: str
    when: datetime
    minutes: int
    leave_in: int
    delay: int
    cancelled: bool


@dataclass
class StopBoard:
    name: str
    walk_minutes: int
    rows: list[DepartureRow] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


def _without_duplicates(departures: list[Departure]) -> list[Departure]:
    """A station board spans several stop points, so a trip may show up twice within minutes.

    The same trip may legitimately reappear much later (e.g. after a loop with another line number),
    therefore only nearby repetitions are dropped.
    """
    kept: list[Departure] = []
    for departure in sorted(departures, key=lambda d: d.when):
        if any(
            other.trip_id == departure.trip_id and departure.when - other.when < DUPLICATE_WINDOW
            for other in kept
        ):
            continue
        kept.append(departure)
    return kept


def _short_direction(direction: str) -> str:
    """'Halle (Saale), Kröllwitz' -> 'Kröllwitz'."""
    _, separator, rest = direction.partition(CITY_PREFIX_SEPARATOR)
    return rest if separator else direction


def _whole_minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


class DeparturesService:
    def __init__(
        self,
        config: DeparturesConfig,
        provider: DepartureProvider,
        clock: Clock,
        cache: TtlCache,
    ) -> None:
        self._config = config
        self._provider = provider
        self._clock = clock
        self._cache = cache

    def boards(self) -> list[StopBoard]:
        return [self._board(stop) for stop in self._config.stops]

    def _board(self, stop: StopConfig) -> StopBoard:
        board = StopBoard(name=stop.name, walk_minutes=stop.walk_minutes)
        try:
            cached = self._cache.get(
                ("departures", stop.id, stop.via, tuple(self._config.products)),
                CACHE_TTL,
                lambda: self._provider.departures(
                    stop.id,
                    self._clock.now(),
                    LOOKAHEAD_MINUTES,
                    via_id=stop.via,
                    products=list(self._config.products),
                ),
            )
        except Exception:
            log.exception("no departures available for %s", stop.name)
            board.unavailable = True
            return board

        board.fetched_at = cached.fetched_at
        board.stale = cached.stale
        board.rows = self._reachable_rows(stop, cached.value)
        return board

    def _reachable_rows(self, stop: StopConfig, departures: list[Departure]) -> list[DepartureRow]:
        now = self._clock.now()
        walk = timedelta(minutes=stop.walk_minutes)
        rows: list[DepartureRow] = []
        for departure in _without_duplicates(departures):
            if departure.product not in self._config.products:
                continue
            if stop.lines and departure.line not in stop.lines:
                continue
            if departure.when - now < walk:
                continue
            rows.append(
                DepartureRow(
                    line=departure.line,
                    direction=_short_direction(departure.direction),
                    when=departure.when,
                    minutes=_whole_minutes(departure.when - now),
                    leave_in=_whole_minutes(departure.when - walk - now),
                    delay=departure.delay_minutes,
                    cancelled=departure.cancelled,
                )
            )
            if len(rows) >= self._config.max_per_stop:
                break
        return rows
