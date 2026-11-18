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


def _pump(app, seconds: float) -> None:
    """Pump the event loop for a fixed wall-clock duration, not a fixed
    iteration count. Settling the map-dominant layout after a resize/show can
    take several independent deferred passes -- window_fit's post-show
    QTimer(0) re-fit, the splitter's own re-apply-until-it-sticks retry (see
    _apply_default_splitter_sizes), and the base-map rebuild worker thread's
    queued delivery -- each of which can itself trigger another resizeEvent.
    A loop keyed on iteration count or on "stopped changing for N reads" can
    lock onto an intermediate state that happens to hold steady for a few
    reads before the next pass lands; pumping a fixed real-time window (long
    enough to cover all of the above) is the only way that's reliable
    regardless of host speed."""
    import time
    from PySide6.QtTest import QTest

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_map_fills_viewport_with_no_letterbox(tmp_path, monkeypatch, width, height):
    """Owner decision (e) (P4-8): dark/black matte bands around the map are
    never acceptable, but neither is cropping longitude to avoid them -- the
    full -180..180 range must always stay on-screen (see
    tests/test_map_full_longitude.py for that check in detail). So
    map_widget._fit_scene_rect() no longer unconditionally cover-fits
    (cropping whichever axis overshoots); it pads the fit rect with
    MAP_OCEAN-coloured margin instead, whenever the viewport's own aspect
    doesn't exactly match the basemap's 2:1. This test checks what's left of
    the old "no letterbox" guarantee: the basemap is never cropped
    horizontally (its full mapped width always lies inside the viewport, so
    no longitude is ever scrolled out of view), any margin around it is
    ocean-coloured rather than black/matte, and the fit stays a uniform zoom
    (m11 == m22) so overlay/marker items -- drawn in the same scene
    coordinates as the basemap -- never drift out of alignment."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    import orbitrx.ui.window_fit as window_fit

    # Decouple from the real/offscreen platform's own default screen size
    # (tools/_ui_offline_harness.py documents it clamping a requested
    # 1280x800 window on its own) -- window_fit.fit_to_screen()'s clamp is a
    # no-op against a generously large available geometry regardless of
    # which size this test resizes to.
    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: QRect(0, 0, 1920, 1200))

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
    win.resize(width, height)
    win.show()

    _pump(app, 0.5)
    win.map_widget.join_rebuild_thread(timeout=5.0)
    app.processEvents()

    from PySide6.QtGui import QColor
    from orbitrx.ui.theme import MAP_OCEAN

    view = win.map_widget.view
    vp = view.viewport()
    rect = win.map_widget._base_item.sceneBoundingRect()
    tl = view.mapFromScene(rect.topLeft())
    br = view.mapFromScene(rect.bottomRight())
    t = view.transform()
    vp_w, vp_h = vp.width(), vp.height()
    left, top, right, bottom = tl.x(), tl.y(), br.x(), br.y()
    m11, m22 = t.m11(), t.m22()

    # fitInView's own scale/centering rounds to whole device pixels, so a
    # boundary that's supposed to land exactly on an edge can be a couple of
    # px off -- real, but far too small to read as a dark bar or a cropped
    # sliver of longitude.
    TOLERANCE = 3
    # Full longitude stays on-screen: the basemap's own mapped width never
    # exceeds the viewport (it may sit inset from the edges, with ocean
    # margin either side, but it's never cropped off past them).
    assert left >= -TOLERANCE, (left, top, right, bottom, vp_w, vp_h)
    assert right <= vp_w + TOLERANCE, (left, top, right, bottom, vp_w, vp_h)
    # Any margin around the basemap (top/bottom padding, or left/right in the
    # rare extreme-aspect case) is ocean-coloured, never the old black/matte
    # fallback brush.
    assert view.backgroundBrush().color() == QColor(MAP_OCEAN)
    assert m11 == pytest.approx(m22), (m11, m22)

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
    from PySide6.QtWidgets import QApplication, QPushButton, QMenu

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
    # P2A: Export actions moved off the toolbar/» overflow into the File menu;
    # they must not also exist as separate QPushButtons.
    assert not [b for b in win.findChildren(QPushButton) if b.text() in ("Export snapshot", "Export DX CSV")]
    menu_file = win.findChild(QMenu, "menuFile")
    labels = [a.text() for a in menu_file.actions() if a.text() in ("Export snapshot", "Export DX CSV")]
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


def test_basemap_load_runs_off_the_ui_thread_and_never_blocks_init(tmp_path, monkeypatch):
    """F7: Image.open + LANCZOS scaling must not block window construction;
    the real basemap swaps in once a background thread finishes loading it."""
    monkeypatch.chdir(tmp_path)
    import threading
    import time as time_mod
    from PySide6.QtWidgets import QApplication
    from PIL import Image

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

    fake_map_path = tmp_path / "fake_basemap.png"
    Image.new("RGB", (10, 10), (1, 2, 3)).save(fake_map_path)

    import orbitrx.paths as paths_mod
    monkeypatch.setattr(paths_mod, "ensure_map_image", lambda: fake_map_path)

    real_open = Image.open

    def slow_open(path, *a, **kw):
        seen_threads.append(threading.current_thread())
        release.wait(timeout=5)
        return real_open(path, *a, **kw)

    monkeypatch.setattr(Image, "open", slow_open)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    t0 = time_mod.perf_counter()
    win = QtOrbitRxApplication()
    init_duration = time_mod.perf_counter() - t0
    assert init_duration < 1.0  # must not block on the slow Image.open

    deadline = time_mod.time() + 5
    while not seen_threads and time_mod.time() < deadline:
        time_mod.sleep(0.01)
    assert seen_threads and seen_threads[0] is not main_thread

    release.set()
    deadline = time_mod.time() + 5
    while win._map_label != "Map · offline basemap" and time_mod.time() < deadline:
        app.processEvents()
        time_mod.sleep(0.01)
    assert win._map_label == "Map · offline basemap"

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_layer_toggle_defers_cfg_save_and_flushes_on_close(tmp_path, monkeypatch):
    """F8: a chip toggle must not synchronously hit disk (cfg.save() can spike
    under Windows AV scanning); rapid toggles coalesce into one deferred save
    of the final mask, and closing the window flushes it so persistence
    survives a quick close right after toggling."""
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

    save_calls = []
    orig_save = win.ctrl.cfg.save

    def counting_save():
        save_calls.append(True)
        orig_save()

    monkeypatch.setattr(win.ctrl.cfg, "save", counting_save)

    win._layer_checks["grid"].setChecked(True)
    win._layer_checks["aurora"].setChecked(False)
    win._layer_checks["night"].setChecked(False)
    assert save_calls == []  # no synchronous disk write from the toggles themselves
    # In-memory config (and therefore the redraw) already reflects the final
    # state, so visuals are never stale even though the write is deferred.
    assert win.ctrl.cfg.data["map_layers"]["grid"] is True
    assert win.ctrl.cfg.data["map_layers"]["aurora"] is False

    win.close()
    # closeEvent flushes the deferred layers save and separately persists
    # window_geometry (its own cfg.set -> save); either write already carries
    # the up-to-date in-memory map_layers mask, so no toggle is lost.
    assert len(save_calls) >= 1

    from orbitrx.config import AppConfig
    reloaded = AppConfig(path=win.ctrl.cfg.path).load()
    assert reloaded.data["map_layers"]["grid"] is True
    assert reloaded.data["map_layers"]["aurora"] is False

    win.deleteLater()
    app.processEvents()


def test_slider_drag_throttles_redraw_to_final_value(tmp_path, monkeypatch):
    """F10: dragging the time slider through many values in quick succession
    must not fire one full redraw per step; redraws are throttled to <=10Hz
    and the final value still settles quickly."""
    monkeypatch.chdir(tmp_path)
    import time as time_mod
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
    # Neutralize the other deferred callbacks so they can't sneak a redraw in
    # while we pump the event loop below.
    win._startup = lambda: None
    win._check_updates = lambda: None
    win._timer.stop()
    win._cluster_pulse_timer.stop()

    refresh_calls = []
    orig_refresh_map = win._refresh_map

    def counting_refresh_map(*a, **kw):
        refresh_calls.append(win.ctrl.state.slider_offset_hours)
        orig_refresh_map(*a, **kw)

    win._refresh_map = counting_refresh_map

    from orbitrx.ui.formatting import format_hour_offset

    for v in range(20):
        win._slider_moved(v)
    # The label is immediate even though the redraw is throttled.
    assert win.lbl_slider.text() == format_hour_offset(19)
    # The leading edge fired once immediately; the other 19 rapid steps must
    # not have each triggered their own redraw.
    assert len(refresh_calls) == 1

    deadline = time_mod.time() + 1.0
    while len(refresh_calls) < 2 and time_mod.time() < deadline:
        app.processEvents()
        time_mod.sleep(0.005)
    # A trailing redraw lands with the final dragged-to value.
    assert refresh_calls[-1] == 19.0

    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()
