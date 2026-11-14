"""Behaviour of the weather widget, driven by a recorded Open-Meteo response (2026-11-14 14:30)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, DeparturesConfig, HomeConfig, WeatherConfig
from tests.conftest import BERLIN
from tests.hafas_fake import HafasFake
from tests.html import weather
from tests.open_meteo_fake import OpenMeteoFake
from tests.test_departures import RANNISCHER_PLATZ

HOME = HomeConfig(lat=51.48, lon=11.97)
TOMORROW = date(2026, 11, 15)


def weather_config(**overrides) -> AppConfig:
    return AppConfig(home=HOME, weather=WeatherConfig(**overrides))


@pytest.fixture
def open_meteo(respx_mock: respx.Router) -> OpenMeteoFake:
    return OpenMeteoFake(respx_mock)


@pytest.fixture
def afternoon(clock: FixedClock) -> FixedClock:
    clock.instant = datetime(2026, 11, 14, 14, 40, tzinfo=BERLIN)
    return clock


@pytest.fixture
def client(make_client: Callable[..., TestClient], open_meteo, afternoon) -> TestClient:
    return make_client(weather_config())


def shown(client: TestClient) -> dict:
    response = client.get("/widgets/weather")
    assert response.status_code == 200
    return weather(response.text)


def test_shows_current_weather_in_german(client: TestClient) -> None:
    now = shown(client)["now"]

    assert now["temperature"] == "9°"  # 8.8 °C
    assert now["condition"] == "Teils bewölkt"
    assert now["apparent"] == "gefühlt 6°"
    assert now["icon"] == "partly-day"


def test_shows_today_and_tomorrow_with_highest_and_lowest_temperature(client) -> None:
    days = shown(client)["days"]

    assert [(d["label"], d["max"], d["min"], d["icon"]) for d in days] == [
        ("Heute", "9°", "2°", "partly-day"),
        ("Morgen", "9°", "1°", "rain"),  # light rain around noon
    ]


def test_coming_hours_start_with_the_next_full_hour(client: TestClient) -> None:
    hours = shown(client)["hours"]

    assert [(h["label"], h["temperature"]) for h in hours] == [
        ("15 Uhr", "9°"), ("16 Uhr", "8°"), ("17 Uhr", "7°"),
        ("18 Uhr", "6°"), ("19 Uhr", "5°"), ("20 Uhr", "4°"),
    ]  # fmt: skip
    assert hours[0]["precipitation"] == "0 %"


def test_night_hours_show_the_moon(client: TestClient) -> None:
    icons = [hour["icon"] for hour in shown(client)["hours"]]

    # sunset between 16 and 17 o'clock; codes 0 = clear, 1 = mainly clear
    assert icons[:4] == ["partly-day", "partly-day", "clear-night", "partly-night"]


def test_number_of_hours_is_configurable_and_continues_after_midnight(
    make_client: Callable[..., TestClient], open_meteo, clock: FixedClock
) -> None:
    clock.instant = datetime(2026, 11, 14, 22, 10, tzinfo=BERLIN)
    client = make_client(weather_config(hours=3))

    assert [hour["label"] for hour in shown(client)["hours"]] == ["23 Uhr", "0 Uhr", "1 Uhr"]


def test_likely_rain_stands_out(client: TestClient, open_meteo: OpenMeteoFake) -> None:
    open_meteo.set_hour(15, precipitation_probability=30)
    open_meteo.set_hour(16, precipitation_probability=50, weather_code=63)

    hours = shown(client)["hours"]

    assert hours[0]["precipitation"] == "30 %"
    assert "rain-likely" not in hours[0]["classes"]
    assert hours[1]["precipitation"] == "50 %"
    assert "rain-likely" in hours[1]["classes"]
    assert hours[1]["icon"] == "rain"


@pytest.mark.parametrize(
    ("code", "is_day", "condition", "icon"),
    [
        (0, 1, "Sonnig", "clear-day"),
        (0, 0, "Klar", "clear-night"),
        (3, 1, "Bedeckt", "cloudy"),
        (45, 1, "Nebel", "fog"),
        (53, 1, "Nieselregen", "drizzle"),
        (67, 1, "Gefrierender Regen", "sleet"),
        (75, 1, "Starker Schneefall", "snow"),
        (81, 1, "Regenschauer", "rain"),
        (99, 1, "Gewitter mit Hagel", "thunder"),
        (42, 1, "Unbekannt", "cloudy"),  # not a WMO code
    ],
)
def test_weather_codes_are_described_in_german(
    client: TestClient, open_meteo: OpenMeteoFake, code, is_day, condition, icon
) -> None:
    open_meteo.response["current"].update(weather_code=code, is_day=is_day)

    now = shown(client)["now"]

    assert (now["condition"], now["icon"]) == (condition, icon)


def test_temperatures_are_rounded_to_whole_degrees(client, open_meteo: OpenMeteoFake) -> None:
    open_meteo.response["current"].update(temperature_2m=-0.4, apparent_temperature=-2.5)

    now = shown(client)["now"]

    assert now["temperature"] == "0°"  # not "-0°"
    assert now["apparent"] == "gefühlt -2°"


def test_asks_for_the_home_location_in_local_time(client, open_meteo: OpenMeteoFake) -> None:
    shown(client)

    params = open_meteo.requests[0].url.params
    assert (params["latitude"], params["longitude"]) == ("51.48", "11.97")
    assert params["timezone"] == "Europe/Berlin"


def test_polls_within_the_fetch_interval_share_one_request(
    client: TestClient, open_meteo: OpenMeteoFake, afternoon: FixedClock
) -> None:
    shown(client)
    afternoon.instant += timedelta(minutes=5)  # tablet refresh
    client.get("/")  # second display
    assert len(open_meteo.requests) == 1

    afternoon.instant += timedelta(minutes=10)
    shown(client)
    assert len(open_meteo.requests) == 2


def test_hours_move_on_with_the_clock_between_fetches(client, afternoon: FixedClock) -> None:
    shown(client)
    afternoon.instant += timedelta(minutes=25)  # 15:05, forecast still cached

    assert shown(client)["hours"][0]["label"] == "16 Uhr"


def test_last_known_weather_is_shown_when_open_meteo_fails(
    client: TestClient, open_meteo: OpenMeteoFake, afternoon: FixedClock
) -> None:
    shown(client)
    open_meteo.failing = True
    afternoon.instant += timedelta(minutes=20)

    widget = shown(client)

    assert len(open_meteo.requests) == 2
    assert widget["now"]["temperature"] == "9°"
    assert widget["notices"] == ["Stand: 14:40"]


def test_notice_when_there_is_no_weather_yet(client: TestClient, open_meteo) -> None:
    open_meteo.failing = True

    widget = shown(client)

    assert widget["now"] is None
    assert widget["notices"] == ["Wetter nicht verfügbar"]


def test_unexpected_response_counts_as_unavailable(client: TestClient, open_meteo) -> None:
    del open_meteo.response["hourly"]

    assert shown(client)["notices"] == ["Wetter nicht verfügbar"]


@pytest.mark.parametrize(
    "config",
    [AppConfig(), AppConfig(home=HOME, weather=WeatherConfig(enabled=False))],
    ids=["no-location", "disabled"],
)
def test_no_weather_widget_without_location_or_when_disabled(
    make_client: Callable[..., TestClient], open_meteo: OpenMeteoFake, config: AppConfig
) -> None:
    client = make_client(config)

    assert 'id="weather"' not in client.get("/").text
    assert client.get("/widgets/weather").status_code == 404
    assert open_meteo.requests == []


def test_weather_is_placed_below_the_departures(
    make_client: Callable[..., TestClient], open_meteo, afternoon, respx_mock
) -> None:
    HafasFake(respx_mock)
    config = AppConfig(home=HOME, departures=DeparturesConfig(stops=[RANNISCHER_PLATZ]))

    page = make_client(config).get("/").text

    column = page[page.index('class="column') :]
    assert column.index('id="departures"') < column.index('id="weather"')
    assert 'hx-get="/widgets/weather"' in page
    assert "Teils bewölkt" in page
