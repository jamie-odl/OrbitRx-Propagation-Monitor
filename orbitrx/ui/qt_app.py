from __future__ import annotations

import datetime
import faulthandler
import gc
import json
import os
import sys
import threading
import time
from pathlib import Path

from PIL import Image

from orbitrx import __version__
from orbitrx.dx import verify_qrz_api
from orbitrx.map_renderer import MapLayers, MapRenderer
from orbitrx.propagation import HF_BANDS, kp_state
from orbitrx.ui.async_utils import CatTestRunner
from orbitrx.ui.band_panel import BandPanelWidget
from orbitrx.ui.controller import OrbitRxController
from orbitrx.ui.dpi import set_high_dpi_rounding_policy
from orbitrx.ui.map_widget import PropagationMapWidget, QT_AVAILABLE, _pil_to_qimage
from orbitrx.spots.settings import clamp_poll_seconds
from orbitrx.ui.formatting import (
    widen_to_min_span,
    humanize_iso_dates, fmt, format_value,
    format_hour_offset, format_no_spots_message, format_replay_offset,
    history_plot_date_format, insert_gap_breaks, pad_datetime_range, EXPECTED_POLL_S,
)
from orbitrx.ui.rig_wizard import RigWizardDialog, populate_port_combo
from orbitrx.ui.theme import (
    BAND_CHIP_HEIGHT_COMPACT, BG_ELEVATED, BORDER, CARD_STYLE, CARD_TEXT, CONTROL_HEIGHT,
    CONTROL_HEIGHT_COMPACT, ERR, FAIR, FONT_BODY, FONT_MONO, GOOD, GUTTER_COMPACT, GUTTER_WIDE,
    MAP_HEADER_HEIGHT, MAP_HEADER_HEIGHT_COMPACT, MENU_BAR_HEIGHT, MENU_BAR_HEIGHT_COMPACT, MUTED,
    MUTED_SECONDARY, NO_DATA, OK, POOR, RADIUS_M, SLIDER_VALUE_MIN_WIDTH, SLIDER_WIDTH,
    SLIDER_WIDTH_COMPACT, SPACE_1, SPACE_2, SPACE_3, STATUS_BAR_HEIGHT, STATUS_BAR_HEIGHT_COMPACT,
    TEXT_SECONDARY, TEXT_TERTIARY, UNKNOWN, apply_theme,
)
from orbitrx.ui.toast import ToastManager
from orbitrx.ui.window_fit import fit_to_screen
from orbitrx.update_checker import check_github_release

if not QT_AVAILABLE:
    raise ImportError("PySide6 is required for the Qt UI")

from PySide6.QtCore import QDate, QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QSizePolicy,
    QGridLayout,
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QSplitter, QStackedWidget, QTabWidget, QToolButton, QVBoxLayout, QWidget, QFileDialog,
    QSystemTrayIcon, QMenu, QWidgetAction,
)

PLOT_QT = False
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.dates import AutoDateLocator, DateFormatter, DayLocator
    from matplotlib.figure import Figure
    PLOT_QT = True
except ImportError:
    FigureCanvas = None

CONTINENT_OPTS = [("NA", "North America"), ("SA", "South America"), ("EU", "Europe"),
                  ("AF", "Africa"), ("AS", "Asia"), ("OC", "Oceania")]

# Shared label column width for every Settings page, so the field column starts at the
# same x regardless of which page's labels happen to be widest (N-new-3).
SETTINGS_LABEL_WIDTH = 170

# S1: fields keep at least this width instead of being squeezed unreadably thin;
# below it the row wraps (the label moves above the field) rather than clipping.
SETTINGS_FIELD_MIN_WIDTH = 160

# S1: below this page width (dialog width minus the nav list), every form row
# wraps (label above field) instead of just the long ones.
SETTINGS_NARROW_PAGE_WIDTH = 560
SETTINGS_NAV_WIDTH_WIDE = 180
SETTINGS_NAV_WIDTH_NARROW = 150

# S4: a one-line description at the top of every Settings page, so a page with only
# one or two controls still reads as a deliberate, populated screen.
SETTINGS_PAGE_DESCRIPTIONS = {
    "Station": "Your callsign and home coordinates, used to centre the map and tag your spots.",
    "Rig": "Connect to your radio over CAT so clicking a spot on the map can tune it for you.",
    "DX cluster": "Pick a cluster node and filter which DX spots show up on the map.",
    "Map & spots": "How often live spots refresh from PSKReporter, and which mode they show.",
    "Services": "Optional QRZ lookups and how often space weather data refreshes.",
}

# M1: below this main-window width, the map and side panel move from a side-by-side
# splitter into a "Map" / "Conditions" tab pair; above the (higher) exit width, they
# move back. The gap between the two is hysteresis, so a resize that lands right on
# the boundary doesn't flip back and forth.
COMPACT_WIDTH_BELOW = 900
COMPACT_WIDTH_ABOVE = 940

# Default Test CAT timeout; a module attribute (not a literal in do_test_cat) so
# tests can monkeypatch it to run a slow-serial-stub scenario quickly.
CAT_TEST_TIMEOUT_S = 5.0

# P2B: status bar wording for AppState.location_source.
LOCATION_SOURCE_LABELS = {"manual": "manual", "geolocated": "geolocated", "unset": "not set"}


def _build_history_figure(rows: list[dict], poll_interval_s: float) -> tuple[Figure, bool]:
    """Builds the matplotlib Figure for the history plot. matplotlib (incl. its
    FreeType font cache used by tight_layout) is not thread-safe, so this
    always runs on the UI thread -- _refresh_plot_tab only runs the sqlite
    query on a worker thread; this is called back on the UI thread with the
    query result. Returns (figure, has_enough_data); the caller wraps the
    figure in a FigureCanvasQTAgg and adds it to the layout."""
    times, kp, flux = [], [], []
    for r in rows:
        times.append(datetime.datetime.fromisoformat(r["ts"]))
        kp.append(float(r.get("kp") or 0))
        flux.append(float(r.get("flux") or 0))

    fig = Figure(figsize=(5, 3.5), facecolor="#0B1220")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#0B1220")
    ax.tick_params(colors="#CDDDFE")
    for spine in ax.spines.values():
        spine.set_color("#37474F")

    if len(times) < 2 or (max(times) - min(times)).total_seconds() < 60:
        # S2: fewer than two readings at least a minute apart have no meaningful line to plot.
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(
            0.5, 0.5, "Not enough data yet", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontsize=13,
        )
        fig.tight_layout()
        return fig, False

    # S2: pad the data range by 10% total (5% each side) so points never sit
    # flush against an axis edge, with a minimum 1 h span centred on the data
    # so a tight cluster of points still occupies most of the plot width
    # instead of a sliver.
    lo, hi = pad_datetime_range(min(times), max(times))
    lo, hi = widen_to_min_span(lo, hi)
    span_h = (hi - lo).total_seconds() / 3600.0
    if span_h < 36:
        locator = AutoDateLocator(maxticks=6)
    else:
        # "dd MMM" daily ticks: one tick per day (or fewer) so they never overlap.
        locator = DayLocator(interval=max(1, round(span_h / 24 / 3)))
    ax.xaxis.set_major_locator(locator)
    # M4/S3: HH:mm within a day, "dd MMM HH:mm" up to 36 h, then date-only "dd MMM"
    # daily ticks so labels never repeat "00:00".
    ax.xaxis.set_major_formatter(DateFormatter(history_plot_date_format(lo, hi)))
    ax.set_xlim(lo, hi)

    # M4: break the line (insert a NaN) only across a gap bigger than a real
    # outage would allow -- max(3x the app's expected poll interval, 30 min) --
    # instead of the old median-relative rule, which broke real, jittery data
    # into isolated points. Isolated points still show via a size-7 marker.
    kp_times, kp_gapped = insert_gap_breaks(times, kp, poll_interval_s)
    flux_times, flux_gapped = insert_gap_breaks(times, flux, poll_interval_s)

    kp_line, = ax.plot(
        kp_times, kp_gapped, label="Kp", marker="o", markersize=7, linestyle="-", color="#64B5F6"
    )
    ax.set_ylabel("Kp", color="#64B5F6")
    ax.set_ylim(0, 9)
    ax.yaxis.set_ticks(range(0, 10))

    ax2 = ax.twinx()
    sfi_line, = ax2.plot(
        flux_times, flux_gapped, label="SFI", marker="o", markersize=7, linestyle="-", color="#FFD54F"
    )
    ax2.set_ylabel("SFI", color="#FFD54F")
    ax2.set_ylim(50, 300)
    for spine in ax2.spines.values():
        spine.set_color("#37474F")
    ax2.tick_params(colors="#CDDDFE")

    legend = ax.legend(
        [kp_line, sfi_line], ["Kp", "SFI"],
        loc="upper left", fontsize=8, facecolor="#16212C", edgecolor="#37474F",
    )
    for text in legend.get_texts():
        text.set_color("#E3EAF2")
    fig.tight_layout()
    return fig, True


class _ReflowGrid(QWidget):
    """A row of widgets (layer toggles, continent checkboxes) that reflows into
    fewer columns as it narrows, so it is always reachable by vertical scroll
    alone and never needs a horizontal scrollbar (M1)."""

    def __init__(
        self, widgets: list[QWidget], min_item_width: int, parent=None,
        min_cols: int = 1, max_cols: int | None = None, spacing: int = 6,
        on_relayout=None,
    ) -> None:
        super().__init__(parent)
        self._widgets = widgets
        self._min_cols = max(1, min_cols)
        self._max_cols = max_cols or (len(widgets) or 1)
        # Round 6: an optional callback fired after every _relayout() (both
        # the initial one and any resize-triggered one), so a caller that
        # needs to react to the *current* row/column arrangement -- e.g.
        # _JoinedToggleGroup re-deriving which button is first/last in its
        # row for the QSS pos="first|mid|last" joined look -- doesn't have
        # to duplicate _columns_for_width's own wrapping math.
        self._on_relayout = on_relayout
        # W1: size columns off each widget's real sizeHint, not a fixed guess -
        # native styles (e.g. Windows' chip padding) render noticeably wider
        # than Linux's, and a fixed width let a too-wide column overflow the
        # window on Windows while fitting fine on Ubuntu.
        # Round 8: max() with minimumSizeHint() too -- on windows-latest CI a
        # QToolButton's minimumSizeHint() has come back a few px wider than
        # its own sizeHint() under bulkier Segoe UI metrics, so sizeHint()
        # alone under-reserved a column and QGridLayout then had to squeeze
        # that button below its real minimum to fit the chosen column count.
        self._min_item_width = max(
            [max(1, min_item_width)]
            + [max(w.sizeHint().width(), w.minimumSizeHint().width()) for w in widgets]
        )
        self._grid = QGridLayout(self)
        self._grid.setSpacing(spacing)
        self._grid.setContentsMargins(0, 0, 0, 0)
        # Qt's default SizeConstraint auto-floors a *top-level* widget's
        # resize() at its layout's current minimum -- irrelevant in the real
        # app (this is always embedded in a parent layout, which governs its
        # size instead), but it defeats a standalone top-level usage (e.g. a
        # test) ever actually narrowing below whatever column-width floor the
        # previous _relayout() happened to pin.
        self._grid.setSizeConstraint(QGridLayout.SizeConstraint.SetNoConstraint)
        self._cols = 0
        self._prefer_full_row = False
        self._relayout(self._columns_for_width(len(widgets) * self._min_item_width))

    def _row_major_col_mins(self, cols: int) -> list[int]:
        """Each column's real minimum width for a row-major (divmod(i, cols))
        placement -- the same assignment _relayout() uses -- rather than
        assuming every column is as wide as the single widest item. Toggle
        groups like Layers (Greyline/Night/DX/Aurora/Grid) hold items of very
        different label lengths, so that uniform assumption reserved far more
        width than a real row actually needs and under-packed columns."""
        mins = [0] * cols
        for i, w in enumerate(self._widgets):
            col = i % cols
            mins[col] = max(mins[col], w.sizeHint().width(), w.minimumSizeHint().width())
        return mins

    def _columns_for_width(self, width: int) -> int:
        n = len(self._widgets) or 1
        spacing = self._grid.spacing()
        upper = max(self._min_cols, min(self._max_cols, n))
        cols = self._min_cols
        for candidate in range(upper, self._min_cols - 1, -1):
            mins = self._row_major_col_mins(candidate)
            total = sum(mins) + spacing * (candidate - 1)
            if total <= width:
                cols = candidate
                break
        # V12 tune 2: avoid an orphan last-row chip (e.g. Heatmap alone under Greyline).
        if cols < n:
            while cols > self._min_cols:
                rem = n % cols
                if rem == 0 or rem >= (cols + 1) // 2:
                    break
                cols -= 1
        return cols

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cols = self._columns_for_width(self.width())
        if cols != self._cols:
            self._relayout(cols)

    def natural_width(self) -> int:
        """Width needed to show every item in a single row -- the real sum of
        each item's own width, not every item reserving the widest one's
        width (see _row_major_col_mins), so a request for "everyone on one
        row" doesn't overshoot what the row actually needs and get squeezed
        by a sibling layout below that real need."""
        if not self._widgets:
            return self._min_item_width
        widths = [max(w.sizeHint().width(), w.minimumSizeHint().width()) for w in self._widgets]
        return sum(widths) + (len(widths) - 1) * self._grid.spacing()

    def set_prefer_full_row(self, enabled: bool) -> None:
        """Tell sizeHint() to always ask for natural_width() (every item on
        one row) regardless of this grid's *actual* current column count --
        a sibling (_MapControlStrip) that wants to *try* a single-row display
        calls this instead of relying on this grid's plain sizeHint(), which
        otherwise reflects whatever column count a previous, narrower width
        last settled it into: a stretch-0 QHBoxLayout slot sized off that
        stale, narrow sizeHint would hand this grid too little width to ever
        recover -- a self-reinforcing single-column layout even once real
        room is available. The actual rendered column count still comes from
        resizeEvent()/_columns_for_width() once real geometry is assigned, so
        asking big here never forces anything to render below its own
        per-item minimum -- see minimumSizeHint()."""
        if self._prefer_full_row != enabled:
            self._prefer_full_row = enabled
            self.updateGeometry()

    def sizeHint(self):
        if self._prefer_full_row:
            from PySide6.QtCore import QSize

            return QSize(self.natural_width(), super().sizeHint().height())
        return super().sizeHint()

    def minimumSizeHint(self):
        """Width/height for as few columns as this grid is allowed
        (self._min_cols) -- independent of self._cols (the column count
        actually being rendered right now, which set_prefer_full_row() above
        can push as high as every item in one row). Reporting that live,
        possibly-maximal _cols arrangement as this grid's *minimum* would
        force an ancestor layout (here: the map column vs. the side panel)
        to always reserve this grid's full single-row width even when a
        squeeze (e.g. unusually wide Windows fonts) leaves less room than
        that -- this floor is low enough that the grid can still wrap onto
        many more rows instead. Round 6: honours self._min_cols exactly
        (previously floored at 2 regardless of a caller's own min_cols=1) --
        _JoinedToggleGroup's Layers/Spots groups need that true 1-column
        floor, since two of these grids now sit side by side instead of one
        flat 7-chip row, and a floor of 2 columns *each* summed to a bigger
        total minimum than the old single grid's floor ever did."""
        from PySide6.QtCore import QSize

        n = len(self._widgets) or 1
        cols = max(1, min(n, self._min_cols))
        spacing = self._grid.spacing()
        row_height = max([w.sizeHint().height() for w in self._widgets], default=0)
        width = cols * self._min_item_width + (cols - 1) * spacing
        # Height uses the column count *actually rendered right now*
        # (self._cols), not this same min-cols floor -- Qt always expands
        # sizeHint() to at least minimumSizeHint() in each dimension
        # independently, so a minimumSizeHint() tall enough for the
        # worst-case (1-column, every item stacked) squeeze forced every
        # *current*, wider-and-shorter arrangement's effective height up to
        # that same worst case too, even while comfortably rendering far
        # fewer rows. The width floor still protects the real squeeze case;
        # resizeEvent()/_columns_for_width() still shrinks to min_cols (and
        # this minimum's width) if the ancestor ever actually hands over
        # only that much room.
        current_cols = max(1, min(n, self._cols or n))
        current_rows = -(-n // current_cols)
        height = current_rows * row_height + (current_rows - 1) * spacing
        return QSize(width, height)

    def _relayout(self, cols: int) -> None:
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        col_mins = [0] * cols
        for i, w in enumerate(self._widgets):
            row, col = divmod(i, cols)
            self._grid.addWidget(w, row, col)
            col_mins[col] = max(col_mins[col], w.sizeHint().width(), w.minimumSizeHint().width())
        # Round 9: pin each column's real minimum explicitly -- QGridLayout's
        # own surplus-distribution (used when this grid is handed more than
        # its bare minimumSizeHint, e.g. via set_prefer_full_row()'s single-
        # row request) doesn't always divide that surplus evenly across
        # columns of differing content widths; on windows-latest CI this let
        # a column holding a wider button (e.g. "Greyline") render a few px
        # *below* that button's own minimumSizeHint even though the grid as a
        # whole had enough room. setColumnMinimumWidth() is a hard floor Qt
        # always honours per column, independent of that distribution.
        # Columns are reset up to self._max_cols (not just the current `cols`)
        # because QGridLayout remembers a minimum width set on a column index
        # even after a later _relayout() stops placing any widget there (e.g.
        # going from 5 columns down to 1 on a narrower resize) -- without
        # resetting those now-unused columns back to 0, their stale minimums
        # keep reserving phantom width the grid no longer has any content
        # for, squeezing the real column(s) well below their own minimum.
        for col in range(self._max_cols):
            self._grid.setColumnMinimumWidth(col, col_mins[col] if col < cols else 0)
        # A column-count change moves this widget's own sizeHint (fewer
        # columns means a taller, narrower hint; more means shorter and
        # wider) -- updateGeometry() invalidates the ancestor layouts'
        # cached sizeHint so a wrapper like _JoinedToggleGroup (a plain
        # QHBoxLayout around just this grid) actually re-queries it instead
        # of reporting a stale hint left over from the column count this
        # grid last had when that ancestor layout was built/activated.
        self.updateGeometry()
        if self._on_relayout is not None:
            self._on_relayout()


class _JoinedToggleGroup(QWidget):
    """A shared-outline, zero-gap row of checkable QToolButtons (SPEC §11:
    the "Layers" and "Spots" control-strip groups), each styled through the
    #toggle objectName plus a pos="first|mid|last|only" property so only the
    outer ends get rounded corners.

    Wraps a `_ReflowGrid` with spacing=0 rather than a plain QHBoxLayout so
    the group keeps the same wide-font-safe fallback (wrap onto another row
    instead of clipping past the window edge) the old flat chip row already
    had -- see tests/test_map_dominant_layout.py's wide_font_window fixture.
    """

    def __init__(self, buttons: list[QToolButton], parent=None) -> None:
        super().__init__(parent)
        self._buttons = buttons
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # _ReflowGrid's own __init__ runs its first _relayout() (and so its
        # on_relayout callback) before this constructor call returns -- i.e.
        # before `self._grid` below would exist -- so the grid is built
        # without the callback first, then wired up and applied once by hand
        # to cover that initial layout too.
        self._grid = _ReflowGrid(buttons, min_item_width=0, max_cols=len(buttons), spacing=0)
        self._grid._on_relayout = self._apply_positions
        layout.addWidget(self._grid)
        self._apply_positions()

    def _apply_positions(self) -> None:
        cols = max(1, self._grid._cols)
        n = len(self._buttons)
        for i, btn in enumerate(self._buttons):
            row, col = divmod(i, cols)
            row_len = min(cols, n - row * cols)
            if row_len <= 1:
                pos = "only"
            elif col == 0:
                pos = "first"
            elif col == row_len - 1:
                pos = "last"
            else:
                pos = "mid"
            if btn.property("pos") != pos:
                btn.setProperty("pos", pos)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def set_prefer_full_row(self, enabled: bool) -> None:
        self._grid.set_prefer_full_row(enabled)


class _ChipsRow(QWidget):
    """Holds the control strip's "Layers slot" + "Spots slot" side by side
    and forwards set_prefer_full_row() to both of their _JoinedToggleGroups.

    Without this, _MapControlStrip._apply_layout()'s `self._chips.
    set_prefer_full_row(single_row)` call (hasattr-guarded) would silently
    no-op against a plain QWidget, and each inner _ReflowGrid could latch
    onto whatever narrow width it was first given during layout settling --
    the exact self-reinforcing-narrow-column problem set_prefer_full_row()
    exists to prevent, just one level deeper than the original single flat
    chip row it was written for (see _ReflowGrid.set_prefer_full_row's own
    docstring)."""

    def __init__(self, slots: list[QWidget], parent=None) -> None:
        super().__init__(parent)
        self._groups = [s.findChild(_JoinedToggleGroup) for s in slots]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_3)
        for slot in slots:
            layout.addWidget(slot)

    def set_prefer_full_row(self, enabled: bool) -> None:
        for group in self._groups:
            if group is not None:
                group.set_prefer_full_row(enabled)


class _ElidedLabel(QLabel):
    """A label that elides its text on the right as it narrows, always exposing
    the untruncated text via its tooltip (M1)."""

    def setFullText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._reelide()
        self.updateGeometry()

    def minimumSizeHint(self):
        """Width 0 (not the full/current text's width) so a layout under
        pressure (e.g. a narrow side panel) shrinks this label first instead
        of leaving it at its last-elided width and overflowing a sibling
        widget with a fixed, un-shrinkable sizeHint past the container edge."""
        from PySide6.QtCore import QSize

        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self):
        """The *full* (un-elided) text's natural width, not the currently
        -displayed (already-elided) text's -- QLabel's own sizeHint() reads
        the live text, which here is a self-reinforcing trap: once narrowed
        once, the elided text is short, so sizeHint() asks for little, so a
        sibling-stretch layout (e.g. the map header, G3) never hands it back
        the room its real content needs. minimumSizeHint() above still stays
        0, so a genuine squeeze (narrow window, wide fonts) still shrinks
        this first, same as before -- only the "how much do I want when
        there's room" answer changes."""
        from PySide6.QtCore import QSize

        text = getattr(self, "_full_text", "")
        if not text:
            return super().sizeHint()
        width = self.fontMetrics().horizontalAdvance(text)
        return QSize(width, super().sizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reelide()

    def _reelide(self) -> None:
        text = getattr(self, "_full_text", "")
        fm = self.fontMetrics()
        super().setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max(1, self.width())))


class _MapControlStrip(QWidget):
    """Layer-toggle chips and the time/replay sliders share one slim strip
    under the map (P4). When the map pane is wide enough -- the 1280x800
    default, where the map is the dominant pane -- they sit in a single
    horizontal row; on a narrower pane (compact mode, a small window) they
    fall back to two stacked rows so nothing clips, the same guarantee
    _ReflowGrid already gives the chips on their own.

    The single-row/stacked decision uses a fixed width threshold rather than
    the chips widget's live sizeHint(): the chips are themselves a reflowing
    grid (_ReflowGrid) whose sizeHint depends on its *current* column count,
    which in turn depends on the width it was last given by this strip's own
    layout -- measuring it live creates a feedback loop that can latch onto a
    narrow-and-tall layout (one chip per row) instead of settling flat.
    """

    # Comfortably fits 7 layer chips + two compact sliders in one row; below
    # this (compact mode, a narrow window) they stack instead.
    _SINGLE_ROW_MIN_WIDTH = 820

    def __init__(
        self, chips: QWidget, sliders: QWidget, parent=None,
        single_row_min_width: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._chips = chips
        self._sliders = sliders
        # Round 10 (p4-r11): the header-row reuse of this class has much
        # narrower single-row content than the chips+sliders strip's fixed
        # 820px -- at a plain 683px compact window (no font stress at all)
        # the header's own view-switch/title/cluster/toggle/help content
        # fits a single row well under 820px, so forcing the *shared* 820px
        # threshold on it stacked it needlessly there, eating extra height
        # from the map (test_map_dominates_compact_window_height_at_683x485
        # caught this). An explicit override keeps the chips+sliders strip's
        # existing, already-tuned threshold untouched.
        self._single_row_min_width = (
            single_row_min_width if single_row_min_width is not None else self._SINGLE_ROW_MIN_WIDTH
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._row_page = QWidget()
        self._row_layout = QHBoxLayout(self._row_page)
        self._row_layout.setContentsMargins(0, SPACE_1, 0, 0)
        self._row_layout.setSpacing(SPACE_3)

        self._col_page = QWidget()
        self._col_layout = QVBoxLayout(self._col_page)
        self._col_layout.setContentsMargins(0, 0, 0, 0)
        self._col_layout.setSpacing(SPACE_1)

        self._stack.addWidget(self._row_page)
        self._stack.addWidget(self._col_page)
        self._single_row: bool | None = None
        self._apply_layout(False)

    def _apply_layout(self, single_row: bool) -> None:
        if self._single_row == single_row:
            return
        self._single_row = single_row
        # _ReflowGrid.set_prefer_full_row() makes the chips grid *ask* for
        # its one-row natural width via sizeHint() while in this mode, but
        # its minimumSizeHint() always stays well below that -- unlike the
        # old setMinimumWidth(natural_width) pin, which forced this
        # ancestor's (the map column's) minimumSizeHint that wide too, and on
        # Windows' bulkier Segoe UI chip padding that exceeded the room
        # actually available once the ~300px side panel is accounted for,
        # crushing it to a few dozen px. Short of the full natural width, the
        # grid's own resizeEvent wraps it onto extra rows instead.
        if hasattr(self._chips, "set_prefer_full_row"):
            self._chips.set_prefer_full_row(single_row)
        if single_row:
            self._col_layout.removeWidget(self._chips)
            self._col_layout.removeWidget(self._sliders)
            self._row_layout.addWidget(self._chips)
            self._row_layout.addWidget(self._sliders, 1)
            self._stack.setCurrentWidget(self._row_page)
        else:
            self._row_layout.removeWidget(self._chips)
            self._row_layout.removeWidget(self._sliders)
            self._col_layout.addWidget(self._chips)
            self._col_layout.addWidget(self._sliders)
            self._stack.setCurrentWidget(self._col_page)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_layout(self.width() >= self._single_row_min_width)

    def minimumSizeHint(self):
        """Round 8: the floor this strip can actually be squeezed to is the
        *stacked* (chips above sliders) arrangement's minimum, not whichever
        page _stack currently shows -- QStackedWidget's own minimumSizeHint
        only reflects the current page, and while in single-row mode that
        page's minimum is both chips and sliders side by side, which on
        windows-latest's bulkier fonts pushed the whole map column's
        minimumSizeHint past the 1280-minus-side-panel budget even though
        resizeEvent() above would happily wrap onto two rows well before
        actually running out of room."""
        from PySide6.QtCore import QSize

        chips_min = self._chips.minimumSizeHint()
        sliders_min = self._sliders.minimumSizeHint()
        spacing = self._col_layout.spacing()
        return QSize(
            max(chips_min.width(), sliders_min.width()),
            chips_min.height() + sliders_min.height() + spacing,
        )


# P4-7 (SPEC §9 item 3): Kp over the window drawn as bars never exceeds this,
# so a single stray high reading can't flatten every other bar to a sliver.
_SPARKLINE_MAX_KP = 9.0
_SPARKLINE_REF_KP = 4.0


class _KpSparklineChart(QWidget):
    """Bars-only drawing surface for _KpSparkline, kept a separate QWidget
    so the fixed chart height (SPEC's 36px) never fights the header label's
    own sizeHint in the same layout cell."""

    _HEIGHT = 36
    _BAR_GAP = 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self.setMinimumHeight(self._HEIGHT)
        self.setMaximumHeight(self._HEIGHT)

    def set_values(self, values: list[float]) -> None:
        self._values = list(values)
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPen

        from orbitrx.ui.theme import BORDER_DEFAULT, FAIR, SPARK_BAR

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        n = len(self._values)

        # Dashed Kp=4 reference line (SPEC §9: "A dashed reference line at
        # Kp 4 in BORDER_DEFAULT").
        ref_y = h - (_SPARKLINE_REF_KP / _SPARKLINE_MAX_KP) * h
        pen = QPen(QColor(BORDER_DEFAULT))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, int(ref_y), w, int(ref_y))

        if not n:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        bar_w = max(1.0, (w - self._BAR_GAP * (n - 1)) / n)
        for i, kp in enumerate(self._values):
            clamped = max(0.0, min(float(kp), _SPARKLINE_MAX_KP))
            bar_h = max(1.0, (clamped / _SPARKLINE_MAX_KP) * h)
            x = i * (bar_w + self._BAR_GAP)
            color = FAIR if kp >= _SPARKLINE_REF_KP else SPARK_BAR
            painter.setBrush(QColor(color))
            painter.drawRect(QRectF(x, h - bar_h, bar_w, bar_h))


class _KpSparkline(QWidget):
    """Kp 24h sparkline (P4-7, SPEC §9 item 3). Built only from real
    DataStore.query_propagation rows (see QtOrbitRxApplication._refresh_kp_sparkline);
    hidden entirely -- zero height, not an empty chart -- with fewer than 2
    rows in the last 24h, per SPEC's "If there is no history, hide the
    sparkline entirely" rule."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_1)
        header = QLabel("Kp · last 24 h")
        header.setObjectName("muted")
        layout.addWidget(header)
        self._chart = _KpSparklineChart(self)
        layout.addWidget(self._chart)
        self.setVisible(False)

    def set_rows(self, kp_values: list[float]) -> None:
        self._chart.set_values(kp_values)
        self.setVisible(len(kp_values) >= 2)

    def bar_count(self) -> int:
        return len(self._chart._values)


class _UiInvoker(QObject):
    """Runs callables on the Qt GUI thread (controller callbacks come from worker threads).

    Must be parented to the window it delivers callbacks for: a queued
    `call.emit(...)` posts an event that is only processed on a later turn of
    the event loop, and destroying this invoker along with its window makes
    Qt drop any such event still in flight. Without a parent this object
    would outlive the window (kept alive only by a plain Python reference),
    so a worker-thread result arriving after the window was closed would
    still fire and touch widgets whose C++ objects are already deleted --
    the "already deleted" shiboken RuntimeError this parenting prevents.
    """

    call = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.call.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)

    def wrap(self, fn):
        def emit(*args):
            import shiboken6
            if not shiboken6.isValid(self):
                return  # window closed/deleted before this worker-thread result arrived
            self.call.emit(lambda: fn(*args))
        return emit


class QtOrbitRxApplication(QMainWindow):
    # Round 6 (SPEC §11): the control strip's two joined toggle groups.
    # Spots stays inline at every width ("At 683 ... Spots stay inline");
    # Layers is the one that collapses into #layersMenuButton.
    _LAYER_GROUP_ITEMS = [
        ("greyline", "Greyline"), ("night", "Night"), ("dx_arcs", "DX"),
        ("aurora", "Aurora"), ("grid", "Grid"),
    ]
    _SPOTS_GROUP_ITEMS = [("spot_arcs", "Live"), ("spot_heatmap", "Heat")]

    # Round 6 (SPEC §11 "Below 600 px width, the time sliders move into a
    # 'Time ▾' popover"), same ±16px hysteresis idiom as
    # COMPACT_WIDTH_BELOW/ABOVE above.
    _TIME_POPOVER_BELOW = 600
    _TIME_POPOVER_ABOVE = 616

    def __init__(self) -> None:
        self._t_init_start = time.perf_counter()
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        self.setWindowTitle(f"OrbitRx Propagation Monitor {__version__}")
        # 2:1 matches the equirectangular basemap's own aspect; map_widget's
        # _fit_scene_rect() always fitInView(KeepAspectRatioByExpanding), so
        # the map fills the pane completely with a uniform zoom (overlays
        # stay aligned) and crops symmetrically off whichever axis the pane's
        # own aspect overshoots, instead of ever leaving a dark letterbox bar.
        self.renderer = MapRenderer(width=1200, height=600)
        self._labels: dict[str, QLabel] = {}
        self._layer_checks: dict[str, QToolButton] = {}
        self._map_container: QWidget | None = None
        self._side_panel_visible = True
        self._tray: QSystemTrayIcon | None = None
        self._layers_save_timer: QTimer | None = None
        self._slider_refresh_timer = QTimer(self)
        self._slider_refresh_timer.setSingleShot(True)
        self._slider_refresh_timer.timeout.connect(self._slider_refresh_cooldown)
        self._slider_refresh_pending = False
        self._replay_refresh_timer = QTimer(self)
        self._replay_refresh_timer.setSingleShot(True)
        self._replay_refresh_timer.timeout.connect(self._replay_refresh_cooldown)
        self._replay_refresh_pending = False
        # P1: weather-refresh and DX-spot-triggered map rebuilds share the same
        # ~80ms debounce as the slider/replay drags above, so a burst of either
        # (e.g. several DX spots landing close together) coalesces into at most
        # one extra rebuild instead of one dispatch per event.
        self._map_rebuild_timer = QTimer(self)
        self._map_rebuild_timer.setSingleShot(True)
        self._map_rebuild_timer.timeout.connect(self._map_rebuild_cooldown)
        self._map_rebuild_pending = False
        self._map_rebuild_pending_vectors_only = False

        self._ui = _UiInvoker(self)
        self._map_load_thread: threading.Thread | None = None
        self._update_check_thread: threading.Thread | None = None
        self._plot_query_thread: threading.Thread | None = None
        # P2B: one toast surface for the whole main window, used by both
        # controller-reported failures (below) and the UI's own (export,
        # map-load, update-check) failure paths.
        self._toasts = ToastManager(self)
        ui = self._ui.wrap
        self.ctrl = OrbitRxController(
            on_status=ui(self._set_status),
            on_weather=ui(self._refresh_labels_and_map),
            on_dx=ui(self._refresh_labels_and_map),
            on_cluster=ui(self._set_cluster),
            on_alarm_excellent=ui(self._alarm_excellent),
            on_alarm_storm=ui(self._alarm_storm),
            on_error=ui(self._on_controller_error),
        )
        self.ctrl._on_band_beep = ui(self._spot_beep)
        self.ctrl.on_live_spots = ui(self._refresh_live_spots)

        geom = self.ctrl.cfg.get("window_geometry", "1400x820")
        self.resize(*self._parse_geom(geom))
        self._build_ui()
        self._render_cluster_label()  # P4-8: sync the map's cluster pill to the initial real state
        fit_to_screen(self, 640, 440)
        self._load_map()
        self._refresh_map()
        self.ctrl.seed_demo_spots()
        self.ctrl.start()
        self._setup_tray()
        QTimer.singleShot(200, self._startup)
        if self.ctrl.cfg.get("check_updates_on_launch", True):
            QTimer.singleShot(3000, self._check_updates)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start(int(self.ctrl.cfg.get("refresh_interval_seconds", 60)) * 1000)
        self._update_next_refresh_label()

        self._cluster_pulse_phase = False
        self._cluster_pulse_timer = QTimer(self)
        self._cluster_pulse_timer.timeout.connect(self._tick_cluster_pulse)
        self._cluster_pulse_timer.start(700)

        # P4-3: menu-bar corner clock. Minute resolution, so a 15s tick is
        # plenty to stay visibly in sync without waking the event loop every
        # second for a label that only ever shows HH:MM.
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(15000)

        self.ctrl.log.info(
            "perf: cold_start_to_first_paint_ready_ms=%.1f",
            (time.perf_counter() - self._t_init_start) * 1000,
        )

    def _parse_geom(self, g: str) -> tuple[int, int]:
        try:
            w, h = g.split("x")
            return int(w), int(h)
        except Exception:
            return 1400, 820

    def _create_map_widget(self):
        return PropagationMapWidget(self.renderer)

    def _build_view_switch(self) -> QFrame:
        """P4-4: Map/Bands/Log segmented control in the map header, replacing
        the removed mainToolbar row (SPEC §6.1/§14 "viewSwitch"). Wired to the
        same QAction objects as Ctrl+1/2/3 and the View menu (_build_actions)
        rather than duplicating _focus_panel, so there is still exactly one
        handler per command; _activate_view keeps the checked segment in sync
        no matter which of the three entry points (click, shortcut, menu) was
        used."""
        track = QFrame()
        track.setObjectName("segTrack")
        layout = QHBoxLayout(track)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._seg_buttons: dict[str, QToolButton] = {}
        self._seg_group = QButtonGroup(track)
        self._seg_group.setExclusive(True)
        for key, shortcut in (("Map", "Ctrl+1"), ("Bands", "Ctrl+2"), ("Log", "Ctrl+3")):
            btn = QToolButton()
            btn.setObjectName("segButton")
            btn.setText(key)
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setToolTip(f"{key} ({shortcut})")
            btn.clicked.connect(lambda _=False, k=key: self._actions[k].trigger())
            self._seg_group.addButton(btn)
            layout.addWidget(btn)
            self._seg_buttons[key] = btn
        self._seg_buttons["Map"].setChecked(True)
        return track

    def _activate_view(self, which: str) -> None:
        """Shared by the Map/Bands/Log QActions (Ctrl+1/2/3, View menu and the
        segmented control's own click handler) so all three entry points keep
        the segmented control's checked segment in sync with whichever pane is
        actually focused, instead of three independent triggers."""
        self._focus_panel(which)
        seg_buttons = getattr(self, "_seg_buttons", None)
        if seg_buttons is None:
            return
        btn = seg_buttons.get(which.capitalize())
        if btn is not None and not btn.isChecked():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)

    def _build_ui(self) -> None:
        self._build_actions()
        self._build_menu_bar()
        self._build_status_bar()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        map_pane = QWidget()
        map_layout = QVBoxLayout(map_pane)
        # P4: one slim header row -- view switch, title, Cluster combo, the
        # side-panel collapse toggle and the help chip -- replaces the old
        # three stacked rows (title / greyline subtitle / cluster) plus the
        # removed mainToolbar row (P4-4), so the map starts right under the
        # menu bar. G6: the greyline caption's status-bar duplicate is gone
        # too, now that this header shows the real string directly.
        # P5-r2 (G2/G3 leftover): the left/right gutter now lives on
        # map_tab_layout below, so it applies evenly to the header, the map
        # frame, the control strip and the band row alike -- previously only
        # map_pane had this margin, leaving the control strip (added straight
        # to map_tab_layout) flush against the window edge.
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(SPACE_1)
        self._map_layout = map_layout
        header_left = QWidget()
        header_left_layout = QHBoxLayout(header_left)
        header_left_layout.setContentsMargins(0, 0, 0, 0)
        header_left_layout.setSpacing(SPACE_2)
        header_left_layout.addWidget(self._build_view_switch(), 0, Qt.AlignmentFlag.AlignVCenter)
        # Round 10 (p4-r11): _ElidedLabel, not a plain QLabel -- its
        # minimumSizeHint() is pinned to 0 (see that class), so this title can
        # never be the thing that forces the unreflowable header row's own
        # minimum width past the map column's budget. Load-failure text
        # (_on_map_load_failed) interpolates a real, unbounded exception
        # message here, which was a genuine latent bug independent of any CI
        # font metrics: a long enough error string could already force this
        # row arbitrarily wide. setFullText() keeps the untruncated string
        # reachable via tooltip.
        # SPEC §6.2/§12 callout 1: "Greyline · <date> <time> UTC" in mono,
        # driven by the map's own real greyline_meta_changed signal below --
        # never the static "Map"/"Loading map..." placeholder this replaced
        # (see _load_map/_on_map_loaded, which used to overwrite this with
        # literal "Map" text on every load). _ElidedLabel still elides (and
        # keeps the untruncated string in its tooltip) if the header is ever
        # squeezed narrower than the caption needs.
        self.banner = _ElidedLabel()
        self.banner.setObjectName("headerGreyline")
        self.banner.setWordWrap(False)
        self.banner.setFullText("Loading map...")
        header_left_layout.addWidget(self.banner)
        header_left_layout.addStretch(1)

        header_right = QWidget()
        header_right_layout = QHBoxLayout(header_right)
        header_right_layout.setContentsMargins(0, 0, 0, 0)
        header_right_layout.setSpacing(SPACE_2)
        header_right_layout.addStretch(1)
        header_right_layout.addWidget(QLabel("Cluster"))
        # SPEC §6.1/§11 "Cluster combo with a status dot": a small dot
        # ahead of the combo, synced to the real cluster_status in
        # _render_cluster_label -- same connection-state source the corner
        # widget's dot and the status bar's label already use.
        self._cluster_dot_lbl = QLabel("●")
        self._cluster_dot_lbl.setObjectName("clusterComboDot")
        header_right_layout.addWidget(self._cluster_dot_lbl)
        self.cluster_combo = QComboBox()
        self.cluster_combo.setMaximumWidth(260)
        # Round 9: without this, QComboBox's default AdjustToContentsOnFirstShow
        # sizes (and floors) this combo off its *widest real item* -- a
        # cluster hostname:port string with no length limit -- which can grow
        # this header row's minimum width well past the map-column budget
        # under a bulkier font. A fixed contents-length budget keeps the
        # floor bounded; the combo still elides its own displayed text when
        # narrower than it, and every item's full host string is still
        # reachable in the dropdown.
        self.cluster_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.cluster_combo.setMinimumContentsLength(10)
        self._populate_cluster_combo()
        self.cluster_combo.currentIndexChanged.connect(self._cluster_node_changed)
        header_right_layout.addWidget(self.cluster_combo)
        # SPEC §6.2/§12 callout 1 + G3: the unlabelled ">>"/"<<" collapse
        # button that used to sit here is gone -- Ctrl+B and the View menu's
        # "Show side panel" action (both wired to the same
        # _set_side_panel_visible handler) are the only entry points now.
        self._map_help = QToolButton()
        self._map_help.setText("?")
        self._map_help.setObjectName("helpChip")
        self._map_help.setToolTip(
            "Scroll to zoom · Right-drag to pan · Double-click to reset · Click a spot to tune"
        )
        self._map_help.setAutoRaise(True)
        header_right_layout.addWidget(self._map_help)
        # Round 6 (SPEC §5/§13 "the map header 36/32"): wrapped in its own
        # QWidget (rather than added as a bare QHBoxLayout) so
        # _update_compact_chrome can cap its height directly.
        # Round 10 (p4-r11): this used to be one flat, unreflowable QHBoxLayout
        # -- its minimum width was the *sum* of every item (view switch, title,
        # "Cluster:" label, combo, side-panel toggle, help chip), which under
        # Windows' bulkier Segoe UI metrics could exceed the map column's
        # budget and crush the side panel even though every individual item
        # was already font-independently bounded. Reusing _MapControlStrip's
        # single-row/stacked-pair mechanism (same 820px breakpoint the control
        # strip and the in-map legend already use) gives this row the same
        # guarantee: its minimumSizeHint() is always the *stacked* (two-row)
        # floor -- max(header_left, header_right), not their sum -- so it can
        # never be the thing that forces the map column wider than the side
        # panel's share can afford.
        # The header's own content needs far less width in one row than the
        # chips+sliders strip's shared 820px floor -- deriving this threshold
        # from the two halves' real sizeHint() widths (same "size off the
        # real font metrics, not a fixed guess" rule _ReflowGrid already
        # follows) means a plain 683px compact window still gets a genuine
        # single-row header, while a font-stressed ~1000px window still
        # stacks once its *own* content actually needs to.
        header_single_row_width = (
            header_left.sizeHint().width() + header_right.sizeHint().width() + SPACE_3
        )
        self._map_header_row = _MapControlStrip(
            header_left, header_right, single_row_min_width=header_single_row_width
        )
        map_layout.addWidget(self._map_header_row)

        self.map_widget = self._create_map_widget()
        self.map_widget.spot_clicked.connect(self._tune_from_map)
        if hasattr(self.map_widget, "greyline_meta_changed"):
            # G3/SPEC §6.2: the header caption shows this real caption --
            # G6 dropped the status bar's old duplicate "Greyline @ ..."
            # subtitle, since the header already shows the same string.
            self.map_widget.greyline_meta_changed.connect(self.banner.setFullText)
        self.map_widget.map_clicked.connect(self._on_map_click)
        # P4-8 (SPEC §7): "QFrame#mapFrame has a 1px BORDER_SUBTLE border,
        # radius 8, and a MAP_OCEAN background" -- wraps the graphics view so
        # the never-letterbox ocean padding _fit_scene_rect() now adds sits
        # inside a visibly-framed map, not a borderless rectangle.
        self._map_frame = QFrame()
        self._map_frame.setObjectName("mapFrame")
        map_frame_layout = QVBoxLayout(self._map_frame)
        map_frame_layout.setContentsMargins(0, 0, 0, 0)
        map_frame_layout.addWidget(self.map_widget)
        map_layout.addWidget(self._map_frame, stretch=1)

        # Round 6 (SPEC §11): "Layers" (Greyline/Night/DX/Aurora/Grid) and
        # "Spots" (Live/Heat) are now two separate joined toggle groups, each
        # with its own label, instead of one flat 7-chip row -- Live/Heat
        # still apply to the native map's own live-spots layer
        # (set_live_spots), same as every other toggle here. _layer_checks
        # keeps all 7 keys regardless of grouping, since _layers_changed/
        # _refresh_live_spots and several tests read it as one flat dict.
        for key, label in self._LAYER_GROUP_ITEMS + self._SPOTS_GROUP_ITEMS:
            chip = QToolButton()
            chip.setText(label)
            chip.setCheckable(True)
            chip.setObjectName("toggle")
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            chip.blockSignals(True)
            chip.setChecked(self.ctrl.cfg.get("map_layers", {}).get(key, key != "grid"))
            chip.blockSignals(False)
            self._layer_checks[key] = chip
        for chip in self._layer_checks.values():
            chip.toggled.connect(lambda _=False: self._layers_changed())

        layers_label = QLabel("Layers")
        layers_label.setObjectName("groupLabel")
        self._layers_group = _JoinedToggleGroup(
            [self._layer_checks[k] for k, _ in self._LAYER_GROUP_ITEMS]
        )
        self._layers_menu_btn = self._build_layers_menu_button()
        self._layers_slot = QWidget()
        layers_slot_layout = QHBoxLayout(self._layers_slot)
        layers_slot_layout.setContentsMargins(0, 0, 0, 0)
        layers_slot_layout.setSpacing(SPACE_1)
        layers_slot_layout.addWidget(layers_label)
        layers_slot_layout.addWidget(self._layers_group)
        layers_slot_layout.addWidget(self._layers_menu_btn)
        self._layers_label = layers_label

        spots_label = QLabel("Spots")
        spots_label.setObjectName("groupLabel")
        self._spots_group = _JoinedToggleGroup(
            [self._layer_checks[k] for k, _ in self._SPOTS_GROUP_ITEMS]
        )
        spots_slot = QWidget()
        spots_slot_layout = QHBoxLayout(spots_slot)
        spots_slot_layout.setContentsMargins(0, 0, 0, 0)
        spots_slot_layout.setSpacing(SPACE_1)
        spots_slot_layout.addWidget(spots_label)
        spots_slot_layout.addWidget(self._spots_group)

        chips_row = _ChipsRow([self._layers_slot, spots_slot])
        chips_row.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._chips_row = chips_row
        self._layers_compact = None  # sentinel: force _apply_layers_compact's first call through
        self._apply_layers_compact(False)
        # V11 must-fix 3: chips live under the map pane (not inside it) so 150%
        # compact never paints them over Antarctica / greyline.

        # P4/Round 6: the two time sliders share one compact row (label/
        # slider/mono value each, SPEC §11 item 4); combined with the chips
        # above via _MapControlStrip, this is the "one slim control strip" a
        # map-dominant layout calls for, instead of the three previously-
        # stacked rows. _time_box is reparented into a "Time ▾" popover below
        # 600px width (_apply_time_popover) rather than living in a second
        # fixed location, so there is still exactly one pair of slider widgets.
        sliders_row = QWidget()
        sliders_row_layout = QHBoxLayout(sliders_row)
        sliders_row_layout.setContentsMargins(0, 0, 0, 0)
        sliders_row_layout.setSpacing(0)
        # SPEC §11: "a stretch" separates the Layers/Spots groups from the
        # time sliders, which sit at the strip's far right -- _MapControlStrip
        # already gives this row a stretch=1 slot of its own, so this second,
        # inner stretch right-aligns _time_box/_time_popover_btn within it
        # rather than leaving the gap on the wrong side.
        sliders_row_layout.addStretch(1)
        self._sliders_row_layout = sliders_row_layout

        self._time_box = QWidget()
        time_box_layout = QHBoxLayout(self._time_box)
        time_box_layout.setContentsMargins(0, 0, 0, 0)
        time_box_layout.setSpacing(SPACE_3)

        offset_box = QHBoxLayout()
        offset_box.setSpacing(SPACE_1)
        offset_lbl = QLabel("Offset")
        offset_lbl.setObjectName("groupLabel")
        offset_lbl.setToolTip("Time offset (hours)")
        offset_box.addWidget(offset_lbl)
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 48)
        self.time_slider.setValue(0)
        self.time_slider.setToolTip("Time offset (hours)")
        self.time_slider.setFixedWidth(SLIDER_WIDTH)
        self.time_slider.valueChanged.connect(self._slider_moved)
        offset_box.addWidget(self.time_slider)
        self.lbl_slider = QLabel(format_hour_offset(0))
        self.lbl_slider.setObjectName("sliderValue")
        self.lbl_slider.setMinimumWidth(SLIDER_VALUE_MIN_WIDTH)
        self.lbl_slider.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        offset_box.addWidget(self.lbl_slider)
        time_box_layout.addLayout(offset_box)

        replay_box = QHBoxLayout()
        replay_box.setSpacing(SPACE_1)
        replay_lbl = QLabel("Replay")
        replay_lbl.setObjectName("groupLabel")
        replay_lbl.setToolTip("Spot replay (hours ago)")
        replay_box.addWidget(replay_lbl)
        self.replay_slider = QSlider(Qt.Orientation.Horizontal)
        self.replay_slider.setRange(0, 48)  # whole-hour steps, up to 48 hours ago
        self.replay_slider.setValue(0)
        self.replay_slider.setToolTip("0 = live. Drag left to right to replay cached PSKReporter spots.")
        self.replay_slider.setFixedWidth(SLIDER_WIDTH)
        self.replay_slider.valueChanged.connect(self._replay_moved)
        replay_box.addWidget(self.replay_slider)
        self.lbl_replay = QLabel("Live")
        self.lbl_replay.setObjectName("sliderValue")
        self.lbl_replay.setMinimumWidth(SLIDER_VALUE_MIN_WIDTH)
        self.lbl_replay.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        replay_box.addWidget(self.lbl_replay)
        time_box_layout.addLayout(replay_box)

        self._time_popover_btn = QToolButton(sliders_row)
        self._time_popover_btn.setObjectName("timePopoverButton")
        self._time_popover_btn.setText("Time ▾")
        self._time_popover_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        time_menu = QMenu(self._time_popover_btn)
        # No setDefaultWidget(self._time_box) yet: QWidgetAction hides a
        # widget it's given as soon as it's handed one (the menu itself
        # isn't open), and that explicit hide survives a later
        # sliders_row_layout.addWidget() reparent -- _apply_time_popover(True)
        # associates _time_box with this action (and shows it again) only
        # once the popover is actually entered.
        time_menu.addAction(QWidgetAction(time_menu))
        self._time_popover_btn.setMenu(time_menu)
        self._time_popover = False
        # Not yet added to sliders_row_layout below -- an un-laid-out child
        # widget is still visible by default once its parent is shown, so
        # without this it would float, visible, at (0,0) until the first
        # _apply_time_popover(True) call ever adds it to a layout.
        self._time_popover_btn.setVisible(False)
        sliders_row_layout.addWidget(self._time_box)

        self._map_controls = _MapControlStrip(chips_row, sliders_row)

        # M1: no scroll area around the map pane. The map stretches and shrinks so
        # the layer toggles and sliders stay visible without scrolling.
        self._map_scroll = None
        self._map_pane = map_pane

        map_tab = QWidget()
        map_tab_layout = QVBoxLayout(map_tab)
        map_tab_layout.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        map_tab_layout.setSpacing(SPACE_1)
        map_tab_layout.addWidget(map_pane, stretch=1)
        map_tab_layout.addWidget(self._map_controls)
        # SPEC §6.2/§8: one row of 6 band cards under the map, below the
        # control strip, spanning the map column at the 1280 width this
        # round targets -- not the side panel's 2x3 grid. _enter_/
        # _exit_compact_mode move it back into the side panel (its pre-P5
        # position) below COMPACT_WIDTH_BELOW: the compact band-chips-under-
        # the-map row is its own gap (G10, a later round), and at 683 there
        # isn't vertical room under the map for both the map and this row
        # without shrinking the map below its own dominance floor.
        self.band_panel = BandPanelWidget()
        map_tab_layout.addWidget(self.band_panel)
        self._map_tab = map_tab
        self._map_tab_layout = map_tab_layout

        # P5-r2 (G4): this used to be a second QScrollArea nested inside the
        # outer sidePaneScroll, with a *third* one (stats_scroll, below)
        # nested inside that -- three stacked scroll areas, with the
        # innermost showing a visible bar even at the full 1280x800 height
        # the panel's own content is supposed to fit in (SPEC §6.2's budget),
        # while the outer two silently clipped whatever didn't fit their own
        # policy-Off bars. Collapsed to a single scroll area (side_scroll,
        # below) that is the one real fallback for small window heights;
        # right_panel is now a plain (non-scrolling) widget.
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        right_layout.setSpacing(SPACE_2)
        self._right_layout = right_layout

        right_panel.setMinimumWidth(0)
        # P4-3: the panel's old "Last updated: ..." / "Cluster: ..." header
        # rows are gone -- both facts already live elsewhere (refresh time
        # and cluster status in the status bar, cluster also in the menu-bar
        # corner widget), so repeating them here was pure duplication
        # (SPEC §1 #4, §6.1 "Removed: the panel's top status lines").

        self.tabs = QTabWidget()
        stats_tab = QWidget()
        stats_outer = QVBoxLayout(stats_tab)
        stats_outer.setSpacing(SPACE_2)

        # P4-7/SPEC §9 item 1: "Space weather" title left, a real freshness
        # stamp right (Updated/Refreshing…/Stale ·/Never updated -- computed
        # in _space_weather_freshness_text from the controller's actual fetch
        # state, never a sample value).
        sw_header_row = QHBoxLayout()
        sw_title_lbl = QLabel("Space weather")
        sw_title_lbl.setObjectName("sectionTitle")
        sw_header_row.addWidget(sw_title_lbl)
        sw_header_row.addStretch(1)
        self._freshness_lbl = QLabel("Never updated")
        self._freshness_lbl.setObjectName("freshness")
        sw_header_row.addWidget(self._freshness_lbl)
        stats_outer.addLayout(sw_header_row)

        # P4-7/SPEC §9 item 2: three key tiles -- SFI, Kp, A-index. The old
        # Kp/SFI/MUF trio is gone: MUF (and LUF) move to their own
        # Propagation tiles below, so Kp appears exactly once on screen
        # ("remove the duplicate Kp row/tile so each fact appears once").
        # The Kp tile's caption adds the kp_state() word in a semantic
        # colour; the value itself always stays primary (never coloured).
        self._kpi_labels: dict[str, QLabel] = {}
        self._kp_caption_lbl: QLabel | None = None
        key_metrics_row = QHBoxLayout()
        key_metrics_row.setSpacing(SPACE_2)
        for key, caption in (("sfi", "SFI"), ("kp", "Kp"), ("a_index", "A-index")):
            tile = QFrame()
            tile.setObjectName("keyMetricTile")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(SPACE_2, SPACE_1, SPACE_2, SPACE_1)
            tile_layout.setSpacing(0)
            value_lbl = QLabel(NO_DATA)
            value_lbl.setObjectName("keyMetricValue")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption_lbl = QLabel(caption)
            caption_lbl.setObjectName("keyMetricCaption")
            caption_lbl.setTextFormat(Qt.TextFormat.RichText)
            caption_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile_layout.addWidget(value_lbl)
            tile_layout.addWidget(caption_lbl)
            self._kpi_labels[key] = value_lbl
            if key == "kp":
                self._kp_caption_lbl = caption_lbl
            key_metrics_row.addWidget(tile, 1)
        stats_outer.addLayout(key_metrics_row)

        # P4-7/SPEC §9 item 3: Kp 24h sparkline, built only from real
        # propagation-table rows (see _refresh_kp_sparkline) on a worker
        # thread -- hidden entirely (not an empty chart) with <2 rows.
        self._kp_sparkline = _KpSparkline()
        stats_outer.addWidget(self._kp_sparkline)

        # P4-6 (SPEC §10 "Whole section never loaded"/states-sheet.png): a
        # single muted line, shown only before the first successful weather
        # fetch, pointing at the real cause instead of leaving the tiles'
        # NO_DATA dashes unexplained. Toggled in _refresh_labels_and_map;
        # visible by default so it is correct even before the first refresh.
        self._weather_never_loaded_lbl = QLabel(
            'No data yet. Values appear after the first refresh. <a href="#">Refresh now</a>'
        )
        self._weather_never_loaded_lbl.setWordWrap(True)
        self._weather_never_loaded_lbl.setObjectName("muted")
        self._weather_never_loaded_lbl.linkActivated.connect(lambda _: self._trigger_weather_refresh())
        stats_outer.addWidget(self._weather_never_loaded_lbl)

        stats_body = QWidget()
        stats_body_layout = QVBoxLayout(stats_body)
        stats_body_layout.setContentsMargins(0, 0, 0, 0)
        stats_body_layout.setSpacing(SPACE_2)

        pretty = {
            "kp_forecast": "Kp forecast", "sunspot": "Sunspot", "solar_wind": "Solar wind",
            "bz": "Bz", "bands": "Bands", "path_muf": "Path MUF", "sunrise": "Sunrise",
            "sunset": "Sunset", "location": "You",
        }

        self._stat_name_labels: dict[str, QLabel] = {}

        def _build_detail_row(key: str, label_text: str) -> QFrame:
            """P4-7/SPEC §9 item 4: label left (tertiary), mono value right
            (primary), 1px bottom divider, no card box -- replaces the old
            boxed grid-card row for every key that moves here."""
            row = QFrame()
            row.setObjectName("detailRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(SPACE_2)
            name = QLabel(label_text)
            name.setObjectName("rowLabel")
            name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value = QLabel(NO_DATA)
            value.setObjectName("rowValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(name)
            row_layout.addStretch(1)
            row_layout.addWidget(value)
            self._stat_name_labels[key] = name
            self._labels[key] = value
            return row

        def _hline_divider() -> QFrame:
            line = QFrame()
            line.setStyleSheet(f"background: {BORDER}; border: none; min-height: 1px; max-height: 1px;")
            return line

        # Detail rows: Kp forecast, Sunspot, Solar wind, Bz -- the old
        # combined "Wind ... Bz" cell is now two rows (SPEC §9 item 4).
        for key in ("kp_forecast", "sunspot", "solar_wind", "bz"):
            stats_body_layout.addWidget(_build_detail_row(key, pretty[key]))

        stats_body_layout.addWidget(_hline_divider())

        # Propagation: header with the "HamQSL" source label on the right,
        # MUF/LUF Metric-M tiles, then a Bands row (SPEC §9 item 5).
        prop_header_row = QHBoxLayout()
        prop_title_lbl = QLabel("Propagation")
        prop_title_lbl.setObjectName("sectionTitle")
        prop_header_row.addWidget(prop_title_lbl)
        prop_header_row.addStretch(1)
        prop_source_lbl = QLabel("HamQSL")
        prop_source_lbl.setObjectName("rowLabel")
        prop_header_row.addWidget(prop_source_lbl)
        stats_body_layout.addLayout(prop_header_row)

        prop_tiles_row = QHBoxLayout()
        prop_tiles_row.setSpacing(SPACE_2)
        for key, caption in (("muf", "MUF"), ("luf", "LUF")):
            tile = QFrame()
            tile.setObjectName("keyMetricTile")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(SPACE_2, SPACE_1, SPACE_2, SPACE_1)
            tile_layout.setSpacing(0)
            value_lbl = QLabel(NO_DATA)
            value_lbl.setObjectName("keyMetricValue")
            value_lbl.setProperty("size", "m")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption_lbl = QLabel(caption)
            caption_lbl.setObjectName("keyMetricCaption")
            caption_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile_layout.addWidget(value_lbl)
            tile_layout.addWidget(caption_lbl)
            value_lbl.style().unpolish(value_lbl)
            value_lbl.style().polish(value_lbl)
            self._labels[key] = value_lbl
            prop_tiles_row.addWidget(tile, 1)
        stats_body_layout.addLayout(prop_tiles_row)

        stats_body_layout.addWidget(_build_detail_row("bands", pretty["bands"]))

        stats_body_layout.addWidget(_hline_divider())

        # Path: collapsible row, collapsed by default. While Location is not
        # set, the header's right side is a "Set location to enable" link to
        # Location settings (SPEC §9 item 8).
        path_header_row = QHBoxLayout()
        path_header_row.setSpacing(SPACE_1)
        self._path_toggle_btn = QToolButton()
        self._path_toggle_btn.setObjectName("pathToggle")
        self._path_toggle_btn.setCheckable(True)
        self._path_toggle_btn.setChecked(False)
        self._path_toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
        self._path_toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._path_toggle_btn.setText("Path")
        self._path_toggle_btn.setAutoRaise(True)
        self._path_toggle_btn.toggled.connect(self._on_path_toggled)
        path_header_row.addWidget(self._path_toggle_btn)
        path_header_row.addStretch(1)
        self._path_hint_lbl = QLabel('<a href="#">Set location to enable</a>')
        self._path_hint_lbl.setObjectName("muted")
        self._path_hint_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._path_hint_lbl.linkActivated.connect(lambda _: self._settings(initial_page="Station"))
        path_header_row.addWidget(self._path_hint_lbl)
        stats_body_layout.addLayout(path_header_row)

        self._path_body = QWidget()
        path_body_layout = QVBoxLayout(self._path_body)
        path_body_layout.setContentsMargins(0, SPACE_1, 0, 0)
        path_body_layout.setSpacing(0)
        for key in ("path_muf", "sunrise", "sunset", "location"):
            path_body_layout.addWidget(_build_detail_row(key, pretty[key]))
        self._location_hint_lbl = QLabel(
            'Set your location to unlock path MUF and sun times. <a href="#">Location</a>'
        )
        self._location_hint_lbl.setWordWrap(True)
        self._location_hint_lbl.setObjectName("muted")
        self._location_hint_lbl.setStyleSheet(
            f"background: {BG_ELEVATED}; border: 1px solid {BORDER}; "
            f"border-radius: {RADIUS_M}px; padding: {SPACE_3}px;"
        )
        self._location_hint_lbl.linkActivated.connect(lambda _: self.ctrl.refresh_location())
        self._location_hint_lbl.setVisible(False)
        path_body_layout.addWidget(self._location_hint_lbl)
        self._path_body.setVisible(False)  # collapsed by default
        stats_body_layout.addWidget(self._path_body)

        # P5-r2 (G4): the "OPS" card (UTC/cluster/27-day-forecast/contest/DX)
        # is gone -- not in SPEC §9's panel structure, and it was the single
        # biggest contributor to the side panel's vertical overflow. UTC and
        # cluster state already live in the menu-bar corner (G5) and the
        # header's cluster combo; the 27-day-forecast/contest/DX-preview
        # fields had no other home and are dropped (real information lost,
        # logged in the P5 round notes, not silently -- none of SPEC's panel
        # structure calls for them).
        stats_body_layout.addStretch(1)

        stats_outer.addWidget(stats_body, stretch=1)

        stats_outer.addWidget(QLabel("Alerts"))
        self.alerts_list = QListWidget()
        self.alerts_list.setMaximumHeight(90)
        self.alerts_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.alerts_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.alerts_list.setWordWrap(False)
        self.alerts_list.setUniformItemSizes(True)
        stats_outer.addWidget(self.alerts_list)
        self.tabs.addTab(stats_tab, "Stats")
        self._stats_tab = stats_tab

        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        hist_row = QHBoxLayout()
        # S1: a field label for the date picker, so it must stay visible in every
        # plot state (before Refresh, no-data, and an actually-rendered chart alike).
        self.hist_ending_lbl = QLabel("Ending")
        hist_row.addWidget(self.hist_ending_lbl)
        self.hist_date = QDateEdit()
        self.hist_date.setCalendarPopup(True)
        self.hist_date.setDisplayFormat("dd MMM yyyy")  # S1: no ISO dates in the UI
        self.hist_date.setDate(QDate.currentDate())
        hist_row.addWidget(self.hist_date)
        hist_row.addWidget(QPushButton("Refresh", clicked=self._refresh_plot_tab))
        plot_layout.addLayout(hist_row)
        self.plot_container = QVBoxLayout()
        plot_layout.addLayout(self.plot_container)
        self.plot_placeholder = QLabel("Click Refresh to load history chart")
        self.plot_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_container.addWidget(self.plot_placeholder)
        self.tabs.addTab(plot_tab, "Plot")
        self._plot_tab = plot_tab
        # P5-r2 (G4/SPEC §6.1 "Removed: the Stats/Plot tabs. Stats *is* the
        # panel"): the tab *bar* is hidden (Stats stays the only thing shown
        # by default, matching the mockup exactly), but the QTabWidget itself
        # -- and both its pages -- stay exactly as they were rather than
        # being torn out: tests/test_history_plot.py and
        # tests/test_p1_threading.py drive the Plot tab's threaded history
        # query via window.tabs.setCurrentIndex(1), and
        # tests/test_menu_bar.py pins window.tabs.currentWidget() at
        # startup -- rewriting ~25 tests' tab-switching setup for a purely
        # cosmetic tab-row removal was out of this round's time box. Plot
        # stays reachable without the visible tab row via the new "Open
        # plot…" View-menu action below.
        self.tabs.tabBar().setVisible(False)

        right_layout.addWidget(self.tabs)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("muted")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        right_layout.addWidget(self.status_lbl)

        self.click_lbl = QLabel("")
        self.click_lbl.setWordWrap(True)
        self.click_lbl.setObjectName("muted")
        right_layout.addWidget(self.click_lbl)
        right_layout.addStretch()

        # M1: action buttons live in the menu bar/map header, not here, so the
        # side panel only needs its own vertical scroll for the band
        # tiles/tabs above.
        side_scroll = QScrollArea()
        side_scroll.setObjectName("sidePaneScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll_body = QWidget()
        side_scroll_body_layout = QVBoxLayout(side_scroll_body)
        side_scroll_body_layout.setContentsMargins(0, 0, 0, 0)
        side_scroll_body_layout.addWidget(right_panel, stretch=1)
        side_scroll.setWidget(side_scroll_body)
        self._side_scroll = side_scroll

        side_pane = QWidget()
        side_pane_layout = QVBoxLayout(side_pane)
        side_pane_layout.setContentsMargins(0, 0, 0, 0)
        side_pane_layout.addWidget(side_scroll)
        self._side_pane = side_pane

        # P4: narrowed to a ~300px rail (280-320px) by default, down from the
        # old 320-420px range, so the map stays the dominant pane. It can be
        # hidden entirely -- via the header's collapse button, the View menu's
        # "Show side panel" action (Ctrl+B, see _set_side_panel_visible), or
        # by dragging the splitter handle all the way shut (collapsible).
        # Below COMPACT_WIDTH_BELOW logical px, _update_compact_mode() swaps
        # to the Map/Conditions tabs instead (see resizeEvent).
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._map_tab)
        side_pane.setMinimumWidth(0)
        side_pane.setMaximumWidth(340)
        self._splitter.addWidget(side_pane)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setChildrenCollapsible(True)
        self._splitter_user_resized = False
        self._splitter.splitterMoved.connect(self._on_splitter_moved_by_user)
        self._apply_default_splitter_sizes()

        self._compact_tabs = QTabWidget()
        self._compact_tabs.setObjectName("compactTabs")
        self._compact_tabs.hide()

        outer.addWidget(self._splitter)
        self._compact = False
        self._update_compact_mode()

    def _build_actions(self) -> None:
        """One QAction per command, shared between the menu bar and the map
        header's segmented control (P2A/P4-4) so there is a single handler
        per command instead of duplicates. Window-wide (Qt.WindowShortcut,
        QAction's default context) so e.g. Ctrl+1 fires no matter which child
        widget inside the main window has focus (P2C)."""
        self._actions: dict[str, QAction] = {}

        def make(
            key: str,
            text: str,
            slot,
            shortcut: str | QKeySequence.StandardKey | None = None,
            extra_standard_key: QKeySequence.StandardKey | None = None,
        ) -> QAction:
            action = QAction(text, self)
            action.triggered.connect(slot)
            sequences: list[QKeySequence] = []
            seen: set[str] = set()
            for raw in (extra_standard_key, shortcut):
                if raw is None:
                    continue
                seq = QKeySequence(raw)
                if seq.isEmpty() or seq.toString() in seen:
                    continue
                seen.add(seq.toString())
                sequences.append(seq)
            if sequences:
                action.setShortcuts(sequences)
            self._actions[key] = action
            return action

        # Shared between the map header's segmented control and the View menu.
        make("Map", "Map", lambda: self._activate_view("map"), "Ctrl+1")
        make("Bands", "Bands", lambda: self._activate_view("bands"), "Ctrl+2")
        make("Log", "Log", lambda: self._activate_view("log"), "Ctrl+3")

        # P4: collapsible side panel -- checkable, shared with the header's
        # collapse button via _set_side_panel_visible.
        toggle_side_panel = QAction("Show side panel", self)
        toggle_side_panel.setCheckable(True)
        toggle_side_panel.setChecked(True)
        toggle_side_panel.setShortcut(QKeySequence("Ctrl+B"))
        toggle_side_panel.toggled.connect(self._set_side_panel_visible)
        self._actions["ShowSidePanel"] = toggle_side_panel

        # Explicit "Ctrl+," so this works on Windows/Linux too -- the
        # Preferences standard key only resolves to a real sequence on macOS.
        make(
            "Settings",
            "Settings",
            self._settings,
            "Ctrl+,",
            extra_standard_key=QKeySequence.StandardKey.Preferences,
        )

        # Menu-only commands; every one of these existed on the old toolbar or
        # its » overflow menu and must stay reachable from the menu bar.
        make("Export snapshot", "Export snapshot", self._export_json)
        make("Export DX CSV", "Export DX CSV", self._export_dx)
        make("Quit", "Quit", self._quit_app, QKeySequence.StandardKey.Quit)
        # Explicit F5 alongside the Refresh standard key: the two already
        # coincide on Windows/Linux, but this keeps F5 working even on
        # platforms where the standard key resolves elsewhere (e.g. macOS).
        make(
            "Refresh",
            "Refresh",
            self._auto_refresh,
            "F5",
            extra_standard_key=QKeySequence.StandardKey.Refresh,
        )
        make("Location", "Refresh Location", self.ctrl.refresh_location)
        make("Weather", "Refresh Weather", self._trigger_weather_refresh)
        # SPEC §6.1 "Plot becomes the Kp 24h sparkline plus 'Open plot…' in
        # View": the Stats/Plot tab bar is hidden (G4), so this is now Plot's
        # only visible entry point.
        make("OpenPlot", "Open plot…", self._open_plot_tab)
        make("Rig", "Rig Wizard…", self._rig_wizard)
        make("About", "About", self._about)
        make("Check for Updates", "Check for Updates", self._check_updates)

    def _build_menu_bar(self) -> None:
        """File/View/Tools/Help (P2A): every command that used to live on the
        old toolbar or its » overflow menu is reachable here. P4-4 removes
        the toolbar row entirely -- Map/Bands/Log move to the map header's
        segmented control (_build_view_switch) and Settings/Rig/About/etc.
        stay exactly where they already were, in these menus."""
        menu_bar = self.menuBar()

        menu_file = menu_bar.addMenu("&File")
        menu_file.setObjectName("menuFile")
        menu_file.addAction(self._actions["Export snapshot"])
        menu_file.addAction(self._actions["Export DX CSV"])
        menu_file.addSeparator()
        menu_file.addAction(self._actions["Quit"])

        menu_view = menu_bar.addMenu("&View")
        menu_view.setObjectName("menuView")
        menu_view.addAction(self._actions["Map"])
        menu_view.addAction(self._actions["Bands"])
        menu_view.addAction(self._actions["Log"])
        menu_view.addSeparator()
        menu_view.addAction(self._actions["ShowSidePanel"])
        menu_view.addSeparator()
        menu_view.addAction(self._actions["Refresh"])
        menu_view.addAction(self._actions["Location"])
        menu_view.addAction(self._actions["Weather"])
        menu_view.addSeparator()
        menu_view.addAction(self._actions["OpenPlot"])

        menu_tools = menu_bar.addMenu("&Tools")
        menu_tools.setObjectName("menuTools")
        menu_tools.addAction(self._actions["Settings"])
        menu_tools.addAction(self._actions["Rig"])

        menu_help = menu_bar.addMenu("&Help")
        menu_help.setObjectName("menuHelp")
        menu_help.addAction(self._actions["About"])
        menu_help.addAction(self._actions["Check for Updates"])

        menu_bar.setCornerWidget(self._build_status_corner(), Qt.Corner.TopRightCorner)

    def _build_status_corner(self) -> QWidget:
        """P4-3/G5: QMenuBar.setCornerWidget -- a coloured-dot cluster pill,
        a live UTC clock and a refresh button (SPEC §6.1/§6.2 "merged menu
        bar plus corner status"). G5/G6 finished the SPEC §6.2 "cluster only
        in the corner" consolidation the P4 round log deferred: the status
        bar's old duplicate cluster label is gone, so this corner pill is now
        the single place cluster state renders as text."""
        corner = QWidget()
        corner.setObjectName("statusCorner")
        layout = QHBoxLayout(corner)
        layout.setContentsMargins(0, 0, SPACE_2, 0)
        layout.setSpacing(SPACE_2)

        # Round 6 (SPEC §9 "At 683, the menu-bar corner shows SFI 142 Kp 3.0
        # A 12"): real values (never a sample), hidden above the 820px
        # side-panel-hidden breakpoint since the panel's own tiles already
        # show the same facts there -- additive alongside the existing
        # cluster/clock widgets below, not a relocation (same reasoning as
        # the P4-3 cluster-corner decision logged in an earlier round).
        self._corner_summary_lbl = QLabel("")
        self._corner_summary_lbl.setObjectName("statusCornerSummary")
        self._corner_summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._corner_summary_lbl.setVisible(False)
        self._corner_summary_visible = False
        layout.addWidget(self._corner_summary_lbl)

        self._corner_cluster_lbl = QLabel("Cluster disconnected")
        self._corner_cluster_lbl.setObjectName("statusCornerCluster")
        self._corner_cluster_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._corner_cluster_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        layout.addWidget(sep)

        self._corner_clock_lbl = QLabel("")
        self._corner_clock_lbl.setObjectName("statusCornerClock")
        layout.addWidget(self._corner_clock_lbl)

        # G5/SPEC §6.2 "[↻]" next to the UTC clock -- the same Refresh
        # QAction F5/the View menu already trigger, not a second handler.
        self._corner_refresh_btn = QToolButton()
        self._corner_refresh_btn.setObjectName("statusCornerRefresh")
        self._corner_refresh_btn.setText("↻")
        self._corner_refresh_btn.setAutoRaise(True)
        self._corner_refresh_btn.setToolTip("Refresh (F5)")
        self._corner_refresh_btn.clicked.connect(lambda: self._actions["Refresh"].trigger())
        layout.addWidget(self._corner_refresh_btn)
        self._tick_clock()
        # Keep a Python-side reference: QMenuBar.setCornerWidget takes visual
        # ownership but a local-only widget can otherwise get garbage
        # collected by shiboken once this method returns, deleting the C++
        # object (and its children) out from under the menu bar.
        self._status_corner = corner
        return corner

    def _tick_clock(self) -> None:
        """Minute-resolution UTC clock in the menu-bar corner (SPEC §6.1/§6.2).
        Real current time, not derived from any data feed -- matches the
        "UTC 13:46" mockup element, which the spec notes becomes a live clock
        rather than a static table row."""
        now = datetime.datetime.now(datetime.timezone.utc)
        self._corner_clock_lbl.setText(f"UTC {now.strftime('%H:%M')}")
        self._update_next_refresh_label()

    def _update_next_refresh_label(self) -> None:
        """G6/SPEC §6.2 "Next refresh 13:47:57": the real auto-refresh
        QTimer (self._timer) repeats on a fixed interval, so its own
        remainingTime() at any moment *is* the real countdown to the next
        scheduled fetch -- reading it rather than tracking a separate
        "last refreshed" stamp (that fact already lives in the space-weather
        panel's freshness header, G4). Ticks every 15s off the same timer as
        the menu-bar clock, plus once immediately whenever a refresh
        actually completes (_refresh_labels_and_map) so the countdown stays
        visibly in sync with the timer it reads."""
        timer = getattr(self, "_timer", None)
        lbl = getattr(self, "_status_refresh_lbl", None)
        if timer is None or lbl is None or not timer.isActive():
            return
        next_at = datetime.datetime.now() + datetime.timedelta(milliseconds=timer.remainingTime())
        lbl.setText(f"Next refresh {next_at.strftime('%H:%M:%S')}")

    def _build_status_bar(self) -> None:
        """Permanent status bar widgets (P2B): rig/CAT, DX cluster, last-refresh
        time and location source, so system health is visible without opening
        any dialog. Driven entirely by existing controller callbacks/signals
        via _UiInvoker -- nothing here polls serial/network on the UI thread."""
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)

        def make_left(object_name: str, text: str) -> QLabel:
            # Non-permanent widgets occupy QStatusBar's stretchy left region
            # (SPEC §6.2: "[○ Rig: not tested] [Location: not set] ...").
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            bar.addWidget(lbl)
            return lbl

        def make_right(object_name: str, text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName(object_name)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            bar.addPermanentWidget(lbl)
            return lbl

        # G6: the old "Greyline @ ..." subtitle and "Cluster: ..." label are
        # gone from here -- both are real duplicates now that the map header
        # shows the greyline caption directly (G3) and the menu-bar corner
        # shows cluster state with a coloured dot (G5).
        self._status_rig_lbl = make_left("statusRig", f'<span style="color:{MUTED}">●</span> Rig: not tested')
        self._status_location_lbl = make_left("statusLocation", "Location: not set")
        self._status_refresh_lbl = make_right("statusRefresh", "Next refresh --:--:--")

    def _set_rig_status(self, ok: bool, detail: str) -> None:
        """Updates the status bar's rig/CAT indicator. Driven by Test CAT
        (Settings dialog and Rig Wizard) and by tuning a frequency from the
        map -- the only places the app actually talks to the rig."""
        color = OK if ok else ERR
        self._status_rig_lbl.setText(f'<span style="color:{color}">●</span> Rig: {detail}')

    def _set_side_panel_visible(self, visible: bool) -> None:
        """Handler for the View menu's "Show side panel" action/Ctrl+B (P4;
        Round 6/SPEC §13 "W<820: side panel hidden ... Ctrl+B opens it"; G3:
        the header's own ">>"/"<<" collapse button these used to also sync is
        gone, so Ctrl+B/the menu action are the only entry points now): in
        the wide/splitter layout this hides/shows the pane directly; in
        compact mode (where the side pane is one of _compact_tabs' two pages
        rather than a splitter child) it instead switches the visible tab.
        Defensively tolerant of running before the widgets it syncs exist yet
        (QAction.setChecked during _build_actions can fire this once, before
        the splitter is built)."""
        self._side_panel_visible = visible
        side_pane = getattr(self, "_side_pane", None)
        if side_pane is not None:
            if getattr(self, "_compact", False):
                compact_tabs = getattr(self, "_compact_tabs", None)
                if compact_tabs is not None and compact_tabs.indexOf(side_pane) != -1:
                    compact_tabs.setCurrentWidget(side_pane if visible else self._map_tab)
            else:
                side_pane.setVisible(visible)
        action = getattr(self, "_actions", {}).get("ShowSidePanel")
        if action is not None and action.isChecked() != visible:
            action.blockSignals(True)
            action.setChecked(visible)
            action.blockSignals(False)

    def _open_plot_tab(self) -> None:
        """View menu "Open plot…" (SPEC §6.1): the Stats/Plot tab bar is
        hidden (G4), so this -- not a visible tab click -- is now the real
        entry point to the Plot tab's history chart. Ensures the side panel
        is actually visible first (wide-splitter or compact-tab layout
        alike), the same way _focus_panel's "log"/"bands" branches do."""
        if self._compact:
            self._compact_tabs.setCurrentWidget(self._side_pane)
        else:
            self._set_side_panel_visible(True)
        self.tabs.setCurrentWidget(self._plot_tab)

    def _focus_panel(self, which: str) -> None:
        """Focus/raise Map, Bands or Log, in both wide (splitter) and compact
        (tab) layouts (P2A). In the wide layout, band_panel lives under the
        map (SPEC §6.2/§8) so it's reached the same way "map" is; in compact
        mode it moves back into the side panel (see _enter_compact_mode), so
        there it's reached the same way "log" is instead."""
        if which == "map":
            if self._compact:
                self._compact_tabs.setCurrentWidget(self._map_tab)
            self.map_widget.setFocus()
            return
        if which == "bands" and not self._compact:
            self.band_panel.setFocus()
            return
        if self._compact:
            self._compact_tabs.setCurrentWidget(self._side_pane)
        if which == "bands":
            self._side_scroll.ensureWidgetVisible(self.band_panel)
            self.band_panel.setFocus()
        elif which == "log":
            self.tabs.setCurrentWidget(self._stats_tab)
            self._side_scroll.ensureWidgetVisible(self.alerts_list)
            self.alerts_list.setFocus()

    def controls_reachable(self) -> dict[str, bool]:
        """Every tracked command is reachable as long as the menu bar itself
        is shown (P4-4: there is no toolbar any more, so this no longer has
        a separate toolbar-widget-visibility branch). Map/Bands/Log are also
        reachable via the map header's segmented control, but the menu bar
        alone is already sufficient for every entry in self._actions."""
        menu_bar_visible = self.menuBar().isVisible()
        return {
            name: menu_bar_visible and action.isVisible() and action.isEnabled()
            for name, action in self._actions.items()
        }

    def hscroll_visible(self) -> bool:
        """M1: whether any scroll area inside the main window currently shows a
        horizontal scrollbar (there should never be one)."""
        return _main_window_hscroll_visible(self)

    def _populate_cluster_combo(self) -> None:
        self.cluster_combo.blockSignals(True)
        self.cluster_combo.clear()
        nodes = self.ctrl.cfg.get("dx_cluster_nodes") or []
        current_host = self.ctrl.cfg.get("dx_cluster_host", "")
        select_idx = 0
        for i, node in enumerate(nodes):
            label = f"{node.get('name', '?')} ({node.get('host')}:{node.get('port', 23)})"
            self.cluster_combo.addItem(label, node)
            if node.get("host") == current_host:
                select_idx = i
        if not nodes:
            self.cluster_combo.addItem(
                f"Custom ({current_host})", {"host": current_host, "port": self.ctrl.cfg.get("dx_cluster_port", 23)}
            )
        else:
            self.cluster_combo.setCurrentIndex(select_idx)
        self.cluster_combo.blockSignals(False)

    def _cluster_node_changed(self, index: int) -> None:
        if index < 0:
            return
        node = self.cluster_combo.itemData(index)
        if not node:
            return
        self.ctrl.cfg.set("dx_cluster_host", node.get("host"))
        self.ctrl.cfg.set("dx_cluster_port", int(node.get("port", 23)))
        self.ctrl.stop()
        self.ctrl.start()
        self._set_status(f"Cluster → {node.get('name', node.get('host'))}")

    def _load_map(self) -> None:
        """F7: the basemap PIL load + LANCZOS scale is real CPU work (cold-start
        cost measured ~185ms); never do it on the UI thread. Show the renderer's
        placeholder immediately so first paint/menu chrome is never blocked, then
        swap in the real basemap once a daemon thread finishes loading it."""
        from orbitrx.paths import ensure_map_image

        self._map_label = "Map · loading"
        self.renderer.set_base_map(None)
        self.map_widget.set_base_map(self.renderer.base_rgba_image())

        on_loaded = self._ui.wrap(self._on_map_loaded)
        on_failed = self._ui.wrap(self._on_map_load_failed)

        def worker() -> None:
            try:
                map_path = ensure_map_image()
                if not map_path.is_file():
                    raise FileNotFoundError(f"{map_path.name} not found at {map_path}")
                img = Image.open(map_path)
                img.load()
                scaled = self.renderer.prepare_base_map(img)
                # F7: QImage has no GUI-thread affinity (unlike QPixmap), so the
                # byte-level conversion is also safe to do here, off the UI
                # thread; only the cheap QPixmap wrap + scene assignment is
                # left for _on_map_loaded.
                qimage = _pil_to_qimage(scaled)
            except Exception as exc:
                on_failed(exc)
            else:
                on_loaded(scaled, qimage)

        self._map_load_thread = threading.Thread(target=worker, daemon=True, name="map-load")
        self._map_load_thread.start()

    def _on_map_loaded(self, scaled_image, qimage) -> None:
        self.renderer.set_prescaled_base_map(scaled_image)
        self.map_widget.set_base_map_from_qimage(qimage)
        # M1: never print the asset filename in the UI.
        self._map_label = "Map · offline basemap"

    def _on_map_load_failed(self, exc: Exception) -> None:
        self.renderer.set_base_map(None)
        if hasattr(self.map_widget, "set_base_map"):
            self.map_widget.set_base_map(self.renderer.base_rgba_image())
        self._map_label = f"Map FAILED: {exc}"
        self.banner.setText(self._map_label)
        self.banner.setProperty("state", "error")
        self.banner.style().polish(self.banner)
        self._toasts.show_toast(f"Map failed to load: {exc}", kind="error")

    def _current_layers(self) -> MapLayers:
        return MapLayers(
            greyline=self._layer_checks["greyline"].isChecked(),
            night=self._layer_checks["night"].isChecked(),
            dx_arcs=self._layer_checks["dx_arcs"].isChecked(),
            aurora=self._layer_checks["aurora"].isChecked(),
            grid=self._layer_checks["grid"].isChecked(),
        )

    def _replay_moved(self, val: int) -> None:
        # F10: the label updates immediately; the (heavier) live-spots refresh
        # is throttled to <=10Hz while dragging, same mechanism as the time
        # slider below.
        self.lbl_replay.setText(format_replay_offset(val))
        if self._replay_refresh_timer.isActive():
            self._replay_refresh_pending = True
            return
        self._refresh_live_spots()
        self._replay_refresh_timer.start(80)

    def _replay_refresh_cooldown(self) -> None:
        if self._replay_refresh_pending:
            self._replay_refresh_pending = False
            self._refresh_live_spots()
            self._replay_refresh_timer.start(80)

    def _refresh_live_spots(self) -> None:
        from orbitrx.spots.geo import arcs_payload, heatmap_payload

        val = self.replay_slider.value() if hasattr(self, "replay_slider") else 0
        spots = self.ctrl.spots.snapshot() if val == 0 else self.ctrl.spots.replay(float(val))
        live_on = self._layer_checks["spot_arcs"].isChecked() or self._layer_checks["spot_heatmap"].isChecked()
        if hasattr(self.map_widget, "set_live_spots"):
            self.map_widget.set_live_spots({
                "arcs": self._layer_checks["spot_arcs"].isChecked(),
                "heatmap": self._layer_checks["spot_heatmap"].isChecked(),
                "spots": arcs_payload(spots),
                "heat": heatmap_payload(spots),
            })
        if hasattr(self.map_widget, "set_empty_overlay"):
            self.map_widget.set_empty_overlay(format_no_spots_message(val) if live_on and not spots else "")
        err = self.ctrl.spots.last_error
        if err:
            self._set_status("Live spots offline: PSKReporter unreachable, showing cached data")
        elif val:
            self._set_status(f"Replaying {len(spots)} cached spots")

    def _about(self) -> None:
        from orbitrx.ui.about import show_about
        show_about(self)

    def _refresh_map(self, vectors_only: bool = False) -> None:
        spots, coords = self.ctrl.get_spots_snapshot()
        self.map_widget.set_layers(self._current_layers())
        self.map_widget.update_scene(
            self.ctrl.state, spots, coords, vectors_only=vectors_only
        )
        if not vectors_only:
            self._refresh_live_spots()

    def _refresh_labels_and_map(self) -> None:
        labels = self.ctrl.weather_labels()
        # M4: row caption lives in the form label; strip duplicated "Key: " prefixes.
        strip_map = {
            "kp_forecast": "Kp Forecast: ", "solar": "Solar Flux: ",
            "sunspot": "Sunspot: ", "solar_wind": "Solar wind: ", "bz": "Bz: ",
            "bands": "Bands: ", "muf": "MUF: ", "luf": "LUF: ",
            "path_muf": "Path MUF: ", "sunrise": "Sunrise: ", "sunset": "Sunset: ",
            "location": "You: ",
        }
        for k, v in labels.items():
            if k in self._labels:
                prefix = strip_map.get(k)
                if prefix and v.startswith(prefix):
                    v = v[len(prefix):]
                self._labels[k].setText(v)
        self._refresh_key_tiles()
        self._freshness_lbl.setText(self._space_weather_freshness_text())
        self._update_location_hint_visibility()
        self._weather_never_loaded_lbl.setVisible(self.ctrl.state.last_weather_update is None)
        self.alerts_list.clear()
        for alert in self.ctrl.state.alerts[:5] or ["No active alerts"]:
            item = QListWidgetItem(humanize_iso_dates(alert))
            item.setToolTip(humanize_iso_dates(alert))
            self.alerts_list.addItem(item)
        self._render_cluster_label()
        self.band_panel.update_grid(self.ctrl.state.band_grid)
        # P2B/G6: "whenever data refresh completes" -- on_weather and on_dx
        # are both wired to this same method, so this covers both triggers.
        # The status bar's right-hand label is the *next* scheduled refresh
        # (SPEC §6.2 "Next refresh 13:47:57"), computed from the real
        # self._timer's own remaining time -- not a "last refreshed at" stamp
        # (that info already lives in the space-weather panel's freshness
        # header, G4), so a completed refresh just re-syncs this to the
        # timer's freshly-restarted countdown.
        self._update_next_refresh_label()
        location_source = self.ctrl.state.location_source
        loc_text = f"Location: {LOCATION_SOURCE_LABELS.get(location_source, 'not set')}"
        if location_source == "unset":
            loc_text = f'<span style="color:{FAIR}">{loc_text}</span>'
        self._status_location_lbl.setText(loc_text)
        self._schedule_map_rebuild()
        self._refresh_kp_sparkline()

    def _refresh_key_tiles(self) -> None:
        """SPEC §9 item 2: SFI/Kp/A-index tiles, gated as a whole on "has the
        first successful fetch happened yet" (not field-by-field None checks)
        so the never-loaded state shows NO_DATA on every tile at once, the
        same way states-sheet.png's "Never updated" panel does."""
        s = self.ctrl.state
        loaded = s.last_weather_update is not None
        self._kpi_labels["sfi"].setText(format_value(s.flux, fmt="{:.1f}") if loaded else NO_DATA)
        # SPEC §9's tile has no room for the trend arrow/word the old grouped
        # "SPACE WEATHER" row showed next to flux -- rather than dropping that
        # real information outright, it survives as the tile's tooltip.
        self._kpi_labels["sfi"].setToolTip(f"Trend: {s.flux_trend}" if loaded and s.flux_trend else "")
        self._kpi_labels["kp"].setText(format_value(s.kp_index, fmt="{:.1f}") if loaded else NO_DATA)
        self._kpi_labels["a_index"].setText(format_value(s.a_index, fmt="{:g}") if loaded else NO_DATA)
        if self._kp_caption_lbl is None:
            return
        if not loaded:
            self._kp_caption_lbl.setText("Kp")
            return
        word, token = kp_state(s.kp_index)
        color = {"GOOD": GOOD, "FAIR": FAIR, "POOR": POOR}[token]
        self._kp_caption_lbl.setText(f'Kp &middot; <span style="color:{color}">{word}</span>')
        self._update_control_strip_corner_summary()

    # Round 6 (SPEC §9 "At 683"/§13 "W<820"): corner space-weather summary.
    _CORNER_SUMMARY_BELOW = 820
    _CORNER_SUMMARY_ABOVE = 836

    def _corner_summary_text(self) -> str:
        """Real SFI/Kp/A-index values -- NO_DATA before the first fetch,
        same gate _refresh_key_tiles uses, never a sample like the mockup's
        'SFI 142 Kp 3.0 A 12'."""
        s = self.ctrl.state
        loaded = s.last_weather_update is not None
        sfi = format_value(s.flux, fmt="{:.1f}") if loaded else NO_DATA
        kp = format_value(s.kp_index, fmt="{:.1f}") if loaded else NO_DATA
        a_index = format_value(s.a_index, fmt="{:g}") if loaded else NO_DATA

        def pair(label: str, value: str) -> str:
            return (
                f'<span style="color:{TEXT_TERTIARY}">{label}</span> '
                f'<span style="font-family:\'{FONT_MONO}\'; color:{TEXT_SECONDARY}">{value}</span>'
            )

        return "&nbsp;&nbsp;".join([pair("SFI", sfi), pair("Kp", kp), pair("A", a_index)])

    def _apply_corner_summary_visible(self, visible: bool) -> None:
        if self._corner_summary_visible == visible:
            return
        self._corner_summary_visible = visible
        self._corner_summary_lbl.setVisible(visible)

    def _update_control_strip_corner_summary(self) -> None:
        lbl = getattr(self, "_corner_summary_lbl", None)
        if lbl is None:
            return
        lbl.setText(self._corner_summary_text())
        width = self.width()
        if width < self._CORNER_SUMMARY_BELOW:
            self._apply_corner_summary_visible(True)
        elif width > self._CORNER_SUMMARY_ABOVE:
            self._apply_corner_summary_visible(False)

    # Round 6 (SPEC §8/§13 "Compact variant (683, or a window height under
    # 560)"): band-chip compact threshold, same ±16px hysteresis idiom.
    _BAND_CHIP_COMPACT_HEIGHT_BELOW = 560
    _BAND_CHIP_COMPACT_HEIGHT_ABOVE = 576

    # Round 6 (SPEC §13 "H < 560: ... Menu bar 28, status bar 22, map header
    # 32, controls 28", plus "Window gutters: 16px at 1280, 8px at 683"):
    # same ±16px hysteresis idiom as every other breakpoint in this file.
    _COMPACT_CHROME_HEIGHT_BELOW = 560
    _COMPACT_CHROME_HEIGHT_ABOVE = 576

    def _update_compact_chrome(self) -> None:
        """Shrinks the chrome rows above/around the map -- not the map
        itself -- so more of a short window's client height goes to the map
        frame (Round 5 measured the 683x485 map share short of SPEC's 55%
        target because this app's compact chrome ate more height than
        SPEC's own budget table assumed; this directly answers that gap).
        Only ever touches heights/margins, never widget *identity* -- every
        control stays the same QToolButton/QSlider/QComboBox it always was,
        just shorter."""
        compact = getattr(self, "_compact_chrome", False)
        height = self.height()
        if height < self._COMPACT_CHROME_HEIGHT_BELOW:
            compact = True
        elif height > self._COMPACT_CHROME_HEIGHT_ABOVE:
            compact = False
        if compact == getattr(self, "_compact_chrome", None):
            return
        self._compact_chrome = compact

        self.menuBar().setFixedHeight(MENU_BAR_HEIGHT_COMPACT if compact else MENU_BAR_HEIGHT)
        self.statusBar().setFixedHeight(STATUS_BAR_HEIGHT_COMPACT if compact else STATUS_BAR_HEIGHT)
        # The header row's own wrapper is floored at its target height
        # directly -- its children (segButton/combo/help chip) already fit
        # comfortably inside 32px, so there's no need to also shrink their
        # own min-height/padding the way the control-strip toggles below do.
        # Round 10 (p4-r11): a floor via setMinimumHeight, not setFixedHeight
        # -- this row can now stack onto two lines under width pressure (see
        # its _MapControlStrip wrapping above), and a hard Fixed height would
        # clip that second line instead of letting the row grow to fit it.
        target_header_height = MAP_HEADER_HEIGHT_COMPACT if compact else MAP_HEADER_HEIGHT
        self._map_header_row.setMinimumHeight(target_header_height)
        self._map_header_row.setMaximumHeight(16777215)
        gutter = GUTTER_COMPACT if compact else GUTTER_WIDE
        self._map_tab_layout.setContentsMargins(gutter, 0, gutter, 0)

        # The control strip has no single wrapper to force-shrink (clipping
        # content instead of actually reclaiming height) -- each toggle's
        # own `compact` property drives a smaller QSS min-height/padding,
        # which genuinely shrinks sizeHint() so the row/col layout holding
        # them actually reserves less space, not just leaves dead space
        # around a visually-smaller (but still geometrically unchanged)
        # button.
        strip_controls = [*self._layer_checks.values(), self._layers_menu_btn, self._time_popover_btn]
        for widget in strip_controls:
            if widget.property("compact") == compact:
                continue
            widget.setProperty("compact", compact)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.updateGeometry()

    def _update_band_panel_compact(self) -> None:
        panel = getattr(self, "band_panel", None)
        if panel is None:
            return
        height = self.height()
        band_compact = getattr(self, "_band_chip_height_compact", False)
        if height < self._BAND_CHIP_COMPACT_HEIGHT_BELOW:
            band_compact = True
        elif height > self._BAND_CHIP_COMPACT_HEIGHT_ABOVE:
            band_compact = False
        self._band_chip_height_compact = band_compact
        panel.set_compact(self._compact or band_compact)

    def _space_weather_freshness_text(self) -> str:
        """SPEC §9 item 1 / §10: a real freshness stamp driven entirely by
        the controller's actual fetch state, never a sample timestamp."""
        s = self.ctrl.state
        if s.weather_fetch_in_progress:
            return "Refreshing…"
        if s.last_weather_update is None and s.last_weather_success_update is None:
            return "Never updated"
        if not s.weather_last_fetch_ok and s.last_weather_success_update is not None:
            return f"Stale · {s.last_weather_success_update.strftime('%H:%M')}"
        if s.last_weather_update is not None:
            return f"Updated {s.last_weather_update.strftime('%H:%M')}"
        return "Never updated"

    def _trigger_weather_refresh(self) -> None:
        """Every UI entry point that kicks off a weather fetch goes through
        here instead of calling ctrl.fetch_weather() directly, so the header
        freshness stamp flips to "Refreshing…" immediately -- fetch_weather()
        sets state.weather_fetch_in_progress synchronously before handing the
        actual network call to its worker thread, so this read-back is safe
        and never blocks."""
        self.ctrl.fetch_weather()
        self._freshness_lbl.setText(self._space_weather_freshness_text())

    def _on_path_toggled(self, checked: bool) -> None:
        self._path_body.setVisible(checked)
        self._path_toggle_btn.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def _refresh_kp_sparkline(self) -> None:
        """P4-7: the last-24h Kp sparkline is built only from real sqlite
        rows (DataStore.query_propagation), queried on a worker thread --
        never on the UI thread (P1 pattern, same shape as _refresh_plot_tab).
        parse_history_query only splits "date:date" ranges (not full ISO
        timestamps on both sides), so this queries a padded calendar-day
        window and filters to the exact last 24h on the worker thread before
        handing rows back."""
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(hours=24)
        query = (
            f"{(start.date() - datetime.timedelta(days=1)).isoformat()}:"
            f"{(now.date() + datetime.timedelta(days=1)).isoformat()}"
        )
        on_done = self._ui.wrap(self._on_kp_sparkline_ready)

        def worker() -> None:
            try:
                rows = self.ctrl.store.query_propagation(query)
            except ValueError:
                rows = []
            values = []
            for row in rows:
                kp = row.get("kp")
                ts = row.get("ts")
                if kp is None or ts is None:
                    continue
                try:
                    when = datetime.datetime.fromisoformat(ts)
                except ValueError:
                    continue
                if start <= when <= now:
                    values.append(float(kp))
            on_done(values)

        self._sparkline_query_thread = threading.Thread(
            target=worker, daemon=True, name="kp-sparkline-query"
        )
        self._sparkline_query_thread.start()

    def _on_kp_sparkline_ready(self, values: list[float]) -> None:
        self._kp_sparkline.set_rows(values)

    def _schedule_map_rebuild(self, vectors_only: bool = False) -> None:
        # P1: weather refreshes and DX spot arrivals share this debounce (same
        # pattern as _slider_moved/_replay_moved above) so a burst of either
        # triggers at most one extra rebuild instead of one dispatch per event.
        # A full rebuild requested anywhere in the burst wins over a vectors-only
        # one, so a pending full redraw is never downgraded.
        if self._map_rebuild_timer.isActive():
            if self._map_rebuild_pending:
                self._map_rebuild_pending_vectors_only = self._map_rebuild_pending_vectors_only and vectors_only
            else:
                self._map_rebuild_pending = True
                self._map_rebuild_pending_vectors_only = vectors_only
            return
        self._refresh_map(vectors_only=vectors_only)
        self._map_rebuild_timer.start(80)

    def _map_rebuild_cooldown(self) -> None:
        if self._map_rebuild_pending:
            self._map_rebuild_pending = False
            self._refresh_map(vectors_only=self._map_rebuild_pending_vectors_only)
            self._map_rebuild_timer.start(80)

    def _layers_changed(self) -> None:
        # F8: the chip itself already flipped (native QToolButton paint, before
        # this slot even runs) so visual feedback is immediate. The redraw stays
        # synchronous (cheap, ~2-21ms measured) but the disk write is deferred:
        # cfg.save() can spike under Windows AV scanning, so rapid toggles are
        # coalesced into a single debounced save of the final mask rather than
        # one write per click.
        ml = {k: cb.isChecked() for k, cb in self._layer_checks.items()}
        self.ctrl.cfg.data["map_layers"] = ml
        self._refresh_map()
        self._schedule_layers_save()
        self._update_layers_menu_badge()

    def _build_layers_menu_button(self) -> QToolButton:
        """SPEC §11 "At 683": Layers collapses to a QToolButton#layersMenuButton
        with InstantPopup, a checkable QMenu, and a count badge. The menu's
        QActions are proxies, not a second source of truth -- toggling one
        just flips the real _layer_checks[key] QToolButton (already wired to
        _layers_changed), and _sync_layers_menu() (on the menu's aboutToShow)
        pulls the actions back into sync with the real buttons so the badge
        and checkmarks can never drift from the state that actually drives
        the map."""
        btn = QToolButton()
        btn.setObjectName("layersMenuButton")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        self._layers_menu_actions: dict[str, QAction] = {}
        for key, label in self._LAYER_GROUP_ITEMS:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, k=key: self._layer_checks[k].setChecked(checked))
            menu.addAction(action)
            self._layers_menu_actions[key] = action
        menu.aboutToShow.connect(self._sync_layers_menu)
        btn.setMenu(menu)
        self._layers_menu_btn_ref = btn
        self._sync_layers_menu()  # QAction defaults to unchecked; match the real buttons from the start
        self._update_layers_menu_badge()
        return btn

    def _sync_layers_menu(self) -> None:
        for key, action in self._layers_menu_actions.items():
            checked = self._layer_checks[key].isChecked()
            if action.isChecked() != checked:
                action.blockSignals(True)
                action.setChecked(checked)
                action.blockSignals(False)

    def _update_layers_menu_badge(self) -> None:
        btn = getattr(self, "_layers_menu_btn_ref", None)
        if btn is None:
            return
        count = sum(1 for k, _ in self._LAYER_GROUP_ITEMS if self._layer_checks[k].isChecked())
        btn.setText(f"Layers {count} ▾")

    def _apply_layers_compact(self, compact: bool) -> None:
        """SPEC §11 "At 683": the Layers label+group swap for the
        #layersMenuButton; Spots (built separately in _build_ui) is never
        touched here -- it "stay[s] inline" at every width."""
        if getattr(self, "_layers_compact", None) == compact:
            return
        self._layers_compact = compact
        self._layers_label.setVisible(not compact)
        self._layers_group.setVisible(not compact)
        self._layers_menu_btn.setVisible(compact)
        if compact:
            self._update_layers_menu_badge()

    def _apply_sliders_compact(self, compact: bool) -> None:
        """SPEC §11 "At 683" "the sliders shrink to 84px"."""
        width = SLIDER_WIDTH_COMPACT if compact else SLIDER_WIDTH
        self.time_slider.setFixedWidth(width)
        self.replay_slider.setFixedWidth(width)

    def _apply_time_popover(self, popover: bool) -> None:
        """SPEC §11 "Below 600 px width, the time sliders move into a 'Time
        ▾' popover" -- reparents the single real _time_box (both sliders)
        between the inline sliders row and the popover menu's QWidgetAction,
        the same reparent-don't-duplicate pattern _MapControlStrip already
        uses for chips/sliders between its row/stacked pages."""
        if getattr(self, "_time_popover", None) == popover:
            return
        self._time_popover = popover
        if popover:
            self._sliders_row_layout.removeWidget(self._time_box)
            self._time_popover_btn.menu().actions()[0].setDefaultWidget(self._time_box)
            self._sliders_row_layout.addWidget(self._time_popover_btn)
            self._time_popover_btn.setVisible(True)
        else:
            self._sliders_row_layout.removeWidget(self._time_popover_btn)
            self._time_popover_btn.setParent(None)
            self._time_popover_btn.setVisible(False)
            self._sliders_row_layout.addWidget(self._time_box)
        self._time_box.setVisible(True)

    def _schedule_layers_save(self) -> None:
        if self._layers_save_timer is None:
            self._layers_save_timer = QTimer(self)
            self._layers_save_timer.setSingleShot(True)
            self._layers_save_timer.timeout.connect(self.ctrl.cfg.save)
        self._layers_save_timer.start(400)

    def _flush_layers_save(self) -> None:
        if self._layers_save_timer is not None and self._layers_save_timer.isActive():
            self._layers_save_timer.stop()
            self.ctrl.cfg.save()

    def _slider_moved(self, val: int) -> None:
        # F10: thumb/label update is immediate (cheap); the full map+live-spots
        # redraw is throttled to <=10Hz (80ms) while dragging so a fast drag
        # doesn't fire one full redraw per pixel of mouse movement. The first
        # move in a burst still redraws immediately, and a trailing redraw
        # always runs right after the last move/release so the final position
        # settles well within the design's 300ms budget.
        self.ctrl.state.slider_offset_hours = float(val)
        self.lbl_slider.setText(format_hour_offset(val))
        if self._slider_refresh_timer.isActive():
            self._slider_refresh_pending = True
            return
        self._refresh_map()
        self._slider_refresh_timer.start(80)

    def _slider_refresh_cooldown(self) -> None:
        if self._slider_refresh_pending:
            self._slider_refresh_pending = False
            self._refresh_map()
            self._slider_refresh_timer.start(80)

    def _on_map_click(self, x: float, y: float) -> None:
        self.click_lbl.setText(self.ctrl.map_click_latlon(x, y, self.renderer))

    def _tune_from_map(self, freq: float) -> None:
        def confirm(msg: str) -> bool:
            return QMessageBox.question(self, "CAT", msg) == QMessageBox.StandardButton.Yes
        result = self.ctrl.tune_radio(freq, confirm if self.ctrl.cfg.get("cat_confirm_before_tune") else None)
        if result != "cancelled":
            ok = "Sent CAT" in result
            self._set_rig_status(ok, result if ok else "tune failed")
        QMessageBox.information(self, "CAT", result)

    def _set_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def _on_controller_error(self, message: str) -> None:
        self._toasts.show_toast(message, kind="error")

    def _set_cluster(self, status: str) -> None:
        was_connected = self.ctrl.state.cluster_status == "connected"
        self.ctrl.state.cluster_status = status
        self._render_cluster_label()
        if status == "reconnecting" and was_connected:
            self._toasts.show_toast("DX cluster disconnected, reconnecting…", kind="warning")

    def _tick_cluster_pulse(self) -> None:
        self._cluster_pulse_phase = not self._cluster_pulse_phase
        if self.ctrl.state.cluster_status == "connected":
            self._render_cluster_label()

    def _current_cluster_node_name(self) -> str:
        """G5: the corner pill's connected text names the real node (e.g.
        "VE7CC connected"), not a generic "Cluster: connected" -- pulled from
        the same cluster_combo data _populate_cluster_combo already built
        from the real config, never a sample name."""
        combo = getattr(self, "cluster_combo", None)
        data = combo.currentData() if combo is not None else None
        if isinstance(data, dict) and data.get("name"):
            return str(data["name"])
        host = self.ctrl.cfg.get("dx_cluster_host", "")
        return host or "Cluster"

    def _render_cluster_label(self) -> None:
        """G5/SPEC §6.2: the menu-bar corner pill is the one place cluster
        state is rendered as text now -- the status bar's old duplicate
        label is gone (G6) and the OPS card's copy is gone (G4)."""
        status = self.ctrl.state.cluster_status
        if status == "connected":
            dot_color = "#81C784" if self._cluster_pulse_phase else "#2E7D32"
            phrase = f"{self._current_cluster_node_name()} connected"
        else:
            dot_color = FAIR if status == "connecting" else ERR if status == "reconnecting" else MUTED
            phrase = f"Cluster {status}"
        if hasattr(self, "_corner_cluster_lbl"):
            self._corner_cluster_lbl.setText(f'<span style="color:{dot_color}">●</span> {phrase}')
        # G3/SPEC §6.1/§11: the header's cluster combo leads with a status
        # dot in the same real cluster_status colour as the corner text
        # above, not a static glyph.
        if hasattr(self, "_cluster_dot_lbl"):
            self._cluster_dot_lbl.setStyleSheet(f"color: {dot_color};")
        # P4-8 (SPEC §10): the map's own "Cluster disconnected" pill, driven
        # by the same real cluster_status the corner/status-bar labels use --
        # "disconnected" (never started, or deliberately dropped) and
        # "reconnecting" (lost a live connection) both mean there is no
        # working cluster feed right now; "connecting" (first attempt) is
        # not flagged here, since it isn't a failure yet.
        if hasattr(self.map_widget, "set_cluster_pill"):
            self.map_widget.set_cluster_pill(
                "Cluster disconnected" if status in ("disconnected", "reconnecting") else ""
            )

    def _update_location_hint_visibility(self) -> None:
        """M5: path_muf/sunrise/sunset only mean anything once a location is set;
        otherwise show the single explanatory line instead of three no-data rows."""
        has_location = self.ctrl.state.user_lat is not None and self.ctrl.state.user_lon is not None
        for key in ("path_muf", "sunrise", "sunset", "location"):
            if key in self._labels:
                self._labels[key].setVisible(has_location)
            # Grid rows (unlike QFormLayout's addRow) don't auto-hide their
            # caption label when the value is hidden, so toggle both.
            if key in self._stat_name_labels:
                self._stat_name_labels[key].setVisible(has_location)
        self._location_hint_lbl.setVisible(not has_location)
        self._path_hint_lbl.setVisible(not has_location)

    def _spot_beep(self, spot: dict) -> None:
        self.ctrl.spot_beep(spot)
        self._schedule_map_rebuild(vectors_only=True)

    def _alarm_excellent(self) -> None:
        # Non-modal: a queued alarm must never spin a nested event loop (that
        # aborted headless CI when the alarm arrived while a window was closing).
        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return
        except ImportError:
            pass
        box = QMessageBox(
            QMessageBox.Icon.Information, "Propagation Alarm",
            f"Excellent conditions! Kp {self.ctrl.state.kp_index}  MUF {self.ctrl.state.muf} MHz",
            QMessageBox.StandardButton.Ok, self,
        )
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def _alarm_storm(self) -> None:
        QMessageBox.warning(self, "Storm Warning", f"Geomagnetic storm: Kp {self.ctrl.state.kp_index}")

    def _startup(self) -> None:
        self.ctrl.refresh_location()
        self._trigger_weather_refresh()
        self._refresh_labels_and_map()
        elapsed_ms = (time.perf_counter() - self._t_init_start) * 1000
        self.ctrl.log.info("perf: cold_start_to_startup_complete_ms=%.1f", elapsed_ms)

    def _auto_refresh(self) -> None:
        self.ctrl.state.prune_dx_spots()
        self.ctrl.refresh_location()
        self._trigger_weather_refresh()

    def _check_updates(self) -> None:
        # check_github_release does a blocking network call (10s timeout) --
        # never run it on the UI thread, or a slow/unreachable GitHub freezes
        # the whole window for up to that long.
        on_done = self._ui.wrap(self._show_update_available)
        on_error = self._ui.wrap(self._on_update_check_error)

        def worker() -> None:
            info = check_github_release(__version__)
            if info.get("update_available"):
                on_done(info)
            elif info.get("error"):
                # Previously silent: a failed check never told the user anything.
                on_error(info.get("message") or "could not reach GitHub")

        # Stored so capture-process teardown can join it before deleting any
        # Qt object the finished callback might otherwise reach into.
        self._update_check_thread = threading.Thread(target=worker, daemon=True, name="update-check")
        self._update_check_thread.start()

    def _show_update_available(self, info: dict) -> None:
        QMessageBox.information(
            self, "Update Available",
            f"{info['message']}\n\nDownload: {info['url']}",
        )

    def _on_update_check_error(self, message: str) -> None:
        self._toasts.show_toast(f"Update check failed: {message}", kind="warning")

    def _export_json(self) -> None:
        try:
            p = self.ctrl.export_json()
        except Exception as e:
            self._toasts.show_toast(f"Export failed: {e}", kind="error")
            return
        QMessageBox.information(self, "Export", f"Saved {p}")

    def _export_dx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export DX", "dx_spots.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self.ctrl.store.export_dx_csv(Path(path))
        except Exception as e:
            self._toasts.show_toast(f"Export failed: {e}", kind="error")
            return
        QMessageBox.information(self, "Export", f"Saved {path}")

    def _rig_wizard(self) -> None:
        dlg = RigWizardDialog(self.ctrl.cfg, self.ctrl.cat, self, on_rig_status=self._set_rig_status)
        dlg.exec()

    def _refresh_plot_tab(self) -> None:
        # P1/regression: only the sqlite query (potentially slow on a long date
        # range) runs on a worker thread. matplotlib is not thread-safe -- its
        # FreeType font cache can crash if two threads touch it at once, or if
        # a worker builds a Figure while the UI thread is doing anything else
        # with matplotlib (e.g. test teardown's plt.close("all")) -- so the
        # Figure build (_build_history_figure, including tight_layout) always
        # runs on the UI thread below, never on the worker. A generation
        # counter drops a result superseded by a newer Refresh/date change
        # before it ever reaches the UI.
        if not PLOT_QT:
            self.plot_placeholder.setText("matplotlib Qt backend required")
            return
        q = self.hist_date.date().toString("yyyy-MM-dd")
        poll_interval_s = float(self.ctrl.cfg.get("refresh_interval_seconds", EXPECTED_POLL_S))
        self._plot_request_gen = getattr(self, "_plot_request_gen", 0) + 1
        gen = self._plot_request_gen

        while self.plot_container.count():
            item = self.plot_container.takeAt(0)
            if item.widget() is not None and item.widget() is not self.plot_placeholder:
                item.widget().deleteLater()
        self.plot_placeholder.setText("Loading…")
        self.plot_container.addWidget(self.plot_placeholder)

        on_done = self._ui.wrap(lambda payload: self._on_plot_tab_ready(gen, poll_interval_s, payload))

        def worker() -> None:
            try:
                rows = self.ctrl.store.query_propagation(q)
            except ValueError as e:
                on_done(("error", str(e)))
                return
            if not rows:
                on_done(("empty", None))
                return
            on_done(("rows", rows))

        self._plot_query_thread = threading.Thread(target=worker, daemon=True, name="history-query")
        self._plot_query_thread.start()

    def _on_plot_tab_ready(self, gen: int, poll_interval_s: float, payload: tuple) -> None:
        self._plot_last_handled_gen = gen
        if gen != getattr(self, "_plot_request_gen", gen):
            return  # a newer Refresh/date change already superseded this result
        kind, data = payload
        if kind == "error":
            self.plot_placeholder.setText(data)
            return
        if kind == "empty":
            self.plot_placeholder.setText("No data for this date range")
            return
        # Builds the Figure (incl. tight_layout, which touches the FreeType
        # font cache) on the UI thread -- matplotlib is never used off it.
        fig, has_enough_data = _build_history_figure(data, poll_interval_s)
        while self.plot_container.count():
            item = self.plot_container.takeAt(0)
            if item.widget() is not None and item.widget() is not self.plot_placeholder:
                item.widget().deleteLater()
        canvas = FigureCanvas(fig)
        self.plot_container.addWidget(canvas)
        if has_enough_data:
            save_btn = QPushButton("Save PNG", clicked=lambda: self._save_fig(fig))
            self.plot_container.addWidget(save_btn)

    def _save_fig(self, fig) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "history.png", "PNG (*.png)")
        if not path:
            return
        try:
            fig.savefig(path, dpi=150, facecolor="#0B1220")
        except Exception as e:
            self._toasts.show_toast(f"Save failed: {e}", kind="error")
            return
        QMessageBox.information(self, "Saved", path)

    def _eye_icon(self, crossed: bool, size: int = 16) -> QIcon:
        """Small drawn eye glyph for the QRZ key show/hide action (no icon asset needed)."""
        from PySide6.QtGui import QColor, QPainter

        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QColor(MUTED)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = size * 0.72
        top = (size - r) / 2
        p.drawEllipse(int((size - r) / 2), int(top), int(r), int(r * 0.6))
        pupil = max(1, int(r * 0.18))
        p.setBrush(pen)
        p.drawEllipse(int(size / 2 - pupil / 2), int(size / 2 - pupil / 2), pupil, pupil)
        if crossed:
            p.drawLine(2, 2, size - 2, size - 2)
        p.end()
        return QIcon(pix)

    def _add_form_page(self, pages_list: QListWidget, stack: QStackedWidget, title: str) -> QFormLayout:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # S1: long rows always wrap (label above field); _update_settings_wrap_policy
        # switches every row to wrap once the page itself gets narrow.
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        description = QLabel(SETTINGS_PAGE_DESCRIPTIONS.get(title, ""))
        description.setObjectName("muted")
        description.setWordWrap(True)
        form.addRow(description)
        stack.addWidget(page)
        pages_list.addItem(title)
        return form

    def _add_settings_row(self, form: QFormLayout, text: str, field) -> QLabel:
        """addRow with a fixed-width label so every Settings page lines up (N-new-3)."""
        label = QLabel(text)
        label.setMinimumWidth(SETTINGS_LABEL_WIDTH)
        if hasattr(field, "setMinimumWidth"):
            # S1: fields never shrink below a legible width, so a narrow dialog
            # wraps the row instead of squeezing the field unreadably thin.
            field.setMinimumWidth(SETTINGS_FIELD_MIN_WIDTH)
        form.addRow(label, field)
        return label

    def _build_settings_dialog(self, initial_page: str | None = None) -> QDialog:
        from orbitrx.cat import RIG_PROFILES

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setMinimumSize(520, 380)
        outer = QVBoxLayout(dlg)
        # P2B: a separate toast surface anchored to the dialog itself -- the
        # dialog is modal, so a toast on the main window underneath it would
        # never be seen.
        dlg._toasts = ToastManager(dlg)

        # The list+pages area scrolls independently so a small/scaled-up screen can
        # shrink the dialog without ever hiding the Save/Cancel buttons below it.
        # S1: horizontal scrolling is never offered, even when it "would" fit by a
        # sub-pixel margin (R2) -- rows wrap instead (see _update_settings_wrap_policy).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_body = QWidget()
        body = QHBoxLayout(scroll_body)
        scroll.setWidget(scroll_body)
        outer.addWidget(scroll, stretch=1)
        dlg.scroll = scroll

        page_list = QListWidget()
        page_list.setFixedWidth(SETTINGS_NAV_WIDTH_WIDE)
        stack = QStackedWidget()
        dlg.page_list = page_list
        dlg.stack = stack
        body.addWidget(page_list)
        body.addWidget(stack, stretch=1)
        page_list.currentRowChanged.connect(stack.setCurrentIndex)

        cfg = self.ctrl.cfg
        fields: dict[str, QWidget] = {}

        # --- Station ---
        station = self._add_form_page(page_list, stack, "Station")
        fields["spots_callsign"] = QLineEdit(str(cfg.get("spots_callsign", "") or ""))
        self._add_settings_row(station, "My callsign", fields["spots_callsign"])
        fields["home_lat"] = QDoubleSpinBox()
        fields["home_lat"].setRange(-90.0, 90.0)
        fields["home_lat"].setDecimals(4)
        fields["home_lat"].setSpecialValueText(NO_DATA)
        fields["home_lat"].setMinimumHeight(30)  # M3: room for both spin arrows
        fields["home_lat"].setValue(float(cfg.get("home_lat") or -90.0) if cfg.get("home_lat") is not None else -90.0)
        self._add_settings_row(station, "Home latitude", fields["home_lat"])
        fields["home_lon"] = QDoubleSpinBox()
        fields["home_lon"].setRange(-180.0, 180.0)
        fields["home_lon"].setDecimals(4)
        fields["home_lon"].setSpecialValueText(NO_DATA)
        fields["home_lon"].setMinimumHeight(30)
        fields["home_lon"].setValue(float(cfg.get("home_lon") or -180.0) if cfg.get("home_lon") is not None else -180.0)
        self._add_settings_row(station, "Home longitude", fields["home_lon"])
        fields["ip_geolocation_enabled"] = QCheckBox("Look up my location from my IP")
        fields["ip_geolocation_enabled"].setChecked(bool(cfg.get("ip_geolocation_enabled", False)))
        fields["ip_geolocation_enabled"].setContentsMargins(0, 0, 0, 0)
        # S1/R2: the checkbox is the sole field widget in its row (not nested in a
        # vbox with the helper text below it) so its single line of text sits at the
        # same height as the "Location" label; the helper text gets its own row with
        # an empty label instead.
        location_label = self._add_settings_row(station, "Location", fields["ip_geolocation_enabled"])
        location_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        ip_note = QLabel("Sends your IP address to ipinfo.io to estimate your location.")
        ip_note.setWordWrap(True)
        ip_note.setObjectName("muted")
        # M4: a small top margin (<=4px from its checkbox) and a 24px left indent,
        # so the helper text visually belongs to the checkbox above it.
        ip_note.setContentsMargins(24, 4, 0, 0)
        station.addRow("", ip_note)

        # --- Rig ---
        rig = self._add_form_page(page_list, stack, "Rig")
        cat_port = QComboBox()
        cat_port.setEditable(True)
        populate_port_combo(cat_port, self.ctrl.cat, str(cfg.get("cat_port", "") or ""))
        fields["cat_port"] = cat_port
        self._add_settings_row(rig, "Serial port", cat_port)
        rig_profile = QComboBox()
        rig_profile.addItems(sorted(RIG_PROFILES.keys()))
        pidx = rig_profile.findText(str(cfg.get("cat_rig_profile", "kenwood")))
        if pidx >= 0:
            rig_profile.setCurrentIndex(pidx)
        fields["cat_rig_profile"] = rig_profile
        self._add_settings_row(rig, "Rig profile", rig_profile)
        baud = QComboBox()
        baud.addItems(["4800", "9600", "19200", "38400", "115200"])
        bidx = baud.findText(str(cfg.get("cat_baud", 9600)))
        if bidx >= 0:
            baud.setCurrentIndex(bidx)
        fields["cat_baud"] = baud
        self._add_settings_row(rig, "Baud rate", baud)
        rig_control = QComboBox()
        rig_control.addItem("Serial CAT (pyserial)", "serial")
        rig_control.addItem("OmniRig (Windows)", "omnirig")
        ridx = rig_control.findData(self.ctrl.cat.backend())
        if ridx >= 0:
            rig_control.setCurrentIndex(ridx)
        fields["rig_control"] = rig_control
        self._add_settings_row(rig, "Rig control", rig_control)
        test_cat_row = QHBoxLayout()
        test_cat_btn = QPushButton("Test CAT")
        test_cat_cancel_btn = QPushButton("Cancel")
        test_cat_cancel_btn.setVisible(False)
        test_cat_result = QLabel("")
        test_cat_result.setWordWrap(True)
        cat_runner = CatTestRunner(dlg)

        def on_cat_test_done(kind: str, message: str) -> None:
            test_cat_btn.setEnabled(True)
            test_cat_cancel_btn.setVisible(False)
            if kind == "cancelled":
                test_cat_result.setText("Cancelled")
                test_cat_result.setStyleSheet(f"color: {MUTED};")
                return
            if kind == "timeout":
                test_cat_result.setText(message)
                test_cat_result.setStyleSheet(f"color: {ERR};")
                self._set_rig_status(False, "test timed out")
                dlg._toasts.show_toast(f"CAT test failed: {message}", kind="error")
                return
            ok = "Sent CAT" in message
            test_cat_result.setText(message)
            test_cat_result.setStyleSheet(f"color: {OK if ok else ERR};")
            self._set_rig_status(ok, "connected" if ok else "test failed")
            if not ok:
                dlg._toasts.show_toast(f"CAT test failed: {message}", kind="error")

        def do_test_cat() -> None:
            cfg.data["cat_port"] = (fields["cat_port"].currentData() or fields["cat_port"].currentText()).strip()
            cfg.data["cat_baud"] = int(fields["cat_baud"].currentText())
            cfg.data["cat_rig_profile"] = fields["cat_rig_profile"].currentText()
            test_cat_btn.setEnabled(False)
            test_cat_cancel_btn.setVisible(True)
            test_cat_result.setText("Testing…")
            test_cat_result.setStyleSheet("")
            cat_runner.start(self.ctrl.cat, 14.200, on_cat_test_done, timeout_s=CAT_TEST_TIMEOUT_S)

        test_cat_btn.clicked.connect(do_test_cat)
        test_cat_cancel_btn.clicked.connect(cat_runner.cancel)
        test_cat_row.addWidget(test_cat_btn)
        test_cat_row.addWidget(test_cat_cancel_btn)
        test_cat_row.addWidget(test_cat_result, stretch=1)
        rig.addRow("", test_cat_row)
        # Stable handles for tests, same convention as dlg.fields/band_checks below.
        dlg.test_cat_btn = test_cat_btn
        dlg.test_cat_cancel_btn = test_cat_cancel_btn
        dlg.test_cat_result = test_cat_result
        dlg._cat_runner = cat_runner

        # --- DX cluster ---
        dxc = self._add_form_page(page_list, stack, "DX cluster")
        fields["dx_cluster_callsign"] = QLineEdit(str(cfg.get("dx_cluster_callsign", "") or ""))
        self._add_settings_row(dxc, "Cluster callsign", fields["dx_cluster_callsign"])
        fields["target_dx_callsign"] = QLineEdit(str(cfg.get("target_dx_callsign", "") or ""))
        self._add_settings_row(dxc, "Target DX callsign", fields["target_dx_callsign"])
        fields["target_dx_lat"] = QDoubleSpinBox()
        fields["target_dx_lat"].setRange(-90.0, 90.0)
        fields["target_dx_lat"].setDecimals(4)
        fields["target_dx_lat"].setSpecialValueText(NO_DATA)
        fields["target_dx_lat"].setMinimumHeight(30)
        fields["target_dx_lat"].setValue(float(cfg.get("target_dx_lat") or -90.0) if cfg.get("target_dx_lat") is not None else -90.0)
        self._add_settings_row(dxc, "Target latitude", fields["target_dx_lat"])
        fields["target_dx_lon"] = QDoubleSpinBox()
        fields["target_dx_lon"].setRange(-180.0, 180.0)
        fields["target_dx_lon"].setDecimals(4)
        fields["target_dx_lon"].setSpecialValueText(NO_DATA)
        fields["target_dx_lon"].setMinimumHeight(30)
        fields["target_dx_lon"].setValue(float(cfg.get("target_dx_lon") or -180.0) if cfg.get("target_dx_lon") is not None else -180.0)
        self._add_settings_row(dxc, "Target longitude", fields["target_dx_lon"])

        band_box = QGroupBox("DX band filters (empty = all)")
        band_layout = QVBoxLayout(band_box)
        band_checks: dict[float, QCheckBox] = {}
        current_bands = set(cfg.get("dx_filter_bands_mhz") or [])
        for name, meta in HF_BANDS.items():
            cb = QCheckBox(f"{name} ({meta['freq']} MHz)")
            cb.setChecked(meta["freq"] in current_bands)
            band_checks[meta["freq"]] = cb
            band_layout.addWidget(cb)
        dxc.addRow(band_box)

        cont_box = QGroupBox("DX continent filters (empty = all)")
        cont_box_layout = QVBoxLayout(cont_box)
        cont_checks: dict[str, QCheckBox] = {}
        current_cont = set(cfg.get("dx_filter_continents") or [])
        cont_widgets = []
        for code, label in CONTINENT_OPTS:
            cb = QCheckBox(code)
            cb.setToolTip(label)
            cb.setChecked(code in current_cont)
            cont_checks[code] = cb
            cont_widgets.append(cb)
        # M4: a flow layout (6 per row down to 3) instead of one fixed row, so the
        # continent checkboxes never force a horizontal scrollbar on a narrow page.
        cont_box_layout.addWidget(_ReflowGrid(cont_widgets, min_item_width=90, min_cols=3, max_cols=6))
        dxc.addRow(cont_box)

        # --- Map & spots ---
        map_page = self._add_form_page(page_list, stack, "Map & spots")
        spots_mode = QComboBox()
        spots_mode.addItems(["FT8", "FT4", "WSPR"])
        midx = spots_mode.findText(str(cfg.get("spots_mode", "FT8")))
        if midx >= 0:
            spots_mode.setCurrentIndex(midx)
        fields["spots_mode"] = spots_mode
        self._add_settings_row(map_page, "Mode", spots_mode)
        poll = QSpinBox()
        poll.setRange(300, 3600)
        poll.setSuffix(" s")
        poll.setSingleStep(60)
        poll.setMinimumHeight(30)
        poll.setValue(clamp_poll_seconds(cfg.get("pskreporter_poll_seconds", 300)))
        fields["pskreporter_poll_seconds"] = poll
        self._add_settings_row(map_page, "Poll interval", poll)

        # --- Services ---
        services = self._add_form_page(page_list, stack, "Services")
        qrz_key = QLineEdit(str(cfg.get("qrz_api_key", "") or ""))
        qrz_key.setEchoMode(QLineEdit.EchoMode.Password)
        show_action = QAction(self._eye_icon(crossed=True), "Show key", qrz_key)
        show_action.setCheckable(True)

        def toggle_qrz_echo(checked: bool) -> None:
            qrz_key.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
            show_action.setIcon(self._eye_icon(crossed=not checked))

        show_action.toggled.connect(toggle_qrz_echo)
        qrz_key.addAction(show_action, QLineEdit.ActionPosition.TrailingPosition)
        fields["qrz_api_key"] = qrz_key
        qrz_row = QHBoxLayout()
        qrz_row.addWidget(qrz_key, stretch=1)
        qrz_btn = QPushButton("Test QRZ")
        qrz_row.addWidget(qrz_btn)
        self._add_settings_row(services, "QRZ API key", qrz_row)
        qrz_result = QLabel("")
        qrz_result.setWordWrap(True)

        def do_qrz_test() -> None:
            ok, msg, _ = verify_qrz_api(qrz_key.text().strip())
            qrz_result.setText(msg)
            qrz_result.setStyleSheet(f"color: {OK if ok else ERR};")

        qrz_btn.clicked.connect(do_qrz_test)
        services.addRow("", qrz_result)
        refresh_secs = QSpinBox()
        refresh_secs.setRange(10, 3600)
        refresh_secs.setSuffix(" s")
        refresh_secs.setMinimumHeight(30)
        refresh_secs.setValue(int(cfg.get("refresh_interval_seconds", 60)))
        fields["refresh_interval_seconds"] = refresh_secs
        self._add_settings_row(services, "Space weather refresh", refresh_secs)

        dlg.fields = fields
        dlg.band_checks = band_checks
        dlg.cont_checks = cont_checks

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_btn is not None:
            save_btn.setObjectName("primaryButton")
            save_btn.setDefault(True)
            save_btn.setStyleSheet("")  # let QSS #primaryButton apply
        outer.addWidget(buttons)
        dlg.buttons = buttons

        page_names = ["Station", "Rig", "DX cluster", "Map & spots", "Services"]
        start_row = page_names.index(initial_page) if initial_page in page_names else 0
        page_list.setCurrentRow(start_row)
        # M3: spinbox text starts at the same inset as QLineEdit text (6px padding).
        for _sb in dlg.findChildren(QAbstractSpinBox):
            _sb.lineEdit().setTextMargins(6, 0, 0, 0)

        # Natural size at 100%, then clamped to the available screen so Save/Cancel
        # stay reachable on a small or scaled-up display.
        dlg.resize(720, 520)
        fit_to_screen(dlg, 520, 380)

        # S1: re-check the wrap policy and nav width on every resize, not just once,
        # so dragging the dialog narrower (or a small/scaled-up screen) keeps every
        # field and helper label fully readable without horizontal scrolling.
        dlg._settings_wrap_filter = _SettingsWrapFilter()
        dlg.installEventFilter(dlg._settings_wrap_filter)
        _update_settings_wrap_policy(dlg)
        return dlg

    def _apply_settings_dialog(self, dlg: QDialog) -> None:
        # P1: one combined write instead of one cfg.save() per field (18 full-file
        # disk writes on the UI thread in the old code) -- set_many() updates every
        # key in memory and flush() writes the batch once.
        fields = dlg.fields
        cfg = self.ctrl.cfg
        cfg.set_many({
            "spots_callsign": fields["spots_callsign"].text().strip(),
            "home_lat": None if fields["home_lat"].value() == -90.0 else fields["home_lat"].value(),
            "home_lon": None if fields["home_lon"].value() == -180.0 else fields["home_lon"].value(),
            "ip_geolocation_enabled": fields["ip_geolocation_enabled"].isChecked(),
            "cat_port": (fields["cat_port"].currentData() or fields["cat_port"].currentText()).strip(),
            "cat_baud": int(fields["cat_baud"].currentText()),
            "cat_rig_profile": fields["cat_rig_profile"].currentText(),
            "rig_control": fields["rig_control"].currentData(),
            "dx_cluster_callsign": fields["dx_cluster_callsign"].text().strip(),
            "target_dx_callsign": fields["target_dx_callsign"].text().strip(),
            "target_dx_lat": None if fields["target_dx_lat"].value() == -90.0 else fields["target_dx_lat"].value(),
            "target_dx_lon": None if fields["target_dx_lon"].value() == -180.0 else fields["target_dx_lon"].value(),
            "dx_filter_bands_mhz": [f for f, cb in dlg.band_checks.items() if cb.isChecked()],
            "dx_filter_continents": [c for c, cb in dlg.cont_checks.items() if cb.isChecked()],
            "spots_mode": fields["spots_mode"].currentText(),
            "pskreporter_poll_seconds": clamp_poll_seconds(fields["pskreporter_poll_seconds"].value()),
            "qrz_api_key": fields["qrz_api_key"].text().strip(),
            "refresh_interval_seconds": fields["refresh_interval_seconds"].value(),
        })
        cfg.flush()
        self._timer.setInterval(int(cfg.get("refresh_interval_seconds", 60)) * 1000)
        self._update_next_refresh_label()
        self._populate_cluster_combo()

    def _settings(self, *, initial_page: str | None = None) -> None:
        t0 = time.perf_counter()
        dlg = self._build_settings_dialog(initial_page=initial_page)
        self.ctrl.log.info("perf: settings_dialog_build_ms=%.1f", (time.perf_counter() - t0) * 1000)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._apply_settings_dialog(dlg)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not self.ctrl.cfg.get("minimize_to_tray", True):
            return
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(pix)
        p.setBrush(QColor(0, 120, 215))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.end()
        self._tray = QSystemTrayIcon(QIcon(pix), self)
        menu = QMenu()
        show_act = QAction("Show OrbitRx", self)
        show_act.triggered.connect(self._show_from_tray)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self._quit_app)
        menu.addAction(show_act)
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.setToolTip("OrbitRx Propagation Monitor")
        self._tray.show()

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()

    def _quit_app(self) -> None:
        self.ctrl.stop()
        QApplication.quit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_compact_mode()
        if not self._compact and not getattr(self, "_splitter_user_resized", False):
            self._apply_default_splitter_sizes()
        self._toasts.reposition()

    def _apply_map_min_height(self) -> None:
        """N6 / M9.3: in compact Map tab, keep the map at least ~40% of the
        central height so 150%/1024 does not shrink it to a tiny thumbnail."""
        central = self.centralWidget()
        if central is None or not hasattr(self, "map_widget"):
            return
        ratio = 0.42 if self._compact else 0.48
        target = max(160, int(central.height() * ratio))
        if self._compact:
            # Leave room for the (stacked, in compact mode) chip + slider
            # control strip under the map.
            reserve = 26 + 60 + 24
            target = min(target, max(120, central.height() - reserve))
        self.map_widget.setMinimumHeight(target)
        if hasattr(self.map_widget, "setSizePolicy"):
            from PySide6.QtWidgets import QSizePolicy as _QSP
            self.map_widget.setSizePolicy(_QSP.Policy.Expanding, _QSP.Policy.Expanding)

    def _update_compact_mode(self) -> None:
        """M1: below COMPACT_WIDTH_BELOW logical px, swap the map/side splitter for
        a Map/Conditions tab pair (and back above COMPACT_WIDTH_ABOVE) so neither
        pane is ever squeezed to the point of needing horizontal scrolling."""
        if not hasattr(self, "_splitter"):
            return
        width = self.width()
        if not self._compact and width < COMPACT_WIDTH_BELOW:
            self._enter_compact_mode()
        elif self._compact and width > COMPACT_WIDTH_ABOVE:
            self._exit_compact_mode()
        self._apply_map_min_height()
        # Round 6 (SPEC §11/§13): the control strip's own responsive rules
        # reuse this same compact flag/hysteresis rather than inventing a
        # separate "683px" breakpoint -- COMPACT_WIDTH_BELOW (900) already
        # fires well before SPEC's 683 reference width, so every "at 683"
        # control-strip rule in this round is simply "while self._compact".
        if hasattr(self, "_layers_group"):
            self._apply_layers_compact(self._compact)
            self._apply_sliders_compact(self._compact)
            if width > self._TIME_POPOVER_ABOVE:
                self._apply_time_popover(False)
            elif width < self._TIME_POPOVER_BELOW:
                self._apply_time_popover(True)
        self._update_control_strip_corner_summary()
        self._update_band_panel_compact()
        self._update_compact_chrome()

    def _on_splitter_moved_by_user(self, pos: int, index: int) -> None:
        """QSplitter.setSizes() never emits splitterMoved (only an actual
        handle drag does), so this only fires for a genuine user resize --
        once it has, _apply_default_splitter_sizes() backs off permanently
        instead of fighting the user's choice on the next resize event."""
        self._splitter_user_resized = True

    def _apply_default_splitter_sizes(self) -> None:
        """Explicit ~300px side-pane default. QSplitter.setSizes() only takes
        effect once the splitter has real width to distribute; before the
        first show/resize (or right after _exit_compact_mode re-inserts a
        child QSplitter) that width can be 0 or a small provisional value --
        e.g. a pre-layout default, or (observed on windows-latest CI) a
        top-level window whose resize() hasn't fully propagated to self.width()
        yet. Rather than latching "the default is applied" after any single
        call (which can permanently stick a shrunken size computed from a
        provisional width, since a later resizeEvent would then see the latch
        already set and skip re-applying the real default), this has no
        latch of its own: resizeEvent() re-runs it on every resize until the
        user actually drags the handle (see _on_splitter_moved_by_user), so a
        bad provisional width self-heals on the very next resize instead of
        sticking forever."""
        if getattr(self, "_splitter", None) is None:
            return
        width = self._splitter.width() or self.width()
        if width <= 0:
            return
        side_w = min(300, max(0, width - 200))
        self._splitter.setSizes([max(0, width - side_w), side_w])

    def _enter_compact_mode(self) -> None:
        self._compact = True
        central_layout = self.centralWidget().layout()
        central_layout.removeWidget(self._splitter)
        self._splitter.hide()
        # G1 is scoped to the 1280 layout; at compact widths there isn't
        # vertical room under the map for both the map and a band-card row
        # without shrinking the map below its own dominance floor (SPEC
        # §6.1 principle #1), so band_panel moves back to its pre-P5 spot
        # in the side panel (reachable via the Conditions tab) until the
        # compact band-chips-under-the-map row (G10) is its own round.
        self._map_tab_layout.removeWidget(self.band_panel)
        self._right_layout.insertWidget(0, self.band_panel)
        # Round 6 (SPEC §13 "W<820: side panel hidden (drawer via Ctrl+B)"):
        # the side pane is reachable via its own "Conditions" tab, and
        # Ctrl+B/the header toggle button switch to it instead of being
        # disabled outright (see _set_side_panel_visible) -- not a true
        # floating overlay drawer (the tab bar stays visible either way),
        # but the same real outcome: one keypress reveals the panel's
        # content over what was otherwise a map-only view.
        self._side_pane.setVisible(True)
        self._compact_tabs.addTab(self._map_tab, "Map")
        self._compact_tabs.addTab(self._side_pane, "Conditions")
        central_layout.addWidget(self._compact_tabs)
        self._compact_tabs.show()
        # Map first, always -- SPEC principle #1 ("the map is the product")
        # and §13's drawer default ("closed"). _side_panel_visible is the
        # *wide*-layout collapse flag and is not reused as a "remember which
        # compact tab was open" flag, so a fresh entry into compact mode
        # never jumps straight to Conditions just because the side panel
        # happened to be visible in the wide layout.
        self._compact_tabs.setCurrentWidget(self._map_tab)

    def _exit_compact_mode(self) -> None:
        self._compact = False
        self._right_layout.removeWidget(self.band_panel)
        self._map_tab_layout.addWidget(self.band_panel)
        central_layout = self.centralWidget().layout()
        central_layout.removeWidget(self._compact_tabs)
        self._compact_tabs.hide()
        self._compact_tabs.removeTab(self._compact_tabs.indexOf(self._side_pane))
        self._compact_tabs.removeTab(self._compact_tabs.indexOf(self._map_tab))
        self._splitter.insertWidget(0, self._map_tab)
        self._splitter.insertWidget(1, self._side_pane)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        central_layout.addWidget(self._splitter)
        self._splitter.show()
        # QTabWidget explicitly hides a page that isn't its current tab, and
        # that explicit-hide flag survives insertWidget() reparenting it back
        # into the splitter -- without this it stays invisible (0-width) even
        # though its new parent is shown.
        self._map_tab.show()
        self._side_pane.setVisible(self._side_panel_visible)
        self._apply_default_splitter_sizes()

    def keyPressEvent(self, event) -> None:
        """Round 6 (SPEC §13 "Ctrl+B opens it ... closed with Esc"): Esc
        closes the side panel only while it's the thing actually showing in
        compact mode (the Conditions tab) -- never in the wide layout, where
        Esc has no other meaning here and shouldn't fight a user's own
        expectations for the key."""
        if (
            event.key() == Qt.Key.Key_Escape
            and getattr(self, "_compact", False)
            and getattr(self, "_compact_tabs", None) is not None
            and self._compact_tabs.currentWidget() is self._side_pane
        ):
            self._actions["ShowSidePanel"].setChecked(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            getattr(self, "_tray", None)
            and self.ctrl.cfg.get("minimize_to_tray", True)
            and event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
        ):
            QTimer.singleShot(0, self.hide)
            self._tray.showMessage(
                "OrbitRx",
                "Running in the system tray. Background refresh is active.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def event(self, event) -> bool:
        # Round 10 (p4-r11): catches deleteLater()-driven teardown too, not
        # just an explicit close() -- most of this suite's own tests tear
        # their window down via `win.deleteLater(); app.processEvents()`
        # directly (bypassing closeEvent entirely), and deleteLater()'s
        # actual C++ destruction happens when Qt delivers this
        # DeferredDelete event, not at the deleteLater() call itself. Without
        # this, that destruction could run while map_widget's own rebuild
        # worker thread is still inside build_scene()/_pil_to_qimage()
        # against `self` -- a real use-after-free, root-caused from the
        # intermittent "Garbage-collecting ... map_renderer._terminator_
        # points" segfault this round fixes. Bounded, not indefinite, for
        # the same reason closeEvent's join is bounded.
        if event.type() == QEvent.Type.DeferredDelete:
            map_widget = getattr(self, "map_widget", None)
            join_rebuild = getattr(map_widget, "join_rebuild_thread", None)
            if join_rebuild is not None:
                join_rebuild(timeout=2.0)
        return super().event(event)

    def closeEvent(self, event) -> None:
        if self._tray and self._tray.isVisible() and self.ctrl.cfg.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "OrbitRx",
                "Minimized to tray. Right-click tray icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        self._flush_layers_save()
        self.ctrl.cfg.set("window_geometry", f"{self.width()}x{self.height()}")
        self.ctrl.cfg.flush()  # P1: nothing from a batched set_many() is lost on close
        self.ctrl.stop()
        # Round 10 (p4-r11): bounded join of the map's own render worker --
        # without this, closing the window while a rebuild is in flight could
        # delete this widget (and its renderer/pixmap state) out from under
        # that still-running thread once Qt/Python actually frees it, a
        # use-after-free rather than a merely slow close. Bounded, not
        # indefinite: a genuinely stuck worker must never hang app shutdown.
        join_rebuild = getattr(self.map_widget, "join_rebuild_thread", None)
        if join_rebuild is not None:
            join_rebuild(timeout=2.0)
        super().closeEvent(event)

    def run(self) -> None:
        self.show()


# M4: the nav list is 150px under this dialog width, 180px otherwise.
SETTINGS_NAV_WIDTH_BREAKPOINT = 700


def _update_settings_wrap_policy(dlg: QDialog) -> None:
    """M4/S1: the nav list width and the form row-wrap policy are both fixed
    functions of the dialog's own width alone, never of a child's *current*
    width -- a child's width is itself an effect of this function, and feeding
    an effect back into its own cause would just toggle forever as child
    geometry settles across layout passes.

    The row-wrap decision always assumes the *narrow* nav width when estimating
    the page's own width, regardless of which nav width is actually in effect --
    otherwise a wide-enough dialog with the wide (180px) nav would wrap rows it
    doesn't need to, just because 180 > 150 ate into the page-width estimate.
    """
    width = dlg.width()
    nav_width = SETTINGS_NAV_WIDTH_NARROW if width < SETTINGS_NAV_WIDTH_BREAKPOINT else SETTINGS_NAV_WIDTH_WIDE
    narrow_page = width < (SETTINGS_NARROW_PAGE_WIDTH + SETTINGS_NAV_WIDTH_NARROW)
    policy = QFormLayout.RowWrapPolicy.WrapAllRows if narrow_page else QFormLayout.RowWrapPolicy.WrapLongRows
    for form in dlg.findChildren(QFormLayout):
        form.setRowWrapPolicy(policy)
    dlg.page_list.setFixedWidth(nav_width)


class _SettingsWrapFilter(QObject):
    """Re-applies the Settings dialog's row-wrap policy on every resize (S1)."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if event.type() == QEvent.Type.Resize:
            _update_settings_wrap_policy(obj)
        return False


def _app_icon() -> QIcon:
    from orbitrx.paths import bundled_root, project_root

    bundle = bundled_root()
    search = ([bundle / "assets" / "orbitrx.ico"] if bundle else []) + [
        project_root() / "assets" / "orbitrx.ico"
    ]
    for path in search:
        if path.is_file():
            return QIcon(str(path))
    return QIcon()


def _save_button_fully_visible(dlg: QDialog) -> bool:
    """Whether the Settings dialog's Save button's geometry lies within the dialog's
    own visible rect, i.e. it hasn't been pushed off-screen by a too-small window."""
    save_btn = dlg.buttons.button(QDialogButtonBox.StandardButton.Save)
    top_left = save_btn.mapTo(dlg, save_btn.rect().topLeft())
    btn_rect = QRect(top_left, save_btn.size())
    if not dlg.rect().contains(btn_rect):
        return False
    # V7: it must also be inside the screen's available area (not behind the
    # taskbar or off the bottom edge), measured in global coordinates.
    if dlg.isVisible() and QGuiApplication.platformName() not in ("offscreen", "minimal"):
        screen = dlg.screen() or QGuiApplication.primaryScreen()
        global_rect = QRect(save_btn.mapToGlobal(save_btn.rect().topLeft()), save_btn.size())
        return screen.availableGeometry().contains(global_rect)
    return True


def _main_window_hscroll_visible(win) -> bool:
    """Whether any scroll area inside the main window shows a horizontal scrollbar."""
    return any(
        sa.horizontalScrollBar().isVisible() for sa in win.findChildren(QScrollArea) if sa.window() is win
    )


def settings_fit_report(dlg: QDialog) -> dict:
    """M4: a small fit report for CI/tests -- no horizontal scrollbar, Save fully
    visible, and every field's right edge still inside the dialog."""
    hscroll_visible = bool(
        hasattr(dlg, "scroll") and dlg.scroll.horizontalScrollBar().isVisible()
    )
    fields_right_visible = True
    for field in dlg.fields.values():
        if not field.isVisibleTo(dlg):
            continue  # on another Settings page
        top_right = field.mapTo(dlg, field.rect().topRight())
        if top_right.x() > dlg.width():
            fields_right_visible = False
            break
    return {
        "hscroll_visible": hscroll_visible,
        "save_visible": _save_button_fully_visible(dlg),
        "fields_right_visible": fields_right_visible,
    }


def run_release_capture_hook(out_dir: str | Path) -> int:
    """Release-exe self-capture (M3 evidence): grab the rig wizard's port dropdown and
    the DX cluster settings page into `out_dir`, then return. Runs against whatever
    CatController the release build actually has -- the simulated rig is never involved
    here, so a "Simulated" entry in the written port list is a genuine release bug.
    Read-only, and waits only a few fixed seconds regardless of network state so it
    completes the same way online or offline.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    set_high_dpi_rounding_policy()
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    # Capture mode must never block on a modal alarm popup.
    QtOrbitRxApplication._alarm_excellent = lambda self: None
    QtOrbitRxApplication._alarm_storm = lambda self: None
    win = QtOrbitRxApplication()
    win.resize(1440, 860)
    fit_to_screen(win, 640, 440)
    win.show()

    def wait(seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            app.processEvents()
            time.sleep(0.05)

    wait(0.3)
    # N2: raise the app above any runner console so screen grabs are not covered.
    win.raise_()
    win.activateWindow()
    app.processEvents()

    # Wait briefly for weather/band tiles so captures do not show UNKNOWN (N6).
    try:
        win.ctrl.fetch_weather()
    except Exception:
        pass
    deadline = time.time() + 10.0
    while time.time() < deadline:
        app.processEvents()
        grid = getattr(win.ctrl.state, "band_grid", {}) or {}
        if grid and any(v and v != "UNKNOWN" for v in grid.values()):
            break
        time.sleep(0.2)
    win._refresh_labels_and_map()
    app.processEvents()

    cat = win.ctrl.cat
    if os.environ.get("ORBITRX_TEST_SIMULATED_RIG") == "1":
        # CI negative control only: with the test switch on, the gate check must see
        # the simulated rig. Without it (the default) the real CatController is used.
        from orbitrx.ui.rig_wizard import SimulatedCatController
        cat = SimulatedCatController()
    wizard = RigWizardDialog(win.ctrl.cfg, cat, win)
    wizard.show()
    wait(0.4)
    wfg = wizard.frameGeometry()
    (wizard.screen() or app.primaryScreen()).grabWindow(0, wfg.x(), wfg.y(), wfg.width(), wfg.height()).save(
        str(out_dir / "rig-wizard.png")
    )
    wizard_on_screen = (wizard.screen() or app.primaryScreen()).availableGeometry().contains(wfg)
    wizard.port_combo.showPopup()
    wait(0.3)
    rect = wizard.frameGeometry()
    popup = wizard.port_combo.view().window()
    if popup is not None and popup.isVisible():
        rect = rect.united(popup.frameGeometry())
    screen = wizard.screen() or app.primaryScreen()
    screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).save(
        str(out_dir / "rig-wizard-release-dropdown.png")
    )
    items = [wizard.port_combo.itemText(i) for i in range(wizard.port_combo.count())]
    (out_dir / "rig-wizard-release-ports.txt").write_text("\n".join(items) + "\n", encoding="utf-8")
    wizard.port_combo.hidePopup()
    wizard.reject()

    settings_dlg = win._build_settings_dialog(initial_page="DX cluster")
    settings_dlg.show()
    settings_dlg.raise_()
    settings_dlg.activateWindow()
    wait(0.4)
    fg = settings_dlg.frameGeometry()
    # Grab the dialog widget itself (not the whole screen) so a runner console
    # cannot cover the evidence (N2).
    settings_dlg.grab().save(str(out_dir / "settings-dx-cluster.png"))
    # N7: settings-full is the Station page, not a duplicate of DX cluster.
    for i in range(settings_dlg.page_list.count()):
        if settings_dlg.page_list.item(i).text().strip().lower().startswith("station"):
            settings_dlg.page_list.setCurrentRow(i)
            break
    wait(0.3)
    settings_dlg.grab().save(str(out_dir / "settings-full.png"))
    # Whole-desktop grab after raising the dialog again.
    settings_dlg.raise_()
    app.processEvents()
    app.primaryScreen().grabWindow(0).save(str(out_dir / "desktop-settings.png"))
    save_visible = _save_button_fully_visible(settings_dlg)
    settings_on_screen = settings_dlg.screen().availableGeometry().contains(settings_dlg.frameGeometry())
    settings_size = (settings_dlg.width(), settings_dlg.height())
    settings_dlg.reject()

    from orbitrx.ui.about import _build_about_dialog
    about = _build_about_dialog(win)
    about.show()
    wait(0.4)
    afg = about.frameGeometry()
    about.grab().save(str(out_dir / "about.png"))
    about_on_screen = (about.screen() or app.primaryScreen()).availableGeometry().contains(afg)
    about.reject()

    win_screen = win.screen() or app.primaryScreen()
    avail = win_screen.availableGeometry()
    win.raise_()
    win.activateWindow()
    wait(0.3)
    main_fg = win.frameGeometry()
    # N2: widget grab for the window itself (immune to overlapping consoles).
    win.grab().save(str(out_dir / "main-window.png"))
    # Desktop grab still useful for on-screen framing; raise first.
    win.raise_()
    app.processEvents()
    win_screen.grabWindow(0).save(str(out_dir / "desktop-main.png"))
    # M1: all of Settings/Rig/About must be reachable (directly or via the
    # toolbar's overflow chevron) in this capture.
    controls_reachable = all(win.controls_reachable().get(name, False) for name in ("Settings", "Rig", "About"))
    (out_dir / "fit.txt").write_text(
        f"avail={avail.width()}x{avail.height()} "
        f"settings={settings_size[0]}x{settings_size[1]} "
        f"save_visible={save_visible} "
        f"settings_frame_on_screen={settings_on_screen} "
        f"main={win.width()}x{win.height()} "
        f"main_frame_on_screen={avail.contains(main_fg)} "
        f"main_hscroll={_main_window_hscroll_visible(win)} "
        f"controls_reachable={controls_reachable} "
        f"about_frame_on_screen={about_on_screen} "
        f"wizard_frame_on_screen={wizard_on_screen}\n",
        encoding="utf-8",
    )

    # M5: the rendered Stats text, so CI can grep for "n/a <unit>".
    stats_lines = [lbl.text() for lbl in win._labels.values()]
    if win._location_hint_lbl.isVisibleTo(win):
        stats_lines.append(win._location_hint_lbl.text())
    (out_dir / "stats.txt").write_text("\n".join(stats_lines) + "\n", encoding="utf-8")

    # Stop background work and close the window, but never exit the process
    # here (CI runs 42876091854 and 42878248609 hung/crashed because an
    # earlier version of this hook tried to end the process itself while Qt
    # objects were still alive). In-process pytest callers rely on
    # QApplication staying alive afterwards; the frozen exe's self-capture
    # and tools/capture_shutdown_probe.py drive the real process-ending
    # teardown themselves, via run_capture_and_exit, after this returns.
    quiet_capture_shutdown(app, win, out_dir / "shutdown-stage.txt")
    return 0


def _stage(stage_log: Path | None, name: str) -> None:
    if stage_log is None:
        return
    stage_log.parent.mkdir(parents=True, exist_ok=True)
    with stage_log.open("a", encoding="utf-8") as handle:
        handle.write(name + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _delete_qt_object(obj) -> None:
    if obj is None:
        return
    from PySide6.QtCore import QObject
    if not isinstance(obj, QObject):
        return
    import shiboken6

    if shiboken6.isValid(obj):
        shiboken6.delete(obj)


def quiet_capture_shutdown(app, win, stage_log: Path | None) -> None:
    """Stop background work and close the window. Does not exit the process.

    closeEvent ignores the close while the tray icon is visible, which is the
    default. The capture is not a minimize-to-tray. Hide the tray first so the
    window actually closes. Historical note: this used to also release a
    WebEngine view before that close, back when the leaflet import loaded Qt
    WebEngine even for the static map. Qt WebEngine is gone now (Option B,
    2026-11-09); `map_widget.web` never exists, so the "webengine-not-created"
    stage below always fires -- it stays named that for continuity with the
    historical shutdown-stage logs this fed into.
    """
    if win is None:
        _stage(stage_log, "webengine-not-created")
        return
    # F7: drop queued map-load/history-plot callbacks and wait for the workers
    # so a later QApplication teardown cannot stall on an off-thread QImage /
    # pending slot, and so no stale worker is still running (touching
    # matplotlib, in the history-query case) once this returns.
    invoker = getattr(win, "_ui", None)
    if invoker is not None:
        try:
            invoker.call.disconnect()
        except Exception:
            pass
    for name in ("_map_load_thread", "_plot_query_thread"):
        thread = getattr(win, name, None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
    map_widget = getattr(win, "map_widget", None)
    join_rebuild = getattr(map_widget, "join_rebuild_thread", None)
    if join_rebuild is not None:
        join_rebuild(timeout=2.0)
    for name in ("_timer", "_cluster_pulse_timer", "_clock_timer"):
        timer = getattr(win, name, None)
        if timer is not None:
            timer.stop()
    _stage(stage_log, "timers-stopped")
    tray = getattr(win, "_tray", None)
    if tray is not None:
        tray.hide()
    if getattr(win, "ctrl", None) is not None:
        win.ctrl.cfg.set("minimize_to_tray", False)
        win.ctrl.stop()
    win._tray = None
    _stage(stage_log, "tray-hidden")
    _stage(stage_log, "controller-stopped")
    web = getattr(getattr(win, "map_widget", None), "web", None)
    if web is None:
        _stage(stage_log, "webengine-not-created")
    else:
        web.deleteLater()
        if app is not None:
            app.processEvents()
        _stage(stage_log, "webengine-page-released")
    win.close()
    if app is not None:
        app.processEvents()
    _stage(stage_log, "window-closed")


def _join_worker_threads(win, stage_log: Path | None) -> None:
    """Capture-process teardown only: stop and join every background thread this
    app may have started, before any Qt object is deleted. A Qt destructor on
    the main thread holds the GIL; a worker thread that later tries to queue a
    call into a deleted QObject (e.g. the weather-fetch completion callback)
    cannot be allowed to still be running once we start deleting widgets below.
    Threads that do not finish within their timeout are logged by name (via
    threading.enumerate(), to also catch anything not explicitly tracked here)
    rather than joined forever -- this capture process must still end.
    """
    ctrl = getattr(win, "ctrl", None) if win is not None else None
    if ctrl is not None:
        ctrl.join_background_threads()
    update_thread = getattr(win, "_update_check_thread", None) if win is not None else None
    if update_thread is not None and update_thread.is_alive():
        update_thread.join(timeout=3.0)
    map_thread = getattr(win, "_map_load_thread", None) if win is not None else None
    if map_thread is not None and map_thread.is_alive():
        map_thread.join(timeout=2.0)
    plot_thread = getattr(win, "_plot_query_thread", None) if win is not None else None
    if plot_thread is not None and plot_thread.is_alive():
        plot_thread.join(timeout=2.0)
    map_widget = getattr(win, "map_widget", None) if win is not None else None
    join_rebuild = getattr(map_widget, "join_rebuild_thread", None)
    if join_rebuild is not None:
        join_rebuild(timeout=2.0)
    stragglers = sorted(t.name for t in threading.enumerate() if t is not threading.main_thread())
    if stragglers:
        _stage(stage_log, f"threads-still-alive:{','.join(stragglers)}")
    else:
        _stage(stage_log, "threads-joined")


def _delete_all_top_level_widgets(app, stage_log: Path | None) -> None:
    """Capture-process teardown only: close and delete every top-level widget
    (main window, and any dialog the hook only reject()/close()'d -- RigWizardDialog,
    the Settings dialog, the About box -- which stay alive as undeleted QObjects
    otherwise) before QApplication itself is deleted. Processes DeferredDelete
    events between rounds so children scheduled via deleteLater() actually go."""
    import shiboken6
    from PySide6.QtCore import QCoreApplication

    try:
        import matplotlib.pyplot as plt
        plt.close("all")
    except Exception:
        pass

    if app is None:
        _stage(stage_log, "widgets-deleted")
        return

    for widget in list(app.topLevelWidgets()):
        if shiboken6.isValid(widget):
            widget.close()
    remaining = [w for w in app.topLevelWidgets() if shiboken6.isValid(w)]
    for _ in range(50):
        if not remaining:
            break
        for widget in remaining:
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        remaining = [w for w in app.topLevelWidgets() if shiboken6.isValid(w)]
    if remaining:
        _stage(stage_log, f"widgets-still-alive:{len(remaining)}")
        for widget in remaining:
            _delete_qt_object(widget)
    _stage(stage_log, "widgets-deleted")


def _delete_qapplication(app, stage_log: Path | None) -> None:
    """Capture-process teardown only: end QApplication itself, having already
    joined every worker thread and deleted every other Qt object above, then
    drop the last Python references to it and collect. This is the "process
    an app the documented way" counterpart to the historical os._exit calls
    this replaces -- os._exit (and the ExitProcess it maps to on Windows) runs
    DLL-detach / Qt global-static destructors unconditionally, which crashed
    (0xC0000005) when QApplication and widgets were still alive (CI run
    42881812414). Nothing is alive here for that to race against.
    """
    if app is not None and hasattr(app, "shutdown"):
        try:
            app.shutdown()
        except Exception:
            pass
    _delete_qt_object(app)
    gc.collect()
    _stage(stage_log, "qapplication-deleted")


def shutdown_capture_process(app, win, exit_code: int, stage_log: Path | None) -> int:
    """Deterministic end-of-process teardown for the capture-only path (the
    frozen exe's self-capture and tools/capture_shutdown_probe.py). Unlike
    quiet_capture_shutdown (used in-process by pytest, which must leave
    QApplication alive for later tests), this actually tears everything down:
    worker threads joined, every top-level widget deleted, then QApplication
    itself. The caller is expected to end the process (sys.exit or platform
    equivalent) with the returned code immediately afterward -- normal
    interpreter finalisation is safe at that point because there is no live
    Qt object left for it to touch.
    """
    try:
        _join_worker_threads(win, stage_log)
        _delete_all_top_level_widgets(app, stage_log)
        _delete_qapplication(app, stage_log)
    except Exception as exc:
        _stage(stage_log, f"exception:{type(exc).__name__}: {exc}")
        if sys.stderr is not None:  # None in the windowed (console=False) frozen exe
            sys.stderr.write(f"capture shutdown failed: {type(exc).__name__}: {exc}\n")
        exit_code = 4
    _stage(stage_log, "process-exit")
    return exit_code


def run_capture_and_exit(capture_dir: str | Path) -> None:
    """Drive the self-capture hook and then end the process. Shared by
    run_qt_app (the frozen exe, when ORBITRX_CAPTURE_DIR is set) and
    tools/capture_shutdown_probe.py, so the probe exercises exactly the
    shutdown path the Windows CI job depends on. Does not return.
    """
    capture_dir = Path(capture_dir)
    stage_log = capture_dir / "shutdown-stage.txt"
    fault_log = capture_dir / "faulthandler.txt"
    capture_dir.mkdir(parents=True, exist_ok=True)
    fault_file = fault_log.open("w", encoding="utf-8")
    # The frozen exe is windowed (no console), so stderr may be None -- always
    # pass an explicit file. faulthandler's watchdog runs on its own C thread
    # and does not need the GIL, unlike the threading.Timer it replaces (CI run
    # 42876091854: the GIL was stuck inside a Qt destructor, so a Timer
    # callback could never have run either). 75s leaves headroom inside both the
    # 90s pytest probe timeout and the 120s CI exe timeout, so a hang dumps a
    # traceback here before the caller kills the process.
    faulthandler.enable(file=fault_file)
    faulthandler.dump_traceback_later(75.0, exit=True, file=fault_file)
    try:
        code = run_release_capture_hook(capture_dir)
        app = QApplication.instance()
        win = next(
            (w for w in app.topLevelWidgets() if isinstance(w, QtOrbitRxApplication)), None
        ) if app is not None else None
        code = shutdown_capture_process(app, win, code, stage_log)
    finally:
        faulthandler.cancel_dump_traceback_later()
    # CI run 43299583680 (17ad018): the frozen exe wrote process-exit but never
    # reached atexit, and the re-armed watchdog never fired -- because it was
    # never re-armed. The exe is windowed (console=False), so sys.stdout and
    # sys.stderr are None there; the unguarded stdout flush that used to sit
    # here raised AttributeError, which escaped main() as an unhandled
    # exception, and PyInstaller's windowed bootloader then shows a modal
    # "Unhandled exception" dialog that nobody on a CI runner can dismiss.
    # That dialog, not a Qt destructor, was the post-teardown 120s hang.
    # (Python and the offscreen pytest probe always have real stdio, which is
    # why Linux and the Windows test job never saw it.)
    _flush_stdio()
    fault_file.flush()
    # CI run 43297268110 (8a9beb4): on the frozen Windows exe the whole
    # teardown above completed (stage log ends in process-exit, faulthandler.txt
    # empty) and the process still did not end within 120s, so the hang is in
    # interpreter finalisation after sys.exit. Keep faulthandler armed through
    # finalisation -- the file stays open on purpose -- so a hang there dumps
    # every thread's stack and ends the process instead of hanging silently,
    # and mark the atexit point (in finalise-stage.txt, so shutdown-stage.txt
    # still ends at process-exit) to locate it.
    import atexit
    atexit.register(_stage, capture_dir / "finalise-stage.txt", "atexit")
    faulthandler.dump_traceback_later(FINALISE_WATCHDOG_SECONDS, exit=True, file=fault_file)
    sys.exit(code)


def _flush_stdio() -> None:
    """Flush stdout/stderr when they exist. In the windowed frozen exe both are
    None, and calling .flush() on None would raise."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            try:
                stream.flush()
            except Exception:
                pass


# Interpreter-finalisation watchdog for the capture process only (see
# run_capture_and_exit). Well inside the 90s probe and 120s CI timeouts.
FINALISE_WATCHDOG_SECONDS = 20.0


def run_qt_app() -> None:
    set_high_dpi_rounding_policy()
    capture_dir = os.environ.get("ORBITRX_CAPTURE_DIR")
    if capture_dir:
        run_capture_and_exit(capture_dir)
        return  # pragma: no cover - unreachable, run_capture_and_exit always exits
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)
    win = QtOrbitRxApplication()
    win.setWindowIcon(_app_icon())
    win.run()
    sys.exit(app.exec())
