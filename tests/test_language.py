"""UI languages: the catalogs in locales/ are complete, and the dashboard speaks the chosen one.

The other tests render German (the default); here the same widgets are rendered in English.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.app import create_app_from_env
from home_dashboard.clock import FixedClock
from home_dashboard.config import CONFIG_PATH_ENV, AppConfig, CalendarConfig, EveryoneConfig
from home_dashboard.i18n import (
    LANGUAGE_ENV,
    LOCALES_DIR,
    available_languages,
    flatten,
    load_translator,
    placeholders,
)
from home_dashboard.widgets.weather.service import UV_LEVELS, WMO_ICONS
from tests.conftest import BERLIN
from tests.hafas_fake import HafasFake
from tests.html import birthdays, calendar_days, departures_by_stop, services, weather
from tests.open_meteo_fake import OpenMeteoFake
from tests.services_fake import ServicesFake
from tests.test_birthdays import BIRTHDAYS_ICS, BIRTHDAYS_URL, birthdays_config
from tests.test_calendar import ICAL_URL, ICS, calendar_config
from tests.test_departures import RANNISCHER_PLATZ
from tests.test_departures import config as departures_config
from tests.test_status import NAS, status_config
from tests.test_weather import weather_config

REFERENCE = "de"
OTHERS = [language for language in available_languages() if language != REFERENCE]


def catalog(language: str) -> dict:
    with (LOCALES_DIR / f"{language}.toml").open("rb") as file:
        return flatten(tomllib.load(file))


# --- The catalogs -------------------------------------------------------------------------------


def test_german_and_english_are_available() -> None:
    assert {"de", "en"} <= set(available_languages())


@pytest.mark.parametrize("language", OTHERS)
def test_every_catalog_has_the_texts_and_placeholders_of_the_german_one(language: str) -> None:
    """What a translator has forgotten, misspelt or added (de.toml is the reference)."""
    reference, texts = catalog(REFERENCE), catalog(language)

    assert sorted(reference.keys() - texts.keys()) == [], f"missing in {language}.toml"
    assert sorted(texts.keys() - reference.keys()) == [], f"not in {REFERENCE}.toml"
    for key, original in reference.items():
        text = texts[key]
        assert type(text) is type(original), key
        if isinstance(original, list):
            assert len(text) == len(original), key
        else:
            assert placeholders(text) == placeholders(original), key


@pytest.mark.parametrize("language", available_languages())
def test_every_text_can_be_filled_in(language: str) -> None:
    """No broken {placeholder} syntax; numbers fit the format specs of the date patterns."""
    for key, text in catalog(language).items():
        if isinstance(text, str):
            try:
                text.format(**dict.fromkeys(placeholders(text), 1))
            except (ValueError, IndexError, KeyError) as error:
                pytest.fail(f"{language}.toml, {key}: {error}")


def test_the_reference_catalog_covers_every_weather_code_and_uv_level() -> None:
    texts = catalog(REFERENCE)

    assert {f"weather.conditions.{code}" for code in WMO_ICONS} <= texts.keys()
    assert {f"weather.uv_levels.{level}" for _, level in UV_LEVELS} <= texts.keys()
    assert len(texts["dates.weekdays"]) == len(texts["dates.weekdays_short"]) == 7
    assert len(texts["dates.months"]) == 12


def test_an_unknown_language_fails_with_the_available_ones() -> None:
    with pytest.raises(ValueError, match=r"'xx' is not available, available: de, en"):
        load_translator("xx")
    with pytest.raises(ValueError, match="not available"):
        load_translator("../config")


# --- The dashboard in English -------------------------------------------------------------------


@pytest.fixture
def english(make_client: Callable[..., TestClient]) -> Callable[[AppConfig], TestClient]:
    return lambda config: make_client(config, language="en")


@pytest.fixture
def monday_morning(clock: FixedClock) -> FixedClock:
    clock.instant = datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)
    return clock


def test_page_language_date_and_offline_notice(english) -> None:
    page = english(AppConfig()).get("/").text

    assert '<html lang="en">' in page
    assert "Monday, 9 November 2026" in page
    assert "No connection since <span data-offline-since></span>" in page
    assert 'title="Source code on GitHub"' in page


def test_departures(english, respx_mock: respx.Router) -> None:
    HafasFake(respx_mock)

    html = english(departures_config(RANNISCHER_PLATZ)).get("/widgets/departures").text

    assert "Departures</h2>" in html
    assert "5 min walk" in html
    first = departures_by_stop(html)["Rannischer Platz"][0]
    assert (first["minutes"], first["leave"]) == ("in 16 min", "leave in 11 min")


def test_calendar(english, respx_mock: respx.Router, monday_morning) -> None:
    respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=ICS))

    days = calendar_days(english(calendar_config()).get("/widgets/calendar").text)

    assert list(days)[:3] == ["Today", "Tomorrow", "Wed 11/11"]
    times = [event["time"] for events in days.values() for event in events]
    assert {"08:00–09:00", "all day", "day 1/3", "from 18:00", "until 10:00"} <= set(times)


def test_birthdays(english, respx_mock: respx.Router, monday_morning) -> None:
    respx_mock.get(BIRTHDAYS_URL).mock(return_value=httpx.Response(200, content=BIRTHDAYS_ICS))

    html = english(birthdays_config()).get("/widgets/birthdays").text

    assert "Birthdays &amp; more</h2>" in html
    shown = {occasion["name"]: (occasion["day"], occasion["years"]) for occasion in birthdays(html)}
    assert shown["Oma Erna"] == ("Today", "turns 70")
    assert shown["Mia"] == ("Tomorrow", "turns 4")
    assert shown["Max Muster"] == ("Sat 21/11", "14 years")


def test_weather(english, respx_mock: respx.Router, clock: FixedClock) -> None:
    OpenMeteoFake(respx_mock)
    clock.instant = datetime(2026, 11, 14, 14, 40, tzinfo=BERLIN)
    english_texts = catalog("en")

    shown = weather(english(weather_config()).get("/widgets/weather").text)

    assert set(shown["temperatures"]) == {"actual", "feels like"}
    assert [slot["label"] for slot in shown["slots"]] == ["now", "16:00", "17:00"]
    conditions = {text for key, text in english_texts.items() if key.startswith("weather.cond")}
    assert {slot["condition"] for slot in shown["slots"]} <= conditions | {"Sunny"}
    uv_labels = {text for key, text in english_texts.items() if key.startswith("weather.uv_")}
    assert {uv["label"] for uv in shown["uv"] if uv} <= uv_labels


def test_service_tooltips(english, respx_mock: respx.Router, clock: FixedClock) -> None:
    health = ServicesFake(respx_mock)
    for service in status_config().status.services:
        health.add(service.url)
    health.answer(NAS, 503)

    shown = {
        service["name"]: service["title"]
        for service in services(english(status_config()).get("/widgets/status").text)
    }

    assert shown["Pi-hole"] == "Pi-hole: reachable"
    assert shown["NAS"] == "NAS: last check failed"


def test_default_labels_follow_the_language_and_configured_ones_win(
    english, make_client, respx_mock: respx.Router, monday_morning
) -> None:
    respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=ICS))
    respx_mock.get(BIRTHDAYS_URL).mock(return_value=httpx.Response(200, content=BIRTHDAYS_ICS))
    defaults = AppConfig(
        calendar=CalendarConfig(ical_url=ICAL_URL),
        birthdays=birthdays_config().birthdays,
    )
    configured = defaults.model_copy(
        update={
            "calendar": CalendarConfig(ical_url=ICAL_URL, everyone=EveryoneConfig(label="Family")),
            "birthdays": birthdays_config(title="Parties").birthdays,
        }
    )

    def legend_and_title(client: TestClient) -> tuple[str, str]:
        first_day = next(iter(calendar_days(client.get("/widgets/calendar").text).values()))
        everyone = first_day[0]["people"][0]
        title = client.get("/widgets/birthdays").text.split("</h2>")[0].rsplit(">", 1)[1]
        return everyone, title

    assert legend_and_title(english(defaults)) == ("Everyone", "Birthdays &amp; more")
    assert legend_and_title(make_client(defaults)) == ("Alle", "Geburtstage &amp; mehr")
    assert legend_and_title(english(configured)) == ("Family", "Parties")


def test_the_language_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("{}\n")
    monkeypatch.setenv(CONFIG_PATH_ENV, str(config))

    monkeypatch.setenv(LANGUAGE_ENV, "en")
    assert '<html lang="en">' in TestClient(create_app_from_env()).get("/").text

    monkeypatch.delenv(LANGUAGE_ENV)
    assert '<html lang="de">' in TestClient(create_app_from_env()).get("/").text

    monkeypatch.setenv(LANGUAGE_ENV, "xx")
    with pytest.raises(ValueError, match="'xx' is not available"):
        create_app_from_env()
