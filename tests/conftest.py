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
from home_dashboard.i18n import DEFAULT_LANGUAGE, load_translator

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
    def _make(config: AppConfig | None = None, language: str = DEFAULT_LANGUAGE) -> TestClient:
        app = create_app(config or AppConfig(), clock=clock, translator=load_translator(language))
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
