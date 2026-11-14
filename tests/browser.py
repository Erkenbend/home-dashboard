"""Browser fixtures: the dashboard in headless Chromium, served by an in-process TestClient.

Needs a headless Chromium: `uv run playwright install chromium-headless-shell`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.config import AppConfig, CalendarConfig, DeparturesConfig, HomeConfig
from tests.hafas_fake import HafasFake
from tests.open_meteo_fake import OpenMeteoFake
from tests.test_calendar import ANNA, BEN, EVERYONE, ICAL_URL, ICS
from tests.test_departures import FRANCKEPLATZ, RANNISCHER_PLATZ

try:
    from playwright import sync_api as playwright_api
except ImportError:  # dev dependency; without it the browser tests are skipped
    playwright_api = None

BASE_URL = "http://dashboard.test"


@pytest.fixture(scope="session")
def browser() -> Iterator:
    if playwright_api is None:
        pytest.skip("playwright is not installed")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except playwright_api.Error as error:
            pytest.skip(f"no Chromium for Playwright ({error.message.splitlines()[0]})")
        yield browser
        browser.close()


@pytest.fixture
def busy_hafas(respx_mock: respx.Router) -> HafasFake:
    """Eight reachable trams per stop, more than a small display can show."""
    hafas = HafasFake(respx_mock)
    for stop_id, via_id, line, planned in [
        ("5258", "5232", "1", "215200"),
        ("5125", "8010159", "7", "220200"),
    ]:
        template = hafas.journey(stop_id, line, planned)
        for minute in range(30, 90, 10):
            departure = f"{22 + minute // 60}{minute % 60:02d}00"
            arrival = f"{22 + minute // 60}{minute % 60 + 5:02d}00"
            hafas.add_journey(
                stop_id, template, via=(via_id, arrival), dTimeS=departure, dTimeR=departure
            )
    respx_mock.get(ICAL_URL).mock(return_value=httpx.Response(200, content=ICS))
    return hafas


@pytest.fixture
def open_meteo(respx_mock: respx.Router, clock) -> OpenMeteoFake:
    """The recorded forecast, moved to the day of the HAFAS recording; a rainy evening."""
    open_meteo = OpenMeteoFake(respx_mock)
    open_meteo.move_to(clock.now().date())
    for hour in (22, 23):
        open_meteo.set_hour(hour, clock.now().date(), weather_code=63, precipitation_probability=80)
    return open_meteo


class Network:
    """Connection between tablet and server, as seen by the browser."""

    def __init__(self) -> None:
        self.state = "up"

    def up(self) -> None:
        self.state = "up"

    def down(self) -> None:
        """Requests fail like on a dropped Wi-Fi."""
        self.state = "down"

    def hang(self) -> None:
        """Requests get no answer at all."""
        self.state = "hang"


@pytest.fixture
def network() -> Network:
    return Network()


@pytest.fixture
def open_dashboard(
    browser,
    make_client: Callable[..., TestClient],
    busy_hafas: HafasFake,
    open_meteo: OpenMeteoFake,
    network: Network,
) -> Iterator[Callable]:
    config = AppConfig(
        home=HomeConfig(lat=51.48, lon=11.97),
        departures=DeparturesConfig(
            # One stop with a configured direction, one showing the destination of each tram
            stops=[RANNISCHER_PLATZ.model_copy(update={"direction": "Markt"}), FRANCKEPLATZ],
            max_per_stop=8,
        ),
        calendar=CalendarConfig(ical_url=ICAL_URL, people=[ANNA, BEN], everyone=EVERYONE, days=14),
    )
    client = make_client(config)
    pages = []

    def serve(route) -> None:
        if network.state == "down":
            route.abort("internetdisconnected")
            return
        if network.state == "hang":
            return  # never answered
        path = route.request.url.removeprefix(BASE_URL)
        response = client.get(path)
        route.fulfill(
            status=response.status_code,
            headers={"content-type": response.headers["content-type"]},
            body=response.content,
        )

    def _open(viewport: tuple[int, int], fake_timers: bool = False):
        """Open the dashboard; with `fake_timers`, polling only runs via `page.clock.run_for`."""
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        pages.append(page)
        if fake_timers:
            page.clock.install()
        page.route(f"{BASE_URL}/**", serve)
        page.goto(f"{BASE_URL}/")
        return page

    yield _open
    for page in pages:
        page.close()
