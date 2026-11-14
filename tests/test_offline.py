"""Offline indicator: when the tablet cannot reach the server, the frozen display says so."""

from __future__ import annotations

from tests.test_layout import LARGE, SMALL, assert_fits

POLL_MS = 16_000  # one clock poll (default clock_refresh_seconds: 15)

STATE = """() => {
  const shown = (selector) => document.querySelector(selector).offsetParent !== null;
  return {
    notice: shown('#offline') ? document.querySelector('#offline').textContent.trim() : null,
    date: shown('.clock-date'),
    widgetOpacity: [...document.querySelectorAll('.widget')]
      .map((widget) => getComputedStyle(widget).opacity),
    headerHeight: document.querySelector('.header').getBoundingClientRect().height,
  };
}"""


def poll(page, times: int = 1) -> dict:
    for _ in range(times):
        page.clock.run_for(POLL_MS)
        # let the browser deliver the request outcome (route handled on the Python side)
        page.wait_for_timeout(100)
    return page.evaluate(STATE)


def test_lost_connection_is_shown_and_clears_when_the_server_is_back(open_dashboard, network):
    page = open_dashboard(LARGE, fake_timers=True)
    online = page.evaluate(STATE)
    assert online["notice"] is None
    assert online["date"]
    assert online["widgetOpacity"] == ["1", "1", "1"]

    network.down()
    offline = poll(page)

    assert offline["notice"] == "Keine Verbindung seit 21:36", "last clock time shown"
    assert not offline["date"], "the notice takes the place of the date"
    assert offline["widgetOpacity"] == ["0.4", "0.4", "0.4"], "frozen data is dimmed"
    assert offline["headerHeight"] == online["headerHeight"], "widgets keep their space"

    network.up()
    assert poll(page) == online


def test_hanging_requests_count_as_lost_connection(open_dashboard, network):
    page = open_dashboard(LARGE, fake_timers=True)
    page.evaluate("() => { htmx.config.timeout = 200; }")  # production: 30 s

    network.hang()
    page.clock.run_for(POLL_MS)
    page.wait_for_function("() => document.body.classList.contains('offline')", timeout=5000)


def test_offline_notice_fits_small_displays(open_dashboard, network):
    page = open_dashboard(SMALL, fake_timers=True)

    network.down()
    assert poll(page)["notice"]

    assert_fits(page)
    header_fits = page.evaluate(
        "() => { const h = document.querySelector('.header');"
        " return h.scrollWidth <= h.clientWidth; }"
    )
    assert header_fits, "notice must not be cut off"
