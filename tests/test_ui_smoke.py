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
    vp_height = view.viewport().height()
    visible_height = min(p2.y(), vp_height) - max(p1.y(), 0)
    # P2 (BRIEF-TO-9): the map keeps its 2:1 aspect and letterboxes, so it must
    # fill at least 90% of whichever viewport dimension is the limiting one.
    assert max(visible_width / vp_width, visible_height / vp_height) >= 0.90
    # No stretching: the on-screen aspect matches the rendered image's aspect.
    img_aspect = scene_rect.width() / scene_rect.height()
    assert abs((p2.x() - p1.x()) / (p2.y() - p1.y()) - img_aspect) < 0.05

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
    # In the compact Map/Conditions layout (small offscreen screens) scan both tabs.
    panes = [None]
    if getattr(win, "_compact", False):
        panes = [win._map_tab, win._side_pane]
    seen = set()
    for pane in panes:
        if pane is not None:
            win._compact_tabs.setCurrentWidget(pane)
            app.processEvents()
        for lbl in win.findChildren(QLabel):
            if not lbl.isVisible() or id(lbl) in seen:
                continue
            seen.add(id(lbl))
            checked += 1
            f = lbl.font()
            px = QFontInfo(f).pixelSize()
            if px <= 0:  # some platform plugins (Windows offscreen) do not resolve QFontInfo
                px = f.pixelSize() if f.pixelSize() > 0 else round(f.pointSizeF() * lbl.logicalDpiY() / 72.0)
            assert px > 0, f"{lbl.objectName() or lbl.text()[:30]!r} has no resolvable font size"
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
    from PySide6.QtWidgets import QApplication, QPushButton, QToolBar

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
    # M1 (BRIEF-TO-9): the action buttons moved into the top toolbar.
    labels = [b.text() for b in win.findChildren(QPushButton) if b.text() in ("Export snapshot", "Export DX CSV")]
    for tb in win.findChildren(QToolBar):
        labels += [a.text() for a in tb.actions() if a.text() in ("Export snapshot", "Export DX CSV")]
    assert sorted(labels) == ["Export DX CSV", "Export snapshot"]
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_check_updates_runs_off_the_ui_thread(tmp_path, monkeypatch):
    """The update check is a blocking network call (10s timeout); calling it
    from _check_updates must return immediately and do the request on a
    worker thread, not stall the window."""
    monkeypatch.chdir(tmp_path)
    import threading
    import time as time_mod
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    main_thread = threading.current_thread()
    seen_threads = []
    release = threading.Event()

    def slow_fake_check(_version):
        seen_threads.append(threading.current_thread())
        release.wait(timeout=5)
        return {"update_available": False, "latest": _version, "url": "", "message": "ok"}

    import orbitrx.ui.qt_app as qt_app
    monkeypatch.setattr(qt_app, "check_github_release", slow_fake_check)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()

    t0 = time_mod.perf_counter()
    win._check_updates()
    call_duration = time_mod.perf_counter() - t0
    assert call_duration < 1.0  # must return immediately, not wait for the "network" call

    deadline = time_mod.time() + 5
    while not seen_threads and time_mod.time() < deadline:
        time_mod.sleep(0.01)
    assert seen_threads and seen_threads[0] is not main_thread

    release.set()
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_live_spot_toggles_are_enabled_on_the_native_map(tmp_path, monkeypatch):  # P5
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication, QToolButton

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
    for key in ("spot_arcs", "spot_heatmap"):
        cb = win._layer_checks[key]
        assert cb.isEnabled()
        assert cb.toolTip() == ""
    assert win.findChild(QToolButton, "switchMapButton") is None
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()
