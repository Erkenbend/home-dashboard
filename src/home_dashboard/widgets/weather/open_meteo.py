"""WeatherSource backed by Open-Meteo (no API key), see ADR 0004."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from home_dashboard.widgets.weather.source import (
    CurrentWeather,
    Forecast,
    HourForecast,
    WeatherError,
)

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 2  # today and tomorrow: the next hours also late in the evening


class OpenMeteoSource:
    def __init__(self, http: httpx.Client, lat: float, lon: float, timezone: str) -> None:
        self._http = http
        self._tz = ZoneInfo(timezone)
        self._params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": timezone,
            "timeformat": "unixtime",  # unambiguous, also around DST changes
            "forecast_days": FORECAST_DAYS,
            "current": "temperature_2m,apparent_temperature,weather_code,is_day",
            "hourly": "weather_code,is_day",
        }

    def forecast(self) -> Forecast:
        try:
            response = self._http.get(ENDPOINT, params=self._params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise WeatherError(f"Open-Meteo request failed: {error!r}") from error
        try:
            return self._parse(response.json())
        except (ValueError, KeyError, TypeError, IndexError) as error:
            raise WeatherError(f"unexpected Open-Meteo response: {error!r}") from error

    def _time(self, unixtime: int) -> datetime:
        return datetime.fromtimestamp(unixtime, self._tz)

    def _parse(self, data: dict[str, Any]) -> Forecast:
        current = data["current"]
        hourly = data["hourly"]
        hours = [
            HourForecast(time=self._time(time), code=code, is_day=bool(is_day))
            for time, code, is_day in zip(
                hourly["time"], hourly["weather_code"], hourly["is_day"], strict=True
            )
            if code is not None  # end of a model's range
        ]
        return Forecast(
            current=CurrentWeather(
                time=self._time(current["time"]),
                temperature=float(current["temperature_2m"]),
                apparent_temperature=float(current["apparent_temperature"]),
                code=int(current["weather_code"]),
                is_day=bool(current["is_day"]),
            ),
            hours=hours,
        )
