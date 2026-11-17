"""The README screenshot (scripts/screenshot.py) can still be generated."""

from __future__ import annotations

import importlib.util
import struct
from pathlib import Path

from tests.conftest import REPO_ROOT


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "screenshot", REPO_ROOT / "scripts" / "screenshot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_screenshot_script_renders_the_tablet_resolution(browser, tmp_path: Path) -> None:
    output = tmp_path / "screenshot.png"

    _load_script().render(browser, output)

    header = output.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", header[16:24]) == (1920, 1200)  # Galaxy Tab A 10.1
