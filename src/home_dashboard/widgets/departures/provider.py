"""Interface between the departures widget and a concrete public transport data source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

Product = Literal["tram", "bus", "suburban", "regional", "other"]


@dataclass(frozen=True)
class Departure:
    trip_id: str
    line: str
    product: Product
    direction: str
    planned: datetime
    realtime: datetime | None
    cancelled: bool = False
    platform: str | None = None

    @property
    def when(self) -> datetime:
        """Best known departure time (realtime prognosis if available)."""
        return self.realtime or self.planned

    @property
    def delay_minutes(self) -> int:
        if self.realtime is None:
            return 0
        return round((self.realtime - self.planned).total_seconds() / 60)


@dataclass(frozen=True)
class StopMatch:
    id: str
    name: str


class ProviderError(Exception):
    """The data source could not deliver usable data."""


class DepartureProvider(Protocol):
    def departures(
        self,
        stop_id: str,
        start: datetime,
        duration_minutes: int,
        via_id: str | None = None,
        products: list[Product] | None = None,
    ) -> list[Departure]:
        """Departures at `stop_id` from `start` on, optionally only trips passing `via_id` later."""
        ...

    def search_stops(self, query: str) -> list[StopMatch]: ...
