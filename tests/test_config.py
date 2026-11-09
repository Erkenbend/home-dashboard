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
