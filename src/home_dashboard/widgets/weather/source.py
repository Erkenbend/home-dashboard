"""Interface between the weather widget and a concrete weather service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    """Full hour, timezone-aware, in the configured timezone."""
    code: int
    is_day: bool


@dataclass(frozen=True)
class Forecast:
    current: CurrentWeather
    hours: list[HourForecast] = field(default_factory=list)


class WeatherError(Exception):
    """The weather service could not deliver usable data."""


class WeatherSource(Protocol):
    def forecast(self) -> Forecast:
        """Current weather plus hourly forecasts for at least the coming three hours."""
        ...
