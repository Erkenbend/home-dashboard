"""DepartureProvider for INSA HAFAS (Nahverkehr Sachsen-Anhalt), see ADR 0003."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from home_dashboard.widgets.departures.provider import (
    Departure,
    Product,
    ProviderError,
    StopMatch,
)

ENDPOINT = "https://reiseauskunft.insa.de/bin/mgate.exe"
REQUEST_ENVELOPE = {
    "auth": {"type": "AID", "aid": "nasa-apps"},
    "client": {"type": "IPH", "id": "NASA", "v": "4000200", "name": "nasaPROD"},
    "ver": "1.44",
    "lang": "de",
}
PRODUCT_BITMASKS: dict[Product, int] = {
    "regional": 8,
    "suburban": 16,
    "tram": 32,
    "bus": 64 | 128,
}
MAX_JOURNEYS = 40
# The arrival board at the via stop contains all lines passing there, not only ours
MAX_ARRIVALS = 300
# Longest plausible ride from the stop to its via stop; later arrivals are not checked
MAX_RIDE_TO_VIA_MINUTES = 30


def _lid(stop_id: str) -> str:
    """Numeric stop ids (extId) are expanded to a minimal HAFAS location id."""
    return f"A=1@L={stop_id}@" if stop_id.isdigit() else stop_id


def _product_from_class(cls: int) -> Product:
    for product, bitmask in PRODUCT_BITMASKS.items():
        if cls & bitmask:
            return product
    return "other"


def _line_name(product: dict[str, Any]) -> str:
    return product.get("nameS") or product.get("number") or product.get("name", "?")


def _parse_time(date: str, time: str | None, tz_offset_minutes: int | None) -> datetime | None:
    """HAFAS times are HHMMSS relative to the journey date, with an optional day-offset prefix."""
    if not time:
        return None
    day_offset = int(time[:-6]) if len(time) > 6 else 0
    tz = timezone(timedelta(minutes=tz_offset_minutes or 0))
    base = datetime.strptime(date + time[-6:], "%Y%m%d%H%M%S").replace(tzinfo=tz)
    return base + timedelta(days=day_offset)


class InsaHafasProvider:
    def __init__(self, http: httpx.Client, endpoint: str = ENDPOINT) -> None:
        self._http = http
        self._endpoint = endpoint

    def _call(self, method: str, request: dict[str, Any]) -> dict[str, Any]:
        body = {**REQUEST_ENVELOPE, "svcReqL": [{"meth": method, "req": request}]}
        try:
            response = self._http.post(self._endpoint, json=body)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderError(f"HAFAS {method} request failed: {error}") from error
        if data.get("err", "OK") != "OK":
            raise ProviderError(f"HAFAS error: {data.get('err')} {data.get('errTxt', '')}")
        try:
            result = data["svcResL"][0]
        except (KeyError, IndexError) as error:
            raise ProviderError("HAFAS response without result") from error
        if result.get("err") != "OK":
            raise ProviderError(f"HAFAS {method} error: {result.get('err')} {result.get('errTxt')}")
        return result.get("res", {})

    def departures(
        self,
        stop_id: str,
        start: datetime,
        duration_minutes: int,
        via_id: str | None = None,
        products: list[Product] | None = None,
    ) -> list[Departure]:
        request = self._board_request("DEP", stop_id, start, duration_minutes, products)
        request["maxJny"] = MAX_JOURNEYS
        if via_id:
            request["dirLoc"] = {"type": "S", "lid": _lid(via_id)}
        result = self._call("StationBoard", request)
        try:
            departures = [
                self._parse_journey(journey, result) for journey in result.get("jnyL", [])
            ]
        except (KeyError, IndexError, ValueError) as error:
            raise ProviderError(f"unexpected HAFAS StationBoard format: {error!r}") from error
        if via_id:
            departures = self._passing_via(departures, via_id, start, duration_minutes, products)
        return departures

    @staticmethod
    def _board_request(
        board_type: str,
        stop_id: str,
        start: datetime,
        duration_minutes: int,
        products: list[Product] | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "type": board_type,
            "date": start.strftime("%Y%m%d"),
            "time": start.strftime("%H%M%S"),
            "stbLoc": {"type": "S", "lid": _lid(stop_id)},
            "dur": duration_minutes,
        }
        if products:
            bitmask = sum(PRODUCT_BITMASKS.get(product, 0) for product in set(products))
            request["jnyFltrL"] = [{"type": "PROD", "mode": "INC", "value": str(bitmask)}]
        return request

    def _passing_via(
        self,
        departures: list[Departure],
        via_id: str,
        start: datetime,
        duration_minutes: int,
        products: list[Product] | None,
    ) -> list[Departure]:
        """Keep departures whose trip reaches the via stop next *under the same line*.

        HAFAS `dirLoc` accepts any trip passing the via stop at some point later, also after the
        vehicle changed its line number at a terminus and turned around (observed: line 1 towards
        Südstadt continues as line 2 to the main station, line 94 towards Kröllwitz returns as 7).
        Such trips leave in the opposite direction, so the arrival board of the via stop is used
        to check where the trip actually goes first.
        """
        request = self._board_request(
            "ARR", via_id, start, duration_minutes + MAX_RIDE_TO_VIA_MINUTES, products
        )
        request["maxJny"] = MAX_ARRIVALS
        result = self._call("StationBoard", request)
        arrivals: dict[str, list[tuple[datetime, str]]] = {}
        try:
            for journey in result.get("jnyL", []):
                stop = journey["stbStop"]
                planned = _parse_time(journey["date"], stop["aTimeS"], stop.get("aTZOffset"))
                product = result["common"]["prodL"][stop.get("aProdX", journey["prodX"])]
                arrivals.setdefault(journey["jid"], []).append((planned, _line_name(product)))
        except (KeyError, IndexError, ValueError) as error:
            raise ProviderError(f"unexpected HAFAS arrival board format: {error!r}") from error

        def reaches_via_next(departure: Departure) -> bool:
            later = sorted(
                a for a in arrivals.get(departure.trip_id, []) if a[0] > departure.planned
            )
            return bool(later) and later[0][1] == departure.line

        return [departure for departure in departures if reaches_via_next(departure)]

    @staticmethod
    def _parse_journey(journey: dict[str, Any], result: dict[str, Any]) -> Departure:
        stop = journey["stbStop"]
        # The product at this stop (a vehicle can change its line number during the trip)
        product = result["common"]["prodL"][stop.get("dProdX", journey["prodX"])]
        tz_offset = stop.get("dTZOffset")
        platform = stop.get("dPltfR") or stop.get("dPltfS") or {}
        return Departure(
            trip_id=journey["jid"],
            line=_line_name(product),
            product=_product_from_class(product.get("cls", 0)),
            direction=journey.get("dirTxt", ""),
            planned=_parse_time(journey["date"], stop["dTimeS"], tz_offset),
            realtime=_parse_time(journey["date"], stop.get("dTimeR"), tz_offset),
            cancelled=bool(stop.get("dCncl", False) or journey.get("isCncl", False)),
            platform=platform.get("txt"),
        )

    def search_stops(self, query: str) -> list[StopMatch]:
        result = self._call(
            "LocMatch",
            {"input": {"loc": {"type": "S", "name": query + "?"}, "maxLoc": 10, "field": "S"}},
        )
        return [
            StopMatch(id=loc.get("extId") or loc["lid"], name=loc["name"])
            for loc in result.get("match", {}).get("locL", [])
        ]
