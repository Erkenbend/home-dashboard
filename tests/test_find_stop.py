from __future__ import annotations

import pytest
import respx

from home_dashboard.cli import main
from tests.hafas_fake import HafasFake


def test_find_stop_prints_ids_for_the_config(
    respx_mock: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    HafasFake(respx_mock)

    main(["find-stop", "Rannischer Platz Halle"])

    output = capsys.readouterr().out.splitlines()
    assert output[0].split() == ["5258", "Halle", "(Saale),", "Rannischer", "Platz"]


def test_find_stop_without_result(
    respx_mock: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    HafasFake(respx_mock)

    main(["find-stop", "Gibtsnicht"])

    assert "Keine Haltestelle gefunden." in capsys.readouterr().out
