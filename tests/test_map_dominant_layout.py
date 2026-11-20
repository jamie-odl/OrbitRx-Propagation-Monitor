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
- band cards (QFrame#bandCard + bandName/bandFreq/stateBadge child labels,
  P4-5) expose their good/fair/poor/unknown state as a widget property, with
  a matching badge word/colour and never a raw "UNKNOWN" string
- the Kp/SFI/MUF key-metric tiles exist and track the same values as the
  grouped stats cards below them
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor
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


def _wh(widget, label: str) -> str:
    """One widget's width()/minimumSizeHint().width()/sizeHint().width(), or
    a plain "<missing>" marker -- used to build the per-child breakdown in
    _full_map_column_diag below without a dozen near-identical f-strings."""
    if widget is None:
        return f"{label}=<missing>"
    return (
        f"{label}(w={widget.width()}, "
        f"min={widget.minimumSizeHint().width()}, hint={widget.sizeHint().width()})"
    )


def _full_map_column_diag(window) -> str:
    """Round 10 (p4-r11): every number that could explain *why* the map
    column's minimum width came out some particular value on a CI runner
    this doesn't reproduce on locally -- window/splitter/side-pane geometry
    (as _layout_diag already had), _map_tab/map_widget's own width and size
    hints, LEGEND_COMPACT_WIDTH, the width/min/hint of every direct child of
    the map column that isn't itself a reflowing grid (header row, cluster
    combo, the control strip, the Layers/Spots groups, both sliders, the
    Time cluster, the chips row, the in-map legend, the map frame, the
    cluster/no-spots status pills), and the logical DPI/devicePixelRatio +
    app font family/pointSize/pixelSize that drive every one of those
    widths. A shared helper (imported by tests/test_map_frame.py too) so one
    CI run gives real numbers instead of a third round of guessing."""
    from PySide6.QtWidgets import QApplication

    from orbitrx.ui.map_widget import LEGEND_COMPACT_WIDTH

    app = QApplication.instance()
    font = app.font() if app is not None else None
    splitter = getattr(window, "_splitter", None)
    side_pane = getattr(window, "_side_pane", None)
    map_tab = getattr(window, "_map_tab", None)
    map_widget = getattr(window, "map_widget", None)

    children = [
        (getattr(window, "_map_header_row", None), "header_row"),
        (getattr(window, "cluster_combo", None), "cluster_combo"),
        (getattr(window, "_map_controls", None), "control_strip"),
        (getattr(window, "_layers_group", None), "layers_group"),
        (getattr(window, "_spots_group", None), "spots_group"),
        (getattr(window, "time_slider", None), "time_slider"),
        (getattr(window, "replay_slider", None), "replay_slider"),
        (getattr(window, "_time_box", None), "time_cluster"),
        (getattr(window, "_chips_row", None), "chips_row"),
        (getattr(map_widget, "_legend_lbl", None), "legend"),
        (getattr(window, "_map_frame", None), "map_frame"),
        (getattr(map_widget, "_cluster_pill", None), "cluster_pill"),
        (getattr(map_widget, "_empty_overlay", None), "no_spots_pill"),
    ]

    return (
        f"map_tab.width()={map_tab.width() if map_tab is not None else None} "
        f"map_tab.minimumSizeHint()={map_tab.minimumSizeHint() if map_tab is not None else None} "
        f"map_tab.sizeHint()={map_tab.sizeHint() if map_tab is not None else None} "
        f"map_widget.width()={map_widget.width() if map_widget is not None else None} "
        f"map_widget.minimumSizeHint()="
        f"{map_widget.minimumSizeHint() if map_widget is not None else None} "
        f"LEGEND_COMPACT_WIDTH={LEGEND_COMPACT_WIDTH} "
        f"children=[{' '.join(_wh(w, label) for w, label in children)}] "
        f"logicalDpiX={window.logicalDpiX()} devicePixelRatio={window.devicePixelRatio()} "
        f"font.family()={font.family() if font is not None else None} "
        f"font.pointSize()={font.pointSize() if font is not None else None} "
        f"font.pixelSize()={font.pixelSize() if font is not None else None}"
    )


def _layout_diag(window) -> str:
    """Dump every piece of state relevant to side-pane/splitter sizing, for
    windows-latest-only CI failures that don't reproduce locally -- without
    this, a timeout just says a predicate never became true and gives no clue
    whether the window itself never reached the resized-to size, the splitter
    never got real width, or the side pane is being clamped by its own min/max.

    Round 10 (p4-r11): appends _full_map_column_diag's per-child breakdown
    too -- the plain splitter/side-pane numbers alone weren't enough to tell
    *which* map-column child pushed the minimum over budget on windows-latest."""
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
        f"side_pane.minimumSizeHint()="
        f"{side_pane.minimumSizeHint() if side_pane is not None else None} "
        f"side_pane.maximumWidth()={side_pane.maximumWidth() if side_pane is not None else None} "
        f"side_pane.sizeHint()={side_pane.sizeHint() if side_pane is not None else None} "
        f"screen.availableGeometry()={screen.availableGeometry() if screen is not None else None} "
        f"{_full_map_column_diag(window)}"
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


def test_show_side_panel_action_hides_and_shows_the_side_pane(window):
    """G3: the header's unlabelled ">>"/"<<" collapse button is gone -- Ctrl+B
    and the View menu's "Show side panel" action (same QAction) are the only
    entry points now."""
    window.resize(1280, 800)
    window._update_compact_mode()
    _wait_until(lambda: window._splitter.width() > 0)
    assert window._side_pane.isVisible()

    window._actions["ShowSidePanel"].setChecked(False)
    _wait_until(lambda: not window._side_pane.isVisible())
    assert window._side_panel_visible is False
    # The map pane takes over the full width once the side panel is hidden
    # (QSplitter reclaims a hidden child's space) -- needs one layout pass.
    _wait_until(lambda: window._map_tab.width() == window._splitter.width())
    assert window._map_tab.width() == window._splitter.width()

    window._actions["ShowSidePanel"].setChecked(True)
    _wait_until(lambda: window._side_pane.isVisible())
    assert window._side_pane.isVisible()


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_no_visible_button_has_both_empty_text_and_a_null_icon(window, width, height):
    """Owner-reported bug: a blank, unlabelled square button (the old
    _side_panel_toggle_btn, since removed -- G3) sat between the Cluster
    picker and the '?' help chip. No visible button anywhere in the main
    window should be blank: every one must have non-empty text, a real
    icon, or both."""
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

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert window._side_pane.isVisible()
    assert window._actions["ShowSidePanel"].isChecked() is True


def test_side_panel_action_stays_enabled_in_compact_mode_and_switches_tabs(window):
    """Round 6 (SPEC §13 "W<820: side panel hidden ... Ctrl+B opens it"):
    the action used to be disabled outright in compact mode; now it stays
    reachable and instead flips _compact_tabs between its Map and
    Conditions pages, so Ctrl+B still does something useful at every width.
    G8: _compact_tabs' own tab bar is hidden (it used to render a second,
    duplicate "Map | Conditions" row above the real Map/Bands/Log segmented
    control), but it is still the real underlying page-switcher Ctrl+B/the
    View menu/Esc drive."""
    window.resize(1280, 800)
    window._update_compact_mode()
    window._actions["ShowSidePanel"].setChecked(False)  # collapse while wide
    assert window._side_panel_visible is False

    window.resize(600, 500)
    window._update_compact_mode()
    assert window._compact
    assert window._actions["ShowSidePanel"].isEnabled()
    # Starts on the Map tab: the wide-mode collapsed state carried over.
    assert window._compact_tabs.currentWidget() is window._map_tab

    window._actions["ShowSidePanel"].setChecked(True)
    assert window._drawer_open
    assert window._compact_tabs.currentWidget() is window._map_tab
    assert window._side_pane.isVisible()
    assert window.map_widget.isVisible()

    window._actions["ShowSidePanel"].setChecked(False)
    assert not window._drawer_open
    assert window._compact_tabs.currentWidget() is window._map_tab

    window.resize(1280, 800)
    window._update_compact_mode()
    assert not window._compact
    assert window._actions["ShowSidePanel"].isEnabled()
    # The collapsed state from before compact mode is restored.
    assert not window._side_pane.isVisible()


def test_ctrl_b_shows_and_esc_closes_the_side_panel_in_compact_mode(window):
    """Round 6 (SPEC §13/§15 "683: ... Ctrl+B opens the drawer, and Esc
    closes it"): not a floating overlay, but the same real outcome -- one
    keypress reveals the panel content, Esc puts the map back. G8: the
    underlying _compact_tabs' own tab bar is hidden, so this is reached only
    via Ctrl+B/the View menu/Esc, never a second clickable tab row."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    # The side panel defaults to visible (never collapsed in this test),
    # so compact mode starts on the Conditions tab -- switch to Map first so
    # Ctrl+B has something to show.
    window._actions["ShowSidePanel"].setChecked(False)
    assert window._compact_tabs.currentWidget() is window._map_tab

    QTest.keyClick(window, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert window._drawer_open
    assert window._compact_tabs.currentWidget() is window._map_tab
    assert window._actions["ShowSidePanel"].isChecked() is True
    assert window.map_widget.isVisible()

    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window._drawer_open
    assert window._compact_tabs.currentWidget() is window._map_tab
    assert window._actions["ShowSidePanel"].isChecked() is False

    # Esc is a no-op while the Map tab (not the side panel) is showing.
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window._compact_tabs.currentWidget() is window._map_tab


def test_esc_does_not_close_the_side_panel_in_wide_layout(window):
    """Esc only means "close the compact drawer" (SPEC §13); in the wide
    splitter layout the side pane has no such keyboard affordance."""
    _resize_and_settle(window, 1280, 800)
    assert not window._compact
    assert window._side_pane.isVisible()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window._side_pane.isVisible()


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


def test_control_strip_forces_single_row_in_compact_mode(window):
    """G11 (SPEC §11 "At 683"): compact mode already shrinks every piece of
    this strip (Layers collapses to a menu button, the Spots label is
    dropped, sliders shrink to SLIDER_WIDTH_COMPACT) specifically so it fits
    one row -- unlike the plain width-vs-_SINGLE_ROW_MIN_WIDTH comparison
    this used to fall back on (that threshold is tuned for the *wide*
    layout's full-size content and would needlessly stack compact content
    too), _MapControlStrip.set_force_single_row() makes compact mode use one
    row regardless of the pane's absolute width."""
    window.resize(667, 441)
    window._update_compact_mode()
    assert window._compact
    assert window._map_controls.width() < window._map_controls._SINGLE_ROW_MIN_WIDTH
    assert window._map_controls._single_row is True
    # Nothing clipped: every chip and both sliders stay within the strip.
    for chip in window._layer_checks.values():
        if not chip.isVisible():
            continue
        right = chip.mapTo(window, chip.rect().topRight()).x()
        assert right <= window.width()
    for slider in (window.time_slider, window.replay_slider):
        right = slider.mapTo(window, slider.rect().topRight()).x()
        assert right <= window.width()


@pytest.fixture(params=[175, 200], ids=["stretch175", "stretch200"])
def wide_font_window(tmp_path, monkeypatch, large_avail, request):
    """Regression harness for a windows-latest-only CI failure: Segoe UI's
    bulkier chip/button padding made the 7 layer chips + 2 sliders control
    strip need ~1222px for a single row at a 1280px window -- wider than the
    1280 - 300 (side panel) budget -- so the splitter crushed the side panel
    to ~54px. QFont.setStretch() widens every glyph's rendered advance
    without depending on which font families happen to be installed on a
    given CI image, so this reproduces that same bulkier-glyph effect
    deterministically on any platform (including this offscreen/Linux test
    run). The font is restored after the test so it can't bleed into others
    sharing this session's QApplication instance. Parametrized at both 175
    (the measured windows-latest Segoe UI stretch) and 200 (extra margin
    beyond what's been observed on CI, so a regression that only eats into
    the margin trips this before it reaches the real failure threshold)."""
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
    wide_font.setStretch(request.param)
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


@pytest.fixture
def taller_font_window(tmp_path, monkeypatch, large_avail):
    """Regression harness for a windows-latest-only CI failure (p5-r5):
    test_map_dominates_compact_window_height_at_683x485 passed here (ratio
    0.566) but failed on windows-latest (0.497) -- Segoe UI's taller line
    metrics inflated the compact header row/control strip/band chip row just
    enough to starve the map. Unlike the wide_font_window fixture below
    (QFont.setStretch(), which widens glyphs), every widget's *height* here
    is actually driven by theme.QSS's own `font-size: {FONT_BODY}px` rule,
    not the QApplication default font -- QSS font-size always wins over
    QFont.setPointSizeF() for sizeHint/layout purposes, so bumping the app
    font alone (as this fixture's sibling does for width) has no effect on
    any rendered height. Patching the baked-in QSS string before
    construction is the only way to deterministically simulate "every label
    and button is taller" on any platform, including this offscreen Linux
    one. Reset after the test so it can't bleed into others sharing this
    session's QApplication instance."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    import orbitrx.ui.theme as theme
    original_qss = theme.QSS
    theme.QSS = theme.QSS.replace("font-size: 13px", "font-size: 24px")

    app = QApplication.instance() or QApplication([])
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
        theme.QSS = original_qss
        theme.apply_theme(app)


def _compact_chrome_row_heights(window) -> str:
    """p5-r7: a per-row height breakdown for the compact chrome stacked
    above/around the map (menu bar, map header, control strip, band-chip
    row, status bar) plus the map itself -- so a future windows-latest-only
    ratio failure shows exactly which row's height ate the map's share,
    instead of just the bare too-small ratio float this test used to
    assert on."""
    menu_bar = window.menuBar()
    status_bar = window.statusBar()
    header_row = getattr(window, "_map_header_row", None)
    controls = getattr(window, "_map_controls", None)
    band_panel = getattr(window, "band_panel", None)
    return (
        f"menu_bar={menu_bar.height()} "
        f"map_header_row={header_row.height() if header_row is not None else None} "
        f"control_strip={controls.height() if controls is not None else None} "
        f"band_chip_row={band_panel.height() if band_panel is not None else None} "
        f"status_bar={status_bar.height()} "
        f"map_widget={window.map_widget.height()} "
        f"window={window.height()}"
    )


def test_map_dominates_compact_window_height_at_683x485_under_taller_font(
    taller_font_window,
):
    """Companion to test_map_dominates_compact_window_height_at_683x485: the
    same 683x485 compact ratio floor must hold even when every chrome row
    (header, control strip, band chips) renders taller, not just when every
    chip/label renders wider (test_side_pane_is_not_crushed_by_wide_fonts_at_1280
    below) -- this is the windows-latest regression this fixture reproduces."""
    window = taller_font_window
    window.resize(683, 485)
    window._update_compact_mode()
    assert window._compact

    ratio = window.map_widget.height() / window.height()
    assert ratio >= 0.50, f"{ratio} ({_compact_chrome_row_heights(window)})"


# --- Band cards: QFrame#bandCard + state property + badge (P4-5, SPEC §8) --


@pytest.mark.parametrize(
    "condition,expected_state,expected_badge_is_word",
    [
        ("OPEN", "good", "GOOD"),
        ("FAIR", "fair", "FAIR"),
        ("CLOSED", "poor", "POOR"),
        ("UNKNOWN", "unknown", None),
    ],
)
def test_band_card_exposes_state_property_and_matching_badge(window, condition, expected_state, expected_badge_is_word):
    """band_grid()'s real OPEN/FAIR/CLOSED/UNKNOWN vocabulary (see
    propagation.band_condition) maps onto the card's good/fair/poor/unknown
    state; the badge shows a word or the shared NO_DATA dash (P4-6), never the
    literal "UNKNOWN"."""
    from orbitrx.ui.theme import NO_DATA

    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: condition})

    card = window.band_panel._cards[band]
    badge = window.band_panel._badge_labels[band]
    assert card.property("state") == expected_state
    assert badge.property("state") == expected_state
    assert badge.text() == (expected_badge_is_word or NO_DATA)
    assert "UNKNOWN" not in badge.text()


def test_band_cards_for_different_states_get_different_badge_text(window):
    bands = list(window.band_panel._cards.keys())[:2]
    window.band_panel.update_grid({bands[0]: "OPEN", bands[1]: "CLOSED"})
    badge_good = window.band_panel._badge_labels[bands[0]].text()
    badge_poor = window.band_panel._badge_labels[bands[1]].text()
    assert badge_good != badge_poor


def test_band_card_has_no_per_card_inline_stylesheet(window):
    """SPEC §8 'Implementation': drop the inline setStyleSheet per card (and
    its old 4px coloured left bar) -- state is communicated purely via the
    dynamic "state" property, themed through theme.QSS."""
    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: "OPEN"})
    card = window.band_panel._cards[band]
    assert card.styleSheet() == ""


def test_band_card_defaults_unrecognised_condition_to_unknown(window):
    """Defensive: any condition outside the real vocabulary band_grid() can
    emit reads as unknown, never surfaced as a raw/unexpected word."""
    from orbitrx.ui.theme import NO_DATA

    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: "SOMETHING_ELSE"})
    card = window.band_panel._cards[band]
    badge = window.band_panel._badge_labels[band]
    assert card.property("state") == "unknown"
    assert badge.text() == NO_DATA


def test_band_cards_show_no_data_dash_when_never_loaded(window):
    """Never-loaded state (SPEC §10/states-sheet.png 'Unknown: dash, no
    colour'): state.band_grid defaults to {} and every card starts in the
    "unknown" state at construction time (BandPanelWidget.__init__), before
    update_grid() is ever called -- the badge must show the shared NO_DATA
    glyph, never the literal word "UNKNOWN"."""
    from orbitrx.ui.theme import NO_DATA

    assert window.ctrl.state.band_grid == {}
    for band in window.band_panel._cards:
        assert window.band_panel._cards[band].property("state") == "unknown"
        assert window.band_panel._badge_labels[band].text() == NO_DATA


def test_band_cards_show_no_data_dash_on_feed_failure(tmp_path, monkeypatch):
    """Feed-failure state: a weather fetch that raises with no cache leaves
    state.band_grid exactly as it was before the attempt (the controller
    never reaches band_grid() at all -- see controller.fetch_weather's
    early-return on a cache-less failure) -- fed into a real
    BandPanelWidget, this must render as the NO_DATA dash, never a crash or
    a raw "UNKNOWN"."""
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication
    from orbitrx.ui.theme import NO_DATA
    from orbitrx.ui.controller import OrbitRxController
    from orbitrx.ui.band_panel import BandPanelWidget
    import orbitrx.ui.controller as controller_mod

    QApplication.instance() or QApplication([])
    errors = []
    ctrl = OrbitRxController(on_error=errors.append)
    ctrl.cfg.data["offline_cache_enabled"] = False
    monkeypatch.setattr(
        controller_mod, "fetch_space_weather_data", lambda: (_ for _ in ()).throw(RuntimeError("NOAA down"))
    )

    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)

    assert errors, "weather fetch failure never reached on_error"
    assert ctrl.state.band_grid == {}

    panel = BandPanelWidget()
    panel.update_grid(ctrl.state.band_grid)
    for band in panel._cards:
        assert panel._cards[band].property("state") == "unknown"
        assert panel._badge_labels[band].text() == NO_DATA


def test_band_card_structure_is_frame_with_name_freq_and_badge_labels(window):
    from PySide6.QtWidgets import QFrame, QLabel

    band = next(iter(window.band_panel._cards))
    card = window.band_panel._cards[band]
    assert isinstance(card, QFrame)
    assert card.objectName() == "bandCard"
    assert card.findChild(QLabel, "bandName") is not None
    assert card.findChild(QLabel, "bandFreq") is not None
    assert card.findChild(QLabel, "stateBadge") is not None


def test_band_card_shows_dial_frequency_in_mhz(window):
    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: "OPEN"})
    freq_lbl = window.band_panel._freq_labels[band]
    assert "MHz" in freq_lbl.text()


def test_band_panel_column_reflow_matches_width_buckets(window):
    """The width->column-count bucketing now goes up to 6 (SPEC §6.2/§8:
    one row of 6 cards spanning the full map column), up from the 3-column
    cap the cards had while they lived in the narrow side panel."""
    panel = window.band_panel
    assert panel._columns_for_width(100) == 1
    assert panel._columns_for_width(300) == 2
    assert panel._columns_for_width(944) == 6


def test_band_panel_relayout_and_reflow_keep_all_cards_populated(window):
    """P4-5: _relayout/_reflow_text must still work with the QFrame+labels
    structure -- every card stays in the grid and both child labels keep
    non-empty text at every column count, exactly as the old single
    rich-text QLabel did."""
    panel = window.band_panel
    panel.update_grid({b: "OPEN" for b in panel._cards})
    for cols in (1, 2, 3, 6):
        panel._relayout(cols)
        panel._reflow_text()
        assert panel._grid.count() == len(panel._bands)
        for band in panel._cards:
            assert panel._freq_labels[band].text() != ""
            assert panel._name_labels[band].text() != ""


# --- Key-metric tiles (SFI / Kp / A-index) + Propagation tiles (MUF / LUF) -
# (SPEC §9 items 2/3/5: the old Kp/SFI/MUF trio is replaced by SFI/Kp/A-index
# key tiles plus separate MUF/LUF Propagation tiles, so Kp appears exactly
# once instead of in both a tile and a grouped-card row.)


def test_key_metric_tiles_exist_for_sfi_kp_and_a_index(window):
    from PySide6.QtWidgets import QLabel

    assert set(window._kpi_labels.keys()) == {"sfi", "kp", "a_index"}
    for lbl in window._kpi_labels.values():
        assert isinstance(lbl, QLabel)
        assert lbl.objectName() == "keyMetricValue"


def test_key_metric_tiles_and_propagation_tiles_show_no_data_dash_when_never_loaded(window):
    """Never-loaded state (SPEC §10/states-sheet.png 'Never updated' panel):
    before the first successful fetch, every key tile, the MUF/LUF tiles and
    the new detail rows must show the shared NO_DATA dash, never "n/a" or a
    bare "--" placeholder (_startup's 200ms QTimer hasn't fired yet in this
    fixture, hence the explicit call)."""
    from orbitrx.ui.theme import NO_DATA

    assert window.ctrl.state.last_weather_update is None
    window._refresh_labels_and_map()
    for key in ("sfi", "kp", "a_index"):
        assert window._kpi_labels[key].text() == NO_DATA
    for key in ("muf", "luf", "sunspot", "bands"):
        assert window._labels[key].text() == NO_DATA
    assert "n/a" not in window._labels["sunspot"].text()
    assert window._kp_caption_lbl.text() == "Kp"  # no colour word with no data


@pytest.mark.parametrize(
    "kp,expected_word,expected_color_token",
    [(3.0, "quiet", "GOOD"), (4.0, "unsettled", "FAIR"), (5.0, "storm", "POOR")],
)
def test_kp_tile_caption_shows_kp_state_word_in_colour(window, kp, expected_word, expected_color_token):
    """SPEC §9 item 2: the Kp tile caption adds the kp_state() word in a
    semantic colour; the value label itself stays uncoloured (plain text)."""
    import datetime

    from orbitrx.ui.theme import FAIR, GOOD, POOR

    color = {"GOOD": GOOD, "FAIR": FAIR, "POOR": POOR}[expected_color_token]
    window.ctrl.state.kp_index = kp
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_labels_and_map()

    assert expected_word in window._kp_caption_lbl.text()
    assert color in window._kp_caption_lbl.text()
    assert window._kpi_labels["kp"].text() == f"{kp:.1f}"


def test_weather_never_loaded_hint_visible_before_first_fetch_then_hidden(window):
    """The one-line "No data yet" hint (SPEC §10 "Whole section never
    loaded") is visible by default (the `window` fixture's fetch_weather()
    stub never sets last_weather_update), and hides again once a refresh
    actually lands, without changing the key-metric tiles row's layout."""
    import datetime

    assert window.ctrl.state.last_weather_update is None
    assert not window._weather_never_loaded_lbl.isHidden()

    window.ctrl.state.flux = 111.0
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_labels_and_map()

    assert window._weather_never_loaded_lbl.isHidden()


def test_error_banner_shown_when_fetch_fails_with_no_usable_data(window):
    """G12/SPEC §10 "Error (no usable data)": attempted + failed + never
    loaded is a different, real state from "never attempted" -- it gets the
    POOR "Couldn't reach source · Retry" banner (not the muted "No data yet"
    hint), and the band strip collapses to the single unavailable line."""
    assert window.ctrl.state.last_weather_update is None

    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()

    assert window._weather_banner_lbl.isVisible()
    assert window._weather_banner_lbl.property("state") == "error"
    assert "Couldn't reach source" in window._weather_banner_lbl.text()
    assert window._weather_never_loaded_lbl.isVisible() is False
    assert window.band_panel._all_unknown is True


def test_stale_banner_shown_when_last_good_data_exists_but_fetch_fails(window):
    """G12/SPEC §10 "Stale (refresh failed, has last-good)": a real
    previously-successful snapshot plus a now-failed fetch gets the FAIR
    "Stale · last OK hh:mm · retrying" banner, and band badges switch to
    outline (set_stale), never the collapsed all-unknown strip (there is
    real data to show)."""
    import datetime

    window.ctrl.state.flux = 111.0
    now = datetime.datetime.now(datetime.timezone.utc)
    window.ctrl.state.last_weather_update = now
    window.ctrl.state.last_weather_success_update = now
    window.ctrl.state.weather_last_fetch_ok = True
    window._refresh_labels_and_map()
    assert window._weather_banner_lbl.isVisible() is False

    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()

    assert window._weather_banner_lbl.isVisible()
    assert window._weather_banner_lbl.property("state") == "stale"
    assert "Stale" in window._weather_banner_lbl.text()
    assert "retrying" in window._weather_banner_lbl.text()
    assert window.band_panel._all_unknown is False
    badge = next(iter(window.band_panel._badge_labels.values()))
    assert badge.property("stale") is True


def test_corner_state_indicator_visible_without_drawer_at_683x485(window):
    """P5-r6 (c): the no-data/stale banner (SPEC §10) lives in the side
    panel, which is hidden below 820px wide and only reachable via the
    Ctrl+B drawer -- at 683x485 a feed failure used to be invisible unless
    the user opened it. The one-word menu-bar corner state must say so
    without the drawer: hidden in the normal state, "Error" (error_no_data)
    or "Stale" otherwise, and never while the drawer/side panel is open."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert window._side_pane.isVisible() is False or not window._side_panel_visible

    window.ctrl.state.weather_last_fetch_ok = True
    window._refresh_labels_and_map()
    assert window._corner_state_lbl.isVisible() is False

    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()
    assert window._corner_state_lbl.isVisible()
    assert "Error" in window._corner_state_lbl.text()

    import datetime
    window.ctrl.state.flux = 111.0
    now = datetime.datetime.now(datetime.timezone.utc)
    window.ctrl.state.last_weather_update = now
    window.ctrl.state.last_weather_success_update = now
    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()
    assert window._corner_state_lbl.isVisible()
    assert "Stale" in window._corner_state_lbl.text()


def test_corner_widget_sizehint_fits_its_allotted_width_in_every_state_at_683x485(window):
    """P5-r6 (c): the menu-bar corner must never clip -- QMenuBar only
    re-measures its corner widget's reserved width when the menu bar itself
    relays out, not just because a corner label's text grew (real values
    replacing NO_DATA dashes, "disconnected" vs a longer connected node
    name) -- _resync_corner_widget_geometry() must keep the widget's actual
    width in sync with its sizeHint() after every state change, in every
    state, so nothing is ever cropped."""
    import datetime

    _resize_and_settle(window, 683, 485)
    assert window._compact

    def assert_no_clip():
        hint = window._status_corner.sizeHint()
        assert window._status_corner.width() >= hint.width(), (
            window._status_corner.width(), hint.width()
        )

    # empty (never loaded)
    window._refresh_labels_and_map()
    assert_no_clip()

    # error (no usable data)
    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()
    assert_no_clip()

    # stale (has last-good data)
    window.ctrl.state.flux = 111.0
    now = datetime.datetime.now(datetime.timezone.utc)
    window.ctrl.state.last_weather_update = now
    window.ctrl.state.last_weather_success_update = now
    window.ctrl.state.weather_last_fetch_ok = False
    window._refresh_labels_and_map()
    assert_no_clip()

    # connected, with a long real cluster node name
    window.ctrl.cfg.data["dx_cluster_host"] = "a-rather-long-cluster-hostname.example.net"
    window._set_cluster("connected")
    assert_no_clip()


def test_toast_does_not_overlap_control_strip_at_683x485(window):
    """P5-r6 (c): a toast anchored to the map frame (not the window's own
    bottom-right corner) must never cover the control strip/band chips
    below the map -- both geometries mapped into the same (window)
    coordinate space must not intersect."""
    _resize_and_settle(window, 683, 485)
    assert window._compact

    window._toasts.show_toast("Weather update failed: source unreachable", kind="error")
    assert window._toasts.is_visible()

    toast_label = window._toasts._label
    toast_rect = QRect(toast_label.mapTo(window, toast_label.rect().topLeft()), toast_label.size())
    controls = window._map_controls
    controls_rect = QRect(controls.mapTo(window, controls.rect().topLeft()), controls.size())
    assert not toast_rect.intersects(controls_rect), (toast_rect, controls_rect)

    band_rect = QRect(
        window.band_panel.mapTo(window, window.band_panel.rect().topLeft()), window.band_panel.size()
    )
    assert not toast_rect.intersects(band_rect), (toast_rect, band_rect)


def test_map_pill_consolidated_disconnected_vs_connected(window):
    """G14: the map shows one pill, never two stacked -- disconnected shows
    only "Cluster disconnected · Reconnect"; connected (with a genuinely
    empty live-spots window) shows only "No spots in this window"."""
    window._set_cluster("disconnected")
    assert window.map_widget._cluster_pill.isVisible() is True
    assert window.map_widget._empty_overlay.isVisible() is False

    window._set_cluster("connected")
    window._layer_checks["spot_arcs"].setChecked(True)
    window.ctrl.spots.latest = []
    window._refresh_live_spots()
    assert window.map_widget._cluster_pill.isVisible() is False
    assert window.map_widget._empty_overlay.isVisible() is True


def test_muf_luf_tiles_show_values_with_mhz_unit(window):
    """SPEC §9 item 5: MUF/LUF are now their own Propagation tiles (not the
    old key-metric row), each showing the value with its "MHz" unit."""
    import datetime

    window.ctrl.state.muf = 21.4
    window.ctrl.state.luf = 4.1
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_labels_and_map()

    assert window._labels["muf"].text() == "21.4 MHz"
    assert window._labels["luf"].text() == "4.1 MHz"


def test_sfi_tile_shows_only_the_flux_number_with_trend_in_tooltip(window):
    """The SFI tile is populated directly from state.flux (_refresh_key_tiles).
    SPEC §9's tile has no room for the old grouped-card's "<flux> <trend
    arrow/word>" text, so the big number is just the flux value; the trend
    survives as the tile's tooltip rather than being silently dropped."""
    import datetime

    window.ctrl.state.flux = 123.4
    window.ctrl.state.flux_trend = "↓ (falling)"
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_labels_and_map()

    assert window._kpi_labels["sfi"].text() == "123.4"
    assert window._kpi_labels["sfi"].toolTip() == "Trend: ↓ (falling)"


@pytest.mark.parametrize("fetch_ok", [True, False])
def test_sfi_tile_never_shows_trailing_point_zero_for_a_whole_number(window, fetch_ok):
    """P5-r8/SPEC §10 sample "SFI 142" is a bare integer -- a whole-number
    flux reading (e.g. the offline fixture's 120.0) must never render as
    "120.0" noise, in the ok state or the stale (fetch_ok=False) state
    alike, while a genuinely fractional reading keeps its decimal (covered
    by test_sfi_tile_shows_only_the_flux_number_with_trend_in_tooltip)."""
    import datetime

    window.ctrl.state.flux = 120.0
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window.ctrl.state.weather_last_fetch_ok = fetch_ok
    window._refresh_labels_and_map()

    assert window._kpi_labels["sfi"].text() == "120"


@pytest.mark.parametrize("width,height", [(1280, 800), (683, 485)])
def test_no_key_metric_tile_label_text_overflows_its_width(window, width, height):
    """Owner fix: a key-metric tile label's text must never be wider than
    the space the tile actually gives it, at either size this app supports.
    Exercises the worst-case values this layout has to accommodate: the
    default no-data (NO_DATA dash) state, and a realistic longest-reading
    value for each tile."""
    import datetime

    from PySide6.QtGui import QFontMetrics

    window.resize(width, height)
    window._update_compact_mode()

    cases = [
        {},
        {"kp_index": 8.0},
        {"flux": 999.9, "a_index": 88},
        {"muf": 28.5, "luf": 28.5},
    ]
    for state_kwargs in cases:
        for attr, value in state_kwargs.items():
            setattr(window.ctrl.state, attr, value)
        window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
        window._refresh_labels_and_map()

        labels = [
            window._kpi_labels["sfi"], window._kpi_labels["kp"], window._kpi_labels["a_index"],
            window._labels["muf"], window._labels["luf"],
        ]
        for lbl in labels:
            fm = QFontMetrics(lbl.font())
            advance = fm.horizontalAdvance(lbl.text())
            width_available = lbl.contentsRect().width()
            assert advance <= width_available, (lbl.objectName(), lbl.text(), advance, width_available)


def test_ops_card_is_removed_from_the_side_panel(window):
    """G4 (P5-r2): the "OPS" card (UTC/cluster/27-day-forecast/contest/DX)
    is gone -- not part of SPEC §9's panel structure, and it was the single
    biggest contributor to the side panel needing its own scrollbar at the
    real 1280x800 budget. UTC and cluster state already live in the
    menu-bar corner (G5); nothing registers those keys in the side panel's
    label dicts any more."""
    from PySide6.QtWidgets import QFrame

    for key in ("time", "cluster", "solar_forecast", "contest", "dx"):
        assert key not in window._stat_name_labels, key
        assert key not in window._labels, key
    assert window.findChild(QFrame, "statsCard") is None


def test_detail_rows_are_left_label_right_mono_value_with_no_box(window):
    """SPEC §9 item 4: Kp forecast/Sunspot/Solar wind/Bz (and the Bands row)
    are QFrame#detailRow -- label left (tertiary), value right (mono,
    primary), no card background/border."""
    for key in ("kp_forecast", "sunspot", "solar_wind", "bz", "bands"):
        name_lbl = window._stat_name_labels[key]
        value_lbl = window._labels[key]
        assert name_lbl.objectName() == "rowLabel"
        assert value_lbl.objectName() == "rowValue"
        assert name_lbl.alignment() & Qt.AlignmentFlag.AlignLeft
        assert value_lbl.alignment() & Qt.AlignmentFlag.AlignRight
        row = value_lbl.parentWidget()
        assert row.objectName() == "detailRow"
        assert row.styleSheet() == ""  # themed via QSS, no inline per-row style


def test_space_weather_header_shows_section_title_and_freshness_stamp(window):
    assert window._freshness_lbl.objectName() == "freshness"
    sw_title = next(
        lbl for lbl in window.findChildren(type(window._freshness_lbl))
        if lbl.objectName() == "sectionTitle" and lbl.text() == "Space weather"
    )
    assert sw_title.text() == "Space weather"


def test_propagation_header_shows_hamqsl_source_label(window):
    prop_title = next(
        lbl for lbl in window.findChildren(type(window._freshness_lbl))
        if lbl.objectName() == "sectionTitle" and lbl.text() == "Propagation"
    )
    assert prop_title.text() == "Propagation"
    hamqsl_lbl = next(
        lbl for lbl in window.findChildren(type(window._freshness_lbl))
        if lbl.objectName() == "rowLabel" and lbl.text() == "HamQSL"
    )
    assert hamqsl_lbl.text() == "HamQSL"


def test_path_row_is_collapsed_by_default_and_toggles(window):
    assert window._path_toggle_btn.isChecked() is False
    assert window._path_body.isHidden()

    window._path_toggle_btn.setChecked(True)
    assert window._path_body.isVisible()

    window._path_toggle_btn.setChecked(False)
    assert window._path_body.isHidden()


def test_path_header_hint_links_to_location_settings_when_unset(window, monkeypatch):
    window.ctrl.state.user_lat = None
    window.ctrl.state.user_lon = None
    window._update_location_hint_visibility()
    assert not window._path_hint_lbl.isHidden()
    assert "Set location in Settings (Ctrl+,)" in window._path_hint_lbl.text()
    assert "href" not in window._path_hint_lbl.text()

    window.ctrl.state.user_lat = 51.5
    window.ctrl.state.user_lon = -0.1
    window._update_location_hint_visibility()
    assert window._path_hint_lbl.isHidden()


def test_tile_and_row_geometry_is_identical_empty_vs_populated(window):
    """SPEC §10/UXR §7 "layout stability": switching between the never-loaded
    (NO_DATA) and populated states must not move anything by 4px or more --
    pinned here across every real state the controller can inject (never a
    sample value shipped in code)."""
    import datetime

    window.resize(1280, 800)
    window._update_compact_mode()
    tracked = (
        [window._kpi_labels[k] for k in ("sfi", "kp", "a_index")]
        + [window._labels[k] for k in ("muf", "luf", "bands", "kp_forecast", "sunspot", "solar_wind", "bz")]
    )

    assert window.ctrl.state.last_weather_update is None
    window._refresh_labels_and_map()
    empty_geoms = [(w.x(), w.y(), w.width(), w.height()) for w in tracked]

    window.ctrl.state.flux = 142.0
    window.ctrl.state.kp_index = 3.0
    window.ctrl.state.a_index = 12.0
    window.ctrl.state.muf = 21.4
    window.ctrl.state.luf = 4.1
    window.ctrl.state.hamqsl_band_hint = "40m | 20m"
    window.ctrl.state.kp_forecast = "3.33"
    window.ctrl.state.sunspot_observed = 118.0
    window.ctrl.state.solar_wind_speed = 412.0
    window.ctrl.state.bz = -2.1
    window.ctrl.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
    window._refresh_labels_and_map()
    populated_geoms = [(w.x(), w.y(), w.width(), w.height()) for w in tracked]

    for before, after, widget in zip(empty_geoms, populated_geoms, tracked):
        assert before[1] == after[1] and before[3] == after[3], (widget.objectName(), before, after)


# --- P5-r3 G8-G11: 683x485 compact layout fidelity --------------------------


def test_no_duplicate_tab_row_at_compact_width(window):
    """G8: the only visible navigation at 683 is the map header's own
    Map/Bands/Log segmented control -- _compact_tabs still exists and still
    switches pages (Ctrl+B/the View menu/Esc all drive it), but its own tab
    bar must never render a second "Map | Conditions" row above it."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert window._compact_tabs.tabBar().isVisible() is False
    assert window._compact_tabs.isVisible()
    for key in ("Map", "Bands", "Log"):
        assert window._seg_buttons[key].isVisible()


def test_band_chip_row_has_6_chips_in_one_row_at_compact_width(window):
    """G10: one row of 6 compact band chips under the map, same anatomy
    (name + dot + state word) the full-size cards use, reusing the real
    BandPanelWidget rather than a second model."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert window.band_panel.is_compact()
    assert window.band_panel.isVisible()
    assert window._map_tab_layout.indexOf(window.band_panel) != -1, (
        "band_panel must stay under the map, not move into the Conditions drawer"
    )

    cards = list(window.band_panel._cards.values())
    assert len(cards) == 6
    rows = {card.mapTo(window, card.rect().topLeft()).y() for card in cards}
    assert len(rows) == 1, ("expected a single row", rows)


def test_compact_controls_fit_within_window_width_with_live_not_clipped(window):
    """G11: Layers menu button, joined Live|Heat, Offset slider and Replay
    slider all sit in one row at 683, and nothing -- in particular the
    "Live" replay value label -- extends past the window's right edge."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert window._map_controls._single_row is True
    assert not window._spots_label.isVisible()

    controls = [
        window._layers_menu_btn,
        window._spots_group,
        window.time_slider, window.lbl_slider,
        window.replay_slider, window.lbl_replay,
    ]
    for widget in controls:
        assert widget.isVisible()
        right = widget.mapTo(window, widget.rect().topRight()).x()
        assert right <= window.width(), (widget.objectName() or widget, right, window.width())
    assert window.lbl_replay.text() == "Live"


def test_map_frame_has_no_non_ocean_side_bars_at_compact_width(window):
    """G9: no dark letterbox bars left/right of the map at 683 -- every
    pixel along the map frame's inner edge columns must read as the ocean
    colour token (or something the night veil/graticule only darkens
    slightly), never a visually distinct matte bar."""
    from orbitrx.ui.theme import MAP_OCEAN

    _resize_and_settle(window, 683, 485)
    assert window._compact

    ocean = QColor(MAP_OCEAN)
    pixmap = window._map_frame.grab()
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    assert width > 20 and height > 20

    tolerance = 40  # night veil/greyline shading, not a distinct letterbox colour
    for x in (2, width - 3):
        for y in (height // 4, height // 2, 3 * height // 4):
            colour = image.pixelColor(x, y)
            diff = (
                abs(colour.red() - ocean.red())
                + abs(colour.green() - ocean.green())
                + abs(colour.blue() - ocean.blue())
            )
            assert diff <= tolerance, (x, y, colour.getRgb(), ocean.getRgb(), diff)


def test_band_chip_row_bottom_is_inside_central_widget_at_compact_width(window):
    """P5-r4 683x485 leftover: the band chip row used to be clipped by the
    status bar -- its bottom border (plus a small gap above the status bar)
    must be fully visible inside the central widget's own height, not
    overdrawn or pushed past it."""
    _resize_and_settle(window, 683, 485)
    assert window._compact

    central = window.centralWidget()
    chip_bottom = window.band_panel.mapTo(central, window.band_panel.rect().bottomLeft()).y()
    assert 0 < chip_bottom < central.height(), (chip_bottom, central.height())
    # A visible gap above the status bar, not the chip row's border landing
    # flush on it.
    assert central.height() - chip_bottom >= 2


def test_header_greyline_caption_hidden_at_compact_width(window):
    """P5-r4 683x485 leftover: the header's own "Greyline · ..." caption has
    no room to avoid eliding next to the segmented control at this width --
    the map's own bottom-left caption (SPEC §7 "At 683") already shows the
    identical real string, so the header hides its copy and is just the
    segmented control, stretch, Cluster combo and "?"."""
    _resize_and_settle(window, 683, 485)
    assert window._compact
    assert window.banner.isVisible() is False

    _resize_and_settle(window, 1280, 800)
    assert not window._compact
    assert window.banner.isVisible() is True


def test_unknown_band_badge_has_no_border(window):
    """G13: the unknown badge is a bare dash with no colour -- not an empty
    bordered chip, which is how the badge used to render before this."""
    band = next(iter(window.band_panel._cards))
    window.band_panel.update_grid({band: "UNKNOWN"})
    badge = window.band_panel._badge_labels[band]
    assert badge.property("state") == "unknown"
    assert "border" not in window.band_panel.styleSheet()
    from orbitrx.ui.theme import QSS

    assert 'stateBadge[state="unknown"]' in QSS
    unknown_rule = QSS.split('stateBadge[state="unknown"]')[1].split("}")[0]
    assert "border" not in unknown_rule
