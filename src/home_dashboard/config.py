"""Application configuration, loaded from a YAML file (see config.example.yaml)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = "config.yaml"
CONFIG_PATH_ENV = "HOME_DASHBOARD_CONFIG"
DEFAULT_PORT = 3274  # T9 for "DASH"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HomeConfig(_Strict):
    address: str | None = None
    lat: float | None = None
    lon: float | None = None


class StopConfig(_Strict):
    name: str
    id: str = Field(description="stop id, look up with `home-dashboard find-stop`")
    walk_minutes: int = Field(ge=0)
    via: str | None = Field(
        default=None, description="id of a stop the trip must pass later (direction filter)"
    )
    lines: list[str] | None = None
    direction: str | None = Field(
        default=None,
        description="direction label shown next to the stop name; replaces the per-departure "
        "destination, so only the line number is shown",
    )


class DisplayConfig(_Strict):
    clock_refresh_seconds: int = Field(default=15, ge=1)
    page_reload_hours: float = Field(
        default=6, ge=0, description="full page reload as safety net for kiosk browsers, 0 = off"
    )


class DeparturesConfig(_Strict):
    refresh_seconds: int = Field(
        default=30, ge=5, description="how often the tablet updates the widget (countdowns)"
    )
    fetch_seconds: int = Field(
        default=60, ge=15, description="how often the Pi asks the transit API at most"
    )
    max_per_stop: int = Field(
        default=8, ge=1, description="upper limit, the display shows as many as fit"
    )
    products: list[Literal["tram", "bus", "suburban", "regional"]] = ["tram"]
    stops: list[StopConfig] = []


Color = Annotated[str, Field(pattern=r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]+)$")]


class PersonConfig(_Strict):
    name: str
    color: Color
    match: list[str] = Field(description="keywords in event titles (case-insensitive, whole words)")


class EveryoneConfig(_Strict):
    """Events for everyone: titles with one of these keywords, or without any person keyword."""

    label: str = "Alle"
    color: Color = "#c9b458"
    match: list[str] = []


class CalendarConfig(_Strict):
    ical_url: str | None = None
    days: int = Field(default=14, ge=1, description="upper limit, the display shows as many as fit")
    refresh_seconds: int = Field(default=300, ge=5, description="how often the tablet updates")
    fetch_seconds: int = Field(
        default=600, ge=60, description="how often the Pi downloads the iCal feed at most"
    )
    people: list[PersonConfig] = []
    everyone: EveryoneConfig = EveryoneConfig()


class WeatherConfig(_Strict):
    """Weather at home.lat / home.lon; the widget is shown only if both are set."""

    enabled: bool = True
    hours: int = Field(default=6, ge=1, le=24, description="hourly forecasts after now")
    refresh_seconds: int = Field(default=300, ge=5, description="how often the tablet updates")
    fetch_seconds: int = Field(
        default=900, ge=300, description="how often the Pi asks the weather service at most"
    )


class AppConfig(_Strict):
    timezone: str = "Europe/Berlin"
    display: DisplayConfig = DisplayConfig()
    home: HomeConfig = HomeConfig()
    departures: DeparturesConfig = DeparturesConfig()
    calendar: CalendarConfig = CalendarConfig()
    weather: WeatherConfig = WeatherConfig()

    @property
    def weather_location(self) -> tuple[float, float] | None:
        """(lat, lon) of the weather widget, None if it is off."""
        if not self.weather.enabled or self.home.lat is None or self.home.lon is None:
            return None
        return (self.home.lat, self.home.lon)


def load_config(path: str | Path) -> AppConfig:
    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return AppConfig.model_validate(data)


def config_path_from_env() -> Path:
    return Path(os.environ.get(CONFIG_PATH_ENV, DEFAULT_CONFIG_PATH))
