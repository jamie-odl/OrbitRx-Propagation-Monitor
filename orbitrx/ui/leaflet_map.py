from __future__ import annotations

import datetime
import json
import logging
from typing import Any

try:
    from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QColor
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
    )
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    QWidget = object  # type: ignore

from pathlib import Path

from orbitrx.map_renderer import MapLayers, MapRenderer
from orbitrx.paths import bundled_root
from orbitrx.ui.formatting import format_hour_offset, format_map_hud_datetime
from orbitrx.ui.theme import ACCENT, BG, BG_ELEVATED, BORDER, CARD_STYLE, CARD_TEXT, EMPTY_OVERLAY_STYLE, MUTED, TEXT, TEXT_MUTED

log = logging.getLogger("orbitrx")

# M3: shown over the map when the page fails to load, or loads but the tiles
# never do (offline, or an unreachable tile server) -- never a blank white page.
MAP_UNAVAILABLE_TEXT = "Map tiles unavailable (offline?)"
MAP_UNAVAILABLE_BODY = "Check your connection, then retry - or switch to the static map."
# M5: branded offline card - elevated fill, 12 radius, no stock triangle as sole brand.
MAP_UNAVAILABLE_STYLE = (
    f"QWidget#mapUnavailableCard {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; "
    f"border-radius: 12px; padding: 24px; }}"
    f" QWidget#mapUnavailableCard QLabel {{ border: none; background: transparent; }}"
)
MAP_UNAVAILABLE_HINT_STYLE = f"color: {MUTED}; font-size: 12px;"

# M3: how long to wait for Leaflet's tile layer to report its first successful
# tile load before treating the map as unavailable.
TILE_LOAD_TIMEOUT_MS = 8_000


def _assets_dir() -> Path:
    bundle = bundled_root()
    if bundle and (bundle / "orbitrx" / "ui" / "assets").is_dir():
        return bundle / "orbitrx" / "ui" / "assets"
    return Path(__file__).resolve().parent / "assets"


ASSETS_DIR = _assets_dir()

_LEAFLET_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
<script>__QWEBCHANNEL_JS__</script>
<style>html,body,#map{margin:0;height:100%;background:#070B14}
.leaflet-control-attribution{
  background:rgba(7,11,20,0.75)!important;color:#6B7A90!important;
  border-radius:8px;padding:2px 8px;font-size:11px!important;margin:8px!important}
.leaflet-control-attribution a{color:#6B7A90!important}
.leaflet-control-zoom a{
  background:#121A2B!important;color:#9AA8BC!important;border-color:#243044!important;
  width:28px!important;height:28px!important;line-height:28px!important;
  border-radius:0!important}
.leaflet-control-zoom{border:none!important;border-radius:8px;overflow:hidden;
  box-shadow:none!important;width:28px}
.leaflet-control-zoom a:first-child{border-radius:8px 8px 0 0!important}
.leaflet-control-zoom a:last-child{border-radius:0 0 8px 8px!important;height:28px!important}
</style>
</head><body>
<div id="map"></div>
<script>
let spotBridge = null;
// Tile events can fire before the web channel is ready, so remember them and
// report once the bridge exists (otherwise the 8 s timeout fires on a good map).
let tilesOk = false, tilesFailed = false;
new QWebChannel(qt.webChannelTransport, ch => {
  spotBridge = ch.objects.spotBridge;
  if (tilesOk) spotBridge.tilesLoaded(); else if (tilesFailed) spotBridge.tileError();
});
const map = L.map('map', {worldCopyJump: true, zoomControl: true, minZoom: 1, maxZoom: 6}).setView([20, 0], 2);
// V11 must-fix 1: offline-first dark equirectangular basemap — never Carto watermarks.
const basemap = L.imageOverlay('__BASEMAP_URL__', [[-90, -180], [90, 180]], {
  opacity: 1, interactive: false, zIndex: 0
}).addTo(map);
L.control.attribution({prefix: false}).addTo(map);
map.attributionControl.addAttribution('OrbitRx dark basemap');
basemap.on('load', () => {
  if (!tilesOk) { tilesOk = true; if (spotBridge) spotBridge.tilesLoaded(); }
});
basemap.on('error', () => {
  if (tilesOk) return; tilesFailed = true; if (spotBridge) spotBridge.tileError();
});
setTimeout(() => {
  const el = basemap.getElement && basemap.getElement();
  if (!tilesOk && el && el.complete && el.naturalWidth > 0) {
    tilesOk = true; if (spotBridge) spotBridge.tilesLoaded();
  }
}, 400);
let userM=null, sunM=null, dxLayer=L.layerGroup().addTo(map), termLine=null, nightPane=[];
function setPayload(p) {
  dxLayer.clearLayers();
  nightPane.forEach(l => map.removeLayer(l)); nightPane=[];
  if (termLine) { map.removeLayer(termLine); termLine=null; }
  if (p.layers.night) {
    for (let lon=-180; lon<180; lon+=2) {
      if (Math.abs(((lon - p.sun_lon + 180) % 360) - 180) > 90) {
        const r = L.rectangle([[ -85, lon], [85, lon+2]], {color:'#080E1C', fillColor:'#080E1C', fillOpacity:0.55, weight:0});
        r.addTo(map); nightPane.push(r);
      }
    }
  }
  if (p.layers.greyline && p.terminator.length > 1) {
    termLine = L.polyline(p.terminator, {color:'#FF8A4C', weight:2, opacity:0.95}).addTo(map);
  }
  if (p.user) {
    if (!userM) userM = L.circleMarker(p.user, {radius:5, color:'#3DDC97', fillColor:'#3DDC97', fillOpacity:1, weight:3, opacity:0.45}).addTo(map).bindPopup('You');
    else userM.setLatLng(p.user);
  }
  if (p.sun) {
    if (!sunM) sunM = L.circleMarker(p.sun, {radius:9, color:'#F0B429', fillColor:'#F0B429', fillOpacity:1, weight:0}).addTo(map).bindPopup('Sub-solar');
    else sunM.setLatLng(p.sun);
  }
  (p.spots||[]).forEach(s => {
    if (p.layers.dx_arcs && s.from_ll && s.to_ll) {
      L.polyline([s.from_ll, s.to_ll], {color:'rgba(120,180,255,0.55)', weight:1.25}).addTo(dxLayer);
    }
    if (s.from_ll) L.circleMarker(s.from_ll, {radius:5, color:'#fff', fillColor:'#FF9800', fillOpacity:1}).addTo(dxLayer);
    if (s.to_ll) {
      const col = s.demo ? '#7B1FA2' : '#AB47BC';
      const m = L.circleMarker(s.to_ll, {radius:7, color:'#fff', fillColor:col, fillOpacity:1}).addTo(dxLayer);
      m.bindPopup(s.to + ' ' + s.freq + ' MHz');
      m.on('click', () => { if (spotBridge) spotBridge.spotClicked(s.freq); });
    }
  });
}
let liveArcs=L.layerGroup().addTo(map), liveHeat=L.layerGroup().addTo(map);
function setLiveSpots(p) {
  liveArcs.clearLayers(); liveHeat.clearLayers();
  if (p.heatmap) {
    // P4: radius shrinks with zoom so the heatmap never swamps the spot lines
    // underneath it at a closer-in view.
    const zoomScale = Math.pow(0.72, Math.max(0, map.getZoom() - 2));
    const heats = (p.heat||[]).slice(0, 40);
    heats.forEach(c => {
      L.circle([c[0], c[1]], {radius: 280000 * zoomScale, stroke:false, fillColor:'#F07178', fillOpacity: 0.28}).addTo(liveHeat);
    });
  }
  if (p.arcs) {
    const spots = (p.spots||[]).slice(0, 200);
    spots.forEach(s => {
      let opacity = (typeof s.opacity === 'number') ? s.opacity : 0.9;
      if (typeof s.age_min === 'number' && s.age_min > 15) opacity = Math.min(opacity, 0.35);
      L.polyline([s.tx, s.rx], {color:'rgba(120,180,255,0.55)', weight:1.25, opacity: opacity}).bindTooltip(s.label).addTo(liveArcs);
      L.circleMarker(s.tx, {radius:3, color:'#78B4FF', fillOpacity:1, opacity: opacity}).addTo(liveArcs);
    });
  }
}
map.on('click', e => { if (spotBridge) spotBridge.mapClicked(e.latlng.lat, e.latlng.lng); });
</script></body></html>"""


def _leaflet_html(basemap_url: str) -> str:
    """Build the page with bundled Leaflet + offline dark basemap (no CDN tiles, no Carto)."""
    from PySide6.QtCore import QFile, QIODevice

    js = ""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QIODevice.OpenModeFlag.ReadOnly):
        js = bytes(f.readAll()).decode("utf-8")
        f.close()
    leaflet_dir = ASSETS_DIR / "leaflet"
    css = (leaflet_dir / "leaflet.css").read_text(encoding="utf-8").replace("url(images/", "url(leaflet/images/")
    ljs = (leaflet_dir / "leaflet.js").read_text(encoding="utf-8")
    return (_LEAFLET_HTML.replace("__LEAFLET_CSS__", css)
            .replace("__LEAFLET_JS__", ljs)
            .replace("__QWEBCHANNEL_JS__", js)
            .replace("__BASEMAP_URL__", basemap_url))


if WEBENGINE_AVAILABLE:

    class _SpotBridge(QObject):
        spot_clicked = Signal(float)
        map_clicked = Signal(float, float)
        tiles_loaded = Signal()
        tile_error = Signal()

        @Slot(float)
        def spotClicked(self, freq: float) -> None:
            self.spot_clicked.emit(float(freq))

        @Slot(float, float)
        def mapClicked(self, lat: float, lon: float) -> None:
            self.map_clicked.emit(float(lat), float(lon))

        @Slot()
        def tilesLoaded(self) -> None:
            self.tiles_loaded.emit()

        @Slot()
        def tileError(self) -> None:
            self.tile_error.emit()

    class LeafletMapWidget(QWidget):
        spot_clicked = Signal(float)
        map_clicked = Signal(float, float)
        # M3: lets the main window route this to the same action as the
        # "Switch map" link on the static map (Settings > Map & spots).
        switch_to_static_requested = Signal()

        def __init__(self, renderer: MapRenderer, parent=None) -> None:
            super().__init__(parent)
            self.renderer = renderer
            self._layers = MapLayers()
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.hud = QLabel("")
            self.hud.hide()
            self.hud.setObjectName("muted")
            # M3: its text grows with the current time/offset state, so it must wrap
            # (and never force the pane wider) on a narrow window.
            self.hud.setWordWrap(True)
            self.hud.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            layout.addWidget(self.hud)
            self.web = QWebEngineView()
            # M3: 1.0 so device-pixel-ratio scaling (e.g. a 150% display) never
            # doubles up with Qt's own scale factor and renders a blank page.
            self.web.setZoomFactor(1.0)
            # OSM tile policy asks apps to identify themselves.
            from orbitrx import __version__
            self.web.page().profile().setHttpUserAgent(
                f"OrbitRx/{__version__} (+https://github.com/jamie-odl/OrbitRx-Propagation-Monitor)"
            )
            self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            self.web.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            # M3: a dark page background instead of Qt's default white, so a slow or
            # failed load never flashes blank white at any zoom/scale factor.
            self.web.page().setBackgroundColor(QColor(BG))
            layout.addWidget(self.web, stretch=1)
            self._bridge = _SpotBridge()
            self._bridge.spot_clicked.connect(self.spot_clicked)
            self._bridge.map_clicked.connect(self._emit_map_click)
            self._bridge.tiles_loaded.connect(self._on_tiles_loaded)
            self._bridge.tile_error.connect(self._on_tile_error)
            channel = QWebChannel(self.web.page())
            channel.registerObject("spotBridge", self._bridge)
            self.web.page().setWebChannel(channel)
            # Leaflet JS/CSS bundled; basemap is the local dark equirectangular PNG (no Carto).
            from orbitrx.paths import ensure_map_image
            from PySide6.QtCore import QUrl as _QUrl
            basemap_path = ensure_map_image()
            basemap_url = _QUrl.fromLocalFile(str(basemap_path.resolve())).toString()
            base = basemap_path.resolve().parent
            self.web.setHtml(_leaflet_html(basemap_url), _QUrl.fromLocalFile(str(base) + "/"))
            self._ready = False
            self.web.loadFinished.connect(self._on_ready)

            # M3: once the page itself loads, wait up to TILE_LOAD_TIMEOUT_MS for the
            # first tile to actually come in before deciding the map is unavailable
            # (e.g. offline, or the tile server is unreachable).
            self._tile_timeout_timer = QTimer(self)
            self._tile_timeout_timer.setSingleShot(True)
            self._tile_timeout_timer.timeout.connect(self._on_tile_timeout)

            # S1: centred label shown over the map when live spots are on but the
            # current replay window has nothing to plot.
            self._empty_overlay = QLabel("", self)
            self._empty_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_overlay.setWordWrap(False)  # one-line pill; the text is short
            self._empty_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self._empty_overlay.setStyleSheet(EMPTY_OVERLAY_STYLE)
            self._empty_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._empty_overlay.hide()

            self._build_unavailable_overlay()

        def _build_unavailable_overlay(self) -> None:
            """M3: a dark-card fallback (same 8px-radius card look as the band tiles)
            covering the whole map, shown instead of a blank/white page when the page
            fails to load or its tiles never arrive. Retry reloads the page; "Switch to
            static map" hands off to the same action as the static map's own link."""
            self._unavailable_overlay = QWidget(self)
            self._unavailable_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            outer = QVBoxLayout(self._unavailable_overlay)
            outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

            card = QWidget()
            card.setObjectName("mapUnavailableCard")
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setStyleSheet(MAP_UNAVAILABLE_STYLE)
            card_layout = QVBoxLayout(card)

            icon = QLabel("⌖")  # map-off glyph stand-in (32px feel)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet(f"font-size: 32px; color: {TEXT_MUTED}; background: transparent;")
            card_layout.addWidget(icon)

            self._unavailable_message = QLabel(MAP_UNAVAILABLE_TEXT)
            self._unavailable_message.setWordWrap(True)
            self._unavailable_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._unavailable_message.setStyleSheet(
                f"background: transparent; color: {TEXT}; font-size: 15px; font-weight: 600;"
            )
            card_layout.addWidget(self._unavailable_message)
            body = QLabel(MAP_UNAVAILABLE_BODY)
            body.setWordWrap(True)
            body.setAlignment(Qt.AlignmentFlag.AlignCenter)
            body.setStyleSheet(f"background: transparent; color: {MUTED}; font-size: 13px;")
            card_layout.addWidget(body)

            btn_row = QHBoxLayout()
            self.retry_btn = QPushButton("Retry")
            self.retry_btn.setObjectName("primaryButton")
            self.switch_static_btn = QPushButton("Switch to static map")
            self.retry_btn.clicked.connect(self._retry)
            self.switch_static_btn.clicked.connect(self.switch_to_static_requested.emit)
            btn_row.addWidget(self.retry_btn)
            btn_row.addWidget(self.switch_static_btn)
            card_layout.addLayout(btn_row)

            outer.addWidget(card)
            self._unavailable_overlay.hide()

        def _retry(self) -> None:
            log.info("Leaflet map retry requested; reloading offline basemap")
            self._hide_unavailable_overlay()
            self._ready = False
            self._tiles_ok = False
            from orbitrx.paths import ensure_map_image
            from PySide6.QtCore import QUrl as _QUrl
            basemap_path = ensure_map_image()
            basemap_url = _QUrl.fromLocalFile(str(basemap_path.resolve())).toString()
            base = basemap_path.resolve().parent
            self.web.setHtml(_leaflet_html(basemap_url), _QUrl.fromLocalFile(str(base) + "/"))

        def _on_ready(self, ok: bool) -> None:
            self._ready = ok
            if not ok:
                log.warning("Leaflet map page failed to load")
                self._show_unavailable_overlay()
            elif not getattr(self, "_tiles_ok", False):
                # Tiles can arrive before loadFinished; only arm the timeout if
                # none have been reported yet.
                self._tile_timeout_timer.start(TILE_LOAD_TIMEOUT_MS)

        def _on_tiles_loaded(self) -> None:
            self._tiles_ok = True
            self._tile_timeout_timer.stop()
            self._hide_unavailable_overlay()

        def _on_tile_error(self) -> None:
            log.warning("Leaflet tile load error")
            self._tile_timeout_timer.stop()
            self._show_unavailable_overlay()

        def _on_tile_timeout(self) -> None:
            log.warning("Leaflet tiles did not load within %sms", TILE_LOAD_TIMEOUT_MS)
            self._show_unavailable_overlay()

        def _show_unavailable_overlay(self) -> None:
            self._unavailable_overlay.setGeometry(0, 0, self.width(), self.height())
            self._unavailable_overlay.show()
            self._unavailable_overlay.raise_()

        def _hide_unavailable_overlay(self) -> None:
            self._unavailable_overlay.hide()

        def set_empty_overlay(self, text: str) -> None:
            self._empty_overlay.setText(text)
            self._reposition_empty_overlay()
            self._empty_overlay.setVisible(bool(text))
            if text:
                self._empty_overlay.raise_()

        def _reposition_empty_overlay(self) -> None:
            """Size the pill to its text and centre it (S2: a centred pill, not a
            label stretched across the whole map)."""
            self._empty_overlay.adjustSize()
            self._empty_overlay.move(
                (self.width() - self._empty_overlay.width()) // 2,
                (self.height() - self._empty_overlay.height()) // 2,
            )

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            self._reposition_empty_overlay()
            if self._unavailable_overlay.isVisible():
                self._unavailable_overlay.setGeometry(0, 0, self.width(), self.height())

        def _emit_map_click(self, lat: float, lon: float) -> None:
            x, y = self.renderer.world_to_map(lat, lon)
            self.map_clicked.emit(x, y)

        def set_layers(self, layers: MapLayers) -> None:
            self._layers = layers

        def set_base_map(self, _base_rgba) -> None:
            pass

        def set_live_spots(self, payload: dict[str, Any]) -> None:
            """payload: {"arcs": bool, "heatmap": bool, "spots": [...], "heat": [...]}"""
            if self._ready:
                self.web.page().runJavaScript(f"setLiveSpots({json.dumps(payload)});")

        def update_scene(
            self,
            state: Any,
            spots: list[dict[str, Any]],
            coordinates: dict[str, tuple[float, float]],
            vectors_only: bool = False,
        ) -> None:
            if not self._ready:
                return
            scene = self.renderer.build_scene(state, self._layers, spots, coordinates)
            terminator = []
            import math
            w, h = self.renderer.width, self.renderer.height
            decl_rad = math.radians(scene.declination_deg)
            sun_lon_rad = math.radians(scene.sun_lon_deg)
            for x in range(0, w + 1, 4):
                lon_deg = (x / w) * 360 - 180
                lon_rad = math.radians(lon_deg)
                tan_dec = math.tan(decl_rad) or 0.0001
                tan_lat = -math.cos(lon_rad - sun_lon_rad) / tan_dec
                lat_deg = math.degrees(math.atan(tan_lat))
                terminator.append([lat_deg, lon_deg])
            spot_payload = []
            for ann in scene.annotations:
                if ann.kind != "dx_spot":
                    continue
                d = ann.data
                fcs = coordinates.get(d.get("from", ""))
                tcs = coordinates.get(d.get("to", ""))
                spot_payload.append({
                    "from": d.get("from"), "to": d.get("to"),
                    "freq": d.get("freq"), "demo": d.get("demo", False),
                    "from_ll": list(fcs) if fcs else None,
                    "to_ll": list(tcs) if tcs else None,
                })
            user = None
            sun = None
            for ann in scene.annotations:
                if ann.kind == "user" and state.user_lat is not None:
                    user = [state.user_lat, state.user_lon]
                if ann.kind == "sun":
                    lat, lon = self.renderer.map_to_world(ann.data["x"], ann.data["y"])
                    sun = [lat, lon]
            payload = {
                "layers": {
                    "greyline": self._layers.greyline,
                    "night": self._layers.night,
                    "dx_arcs": self._layers.dx_arcs,
                },
                "sun_lon": scene.sun_lon_deg,
                "terminator": terminator,
                "user": user,
                "sun": sun,
                "spots": spot_payload,
            }
            js = f"setPayload({json.dumps(payload)});"
            self.web.page().runJavaScript(js)
            offset = state.slider_offset_hours
            now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=offset)
            extra = f"  ({format_hour_offset(offset)})" if offset else ""
            self.hud.setText(
                f"Leaflet @ {format_map_hud_datetime(now)}{extra} · "
                "Scroll to zoom · Click a spot to tune"
            )

else:
    LeafletMapWidget = None  # type: ignore
