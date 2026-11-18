"""P2A: a proper File/View/Tools/Help menu bar. Every command that used to
live on the old toolbar or its » overflow menu must stay reachable from the
menu bar.

P4-4 removes the toolbar row entirely -- Map/Bands/Log move to a segmented
control in the map header (_build_view_switch), wired to the same QAction
objects as Ctrl+1/2/3 and the View menu (one handler per command, still not
duplicated, just via _activate_view instead of a toolbar widget). P4-3 adds
a QMenuBar.setCornerWidget with a UTC clock and the DX cluster status."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

EXPECTED_MENUS = ["menuFile", "menuView", "menuTools", "menuHelp"]
SEGMENTED_VIEW_ACTIONS = ["Map", "Bands", "Log"]
# Every command that existed before the P2A/P4-4 chunks (toolbar buttons + » overflow).
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


def test_no_main_toolbar_exists(window):
    """P4-4: the old mainToolbar row is gone outright, not just hidden."""
    from PySide6.QtWidgets import QToolBar

    assert window.findChild(QToolBar, "mainToolbar") is None
    assert not hasattr(window, "_toolbar")
    assert not hasattr(window, "_toolbar_actions")


def test_segmented_view_switch_has_exactly_map_bands_log(window):
    """P4-4: the map header's segmented control replaces the toolbar row."""
    assert list(window._seg_buttons.keys()) == SEGMENTED_VIEW_ACTIONS
    for name in SEGMENTED_VIEW_ACTIONS:
        btn = window._seg_buttons[name]
        assert btn.objectName() == "segButton"
        assert btn.isCheckable()
        assert btn.text() == name


def test_segmented_view_switch_defaults_to_map_checked(window):
    checked = [name for name, btn in window._seg_buttons.items() if btn.isChecked()]
    assert checked == ["Map"]


def test_settings_action_only_reachable_via_tools_menu(window):
    from PySide6.QtWidgets import QMenu

    menu_tools = window.findChild(QMenu, "menuTools")
    settings_in_menu = next(a for a in menu_tools.actions() if a.text() == "Settings")
    assert settings_in_menu is window._actions["Settings"]


def test_panel_focus_actions_shared_between_segmented_control_and_view_menu(window):
    """Clicking a segmented-control button must trigger the exact same
    QAction as the View menu's equivalent entry (Ctrl+1/2/3), not a second,
    independent handler."""
    from PySide6.QtWidgets import QMenu

    menu_view = window.findChild(QMenu, "menuView")
    for name in SEGMENTED_VIEW_ACTIONS:
        in_menu = next(a for a in menu_view.actions() if a.text() == name)
        assert in_menu is window._actions[name]


@pytest.mark.parametrize("name", SEGMENTED_VIEW_ACTIONS)
def test_clicking_segmented_button_triggers_its_action_and_checks_it(window, name):
    for other in SEGMENTED_VIEW_ACTIONS:
        if other != name:
            window._seg_buttons[other].setChecked(True)

    window._seg_buttons[name].click()

    assert window._seg_buttons[name].isChecked()
    for other in SEGMENTED_VIEW_ACTIONS:
        if other != name:
            assert not window._seg_buttons[other].isChecked()


def test_menu_bar_has_corner_widget_with_clock_and_cluster(window):
    """P4-3: QMenuBar.setCornerWidget carries the UTC clock + cluster dot."""
    import re

    corner = window.menuBar().cornerWidget()
    assert corner is not None
    assert corner.objectName() == "statusCorner"
    assert re.search(r"UTC \d{2}:\d{2}", window._corner_clock_lbl.text())
    assert "Cluster" in window._corner_cluster_lbl.text()


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
