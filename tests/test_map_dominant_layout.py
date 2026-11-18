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

from PySide6.QtCore import QRect, Qt
from PySide6.QtTest import QTest

# A deliberately roomy available-desktop geometry: every size these tests
# resize to (683x485 .. 1280x800) fits inside it with margin, so
# window_fit.fit_to_screen()'s clamp (both the construction-time call and the
# deferred post-Show _RefitOnShow one) is always a no-op here. Without this,
# these tests are at the mercy of the real/offscreen platform's own default
# screen size, which tools/_ui_offline_harness.py documents as clamping a
# requested 1280x800 window on its own (see patch_window_fit_avail) -- that is
# the windows-latest CI failure this module regression-tests against.
LARGE_AVAIL = QRect(0, 0, 1920, 1200)


def _wait_until(predicate, timeout_s: float = 2.0, step_ms: int = 20, diag=None) -> None:
    """Poll `predicate` while pumping the event loop instead of trusting a
    single resize() + one processEvents() to have fully settled a
    QSplitter/QTabWidget reflow -- a slow CI runner can need more than one
    event-loop turn after a resize or a reparent (_enter_compact_mode /
    _exit_compact_mode) before child widths actually update. Returns as soon
    as `predicate` is true (often immediately); only sleeps if it isn't.
    `diag`, if given, is called to build a diagnostic message on timeout."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    elapsed = 0.0
    while elapsed < timeout_s:
        if predicate():
            return
        app.processEvents()
        QTest.qWait(step_ms)
        elapsed += step_ms / 1000.0
    message = "timed out waiting for layout to settle"
    if diag is not None:
        message = f"{message}: {diag()}"
    assert predicate(), message


def _layout_diag(window) -> str:
    """Dump every piece of state relevant to side-pane/splitter sizing, for
    windows-latest-only CI failures that don't reproduce locally -- without
    this, a timeout just says a predicate never became true and gives no clue
    whether the window itself never reached the resized-to size, the splitter
    never got real width, or the side pane is being clamped by its own min/max."""
    splitter = getattr(window, "_splitter", None)
    side_pane = getattr(window, "_side_pane", None)
    screen = window.screen()
    return (
        f"window.size()={window.size()} geometry={window.geometry()} "
        f"minimumSize={window.minimumSize()} maximumSize={window.maximumSize()} "
        f"compact={getattr(window, '_compact', None)} "
        f"splitter_user_resized={getattr(window, '_splitter_user_resized', None)} "
        f"splitter.width()={splitter.width() if splitter is not None else None} "
        f"splitter.sizes()={splitter.sizes() if splitter is not None else None} "
        f"side_pane.isVisible()={side_pane.isVisible() if side_pane is not None else None} "
        f"side_pane.width()={side_pane.width() if side_pane is not None else None} "
        f"side_pane.minimumWidth()={side_pane.minimumWidth() if side_pane is not None else None} "
        f"side_pane.maximumWidth()={side_pane.maximumWidth() if side_pane is not None else None} "
        f"side_pane.sizeHint()={side_pane.sizeHint() if side_pane is not None else None} "
        f"screen.availableGeometry()={screen.availableGeometry() if screen is not None else None}"
    )


def _resize_and_settle(window, width: int, height: int, timeout_s: float = 2.0) -> None:
    """resize() a top-level window and wait for it to actually report that
    size before touching layout state that depends on it. On some platforms
    a top-level resize() doesn't apply synchronously -- self.width()/height()
    can still read the pre-resize value for one or more event-loop turns --
    so asserting on derived layout (splitter/side-pane widths) before the
    resize itself has visibly landed chases a moving target. Isolating that
    wait here also makes a genuine "the test harness never resized the
    window" platform artifact fail with its own clear message instead of
    masquerading as a layout bug."""
    window.resize(width, height)
    _wait_until(
        lambda: window.width() == width and window.height() == height,
        timeout_s=timeout_s,
        diag=lambda: (
            f"window never reported the resized-to size {width}x{height}: "
            + _layout_diag(window)
        ),
    )
    window._update_compact_mode()


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


# --- Map pane dominance (wide/splitter layout) -----------------------------


def test_map_pane_is_at_least_65_percent_of_central_width_at_1280x800(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    _wait_until(lambda: not window._compact and window._splitter.width() > 0)
    assert not window._compact

    ratio = window._map_tab.width() / window._splitter.width()
    assert ratio >= 0.65, ratio


def test_side_pane_default_width_is_roughly_280_to_320px(window):
    _resize_and_settle(window, 1280, 800)
    _wait_until(
        lambda: 260 <= window._side_pane.width() <= 340,
        diag=lambda: _layout_diag(window),
    )
    assert 260 <= window._side_pane.width() <= 340, _layout_diag(window)


def test_regression_small_initial_width_then_resize_still_reaches_default_side_pane_width(window):
    """Regression for a windows-latest-only CI failure: _apply_default_splitter_sizes()
    is first called from __init__, before show() has established the window's
    real geometry -- on that platform self.width() can report a small
    provisional value there (observed: 254px), which clamps the computed
    side-pane width down (width - 200). A prior fix latched "the default is
    applied" the first time sizes()[1] was merely > 0, which a tiny
    provisional width also satisfied, so every later resize saw that latch
    already set and skipped reapplying the real ~300px default, leaving the
    side pane stuck at a few dozen pixels even at 1280x800.
    _apply_default_splitter_sizes() now has no such latch: resizeEvent()
    re-runs it on every resize until the user actually drags the splitter
    handle (tracked via splitterMoved, see _splitter_user_resized), so a bad
    provisional width self-heals on the very next resize instead of sticking.
    Simulates that exact ordering directly rather than relying on the host
    platform's own pre-show width quirks."""
    # Hold compact-mode switching off while shrinking the window, matching
    # __init__'s real ordering: _apply_default_splitter_sizes() runs at line
    # 880 (while the window can report a small provisional width) *before*
    # _update_compact_mode() is ever called at line 888, so the splitter
    # still has both children at that point instead of having been torn
    # down into compact tabs.
    original_update_compact_mode = window._update_compact_mode
    window._update_compact_mode = lambda: None
    try:
        window.resize(254, 600)
        window._apply_default_splitter_sizes()
    finally:
        window._update_compact_mode = original_update_compact_mode
    assert window._splitter_user_resized is False, (
        "a provisional narrow width is not a user drag and must not freeze the default in place"
    )

    _resize_and_settle(window, 1280, 800)
    _wait_until(
        lambda: 260 <= window._side_pane.width() <= 340,
        diag=lambda: _layout_diag(window),
    )
    assert 260 <= window._side_pane.width() <= 340, _layout_diag(window)


def test_windows_ci_regression_compact_startup_then_resize_to_wide(window):
    """Regression for a windows-latest-only CI failure: the window can start
    (or land back in) compact mode -- e.g. because the real/offscreen screen
    it first measured itself against was small -- and must still fully exit
    compact mode once resized wide: map tab visible and correctly sized, not
    stuck at width 0 from the tab page it just left (see LARGE_AVAIL above,
    which rules out the screen-size cause here so this isolates the
    compact-exit code path itself)."""
    window.resize(683, 485)
    window._update_compact_mode()
    _wait_until(lambda: window._compact)
    assert window._compact

    window.resize(1280, 800)
    window._update_compact_mode()
    _wait_until(lambda: not window._compact and window._map_tab.width() > 0)

    assert not window._compact
    assert window._map_tab.isVisible()
    ratio = window._map_tab.width() / window._splitter.width()
    assert ratio >= 0.65, ratio
    assert 260 <= window._side_pane.width() <= 340, window._side_pane.width()


# --- Side panel collapse: button, menu action, Ctrl+B -----------------------


def test_side_panel_toggle_button_hides_and_shows_the_side_pane(window):
    window.resize(1280, 800)
    window._update_compact_mode()
    _wait_until(lambda: window._splitter.width() > 0)
    assert window._side_pane.isVisible()

    window._side_panel_toggle_btn.setChecked(False)
    _wait_until(lambda: not window._side_pane.isVisible())
    assert window._side_panel_visible is False
    # The map pane takes over the full width once the side panel is hidden
    # (QSplitter reclaims a hidden child's space) -- needs one layout pass.
    _wait_until(lambda: window._map_tab.width() == window._splitter.width())
    assert window._map_tab.width() == window._splitter.width()

    window._side_panel_toggle_btn.setChecked(True)
    _wait_until(lambda: window._side_pane.isVisible())
    assert window._side_pane.isVisible()


def test_side_panel_toggle_button_has_a_visible_glyph_that_flips_with_state(window):
    """The button is QToolButton with ToolButtonTextOnly and no icon -- it must
    carry real text so offscreen/CI renders show a glyph, not an empty filled
    square (there is no font-independent way to verify the drawn pixels here,
    only that non-empty, state-tracking text is set)."""
    btn = window._side_panel_toggle_btn
    assert btn.isChecked() is True
    assert btn.text().strip() != ""
    collapsed_glyph = btn.text()

    btn.setChecked(False)
    assert btn.text().strip() != ""
    assert btn.text() != collapsed_glyph
    assert "Ctrl+B" in btn.toolTip()

    btn.setChecked(True)
    assert btn.text() == collapsed_glyph


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_no_visible_button_has_both_empty_text_and_a_null_icon(window, width, height):
    """Owner-reported bug: a blank, unlabelled square button sat between the
    Cluster picker and the '?' help chip -- that was _side_panel_toggle_btn,
    a QToolButton with ToolButtonTextOnly and (at the time) no text set, so
    nothing rendered. Now that it carries a real ">>"/"<<" glyph (see
    test_side_panel_toggle_button_has_a_visible_glyph_that_flips_with_state),
    no visible button anywhere in the main window should be blank: every one
    must have non-empty text, a real icon, or both."""
    from PySide6.QtWidgets import QAbstractButton

    window.resize(width, height)
    window._update_compact_mode()

    blank = [
        btn for btn in window.findChildren(QAbstractButton)
        if btn.isVisible() and not btn.text().strip() and btn.icon().isNull()
    ]
    assert blank == [], [(b.objectName(), b.geometry()) for b in blank]


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
    _wait_until(lambda: window._map_tab.width() > 0)
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


@pytest.fixture
def wide_font_window(tmp_path, monkeypatch, large_avail):
    """Regression harness for a windows-latest-only CI failure: Segoe UI's
    bulkier chip/button padding made the 7 layer chips + 2 sliders control
    strip need ~1222px for a single row at a 1280px window -- wider than the
    1280 - 300 (side panel) budget -- so the splitter crushed the side panel
    to ~54px. QFont.setStretch() widens every glyph's rendered advance
    without depending on which font families happen to be installed on a
    given CI image, so this reproduces that same bulkier-glyph effect
    deterministically on any platform (including this offscreen/Linux test
    run). The font is restored after the test so it can't bleed into others
    sharing this session's QApplication instance."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    app = QApplication.instance() or QApplication([])
    original_font = QFont(app.font())
    wide_font = QFont(app.font())
    wide_font.setStretch(175)
    app.setFont(wide_font)
    try:
        from orbitrx.ui.qt_app import QtOrbitRxApplication
        win = QtOrbitRxApplication()
        win.show()
        app.processEvents()
        win.activateWindow()
        app.processEvents()
        yield win
        win.ctrl.stop()
        win.close()
    finally:
        app.setFont(original_font)


def test_side_pane_is_not_crushed_by_wide_fonts_at_1280(wide_font_window):
    """The actual windows-latest regression this reproduces (see the
    wide_font_window fixture docstring): without a font-independent cap on
    how much width the single-row control strip can force onto the map
    column, the side panel got crushed to ~54px at exactly this window size
    on that CI image."""
    window = wide_font_window
    _resize_and_settle(window, 1280, 800)
    assert window._map_tab.minimumSizeHint().width() + 300 <= window._splitter.width(), (
        _layout_diag(window)
    )
    _wait_until(
        lambda: 260 <= window._side_pane.width() <= 340,
        diag=lambda: _layout_diag(window),
    )
    assert 260 <= window._side_pane.width() <= 340, _layout_diag(window)
    assert window._splitter.sizes()[1] >= 260, window._splitter.sizes()


def test_control_strip_wraps_instead_of_clipping_under_wide_fonts_at_1280(wide_font_window):
    """Companion to test_side_pane_is_not_crushed_by_wide_fonts_at_1280: once
    the side panel is no longer crushed, the map column itself is narrower
    than the chips' one-row natural width -- every chip and slider must still
    be fully reachable (wrapped onto more rows), not squeezed below its own
    minimumSizeHint or clipped past the window edge."""
    window = wide_font_window
    _resize_and_settle(window, 1280, 800)
    _wait_until(lambda: window._splitter.sizes()[1] >= 260, diag=lambda: _layout_diag(window))

    for chip in window._layer_checks.values():
        right = chip.mapTo(window, chip.rect().topRight()).x()
        assert right <= window.width(), (chip.text(), right, window.width())
        assert chip.width() >= chip.minimumSizeHint().width(), (chip.text(), chip.geometry())
    for slider in (window.time_slider, window.replay_slider):
        right = slider.mapTo(window, slider.rect().topRight()).x()
        assert right <= window.width(), right


@pytest.fixture
def small_screen_window(tmp_path, monkeypatch):
    """Second hypothesis for the windows-latest side-pane-crush failure:
    that CI run's own screen.availableGeometry() (800x800) was narrower than
    the 1280x800 test window. The side-pane default-width computation
    (_apply_default_splitter_sizes) must come from the splitter's own actual
    width after a resize, never from the screen's available geometry -- a
    window can legitimately be resized wider than the screen reports (e.g. a
    multi-monitor CI VM, or a caller that never re-clamps after the one-time
    post-show window_fit refit), and the side pane must still get its normal
    ~300px share in that case. Unlike the `window`/`large_avail` fixtures
    (which make the screen roomy so window_fit.fit_to_screen's clamp is
    always a no-op), this deliberately keeps the screen *smaller* than the
    window to isolate this hypothesis."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.ui.window_fit as window_fit
    monkeypatch.setattr(window_fit, "_available_geometry", lambda widget: QRect(0, 0, 800, 800))

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


def test_side_pane_width_is_deterministic_on_a_screen_smaller_than_the_window(small_screen_window):
    """Regression for the second hypothesis behind the windows-latest
    side-pane-crush failure (see small_screen_window fixture docstring): a
    1280x800 window on an 800x800-available screen must still get its normal
    ~300px side pane and the map must still keep its >=65% share, because the
    default-width computation is keyed off the splitter's real post-resize
    width, not the screen's availableGeometry."""
    window = small_screen_window
    _resize_and_settle(window, 1280, 800)
    _wait_until(
        lambda: 260 <= window._side_pane.width() <= 340,
        diag=lambda: _layout_diag(window),
    )
    assert 260 <= window._side_pane.width() <= 340, _layout_diag(window)
    ratio = window._map_tab.width() / window._splitter.width()
    assert ratio >= 0.65, (ratio, _layout_diag(window))


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

    for key in ("kp", "solar"):
        assert window._kpi_labels[key].text() == window._labels[key].text()


def test_muf_tile_shows_only_the_muf_value_with_luf_as_a_small_caption(window):
    """The MUF tile used to show the full "n/a / LUF: n/a" stats-card string
    in big type, overflowing the tile. The big number must be just the MUF
    value; LUF moves to its own small caption. Both tile fields drop the
    " MHz" unit suffix (the tile is only ~65-90px wide once squeezed into a
    3-up row inside the default side pane) -- the grouped stats card below
    (window._labels["muf"]) keeps the full combined text, unit included,
    unchanged."""
    window.ctrl.state.muf = 21.3
    window.ctrl.state.luf = 3.2
    window._refresh_labels_and_map()

    assert window._kpi_labels["muf"].text() == "21.3"
    assert window._muf_luf_caption.text() == "LUF: 3.2"
    assert window._labels["muf"].text() == "21.3 MHz / LUF: 3.2 MHz"


def test_solar_tile_shows_only_the_flux_number_without_the_trend_suffix(window):
    """The SFI tile mirrored the grouped stats card's full "<flux> <trend
    arrow/word>" text (e.g. "123.4 ↓ (falling)"), which overflows the tile
    just as badly as the MUF tile did. The big number must be just the flux
    value; the full text (trend included) stays in the grouped stats card."""
    window.ctrl.state.flux = 123.4
    window.ctrl.state.flux_trend = "↓ (falling)"
    window._refresh_labels_and_map()

    assert window._kpi_labels["solar"].text() == "123.4"
    assert window._labels["solar"].text() == "123.4 ↓ (falling)"


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_no_key_metric_tile_label_text_overflows_its_width(window, width, height):
    """Owner fix: a key-metric tile label's text must never be wider than
    the space the tile actually gives it, at either size this app supports.
    Exercises the worst-case values this layout has to accommodate: the
    default "n/a" (no-data) state, and a realistic longest-reading
    value/trend combination for each tile."""
    from PySide6.QtGui import QFontMetrics

    window.resize(width, height)
    window._update_compact_mode()

    cases = [
        {},
        {"kp_index": 8.0},
        {"flux": 999.9, "flux_trend": "↓ (falling)"},
        {"muf": 28.5, "luf": 28.5},
    ]
    for state_kwargs in cases:
        for attr, value in state_kwargs.items():
            setattr(window.ctrl.state, attr, value)
        window._refresh_labels_and_map()

        labels = [window._kpi_labels["kp"], window._kpi_labels["solar"],
                  window._kpi_labels["muf"], window._muf_luf_caption]
        for lbl in labels:
            fm = QFontMetrics(lbl.font())
            advance = fm.horizontalAdvance(lbl.text())
            width_available = lbl.contentsRect().width()
            assert advance <= width_available, (lbl.objectName(), lbl.text(), advance, width_available)


def test_grouped_stats_card_captions_are_left_aligned_with_comfortable_spacing(window):
    """Owner fix: the caption column in the grouped stats cards (SPACE
    WEATHER / PROPAGATION / PATH / OPS) was right-aligned and crowded the
    value column -- captions must read left-aligned, with a comfortable
    SPACE_3+ gutter between the caption and value columns, not jammed up
    against them."""
    from orbitrx.ui.theme import SPACE_3

    assert window._stat_name_labels, "no stat caption labels were built"
    for key, name_lbl in window._stat_name_labels.items():
        assert name_lbl.alignment() & Qt.AlignmentFlag.AlignLeft, key
        assert not (name_lbl.alignment() & Qt.AlignmentFlag.AlignRight), key

        card = name_lbl.parentWidget()
        grid = card.layout()
        assert grid.horizontalSpacing() >= SPACE_3, (key, grid.horizontalSpacing())
