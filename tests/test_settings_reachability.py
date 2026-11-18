"""P4 owner decision (c): Settings must stay reachable via the Tools menu and
Ctrl+, both before and after the toolbar row is removed (plan item P4-4).
These tests deliberately never touch window._toolbar / _toolbar_actions --
P4-4 has now actually deleted that toolbar (see tests/test_menu_bar.py::
test_no_main_toolbar_exists), so there's nothing left to simulate removing."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


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
    win.activateWindow()
    app.processEvents()
    yield win
    win.ctrl.stop()
    win.close()


def _patched_exec(calls):
    from PySide6.QtWidgets import QDialog

    def fake_exec(self):
        calls.append(self)
        return QDialog.DialogCode.Rejected

    return fake_exec


def test_tools_menu_carries_the_real_settings_action_by_identity(window):
    """Not just a label match: the Tools menu must hold the exact same QAction
    instance as window._actions["Settings"], independent of the toolbar."""
    from PySide6.QtWidgets import QMenu

    menu_tools = window.findChild(QMenu, "menuTools")
    assert window._actions["Settings"] in menu_tools.actions()


def test_tools_menu_settings_action_opens_the_settings_dialog(window, monkeypatch):
    calls: list = []
    monkeypatch.setattr(__import__("PySide6.QtWidgets", fromlist=["QDialog"]).QDialog, "exec", _patched_exec(calls))

    settings_action = window._actions["Settings"]
    settings_action.trigger()

    assert len(calls) == 1
    assert calls[0].windowTitle() == "Settings"


def test_ctrl_comma_opens_the_settings_dialog(window, monkeypatch):
    from PySide6.QtWidgets import QDialog

    calls: list = []
    monkeypatch.setattr(QDialog, "exec", _patched_exec(calls))

    QTest.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)

    assert len(calls) == 1
    assert calls[0].windowTitle() == "Settings"


def test_settings_reachable_via_tools_menu_and_shortcut_without_the_toolbar(window, monkeypatch):
    """P4-4 has deleted the toolbar outright (tests/test_menu_bar.py::
    test_no_main_toolbar_exists pins that); confirm both routes to Settings
    still work on the real post-P4-4 window, per owner decision (c)."""
    from PySide6.QtWidgets import QDialog, QMenu, QToolBar

    assert window.findChild(QToolBar, "mainToolbar") is None

    menu_tools = window.findChild(QMenu, "menuTools")
    assert window._actions["Settings"] in menu_tools.actions()

    calls: list = []
    monkeypatch.setattr(QDialog, "exec", _patched_exec(calls))

    window._actions["Settings"].trigger()
    QTest.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)

    assert len(calls) == 2
    assert all(dlg.windowTitle() == "Settings" for dlg in calls)
