"""Configurable refresh (tablet polling) and fetch (upstream) intervals."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timedelta

import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, DeparturesConfig, DisplayConfig
from tests.hafas_fake import HafasFake
from tests.test_departures import RANNISCHER_PLATZ


def polling(page: str) -> dict[str, str]:
    return dict(re.findall(r'hx-get="/widgets/(\w+)" hx-trigger="every (\d+)s"', page))


@pytest.fixture
def hafas(respx_mock: respx.Router) -> HafasFake:
    return HafasFake(respx_mock)


def test_default_intervals(make_client: Callable[..., TestClient], hafas) -> None:
    config = AppConfig(departures=DeparturesConfig(stops=[RANNISCHER_PLATZ]))

    page = make_client(config).get("/").text

    assert polling(page) == {"clock": "15", "departures": "30"}
    assert '<meta http-equiv="refresh" content="21600">' in page


def test_configured_intervals_are_used_by_the_page(
    make_client: Callable[..., TestClient], hafas
) -> None:
    config = AppConfig(
        display=DisplayConfig(clock_refresh_seconds=5, page_reload_hours=0.5),
        departures=DeparturesConfig(stops=[RANNISCHER_PLATZ], refresh_seconds=20),
    )

    page = make_client(config).get("/").text

    assert polling(page) == {"clock": "5", "departures": "20"}
    assert '<meta http-equiv="refresh" content="1800">' in page


def test_page_reload_can_be_disabled(make_client: Callable[..., TestClient]) -> None:
    config = AppConfig(display=DisplayConfig(page_reload_hours=0))

    assert 'http-equiv="refresh"' not in make_client(config).get("/").text


def test_departures_are_fetched_at_most_every_fetch_seconds(
    make_client: Callable[..., TestClient], hafas: HafasFake, clock: FixedClock
) -> None:
    config = AppConfig(departures=DeparturesConfig(stops=[RANNISCHER_PLATZ], fetch_seconds=120))
    client = make_client(config)

    for _ in range(4):  # polls at 0, 30, 60, 90 s
        client.get("/widgets/departures")
        clock.instant += timedelta(seconds=30)
    assert hafas.route.call_count == 1

    client.get("/widgets/departures")  # 120 s
    assert hafas.route.call_count == 2


def test_slightly_early_poll_does_not_skip_a_fetch_cycle(
    make_client: Callable[..., TestClient], hafas: HafasFake, clock: FixedClock
) -> None:
    client = make_client(AppConfig(departures=DeparturesConfig(stops=[RANNISCHER_PLATZ])))

    client.get("/widgets/departures")
    clock.instant += timedelta(seconds=58)  # default fetch_seconds 60, poll arrives 2 s early
    client.get("/widgets/departures")

    assert hafas.route.call_count == 2


def test_too_frequent_fetching_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DeparturesConfig(fetch_seconds=5)
