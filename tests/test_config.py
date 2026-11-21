from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from home_dashboard.config import load_config
from tests.conftest import REPO_ROOT


def test_example_config_is_valid() -> None:
    config = load_config(REPO_ROOT / "config.example.yaml")

    assert config.departures.products == ["tram"]
    assert [stop.name for stop in config.departures.stops] == ["Rannischer Platz", "Franckeplatz"]


def test_trams_only_by_default(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("departures:\n  stops: []\n")

    assert load_config(path).departures.products == ["tram"]


def test_typos_in_config_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("departures:\n  stops:\n    - {name: X, id: Y, walk_minute: 3}\n")

    with pytest.raises(ValidationError):
        load_config(path)


@pytest.mark.parametrize(
    "service",
    [
        "{name: NAS, url: 'nas.home.arpa:5000'}",  # no scheme
        "{name: NAS, url: 'ftp://nas.home.arpa/'}",
        "{name: '', url: 'http://nas.home.arpa/'}",
    ],
    ids=["no-scheme", "not-http", "no-name"],
)
def test_services_need_a_name_and_an_http_url(tmp_path: Path, service: str) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(f"status:\n  services:\n    - {service}\n")

    with pytest.raises(ValidationError):
        load_config(path)


def test_service_checks_at_most_once_a_minute_by_default(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("status:\n  services:\n    - {name: NAS, url: 'http://nas.home.arpa/'}\n")

    assert load_config(path).status.check_seconds == 60
