"""Regression budget for Settings-dialog open time (Phase 0 remainder of the
UI overhaul plan): median of a few opens, after a warm-up open, must stay
under a generous CI budget. Reuses tools/ui_timing.py's own
time_settings_open_close measurement rather than re-implementing it."""

from __future__ import annotations

import os
import statistics

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

# Generous on purpose: this guards against a regression (e.g. a disk/network
# call creeping back into dialog construction), not a tight perf target --
# CI runners (Windows + Ubuntu, offscreen) are slower and noisier than a dev
# machine. Override with ORBITRX_SETTINGS_OPEN_BUDGET_MS for a slower runner.
DEFAULT_BUDGET_MS = 1500.0
BUDGET_MS = float(os.environ.get("ORBITRX_SETTINGS_OPEN_BUDGET_MS", DEFAULT_BUDGET_MS))

WARMUP_OPENS = 1
TIMED_OPENS = 3


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    yield app, win
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_settings_dialog_open_time_median_within_budget(window):
    app, win = window
    from tools import ui_timing

    open_ms, _apply_ms, _writes = ui_timing.time_settings_open_close(app, win, WARMUP_OPENS + TIMED_OPENS)
    timed = open_ms[WARMUP_OPENS:]
    median_ms = statistics.median(timed)

    assert median_ms < BUDGET_MS, (
        f"Settings dialog open median {median_ms:.1f}ms >= budget {BUDGET_MS:.1f}ms "
        f"(warm-up={open_ms[:WARMUP_OPENS]}, timed={timed})"
    )
