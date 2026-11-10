"""Fake INSA HAFAS endpoint (via respx) answering with recorded responses from tests/fixtures."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import httpx
import respx

from home_dashboard.widgets.departures.insa_hafas import ENDPOINT
from tests.conftest import FIXTURES

HAFAS_FIXTURES = FIXTURES / "insa_hafas"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((HAFAS_FIXTURES / name).read_text(encoding="utf-8"))


class HafasFake:
    """Recorded at 2026-11-09 21:36 (Europe/Berlin), arrival boards (schedule only) a day later."""

    def __init__(self, router: respx.Router) -> None:
        # stop id -> StationBoard response; tests may modify these (delays, cancellations, ...)
        self.boards: dict[str, dict[str, Any]] = {
            "5258": load_fixture("stationboard_5258_via_5232.json"),
            "5125": load_fixture("stationboard_5125_via_8010159.json"),
        }
        # via stop id -> arrival board (StationBoard type ARR), to check the direction of trips
        self.arrival_boards: dict[str, dict[str, Any]] = {
            "5232": load_fixture("arrivals_5232.json"),
            "8010159": load_fixture("arrivals_8010159.json"),
        }
        self.stop_matches: dict[str, dict[str, Any]] = {
            "Rannischer Platz": load_fixture("locmatch_5258.json"),
        }
        self.failing = False
        self.requests: list[dict[str, Any]] = []  # all received request bodies
        self.route = router.post(ENDPOINT).mock(side_effect=self._respond)

    @property
    def departure_fetches(self) -> int:
        """Requests for departure boards (one per stop and fetch), including failed ones."""
        return sum(
            1
            for body in self.requests
            if body["svcReqL"][0]["meth"] == "StationBoard"
            and body["svcReqL"][0]["req"]["type"] == "DEP"
        )

    def _respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.failing:
            return httpx.Response(503, text="Service Unavailable")
        service = body["svcReqL"][0]
        if service["meth"] == "StationBoard":
            stop_id = re.search(r"L=(\d+)@", service["req"]["stbLoc"]["lid"]).group(1)
            boards = self.arrival_boards if service["req"]["type"] == "ARR" else self.boards
            return httpx.Response(200, json=boards[stop_id])
        if service["meth"] == "LocMatch":
            query = service["req"]["input"]["loc"]["name"].rstrip("?")
            for key, response in self.stop_matches.items():
                if key in query:
                    return httpx.Response(200, json=response)
            empty = {"err": "OK", "res": {"match": {"locL": []}}}
            return httpx.Response(200, json={"err": "OK", "svcResL": [empty]})
        raise NotImplementedError(service["meth"])

    def journeys(self, stop_id: str) -> list[dict[str, Any]]:
        return self.boards[stop_id]["svcResL"][0]["res"]["jnyL"]

    def arrivals(self, via_id: str) -> list[dict[str, Any]]:
        return self.arrival_boards[via_id]["svcResL"][0]["res"]["jnyL"]

    def arrival(self, via_id: str, trip_id: str) -> dict[str, Any]:
        """The (first) arrival of a trip at the via stop, to modify it in a test."""
        return next(journey for journey in self.arrivals(via_id) if journey["jid"] == trip_id)

    def products(self, stop_id: str) -> list[dict[str, Any]]:
        return self.boards[stop_id]["svcResL"][0]["res"]["common"]["prodL"]

    def journey(self, stop_id: str, line: str, planned: str) -> dict[str, Any]:
        """Find a journey by line and scheduled time (HHMMSS) to modify it in a test."""
        products = self.products(stop_id)
        for journey in self.journeys(stop_id):
            stop = journey["stbStop"]
            if products[stop["dProdX"]]["nameS"] == line and stop["dTimeS"] == planned:
                return journey
        raise KeyError((stop_id, line, planned))

    def add_journey(
        self,
        stop_id: str,
        template: dict[str, Any],
        via: tuple[str, str] | None = None,
        **stop_fields: Any,
    ) -> dict[str, Any]:
        """Add a new trip based on `template`; `via=(via_id, aTimeS)` lets it pass the via stop."""
        journey = copy.deepcopy(template)
        journey["jid"] = journey["jid"] + "#copy" + str(len(self.journeys(stop_id)))
        journey["stbStop"].update(stop_fields)
        self.journeys(stop_id).append(journey)
        if via:
            via_id, arrival_time = via
            arrival = copy.deepcopy(self.arrival(via_id, template["jid"]))
            arrival["jid"] = journey["jid"]
            arrival["stbStop"]["aTimeS"] = arrival_time
            self.arrivals(via_id).append(arrival)
        return journey
