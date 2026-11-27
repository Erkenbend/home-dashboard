"""Departures widget logic: which trams can I still catch when leaving now?"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import DeparturesConfig, StopConfig
from home_dashboard.widgets.departures.provider import Departure, DepartureProvider

log = logging.getLogger(__name__)

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
    direction: str | None = None
    rows: list[DepartureRow] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


def _is_duplicate(earlier: Departure, later: Departure) -> bool:
    """Whether `later` is the same tram leaving as `earlier` (sorted by departure time).

    - A station board spans several stop points, so a trip may show up twice within minutes. The
      same trip may legitimately reappear much later (e.g. after a loop with another line number),
      therefore only nearby repetitions count.
    - A redirected trip can be published as an additional trip next to the original one, with
      another trip id but the same line, destination and schedule (observed: line 95).
    """
    if earlier.trip_id == later.trip_id:
        return later.when - earlier.when < DUPLICATE_WINDOW
    return (earlier.line, earlier.direction, earlier.planned) == (
        later.line,
        later.direction,
        later.planned,
    )


def _without_duplicates(departures: list[Departure]) -> list[Departure]:
    """Keep one departure per tram, preferring a variant that is not cancelled."""
    kept: list[Departure] = []
    for departure in sorted(departures, key=lambda d: (d.when, d.cancelled)):
        index = next((i for i, other in enumerate(kept) if _is_duplicate(other, departure)), None)
        if index is None:
            kept.append(departure)
        elif kept[index].cancelled and not departure.cancelled:
            kept[index] = departure
    return sorted(kept, key=lambda d: d.when)


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
        board = StopBoard(name=stop.name, walk_minutes=stop.walk_minutes, direction=stop.direction)
        try:
            cached = self._cache.get(
                ("departures", stop.id, stop.via, tuple(self._config.products)),
                fetch_interval(self._config.fetch_seconds),
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
