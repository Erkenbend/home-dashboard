"""Interface between the weather widget and a concrete weather service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class CurrentWeather:
    time: datetime
    temperature: float
    """°C"""
    apparent_temperature: float
    """°C, "feels like" (wind chill, humidity)"""
    code: int
    """WMO weather interpretation code (0 clear ... 99 thunderstorm with hail)"""
    is_day: bool


@dataclass(frozen=True)
class HourForecast:
    time: datetime
    """Start of the hour, timezone-aware."""
    temperature: float
    code: int
    is_day: bool
    precipitation_probability: int | None = None
    """Percent, None if the service has no value."""


@dataclass(frozen=True)
class DayForecast:
    day: date
    code: int
    temperature_min: float
    temperature_max: float
    precipitation_probability: int | None = None


@dataclass(frozen=True)
class Forecast:
    current: CurrentWeather
    hours: list[HourForecast] = field(default_factory=list)
    days: list[DayForecast] = field(default_factory=list)


class WeatherError(Exception):
    """The weather service could not deliver usable data."""


class WeatherSource(Protocol):
    def forecast(self) -> Forecast:
        """Current weather plus hourly and daily forecasts for today and tomorrow (at least)."""
        ...
