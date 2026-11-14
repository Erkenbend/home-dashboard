from __future__ import annotations

import hashlib
import re
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

    assert re.search(r'<script src="/static/htmx\.min\.js\?v=\w+">', page)
    assert 'hx-get="/widgets/clock"' in page


def test_static_asset_urls_change_with_their_content(client: TestClient) -> None:
    """After a deployment the tablet must not combine new HTML with stale cached CSS/JS."""
    page = client.get("/").text
    urls = re.findall(r'(?:href|src)="(/static/[^"]+)"', page)

    assert len(urls) == 4, urls
    for url in urls:
        path, version = re.fullmatch(r"(/static/[^?]+)\?v=(\w+)", url).groups()
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.content == client.get(path).content
        assert version == hashlib.sha256(response.content).hexdigest()[: len(version)], url


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
