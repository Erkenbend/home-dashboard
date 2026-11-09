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


def _lid(stop_id: str) -> str:
    """Numeric stop ids (extId) are expanded to a minimal HAFAS location id."""
    return f"A=1@L={stop_id}@" if stop_id.isdigit() else stop_id


def _product_from_class(cls: int) -> Product:
    for product, bitmask in PRODUCT_BITMASKS.items():
        if cls & bitmask:
            return product
    return "other"


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
        request: dict[str, Any] = {
            "type": "DEP",
            "date": start.strftime("%Y%m%d"),
            "time": start.strftime("%H%M%S"),
            "stbLoc": {"type": "S", "lid": _lid(stop_id)},
            "dur": duration_minutes,
            "maxJny": MAX_JOURNEYS,
        }
        if via_id:
            request["dirLoc"] = {"type": "S", "lid": _lid(via_id)}
        if products:
            bitmask = sum(PRODUCT_BITMASKS.get(product, 0) for product in set(products))
            request["jnyFltrL"] = [{"type": "PROD", "mode": "INC", "value": str(bitmask)}]

        result = self._call("StationBoard", request)
        try:
            return [self._parse_journey(journey, result) for journey in result.get("jnyL", [])]
        except (KeyError, IndexError, ValueError) as error:
            raise ProviderError(f"unexpected HAFAS StationBoard format: {error!r}") from error

    @staticmethod
    def _parse_journey(journey: dict[str, Any], result: dict[str, Any]) -> Departure:
        stop = journey["stbStop"]
        # The product at this stop (a vehicle can change its line number during the trip)
        product = result["common"]["prodL"][stop.get("dProdX", journey["prodX"])]
        tz_offset = stop.get("dTZOffset")
        platform = stop.get("dPltfR") or stop.get("dPltfS") or {}
        return Departure(
            trip_id=journey["jid"],
            line=product.get("nameS") or product.get("number") or product.get("name", "?"),
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
