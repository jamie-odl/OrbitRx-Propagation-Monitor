from __future__ import annotations

import datetime
import json
import os
import threading
import time
from pathlib import Path

from PIL import Image

from orbitrx import __version__
from orbitrx.dx import verify_qrz_api
from orbitrx.map_renderer import MapLayers, MapRenderer
from orbitrx.propagation import HF_BANDS
from orbitrx.ui.band_panel import BandPanelWidget
from orbitrx.ui.controller import OrbitRxController
from orbitrx.ui.map_widget import PropagationMapWidget, QT_AVAILABLE
from orbitrx.spots.settings import clamp_poll_seconds
from orbitrx.ui.formatting import (
    widen_to_min_span,
    humanize_iso_dates, fmt,
    format_hour_offset, format_no_spots_message, format_replay_offset,
    history_plot_date_format, insert_gap_breaks, pad_datetime_range, EXPECTED_POLL_S,
)
from orbitrx.ui.rig_wizard import RigWizardDialog, populate_port_combo
from orbitrx.ui.theme import CARD_STYLE, CARD_TEXT, ERR, FONT_BODY, MUTED, MUTED_SECONDARY, OK, apply_theme
from orbitrx.ui.window_fit import fit_to_screen
from orbitrx.update_checker import check_github_release

if not QT_AVAILABLE:
    raise ImportError("PySide6 is required for the Qt UI")

from PySide6.QtCore import QDate, QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontMetrics, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QSizePolicy,
    QGridLayout,
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QSplitter, QStackedWidget, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget, QFileDialog,
    QSystemTrayIcon, QMenu,
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


class _ReflowGrid(QWidget):
    """A row of widgets (layer toggles, continent checkboxes) that reflows into
    fewer columns as it narrows, so it is always reachable by vertical scroll
    alone and never needs a horizontal scrollbar (M1)."""

    def __init__(
        self, widgets: list[QWidget], min_item_width: int, parent=None,
        min_cols: int = 1, max_cols: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._widgets = widgets
        self._min_item_width = max(1, min_item_width)
        self._min_cols = max(1, min_cols)
        self._max_cols = max_cols or (len(widgets) or 1)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(6)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._cols = 0
        self._relayout(self._columns_for_width(len(widgets) * min_item_width))

    def _columns_for_width(self, width: int) -> int:
        n = len(self._widgets) or 1
        fit = max(self._min_cols, min(self._max_cols, width // self._min_item_width))
        cols = max(1, min(n, fit))
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

    def _relayout(self, cols: int) -> None:
        self._cols = cols
        while self._grid.count():
            self._grid.takeAt(0)
        for i, w in enumerate(self._widgets):
            row, col = divmod(i, cols)
            self._grid.addWidget(w, row, col)


class _ElidedLabel(QLabel):
    """A label that elides its text on the right as it narrows, always exposing
    the untruncated text via its tooltip (M1)."""

    def setFullText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._reelide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reelide()

    def _reelide(self) -> None:
        text = getattr(self, "_full_text", "")
        fm = self.fontMetrics()
        super().setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, max(1, self.width())))


class _UiInvoker(QObject):
    """Runs callables on the Qt GUI thread (controller callbacks come from worker threads)."""

    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(lambda fn: fn(), Qt.ConnectionType.QueuedConnection)

    def wrap(self, fn):
        return lambda *args: self.call.emit(lambda: fn(*args))


class QtOrbitRxApplication(QMainWindow):
    def __init__(self) -> None:
        self._t_init_start = time.perf_counter()
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        self.setWindowTitle(f"OrbitRx Propagation Monitor {__version__}")
        self.renderer = MapRenderer(width=900, height=720)
        self._labels: dict[str, QLabel] = {}
        self._layer_checks: dict[str, QToolButton] = {}
        self._map_container: QWidget | None = None
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

        self._ui = _UiInvoker()
        ui = self._ui.wrap
        self.ctrl = OrbitRxController(
            on_status=ui(self._set_status),
            on_weather=ui(self._refresh_labels_and_map),
            on_dx=ui(self._refresh_labels_and_map),
            on_cluster=ui(self._set_cluster),
            on_alarm_excellent=ui(self._alarm_excellent),
            on_alarm_storm=ui(self._alarm_storm),
        )
        self.ctrl._on_band_beep = ui(self._spot_beep)
        self.ctrl.on_live_spots = ui(self._refresh_live_spots)

        geom = self.ctrl.cfg.get("window_geometry", "1400x820")
        self.resize(*self._parse_geom(geom))
        self._build_ui()
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

        self._cluster_pulse_phase = False
        self._cluster_pulse_timer = QTimer(self)
        self._cluster_pulse_timer.timeout.connect(self._tick_cluster_pulse)
        self._cluster_pulse_timer.start(700)

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

    def _build_ui(self) -> None:
        self._build_toolbar()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)

        map_pane = QWidget()
        map_layout = QVBoxLayout(map_pane)
        # P1: a bold header ("Map") plus a muted secondary hint line (file name/dims,
        # or an error) that elides on the right with the full text always available
        # as a tooltip.
        map_layout.setContentsMargins(16, 16, 16, 8)
        map_layout.setSpacing(8)
        header_row = QHBoxLayout()
        self.banner = QLabel("Loading map...")
        self.banner.setObjectName("panelTitle")
        self.banner.setWordWrap(False)
        header_row.addWidget(self.banner)
        header_row.addStretch(1)
        self._map_help = QToolButton()
        self._map_help.setText("?")
        self._map_help.setObjectName("helpChip")
        self._map_help.setToolTip(
            "Scroll to zoom · Right-drag to pan · Double-click to reset · Click a spot to tune"
        )
        self._map_help.setAutoRaise(True)
        header_row.addWidget(self._map_help)
        map_layout.addLayout(header_row)
        # M1: meta is the live greyline timestamp only - never the asset filename.
        self.banner_hint = _ElidedLabel()
        self.banner_hint.setObjectName("bannerHint")
        map_layout.addWidget(self.banner_hint)

        cluster_row = QHBoxLayout()
        cluster_row.addWidget(QLabel("Cluster:"))
        self.cluster_combo = QComboBox()
        self.cluster_combo.setMaximumWidth(420)
        self._populate_cluster_combo()
        self.cluster_combo.currentIndexChanged.connect(self._cluster_node_changed)
        cluster_row.addWidget(self.cluster_combo)
        cluster_row.addStretch(1)
        map_layout.addLayout(cluster_row)

        self.map_widget = self._create_map_widget()
        self.map_widget.spot_clicked.connect(self._tune_from_map)
        if hasattr(self.map_widget, "greyline_meta_changed"):
            self.map_widget.greyline_meta_changed.connect(self.banner_hint.setFullText)
        self.map_widget.map_clicked.connect(self._on_map_click)
        map_layout.addWidget(self.map_widget, stretch=1)

        # M3: layer chips (checkable pills) in one wrapping row. Live/Heat apply
        # to the native map's own live-spots layer (set_live_spots), same as
        # every other chip here.
        layer_widgets = []
        for key, label in [("greyline", "Greyline"), ("night", "Night"), ("dx_arcs", "DX"),
                           ("aurora", "Aurora"), ("grid", "Grid"),
                           ("spot_arcs", "Live"), ("spot_heatmap", "Heat")]:
            chip = QToolButton()
            chip.setText(label)
            chip.setCheckable(True)
            chip.setObjectName("layerChip")
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            chip.blockSignals(True)
            chip.setChecked(self.ctrl.cfg.get("map_layers", {}).get(key, key != "grid"))
            chip.blockSignals(False)
            self._layer_checks[key] = chip
            layer_widgets.append(chip)
        for chip in self._layer_checks.values():
            chip.toggled.connect(lambda _=False: self._layers_changed())
        self._layer_grid = _ReflowGrid(layer_widgets, min_item_width=72, max_cols=8)
        self._layer_grid.setMinimumHeight(36)
        self._layer_grid.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # V11 must-fix 3: chips live under the map pane (not inside it) so 150%
        # compact never paints them over Antarctica / greyline.

        # M1: the sliders live in a fixed strip below the map (added to
        # map_tab_layout, not map_layout), so they never scroll out of view even
        # when the window is too short to show everything above them at once.
        slider_strip = QWidget()
        slider_strip_layout = QVBoxLayout(slider_strip)
        slider_strip_layout.setContentsMargins(0, 4, 0, 0)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Time offset (hours):"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 48)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._slider_moved)
        slider_row.addWidget(self.time_slider)
        self.lbl_slider = QLabel(format_hour_offset(0))
        self.lbl_slider.setMinimumWidth(56)
        self.lbl_slider.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider_row.addWidget(self.lbl_slider)
        slider_strip_layout.addLayout(slider_row)

        replay_row = QHBoxLayout()
        replay_row.addWidget(QLabel("Spot replay (hours ago):"))
        self.replay_slider = QSlider(Qt.Orientation.Horizontal)
        self.replay_slider.setRange(0, 48)  # whole-hour steps, up to 48 hours ago
        self.replay_slider.setValue(0)
        self.replay_slider.setToolTip("0 = live. Drag left to right to replay cached PSKReporter spots.")
        self.replay_slider.valueChanged.connect(self._replay_moved)
        replay_row.addWidget(self.replay_slider)
        self.lbl_replay = QLabel("Live")
        self.lbl_replay.setMinimumWidth(56)
        self.lbl_replay.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        replay_row.addWidget(self.lbl_replay)
        slider_strip_layout.addLayout(replay_row)

        # M1: no scroll area around the map pane. The map stretches and shrinks so
        # the layer toggles and sliders stay visible without scrolling.
        self._map_scroll = None
        self._map_pane = map_pane

        map_tab = QWidget()
        map_tab_layout = QVBoxLayout(map_tab)
        map_tab_layout.setContentsMargins(0, 0, 0, 0)
        map_tab_layout.addWidget(map_pane, stretch=1)
        map_tab_layout.addWidget(self._layer_grid)
        map_tab_layout.addWidget(slider_strip)
        self._map_tab = map_tab

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # S3: the Stats tab below has its own scroll area; only one vertical scrollbar
        # should ever be visible in the right column, so this outer one stays off.
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._right_scroll = right_scroll
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_panel.setMinimumWidth(0)
        header_row = QHBoxLayout()
        self.last_updated_lbl = QLabel("Last updated: never")
        self.last_updated_lbl.setObjectName("muted")
        header_row.addWidget(self.last_updated_lbl, stretch=1)
        # N2: live cluster indicator, always visible at the top of the panel.
        self.cluster_live_lbl = QLabel("Cluster: connecting")
        self.cluster_live_lbl.setObjectName("muted")
        self.cluster_live_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.cluster_live_lbl)
        right_layout.addLayout(header_row)

        self.band_panel = BandPanelWidget()
        right_layout.addWidget(self.band_panel)

        self.tabs = QTabWidget()
        stats_tab = QWidget()
        stats_outer = QVBoxLayout(stats_tab)

        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setFrameShape(QFrame.Shape.NoFrame)
        stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._stats_scroll = stats_scroll
        stats_form_widget = QWidget()
        stats_form = QFormLayout(stats_form_widget)
        stats_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        stats_form.setHorizontalSpacing(12)
        stats_form.setVerticalSpacing(8)
        stats_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # M4: labelled definition-list groups (SPACE WEATHER / PROPAGATION / PATH / OPS).
        space_keys = ["kp", "kp_forecast", "solar", "sunspot", "a_index", "solar_wind", "time"]
        prop_keys = ["bands", "muf", "hamqsl"]
        location_keys = ["path_muf", "sunrise", "sunset", "location"]
        late_keys = ["cluster", "solar_forecast", "contest", "dx"]
        pretty = {
            "kp": "Kp", "kp_forecast": "Kp forecast", "solar": "Solar flux",
            "sunspot": "Sunspot", "a_index": "A-index", "solar_wind": "Solar wind",
            "time": "UTC", "bands": "Bands", "muf": "MUF", "hamqsl": "HamQSL",
            "path_muf": "Path MUF", "sunrise": "Sunrise", "sunset": "Sunset",
            "location": "You", "cluster": "Cluster", "solar_forecast": "Forecast",
            "contest": "Contest", "dx": "DX",
        }
        for key in space_keys + prop_keys + location_keys + late_keys:
            lbl = QLabel("--")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("padding: 2px; font-weight: 600; ")
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._labels[key] = lbl
            if key == "solar":
                lbl.setToolTip("Change vs previous reading")

        def _section(title: str) -> None:
            hdr = QLabel(title)
            hdr.setObjectName("sectionLabel")
            stats_form.addRow(hdr)

        def _add_keys(keys: list[str]) -> None:
            for key in keys:
                name = QLabel(pretty.get(key, key))
                name.setObjectName("muted")
                name.setMinimumWidth(110)
                stats_form.addRow(name, self._labels[key])

        _section("SPACE WEATHER")
        _add_keys(space_keys)
        _section("PROPAGATION")
        _add_keys(prop_keys)
        _section("PATH")
        self._location_hint_lbl = QLabel(
            'Set your location to unlock path MUF and sun times. <a href="#">Location</a>'
        )
        self._location_hint_lbl.setWordWrap(True)
        self._location_hint_lbl.setObjectName("muted")
        self._location_hint_lbl.setStyleSheet(
            "background: #1A2438; border: 1px solid #243044; border-radius: 10px; padding: 12px;"
        )
        self._location_hint_lbl.linkActivated.connect(lambda _: self.ctrl.refresh_location())
        self._location_hint_lbl.setVisible(False)
        stats_form.addRow(self._location_hint_lbl)
        _add_keys(location_keys)
        _section("OPS")
        _add_keys(late_keys)
        stats_scroll.setWidget(stats_form_widget)
        stats_outer.addWidget(stats_scroll, stretch=1)

        stats_outer.addWidget(QLabel("Alerts"))
        self.alerts_list = QListWidget()
        self.alerts_list.setMaximumHeight(90)
        self.alerts_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.alerts_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.alerts_list.setWordWrap(False)
        self.alerts_list.setUniformItemSizes(True)
        stats_outer.addWidget(self.alerts_list)
        self.tabs.addTab(stats_tab, "Stats")

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
        right_scroll.setWidget(right_panel)

        # M1: action buttons live in the top toolbar (see _build_toolbar), not here,
        # so the side panel only needs its own vertical scroll for the band
        # tiles/tabs above.
        side_scroll = QScrollArea()
        side_scroll.setObjectName("sidePaneScroll")
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_scroll_body = QWidget()
        side_scroll_body_layout = QVBoxLayout(side_scroll_body)
        side_scroll_body_layout.setContentsMargins(0, 0, 0, 0)
        side_scroll_body_layout.addWidget(right_scroll, stretch=1)
        side_scroll.setWidget(side_scroll_body)
        self._side_scroll = side_scroll

        side_pane = QWidget()
        side_pane.setMinimumWidth(260)
        side_pane_layout = QVBoxLayout(side_pane)
        side_pane_layout.setContentsMargins(0, 0, 0, 0)
        side_pane_layout.addWidget(side_scroll)
        self._side_pane = side_pane

        # M1: side-by-side by default (map:side = 3:1); below COMPACT_WIDTH_BELOW
        # logical px, _update_compact_mode() swaps to the Map/Conditions tabs
        # instead (see resizeEvent).
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._map_tab)
        side_pane.setMinimumWidth(280)
        side_pane.setMaximumWidth(360)
        self._splitter.addWidget(side_pane)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setSizes([900, 320])

        self._compact_tabs = QTabWidget()
        self._compact_tabs.setObjectName("compactTabs")
        self._compact_tabs.hide()

        outer.addWidget(self._splitter)
        self._compact = False
        self._update_compact_mode()

    def _build_toolbar(self) -> None:
        """Primary: Settings · Rig · About · Location · Weather. Export behind » menu
        (V11 must-fix 5) so overflow is always explicit and working."""
        from PySide6.QtWidgets import QMenu

        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        toolbar.setIconSize(toolbar.iconSize())  # keep density
        self.addToolBar(toolbar)
        self._toolbar = toolbar
        self._toolbar_actions: dict[str, QAction] = {}
        for text, slot in [
            ("Settings", self._settings),
            ("Rig", self._rig_wizard),
            ("About", self._about),
            ("Location", self.ctrl.refresh_location),
            ("Weather", self.ctrl.fetch_weather),
        ]:
            action = QAction(text, self)
            action.triggered.connect(slot)
            toolbar.addAction(action)
            self._toolbar_actions[text] = action
        toolbar.addSeparator()
        export_btn = QToolButton(toolbar)
        export_btn.setObjectName("toolbarOverflow")
        export_btn.setText("»")
        export_btn.setToolTip("Export")
        export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        export_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        export_menu = QMenu(export_btn)
        for text, slot in [
            ("Export snapshot", self._export_json),
            ("Export DX CSV", self._export_dx),
        ]:
            # Hidden toolbar QAction keeps tests/controls_reachable happy; a separate
            # menu QAction stays visible under » (sharing one action would hide both).
            tb_action = QAction(text, self)
            tb_action.triggered.connect(slot)
            tb_action.setPriority(QAction.Priority.LowPriority)
            tb_action.setVisible(False)
            toolbar.addAction(tb_action)
            self._toolbar_actions[text] = tb_action
            menu_action = QAction(text, self)
            menu_action.triggered.connect(slot)
            export_menu.addAction(menu_action)
        export_btn.setMenu(export_menu)
        toolbar.addWidget(export_btn)
        self._toolbar_overflow = export_btn
        self._hide_export_toolbar_buttons()

    def _hide_export_toolbar_buttons(self) -> None:
        """Export actions stay on the toolbar (tests) but only the » menu shows them."""
        for name in ("Export snapshot", "Export DX CSV"):
            action = self._toolbar_actions.get(name)
            if action is None:
                continue
            btn = self._toolbar.widgetForAction(action)
            if btn is not None:
                btn.setVisible(False)
        overflow = getattr(self, "_toolbar_overflow", None)
        if overflow is not None:
            overflow.setVisible(True)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._hide_export_toolbar_buttons()

    def controls_reachable(self) -> dict[str, bool]:
        """Primary toolbar actions visible; Export actions reachable via the » menu."""
        overflow = getattr(self, "_toolbar_overflow", None)
        overflow_ok = bool(overflow and overflow.isVisible())
        ext_button = self._toolbar.findChild(QWidget, "qt_toolbar_ext_button")
        qt_overflow = bool(ext_button and ext_button.isVisible())
        result = {}
        for name, action in self._toolbar_actions.items():
            if name.startswith("Export"):
                result[name] = overflow_ok or qt_overflow
                continue
            widget = self._toolbar.widgetForAction(action)
            result[name] = bool(widget and widget.isVisible()) or qt_overflow
        return result

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

        self.banner.setText("Map")
        self.banner_hint.setFullText("loading...")
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
            except Exception as exc:
                on_failed(exc)
            else:
                on_loaded(scaled)

        threading.Thread(target=worker, daemon=True, name="map-load").start()

    def _on_map_loaded(self, scaled_image) -> None:
        self.renderer.set_prescaled_base_map(scaled_image)
        self.map_widget.set_base_map(self.renderer.base_rgba_image())
        # M1: never print the asset filename in the UI.
        self._map_label = "Map · offline basemap"
        self.banner.setText("Map")
        self.banner_hint.setFullText("")

    def _on_map_load_failed(self, exc: Exception) -> None:
        self.renderer.set_base_map(None)
        if hasattr(self.map_widget, "set_base_map"):
            self.map_widget.set_base_map(self.renderer.base_rgba_image())
        self._map_label = f"Map FAILED: {exc}"
        self.banner.setText(self._map_label)
        self.banner_hint.setFullText("")
        self.banner.setProperty("state", "error")
        self.banner.style().polish(self.banner)

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
            "kp": "Kp: ", "kp_forecast": "Kp Forecast: ", "solar": "Solar Flux: ",
            "sunspot": "Sunspot: ", "a_index": "A-index: ", "solar_wind": "Wind: ",
            "time": "NOAA data: ", "bands": "Bands: ", "muf": "MUF: ",
            "path_muf": "Path MUF: ", "sunrise": "Sunrise: ", "sunset": "Sunset: ",
            "location": "You: ", "cluster": "Cluster: ",
        }
        for k, v in labels.items():
            if k in self._labels:
                prefix = strip_map.get(k)
                if prefix and v.startswith(prefix):
                    v = v[len(prefix):]
                self._labels[k].setText(v)
        self._update_location_hint_visibility()
        self.alerts_list.clear()
        for alert in self.ctrl.state.alerts[:5] or ["No active alerts"]:
            item = QListWidgetItem(humanize_iso_dates(alert))
            item.setToolTip(humanize_iso_dates(alert))
            self.alerts_list.addItem(item)
        self._render_cluster_label()
        self.band_panel.update_grid(self.ctrl.state.band_grid)
        self.last_updated_lbl.setText(self.ctrl.last_updated_text())
        self._refresh_map()

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
        QMessageBox.information(self, "CAT", result)

    def _set_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def _set_cluster(self, status: str) -> None:
        self.ctrl.state.cluster_status = status
        self._render_cluster_label()

    def _tick_cluster_pulse(self) -> None:
        self._cluster_pulse_phase = not self._cluster_pulse_phase
        if self.ctrl.state.cluster_status == "connected":
            self._render_cluster_label()

    def _render_cluster_label(self) -> None:
        status = self.ctrl.state.cluster_status
        if status == "connected":
            dot_color = "#81C784" if self._cluster_pulse_phase else "#2E7D32"
            text = f'<span style="color:{dot_color}">●</span> Cluster: live'
            self._labels["cluster"].setText(f'<span style="color:{dot_color}">●</span> Cluster: connected')
        else:
            text = f"Cluster: {status}"
            self._labels["cluster"].setText(text)
        if hasattr(self, "cluster_live_lbl"):
            self.cluster_live_lbl.setText(text)

    def _update_location_hint_visibility(self) -> None:
        """M5: path_muf/sunrise/sunset only mean anything once a location is set;
        otherwise show the single explanatory line instead of three "n/a" rows."""
        has_location = self.ctrl.state.user_lat is not None and self.ctrl.state.user_lon is not None
        for key in ("path_muf", "sunrise", "sunset", "location"):
            if key in self._labels:
                self._labels[key].setVisible(has_location)
        self._location_hint_lbl.setVisible(not has_location)

    def _spot_beep(self, spot: dict) -> None:
        self.ctrl.spot_beep(spot)
        self._refresh_map(vectors_only=True)

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
        self.ctrl.fetch_weather()
        self._refresh_labels_and_map()
        elapsed_ms = (time.perf_counter() - self._t_init_start) * 1000
        self.ctrl.log.info("perf: cold_start_to_startup_complete_ms=%.1f", elapsed_ms)

    def _auto_refresh(self) -> None:
        self.ctrl.state.prune_dx_spots()
        self.ctrl.refresh_location()
        self.ctrl.fetch_weather()

    def _check_updates(self) -> None:
        # check_github_release does a blocking network call (10s timeout) --
        # never run it on the UI thread, or a slow/unreachable GitHub freezes
        # the whole window for up to that long.
        on_done = self._ui.wrap(self._show_update_available)

        def worker() -> None:
            info = check_github_release(__version__)
            if info.get("update_available"):
                on_done(info)

        threading.Thread(target=worker, daemon=True, name="update-check").start()

    def _show_update_available(self, info: dict) -> None:
        QMessageBox.information(
            self, "Update Available",
            f"{info['message']}\n\nDownload: {info['url']}",
        )

    def _export_json(self) -> None:
        p = self.ctrl.export_json()
        QMessageBox.information(self, "Export", f"Saved {p}")

    def _export_dx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export DX", "dx_spots.csv", "CSV (*.csv)")
        if path:
            self.ctrl.store.export_dx_csv(Path(path))
            QMessageBox.information(self, "Export", f"Saved {path}")

    def _rig_wizard(self) -> None:
        dlg = RigWizardDialog(self.ctrl.cfg, self.ctrl.cat, self)
        dlg.exec()

    def _refresh_plot_tab(self) -> None:
        if not PLOT_QT:
            self.plot_placeholder.setText("matplotlib Qt backend required")
            return
        q = self.hist_date.date().toString("yyyy-MM-dd")
        try:
            rows = self.ctrl.store.query_propagation(q)
        except ValueError as e:
            self.plot_placeholder.setText(str(e))
            return
        if not rows:
            self.plot_placeholder.setText("No data for this date range")
            return
        while self.plot_container.count():
            item = self.plot_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
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
            canvas = FigureCanvas(fig)
            self.plot_container.addWidget(canvas)
            return

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
        poll_interval_s = float(self.ctrl.cfg.get("refresh_interval_seconds", EXPECTED_POLL_S))
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
        canvas = FigureCanvas(fig)
        self.plot_container.addWidget(canvas)
        save_btn = QPushButton("Save PNG", clicked=lambda: self._save_fig(fig))
        self.plot_container.addWidget(save_btn)

    def _save_fig(self, fig) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "history.png", "PNG (*.png)")
        if path:
            fig.savefig(path, dpi=150, facecolor="#0B1220")
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
        fields["home_lat"].setSpecialValueText("n/a")
        fields["home_lat"].setMinimumHeight(30)  # M3: room for both spin arrows
        fields["home_lat"].setValue(float(cfg.get("home_lat") or -90.0) if cfg.get("home_lat") is not None else -90.0)
        self._add_settings_row(station, "Home latitude", fields["home_lat"])
        fields["home_lon"] = QDoubleSpinBox()
        fields["home_lon"].setRange(-180.0, 180.0)
        fields["home_lon"].setDecimals(4)
        fields["home_lon"].setSpecialValueText("n/a")
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
        test_cat_result = QLabel("")
        test_cat_result.setWordWrap(True)

        def do_test_cat() -> None:
            cfg.data["cat_port"] = (fields["cat_port"].currentData() or fields["cat_port"].currentText()).strip()
            cfg.data["cat_baud"] = int(fields["cat_baud"].currentText())
            cfg.data["cat_rig_profile"] = fields["cat_rig_profile"].currentText()
            result = self.ctrl.cat.tune(14.200, confirm=None)
            test_cat_result.setText(result)
            test_cat_result.setStyleSheet(f"color: {OK if 'Sent CAT' in result else ERR};")

        test_cat_btn.clicked.connect(do_test_cat)
        test_cat_row.addWidget(test_cat_btn)
        test_cat_row.addWidget(test_cat_result, stretch=1)
        rig.addRow("", test_cat_row)

        # --- DX cluster ---
        dxc = self._add_form_page(page_list, stack, "DX cluster")
        fields["dx_cluster_callsign"] = QLineEdit(str(cfg.get("dx_cluster_callsign", "") or ""))
        self._add_settings_row(dxc, "Cluster callsign", fields["dx_cluster_callsign"])
        fields["target_dx_callsign"] = QLineEdit(str(cfg.get("target_dx_callsign", "") or ""))
        self._add_settings_row(dxc, "Target DX callsign", fields["target_dx_callsign"])
        fields["target_dx_lat"] = QDoubleSpinBox()
        fields["target_dx_lat"].setRange(-90.0, 90.0)
        fields["target_dx_lat"].setDecimals(4)
        fields["target_dx_lat"].setSpecialValueText("n/a")
        fields["target_dx_lat"].setMinimumHeight(30)
        fields["target_dx_lat"].setValue(float(cfg.get("target_dx_lat") or -90.0) if cfg.get("target_dx_lat") is not None else -90.0)
        self._add_settings_row(dxc, "Target latitude", fields["target_dx_lat"])
        fields["target_dx_lon"] = QDoubleSpinBox()
        fields["target_dx_lon"].setRange(-180.0, 180.0)
        fields["target_dx_lon"].setDecimals(4)
        fields["target_dx_lon"].setSpecialValueText("n/a")
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
        fields = dlg.fields
        cfg = self.ctrl.cfg
        cfg.set("spots_callsign", fields["spots_callsign"].text().strip())
        cfg.set("home_lat", None if fields["home_lat"].value() == -90.0 else fields["home_lat"].value())
        cfg.set("home_lon", None if fields["home_lon"].value() == -180.0 else fields["home_lon"].value())
        cfg.set("ip_geolocation_enabled", fields["ip_geolocation_enabled"].isChecked())
        cfg.set("cat_port", (fields["cat_port"].currentData() or fields["cat_port"].currentText()).strip())
        cfg.set("cat_baud", int(fields["cat_baud"].currentText()))
        cfg.set("cat_rig_profile", fields["cat_rig_profile"].currentText())
        cfg.set("rig_control", fields["rig_control"].currentData())
        cfg.set("dx_cluster_callsign", fields["dx_cluster_callsign"].text().strip())
        cfg.set("target_dx_callsign", fields["target_dx_callsign"].text().strip())
        cfg.set("target_dx_lat", None if fields["target_dx_lat"].value() == -90.0 else fields["target_dx_lat"].value())
        cfg.set("target_dx_lon", None if fields["target_dx_lon"].value() == -180.0 else fields["target_dx_lon"].value())
        cfg.set("dx_filter_bands_mhz", [f for f, cb in dlg.band_checks.items() if cb.isChecked()])
        cfg.set("dx_filter_continents", [c for c, cb in dlg.cont_checks.items() if cb.isChecked()])
        cfg.set("spots_mode", fields["spots_mode"].currentText())
        cfg.set("pskreporter_poll_seconds", clamp_poll_seconds(fields["pskreporter_poll_seconds"].value()))
        cfg.set("qrz_api_key", fields["qrz_api_key"].text().strip())
        cfg.set("refresh_interval_seconds", fields["refresh_interval_seconds"].value())
        self._timer.setInterval(int(cfg.get("refresh_interval_seconds", 60)) * 1000)
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

    def _apply_map_min_height(self) -> None:
        """N6 / M9.3: in compact Map tab, keep the map at least ~40% of the
        central height so 150%/1024 does not shrink it to a tiny thumbnail."""
        central = self.centralWidget()
        if central is None or not hasattr(self, "map_widget"):
            return
        ratio = 0.42 if self._compact else 0.48
        target = max(160, int(central.height() * ratio))
        if self._compact:
            # Leave room for layer chips (min 36) + slider strip (~72) under the map.
            reserve = 36 + 72 + 24
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

    def _enter_compact_mode(self) -> None:
        self._compact = True
        central_layout = self.centralWidget().layout()
        central_layout.removeWidget(self._splitter)
        self._splitter.hide()
        self._compact_tabs.addTab(self._map_tab, "Map")
        self._compact_tabs.addTab(self._side_pane, "Conditions")
        central_layout.addWidget(self._compact_tabs)
        self._compact_tabs.show()

    def _exit_compact_mode(self) -> None:
        self._compact = False
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
        self.ctrl.stop()
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

    # Leave QApplication alive so in-process tests can keep using it. The
    # process entry point deletes it before exit. See finish note on
    # exit_after_qapplication_deleted.
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
    for name in ("_timer", "_cluster_pulse_timer"):
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


def exit_after_qapplication_deleted(exit_code: int, stage_log: Path | None) -> None:
    """Delete QApplication, then end the process.

    Actions run 42359055614 wrote the static-map screenshots and then exited
    -1073741819 (0xC0000005). That capture called os._exit while QApplication
    still existed; back then, the leaflet import loaded Qt WebEngine even for
    the static map, and ExitProcess faulted in Qt6WebEngineCore unless the
    application object was destroyed first. Qt WebEngine is gone now (Option
    B, 2026-11-09), but deleting the QApplication before os._exit is still
    correct practice, so this keeps doing it. This does not return.
    """
    try:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
            _delete_qt_object(app)
        _stage(stage_log, "qapplication-deleted")
    except Exception as exc:
        import sys
        _stage(stage_log, f"exception:{type(exc).__name__}: {exc}")
        sys.stderr.write(f"capture shutdown failed: {type(exc).__name__}: {exc}\n")
        os._exit(4)
    _stage(stage_log, "process-exit")
    os._exit(exit_code)


def run_qt_app() -> None:
    import sys
    capture_dir = os.environ.get("ORBITRX_CAPTURE_DIR")
    if capture_dir:
        import threading
        watchdog = threading.Timer(60.0, lambda: os._exit(3))  # capture never hangs CI
        watchdog.daemon = True
        watchdog.start()
        code = run_release_capture_hook(capture_dir)
        sys.stdout.flush()
        exit_after_qapplication_deleted(code, Path(capture_dir) / "shutdown-stage.txt")
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)
    win = QtOrbitRxApplication()
    win.setWindowIcon(_app_icon())
    win.run()
    sys.exit(app.exec())
