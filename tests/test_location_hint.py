"""M4 / Design: no-location Stats shows one hint and hides n/a location rows."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from orbitrx.ui.qt_app import QtOrbitRxApplication


def test_no_location_hides_you_and_shows_hint(qt_app):
    win = QtOrbitRxApplication()
    win.ctrl.state.user_lat = None
    win.ctrl.state.user_lon = None
    win._update_location_hint_visibility()
    # Explicit setVisible flags (isVisibleTo depends on tab/window show state).
    assert not win._location_hint_lbl.isHidden()
    assert win._labels["location"].isHidden()
    assert win._labels["sunrise"].isHidden()
    assert win._labels["sunset"].isHidden()
    assert win._labels["path_muf"].isHidden()
    win.close()


def test_with_location_shows_you_hides_hint(qt_app):
    win = QtOrbitRxApplication()
    win.ctrl.state.user_lat = 51.5
    win.ctrl.state.user_lon = -0.1
    win._update_location_hint_visibility()
    assert win._location_hint_lbl.isHidden()
    assert not win._labels["location"].isHidden()
    win.close()


@pytest.fixture
def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
