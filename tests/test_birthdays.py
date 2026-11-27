"""Behaviour of the birthdays widget: a separate iCal feed of yearly events (week of 2026-11-09)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, BirthdaysConfig, CalendarConfig
from tests.conftest import BERLIN, FIXTURES
from tests.html import birthdays
from tests.test_calendar import ICAL_URL, ICS

BIRTHDAYS_URL = "https://calendar.example/private-birthdays456/basic.ics"
BIRTHDAYS_ICS = (FIXTURES / "calendar" / "birthdays.ics").read_bytes()


def birthdays_config(**overrides) -> AppConfig:
    return AppConfig(birthdays=BirthdaysConfig(**{"ical_url": BIRTHDAYS_URL, **overrides}))


@pytest.fixture
def feed(respx_mock: respx.Router) -> respx.Route:
    return respx_mock.get(BIRTHDAYS_URL).mock(
        return_value=httpx.Response(200, content=BIRTHDAYS_ICS)
    )


@pytest.fixture
def monday_morning(clock: FixedClock) -> FixedClock:
    clock.instant = datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)
    return clock


@pytest.fixture
def client(make_client: Callable[..., TestClient], feed, monday_morning) -> TestClient:
    return make_client(birthdays_config())


def shown(client: TestClient) -> list[tuple[str, str]]:
    response = client.get("/widgets/birthdays")
    assert response.status_code == 200
    return [(occasion["day"], occasion["title"]) for occasion in birthdays(response.text)]


def test_shows_the_next_two_weeks_soonest_first(client: TestClient) -> None:
    assert shown(client) == [
        ("Heute", "Oma Geburtstag"),
        ("Morgen", "Alice Geburtstag"),
        ("Sa, 14.11.", "Anna Geburtstag"),
        ("Sa, 14.11.", "Bob Geburtstag"),
        ("Sa, 21.11.", "Hochzeitstag"),  # all-day before timed
        ("Sa, 21.11.", "18:00 Feier Hochzeitstag"),
    ]  # Onkel Paul (26.11.) is outside the window, Opa (29.09.) long past


def test_todays_occasions_are_highlighted(client: TestClient) -> None:
    today = [o["title"] for o in birthdays(client.get("/widgets/birthdays").text) if o["today"]]

    assert today == ["Oma Geburtstag"]


def test_number_of_days_is_configurable(
    make_client: Callable[..., TestClient], feed, monday_morning
) -> None:
    client = make_client(birthdays_config(days=3))

    assert [title for _, title in shown(client)] == ["Oma Geburtstag", "Alice Geburtstag"]


def test_window_moves_with_the_date(client: TestClient, clock: FixedClock) -> None:
    clock.instant = datetime(2026, 11, 21, 7, 0, tzinfo=BERLIN)

    assert shown(client)[:2] == [("Heute", "Hochzeitstag"), ("Heute", "18:00 Feier Hochzeitstag")]
    assert ("Do, 26.11.", "Onkel Paul Geburtstag") in shown(client)


def test_title_is_configurable(
    make_client: Callable[..., TestClient], feed, monday_morning
) -> None:
    client = make_client(birthdays_config(title="Jahrestage"))

    assert '<h2 class="widget-title">Jahrestage</h2>' in client.get("/widgets/birthdays").text


def test_nothing_coming_up(
    make_client: Callable[..., TestClient], respx_mock: respx.Router, clock: FixedClock
) -> None:
    clock.instant = datetime(2026, 12, 1, 10, 0, tzinfo=BERLIN)
    respx_mock.get(BIRTHDAYS_URL).mock(return_value=httpx.Response(200, content=BIRTHDAYS_ICS))

    html = make_client(birthdays_config()).get("/widgets/birthdays").text

    assert birthdays(html) == []
    assert "Keine in den nächsten 14 Tagen" in html


def test_dashboard_shows_birthdays_below_the_calendar_from_their_own_feed(
    make_client: Callable[..., TestClient], respx_mock: respx.Router, feed, monday_morning
) -> None:
    respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=ICS))
    config = birthdays_config().model_copy(update={"calendar": CalendarConfig(ical_url=ICAL_URL)})

    page = make_client(config).get("/").text

    assert page.index('id="calendar"') < page.index('id="birthdays"')
    assert 'hx-get="/widgets/birthdays" hx-trigger="every 300s"' in page
    assert "Fußballturnier" in page  # calendar
    assert "Alice Geburtstag" in page  # birthdays


@pytest.mark.parametrize(
    "config",
    [AppConfig(), birthdays_config(enabled=False)],
    ids=["without ical_url", "disabled"],
)
def test_no_widget_unless_enabled_with_ical_url(
    make_client: Callable[..., TestClient], feed, config: AppConfig
) -> None:
    client = make_client(config)

    assert 'id="birthdays"' not in client.get("/").text
    assert client.get("/widgets/birthdays").status_code == 404
    assert feed.call_count == 0


def test_feed_is_downloaded_at_most_every_hour(
    client: TestClient, feed: respx.Route, clock: FixedClock
) -> None:
    client.get("/widgets/birthdays")
    clock.instant += timedelta(minutes=50)
    client.get("/widgets/birthdays")
    assert feed.call_count == 1

    clock.instant += timedelta(minutes=11)
    client.get("/widgets/birthdays")
    assert feed.call_count == 2


def test_keeps_last_occasions_when_download_fails(
    client: TestClient, feed: respx.Route, clock: FixedClock
) -> None:
    client.get("/widgets/birthdays")
    feed.mock(return_value=httpx.Response(500))
    clock.instant += timedelta(hours=1)

    html = client.get("/widgets/birthdays").text

    assert "Alice Geburtstag" in html
    assert "Stand: 10:00" in html


def test_unavailable_feed_does_not_break_the_page_nor_leak_the_url(
    make_client: Callable[..., TestClient],
    respx_mock: respx.Router,
    monday_morning,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx_mock.get(BIRTHDAYS_URL).mock(side_effect=httpx.ConnectError("boom"))
    caplog.set_level(logging.WARNING)

    page = make_client(birthdays_config()).get("/")

    assert page.status_code == 200
    assert "Nicht verfügbar" in page.text
    assert "birthdays456" not in page.text
    assert "birthdays456" not in caplog.text
