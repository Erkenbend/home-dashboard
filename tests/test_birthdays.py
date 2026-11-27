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
from tests.test_calendar import feed as feed_of

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
    return make_client(birthdays_config(ignore_contacts=["geburtstagsliste"]))


def shown(client: TestClient) -> list[dict]:
    response = client.get("/widgets/birthdays")
    assert response.status_code == 200
    return birthdays(response.text)


def names(client: TestClient) -> list[tuple[str, str]]:
    return [(occasion["day"], occasion["name"]) for occasion in shown(client)]


def test_shows_the_next_two_weeks_soonest_first(client: TestClient) -> None:
    assert names(client) == [
        ("Heute", "Oma Erna"),
        ("Morgen", "Mia"),
        ("Fr, 13.11.", "Namenstag"),
        ("Sa, 14.11.", "Finn (Sohn Tom)"),
        ("Sa, 14.11.", "Lea Beispiel"),
        ("So, 15.11.", "Opa"),
        ("Sa, 21.11.", "Max Muster"),  # all-day before timed
        ("Sa, 21.11.", "Grillfest"),
    ]  # Onkel Paul (26.11.) is outside the window, Opa Kurt (29.09.) long past


def test_contacts_birthdays_special_events_and_anniversaries(client: TestClient) -> None:
    occasions = {o["name"]: (o["kind"], o["contact"], o["years"]) for o in shown(client)}

    assert occasions == {
        "Oma Erna": ("birthday", "", "wird 70"),  # "Heute hat Oma Erna Geburtstag!"
        "Mia": ("birthday", "(Max Muster)", "wird 4"),  # a special event of the contact Max
        "Namenstag": ("other", "(Lea Beispiel)", ""),  # "Jahr: unbekannt"
        "Finn (Sohn Tom)": ("birthday", "", "wird 5"),  # contact ignored by the config
        "Lea Beispiel": ("birthday", "", ""),
        "Opa": ("birthday", "", ""),  # entered by hand: "Opa Geburtstag", no description
        "Max Muster": ("anniversary", "", "14 Jahre"),
        "Grillfest": ("other", "", ""),
    }


def test_timed_events_show_their_start(client: TestClient) -> None:
    times = {o["name"]: o["time"] for o in shown(client) if o["time"]}

    assert times == {"Grillfest": "18:00"}


@pytest.mark.parametrize(
    ("summary", "description", "expected"),
    [
        ("Geburtstag Max", "", ("birthday", "Max")),
        ("Geburtstag: Max", "", ("birthday", "Max")),
        ("Max Geburtstag", "", ("birthday", "Max")),
        ("Hochzeitstag Alice & Bob", "", ("anniversary", "Alice & Bob")),
        ("Alice & Bob: Jahrestag", "", ("anniversary", "Alice & Bob")),
        ("Kita-Fest", "", ("other", "Kita-Fest")),
        # the description wins: the summary does not say who "(Lea)" is
        ("Geburtstag Mia (Lea)", "Besonderes Ereignis: Geburtstag Mia (aus Lea)\\nJahr: 2020",
         ("birthday", "Mia (Lea)")),
    ],
)  # fmt: skip
def test_kind_and_name_from_summary_or_description(
    make_client: Callable[..., TestClient],
    respx_mock: respx.Router,
    monday_morning,
    summary: str,
    description: str,
    expected: tuple[str, str],
) -> None:
    lines = [f"SUMMARY:{summary}", "DTSTART;VALUE=DATE:20261109"]
    lines += [f"DESCRIPTION:{description}"] if description else []
    respx_mock.get(BIRTHDAYS_URL).mock(
        return_value=httpx.Response(200, content=feed_of("\n".join(lines)))
    )

    [occasion] = shown(make_client(birthdays_config()))

    name = " ".join(filter(None, [occasion["name"], occasion["contact"]]))
    assert (occasion["kind"], name) == expected


def test_todays_occasions_are_highlighted(client: TestClient) -> None:
    assert [o["name"] for o in shown(client) if o["today"]] == ["Oma Erna"]


def test_number_of_days_is_configurable(
    make_client: Callable[..., TestClient], feed, monday_morning
) -> None:
    client = make_client(birthdays_config(days=3))

    assert [name for _, name in names(client)] == ["Oma Erna", "Mia"]


def test_window_moves_with_the_date(client: TestClient, clock: FixedClock) -> None:
    clock.instant = datetime(2026, 11, 21, 7, 0, tzinfo=BERLIN)

    assert names(client)[:2] == [("Heute", "Max Muster"), ("Heute", "Grillfest")]
    assert ("Do, 26.11.", "Onkel Paul") in names(client)


def test_default_title_covers_more_than_birthdays(
    make_client: Callable[..., TestClient], feed, monday_morning
) -> None:
    html = make_client(birthdays_config()).get("/widgets/birthdays").text

    assert '<h2 class="widget-title">Geburtstage &amp; mehr</h2>' in html


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
    assert "Mia" in page  # birthdays


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

    assert "Oma Erna" in html
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
