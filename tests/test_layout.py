"""Layout in a real browser: widgets fit the display, nothing overlaps, nothing scrolls."""

from __future__ import annotations

import itertools

import pytest

# Common landscape tablets (CSS pixels) plus portrait
SMALL = (800, 480)
LARGE = (1920, 1080)
VIEWPORTS = [LARGE, (1280, 800), (1024, 600), (960, 600), SMALL, (600, 960)]


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
    // configured stop directions must not be cut off by the stop name's ellipsis
    cutStopDirections: [...document.querySelectorAll('.stop-direction')].filter(visible)
      .filter((direction) => box(direction).right > box(direction.parentElement).right + 1).length,
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
    assert layout["cutStopDirections"] == 0, "stop direction must stay readable"
    boxes = {widget["id"]: widget["box"] for widget in layout["widgets"]}
    assert list(boxes) == ["departures", "weather", "calendar"]
    for first, second in itertools.combinations(boxes.values(), 2):
        side_by_side = first["right"] <= second["left"]
        stacked = first["bottom"] <= second["top"]
        assert side_by_side or stacked, layout["widgets"]
    departures, weather = boxes["departures"], boxes["weather"]
    assert weather["top"] >= departures["bottom"], "weather below the departures"
    assert (weather["left"], weather["right"]) == (departures["left"], departures["right"])


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_widgets_fit_the_display_without_overlapping_or_scrolling(open_dashboard, viewport):
    assert_fits(open_dashboard(viewport))


@pytest.mark.parametrize("viewport", [LARGE, (1280, 800)], ids=lambda size: f"{size[0]}x{size[1]}")
def test_calendar_takes_the_right_half_and_departures_two_thirds_of_the_left(
    open_dashboard, viewport
):
    """Smaller displays: the weather needs more than a third for its two rows of tiles, the
    departures give up rows instead (see test_widgets_fit_the_display_without_overlapping...)."""
    boxes = {
        widget["id"]: widget["box"]
        for widget in open_dashboard(viewport).evaluate(LAYOUT)["widgets"]
    }
    departures, weather, calendar = boxes["departures"], boxes["weather"], boxes["calendar"]

    assert departures["right"] - departures["left"] == pytest.approx(
        calendar["right"] - calendar["left"], abs=1
    )
    # the gap between departures and weather is taken from both
    column = calendar["bottom"] - departures["top"]
    third = column / 3
    assert departures["bottom"] - departures["top"] == pytest.approx(2 * third, abs=0.15 * third)
    assert weather["bottom"] - weather["top"] == pytest.approx(third, abs=0.15 * third)


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
    for widget in ("departures", "weather", "calendar"):
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


@pytest.mark.parametrize("widget", ["departures", "calendar"])
def test_refreshed_widget_is_never_shown_unfitted(open_dashboard, widget):
    """No flicker: the new content is fitted before the browser can paint it."""
    page = open_dashboard(SMALL)

    # The state after the task that swapped in the new content: the browser may paint it
    overflowed = page.evaluate(
        """(id) => new Promise((resolve) => {
            const widget = document.getElementById(id);
            let overflowed = null;
            new MutationObserver((records, observer) => {
                observer.disconnect();
                overflowed = widget.scrollHeight > widget.clientHeight + 1;
            }).observe(widget, {childList: true});
            document.addEventListener('htmx:afterSettle', () => resolve(overflowed), {once: true});
            htmx.ajax('GET', '/widgets/' + id, '#' + id);
        })""",
        widget,
    )

    assert overflowed is False


@pytest.mark.parametrize("viewport", [SMALL, (600, 960)], ids=lambda size: f"{size[0]}x{size[1]}")
def test_wide_temperatures_do_not_push_into_the_weather_icons(open_dashboard, open_meteo, viewport):
    open_meteo.response["current"].update(temperature_2m=-10.2, apparent_temperature=-12.4)
    page = open_dashboard(viewport)

    temperature, slot, uv = page.evaluate(
        """() => ['.weather-apparent', '.weather-slot .weather-icon', '.uv']
            .map((selector) => document.querySelector(selector).getBoundingClientRect())
            .map((box) => ({left: box.left, right: box.right}))"""
    )

    assert page.text_content(".weather-grid").split()[:2] == ["-10°", "echt"]
    assert temperature["right"] <= slot["left"]
    assert temperature["right"] <= uv["left"]
    assert_fits(page)


WEATHER_TILES = """() => {
    const box = (el) => {
        const b = el.getBoundingClientRect();
        return {left: b.left, right: b.right, top: b.top, bottom: b.bottom};
    };
    const all = (selector) => [...document.querySelectorAll(selector)].map(box);
    return {
        rows: [...document.querySelectorAll('.weather-grid tr')]
            .map((row) => [...row.children].map(box)),
        icons: all('.weather-slot .weather-icon'),
        times: all('.weather-time .weather-label'),
        uv: all('.uv'),
        real: box(document.querySelector('.weather-actual-label')),
    };
}"""


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_weather_tiles_form_a_grid_of_four_by_two_with_the_times_on_the_line(
    open_dashboard, viewport
):
    tiles = open_dashboard(viewport).evaluate(WEATHER_TILES)

    top, line, bottom = tiles["rows"]
    assert [len(row) for row in (top, line, bottom)] == [4, 3, 4]
    for upper, lower in zip(top, bottom, strict=True):
        assert (upper["left"], upper["right"]) == pytest.approx((lower["left"], lower["right"]))
    for upper, middle in zip(top[1:], line, strict=True):
        assert (upper["left"], upper["right"]) == pytest.approx((middle["left"], middle["right"]))
    widths = [tile["right"] - tile["left"] for tile in top[1:]]
    assert max(widths) - min(widths) <= 1, "weather and UV tiles share the width equally"

    for icon, time, uv, cell in zip(tiles["icons"], tiles["times"], tiles["uv"], line, strict=True):
        assert icon["bottom"] <= time["top"] and time["bottom"] <= uv["top"]
        middle = (time["top"] + time["bottom"]) / 2
        assert middle == pytest.approx((cell["top"] + cell["bottom"]) / 2, abs=1), "on the line"
        assert time["top"] == pytest.approx(tiles["real"]["top"], abs=1), "level with 'echt'"
