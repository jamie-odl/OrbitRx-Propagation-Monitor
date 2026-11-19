"""P2B: a QStatusBar carrying rig/CAT state, next-refresh time and location
source, driven entirely by existing controller callbacks/signals via the
_UiInvoker pattern -- never by polling serial/network on the UI thread.

G6 (P5-r2) dropped the status bar's cluster label: cluster state now renders
only in the menu-bar corner pill (tests/test_menu_bar.py), since showing it
in both places was a literal text duplicate."""

from __future__ import annotations

import os
import re
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

STATUS_OBJECT_NAMES = ["statusRig", "statusRefresh", "statusLocation"]


def _pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


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
    win.close()


def test_status_bar_exists_with_expected_widgets(window):
    from PySide6.QtWidgets import QLabel

    bar = window.statusBar()
    assert bar is not None
    for name in STATUS_OBJECT_NAMES:
        lbl = window.findChild(QLabel, name)
        assert lbl is not None, f"missing status widget {name}"


def test_rig_status_updates_on_cat_success(window):
    window._set_rig_status(True, "connected")
    assert "connected" in window._status_rig_lbl.text()


def test_rig_status_updates_on_cat_failure(window):
    window._set_rig_status(False, "test failed")
    assert "test failed" in window._status_rig_lbl.text()


@pytest.mark.parametrize(
    "status,expect_substring",
    [
        ("connecting", "connecting"),
        ("connected", "connected"),  # "<real node name> connected", SPEC §6.2
        ("reconnecting", "reconnecting"),
        ("disconnected", "disconnected"),
    ],
)
def test_cluster_corner_widget_tracks_callback(window, status, expect_substring):
    """G5/G6: cluster state now renders only in the menu-bar corner pill."""
    window._set_cluster(status)
    assert expect_substring in window._corner_cluster_lbl.text()


def test_next_refresh_label_shows_real_scheduler_hhmmss_on_refresh(window):
    """G6/SPEC §6.2 "Next refresh 13:47:57": computed from the real
    self._timer's remainingTime(), not a "last refreshed" stamp."""
    window._refresh_labels_and_map()
    text = window._status_refresh_lbl.text()
    assert text.startswith("Next refresh"), text
    assert re.search(r"\d{2}:\d{2}:\d{2}", text), text


def test_location_source_reflects_controller_state(window):
    window.ctrl.state.location_source = "manual"
    window._refresh_labels_and_map()
    assert "manual" in window._status_location_lbl.text()

    window.ctrl.state.location_source = "geolocated"
    window._refresh_labels_and_map()
    assert "geolocated" in window._status_location_lbl.text()

    window.ctrl.state.location_source = "unset"
    window._refresh_labels_and_map()
    assert "not set" in window._status_location_lbl.text()


def test_location_not_set_uses_fair_amber_colour(window):
    """SPEC §6.2 "Location: not set (FAIR colour, clickable)"."""
    from orbitrx.ui.theme import FAIR

    window.ctrl.state.location_source = "unset"
    window._refresh_labels_and_map()
    assert FAIR in window._status_location_lbl.text()

    window.ctrl.state.location_source = "manual"
    window._refresh_labels_and_map()
    assert FAIR not in window._status_location_lbl.text()


def test_on_dx_callback_also_updates_refresh_time(window):
    """on_weather and on_dx are wired to the same _refresh_labels_and_map, so
    a DX-triggered refresh updates the status bar's refresh time too. on_dx
    is delivered via the queued _UiInvoker, same as every controller
    callback, so this must pump the event loop once to see it land."""
    from PySide6.QtWidgets import QApplication

    window._status_refresh_lbl.setText("Next refresh --:--:--")
    window.ctrl._on_dx()
    QApplication.instance().processEvents()
    assert window._status_refresh_lbl.text() != "Next refresh --:--:--"


@pytest.mark.parametrize("width,height", [(1400, 820), (683, 485)])
def test_status_bar_fits_without_horizontal_scrollbar(window, width, height):
    from PySide6.QtWidgets import QScrollArea

    window.resize(width, height)
    window._update_compact_mode()
    window.show()
    assert window.statusBar().isVisible()
    offenders = [
        area.objectName() or area.__class__.__name__
        for area in window.findChildren(QScrollArea)
        if area.horizontalScrollBar().isVisible()
    ]
    assert offenders == []
