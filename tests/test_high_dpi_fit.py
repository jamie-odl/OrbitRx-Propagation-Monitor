"""150% device-pixel-ratio analogue of test_small_screen_fit.py: the main
window and Settings dialog must still fit the available desktop, and
window_fit's clamping must still kick in on a tight desktop, when the
platform reports a real (non-1.0) device pixel ratio.

Qt latches its high-DPI scale factor in when the first
QApplication/QGuiApplication is constructed, and the shared pytest-session
QApplication (built by the first test file that needs one) is always
dpr=1.0 under the offscreen plugin's default config. So this exercises a
real dpr=1.5 screen the only way that's possible this late: a short-lived
subprocess that sets QT_QPA_PLATFORM's offscreen configfile dpr before its
own QApplication is built, mirroring the technique tests/conftest.py already
uses to give the offscreen platform a desktop-sized screen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).resolve().parent / "_high_dpi_probe.py"
PROBE_TIMEOUT_S = 30

# Same logical desktop test_small_screen_fit.py pins against, now at 150% DPI.
SMALL_AVAIL = (683, 485)
# A roomy desktop at 150% DPI, where nothing needs to clamp.
SPACIOUS_AVAIL = (1920, 1200)
DPR = 1.5


def _dpi_report(tmp_path, width: int, height: int, dpr: float = DPR) -> dict:
    cfg_path = tmp_path / "offscreen-dpi.json"
    cfg_path.write_text(
        json.dumps({
            "synthesized": True,
            "screens": [{
                "name": "s1", "x": 0, "y": 0,
                "width": width, "height": height,
                "logicalDpi": 96, "logicalBaseDpi": 96,
                "dpr": dpr,
            }],
        }),
        encoding="utf-8",
    )
    out_path = tmp_path / "report.json"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = f"offscreen:configfile={cfg_path}"
    env["ORBITRX_OFFLINE_FIXTURE"] = "1"
    result = subprocess.run(
        [sys.executable, str(PROBE), str(out_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
    )
    assert result.returncode == 0, (
        f"probe failed (exit {result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def test_high_dpi_rounding_policy_is_passthrough_before_app_exists(tmp_path):
    report = _dpi_report(tmp_path, *SPACIOUS_AVAIL)
    assert report["rounding_policy"] == "HighDpiScaleFactorRoundingPolicy.PassThrough"


def test_simulated_screen_reports_150_percent_device_pixel_ratio(tmp_path):
    report = _dpi_report(tmp_path, *SPACIOUS_AVAIL)
    assert report["device_pixel_ratio"] == pytest.approx(DPR)


def test_window_and_settings_fit_spacious_150pct_desktop(tmp_path):
    avail_w, avail_h = SPACIOUS_AVAIL
    report = _dpi_report(tmp_path, avail_w, avail_h)
    assert report["win_w"] <= avail_w
    assert report["win_h"] <= avail_h
    assert report["dlg_w"] <= avail_w
    assert report["dlg_h"] <= avail_h
    assert report["save_button_visible"] is True


def test_window_fit_clamping_still_works_at_150pct(tmp_path):
    """Same assertions as test_small_screen_fit.py's small-available-geometry
    tests, now with a real dpr=1.5 screen instead of dpr=1.0."""
    avail_w, avail_h = SMALL_AVAIL
    report = _dpi_report(tmp_path, avail_w, avail_h)

    assert report["win_w"] <= avail_w
    assert report["win_h"] <= avail_h
    assert report["win_min_w"] <= avail_w
    assert report["win_min_h"] <= avail_h

    assert report["dlg_w"] <= avail_w
    assert report["dlg_h"] <= avail_h
    assert report["dlg_w"] >= 520 or report["dlg_w"] == avail_w
    assert report["save_button_visible"] is True
