from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from tests.conftest import BERLIN


def test_dashboard_shows_current_time_and_german_date(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "21:36" in response.text
    assert "Montag, 9. November 2026" in response.text


def test_dashboard_loads_vendored_htmx_and_polls_clock(client: TestClient) -> None:
    page = client.get("/").text

    assert '<script src="/static/htmx.min.js">' in page
    assert 'hx-get="/widgets/clock"' in page
    assert client.get("/static/htmx.min.js").status_code == 200


def test_clock_fragment_follows_the_clock(client: TestClient, clock: FixedClock) -> None:
    clock.instant = datetime(2026, 12, 31, 23, 59, tzinfo=BERLIN)

    fragment = client.get("/widgets/clock").text

    assert "23:59" in fragment
    assert "Donnerstag, 31. Dezember 2026" in fragment
    assert "<html" not in fragment


def test_health_check(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
