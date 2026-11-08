"""The interactive map must keep greyline and the home marker until the page loads."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])

pytest.importorskip("PySide6.QtWebEngineWidgets")

from orbitrx.map_renderer import MapLayers, MapRenderer
from orbitrx.ui.leaflet_map import LeafletMapWidget


class _State:
    slider_offset_hours = 0
    user_lat = 51.5081
    user_lon = -0.1281
    kp_index = 2.0


def test_payload_waits_for_the_page_then_includes_greyline_and_home(qtbot_app):
    widget = LeafletMapWidget(MapRenderer(width=360, height=180))
    calls: list[str] = []
    widget.web.page().runJavaScript = lambda js: calls.append(js)
    widget._ready = False
    widget.set_layers(MapLayers())
    widget.update_scene(_State(), [], {})
    assert calls == []
    assert widget._pending_payload_js
    widget._on_ready(True)
    assert len(calls) == 1
    body = calls[0]
    assert body.startswith("setPayload(")
    payload = json.loads(body[len("setPayload("):-2])
    assert payload["layers"]["greyline"] is True
    assert len(payload["terminator"]) > 1
    assert payload["user"] == [51.5081, -0.1281]


@pytest.fixture
def qtbot_app():
    return _APP
