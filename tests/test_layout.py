"""Layout behaviour in a real browser: widgets fit the display, nothing overlaps, nothing scrolls.

Needs a headless Chromium: `uv run playwright install chromium-headless-shell`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.config import AppConfig, CalendarConfig, DeparturesConfig
from tests.hafas_fake import HafasFake
from tests.test_calendar import ANNA, BEN, EVERYONE, ICAL_URL, ICS
from tests.test_departures import FRANCKEPLATZ, RANNISCHER_PLATZ

playwright_api = pytest.importorskip("playwright.sync_api")

BASE_URL = "http://dashboard.test"

# Common landscape tablets (CSS pixels) plus portrait
SMALL = (800, 480)
LARGE = (1920, 1080)
VIEWPORTS = [LARGE, (1280, 800), (1024, 600), (960, 600), SMALL, (600, 960)]


@pytest.fixture(scope="session")
def browser() -> Iterator:
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
def open_dashboard(
    browser, make_client: Callable[..., TestClient], busy_hafas: HafasFake
) -> Iterator[Callable]:
    config = AppConfig(
        departures=DeparturesConfig(stops=[RANNISCHER_PLATZ, FRANCKEPLATZ], max_per_stop=8),
        calendar=CalendarConfig(ical_url=ICAL_URL, people=[ANNA, BEN], everyone=EVERYONE, days=14),
    )
    client = make_client(config)
    pages = []

    def serve(route) -> None:
        path = route.request.url.removeprefix(BASE_URL)
        response = client.get(path)
        route.fulfill(
            status=response.status_code,
            headers={"content-type": response.headers["content-type"]},
            body=response.content,
        )

    def _open(viewport: tuple[int, int]):
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        pages.append(page)
        page.route(f"{BASE_URL}/**", serve)
        page.goto(f"{BASE_URL}/")
        return page

    yield _open
    for page in pages:
        page.close()


LAYOUT = """() => {
  const box = (el) => el.getBoundingClientRect();
  const visible = (el) => el.offsetParent !== null;
  const widgets = [...document.querySelectorAll('.widget')].map((widget) => {
    const outer = box(widget);
    const rows = [...widget.querySelectorAll('tr, li')].filter(visible);
    return {
      id: widget.id,
      box: {left: outer.left, right: outer.right, top: outer.top, bottom: outer.bottom},
      overflowX: widget.scrollWidth > widget.clientWidth,
      overflowY: widget.scrollHeight > widget.clientHeight + 1,
      cutRows: rows.filter((row) => box(row).bottom > outer.bottom + 1).length,
    };
  });
  const root = document.documentElement;
  const directions = [...document.querySelectorAll('td.direction')].filter(visible);
  return {
    widgets,
    // narrowest direction column, in characters of its font (about 2 per em)
    directionChars: Math.min(...directions.map((cell) =>
      2 * box(cell).width / parseFloat(getComputedStyle(cell).fontSize))),
    pageScrolls: root.scrollWidth > innerWidth || root.scrollHeight > innerHeight,
  };
}"""

VISIBLE_ROWS = """() => {
  const visible = (el) => el.offsetParent !== null;
  const stops = {};
  for (const stop of document.querySelectorAll('[data-stop]')) {
    stops[stop.dataset.stop] = [...stop.querySelectorAll('tr.departure')].map(visible);
  }
  const days = [...document.querySelectorAll('[data-day]')]
    .map((day) => [day.dataset.day, visible(day)]);
  return {stops, days};
}"""


def resize(page, viewport: tuple[int, int]) -> None:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    # The browser fires `resize` asynchronously
    page.evaluate("() => new Promise((done) => requestAnimationFrame(() => setTimeout(done)))")


def assert_fits(page) -> None:
    layout = page.evaluate(LAYOUT)
    assert not layout["pageScrolls"]
    for widget in layout["widgets"]:
        assert not widget["overflowX"], widget
        assert not widget["overflowY"], widget
        assert widget["cutRows"] == 0, widget
    assert layout["directionChars"] >= 8, "direction must stay readable"
    first, second = (widget["box"] for widget in layout["widgets"])
    side_by_side = first["right"] <= second["left"]
    stacked = first["bottom"] <= second["top"]
    assert side_by_side or stacked, layout["widgets"]


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_widgets_fit_the_display_without_overlapping_or_scrolling(open_dashboard, viewport):
    assert_fits(open_dashboard(viewport))


def test_small_display_shows_fewer_rows_and_keeps_the_most_important(open_dashboard):
    small = open_dashboard(SMALL).evaluate(VISIBLE_ROWS)
    large = open_dashboard(LARGE).evaluate(VISIBLE_ROWS)

    for stop, rows in small["stops"].items():
        assert rows[0], f"next departure of {stop} must always stay"
        visible = rows.count(True)
        assert rows == [True] * visible + [False] * (len(rows) - visible), "no gaps"
        assert visible < large["stops"][stop].count(True)
    small_days = [label for label, visible in small["days"] if visible]
    large_days = [label for label, visible in large["days"] if visible]
    assert len(small_days) < len(large_days)
    assert small_days == large_days[: len(small_days)], "days are dropped from the end"


def test_rows_are_dropped_round_robin_across_stops(open_dashboard):
    stops = open_dashboard(SMALL).evaluate(VISIBLE_ROWS)["stops"]

    counts = [rows.count(True) for rows in stops.values()]
    assert max(counts) - min(counts) <= 1, stops


def test_layout_adapts_when_the_display_size_changes(open_dashboard):
    page = open_dashboard(LARGE)

    resize(page, SMALL)
    assert_fits(page)
    resize(page, LARGE)

    assert page.evaluate(VISIBLE_ROWS) == open_dashboard(LARGE).evaluate(VISIBLE_ROWS)


def test_refreshed_widget_content_is_fitted_again(open_dashboard):
    page = open_dashboard(SMALL)
    before = page.evaluate(VISIBLE_ROWS)

    # What HTMX polling does every refresh_seconds
    for widget in ("departures", "calendar"):
        page.evaluate(
            """(id) => new Promise((resolve) => {
                const settled = () => setTimeout(resolve);
                document.addEventListener('htmx:afterSettle', settled, {once: true});
                htmx.ajax('GET', '/widgets/' + id, '#' + id);
            })""",
            widget,
        )

    assert_fits(page)
    assert page.evaluate(VISIBLE_ROWS) == before
