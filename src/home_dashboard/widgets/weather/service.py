"""Weather widget logic: temperature now (felt and real), the weather now and in 1 and 2 hours."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import WeatherConfig
from home_dashboard.widgets.weather.source import HourForecast, WeatherSource

log = logging.getLogger(__name__)

LATER_HOURS = (1, 2)

# WMO weather interpretation codes -> (German description, icon of widgets/weather_icons.html)
_CONDITIONS: dict[int, tuple[str, str]] = {
    0: ("Klar", "clear"),
    1: ("Leicht bewölkt", "partly"),
    2: ("Teils bewölkt", "partly"),
    3: ("Bedeckt", "cloudy"),
    45: ("Nebel", "fog"),
    48: ("Reifnebel", "fog"),
    51: ("Leichter Nieselregen", "drizzle"),
    53: ("Nieselregen", "drizzle"),
    55: ("Starker Nieselregen", "drizzle"),
    56: ("Gefrierender Nieselregen", "sleet"),
    57: ("Gefrierender Nieselregen", "sleet"),
    61: ("Leichter Regen", "rain"),
    63: ("Regen", "rain"),
    65: ("Starker Regen", "rain"),
    66: ("Gefrierender Regen", "sleet"),
    67: ("Gefrierender Regen", "sleet"),
    71: ("Leichter Schneefall", "snow"),
    73: ("Schneefall", "snow"),
    75: ("Starker Schneefall", "snow"),
    77: ("Schneegriesel", "snow"),
    80: ("Leichte Regenschauer", "rain"),
    81: ("Regenschauer", "rain"),
    82: ("Heftige Regenschauer", "rain"),
    85: ("Leichte Schneeschauer", "snow"),
    86: ("Schneeschauer", "snow"),
    95: ("Gewitter", "thunder"),
    96: ("Gewitter mit Hagel", "thunder"),
    99: ("Gewitter mit Hagel", "thunder"),
}
_UNKNOWN = ("Unbekannt", "cloudy")
_DAY_NIGHT_ICONS = {"clear", "partly"}  # sun by day, moon by night


@dataclass(frozen=True)
class Condition:
    label: str
    icon: str
    """clear-day, clear-night, partly-day, partly-night, cloudy, fog, drizzle, rain, sleet, snow,
    thunder"""


def condition(code: int, is_day: bool = True) -> Condition:
    label, icon = _CONDITIONS.get(code, _UNKNOWN)
    if icon in _DAY_NIGHT_ICONS:
        icon = f"{icon}-{'day' if is_day else 'night'}"
    if code == 0 and is_day:
        label = "Sonnig"
    return Condition(label, icon)


def degrees(celsius: float) -> int:
    """Whole degrees, rounded half up (Python's round() rounds 2.5 to 2; -0.4 gives 0, not -0)."""
    return math.floor(celsius + 0.5)


@dataclass(frozen=True)
class Slot:
    """The weather at one point in time: now, in about 1 hour, in about 2 hours."""

    label: str
    condition: Condition


@dataclass
class WeatherView:
    apparent_temperature: int | None = None
    """Now, "feels like", whole °C"""
    temperature: int | None = None
    """Now, measured, whole °C"""
    slots: list[Slot] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


def nearest_hour(hours: list[HourForecast], target: datetime) -> HourForecast | None:
    """The hourly forecast closest to `target` (half past rounds up), None if there is none."""
    candidates = [hour for hour in hours if abs(hour.time - target) <= timedelta(minutes=30)]
    return max(candidates, key=lambda hour: hour.time) if candidates else None


class WeatherService:
    def __init__(
        self,
        config: WeatherConfig,
        source: WeatherSource,
        clock: Clock,
        cache: TtlCache,
    ) -> None:
        self._config = config
        self._source = source
        self._clock = clock
        self._cache = cache

    def view(self) -> WeatherView:
        view = WeatherView()
        try:
            cached = self._cache.get(
                "weather", fetch_interval(self._config.fetch_seconds), self._source.forecast
            )
        except Exception:
            log.exception("weather not available")
            view.unavailable = True
            return view

        forecast = cached.value
        now = self._clock.now()
        view.fetched_at = cached.fetched_at
        view.stale = cached.stale
        view.apparent_temperature = degrees(forecast.current.apparent_temperature)
        view.temperature = degrees(forecast.current.temperature)
        view.slots = [Slot("jetzt", condition(forecast.current.code, forecast.current.is_day))]
        for hours_ahead in LATER_HOURS:
            hour = nearest_hour(forecast.hours, now + timedelta(hours=hours_ahead))
            if hour is not None:
                view.slots.append(Slot(f"{hour.time.hour} Uhr", condition(hour.code, hour.is_day)))
        return view
