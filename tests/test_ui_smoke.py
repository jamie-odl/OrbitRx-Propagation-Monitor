"""Offscreen Qt smoke test: the main window and dialogs build without network."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


def test_main_window_builds_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    assert "OrbitRx" in win.windowTitle()
    assert "spot_arcs" in win._layer_checks and "spot_heatmap" in win._layer_checks
    win._replay_moved(4)
    assert win.lbl_replay.text() == "-2.0h"
    win._refresh_live_spots()
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()
