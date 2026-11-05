"""Settings dialog, main window, rig wizard and About dialog all shrink to fit a
small/scaled-up available desktop (e.g. 683x485 logical pixels) via fit_to_screen,
and the Settings dialog's Save button always stays within the dialog's own rect."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

SMALL_AVAIL = (0, 0, 683, 485)


def _visible_horizontal_scrollbars(widget) -> list[str]:
    """Names of any QScrollArea under `widget` currently showing a horizontal
    scrollbar (M3: none ever should, at window level)."""
    from PySide6.QtWidgets import QScrollArea

    offenders = []
    for area in widget.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        if bar is not None and bar.isVisible():
            offenders.append(area.objectName() or area.__class__.__name__)
    return offenders


def _not_clipped_horizontally(control, window) -> bool:
    top_left = control.mapTo(window, control.rect().topLeft())
    return 0 <= top_left.x() and top_left.x() + control.width() <= window.width()


@pytest.fixture
def small_avail(monkeypatch):
    from PySide6.QtCore import QRect
    import orbitrx.ui.window_fit as window_fit

    rect = QRect(*SMALL_AVAIL)
    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: rect)
    return rect


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
    yield app
    app.processEvents()


def _save_button_fully_visible(dlg) -> bool:
    from orbitrx.ui.qt_app import _save_button_fully_visible
    return _save_button_fully_visible(dlg)


def test_settings_dialog_fits_small_available_geometry_with_save_visible(window, small_avail):
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    dlg = win._build_settings_dialog()
    assert dlg.width() <= small_avail.width()
    assert dlg.height() <= small_avail.height()
    assert dlg.width() >= 520 or dlg.width() == small_avail.width()
    assert _save_button_fully_visible(dlg)

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()


def test_main_window_fits_small_available_geometry(window, small_avail, tmp_path, monkeypatch):
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    assert win.width() <= small_avail.width()
    assert win.height() <= small_avail.height()
    assert win.minimumWidth() <= small_avail.width()
    assert win.minimumHeight() <= small_avail.height()

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()


def test_rig_wizard_fits_small_available_geometry(window, small_avail, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.cat import CatController
    from orbitrx.config import AppConfig
    from orbitrx.ui.rig_wizard import RigWizardDialog

    cfg = AppConfig(path=tmp_path / "c.json").load()
    dlg = RigWizardDialog(cfg, CatController(cfg))
    assert dlg.width() <= small_avail.width()
    assert dlg.height() <= small_avail.height()


def test_about_dialog_fits_small_available_geometry(window, small_avail):
    from orbitrx.ui.about import _build_about_dialog

    dlg = _build_about_dialog()
    assert dlg.width() <= small_avail.width()
    assert dlg.height() <= small_avail.height()


@pytest.fixture
def avail_667x441(monkeypatch):
    from PySide6.QtCore import QRect
    import orbitrx.ui.window_fit as window_fit

    rect = QRect(0, 0, 667, 441)
    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: rect)
    return rect


def test_settings_dialog_no_horizontal_scrollbar_at_667x441(window, avail_667x441): # S1
    from PySide6.QtCore import Qt
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    dlg = win._build_settings_dialog()
    assert dlg.scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()


def test_settings_helper_labels_word_wrap_at_667x441(window, avail_667x441): # S1
    from PySide6.QtWidgets import QLabel
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    dlg = win._build_settings_dialog()
    helper_labels = [
        lbl for lbl in dlg.findChildren(QLabel)
        if lbl.objectName() == "muted" and lbl.text().strip()
    ]
    assert helper_labels
    assert all(lbl.wordWrap() for lbl in helper_labels)

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()


def test_settings_save_visible_at_667x441(window, avail_667x441): # S1
    from orbitrx.ui.qt_app import QtOrbitRxApplication, _save_button_fully_visible

    win = QtOrbitRxApplication()
    dlg = win._build_settings_dialog()
    assert _save_button_fully_visible(dlg)

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()


def test_main_window_content_scrolls_instead_of_overflowing(window):
    """M3: the outer window-level scroll area is gone. The map and side panel
    each reflow and scroll vertically on their own instead, so there is never a
    horizontal scrollbar anywhere in the main window."""
    from PySide6.QtWidgets import QScrollArea
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    win.show()
    window.processEvents()
    assert not isinstance(win.centralWidget(), QScrollArea)
    assert win.findChild(QScrollArea, "centralScroll") is None
    assert _visible_horizontal_scrollbars(win) == []
    win.ctrl.stop()
    win.close()


@pytest.mark.parametrize("width,height,expect_compact", [(1008, 681, False), (667, 441, True)])
def test_main_window_reflows_at_small_sizes(window, width, height, expect_compact): # M3
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    win.show()
    win.resize(width, height)
    window.processEvents()

    assert win._compact is expect_compact
    assert _visible_horizontal_scrollbars(win) == []

    map_controls = [win.time_slider, win.replay_slider, *win._layer_checks.values()]
    if win._compact:
        win._compact_tabs.setCurrentWidget(win._map_scroll)
        window.processEvents()
    for control in map_controls:
        assert control.width() > 0
        assert _not_clipped_horizontally(control, win)

    buttons_by_text = {b.text(): b for b in win._action_buttons_grid._widgets}
    side_controls = [buttons_by_text["Settings"], buttons_by_text["Rig"], buttons_by_text["About"]]
    if win._compact:
        win._compact_tabs.setCurrentWidget(win._side_pane)
        window.processEvents()
    for control in side_controls:
        assert control.width() > 0
        assert _not_clipped_horizontally(control, win)

    win.ctrl.stop()
    win.deleteLater()
    window.processEvents()
