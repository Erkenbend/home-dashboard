"""Render the dashboard with made-up data to docs/screenshot.png (the README hero image).

Usage: uv run python scripts/screenshot.py [output.png]

Needs the dev dependencies and Chromium (`uv run playwright install chromium-headless-shell`).
The app runs in-process with in-memory sources and a fixed clock, so no network access and no
config.yaml are needed. The sources below are also the smallest possible examples of the
DepartureProvider, CalendarSource (calendar and birthdays), WeatherSource and HealthCheck
interfaces (see docs/customizing.md).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from home_dashboard.app import create_app
from home_dashboard.clock import FixedClock
from home_dashboard.config import (
    AppConfig,
    BirthdaysConfig,
    CalendarConfig,
    DeparturesConfig,
    EveryoneConfig,
    HomeConfig,
    PersonConfig,
    ServiceConfig,
    StatusConfig,
    StopConfig,
)
from home_dashboard.widgets.calendar.source import Event
from home_dashboard.widgets.departures.provider import Departure, Product, StopMatch
from home_dashboard.widgets.status.source import Unhealthy
from home_dashboard.widgets.weather.source import CurrentWeather, Forecast, HourForecast

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 17, 7, 41, tzinfo=TZ)  # a Tuesday morning
TODAY = NOW.date()
OUTPUT = Path(__file__).parent.parent / "docs" / "screenshot.png"
# Galaxy Tab A 10.1 (2016): 1920x1200 px at a device pixel ratio of 1.5
VIEWPORT = {"width": 1280, "height": 800}
DEVICE_SCALE_FACTOR = 1.5
BASE_URL = "http://dashboard.test"


class FakeDepartures:
    """Trams every 10 minutes per stop; one delayed and one cancelled to show the markers."""

    LINES = {"5258": ["1", "95"], "5125": ["7", "2"]}

    def departures(
        self,
        stop_id: str,
        start: datetime,
        duration_minutes: int,
        via_id: str | None = None,
        products: list[Product] | None = None,
    ) -> list[Departure]:
        lines = self.LINES.get(stop_id, ["1"])
        first = start.replace(second=0, microsecond=0) + timedelta(
            minutes=3 if stop_id == "5258" else 6
        )
        result = []
        for index in range(duration_minutes // 5):
            planned = first + timedelta(minutes=5 * index)
            delay = 2 if (stop_id, index) == ("5258", 2) else 0
            result.append(
                Departure(
                    trip_id=f"{stop_id}-{index}",
                    line=lines[index % len(lines)],
                    product="tram",
                    direction="Hauptbahnhof",
                    planned=planned,
                    realtime=planned + timedelta(minutes=delay),
                    cancelled=(stop_id, index) == ("5125", 2),
                )
            )
        return result

    def search_stops(self, query: str) -> list[StopMatch]:
        return []


def _at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(TODAY + timedelta(days=day_offset), datetime.min.time(), TZ).replace(
        hour=hour, minute=minute
    )


def _timed(
    uid: str, title: str, day: int, start: tuple[int, int], end: tuple[int, int], *, recurring=False
) -> Event:
    return Event(uid, title, _at(day, *start), _at(day, *end), recurring)


def _all_day(uid: str, title: str, day: int, days: int = 1) -> Event:
    first: date = TODAY + timedelta(days=day)
    return Event(uid, title, first, first + timedelta(days=days))


class FakeCalendar:
    """A family week; titles name the people as configured below (Alice, Bob, "Familie")."""

    EVENTS = [
        _all_day("bin", "Müllabfuhr", 0),
        _timed("run", "Alice: Laufen", 0, (6, 30), (7, 15), recurring=True),
        _timed("swim", "Bob Schwimmtraining", 0, (16, 30), (17, 30), recurring=True),
        _timed("yoga1", "Alice Yoga", 0, (19, 0), (20, 0), recurring=True),
        _timed("dentist", "Alice: Zahnarzt", 1, (8, 15), (9, 0)),
        _timed("party", "Bob Kindergeburtstag bei Max", 1, (15, 0), (18, 0)),
        _timed("cinema", "Familie: Kino", 2, (17, 30), (19, 30)),
        _timed("yoga2", "Alice Yoga", 2, (19, 0), (20, 0), recurring=True),
        _all_day("granny", "Oma zu Besuch", 3, days=3),
        _timed("football1", "Bob Fußballtraining", 3, (15, 0), (16, 30), recurring=True),
        _timed("market", "Flohmarkt in der Schule", 4, (10, 0), (13, 0)),
        _timed("match", "Bob: Fußballspiel", 4, (14, 0), (15, 30)),
        _timed("lunch", "Familie Mittagessen bei Oma und Opa", 5, (12, 0), (14, 0)),
        _timed("choir", "Alice Chor", 6, (18, 30), (20, 0), recurring=True),
        _timed("parents", "Alice & Bob: Elternabend", 7, (19, 0), (20, 30)),
    ]

    def events(self, start: datetime, end: datetime) -> list[Event]:
        def bounds(event: Event) -> tuple[datetime, datetime]:
            if event.all_day:
                return _at(0, 0) + (event.start - TODAY), _at(0, 0) + (event.end - TODAY)
            return event.start, event.end

        return [e for e in self.EVENTS if bounds(e)[0] < end and bounds(e)[1] > start]


class FakeBirthdays:
    """Birthdays and an anniversary of the coming two weeks (a CalendarSource as well)."""

    EVENTS = [
        _all_day("granny", "Oma (70)", 0),
        _all_day("anna", "Tante Anna", 4),
        _all_day("wedding", "Hochzeitstag Alice & Bob", 9),
        _all_day("max", "Max (Bobs Freund)", 12),
    ]

    def events(self, start: datetime, end: datetime) -> list[Event]:
        return [e for e in self.EVENTS if start.date() <= e.start < end.date()]


class FakeWeather:
    """A grey November morning, rain later."""

    def forecast(self) -> Forecast:
        hour = NOW.replace(minute=0)
        return Forecast(
            current=CurrentWeather(
                NOW, temperature=6.0, apparent_temperature=3.0, code=3, is_day=True, uv_index=0.0
            ),
            hours=[
                HourForecast(hour + timedelta(hours=offset), code, is_day=True, uv_index=uv)
                for offset, (code, uv) in enumerate(
                    [(3, 0.0), (3, 0.0), (61, 0.2), (63, 0.4), (61, 0.7)]
                )
            ],
        )


class FakeHealthCheck:
    """All services up except one whose last check failed (yellow)."""

    FAILING = {"http://nas.home.arpa:5000/"}

    def check(self, url: str) -> None:
        if url in self.FAILING:
            raise Unhealthy("HTTP 503")


CONFIG = AppConfig(
    home=HomeConfig(lat=51.48, lon=11.97),
    departures=DeparturesConfig(
        stops=[
            StopConfig(name="Rannischer Platz", id="5258", walk_minutes=5, direction="Markt"),
            StopConfig(name="Franckeplatz", id="5125", walk_minutes=10, direction="Hauptbahnhof"),
        ]
    ),
    calendar=CalendarConfig(
        ical_url="https://calendar.example/demo.ics",
        people=[
            PersonConfig(name="Alice", color="#e07a5f", match=["Alice"]),
            PersonConfig(name="Bob", color="#3d85c6", match=["Bob"]),
        ],
        everyone=EveryoneConfig(label="Alle", color="#c9b458", match=["Familie"]),
    ),
    birthdays=BirthdaysConfig(ical_url="https://calendar.example/birthdays.ics"),
    status=StatusConfig(
        services=[
            ServiceConfig(name="Home Assistant", url="http://host.docker.internal:8123/"),
            ServiceConfig(name="Pi-hole", url="http://host.docker.internal:8080/admin/"),
            ServiceConfig(name="NAS", url="http://nas.home.arpa:5000/"),
            ServiceConfig(name="Drucker", url="http://printer.home.arpa/"),
        ]
    ),
)


def render(browser, output: Path) -> None:
    """Screenshot the dashboard with the fake data in an open Playwright browser."""
    app = create_app(
        CONFIG,
        clock=FixedClock(NOW),
        departure_provider=FakeDepartures(),
        calendar_source=FakeCalendar(),
        birthdays_source=FakeBirthdays(),
        weather_source=FakeWeather(),
        health_check=FakeHealthCheck(),
    )
    client = TestClient(app)

    def serve(route) -> None:
        response = client.get(route.request.url.removeprefix(BASE_URL))
        route.fulfill(
            status=response.status_code,
            headers={"content-type": response.headers["content-type"]},
            body=response.content,
        )

    page = browser.new_page(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR)
    try:
        page.route(f"{BASE_URL}/**", serve)
        page.goto(f"{BASE_URL}/")
        # fit.js hides rows on load; wait for the layout to settle
        page.evaluate(
            "() => new Promise((done) => requestAnimationFrame(() => setTimeout(done, 100)))"
        )
        page.screenshot(path=str(output))
    finally:
        page.close()


def main(output: Path) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        render(browser, output)
        browser.close()
    print(f"wrote {output}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT)
