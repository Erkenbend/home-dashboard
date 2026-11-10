"""Behaviour of the departures widget, driven by recorded INSA HAFAS responses."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, DeparturesConfig, StopConfig
from tests.conftest import BERLIN
from tests.hafas_fake import HafasFake
from tests.html import departures_by_stop, lines

RANNISCHER_PLATZ = StopConfig(name="Rannischer Platz", id="5258", walk_minutes=5, via="5232")
FRANCKEPLATZ = StopConfig(name="Franckeplatz", id="5125", walk_minutes=10, via="8010159")


def config(*stops: StopConfig, max_per_stop: int = 5) -> AppConfig:
    return AppConfig(departures=DeparturesConfig(stops=list(stops), max_per_stop=max_per_stop))


@pytest.fixture
def hafas(respx_mock: respx.Router) -> HafasFake:
    return HafasFake(respx_mock)


@pytest.fixture
def show(
    make_client: Callable[..., TestClient], hafas: HafasFake
) -> Callable[..., dict[str, list[dict[str, str]]]]:
    """Render the departures widget for the given stops and return the visible rows per stop."""
    clients: dict[str, TestClient] = {}

    def _show(*stops: StopConfig, **kwargs) -> dict[str, list[dict[str, str]]]:
        key = repr((stops, sorted(kwargs.items())))
        if key not in clients:
            clients[key] = make_client(config(*stops, **kwargs))
        response = clients[key].get("/widgets/departures")
        assert response.status_code == 200
        return departures_by_stop(response.text)

    return _show


def test_shows_reachable_trams_with_minutes_until_departure_and_leaving(show) -> None:
    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert rows[0] == {
        "cancelled": False,
        "line": "1",
        "direction": "Gertraudenfriedhof",
        "time": "21:52",
        "minutes": "in 16 min",
        "leave": "los in 11 min",
    }
    assert lines(rows) == ["1", "95", "1", "95"]


def test_hides_trams_that_cannot_be_reached_on_foot(show, clock: FixedClock) -> None:
    # Rannischer Platz, 5 min walk: trams 1 and 95 at 21:52 just work at 21:47
    clock.instant = datetime(2026, 11, 9, 21, 47, tzinfo=BERLIN)

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert [(row["line"], row["time"]) for row in rows] == [
        ("1", "21:52"),
        ("95", "21:52"),
        ("1", "22:12"),
        ("95", "22:12"),
    ]
    assert rows[0]["leave"] == "jetzt los!"

    clock.instant = datetime(2026, 11, 9, 21, 48, tzinfo=BERLIN)
    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert [row["time"] for row in rows] == ["22:12", "22:12"]


def test_reachability_follows_the_clock_between_upstream_refreshes(
    show, clock: FixedClock, hafas: HafasFake
) -> None:
    clock.instant = datetime(2026, 11, 9, 21, 46, 45, tzinfo=BERLIN)
    show(RANNISCHER_PLATZ)
    clock.instant += timedelta(seconds=30)  # still cached

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert rows[0]["time"] == "22:12"
    assert hafas.departure_fetches == 1


def test_shows_only_trams(show) -> None:
    # The recorded board for Franckeplatz contains the buses 312, 320 and 380 as well
    rows = show(FRANCKEPLATZ)["Franckeplatz"]

    assert set(lines(rows)) <= {"7", "94"}


def test_asks_upstream_for_trams_passing_the_via_stop(show, hafas: HafasFake) -> None:
    show(RANNISCHER_PLATZ)

    request = hafas.requests[0]["svcReqL"][0]["req"]
    assert request["dirLoc"]["lid"] == "A=1@L=5232@"
    assert request["jnyFltrL"] == [{"type": "PROD", "mode": "INC", "value": "32"}]


def test_hides_trams_reaching_the_via_stop_only_after_changing_their_line(show) -> None:
    # Tram 94 leaves Franckeplatz towards Kröllwitz, i.e. away from the main station. HAFAS still
    # lists it "via Hauptbahnhof", because the vehicle returns as line 7 and passes it 40 min later.
    rows = show(FRANCKEPLATZ, max_per_stop=10)["Franckeplatz"]

    assert [(row["line"], row["direction"], row["time"]) for row in rows] == [
        ("7", "Büschdorf", "22:02"),
        ("7", "Büschdorf", "22:22"),
    ]


def test_hides_trams_that_passed_the_via_stop_before(show, hafas: HafasFake) -> None:
    # Like a line returning from its terminus: it passed Marktplatz before, but not afterwards
    tram_1 = hafas.journey("5258", "1", "215200")
    hafas.arrival("5232", tram_1["jid"])["stbStop"]["aTimeS"] = "214000"

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert [(row["line"], row["time"]) for row in rows] == [
        ("95", "21:52"),
        ("1", "22:12"),
        ("95", "22:12"),
    ]


def test_same_trip_at_two_platforms_is_shown_once(show, hafas: HafasFake) -> None:
    # A station board spans several stop points, so the same trip may show up twice in a row
    tram_7 = hafas.journey("5125", "7", "220200")
    hafas.journeys("5125").append({**tram_7, "stbStop": {**tram_7["stbStop"], "dTimeS": "220300"}})

    rows = show(FRANCKEPLATZ, max_per_stop=10)["Franckeplatz"]

    assert [(row["line"], row["time"]) for row in rows] == [("7", "22:02"), ("7", "22:22")]


def test_line_filter(show) -> None:
    only_95 = RANNISCHER_PLATZ.model_copy(update={"lines": ["95"]})

    rows = show(only_95)["Rannischer Platz"]

    assert lines(rows) == ["95", "95"]


def test_limits_departures_per_stop(show) -> None:
    rows = show(RANNISCHER_PLATZ, max_per_stop=2)["Rannischer Platz"]

    assert len(rows) == 2


def test_delayed_tram_shows_actual_time_with_delay_in_brackets(show, hafas: HafasFake) -> None:
    hafas.journey("5258", "1", "215200")["stbStop"]["dTimeR"] = "215500"

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    tram_1 = rows[1]
    assert (tram_1["line"], tram_1["time"], tram_1["minutes"]) == ("1", "21:55 (+3)", "in 19 min")


def test_cancelled_tram_is_marked(show, hafas: HafasFake) -> None:
    hafas.journey("5258", "95", "215200")["stbStop"]["dCncl"] = True

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert rows[1]["line"] == "95"
    assert rows[1]["cancelled"] is True
    assert rows[1]["status"] == "fällt aus"


def test_departure_after_midnight(show, hafas: HafasFake, clock: FixedClock) -> None:
    clock.instant = datetime(2026, 11, 9, 23, 58, tzinfo=BERLIN)
    template = hafas.journey("5258", "1", "215200")
    hafas.journeys("5258").clear()
    hafas.add_journey(
        "5258", template, via=("5232", "01001000"), dTimeS="01000600", dTimeR="01000700"
    )

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert [(row["time"], row["minutes"]) for row in rows] == [("00:07 (+1)", "in 9 min")]


def test_keeps_last_data_with_timestamp_when_upstream_fails(
    show, hafas: HafasFake, clock: FixedClock
) -> None:
    show(RANNISCHER_PLATZ)
    hafas.failing = True
    clock.instant += timedelta(minutes=2)

    rows = show(RANNISCHER_PLATZ)["Rannischer Platz"]

    assert lines(rows) == ["1", "95", "1", "95"]
    assert rows[0]["minutes"] == "in 14 min"


def test_stale_data_shows_stand_hint(
    make_client: Callable[..., TestClient], hafas: HafasFake, clock: FixedClock
) -> None:
    client = make_client(config(RANNISCHER_PLATZ))
    client.get("/widgets/departures")
    hafas.failing = True
    clock.instant += timedelta(minutes=2)

    html = client.get("/widgets/departures").text

    assert "Stand: 21:36" in html


def test_upstream_unavailable_from_start(
    make_client: Callable[..., TestClient], hafas: HafasFake
) -> None:
    hafas.failing = True
    client = make_client(config(RANNISCHER_PLATZ))

    page = client.get("/")

    assert page.status_code == 200
    assert "Keine Daten verfügbar" in page.text


def test_dashboard_embeds_departures_and_refreshes_them(
    make_client: Callable[..., TestClient], hafas: HafasFake
) -> None:
    page = make_client(config(RANNISCHER_PLATZ, FRANCKEPLATZ)).get("/").text

    assert 'hx-get="/widgets/departures"' in page
    assert set(departures_by_stop(page)) == {"Rannischer Platz", "Franckeplatz"}


def test_no_departures_widget_without_configured_stops(client: TestClient) -> None:
    assert "Abfahrten" not in client.get("/").text


def test_broken_upstream_is_not_asked_again_on_every_refresh(
    make_client: Callable[..., TestClient], hafas: HafasFake, clock: FixedClock
) -> None:
    hafas.failing = True
    client = make_client(config(RANNISCHER_PLATZ))

    client.get("/widgets/departures")
    clock.instant += timedelta(seconds=30)
    client.get("/widgets/departures")
    assert hafas.departure_fetches == 1

    hafas.failing = False
    clock.instant += timedelta(seconds=30)
    rows = departures_by_stop(client.get("/widgets/departures").text)["Rannischer Platz"]
    assert hafas.departure_fetches == 2
    assert lines(rows) == ["1", "95", "1", "95"]
