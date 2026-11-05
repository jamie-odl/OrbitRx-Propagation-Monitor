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


def test_replay_offset_appends_hours_ago_to_overlay(window, monkeypatch):
    # Isolate from the shared on-disk spots database: an empty replay window is the
    # state under test, so real spots captured earlier must not leak in.
    monkeypatch.setattr(window.ctrl.spots, "replay", lambda hours_back, window_minutes=30: [])
    window._layer_checks["spot_arcs"].setChecked(True)
    window.replay_slider.setValue(6)
    window._refresh_live_spots()
    assert window.map_widget._empty_overlay.isVisible() is True
    assert window.map_widget._empty_overlay.text() == "No spots in this window (6 h ago)"


def test_empty_overlay_is_a_legible_pill_on_the_static_map(window): # S2
    style = window.map_widget._empty_overlay.styleSheet()
    assert "color: #C9D1D9" in style
    assert "font-size: 13px" in style
    assert "background: rgba(15,23,32,0.85)" in style
    assert "border-radius" in style
    assert "padding: 8px 14px" in style


def test_empty_overlay_is_a_legible_pill_on_the_leaflet_map():  # S2
    from orbitrx.ui.leaflet_map import WEBENGINE_AVAILABLE, LeafletMapWidget
    from orbitrx.map_renderer import MapRenderer

    if not WEBENGINE_AVAILABLE:
        pytest.skip("QtWebEngine not available")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    widget = LeafletMapWidget(MapRenderer(width=10, height=10))
    style = widget._empty_overlay.styleSheet()
    assert "color: #C9D1D9" in style
    assert "background: rgba(15,23,32,0.85)" in style
    assert "border-radius" in style
    assert "padding: 8px 14px" in style


def test_empty_overlay_pill_is_a_single_line(window):  # S2
    win = window
    mw = getattr(win, "map_widget", None) or getattr(win, "map_view", None)
    if mw is None or not hasattr(mw, "set_empty_overlay"):
        import pytest
        pytest.skip("no static map widget exposed")
    mw.set_empty_overlay("No spots in this window (6 h ago)")
    lbl = mw._empty_overlay
    assert not lbl.wordWrap()
    assert lbl.height() < 2 * lbl.fontMetrics().height() + 20
