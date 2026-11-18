"""P4-8 (SPEC §7): the QFrame#mapFrame wrapper, its in-map legend (bottom-left,
Greyline/Night/DX spot -- replaced by the greyline timestamp caption at
compact widths) and the "Cluster disconnected" status pill, driven only by
real DX-cluster connection state. Never a "Sample data" tag (mockup-only)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


def _build_window(tmp_path, monkeypatch):
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
    return app, win


def test_map_frame_wraps_the_graphics_view(tmp_path, monkeypatch):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        from PySide6.QtWidgets import QFrame
        assert win._map_frame.objectName() == "mapFrame"
        assert isinstance(win._map_frame, QFrame)
        assert win.map_widget.parentWidget() is win._map_frame
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_legend_names_greyline_night_and_dx_spot_at_full_width(tmp_path, monkeypatch):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win.map_widget.resize(1000, 600)
        legend_text = win.map_widget._legend_lbl.text()
        assert "Greyline" in legend_text
        assert "Night" in legend_text
        assert "DX spot" in legend_text
        assert win.map_widget._legend_lbl.isVisible()
        assert not win.map_widget._legend_caption_lbl.isVisible()
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_legend_swaps_to_caption_below_compact_width(tmp_path, monkeypatch):
    from orbitrx.ui.map_widget import LEGEND_COMPACT_WIDTH

    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win.map_widget.resize(LEGEND_COMPACT_WIDTH - 50, 400)
        assert not win.map_widget._legend_lbl.isVisible()
        # The caption only becomes visible once a real greyline meta string
        # has been computed (i.e. after the first scene build) -- never a
        # placeholder/sample value.
        if win.map_widget._greyline_meta_text:
            assert win.map_widget._legend_caption_lbl.isVisible()
            assert win.map_widget._legend_caption_lbl.text() == win.map_widget._greyline_meta_text
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_cluster_pill_hidden_when_connected(tmp_path, monkeypatch):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win._set_cluster("connected")
        assert win.map_widget._cluster_pill.isVisible() is False
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("status", ["disconnected", "reconnecting"])
def test_cluster_pill_shown_when_not_connected(tmp_path, monkeypatch, status):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win._set_cluster(status)
        assert win.map_widget._cluster_pill.isVisible() is True
        assert win.map_widget._cluster_pill.text() == "Cluster disconnected"
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_cluster_pill_not_shown_while_first_connecting(tmp_path, monkeypatch):
    """"connecting" (the first attempt) isn't a failure yet, so it should not
    read the same as a dropped/failed connection."""
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win._set_cluster("connecting")
        assert win.map_widget._cluster_pill.isVisible() is False
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_cluster_and_no_spots_pills_stack_without_overlap(tmp_path, monkeypatch):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win.map_widget.resize(900, 600)
        win._set_cluster("disconnected")
        win.map_widget.set_empty_overlay("No spots in this window")
        cluster_rect = win.map_widget._cluster_pill.geometry()
        empty_rect = win.map_widget._empty_overlay.geometry()
        assert not cluster_rect.intersects(empty_rect)
        assert cluster_rect.bottom() < empty_rect.top()
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_double_click_reset_returns_to_padded_cover_framing(tmp_path, monkeypatch):
    """SPEC §7: "Double-click reset returns to this [cover] framing, not to
    contain." A zoom (scroll) must be undone by a double-click back to the
    same fitted scale _fit_map_view() establishes -- not to a raw 1:1
    transform, which resetTransform() alone would leave it at."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest

    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win.map_widget.resize(900, 600)
        win.map_widget.view.resize(900, 580)
        fitted_m11 = win.map_widget.view.transform().m11()

        win.map_widget.view.scale(2.0, 2.0)
        assert win.map_widget.view.transform().m11() != pytest.approx(fitted_m11)

        QTest.mouseDClick(win.map_widget, _Qt.MouseButton.LeftButton)

        assert win.map_widget.view.transform().m11() == pytest.approx(fitted_m11, rel=1e-3)
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()


def test_no_sample_data_tag_anywhere_in_map_widget(tmp_path, monkeypatch):
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        texts = [
            win.map_widget._legend_lbl.text(),
            win.map_widget._legend_caption_lbl.text(),
            win.map_widget._empty_overlay.text(),
            win.map_widget._cluster_pill.text(),
            win.map_widget.hud.text(),
        ]
        for text in texts:
            assert "Sample" not in text
    finally:
        win.ctrl.stop()
        win.deleteLater()
        app.processEvents()
