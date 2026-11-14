"""Fake Open-Meteo endpoint (via respx) answering with a recorded response from tests/fixtures."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime
from typing import Any

import httpx
import respx

from home_dashboard.widgets.weather.open_meteo import ENDPOINT
from tests.conftest import BERLIN, FIXTURES

RECORDED_AT = datetime(2026, 11, 14, 14, 30, tzinfo=BERLIN)
"""Halle (Saale), Saturday afternoon: partly cloudy, dry; tomorrow light rain around noon."""

_RECORDING = json.loads(
    (FIXTURES / "open_meteo" / "forecast_halle.json").read_text(encoding="utf-8")
)


class OpenMeteoFake:
    def __init__(self, router: respx.Router) -> None:
        # Tests may modify the response (temperatures, weather codes, rain, ...)
        self.response: dict[str, Any] = copy.deepcopy(_RECORDING)
        self.failing = False
        self.requests: list[httpx.Request] = []
        router.get(ENDPOINT).mock(side_effect=self._respond)

    def _respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failing:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json=self.response)

    def hour(self, hour: int, day: date | None = None) -> int:
        """Index of the hourly values for `hour` o'clock (on the recorded day by default)."""
        start = datetime.combine(day or RECORDED_AT.date(), datetime.min.time(), tzinfo=BERLIN)
        return self.response["hourly"]["time"].index(int(start.timestamp()) + hour * 3600)

    def set_hour(self, hour: int, day: date | None = None, **values: Any) -> None:
        index = self.hour(hour, day)
        for key, value in values.items():
            self.response["hourly"][key][index] = value

    def move_to(self, day: date) -> None:
        """Shift the recording to another day (whole days, no DST change in between)."""
        shift = (day - RECORDED_AT.date()).days * 86400
        self.response["current"]["time"] += shift
        for section in ("hourly", "daily"):
            self.response[section]["time"] = [t + shift for t in self.response[section]["time"]]
