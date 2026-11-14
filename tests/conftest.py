from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from home_dashboard.app import create_app
from home_dashboard.clock import FixedClock
from home_dashboard.config import AppConfig

BERLIN = ZoneInfo("Europe/Berlin")
FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent

pytest_plugins = ["tests.browser"]


@pytest.fixture
def clock() -> FixedClock:
    # Time at which the INSA HAFAS fixtures were recorded
    return FixedClock(datetime(2026, 11, 9, 21, 36, tzinfo=BERLIN))


@pytest.fixture
def make_client(clock: FixedClock) -> Callable[..., TestClient]:
    def _make(config: AppConfig | None = None) -> TestClient:
        return TestClient(create_app(config or AppConfig(), clock=clock))

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
