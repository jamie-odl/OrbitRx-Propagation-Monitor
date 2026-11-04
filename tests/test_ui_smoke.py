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
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    assert "OrbitRx" in win.windowTitle()
    assert "spot_arcs" in win._layer_checks and "spot_heatmap" in win._layer_checks
    win._replay_moved(4)
    assert win.lbl_replay.text() == "-4 h"
    win._refresh_live_spots()
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_static_map_fills_most_of_viewport_width(tmp_path, monkeypatch): # S3
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

    view = win.map_widget.view
    vp_width = view.viewport().width()
    scene_rect = win.map_widget._base_item.sceneBoundingRect()
    p1 = view.mapFromScene(scene_rect.topLeft())
    p2 = view.mapFromScene(scene_rect.bottomRight())
    visible_width = min(p2.x(), vp_width) - max(p1.x(), 0)
    assert visible_width / vp_width >= 0.90

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_no_visible_qlabel_renders_below_caption_minimum(tmp_path, monkeypatch): # S2
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtGui import QFontInfo

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
    # Populate the labels that only get real text after a refresh ("Weather updated...").
    win._refresh_labels_and_map()
    win.ctrl.state.cluster_status = "connected"
    win._render_cluster_label()
    app.processEvents()

    checked = 0
    for lbl in win.findChildren(QLabel):
        if not lbl.isVisible():
            continue
        checked += 1
        px = QFontInfo(lbl.font()).pixelSize()
        assert px >= 11, f"{lbl.objectName() or lbl.text()[:30]!r} renders at {px}px"
    assert checked > 10  # sanity: we actually scanned a meaningful number of labels

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_right_column_has_only_one_vertical_scrollbar(tmp_path, monkeypatch): # S3
    monkeypatch.chdir(tmp_path)
    from PySide6.QtCore import Qt
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

    assert win._right_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert win._stats_scroll.verticalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_action_button_grid_has_no_ragged_hole(tmp_path, monkeypatch): # N-new-5
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication, QPushButton

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
    labels = [b.text() for b in win.findChildren(QPushButton) if b.text() in ("Export snapshot", "Export DX CSV")]
    assert sorted(labels) == ["Export DX CSV", "Export snapshot"]
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()
