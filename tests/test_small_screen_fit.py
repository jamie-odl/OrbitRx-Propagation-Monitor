"""Settings dialog, main window, rig wizard and About dialog all shrink to fit a
small/scaled-up available desktop (e.g. 683x485 logical pixels) via fit_to_screen,
and the Settings dialog's Save button always stays within the dialog's own rect."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

SMALL_AVAIL = (0, 0, 683, 485)


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


def test_main_window_content_scrolls_instead_of_overflowing(window):
    """M3 (V7): the main window's content sits in a scroll area, so a content
    minimum larger than a small screen scrolls rather than running off-screen."""
    from PySide6.QtWidgets import QScrollArea

    central = window.centralWidget()
    assert isinstance(central, QScrollArea)
    assert central.objectName() == "centralScroll"
    assert central.widgetResizable()
