from __future__ import annotations

import datetime
import json
import os
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
    humanize_iso_dates,
    format_hour_offset, format_no_spots_message, format_replay_offset,
    history_plot_date_format, insert_gap_breaks, pad_datetime_range,
)
from orbitrx.ui.rig_wizard import RigWizardDialog, populate_port_combo
from orbitrx.ui.theme import ERR, MUTED, OK, apply_theme
from orbitrx.ui.window_fit import fit_to_screen
from orbitrx.update_checker import check_github_release

try:
    from orbitrx.ui.leaflet_map import WEBENGINE_AVAILABLE, LeafletMapWidget
except ImportError:
    WEBENGINE_AVAILABLE = False
    LeafletMapWidget = None

if not QT_AVAILABLE:
    raise ImportError("PySide6 is required for the Qt UI")

from PySide6.QtCore import QDate, QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QSizePolicy,
    QGridLayout,
    QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QStackedWidget, QTabWidget, QVBoxLayout, QWidget, QFileDialog,
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

# S4: a one-line description at the top of every Settings page, so a page with only
# one or two controls still reads as a deliberate, populated screen.
SETTINGS_PAGE_DESCRIPTIONS = {
    "Station": "Your callsign and home coordinates, used to centre the map and tag your spots.",
    "Rig": "Connect to your radio over CAT so clicking a spot on the map can tune it for you.",
    "DX cluster": "Pick a cluster node and filter which DX spots show up on the map.",
    "Map & spots": "Choose the map backend and how often live spots refresh from PSKReporter.",
    "Services": "Optional QRZ lookups and how often space weather data refreshes.",
}


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
        super().__init__()
        apply_theme()
        self.setWindowTitle(f"OrbitRx Propagation Monitor {__version__}")
        self.renderer = MapRenderer(width=900, height=720)
        self._labels: dict[str, QLabel] = {}
        self._layer_checks: dict[str, QCheckBox] = {}
        self._map_container: QWidget | None = None
        self._tray: QSystemTrayIcon | None = None

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

        cfg_backend = self.ctrl.cfg.get("map_backend", "static")
        if cfg_backend == "leaflet" and not self._leaflet_available():
            cfg_backend = "static"
        self._map_backend = cfg_backend

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

    def _leaflet_available(self) -> bool:
        return bool(WEBENGINE_AVAILABLE and LeafletMapWidget)

    def _parse_geom(self, g: str) -> tuple[int, int]:
        try:
            w, h = g.split("x")
            return int(w), int(h)
        except Exception:
            return 1400, 820

    def _create_map_widget(self):
        if self._map_backend == "leaflet" and self._leaflet_available():
            return LeafletMapWidget(self.renderer)
        return PropagationMapWidget(self.renderer)

    def _build_ui(self) -> None:
        central = QWidget()
        # M3 (V7): on a small or scaled-up screen the window is clamped to the
        # available geometry; if the content's minimum is still larger, the whole
        # content scrolls instead of running off the screen edge.
        central_scroll = QScrollArea()
        central_scroll.setObjectName("centralScroll")
        central_scroll.setWidgetResizable(True)
        central_scroll.setFrameShape(QFrame.Shape.NoFrame)
        central_scroll.setWidget(central)
        self._central_scroll = central_scroll
        self.setCentralWidget(central_scroll)
        root = QHBoxLayout(central)

        left = QVBoxLayout()
        self.banner = QLabel("Loading map...")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        left.addWidget(self.banner)

        cluster_row = QHBoxLayout()
        cluster_row.addWidget(QLabel("Cluster:"))
        self.cluster_combo = QComboBox()
        self._populate_cluster_combo()
        self.cluster_combo.currentIndexChanged.connect(self._cluster_node_changed)
        cluster_row.addWidget(self.cluster_combo, stretch=1)
        left.addLayout(cluster_row)

        self.map_widget = self._create_map_widget()
        self.map_widget.spot_clicked.connect(self._tune_from_map)
        self.map_widget.map_clicked.connect(self._on_map_click)
        left.addWidget(self.map_widget, stretch=1)

        layer_row = QHBoxLayout()
        for key, label in [("greyline", "Greyline"), ("night", "Night"), ("dx_arcs", "DX"),
                           ("aurora", "Aurora"), ("grid", "Grid"),
                           ("spot_arcs", "Live spots"), ("spot_heatmap", "Heatmap")]:
            cb = QCheckBox(label)
            cb.setChecked(self.ctrl.cfg.get("map_layers", {}).get(key, key != "grid"))
            cb.stateChanged.connect(self._layers_changed)
            if key.startswith("spot_") and self._map_backend != "leaflet":
                cb.setEnabled(False)
                cb.setToolTip("Live spots need the interactive map. Switch in Settings > Map & spots.")
            self._layer_checks[key] = cb
            layer_row.addWidget(cb)
        if self._map_backend != "leaflet":
            switch_lbl = QLabel('<a href="#">Switch map</a>')
            switch_lbl.setObjectName("muted")
            switch_lbl.setToolTip("Live spots need the interactive map. Switch in Settings > Map & spots.")
            switch_lbl.linkActivated.connect(lambda _: self._settings(initial_page="Map & spots"))
            layer_row.addWidget(switch_lbl)
        left.addLayout(layer_row)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Time offset (hours):"))
        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 48)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._slider_moved)
        slider_row.addWidget(self.time_slider)
        self.lbl_slider = QLabel(format_hour_offset(0))
        self.lbl_slider.setFixedWidth(56)
        self.lbl_slider.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider_row.addWidget(self.lbl_slider)
        left.addLayout(slider_row)

        replay_row = QHBoxLayout()
        replay_row.addWidget(QLabel("Spot replay (hours ago):"))
        self.replay_slider = QSlider(Qt.Orientation.Horizontal)
        self.replay_slider.setRange(0, 48)  # whole-hour steps, up to 48 hours ago
        self.replay_slider.setValue(0)
        self.replay_slider.setToolTip("0 = live. Drag left to right to replay cached PSKReporter spots.")
        self.replay_slider.valueChanged.connect(self._replay_moved)
        replay_row.addWidget(self.replay_slider)
        self.lbl_replay = QLabel("Live")
        self.lbl_replay.setFixedWidth(56)
        self.lbl_replay.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        replay_row.addWidget(self.lbl_replay)
        left.addLayout(replay_row)
        root.addLayout(left, stretch=3)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(320)
        right_scroll.setMaximumWidth(420)
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
        stats_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key in [
            # S6: "band_grid" is deliberately absent - the band_panel tiles above are the
            # single source for per-band conditions, so there is no second wrapping line.
            "kp", "kp_forecast", "solar", "sunspot", "a_index", "solar_wind", "time",
            "bands", "muf", "path_muf", "hamqsl", "sunrise", "sunset",
            "location", "cluster", "solar_forecast", "contest", "dx",
        ]:
            lbl = QLabel(f"{key}: --")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("padding: 2px;")
            self._labels[key] = lbl
            if key == "solar":
                lbl.setToolTip("Change vs previous reading")
            stats_form.addRow(lbl)
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

        btn_row = QGridLayout()
        btn_row.setSpacing(6)
        action_buttons = [
            ("Location", self.ctrl.refresh_location),
            ("Weather", self.ctrl.fetch_weather),
            ("Settings", self._settings),
            ("Rig", self._rig_wizard),
            ("Export snapshot", self._export_json),
            ("Export DX CSV", self._export_dx),
            ("About", self._about),
        ]
        # Two evenly filled rows (4 + 3), each button stretched to the row width,
        # so there is no hole and labels are never clipped (N-new-5).
        rows = [action_buttons[:4], action_buttons[4:]]
        for r, row_items in enumerate(rows):
            for c, (text, slot) in enumerate(row_items):
                btn = QPushButton(text, clicked=slot)
                btn.setMinimumWidth(btn.fontMetrics().horizontalAdvance(text) + 24)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn_row.addWidget(btn, r, c * 12 // len(row_items), 1, 12 // len(row_items))
        right_layout.addStretch()
        right_scroll.setWidget(right_panel)
        # Action buttons sit below the scroll area so they are always visible.
        right_column = QWidget()
        right_column.setMinimumWidth(400)
        right_column.setMaximumWidth(420)
        right_col_layout = QVBoxLayout(right_column)
        right_col_layout.setContentsMargins(0, 0, 0, 0)
        right_col_layout.addWidget(right_scroll, stretch=1)
        right_col_layout.addLayout(btn_row)
        root.addWidget(right_column, stretch=1)

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
        from orbitrx.paths import ensure_map_image

        self._map_label = "Map: loading..."
        try:
            if self._map_backend == "leaflet":
                self._map_label = "Interactive map · OpenStreetMap"
                self.banner.setText(self._map_label)
                return
            map_path = ensure_map_image()
            if not map_path.is_file():
                raise FileNotFoundError(f"world_map.jpg not found at {map_path}")
            img = Image.open(map_path)
            img.load()
            self.renderer.set_base_map(img)
            self.map_widget.set_base_map(self.renderer.base_rgba_image())
            self._map_label = f"Static map · {map_path.name} ({img.width}×{img.height})"
            self.banner.setText(self._map_label)
        except Exception as e:
            self.renderer.set_base_map(None)
            if hasattr(self.map_widget, "set_base_map"):
                self.map_widget.set_base_map(self.renderer.base_rgba_image())
            self._map_label = f"Map FAILED: {e}"
            self.banner.setText(self._map_label)
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
        self.lbl_replay.setText(format_replay_offset(val))
        self._refresh_live_spots()

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
        for k, v in labels.items():
            if k in self._labels:
                self._labels[k].setText(v)
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
        ml = {k: cb.isChecked() for k, cb in self._layer_checks.items()}
        self.ctrl.cfg.data["map_layers"] = ml
        self.ctrl.cfg.save()
        self._refresh_map()

    def _slider_moved(self, val: int) -> None:
        self.ctrl.state.slider_offset_hours = float(val)
        self.lbl_slider.setText(format_hour_offset(val))
        self._refresh_map()

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

    def _spot_beep(self, spot: dict) -> None:
        self.ctrl.spot_beep(spot)
        self._refresh_map(vectors_only=True)

    def _alarm_excellent(self) -> None:
        QMessageBox.information(
            self, "Propagation Alarm",
            f"Excellent conditions! Kp {self.ctrl.state.kp_index}  MUF {self.ctrl.state.muf} MHz",
        )

    def _alarm_storm(self) -> None:
        QMessageBox.warning(self, "Storm Warning", f"Geomagnetic storm: Kp {self.ctrl.state.kp_index}")

    def _startup(self) -> None:
        self.ctrl.refresh_location()
        self.ctrl.fetch_weather()
        self._refresh_labels_and_map()

    def _auto_refresh(self) -> None:
        self.ctrl.state.prune_dx_spots()
        self.ctrl.refresh_location()
        self.ctrl.fetch_weather()

    def _check_updates(self) -> None:
        info = check_github_release(__version__)
        if info.get("update_available"):
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
            locator = AutoDateLocator(maxticks=7)
        else:
            # "dd MMM" daily ticks: one tick per day (or fewer) so they never overlap.
            locator = DayLocator(interval=max(1, round(span_h / 24 / 3)))
        ax.xaxis.set_major_locator(locator)
        # M4/S3: HH:mm within a day, "dd MMM HH:mm" up to 36 h, then date-only "dd MMM"
        # daily ticks so labels never repeat "00:00".
        ax.xaxis.set_major_formatter(DateFormatter(history_plot_date_format(lo, hi)))
        ax.set_xlim(lo, hi)

        # S3: break the line (insert a NaN) across any gap more than 3x the median
        # sampling interval, instead of drawing a straight jump across missing data.
        kp_times, kp_gapped = insert_gap_breaks(times, kp)
        flux_times, flux_gapped = insert_gap_breaks(times, flux)

        kp_line, = ax.plot(kp_times, kp_gapped, label="Kp", marker="o", linestyle="-", color="#64B5F6")
        ax.set_ylabel("Kp", color="#64B5F6")
        ax.set_ylim(0, 9)
        ax.yaxis.set_ticks(range(0, 10))

        ax2 = ax.twinx()
        sfi_line, = ax2.plot(flux_times, flux_gapped, label="SFI", marker="o", linestyle="-", color="#FFD54F")
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
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_body = QWidget()
        body = QHBoxLayout(scroll_body)
        scroll.setWidget(scroll_body)
        outer.addWidget(scroll, stretch=1)

        page_list = QListWidget()
        page_list.setFixedWidth(180)
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
        cont_layout = QHBoxLayout(cont_box)
        cont_checks: dict[str, QCheckBox] = {}
        current_cont = set(cfg.get("dx_filter_continents") or [])
        for code, label in CONTINENT_OPTS:
            cb = QCheckBox(code)
            cb.setToolTip(label)
            cb.setChecked(code in current_cont)
            cont_checks[code] = cb
            cont_layout.addWidget(cb)
        dxc.addRow(cont_box)

        # --- Map & spots ---
        map_page = self._add_form_page(page_list, stack, "Map & spots")
        map_backend = QComboBox()
        map_backend.addItem("Static world map (works offline)", "static")
        if self._leaflet_available():
            map_backend.addItem("Interactive map with live spots (needs internet)", "leaflet")
        idx = map_backend.findData(cfg.get("map_backend", "static"))
        if idx >= 0:
            map_backend.setCurrentIndex(idx)
        fields["map_backend"] = map_backend
        self._add_settings_row(map_page, "Map backend", map_backend)
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
        new_backend = fields["map_backend"].currentData()
        if new_backend != self._map_backend:
            cfg.set("map_backend", new_backend)
            QMessageBox.information(self, "Map backend", "Map backend changed. Restart OrbitRx to apply.")
        self._timer.setInterval(int(cfg.get("refresh_interval_seconds", 60)) * 1000)
        self._populate_cluster_combo()

    def _settings(self, *, initial_page: str | None = None) -> None:
        dlg = self._build_settings_dialog(initial_page=initial_page)
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
        self.ctrl.cfg.set("window_geometry", f"{self.width()}x{self.height()}")
        self.ctrl.stop()
        super().closeEvent(event)

    def run(self) -> None:
        self.show()


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

    wizard = RigWizardDialog(win.ctrl.cfg, win.ctrl.cat, win)
    wizard.show()
    wait(0.2)
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
    wait(0.3)
    fg = settings_dlg.frameGeometry()
    app.primaryScreen().grabWindow(0, fg.x(), fg.y(), fg.width(), fg.height()).save(
        str(out_dir / "settings-dx-cluster.png")
    )
    # Whole Settings dialog (list + pages + the pinned Save/Cancel row) after
    # fit_to_screen, so a release build's capture has direct evidence Save is
    # still on-screen even on a small/scaled-up display.
    app.primaryScreen().grabWindow(0, fg.x(), fg.y(), fg.width(), fg.height()).save(
        str(out_dir / "settings-full.png")
    )
    # Whole-desktop grab: shows the dialog's position relative to the real screen edges.
    app.primaryScreen().grabWindow(0).save(str(out_dir / "desktop-settings.png"))
    save_visible = _save_button_fully_visible(settings_dlg)
    settings_on_screen = settings_dlg.screen().availableGeometry().contains(settings_dlg.frameGeometry())
    settings_size = (settings_dlg.width(), settings_dlg.height())
    settings_dlg.reject()

    win_screen = win.screen() or app.primaryScreen()
    avail = win_screen.availableGeometry()
    wait(0.2)
    main_fg = win.frameGeometry()
    win_screen.grabWindow(0, main_fg.x(), main_fg.y(), main_fg.width(), main_fg.height()).save(
        str(out_dir / "main-window.png")
    )
    win_screen.grabWindow(0).save(str(out_dir / "desktop-main.png"))
    (out_dir / "fit.txt").write_text(
        f"avail={avail.width()}x{avail.height()} "
        f"settings={settings_size[0]}x{settings_size[1]} "
        f"save_visible={save_visible} "
        f"settings_frame_on_screen={settings_on_screen} "
        f"main={win.width()}x{win.height()} "
        f"main_frame_on_screen={avail.contains(main_fg)}\n",
        encoding="utf-8",
    )

    win.ctrl.stop()
    win.close()
    return 0


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
        os._exit(code)  # background service threads must not keep the capture process alive
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)
    win = QtOrbitRxApplication()
    win.setWindowIcon(_app_icon())
    win.run()
    sys.exit(app.exec())
