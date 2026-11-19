"""P2C: window-wide keyboard shortcuts on the shared QActions (Ctrl+1/2/3 to
focus Map/Bands/Log, Ctrl+, to open Settings, F5 to refresh). Each action's
shortcut context defaults to Qt.WindowShortcut, so these must fire no matter
which child widget inside the main window currently has focus; this is
exercised here via QTest.keyClick on the window itself, in both the wide
(splitter) and compact (<900px tab-swap) layouts."""

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


def _shortcut_strings(action) -> list[str]:
    return [seq.toString() for seq in action.shortcuts()]


@pytest.mark.parametrize(
    "action_key,expected",
    [
        ("Map", "Ctrl+1"),
        ("Bands", "Ctrl+2"),
        ("Log", "Ctrl+3"),
        ("Settings", "Ctrl+,"),
        ("Refresh", "F5"),
    ],
)
def test_action_has_expected_shortcut(window, action_key, expected):
    action = window._actions[action_key]
    assert expected in _shortcut_strings(action)


def test_settings_and_refresh_shortcuts_are_unique_across_all_actions(window):
    """No two commands should fight over the same key chord."""
    seen: dict[str, str] = {}
    for key, action in window._actions.items():
        for text in _shortcut_strings(action):
            assert text not in seen, f"{key!r} and {seen.get(text)!r} both bind {text!r}"
            seen[text] = key


def test_menu_items_display_their_shortcut_text(window):
    settings_action = window._actions["Settings"]
    assert settings_action.shortcut().toString() == "Ctrl+,"
    refresh_action = window._actions["Refresh"]
    assert refresh_action.shortcut().toString() == "F5"


@pytest.mark.parametrize(
    "key,modifier,action_key,which",
    [
        (Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, "Map", "map"),
        (Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier, "Bands", "bands"),
        (Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier, "Log", "log"),
    ],
)
def test_ctrl_1_2_3_focus_the_right_panel_in_wide_layout(window, key, modifier, action_key, which):
    window.resize(1280, 800)
    window._update_compact_mode()
    assert not window._compact

    calls = []
    window._focus_panel = lambda w, _calls=calls: _calls.append(w)
    QTest.keyClick(window, key, modifier)

    assert calls == [which]


@pytest.mark.parametrize(
    "key,modifier,which",
    [
        (Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, "map"),
        (Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier, "bands"),
        (Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier, "log"),
    ],
)
def test_ctrl_1_2_3_focus_the_right_panel_in_compact_layout(window, key, modifier, which):
    window.resize(600, 500)
    window._update_compact_mode()
    assert window._compact

    calls = []
    window._focus_panel = lambda w, _calls=calls: _calls.append(w)
    QTest.keyClick(window, key, modifier)

    assert calls == [which]


def test_ctrl_1_switches_compact_tabs_to_map(window):
    window.resize(600, 500)
    window._update_compact_mode()
    assert window._compact

    QTest.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert window._compact_tabs.currentWidget() is window._map_tab


def test_ctrl_2_switches_compact_tabs_to_side_pane_and_focuses_bands(window):
    """Band cards live under the map at the wide/1280 width (SPEC §6.2/§8),
    but move back into the side panel in compact mode (G10, the compact
    band-chips-under-the-map treatment, is a later round) -- so Ctrl+2/
    "Bands" still switches to the Conditions tab here, same as before."""
    window.resize(600, 500)
    window._update_compact_mode()
    assert window._compact

    # Start on the map tab so switching is actually observed.
    window._compact_tabs.setCurrentWidget(window._map_tab)
    QTest.keyClick(window, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    assert window._compact_tabs.currentWidget() is window._side_pane
    assert window.band_panel.hasFocus()


def test_f5_triggers_auto_refresh_in_wide_and_compact_layouts(window):
    for width, height in [(1280, 800), (600, 500)]:
        window.resize(width, height)
        window._update_compact_mode()

        calls = []
        window._auto_refresh = lambda _calls=calls: _calls.append("refresh")
        QTest.keyClick(window, Qt.Key.Key_F5)

        assert calls == ["refresh"]


def test_ctrl_comma_opens_settings_dialog_without_blocking(window, monkeypatch):
    """Settings is opened modally via QDialog.exec(); patch it so the test
    never actually blocks on a real event loop, mirroring how
    tests/test_settings_dialog.py avoids calling exec() at all."""
    from PySide6.QtWidgets import QDialog

    calls = []

    def fake_exec(self):
        calls.append(self)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", fake_exec)

    QTest.keyClick(window, Qt.Key.Key_Comma, Qt.KeyboardModifier.ControlModifier)

    assert len(calls) == 1
    assert calls[0].__class__.__name__ == "SettingsDialog" or calls[0].windowTitle() == "Settings"
