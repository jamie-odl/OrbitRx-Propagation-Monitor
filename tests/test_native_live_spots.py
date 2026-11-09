"""Native PropagationMapWidget.set_live_spots: the port of Leaflet's
setLiveSpots JS onto the Qt map (Option B, 2026-11-09, no Qt WebEngine)."""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from orbitrx.map_renderer import MapRenderer
from orbitrx.ui.map_widget import MAX_LIVE_ARCS, MAX_LIVE_HEAT_CELLS, PropagationMapWidget


@pytest.fixture
def widget():
    QApplication.instance() or QApplication([])
    return PropagationMapWidget(MapRenderer(width=200, height=100))


def _spot(tx=(0.0, 0.0), rx=(10.0, 10.0), opacity=0.9, label="G4ABC > K1AAA 20m +5 dB", freq_mhz=14.074):
    return {"tx": list(tx), "rx": list(rx), "opacity": opacity, "label": label, "freq_mhz": freq_mhz}


def test_empty_payload_is_safe(widget):
    widget.set_live_spots({})
    assert widget._live_spots_root.childItems() == []
    assert widget._live_click_targets == []


def test_none_payload_is_safe(widget):
    widget.set_live_spots(None)
    assert widget._live_spots_root.childItems() == []


def test_arcs_on_draws_line_and_marker_and_click_target(widget):
    widget.set_live_spots({"arcs": True, "heatmap": False, "spots": [_spot()], "heat": []})
    assert len(widget._live_spots_root.childItems()) == 2  # polyline + tx marker
    assert widget._live_click_targets == [pytest.approx((widget.renderer.world_to_map(10.0, 10.0)[0],
                                                           widget.renderer.world_to_map(10.0, 10.0)[1],
                                                           14.074, 9.0))]


def test_arcs_off_draws_nothing_even_with_spots(widget):
    widget.set_live_spots({"arcs": False, "heatmap": False, "spots": [_spot()], "heat": []})
    assert widget._live_spots_root.childItems() == []


def test_heatmap_on_draws_a_cell_per_entry(widget):
    heat = [[0.0, 0.0, 1.0], [10.0, 10.0, 0.5], [20.0, 20.0, 0.0]]
    widget.set_live_spots({"arcs": False, "heatmap": True, "spots": [], "heat": heat})
    assert len(widget._live_spots_root.childItems()) == 3


def test_heatmap_off_draws_no_cells(widget):
    widget.set_live_spots({"arcs": False, "heatmap": True, "spots": [], "heat": []})
    assert widget._live_spots_root.childItems() == []
    widget.set_live_spots({"arcs": False, "heatmap": False, "spots": [], "heat": [[0.0, 0.0, 1.0]]})
    assert widget._live_spots_root.childItems() == []


def test_refresh_clears_previous_items_and_click_targets(widget):
    widget.set_live_spots({"arcs": True, "heatmap": True, "spots": [_spot()], "heat": [[0.0, 0.0, 1.0]]})
    assert widget._live_spots_root.childItems()
    assert widget._live_click_targets
    widget.set_live_spots({"arcs": False, "heatmap": False, "spots": [], "heat": []})
    assert widget._live_spots_root.childItems() == []
    assert widget._live_click_targets == []


def test_arcs_capped_at_200_like_the_old_leaflet_js(widget):
    spots = [_spot(tx=(float(i % 80 - 40), 0.0)) for i in range(250)]
    widget.set_live_spots({"arcs": True, "heatmap": False, "spots": spots, "heat": []})
    # two items (line + marker) per rendered arc, capped at MAX_LIVE_ARCS
    assert len(widget._live_spots_root.childItems()) == 2 * MAX_LIVE_ARCS
    assert MAX_LIVE_ARCS == 200


def test_heat_capped_at_40_like_the_old_leaflet_js(widget):
    heat = [[float(i % 80 - 40), 0.0, 0.5] for i in range(100)]
    widget.set_live_spots({"arcs": False, "heatmap": True, "spots": [], "heat": heat})
    assert len(widget._live_spots_root.childItems()) == MAX_LIVE_HEAT_CELLS
    assert MAX_LIVE_HEAT_CELLS == 40


def test_spot_missing_freq_draws_but_has_no_click_target(widget):
    spot = _spot()
    del spot["freq_mhz"]
    widget.set_live_spots({"arcs": True, "heatmap": False, "spots": [spot], "heat": []})
    assert len(widget._live_spots_root.childItems()) == 2
    assert widget._live_click_targets == []


def test_spot_missing_tx_or_rx_is_skipped(widget):
    spot = _spot()
    spot["rx"] = None
    widget.set_live_spots({"arcs": True, "heatmap": False, "spots": [spot], "heat": []})
    assert widget._live_spots_root.childItems() == []


def test_click_on_live_arc_marker_tunes_to_its_frequency(widget):
    widget.set_live_spots({"arcs": True, "heatmap": False, "spots": [_spot(rx=(10.0, 10.0), freq_mhz=21.074)], "heat": []})
    received = []
    widget.spot_clicked.connect(lambda freq: received.append(freq))
    rx_x, rx_y = widget.renderer.world_to_map(10.0, 10.0)

    from PySide6.QtCore import QPointF, Qt as _Qt
    scene_pt = QPointF(rx_x, rx_y)
    widget.view.mapToScene = lambda _pos: scene_pt

    class _FakeEvent:
        def button(self):
            return _Qt.MouseButton.LeftButton
        def pos(self):
            return scene_pt

    widget.mousePressEvent(_FakeEvent())
    assert received == [21.074]


def test_map_widget_module_does_not_reference_webengine():
    assert "PySide6.QtWebEngineWidgets" not in sys.modules
    assert "PySide6.QtWebChannel" not in sys.modules
    import orbitrx.ui.map_widget as mw
    text = open(mw.__file__, encoding="utf-8").read()
    assert "QtWebEngine" not in text
    assert "WebChannel" not in text
    import pathlib
    assert not (pathlib.Path(mw.__file__).parent / "leaflet_map.py").exists()
