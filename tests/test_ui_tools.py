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


def _png_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _png_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as img:
        return img.size


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

    # SPEC §10/§15 state sheet: state_empty/state_nodata/state_stale at every
    # SIZES entry, plus the 683-only Ctrl+B drawer, each exactly the
    # requested window size (not a crop/scale of it).
    for label, width, height in ui_screenshots.SIZES:
        for prefix in ("state_empty_", "state_nodata_", "state_stale_"):
            path = out_dir / f"{prefix}{label}.png"
            assert path.exists(), f"missing {path.name}"
            assert _png_size(path) == (width, height)

    # G12 (p5-r4): empty/no-data/stale must be three visibly different real
    # states (Never-updated+muted-hint / red Couldn't-reach-source banner /
    # amber Stale banner) -- not just three names for the same screenshot,
    # the bug these three states previously had. A byte-equality check on
    # each PNG is a cheap, deterministic stand-in for a perceptual pixel
    # hash: identical rendered pixels always serialize to identical bytes
    # from the same Qt/PNG encoder in one process, so any difference in
    # content shows up as different bytes.
    for label, _width, _height in ui_screenshots.SIZES:
        empty_bytes = _png_bytes(out_dir / f"state_empty_{label}.png")
        nodata_bytes = _png_bytes(out_dir / f"state_nodata_{label}.png")
        stale_bytes = _png_bytes(out_dir / f"state_stale_{label}.png")
        assert empty_bytes != nodata_bytes, f"state_empty/state_nodata identical at {label}"
        assert empty_bytes != stale_bytes, f"state_empty/state_stale identical at {label}"
        assert nodata_bytes != stale_bytes, f"state_nodata/state_stale identical at {label}"

    drawer_path = out_dir / "drawer_683x485.png"
    assert drawer_path.exists()
    assert _png_size(drawer_path) == (683, 485)
    # 1280x800 has no side-panel drawer (it's never in compact mode).
    assert not (out_dir / "drawer_1280x800.png").exists()


def test_ui_screenshots_scale_option_adds_150pct_suffixed_files(tmp_path, restore_cwd):
    """--scale re-runs the same captures in a subprocess with QT_SCALE_FACTOR
    set (Qt only reads it at QGuiApplication construction time, so this can't
    happen in-process) and must not disturb the normal, unsuffixed output."""
    from tools import ui_screenshots

    out_dir = tmp_path / "shots"
    code = ui_screenshots.main(["--out", str(out_dir), "--scale", "1.5"])

    assert code == 0
    pngs = sorted(p.name for p in out_dir.glob("*.png"))
    assert any(not name.endswith("_150pct.png") for name in pngs)
    scaled = [name for name in pngs if name.endswith("_150pct.png")]
    assert scaled
    assert any(name.startswith("main_") for name in scaled)
    assert any(name.startswith("settings_") for name in scaled)
    for p in out_dir.glob("*_150pct.png"):
        assert p.stat().st_size > 0

    # Every scaled state/drawer file must come out the same device-pixel size
    # as its sibling main_<label>_150pct.png -- whatever that rounds to under
    # Qt's own high-DPI handling, not a formula this test has to guess.
    for label, _width, _height in ui_screenshots.SIZES:
        expected = _png_size(out_dir / f"main_{label}_150pct.png")
        for prefix in ("state_empty_", "state_nodata_", "state_stale_"):
            path = out_dir / f"{prefix}{label}_150pct.png"
            assert path.exists(), f"missing {path.name}"
            assert _png_size(path) == expected

    drawer_path = out_dir / "drawer_683x485_150pct.png"
    assert drawer_path.exists()
    assert _png_size(drawer_path) == _png_size(out_dir / "main_683x485_150pct.png")


def test_ui_timing_runs_one_fast_pass_and_exits_cleanly(tmp_path, restore_cwd):
    from tools import ui_timing

    json_path = tmp_path / "timing.json"
    code = ui_timing.main(["--runs", "1", "--cat-delay", "0.2", "--json", str(json_path)])

    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for key in ("settings_open_ms", "settings_apply_ms", "config_writes"):
        assert key in data
