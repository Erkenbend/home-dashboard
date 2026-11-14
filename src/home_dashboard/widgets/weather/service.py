"""Weather widget logic: now, today/tomorrow and the coming hours, in German."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from home_dashboard.cache import TtlCache, fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import WeatherConfig
from home_dashboard.widgets.weather.source import WeatherSource

log = logging.getLogger(__name__)

RAIN_LIKELY_PERCENT = 50

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
class NowRow:
    temperature: int
    apparent_temperature: int
    condition: Condition


@dataclass(frozen=True)
class DayRow:
    label: str
    condition: Condition
    temperature_min: int
    temperature_max: int


@dataclass(frozen=True)
class HourRow:
    label: str
    temperature: int
    condition: Condition
    precipitation_probability: int | None
    rain_likely: bool


@dataclass
class WeatherView:
    now: NowRow | None = None
    days: list[DayRow] = field(default_factory=list)
    hours: list[HourRow] = field(default_factory=list)
    fetched_at: datetime | None = None
    stale: bool = False
    unavailable: bool = False


class WeatherService:
    def __init__(
        self,
        config: WeatherConfig,
        source: WeatherSource,
        clock: Clock,
        cache: TtlCache,
        timezone: str,
    ) -> None:
        self._config = config
        self._source = source
        self._clock = clock
        self._cache = cache
        self._tz = ZoneInfo(timezone)

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
        now = self._clock.now().astimezone(self._tz)
        today = now.date()
        view.fetched_at = cached.fetched_at
        view.stale = cached.stale
        view.now = NowRow(
            temperature=degrees(forecast.current.temperature),
            apparent_temperature=degrees(forecast.current.apparent_temperature),
            condition=condition(forecast.current.code, forecast.current.is_day),
        )
        labels = {today: "Heute", today + timedelta(days=1): "Morgen"}
        view.days = [
            DayRow(
                label=labels[day.day],
                condition=condition(day.code),
                temperature_min=degrees(day.temperature_min),
                temperature_max=degrees(day.temperature_max),
            )
            for day in forecast.days
            if day.day in labels
        ]
        upcoming = [hour for hour in forecast.hours if hour.time > now]
        view.hours = [
            HourRow(
                label=f"{hour.time.astimezone(self._tz).hour} Uhr",
                temperature=degrees(hour.temperature),
                condition=condition(hour.code, hour.is_day),
                precipitation_probability=hour.precipitation_probability,
                rain_likely=(hour.precipitation_probability or 0) >= RAIN_LIKELY_PERCENT,
            )
            for hour in upcoming[: self._config.hours]
        ]
        return view
