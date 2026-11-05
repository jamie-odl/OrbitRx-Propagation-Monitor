"""Map empty-replay-window overlay: "No spots in this window" (S1)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


def _spot(**overrides):
    from orbitrx.spots.models import Spot
    data = dict(
        rx_lat=51.5, rx_lon=-0.1, tx_lat=40.7, tx_lon=-74.0,
        frequency_hz=14_074_000, mode="FT8", sender="W1AW", receiver="G0ABC",
        snr_db=-10.0, flow_start_seconds=0,
    )
    data.update(overrides)
    return Spot(**data)


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
    win.show()
    app.processEvents()
    yield win
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_empty_live_spots_shows_overlay_on_static_map(window):
    window._layer_checks["spot_arcs"].setChecked(True)
    window.ctrl.spots.latest = []
    window._refresh_live_spots()
    assert window.map_widget._empty_overlay.isVisible() is True
    assert window.map_widget._empty_overlay.text() == "No spots in this window"


def test_nonempty_live_spots_hides_overlay(window):
    window._layer_checks["spot_arcs"].setChecked(True)
    window.ctrl.spots.latest = [_spot()]
    window._refresh_live_spots()
    assert window.map_widget._empty_overlay.isVisible() is False


def test_live_spots_layer_off_hides_overlay_even_when_empty(window):
    window._layer_checks["spot_arcs"].setChecked(False)
    window._layer_checks["spot_heatmap"].setChecked(False)
    window.ctrl.spots.latest = []
    window._refresh_live_spots()
    assert window.map_widget._empty_overlay.isVisible() is False


def test_replay_offset_appends_hours_ago_to_overlay(window):
    window._layer_checks["spot_arcs"].setChecked(True)
    window.replay_slider.setValue(6)
    window._refresh_live_spots()
    assert window.map_widget._empty_overlay.isVisible() is True
    assert window.map_widget._empty_overlay.text() == "No spots in this window (6 h ago)"
