"""WeatherSource backed by Open-Meteo (no API key), see ADR 0004."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from home_dashboard.widgets.weather.source import (
    CurrentWeather,
    DayForecast,
    Forecast,
    HourForecast,
    WeatherError,
)

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 2  # today and tomorrow; enough for 24 hours ahead


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
            "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max",
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
        daily = data["daily"]
        hours = [
            HourForecast(
                time=self._time(time),
                temperature=temperature,
                code=code,
                is_day=bool(is_day),
                precipitation_probability=probability,
            )
            for time, temperature, code, is_day, probability in zip(
                hourly["time"],
                hourly["temperature_2m"],
                hourly["weather_code"],
                hourly["is_day"],
                hourly["precipitation_probability"],
                strict=True,
            )
            if temperature is not None and code is not None  # end of a model's range
        ]
        days = [
            DayForecast(
                day=self._time(time).date(),
                code=code,
                temperature_min=low,
                temperature_max=high,
                precipitation_probability=probability,
            )
            for time, code, low, high, probability in zip(
                daily["time"],
                daily["weather_code"],
                daily["temperature_2m_min"],
                daily["temperature_2m_max"],
                daily["precipitation_probability_max"],
                strict=True,
            )
            if code is not None and low is not None and high is not None
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
            days=days,
        )
