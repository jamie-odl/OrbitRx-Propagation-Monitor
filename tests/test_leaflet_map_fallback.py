"""Leaflet map M5: never blank white, dark page background and a fallback overlay
when the page fails to load or its tiles never arrive."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture
def leaflet_widget():
    from orbitrx.ui.leaflet_map import WEBENGINE_AVAILABLE, LeafletMapWidget

    if not WEBENGINE_AVAILABLE:
        pytest.skip("QtWebEngine not available")
    from PySide6.QtWidgets import QApplication
    from orbitrx.map_renderer import MapRenderer

    app = QApplication.instance() or QApplication([])
    widget = LeafletMapWidget(MapRenderer(width=10, height=10))
    widget.show()
    app.processEvents()
    yield widget
    widget.deleteLater()
    app.processEvents()


def test_page_background_is_dark_not_white(leaflet_widget):
    from orbitrx.ui.theme import BG
    from PySide6.QtGui import QColor

    assert leaflet_widget.web.page().backgroundColor() == QColor(BG)


def test_load_failure_shows_the_unavailable_overlay(leaflet_widget):
    assert leaflet_widget._unavailable_overlay.isVisible() is False
    leaflet_widget._on_ready(False)
    assert leaflet_widget._unavailable_overlay.isVisible() is True
    assert leaflet_widget._unavailable_overlay.text() == "Map unavailable (offline?) · Switch to static map"


def test_tile_error_shows_the_unavailable_overlay(leaflet_widget):
    leaflet_widget._on_ready(True)
    assert leaflet_widget._unavailable_overlay.isVisible() is False
    leaflet_widget._on_tile_error()
    assert leaflet_widget._unavailable_overlay.isVisible() is True


def test_tile_timeout_shows_the_unavailable_overlay(leaflet_widget):
    leaflet_widget._on_ready(True)
    assert leaflet_widget._tile_timeout_timer.isActive() is True
    leaflet_widget._on_tile_timeout()
    assert leaflet_widget._unavailable_overlay.isVisible() is True


def test_tiles_loaded_hides_the_overlay_and_stops_the_timeout(leaflet_widget):
    leaflet_widget._on_ready(True)
    leaflet_widget._on_tile_timeout()
    assert leaflet_widget._unavailable_overlay.isVisible() is True
    leaflet_widget._on_tiles_loaded()
    assert leaflet_widget._unavailable_overlay.isVisible() is False


def test_tiles_loaded_cancels_the_pending_timeout(leaflet_widget):
    leaflet_widget._on_ready(True)
    assert leaflet_widget._tile_timeout_timer.isActive() is True
    leaflet_widget._on_tiles_loaded()
    assert leaflet_widget._tile_timeout_timer.isActive() is False


def test_successful_load_starts_a_bounded_tile_wait(leaflet_widget):
    from orbitrx.ui.leaflet_map import TILE_LOAD_TIMEOUT_MS

    leaflet_widget._on_ready(True)
    assert leaflet_widget._tile_timeout_timer.isActive() is True
    assert leaflet_widget._tile_timeout_timer.interval() == TILE_LOAD_TIMEOUT_MS
    assert TILE_LOAD_TIMEOUT_MS <= 20_000
