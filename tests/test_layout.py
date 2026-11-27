"""Layout in a real browser: widgets fit the display, nothing overlaps, nothing scrolls."""

from __future__ import annotations

import itertools

import pytest

from tests.test_departures import FRANCKEPLATZ, RANNISCHER_PLATZ

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
    // the walk time is only a hint and may be cut off on small displays
    cutWalkTimes: [...document.querySelectorAll('.stop-walk')].filter(visible)
      .filter((walk) => box(walk).right > box(walk.parentElement).right + 1).length,
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
    assert list(boxes) == ["weather", "departures", "calendar"]
    for first, second in itertools.combinations(boxes.values(), 2):
        side_by_side = first["right"] <= second["left"]
        stacked = first["bottom"] <= second["top"]
        assert side_by_side or stacked, layout["widgets"]
    departures, weather = boxes["departures"], boxes["weather"]
    assert departures["top"] >= weather["bottom"], "departures below the weather"
    assert (weather["left"], weather["right"]) == (departures["left"], departures["right"])


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_widgets_fit_the_display_without_overlapping_or_scrolling(open_dashboard, viewport):
    assert_fits(open_dashboard(viewport))


BOTH_WITH_DIRECTION = [
    RANNISCHER_PLATZ.model_copy(update={"direction": "Markt"}),
    FRANCKEPLATZ.model_copy(update={"direction": "Hauptbahnhof"}),
]


@pytest.mark.parametrize("dashboard_stops", [BOTH_WITH_DIRECTION])
@pytest.mark.parametrize(
    "viewport", [LARGE, (1280, 800), (1024, 600)], ids=lambda size: f"{size[0]}x{size[1]}"
)
def test_stop_name_direction_and_walk_time_fit_on_one_line(open_dashboard, viewport):
    page = open_dashboard(viewport)
    layout = page.evaluate(LAYOUT)

    assert layout["cutWalkTimes"] == 0, "walk time must not be cut off"
    assert_fits(page)


@pytest.mark.parametrize("viewport", [LARGE, (1280, 800)], ids=lambda size: f"{size[0]}x{size[1]}")
def test_calendar_takes_55_percent_and_departures_two_thirds_of_the_left_column(
    open_dashboard, viewport
):
    """Smaller displays: the weather needs more than a third for its two rows of tiles, the
    departures give up rows instead (see test_widgets_fit_the_display_without_overlapping...).
    Narrow displays (below 1000 px) split the width in halves, so the departures stay readable."""
    boxes = {
        widget["id"]: widget["box"]
        for widget in open_dashboard(viewport).evaluate(LAYOUT)["widgets"]
    }
    departures, weather, calendar = boxes["departures"], boxes["weather"], boxes["calendar"]

    left = departures["right"] - departures["left"]
    right = calendar["right"] - calendar["left"]
    assert right / (left + right) == pytest.approx(0.55, abs=0.005)
    # the gap between weather and departures is taken from both
    column = calendar["bottom"] - weather["top"]
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

    assert page.text_content(".weather-grid").split()[:2] == ["-10°C", "echt"]
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


REPO_LINK = """() => {
    const box = (selector) => {
        const b = document.querySelector(selector).getBoundingClientRect();
        return {left: b.left, right: b.right, top: b.top, bottom: b.bottom};
    };
    return {link: box('.repo-link'), date: box('.clock-date'), header: box('.header'),
            calendar: box('#calendar'), width: innerWidth};
}"""


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_source_code_link_sits_in_the_top_right_corner_next_to_the_date(open_dashboard, viewport):
    boxes = open_dashboard(viewport).evaluate(REPO_LINK)
    link, header = boxes["link"], boxes["header"]

    assert link["right"] == pytest.approx(boxes["calendar"]["right"], abs=1), "flush with widgets"
    assert header["top"] <= link["top"] and link["bottom"] <= header["bottom"]
    assert boxes["date"]["right"] < link["left"], "no overlap with the date"


STATUS = """() => {
    const box = (el) => {
        const b = el.getBoundingClientRect();
        return {left: b.left, right: b.right, top: b.top, bottom: b.bottom};
    };
    const visible = (el) => el.offsetParent !== null;
    const services = [...document.querySelectorAll('.service')];
    return {
        header: box(document.querySelector('.header')),
        time: box(document.querySelector('.header-time')),
        date: box(document.querySelector('.clock-date')),
        link: box(document.querySelector('.repo-link')),
        status: box(document.querySelector('#status')),
        shown: services.filter(visible).map((el) => ({
            name: el.dataset.service,
            box: box(el),
            bubble: box(el.querySelector('.service-bubble')),
            label: box(el.querySelector('.service-name')),
        })),
        hidden: services.filter((el) => !visible(el)).map((el) => el.dataset.service),
        rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
    };
}"""


def assert_status_fits(status: dict) -> None:
    header = status["header"]
    assert header["bottom"] - header["top"] == pytest.approx(
        status["time"]["bottom"] - status["time"]["top"], abs=1
    ), "the clock alone sets the header height"
    link, rem = status["link"], status["rem"]
    for service in status["shown"]:
        bubble, label = service["bubble"], service["label"]
        assert status["date"]["right"] < bubble["left"], "right of the date"
        assert label["right"] < status["link"]["left"], "left of the source code link"
        assert header["top"] <= bubble["top"] and label["bottom"] <= header["bottom"], service
        assert bubble["bottom"] <= label["top"], "name below the bubble"
        assert (bubble["top"] + bubble["bottom"]) / 2 == pytest.approx(
            (link["top"] + link["bottom"]) / 2, abs=1
        ), "bubbles in line with the source code link"
        assert link["left"] - label["right"] >= 2 * rem, "some space before the link"
        assert (bubble["left"] + bubble["right"]) / 2 == pytest.approx(
            (label["left"] + label["right"]) / 2, abs=1
        ), "name centred below the bubble"


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda size: f"{size[0]}x{size[1]}")
def test_services_status_sits_right_of_the_date_and_time(open_dashboard, viewport):
    page = open_dashboard(viewport)
    status = page.evaluate(STATUS)

    assert_status_fits(status)
    if viewport[0] >= 800:  # portrait (600 px wide) has room for fewer
        shown = [service["name"] for service in status["shown"]]
        assert shown == ["Home Assistant", "Pi-hole", "NAS"]
    assert_fits(page)


MANY_SERVICES = {f"Dienst {index}": 200 for index in range(1, 13)} | {"Dienst 4": 500}


@pytest.mark.parametrize("dashboard_services", [MANY_SERVICES])
@pytest.mark.parametrize("viewport", [SMALL, (1280, 800)], ids=lambda size: f"{size[0]}x{size[1]}")
def test_healthy_services_give_way_first_when_not_all_fit(open_dashboard, viewport):
    status = open_dashboard(viewport).evaluate(STATUS)

    shown = [service["name"] for service in status["shown"]]
    assert "Dienst 4" in shown, "the unhealthy service stays"
    assert status["hidden"], "twelve services do not fit next to the date"
    assert len({service["box"]["top"] for service in status["shown"]}) == 1, "one line"
    assert_status_fits(status)


def test_services_status_is_fitted_again_after_a_refresh(open_dashboard):
    page = open_dashboard(SMALL)
    before = page.evaluate(STATUS)

    page.evaluate(
        """() => new Promise((resolve) => {
            document.addEventListener('htmx:afterSettle', () => setTimeout(resolve), {once: true});
            htmx.ajax('GET', '/widgets/status', '#status');
        })"""
    )

    after = page.evaluate(STATUS)
    assert after["shown"] == before["shown"]
    assert after["shown"][-1]["name"] == "NAS"
