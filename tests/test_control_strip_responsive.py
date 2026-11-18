"""Round 6: SPEC §11 control strip + §13 responsive rules.

- Layers (Greyline/Night/DX/Aurora/Grid) and Spots (Live/Heat) are two
  separate joined toggle groups; Layers collapses into a
  QToolButton#layersMenuButton + checkable QMenu at compact widths, Spots
  stays inline at every width.
- The time sliders shrink to 84px at compact widths and move into a
  "Time ▾" popover below 600px window width.
- The menu-bar corner shows a real SFI/Kp/A-index summary (never a sample)
  while the window is narrow enough to hide the side panel.
- The band strip collapses to ~30px chips at compact widths or a short
  window, with the frequency moved to the card's tooltip.
- Nothing is clipped and no scroll area shows a horizontal scrollbar at
  either 1280x800 or 683x485.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest

from orbitrx.ui.theme import NO_DATA

LARGE_AVAIL = QRect(0, 0, 1920, 1200)


def _not_clipped_horizontally(control, window) -> bool:
    top_left = control.mapTo(window, control.rect().topLeft())
    return 0 <= top_left.x() and top_left.x() + control.width() <= window.width()


def _visible_horizontal_scrollbars(widget) -> list[str]:
    from PySide6.QtWidgets import QScrollArea

    offenders = []
    for area in widget.findChildren(QScrollArea):
        bar = area.horizontalScrollBar()
        if bar is not None and bar.isVisible():
            offenders.append(area.objectName() or area.__class__.__name__)
    return offenders


def _resize_and_settle(window, width: int, height: int) -> None:
    from PySide6.QtWidgets import QApplication

    window.resize(width, height)
    app = QApplication.instance()
    for _ in range(20):
        app.processEvents()
        if window.width() == width and window.height() == height:
            break
        QTest.qWait(20)
    window._update_compact_mode()
    app.processEvents()


@pytest.fixture
def large_avail(monkeypatch):
    import orbitrx.ui.window_fit as window_fit

    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: LARGE_AVAIL)
    return LARGE_AVAIL


@pytest.fixture
def window(tmp_path, monkeypatch, large_avail):
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


_LAYER_ONLY_KEYS = ("greyline", "night", "dx_arcs", "aurora", "grid")
_SPOT_KEYS = ("spot_arcs", "spot_heatmap")


# --- Layers group / layersMenuButton ---------------------------------------


def test_layers_group_visible_and_reachable_at_wide_width(window):
    _resize_and_settle(window, 1280, 800)
    assert not window._compact
    assert window._layers_group.isVisible()
    assert not window._layers_menu_btn.isVisible()
    for key in _LAYER_ONLY_KEYS:
        btn = window._layer_checks[key]
        assert btn.isVisible()
        assert _not_clipped_horizontally(btn, window)


def test_layers_collapse_to_menu_button_at_compact_width(window):
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert not window._layers_group.isVisible()
    assert window._layers_menu_btn.isVisible()
    assert _not_clipped_horizontally(window._layers_menu_btn, window)
    assert window._layers_menu_btn.text().startswith("Layers ")
    assert window._layers_menu_btn.text().endswith("▾")


def test_layers_menu_actions_stay_reachable_and_mirror_real_state(window):
    """Every layer toggle stays functionally reachable through the menu even
    though it's visually collapsed -- toggling a proxy QAction flips the
    real _layer_checks[key] button (which still drives map_layers/the map
    redraw), and the menu re-syncs its own checked state from the buttons
    each time it's about to show."""
    _resize_and_settle(window, 683, 485)
    for key in _LAYER_ONLY_KEYS:
        action = window._layers_menu_actions[key]
        button = window._layer_checks[key]
        before = button.isChecked()
        action.setChecked(not before)
        assert button.isChecked() is (not before)
        # ... and the other direction: an external change to the button
        # (e.g. Settings) is picked up the next time the menu is shown.
        button.setChecked(before)
        window._sync_layers_menu()
        assert action.isChecked() is before


def test_layers_menu_badge_counts_checked_layers(window):
    _resize_and_settle(window, 683, 485)
    for key in _LAYER_ONLY_KEYS:
        window._layer_checks[key].setChecked(False)
    assert window._layers_menu_btn.text() == "Layers 0 ▾"
    window._layer_checks["greyline"].setChecked(True)
    window._layer_checks["night"].setChecked(True)
    assert window._layers_menu_btn.text() == "Layers 2 ▾"


def test_spots_group_stays_inline_at_both_widths(window):
    for width, height in ((1280, 800), (683, 485)):
        _resize_and_settle(window, width, height)
        assert window._spots_group.isVisible()
        for key in _SPOT_KEYS:
            btn = window._layer_checks[key]
            assert btn.isVisible()
            assert _not_clipped_horizontally(btn, window)


# --- Sliders / time popover --------------------------------------------


def test_sliders_shrink_at_compact_width(window):
    from orbitrx.ui.theme import SLIDER_WIDTH, SLIDER_WIDTH_COMPACT

    _resize_and_settle(window, 1280, 800)
    assert window.time_slider.width() == SLIDER_WIDTH
    assert window.replay_slider.width() == SLIDER_WIDTH

    _resize_and_settle(window, 683, 485)
    assert window.time_slider.width() == SLIDER_WIDTH_COMPACT
    assert window.replay_slider.width() == SLIDER_WIDTH_COMPACT


def test_time_popover_hidden_at_683_width(window):
    _resize_and_settle(window, 683, 485)
    assert window._time_popover is False
    assert window._time_popover_btn.isVisible() is False
    assert window.time_slider.isVisible()


@pytest.fixture
def tiny_window(tmp_path, monkeypatch):
    """SPEC §11's "below 600px width" time-popover breakpoint is narrower
    than window_fit's own 640px main-window floor (fit_to_screen(self, 640,
    440), kept as-is per the hard rules) -- the main window can never
    *shrink* to under 600 on a normal desktop. fit_to_screen's own
    clamp_rect() caps that floor to the *available screen* size when the
    screen itself is smaller (see test_fit_to_screen_minimum_size_capped_to_
    tiny_available_geometry in test_window_fit.py), so this fixture starts
    the window on a deliberately tiny fake screen -- the only way to
    legitimately reach sub-600 widths without touching window_fit's floor.
    Once constructed, plain resize() calls aren't re-clamped (only
    fit_to_screen's own construction/first-show calls consult the fake
    screen), so growing back above 600/616 for the hysteresis check works
    normally."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    import orbitrx.ui.window_fit as window_fit

    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: QRect(0, 0, 580, 500))

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
    assert win.width() < 600, f"fixture setup didn't reach a sub-600 width: {win.width()}"
    yield win
    win.ctrl.stop()
    win.close()


def test_time_popover_appears_below_600px_with_hysteresis(tiny_window):
    window = tiny_window
    assert window._time_popover is True
    assert window._time_popover_btn.isVisible()
    assert _not_clipped_horizontally(window._time_popover_btn, window)

    # Hysteresis: widening past 616 (not just 600) disables it again.
    _resize_and_settle(window, 610, 485)
    assert window._time_popover is True
    _resize_and_settle(window, 620, 485)
    assert window._time_popover is False
    assert window.time_slider.isVisible()

    _resize_and_settle(window, 599, 485)
    assert window._time_popover is True


def test_time_popover_still_reaches_the_real_sliders(tiny_window):
    window = tiny_window
    assert window._time_popover is True
    action = window._time_popover_btn.menu().actions()[0]
    assert action.defaultWidget() is window._time_box
    window.time_slider.setValue(5)
    assert window.lbl_slider.text() != ""


# --- Corner space-weather summary ----------------------------------------


def test_corner_summary_shows_no_data_before_first_fetch(window):
    _resize_and_settle(window, 683, 485)
    assert window.ctrl.state.last_weather_update is None
    assert window._corner_summary_lbl.isVisible()
    text = window._corner_summary_lbl.text()
    assert NO_DATA in text
    assert "142" not in text  # never the mockup's sample SFI value


def test_corner_summary_shows_real_values_once_loaded(window):
    import datetime

    _resize_and_settle(window, 683, 485)
    window.ctrl.state.flux = 123.4
    window.ctrl.state.kp_index = 3.0
    window.ctrl.state.a_index = 12
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_key_tiles()
    text = window._corner_summary_lbl.text()
    assert "123.4" in text
    assert "3.0" in text
    assert "12" in text


def test_corner_summary_hidden_above_820px_with_hysteresis(window):
    _resize_and_settle(window, 1280, 800)
    assert window._corner_summary_lbl.isVisible() is False

    _resize_and_settle(window, 800, 800)
    assert window._corner_summary_lbl.isVisible() is True

    _resize_and_settle(window, 828, 800)
    assert window._corner_summary_lbl.isVisible() is True  # inside the hysteresis band
    _resize_and_settle(window, 900, 800)
    assert window._corner_summary_lbl.isVisible() is False


# --- Band strip compact chips ----------------------------------------------


def test_band_chips_full_size_at_wide_width(window):
    _resize_and_settle(window, 1280, 800)
    assert window.band_panel.is_compact() is False


def test_band_chips_compact_at_683_width(window):
    _resize_and_settle(window, 683, 485)
    assert window.band_panel.is_compact() is True
    for band, card in window.band_panel._cards.items():
        assert card.height() <= 30
        assert card.toolTip() != ""


def test_band_chips_compact_below_560_height_even_when_wide(window):
    _resize_and_settle(window, 1280, 500)
    assert not window._compact
    assert window.band_panel.is_compact() is True


def test_band_chips_not_compact_above_both_thresholds(window):
    _resize_and_settle(window, 1280, 800)
    assert window.band_panel.is_compact() is False


# --- No clipping / no horizontal scrollbars --------------------------------


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_no_horizontal_scrollbar_at_either_size(window, width, height):
    _resize_and_settle(window, width, height)
    assert _visible_horizontal_scrollbars(window) == []


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_control_strip_widgets_not_clipped_at_either_size(window, width, height):
    _resize_and_settle(window, width, height)
    controls = [window.time_slider, window.replay_slider, window._spots_group]
    if window._layers_group.isVisible():
        controls.append(window._layers_group)
    if window._layers_menu_btn.isVisible():
        controls.append(window._layers_menu_btn)
    if window._time_popover_btn.isVisible():
        controls.append(window._time_popover_btn)
    for control in controls:
        assert control.width() > 0
        assert _not_clipped_horizontally(control, window)


# --- _ReflowGrid column-count transitions (Round 9) -------------------------


def test_reflow_grid_widgets_never_squeezed_below_minimum_after_column_change():
    """Regression test for a windows-latest-only CI failure (CI 44412075470):
    a layer-toggle chip ("Greyline") rendered a few px narrower than its own
    minimumSizeHint() after the control strip wrapped onto extra rows under a
    bulkier font. Root cause, reproducible deterministically on any platform
    without depending on real font metrics: QGridLayout.setColumnMinimumWidth()
    sticks to a column *index* for the layout's lifetime, so _ReflowGrid
    resizing from more columns to fewer (e.g. 5 -> 3, wrapping onto extra
    rows) left the no-longer-used trailing column indices still reserving
    their old minimum widths. Growing back to more columns later then had to
    fit every real column *and* those stale phantom ones into the same
    space, squeezing every widget below its own minimumSizeHint() -- not just
    a few px, but by half or more. This drives a plain _ReflowGrid directly
    through exactly that narrow-then-wide transition; no QFont trickery
    needed since the bug is in the layout bookkeeping, not glyph metrics."""
    from PySide6.QtWidgets import QToolButton

    from orbitrx.ui.qt_app import _ReflowGrid

    buttons = [QToolButton() for _ in range(5)]
    for btn, text in zip(buttons, ["Greyline", "Night", "DX", "Aurora", "Grid"]):
        btn.setText(text)
        btn.setCheckable(True)

    grid = _ReflowGrid(buttons, min_item_width=0, max_cols=len(buttons), spacing=0)
    grid.show()
    grid.resize(1000, 40)
    QTest.qWait(10)
    assert grid._cols == len(buttons)

    grid.resize(10, 400)
    QTest.qWait(10)
    assert grid._cols < len(buttons)

    grid.resize(1000, 40)
    QTest.qWait(10)
    assert grid._cols == len(buttons)
    for btn in buttons:
        assert btn.width() >= btn.minimumSizeHint().width(), (btn.text(), btn.geometry())
    grid.deleteLater()
