"""P4-8 (SPEC §7): the QFrame#mapFrame wrapper, its in-map legend (bottom-left,
Greyline/Night/DX spot -- replaced by the greyline timestamp caption at
compact widths) and the "Cluster disconnected" status pill, driven only by
real DX-cluster connection state. Never a "Sample data" tag (mockup-only)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

# Round 10 (p4-r11): reused here so test_map_tab_leaves_room_for_side_panel_
# under_wide_fonts_at_1000 below is a deterministic (Linux-safe) companion to
# the windows-latest-only test_legend_swaps_to_caption_below_compact_width --
# both `large_avail` (wide_font_window's own dependency) and `wide_font_window`
# itself need to be visible as fixtures in *this* module for pytest to resolve
# them, not just imported as plain names.
from tests.test_map_dominant_layout import large_avail, wide_font_window  # noqa: F401


def _resize_window_and_settle(win, app, width, height, timeout_s=2.0):
    """resize() the top-level window and pump the event loop until it has
    actually settled at that size. map_widget sits inside this window's own
    splitter/layout, so resizing map_widget directly (as this module used
    to) never reliably sticks -- the layout corrects it back on the very
    next layout pass, which can even happen synchronously mid-resizeEvent.
    Going through the real top-level resize path is what actually changes
    map_widget's width, deterministically, the way a real user resize would.
    """
    from PySide6.QtTest import QTest

    win.resize(width, height)
    elapsed = 0.0
    step_ms = 20
    while elapsed < timeout_s:
        app.processEvents()
        if win.width() == width and win.height() == height:
            break
        QTest.qWait(step_ms)
        elapsed += step_ms / 1000.0
    win._update_compact_mode()
    app.processEvents()


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
        # A wide top-level window gives the splitter's map column well over
        # LEGEND_COMPACT_WIDTH (820) even after the ~300px side panel.
        _resize_window_and_settle(win, app, 1280, 800)
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

    from tests.test_map_dominant_layout import _full_map_column_diag

    app, win = _build_window(tmp_path, monkeypatch)
    try:
        # Still above the side-panel/compact-mode breakpoint (COMPACT_WIDTH_
        # BELOW=900), but narrow enough that the map column itself (window
        # width minus the ~300px side panel) drops below LEGEND_COMPACT_WIDTH.
        _resize_window_and_settle(win, app, 1000, 700)
        # Round 10 (p4-r11): the full geometry breakdown goes into the
        # assertion message itself -- a prior windows-latest-only failure
        # here (908px, then 850px across two rounds of blind guesses) gave
        # no way to see *which* map-column child was too wide without a
        # third CI round just to add this.
        assert win.map_widget.width() < LEGEND_COMPACT_WIDTH, _full_map_column_diag(win)
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


def test_map_tab_leaves_room_for_side_panel_under_wide_fonts_at_1000(wide_font_window):
    """Deterministic (Linux-safe) companion to
    test_legend_swaps_to_caption_below_compact_width above: that test is
    windows-latest-only (it depends on Segoe UI's own, unstretched metrics
    being bulkier than Linux's default font at the same point size), so it
    gives no local repro signal. This reuses the existing wide_font_window
    QFont.setStretch fixture (already proven to reproduce the *shape* of
    that bug for the control strip and cluster combo in earlier rounds) to
    pin the same invariant the windows-latest test wants: at 1000x700, the
    map column's own minimumSizeHint() must leave room for the side panel's
    normal >=260px share, which is exactly what drives the legend into
    caption mode instead of staying full-width."""
    from PySide6.QtWidgets import QApplication

    from orbitrx.ui.map_widget import LEGEND_COMPACT_WIDTH
    from tests.test_map_dominant_layout import _full_map_column_diag

    window = wide_font_window
    app = QApplication.instance()
    _resize_window_and_settle(window, app, 1000, 700)
    assert window._map_tab.minimumSizeHint().width() + 260 <= window._splitter.width(), (
        _full_map_column_diag(window)
    )
    assert window.map_widget.width() < LEGEND_COMPACT_WIDTH, _full_map_column_diag(window)
    assert not window.map_widget._legend_lbl.isVisible()


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
        text = win.map_widget._cluster_pill.text()
        # G14: one pill, with a real Reconnect link -- "Cluster disconnected"
        # alone (the pre-G14 text) is a substring check, not an equality one,
        # so this still catches a regression back to a bare informational pill.
        assert "Cluster disconnected" in text
        assert "Reconnect" in text
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


def test_cluster_pill_suppresses_no_spots_pill(tmp_path, monkeypatch):
    """G14: the map shows at most one pill -- while the cluster is down,
    "Cluster disconnected · Reconnect" always wins over "No spots in this
    window" rather than the two stacking."""
    app, win = _build_window(tmp_path, monkeypatch)
    try:
        win.map_widget.resize(900, 600)
        win._set_cluster("disconnected")
        win.map_widget.set_empty_overlay("No spots in this window")
        assert win.map_widget._cluster_pill.isVisible() is True
        assert win.map_widget._empty_overlay.isVisible() is False

        # Calling set_cluster_pill("") (reconnected) releases the no-spots
        # pill again for a later set_empty_overlay call -- not a one-way gate.
        win._set_cluster("connected")
        win.map_widget.set_empty_overlay("No spots in this window")
        assert win.map_widget._cluster_pill.isVisible() is False
        assert win.map_widget._empty_overlay.isVisible() is True
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
        # Resizing map_widget/view directly (as this used to) doesn't
        # reliably stick -- they're managed by this window's own splitter/
        # layout, which can correct a direct child resize() back on the very
        # next layout pass (even synchronously, mid-call). Resizing the real
        # top-level window instead gives a viewport size that's actually
        # settled, so fitted_m11 reflects what _fit_map_view() will compute
        # again later from that same (unchanged) viewport.
        _resize_window_and_settle(win, app, 1280, 800)
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
