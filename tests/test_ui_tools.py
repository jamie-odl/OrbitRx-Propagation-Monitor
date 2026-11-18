"""Smoke test for tools/ui_screenshots.py and tools/ui_timing.py: both must run
offscreen and offline, in-process, and exit cleanly in well under 30s."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def restore_cwd():
    cwd = os.getcwd()
    yield
    os.chdir(cwd)


def test_ui_screenshots_writes_pngs_and_exits_cleanly(tmp_path, restore_cwd):
    from tools import ui_screenshots

    out_dir = tmp_path / "shots"
    code = ui_screenshots.main(["--out", str(out_dir)])

    assert code == 0
    pngs = sorted(out_dir.glob("*.png"))
    assert pngs
    assert any(p.name.startswith("main_") for p in pngs)
    assert any(p.name.startswith("settings_") for p in pngs)
    for p in pngs:
        assert p.stat().st_size > 0


def test_ui_timing_runs_one_fast_pass_and_exits_cleanly(tmp_path, restore_cwd):
    from tools import ui_timing

    json_path = tmp_path / "timing.json"
    code = ui_timing.main(["--runs", "1", "--cat-delay", "0.2", "--json", str(json_path)])

    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for key in ("settings_open_ms", "settings_apply_ms", "config_writes"):
        assert key in data
