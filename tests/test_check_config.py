from __future__ import annotations

from pathlib import Path

import pytest

from home_dashboard.cli import main
from tests.conftest import REPO_ROOT


def run(*args: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        main(["check-config", *args])
    return exit_info.value.code


def test_valid_config_prints_summary_without_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.yaml"
    example = (REPO_ROOT / "config.example.yaml").read_text()
    config.write_text(
        example.replace("ical_url: null", 'ical_url: "https://x.example/secret42.ics"')
    )

    assert run(str(config)) == 0

    output = capsys.readouterr().out
    assert "OK" in output
    assert "Rannischer Platz (5 min)" in output
    assert "iCal-Adresse gesetzt" in output
    assert "secret42" not in output


def test_invalid_config_names_the_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("departures:\n  stops:\n    - {name: X, id: '1', walk_minute: 3}\n")

    assert run(str(config)) == 1

    errors = capsys.readouterr().err
    assert "departures.stops.0.walk_minutes" in errors
    assert "departures.stops.0.walk_minute" in errors


def test_broken_yaml_and_missing_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("departures: [\n")

    assert run(str(broken)) == 1
    assert run(str(tmp_path / "missing.yaml")) == 1
