"""Layout in a real browser: widgets fit the display, nothing overlaps, nothing scrolls."""

from __future__ import annotations

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
