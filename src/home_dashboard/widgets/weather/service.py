"""Weather widget logic: temperature now (real and felt), the weather and the UV index now and in 1
and 2 hours."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import WeatherConfig
from home_dashboard.i18n import Translator
from home_dashboard.widgets.weather.source import HourForecast, WeatherSource

log = logging.getLogger(__name__)

LATER_HOURS = (1, 2)

# WMO weather interpretation codes -> icon of widgets/weather_icons.html (texts: the catalog,
# weather.conditions)
WMO_ICONS: dict[int, str] = {
    0: "clear",
    1: "partly",
    2: "partly",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "sleet",
    57: "sleet",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "sleet",
    67: "sleet",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunder",
    96: "thunder",
    99: "thunder",
}
_UNKNOWN_ICON = "cloudy"
_DAY_NIGHT_ICONS = {"clear", "partly"}  # sun by day, moon by night


@dataclass(frozen=True)
class Condition:
    label: str
    icon: str
    """clear-day, clear-night, partly-day, partly-night, cloudy, fog, drizzle, rain, sleet, snow,
    thunder"""


def condition(code: int, is_day: bool, translator: Translator) -> Condition:
    icon = WMO_ICONS.get(code, _UNKNOWN_ICON)
    if icon in _DAY_NIGHT_ICONS:
        icon = f"{icon}-{'day' if is_day else 'night'}"
    if code == 0 and is_day:
        label = translator.t("weather.sunny")
    elif code in WMO_ICONS:
        label = translator.t(f"weather.conditions.{code}")
    else:
        label = translator.t("weather.unknown")
    return Condition(label, icon)


def degrees(celsius: float) -> int:
    """Whole degrees, rounded half up (Python's round() rounds 2.5 to 2; -0.4 gives 0, not -0)."""
    return math.floor(celsius + 0.5)


# WHO UV index categories: (lowest whole value, level for the colour code and the catalog,
# weather.uv_levels)
UV_LEVELS = (
    (11, "extreme"),
    (8, "very-high"),
    (6, "high"),
    (3, "moderate"),
    (0, "low"),
)


@dataclass(frozen=True)
class UvIndex:
    value: int
    """Whole number, as the WHO scale is published"""
    level: str
    """low, moderate, high, very-high, extreme (colour code of the WHO scale)"""
    label: str


def uv_index(value: float, translator: Translator) -> UvIndex:
    whole = max(0, math.floor(value + 0.5))
    _, level = next(category for category in UV_LEVELS if whole >= category[0])
    return UvIndex(whole, level, translator.t(f"weather.uv_levels.{level}"))


@dataclass(frozen=True)
class Slot:
    """The weather at one point in time: now, in about 1 hour, in about 2 hours."""

    label: str
    condition: Condition
    uv: UvIndex | None = None
    """None if the source has no UV index for that time"""


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
        translator: Translator,
    ) -> None:
        self._config = config
        self._source = source
        self._clock = clock
        self._cache = cache
        self._t = translator

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
        current = forecast.current
        view.slots = [
            Slot(
                self._t.t("weather.now"),
                condition(current.code, current.is_day, self._t),
                self._uv(current.uv_index),
            )
        ]
        for hours_ahead in LATER_HOURS:
            hour = nearest_hour(forecast.hours, now + timedelta(hours=hours_ahead))
            if hour is not None:
                view.slots.append(
                    Slot(
                        self._t.hour(hour.time.hour),
                        condition(hour.code, hour.is_day, self._t),
                        self._uv(hour.uv_index),
                    )
                )
        return view

    def _uv(self, value: float | None) -> UvIndex | None:
        return None if value is None else uv_index(value, self._t)
