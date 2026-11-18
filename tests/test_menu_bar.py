"""P2A: a proper File/View/Tools/Help menu bar plus a toolbar slimmed to four
primary actions (Map, Bands, Log, Settings). Every command that used to live
on the old toolbar or its » overflow menu must stay reachable from the menu
bar, and commands shared between the toolbar and a menu must be the same
QAction object (one handler per command, not duplicated)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

EXPECTED_MENUS = ["menuFile", "menuView", "menuTools", "menuHelp"]
PRIMARY_TOOLBAR_ACTIONS = ["Map", "Bands", "Log", "Settings"]
# Every command that existed before this chunk (toolbar buttons + » overflow).
PRE_EXISTING_COMMANDS = [
    "Settings", "Rig", "About", "Location", "Weather",
    "Export snapshot", "Export DX CSV",
]


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


def test_menu_bar_has_expected_menus(window):
    from PySide6.QtWidgets import QMenu

    menu_bar = window.menuBar()
    assert menu_bar is not None
    for object_name in EXPECTED_MENUS:
        menu = window.findChild(QMenu, object_name)
        assert menu is not None, f"missing menu {object_name}"
        assert menu in [a.menu() for a in menu_bar.actions()]


def test_export_actions_are_in_file_menu(window):
    from PySide6.QtWidgets import QMenu

    menu_file = window.findChild(QMenu, "menuFile")
    labels = [a.text() for a in menu_file.actions()]
    assert "Export snapshot" in labels
    assert "Export DX CSV" in labels


def test_file_menu_has_quit(window):
    from PySide6.QtWidgets import QMenu

    menu_file = window.findChild(QMenu, "menuFile")
    assert "Quit" in [a.text() for a in menu_file.actions()]


def test_tools_menu_has_settings_and_rig_wizard(window):
    from PySide6.QtWidgets import QMenu

    menu_tools = window.findChild(QMenu, "menuTools")
    labels = [a.text() for a in menu_tools.actions()]
    assert any("Settings" in label for label in labels)
    assert any("Rig" in label for label in labels)


def test_help_menu_has_about(window):
    from PySide6.QtWidgets import QMenu

    menu_help = window.findChild(QMenu, "menuHelp")
    assert "About" in [a.text() for a in menu_help.actions()]


def test_view_menu_has_panel_focus_and_refresh(window):
    from PySide6.QtWidgets import QMenu

    menu_view = window.findChild(QMenu, "menuView")
    labels = [a.text() for a in menu_view.actions()]
    assert "Map" in labels
    assert "Bands" in labels
    assert "Log" in labels
    assert "Refresh" in labels


def test_toolbar_has_exactly_four_primary_actions(window):
    from PySide6.QtWidgets import QToolBar

    toolbar = window.findChild(QToolBar, "mainToolbar")
    assert toolbar is not None
    action_texts = [a.text() for a in toolbar.actions() if not a.isSeparator()]
    assert action_texts == PRIMARY_TOOLBAR_ACTIONS


def test_toolbar_has_no_overflow_chevron_button(window):
    from PySide6.QtWidgets import QToolButton

    toolbar = window._toolbar
    overflow_buttons = [
        btn for btn in toolbar.findChildren(QToolButton)
        if btn.text() == "»" or btn.objectName() == "toolbarOverflow"
    ]
    assert overflow_buttons == []


def test_settings_action_shared_between_toolbar_and_menu(window):
    from PySide6.QtWidgets import QMenu

    menu_tools = window.findChild(QMenu, "menuTools")
    settings_in_menu = next(a for a in menu_tools.actions() if a.text() == "Settings")
    settings_in_toolbar = window._toolbar_actions["Settings"]
    assert settings_in_menu is settings_in_toolbar


def test_panel_focus_actions_shared_between_toolbar_and_view_menu(window):
    from PySide6.QtWidgets import QMenu

    menu_view = window.findChild(QMenu, "menuView")
    for name in ("Map", "Bands", "Log"):
        in_menu = next(a for a in menu_view.actions() if a.text() == name)
        in_toolbar = window._toolbar_actions[name]
        assert in_menu is in_toolbar


def test_all_pre_existing_commands_remain_reachable(window):
    reachable = window.controls_reachable()
    for name in PRE_EXISTING_COMMANDS:
        assert reachable.get(name) is True, f"{name} not reachable"


@pytest.mark.parametrize("width,height", [(1400, 820), (683, 485)])
def test_focus_panel_raises_map_bands_log_in_wide_and_compact(window, width, height):
    # Raising/switching tabs is deterministic and safe to assert offscreen;
    # actual keyboard focus placement depends on window activation, which the
    # offscreen platform does not reliably provide, so this only checks the
    # tab/pane that _focus_panel is responsible for raising.
    window.resize(width, height)
    window._update_compact_mode()

    window._focus_panel("map")
    if window._compact:
        assert window._compact_tabs.currentWidget() is window._map_tab

    window._focus_panel("bands")
    if window._compact:
        assert window._compact_tabs.currentWidget() is window._side_pane

    window._focus_panel("log")
    if window._compact:
        assert window._compact_tabs.currentWidget() is window._side_pane
    assert window.tabs.currentWidget() is window._stats_tab
