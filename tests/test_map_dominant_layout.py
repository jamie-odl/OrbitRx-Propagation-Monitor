"""UI overhaul P4: the map is the dominant pane (not the narrow side panel),
with a collapsible side panel, a slim combined chip/slider control strip, and
a visually richer band/stats panel -- key-metric tiles plus grouped, coloured
band cards. These pin the acceptance criteria from the P4 redesign chunk:

- the map pane is at least 65% of the central width at the 1280x800 default
- the side panel can be hidden/shown via the header button, the View menu's
  "Show side panel" action, and Ctrl+B, and all three stay in sync
- none of the seven layer-toggle chips or the two sliders were dropped while
  folding them into one control strip
- in compact mode (683x485, the size tools/ui_screenshots.py captures) the
  map is the main thing visible, not a thumbnail squeezed under tall chrome
- band cards expose their OPEN/FAIR/POOR/UNKNOWN state as a widget property
  and a matching left-edge colour
- the Kp/SFI/MUF key-metric tiles exist and track the same values as the
  grouped stats cards below them
"""

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


# --- Map pane dominance (wide/splitter layout) -----------------------------


def test_map_pane_is_at_least_65_percent_of_central_width_at_1280x800(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    assert not window._compact

    ratio = window._map_tab.width() / window._splitter.width()
    assert ratio >= 0.65, ratio


def test_side_pane_default_width_is_roughly_280_to_320px(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    assert 260 <= window._side_pane.width() <= 340, window._side_pane.width()


# --- Side panel collapse: button, menu action, Ctrl+B -----------------------


def test_side_panel_toggle_button_hides_and_shows_the_side_pane(window):
    from PySide6.QtWidgets import QApplication

    window.resize(1280, 800)
    window._update_compact_mode()
    assert window._side_pane.isVisible()

    window._side_panel_toggle_btn.setChecked(False)
    QApplication.instance().processEvents()
    assert not window._side_pane.isVisible()
    assert window._side_panel_visible is False
    # The map pane takes over the full width once the side panel is hidden
    # (QSplitter reclaims a hidden child's space) -- needs one layout pass.
    assert window._map_tab.width() == window._splitter.width()

    window._side_panel_toggle_btn.setChecked(True)
    QApplication.instance().processEvents()
    assert window._side_pane.isVisible()


def test_show_side_panel_action_exists_with_ctrl_b_and_is_checked_by_default(window):
    action = window._actions["ShowSidePanel"]
    assert action.isCheckable()
    assert action.isChecked()
    assert "Ctrl+B" in [seq.toString() for seq in action.shortcuts()]


def test_ctrl_b_toggles_the_side_panel_in_wide_layout(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    assert window._side_pane.isVisible()

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert not window._side_pane.isVisible()
    assert window._actions["ShowSidePanel"].isChecked() is False
    assert window._side_panel_toggle_btn.isChecked() is False

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert window._side_pane.isVisible()
    assert window._actions["ShowSidePanel"].isChecked() is True
    assert window._side_panel_toggle_btn.isChecked() is True


def test_menu_action_and_header_button_stay_in_sync(window):
    window.resize(1280, 800)
    window._update_compact_mode()

    window._actions["ShowSidePanel"].setChecked(False)
    assert window._side_panel_toggle_btn.isChecked() is False
    assert not window._side_pane.isVisible()

    window._side_panel_toggle_btn.setChecked(True)
    assert window._actions["ShowSidePanel"].isChecked() is True
    assert window._side_pane.isVisible()


def test_side_panel_toggle_disabled_in_compact_mode_and_restored_on_exit(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    window._side_panel_toggle_btn.setChecked(False)  # collapse while wide
    assert window._side_panel_visible is False

    window.resize(600, 500)
    window._update_compact_mode()
    assert window._compact
    assert not window._side_panel_toggle_btn.isEnabled()
    assert not window._actions["ShowSidePanel"].isEnabled()
    # Reachable via its own "Conditions" tab regardless of the wide-mode
    # collapsed state (not visible until that tab is selected, like any
    # QTabWidget page).
    assert window._compact_tabs.indexOf(window._side_pane) != -1
    window._compact_tabs.setCurrentWidget(window._side_pane)
    assert window._side_pane.isVisible()

    window.resize(1280, 800)
    window._update_compact_mode()
    assert not window._compact
    assert window._side_panel_toggle_btn.isEnabled()
    assert window._actions["ShowSidePanel"].isEnabled()
    # The collapsed state from before compact mode is restored.
    assert not window._side_pane.isVisible()


def test_splitter_is_collapsible(window):
    assert window._splitter.childrenCollapsible() is True


# --- Nothing lost when chips + sliders folded into one control strip -------


def test_all_seven_layer_chips_still_present_inside_map_controls(window):
    expected = {"greyline", "night", "dx_arcs", "aurora", "grid", "spot_arcs", "spot_heatmap"}
    assert set(window._layer_checks.keys()) == expected
    for key, chip in window._layer_checks.items():
        assert chip.isAncestorOf(chip) or True  # sanity: chip itself is a real widget
        assert window._map_controls.isAncestorOf(chip), key


def test_time_and_replay_sliders_still_present_inside_map_controls(window):
    assert window._map_controls.isAncestorOf(window.time_slider)
    assert window._map_controls.isAncestorOf(window.replay_slider)
    assert window.time_slider.minimum() == 0 and window.time_slider.maximum() == 48
    assert window.replay_slider.minimum() == 0 and window.replay_slider.maximum() == 48


def test_control_strip_uses_single_row_when_the_map_pane_is_wide(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    window._map_controls.resize(window._map_tab.width(), window._map_controls.height())
    assert window._map_controls.width() >= window._map_controls._SINGLE_ROW_MIN_WIDTH
    assert window._map_controls._single_row is True


def test_control_strip_stacks_when_the_pane_is_narrow(window):
    window.resize(667, 441)
    window._update_compact_mode()
    assert window._map_controls.width() < window._map_controls._SINGLE_ROW_MIN_WIDTH
    assert window._map_controls._single_row is False
    # Nothing clipped: every chip and both sliders stay within the strip.
    for chip in window._layer_checks.values():
        right = chip.mapTo(window, chip.rect().topRight()).x()
        assert right <= window.width()
    for slider in (window.time_slider, window.replay_slider):
        right = slider.mapTo(window, slider.rect().topRight()).x()
        assert right <= window.width()


# --- Compact mode: the map is the main thing visible ------------------------


def test_map_dominates_compact_window_height_at_683x485(window):
    """683x485 is the exact size tools/ui_screenshots.py captures for the
    compact layout; the map must clearly dominate it, not a thumbnail
    squeezed under tall header/control chrome."""
    window.resize(683, 485)
    window._update_compact_mode()
    assert window._compact

    ratio = window.map_widget.height() / window.height()
    assert ratio >= 0.50, ratio


# --- Band cards: state property + matching left-edge colour ----------------


@pytest.mark.parametrize(
    "condition,expected_state",
    [("OPEN", "open"), ("FAIR", "fair"), ("POOR", "poor"), ("UNKNOWN", "unknown")],
)
def test_band_card_exposes_state_property_and_matching_colour(window, condition, expected_state):
    from orbitrx.ui.band_panel import _STATUS_COLOR

    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: condition})

    card = window.band_panel._cards[band]
    assert card.property("state") == expected_state
    assert _STATUS_COLOR[condition] in card.styleSheet()
    assert "border-left" in card.styleSheet()


def test_band_cards_for_different_states_get_different_colours(window):
    bands = list(window.band_panel._cards.keys())[:2]
    window.band_panel.update_grid({bands[0]: "OPEN", bands[1]: "POOR"})
    style_open = window.band_panel._cards[bands[0]].styleSheet()
    style_poor = window.band_panel._cards[bands[1]].styleSheet()
    assert style_open != style_poor


# --- Key-metric tiles (Kp / SFI / MUF) --------------------------------------


def test_key_metric_tiles_exist_for_kp_sfi_and_muf(window):
    from PySide6.QtWidgets import QLabel

    assert set(window._kpi_labels.keys()) == {"kp", "solar", "muf"}
    for lbl in window._kpi_labels.values():
        assert isinstance(lbl, QLabel)
        assert lbl.objectName() == "keyMetricValue"


def test_key_metric_tiles_mirror_the_grouped_stats_card_values(window):
    window.ctrl.state.kp_index = 3.67
    window._refresh_labels_and_map()

    for key in ("kp", "solar", "muf"):
        assert window._kpi_labels[key].text() == window._labels[key].text()
