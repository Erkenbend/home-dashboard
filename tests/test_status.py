"""Behaviour of the services status widget: health checks from the Pi, bubbles in the header."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig, ServiceConfig, StatusConfig
from tests.html import services, states
from tests.services_fake import ServicesFake

HOME_ASSISTANT = "http://host.docker.internal:8123/api/"
PIHOLE = "http://host.docker.internal:8080/admin/"
NAS = "http://nas.home.arpa:5000/health"
MINUTE = timedelta(minutes=1)


def status_config(**overrides) -> AppConfig:
    status = {
        "services": [
            ServiceConfig(name="Home Assistant", url=HOME_ASSISTANT),
            ServiceConfig(name="Pi-hole", url=PIHOLE),
            ServiceConfig(name="NAS", url=NAS),
        ],
        **overrides,
    }
    return AppConfig(status=StatusConfig(**status))


@pytest.fixture
def health(respx_mock: respx.Router) -> ServicesFake:
    fake = ServicesFake(respx_mock)
    for url in (HOME_ASSISTANT, PIHOLE, NAS):
        fake.add(url)
    return fake


@pytest.fixture
def client(make_client: Callable[..., TestClient], health) -> TestClient:
    return make_client(status_config())


def shown(client: TestClient) -> str:
    response = client.get("/widgets/status")
    assert response.status_code == 200
    return response.text


def one_minute_later(client: TestClient, clock: FixedClock) -> str:
    clock.instant += MINUTE
    return shown(client)


def test_shows_a_green_bubble_with_the_short_name_per_healthy_service(client, health) -> None:
    health.answer(NAS, 204)  # any 2xx

    shown_services = services(shown(client))

    assert [(s["name"], s["state"], s["bubble"]) for s in shown_services] == [
        ("Home Assistant", "ok", True),
        ("Pi-hole", "ok", True),
        ("NAS", "ok", True),
    ]
    assert shown_services[0]["title"] == "Home Assistant: erreichbar"


@pytest.mark.parametrize(
    "failure",
    [
        500,
        404,
        302,  # redirects are not followed
        httpx.ConnectError("Connection refused"),
        httpx.ReadTimeout("timed out"),
    ],
    ids=["server-error", "not-found", "redirect", "connection-refused", "timeout"],
)
def test_a_failed_check_turns_the_bubble_yellow(client, health, failure) -> None:
    if isinstance(failure, int):
        health.answer(PIHOLE, failure, headers={"Location": "/login"})
    else:
        health.fail(PIHOLE, failure)

    shown_services = services(shown(client))

    assert states(shown(client)) == {"Home Assistant": "ok", "Pi-hole": "warning", "NAS": "ok"}
    assert shown_services[1]["title"] == "Pi-hole: letzte Prüfung fehlgeschlagen"


def test_failed_checks_in_a_row_turn_the_bubble_red(client, health, clock) -> None:
    health.answer(NAS, 503)
    assert states(shown(client))["NAS"] == "warning"

    second = one_minute_later(client, clock)
    assert states(second)["NAS"] == "failing"
    assert services(second)[2]["title"] == "NAS: 2 Prüfungen in Folge fehlgeschlagen"

    third = one_minute_later(client, clock)
    assert states(third)["NAS"] == "failing"
    assert services(third)[2]["title"] == "NAS: 3 Prüfungen in Folge fehlgeschlagen"


def test_one_successful_check_turns_the_bubble_green_again(client, health, clock) -> None:
    health.fail(NAS, httpx.ConnectError("No route to host"))
    shown(client)
    one_minute_later(client, clock)

    health.answer(NAS, 200)
    assert states(one_minute_later(client, clock))["NAS"] == "ok"

    health.answer(NAS, 500)
    assert states(one_minute_later(client, clock))["NAS"] == "warning", "counting starts anew"


def test_each_service_is_checked_at_most_once_a_minute_by_default(
    make_client: Callable[..., TestClient], health, clock
) -> None:
    client = make_client(status_config())
    health.answer(PIHOLE, 500)

    client.get("/")
    for _ in range(3):  # the tablet polls every 30 s, a second display loads the page
        clock.instant += timedelta(seconds=20)
        shown(client)
        client.get("/")
    assert [health.checks(url) for url in (HOME_ASSISTANT, PIHOLE, NAS)] == [2, 2, 2]

    # a poll arriving a bit early (network jitter) does not skip a whole check
    clock.instant += MINUTE - timedelta(seconds=2)
    assert states(shown(client))["Pi-hole"] == "failing"
    assert health.checks(PIHOLE) == 3


def test_check_interval_is_configurable(make_client: Callable[..., TestClient], health, clock):
    client = make_client(status_config(check_seconds=300))
    shown(client)

    clock.instant += timedelta(minutes=4)
    shown(client)
    assert health.checks(NAS) == 1

    clock.instant += MINUTE
    shown(client)
    assert health.checks(NAS) == 2


def test_services_are_checked_in_parallel(client, health) -> None:
    """A slow service costs at most one timeout for all of them, not one per service."""
    all_waiting = threading.Barrier(3, timeout=5)

    def slow(request: httpx.Request) -> httpx.Response:
        all_waiting.wait()  # breaks (-> failed checks) unless all three are checked at once
        return httpx.Response(200)

    for url in (HOME_ASSISTANT, PIHOLE, NAS):
        health.handle(url, slow)

    assert set(states(shown(client)).values()) == {"ok"}


def test_checks_use_the_configured_timeout(make_client: Callable[..., TestClient], health) -> None:
    shown(make_client(status_config(timeout_seconds=3)))

    timeouts = {request.extensions["timeout"]["read"] for request in health.requests}
    assert timeouts == {3}


def test_status_sits_in_the_header_between_the_date_and_the_source_code_link(client) -> None:
    page = client.get("/").text

    header = page[page.index('<header class="header">') : page.index("</header>")]
    assert header.index('class="clock"') < header.index('id="status"')
    assert header.index('id="status"') < header.index('class="repo-link"')
    assert 'hx-get="/widgets/status" hx-trigger="every 30s"' in header
    assert states(header) == {"Home Assistant": "ok", "Pi-hole": "ok", "NAS": "ok"}


def test_no_status_without_configured_services(
    make_client: Callable[..., TestClient], health
) -> None:
    client = make_client(AppConfig())

    assert 'id="status"' not in client.get("/").text
    assert client.get("/widgets/status").status_code == 404
    assert health.requests == []
