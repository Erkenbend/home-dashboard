"""Application configuration, loaded from a YAML file (see config.example.yaml)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

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
    id: str = Field(description="HAFAS location id (lid), look up with `home-dashboard find-stop`")
    walk_minutes: int = Field(ge=0)
    via: str | None = Field(
        default=None, description="lid of a stop the trip must pass later (direction filter)"
    )
    lines: list[str] | None = None


class DeparturesConfig(_Strict):
    max_per_stop: int = Field(default=5, ge=1)
    products: list[Literal["tram", "bus", "suburban", "regional"]] = ["tram"]
    stops: list[StopConfig] = []


class PersonConfig(_Strict):
    name: str
    color: str
    match: list[str]


class CalendarConfig(_Strict):
    ical_url: str | None = None
    days: int = Field(default=7, ge=1)
    people: list[PersonConfig] = []


class AppConfig(_Strict):
    timezone: str = "Europe/Berlin"
    home: HomeConfig = HomeConfig()
    departures: DeparturesConfig = DeparturesConfig()
    calendar: CalendarConfig = CalendarConfig()


def load_config(path: str | Path) -> AppConfig:
    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return AppConfig.model_validate(data)


def config_path_from_env() -> Path:
    return Path(os.environ.get(CONFIG_PATH_ENV, DEFAULT_CONFIG_PATH))
