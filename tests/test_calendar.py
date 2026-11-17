"""Behaviour of the calendar widget, driven by a Google-like iCal fixture (week of 2026-11-09)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, CalendarConfig, EveryoneConfig, PersonConfig
from tests.conftest import BERLIN, FIXTURES
from tests.html import calendar_days, titles

ICAL_URL = "https://calendar.example/private-secret123/basic.ics"
ICS = (FIXTURES / "calendar" / "family.ics").read_bytes()

ALICE = PersonConfig(name="Alice", color="#e07a5f", match=["Alice"])
BOB = PersonConfig(name="Bob", color="#3d85c6", match=["bob"])
EVERYONE = EveryoneConfig(label="Alle", color="#c9b458", match=["Familie"])


def calendar_config(**overrides) -> AppConfig:
    settings = {
        "ical_url": ICAL_URL,
        "days": 7,
        "people": [ALICE, BOB],
        "everyone": EVERYONE,
        **overrides,
    }
    return AppConfig(calendar=CalendarConfig(**settings))


@pytest.fixture
def ical(respx_mock: respx.Router) -> respx.Route:
    return respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=ICS))


@pytest.fixture
def monday_morning(clock: FixedClock) -> FixedClock:
    clock.instant = datetime(2026, 11, 9, 10, 0, tzinfo=BERLIN)
    return clock


@pytest.fixture
def client(make_client: Callable[..., TestClient], ical, monday_morning) -> TestClient:
    return make_client(calendar_config())


@pytest.fixture
def days(client: TestClient) -> dict[str, list[dict]]:
    response = client.get("/widgets/calendar")
    assert response.status_code == 200
    return calendar_days(response.text)


def test_shows_the_coming_seven_days_grouped_with_german_labels(days) -> None:
    assert list(days) == [
        "Heute", "Morgen", "Mi, 11.11.", "Do, 12.11.", "Fr, 13.11.", "Sa, 14.11.", "So, 15.11."
    ]  # fmt: skip
    assert "Alice Konzert" not in str(days)  # 20.11. is outside the window


def test_events_of_a_day_with_times_all_day_first(days) -> None:
    assert [(e["time"], e["title"]) for e in days["Morgen"]] == [
        ("ganztägig", "Müllabfuhr"),
        ("20:00–21:00", "Yoga (später)"),
    ]


def test_start_time_is_emphasized(days) -> None:
    def start_of(day: str, title: str) -> str:
        return next(e["start"] for e in days[day] if e["title"] == title)

    assert start_of("Morgen", "Yoga (später)") == "20:00"
    assert start_of("Fr, 13.11.", "Übernachtung bei Max") == "18:00"  # "ab 18:00"
    assert start_of("Sa, 14.11.", "Übernachtung bei Max") == ""  # "bis 10:00"
    assert start_of("Morgen", "Müllabfuhr") == ""


def test_past_events_of_today_are_marked(days) -> None:
    today = {event["title"]: event["past"] for event in days["Heute"]}

    assert today == {
        "Zahnarzt": True,
        "Fußballturnier": False,
        "Bobbycar-Rennen im Park": False,
    }


def test_events_are_assigned_to_people_by_title(days) -> None:
    people = {e["title"]: e["people"] for day in days.values() for e in day}

    assert people["Zahnarzt"] == ["Alice"]
    assert people["Fußballturnier"] == ["Bob"]  # keywords are case-insensitive
    assert people["Klassenfahrt Alice und Bob"] == ["Alice", "Bob"]


def test_leading_keywords_are_replaced_by_the_names_at_the_end(days) -> None:
    shown = {(e["title"], e["names"]) for day in days.values() for e in day}

    assert ("Zahnarzt", "(Alice)") in shown  # "Alice: Zahnarzt"
    assert ("Fußballturnier", "(Bob)") in shown  # "Bob Fußballturnier"
    assert ("Elternabend Bob", "(Bob)") in shown  # not leading: title stays
    assert ("Klassenfahrt Alice und Bob", "(Alice, Bob)") in shown
    assert ("Omas Geburtstag", "") in shown  # "Familie: Omas Geburtstag", no names for everyone
    assert ("Bobbycar-Rennen im Park", "") in shown


def test_events_for_everyone_by_keyword_or_without_recognized_person(days) -> None:
    events = {e["title"]: e for day in days.values() for e in day}

    for title in ["Omas Geburtstag", "Müllabfuhr", "Bobbycar-Rennen im Park"]:
        assert events[title]["everyone"], title
        assert events[title]["people"] == ["Alle"], title
    assert not events["Klassenfahrt Alice und Bob"]["everyone"]


def test_recurring_and_single_events_are_distinguished(days) -> None:
    events = {e["title"]: e["recurring"] for day in days.values() for e in day}

    assert events["Sonntagsessen"] is True
    assert events["Yoga (später)"] is True  # moved occurrence of a series
    assert events["Zahnarzt"] is False
    assert events["Klassenfahrt Alice und Bob"] is False


def test_excluded_occurrence_of_a_series_is_not_shown(days) -> None:
    assert "Yoga" not in titles(days["Do, 12.11."])


def test_multi_day_events(days) -> None:
    def time_of(day: str, title: str) -> str:
        return next(e["time"] for e in days[day] if e["title"] == title)

    trip = "Klassenfahrt Alice und Bob"
    assert [time_of(d, trip) for d in ["Do, 12.11.", "Fr, 13.11.", "Sa, 14.11."]] == [
        "Tag 1/3", "Tag 2/3", "Tag 3/3"
    ]  # fmt: skip
    sleepover = "Übernachtung bei Max"
    assert time_of("Fr, 13.11.", sleepover) == "ab 18:00"
    assert time_of("Sa, 14.11.", sleepover) == "bis 10:00"


def test_utc_times_are_shown_in_local_time(days) -> None:
    assert [(e["time"], e["title"]) for e in days["Mi, 11.11."]] == [
        ("18:00–19:30", "Elternabend Bob")
    ]


def test_days_without_events_are_skipped_but_today_is_always_shown(
    make_client: Callable[..., TestClient], ical, clock: FixedClock
) -> None:
    clock.instant = datetime(2026, 11, 16, 9, 0, tzinfo=BERLIN)

    html = make_client(calendar_config()).get("/widgets/calendar").text

    days = calendar_days(html)
    assert list(days) == ["Heute", "Morgen", "Do, 19.11.", "Fr, 20.11.", "So, 22.11."]
    assert days["Heute"] == []
    assert "Keine Termine" in html


@pytest.mark.parametrize(
    ("summary", "title", "names"),
    [
        ("A - Zahnarzt", "Zahnarzt", "(Alice)"),
        ("A-Zahnarzt", "Zahnarzt", "(Alice)"),
        ("A-N- Kino", "Kino", "(Alice, Nina)"),
        ("Alle: Ausflug", "Ausflug", ""),
        ("A-", "A-", "(Alice)"),  # nothing left: keep the title
    ],
)
def test_prefix_styles(
    make_client: Callable[..., TestClient],
    respx_mock: respx.Router,
    monday_morning,
    summary: str,
    title: str,
    names: str,
) -> None:
    respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=single_event(summary)))
    people = [
        PersonConfig(name="Alice", color="#e07a5f", match=["A-", "A -"]),
        PersonConfig(name="Nina", color="#3d85c6", match=["N-", "N -"]),
    ]
    everyone = EveryoneConfig(match=["Alle"])
    client = make_client(calendar_config(people=people, everyone=everyone))

    [event] = calendar_days(client.get("/widgets/calendar").text)["Heute"]

    assert (event["title"], event["names"]) == (title, names)


def single_event(summary: str) -> bytes:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:single@test\r\n"
        f"SUMMARY:{summary}\r\nDTSTART;VALUE=DATE:20261109\r\nDTEND;VALUE=DATE:20261110\r\n"
        "DTSTAMP:20261101T120000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


def test_legend_lists_people_and_everyone(client: TestClient) -> None:
    html = client.get("/widgets/calendar").text

    for name in ["Alice", "Bob", "Alle"]:
        assert f"{name}</span>" in html


def test_calendar_is_downloaded_at_most_every_ten_minutes(
    client: TestClient, ical: respx.Route, clock: FixedClock
) -> None:
    client.get("/widgets/calendar")
    clock.instant += timedelta(minutes=5)
    client.get("/widgets/calendar")
    assert ical.call_count == 1

    clock.instant += timedelta(minutes=6)
    client.get("/widgets/calendar")
    assert ical.call_count == 2


def test_keeps_last_events_when_download_fails(
    client: TestClient, ical: respx.Route, clock: FixedClock
) -> None:
    client.get("/widgets/calendar")
    ical.mock(return_value=httpx.Response(500))
    clock.instant += timedelta(minutes=11)

    html = client.get("/widgets/calendar").text

    assert "Fußballturnier" in html
    assert "Stand: 10:00" in html


def test_unavailable_calendar_does_not_break_the_page_nor_leak_the_url(
    make_client: Callable[..., TestClient],
    respx_mock: respx.Router,
    monday_morning,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx_mock.get(ICAL_URL).mock(side_effect=httpx.ConnectError("boom"))
    caplog.set_level(logging.WARNING)

    page = make_client(calendar_config()).get("/")

    assert page.status_code == 200
    assert "Kalender nicht verfügbar" in page.text
    assert "secret123" not in page.text
    assert "secret123" not in caplog.text


def test_dashboard_embeds_calendar_and_refreshes_it(client: TestClient) -> None:
    page = client.get("/").text

    assert 'hx-get="/widgets/calendar"' in page
    assert "Fußballturnier" in page


def test_no_calendar_widget_without_ical_url(make_client: Callable[..., TestClient]) -> None:
    client = make_client(AppConfig())

    assert "Termine" not in client.get("/").text
    assert client.get("/widgets/calendar").status_code == 404
