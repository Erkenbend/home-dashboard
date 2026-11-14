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


def test_shows_temperature_now_and_the_weather_now_in_one_and_in_two_hours(client) -> None:
    widget = shown(client)

    assert (widget["apparent"], widget["actual"]) == ("6°", "echt: 9°C")  # felt 6.0, measured 8.8
    assert [(slot["label"], slot["icon"]) for slot in widget["slots"]] == [
        ("jetzt", "partly-day"),
        ("16 Uhr", "partly-day"),  # 14:40 + 1 h = 15:40 -> nearest full hour
        ("17 Uhr", "clear-night"),  # after sunset
    ]


@pytest.mark.parametrize(
    ("time", "hours"),
    [((14, 29), (15, 16)), ((14, 30), (16, 17)), ((14, 0), (15, 16))],
    ids=["round-down", "half-past-rounds-up", "full-hour"],
)
def test_later_weather_is_the_forecast_for_the_nearest_full_hour(
    client: TestClient, open_meteo: OpenMeteoFake, afternoon: FixedClock, time, hours
) -> None:
    afternoon.instant = afternoon.instant.replace(hour=time[0], minute=time[1])
    open_meteo.set_hour(hours[0], weather_code=63)  # rain
    open_meteo.set_hour(hours[1], weather_code=75)  # snow

    later = [slot["icon"] for slot in shown(client)["slots"][1:]]

    assert later == ["rain", "snow"]


def test_later_weather_continues_after_midnight(
    make_client: Callable[..., TestClient], open_meteo: OpenMeteoFake, clock: FixedClock
) -> None:
    clock.instant = datetime(2026, 11, 14, 23, 10, tzinfo=BERLIN)
    open_meteo.set_hour(1, TOMORROW, weather_code=45)

    slots = shown(make_client(weather_config()))["slots"]

    assert [slot["label"] for slot in slots] == ["jetzt", "0 Uhr", "1 Uhr"]
    assert slots[2]["condition"] == "Nebel"


def test_later_weather_is_left_out_beyond_the_forecast(client, open_meteo: OpenMeteoFake) -> None:
    hourly = open_meteo.response["hourly"]
    hourly["weather_code"][open_meteo.hour(17) :] = [None] * len(
        hourly["weather_code"][open_meteo.hour(17) :]
    )

    assert [slot["label"] for slot in shown(client)["slots"]] == ["jetzt", "16 Uhr"]


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

    now = shown(client)["slots"][0]

    assert (now["condition"], now["icon"]) == (condition, icon)


def test_temperatures_are_rounded_to_whole_degrees(client, open_meteo: OpenMeteoFake) -> None:
    open_meteo.response["current"].update(temperature_2m=-0.4, apparent_temperature=-2.5)

    widget = shown(client)

    assert widget["actual"] == "echt: 0°C"  # not "-0°C"
    assert widget["apparent"] == "-2°"  # half rounds up


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


def test_later_weather_moves_on_with_the_clock_between_fetches(client, afternoon) -> None:
    afternoon.instant = afternoon.instant.replace(minute=20)
    assert [slot["icon"] for slot in shown(client)["slots"][1:]] == ["partly-day", "partly-day"]

    afternoon.instant += timedelta(minutes=10)  # 14:30, forecast still cached

    # 15:30 -> 16 o'clock, 16:30 -> 17 o'clock, after sunset
    assert [slot["icon"] for slot in shown(client)["slots"][1:]] == ["partly-day", "clear-night"]


def test_last_known_weather_is_shown_when_open_meteo_fails(
    client: TestClient, open_meteo: OpenMeteoFake, afternoon: FixedClock
) -> None:
    shown(client)
    open_meteo.failing = True
    afternoon.instant += timedelta(minutes=20)

    widget = shown(client)

    assert len(open_meteo.requests) == 2
    assert widget["actual"] == "echt: 9°C"
    assert widget["notices"] == ["Stand: 14:40"]


def test_notice_when_there_is_no_weather_yet(client: TestClient, open_meteo) -> None:
    open_meteo.failing = True

    widget = shown(client)

    assert widget["apparent"] is None
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
