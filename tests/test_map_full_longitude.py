"""P4-8 / owner decision (e): the full -180..180 longitude range must stay
on-screen at every window size, including 1280x800 and 683x485 (no
Pacific/Australia crop) -- overriding SPEC §7's own numeric longitude-crop
prose. Only latitude may crop, and only up to MAX_POLE_CROP_DEG per pole
(aurora stays visible), via map_widget._padded_scene_rect()/_fit_scene_rect().

tests/test_ui_smoke.py::test_map_fills_viewport_with_no_letterbox and
tests/test_high_dpi_fit.py::test_map_fills_the_viewport_with_no_letterbox_at_150pct
cover the "no black/matte, uniform zoom" side of the same fix; this file
checks the longitude/latitude geometry itself in degrees, not just pixels.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from orbitrx.ui.map_widget import MAX_POLE_CROP_DEG  # noqa: E402


def _build_window(tmp_path, monkeypatch, width: int, height: int):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    import orbitrx.ui.window_fit as window_fit

    # Same decoupling from the offscreen platform's own default screen size
    # tests/test_ui_smoke.py's equivalent test uses.
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

    from tests.test_ui_smoke import _pump
    _pump(app, 0.5)
    win.map_widget.join_rebuild_thread(timeout=5.0)
    app.processEvents()
    return app, win


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
@pytest.mark.parametrize("lat", [0.0, 45.0, -45.0])
def test_full_longitude_stays_on_screen(tmp_path, monkeypatch, width, height, lat):
    """renderer.world_to_map(lat, -180) and (lat, 180) must both land inside
    the visible viewport -- i.e. no slice of longitude is ever scrolled out
    of view -- for a representative spread of latitudes, not just the
    equator."""
    app, win = _build_window(tmp_path, monkeypatch, width, height)
    try:
        view = win.map_widget.view
        vp = view.viewport()
        vp_w = vp.width()

        x_minus, y = win.renderer.world_to_map(lat, -180.0)
        x_plus, _ = win.renderer.world_to_map(lat, 180.0)
        from PySide6.QtCore import QPointF
        p_minus = view.mapFromScene(QPointF(x_minus, y))
        p_plus = view.mapFromScene(QPointF(x_plus, y))

        TOLERANCE = 3
        assert -TOLERANCE <= p_minus.x() <= vp_w + TOLERANCE, (p_minus.x(), vp_w)
        assert -TOLERANCE <= p_plus.x() <= vp_w + TOLERANCE, (p_plus.x(), vp_w)
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_latitude_crop_stays_within_budget(tmp_path, monkeypatch, width, height):
    """Whatever latitude crop _padded_scene_rect() applies (only ever at the
    poles, only when the viewport is proportionally wider than the 2:1
    basemap), it must never exceed MAX_POLE_CROP_DEG off either pole -- the
    owner's "aurora stays visible" budget. Padding (not cropping) always
    leaves 0 crop, which trivially satisfies the budget."""
    app, win = _build_window(tmp_path, monkeypatch, width, height)
    try:
        view = win.map_widget.view
        vp = view.viewport()

        top_scene = view.mapToScene(vp.width() // 2, 0)
        bottom_scene = view.mapToScene(vp.width() // 2, max(0, vp.height() - 1))
        top_lat, _ = win.renderer.map_to_world(top_scene.x(), top_scene.y())
        bottom_lat, _ = win.renderer.map_to_world(bottom_scene.x(), bottom_scene.y())

        TOLERANCE_DEG = 1.0  # fitInView's whole-device-pixel rounding, converted to degrees
        crop_at_north_pole = 90.0 - top_lat
        crop_at_south_pole = bottom_lat - (-90.0)
        assert crop_at_north_pole <= MAX_POLE_CROP_DEG + TOLERANCE_DEG, crop_at_north_pole
        assert crop_at_south_pole <= MAX_POLE_CROP_DEG + TOLERANCE_DEG, crop_at_south_pole
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("map_probe_size", ["1280x800", "683x485"])
def test_full_longitude_stays_on_screen_at_150pct(tmp_path, map_probe_size):
    """150% device-pixel-ratio analogue of test_full_longitude_stays_on_screen,
    using the same out-of-process DPI harness tests/test_high_dpi_fit.py
    relies on (Qt's high-DPI scale factor can only be set once per process)."""
    from tests.test_high_dpi_fit import _dpi_report, SPACIOUS_AVAIL

    report = _dpi_report(tmp_path, *SPACIOUS_AVAIL, map_probe_size=map_probe_size)

    TOLERANCE = 3
    vp_w = report["map_vp_w"]
    assert -TOLERANCE <= report["map_lon_m180_x"] <= vp_w + TOLERANCE
    assert -TOLERANCE <= report["map_lon_p180_x"] <= vp_w + TOLERANCE

    TOLERANCE_DEG = 1.0
    assert 90.0 - report["map_top_lat"] <= MAX_POLE_CROP_DEG + TOLERANCE_DEG
    assert report["map_bottom_lat"] + 90.0 <= MAX_POLE_CROP_DEG + TOLERANCE_DEG
