from __future__ import annotations

import datetime
from typing import Any

from PIL import Image

from orbitrx.map_renderer import MapLayers, MapRenderer, MapScene
from orbitrx.ui.formatting import format_hour_offset, format_map_hud_datetime
from orbitrx.ui.theme import BG_MAP_MATTE, EMPTY_OVERLAY_STYLE, FONT_CAPTION, GREYLINE, MUTED, OK, WARN

try:
    from PySide6.QtCore import Qt, QRectF, Signal
    from PySide6.QtGui import (
        QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap,
    )
    from PySide6.QtWidgets import (
        QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPixmapItem,
        QGraphicsScene, QGraphicsTextItem, QGraphicsView, QLabel, QSizePolicy,
        QVBoxLayout, QWidget,
    )
    QT_AVAILABLE = True

    class SmoothGraphicsView(QGraphicsView):
        def wheelEvent(self, event) -> None:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)

except ImportError:
    QT_AVAILABLE = False
    SmoothGraphicsView = None  # type: ignore


# Native port of the Leaflet setLiveSpots JS: same caps so a big PSKReporter
# window never swamps the view.
MAX_LIVE_ARCS = 200
MAX_LIVE_HEAT_CELLS = 40


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    """PIL → Qt with an explicit buffer copy so Qt never holds dangling memory."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    stride = img.width * 4
    qimg = QImage(data, img.width, img.height, stride, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class PropagationMapWidget(QWidget):
    """GPU-friendly map: persistent base raster + overlay + vector DX layer."""

    greyline_meta_changed = Signal(str)
    spot_clicked = Signal(float)
    map_clicked = Signal(float, float)

    def __init__(self, renderer: MapRenderer, parent=None) -> None:
        super().__init__(parent)
        self.renderer = renderer
        self._layers = MapLayers()
        self._scene_data: MapScene | None = None
        self._click_targets: list[tuple[float, float, float, float]] = []
        self._view_fitted = False
        self._overlay_key: tuple | None = None
        self._base_pixmap: QPixmap | None = None
        self._overlay_pixmap: QPixmap | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hud = QLabel("")
        self.hud.setStyleSheet("color: #B3E5FC; padding: 4px; background: #0B1220;")
        # M3: its text grows with the current layer/time state, so it must wrap
        # (and never force the pane wider) on a narrow window instead of pushing
        # a hard minimum width.
        self.hud.setWordWrap(True)
        self.hud.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.hud)

        self.view = SmoothGraphicsView()
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._pan_anchor = None
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # P2: letterbox fill, so a pane that isn't exactly 2:1 shows dark bars
        # (never a crop) above/below or left/right of the map.
        self.view.setBackgroundBrush(QBrush(QColor(BG_MAP_MATTE)))
        layout.addWidget(self.view, stretch=1)

        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)

        self._base_item = QGraphicsPixmapItem()
        self._base_item.setZValue(0)
        self.scene.addItem(self._base_item)

        self._overlay_item = QGraphicsPixmapItem()
        self._overlay_item.setZValue(5)
        self.scene.addItem(self._overlay_item)

        self._vector_root = self.scene.createItemGroup([])
        self._vector_root.setZValue(10)

        # Live PSKReporter layer (arcs + heat); drawn above the DX vectors, same
        # as the old Leaflet liveArcs/liveHeat layer groups.
        self._live_spots_root = self.scene.createItemGroup([])
        self._live_spots_root.setZValue(11)
        self._live_click_targets: list[tuple[float, float, float, float]] = []

        # S1: centred label shown over the map when live spots are on but the
        # current replay window has nothing to plot.
        self._empty_overlay = QLabel("", self)
        self._empty_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_overlay.setWordWrap(False)  # one-line pill; the text is short
        self._empty_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._empty_overlay.setStyleSheet(EMPTY_OVERLAY_STYLE)
        self._empty_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_overlay.hide()

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

    def set_layers(self, layers: MapLayers) -> None:
        if (
            self._layers.greyline != layers.greyline
            or self._layers.night != layers.night
            or self._layers.aurora != layers.aurora
            or self._layers.grid != layers.grid
        ):
            self._overlay_key = None
        self._layers = layers

    def set_base_map(self, base_rgba: Image.Image) -> None:
        """Load world map once; kept until widget is destroyed or map is reloaded."""
        pixmap = _pil_to_qpixmap(base_rgba)
        if pixmap.isNull():
            raise RuntimeError("Base map pixmap conversion failed")
        self._base_pixmap = pixmap
        self._base_item.setPixmap(pixmap)
        self._base_item.setPos(0, 0)
        w, h = base_rgba.width, base_rgba.height
        self.scene.setSceneRect(0, 0, w, h)
        # P2: KeepAspectRatio letterboxes (dark bars, #0F1720) instead of cropping,
        # so the poles are never clipped asymmetrically and the map is centred.
        self.view.fitInView(QRectF(0, 0, w, h), Qt.AspectRatioMode.KeepAspectRatio)
        self._view_fitted = True

    def _overlay_refresh_key(self, scene: MapScene, state: Any) -> tuple:
        return (
            round(scene.sun_lon_deg, 1),
            round(scene.declination_deg, 1),
            round(state.slider_offset_hours, 1),
            self._layers.greyline,
            self._layers.night,
            self._layers.aurora,
            self._layers.grid,
            round(float(state.kp_index), 1),
        )

    def _update_overlay(self, scene: MapScene, state: Any) -> None:
        key = self._overlay_refresh_key(scene, state)
        if key == self._overlay_key and self._overlay_pixmap is not None:
            return
        pixmap = _pil_to_qpixmap(scene.overlay_rgba)
        if pixmap.isNull():
            raise RuntimeError("Overlay pixmap conversion failed")
        self._overlay_pixmap = pixmap
        self._overlay_item.setPixmap(pixmap)
        self._overlay_item.setPos(0, 0)
        self._overlay_key = key

    def update_scene(
        self,
        state: Any,
        spots: list[dict[str, Any]],
        coordinates: dict[str, tuple[float, float]],
        vectors_only: bool = False,
    ) -> None:
        scene = self.renderer.build_scene(state, self._layers, spots, coordinates)
        self._scene_data = scene

        if self._base_pixmap is None or self._base_item.pixmap().isNull():
            self.set_base_map(scene.base_rgba)

        if not vectors_only:
            self._update_overlay(scene, state)

        self._draw_vectors(scene)
        offset = state.slider_offset_hours
        now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=offset)
        extra = f"  ({format_hour_offset(offset)})" if offset else ""
        meta = f"Greyline @ {format_map_hud_datetime(now)}{extra}"
        self.hud.setText("")  # gestures live on the help chip; meta under the title
        self.hud.hide()
        if hasattr(self, "greyline_meta_changed"):
            self.greyline_meta_changed.emit(meta)

    def _clear_live_spots(self) -> None:
        for item in self._live_spots_root.childItems()[:]:
            self._live_spots_root.removeFromGroup(item)
            del item
        self._live_click_targets.clear()

    def set_live_spots(self, payload: dict[str, Any] | None) -> None:
        """Native equivalent of the Leaflet setLiveSpots JS (former
        orbitrx/ui/leaflet_map.py): draws the live PSKReporter arcs/heat layer,
        capped like the old JS (200 arcs, 40 heat cells). A click on an arc's
        receiver marker tunes the rig when the payload carries a frequency.
        """
        self._clear_live_spots()
        if not payload:
            return
        if payload.get("heatmap"):
            for cell in list(payload.get("heat") or [])[:MAX_LIVE_HEAT_CELLS]:
                if len(cell) < 3:
                    continue
                lat, lon, weight = cell[0], cell[1], cell[2]
                try:
                    weight = max(0.0, min(1.0, float(weight)))
                except (TypeError, ValueError):
                    weight = 0.0
                x, y = self.renderer.world_to_map(lat, lon)
                r = 10.0 + 14.0 * weight
                cell_item = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
                cell_item.setBrush(QBrush(QColor(240, 113, 120, int(40 + 70 * weight))))
                cell_item.setPen(QPen(Qt.PenStyle.NoPen))
                self._live_spots_root.addToGroup(cell_item)
        if payload.get("arcs"):
            for spot in list(payload.get("spots") or [])[:MAX_LIVE_ARCS]:
                tx, rx = spot.get("tx"), spot.get("rx")
                if not tx or not rx:
                    continue
                opacity = spot.get("opacity")
                if not isinstance(opacity, (int, float)):
                    opacity = 0.9
                opacity = max(0.0, min(1.0, float(opacity)))
                tx_x, tx_y = self.renderer.world_to_map(tx[0], tx[1])
                rx_x, rx_y = self.renderer.world_to_map(rx[0], rx[1])
                path = QPainterPath()
                path.moveTo(tx_x, tx_y)
                path.lineTo(rx_x, rx_y)
                line = QGraphicsPathItem(path)
                pen = QPen(QColor(120, 180, 255, int(102 * opacity)), 1.0)
                pen.setCosmetic(True)
                line.setPen(pen)
                label = spot.get("label")
                if label:
                    line.setToolTip(str(label))
                self._live_spots_root.addToGroup(line)
                dot = QGraphicsEllipseItem(tx_x - 3, tx_y - 3, 6, 6)
                dot.setBrush(QBrush(QColor(120, 180, 255, int(255 * opacity))))
                dot.setPen(QPen(Qt.PenStyle.NoPen))
                self._live_spots_root.addToGroup(dot)
                freq_mhz = spot.get("freq_mhz")
                if isinstance(freq_mhz, (int, float)):
                    self._live_click_targets.append((rx_x, rx_y, float(freq_mhz), 9.0))

    def _clear_vectors(self) -> None:
        for item in self._vector_root.childItems()[:]:
            self._vector_root.removeFromGroup(item)
            del item

    def _add_to_vectors(self, item) -> None:
        self._vector_root.addToGroup(item)

    def _draw_vectors(self, scene: MapScene) -> None:
        self._clear_vectors()
        self._click_targets.clear()

        if scene.terminator and len(scene.terminator) > 1:
            path = QPainterPath()
            path.moveTo(*scene.terminator[0])
            for px, py in scene.terminator[1:]:
                path.lineTo(px, py)
            greyline = QGraphicsPathItem(path)
            # P3/V12: cosmetic ~2 logical-px terminator; hairline outer only
            # (no thick 8px glow — Founder eyes read that as amateur weight).
            hair = QGraphicsPathItem(QPainterPath(path))
            hpen = QPen(QColor(255, 138, 76, 48), 3)
            hpen.setCosmetic(True)
            hair.setPen(hpen)
            self._add_to_vectors(hair)
            pen = QPen(QColor(GREYLINE), 2.0)
            pen.setCosmetic(True)
            greyline.setPen(pen)
            self._add_to_vectors(greyline)

        sun_font = QFont("Segoe UI", FONT_CAPTION)
        sun_drawn = False
        img_w = float(getattr(scene, "width", 0) or getattr(self.renderer, "width", 0) or 0)
        for ann in scene.annotations:
            if ann.kind == "sun":
                if sun_drawn:
                    continue  # S4: wrapped copies fall outside the scene; clamp the first instead
                sun_drawn = True
                x, y = ann.data["x"], ann.data["y"]
                if img_w > 32:
                    x = min(max(x, 16.0), img_w - 16.0)
                # M1: 18px disc #F0B429 + soft halo, no cartoon rays.
                glow = QGraphicsEllipseItem(x - 14, y - 14, 28, 28)
                glow.setBrush(QBrush(QColor(240, 180, 41, 89)))
                glow.setPen(QPen(Qt.PenStyle.NoPen))
                self._add_to_vectors(glow)
                core = QGraphicsEllipseItem(x - 9, y - 9, 18, 18)
                core.setBrush(QBrush(QColor(WARN)))
                core.setPen(QPen(Qt.PenStyle.NoPen))
                self._add_to_vectors(core)

            elif ann.kind == "user":
                x, y = ann.data["x"], ann.data["y"]
                # M1: 10px disc --ok + 14px ring + label 11/600 with matte halo.
                ring = QGraphicsEllipseItem(x - 7, y - 7, 14, 14)
                ring.setBrush(QBrush(QColor(61, 220, 151, 89)))
                ring.setPen(QPen(Qt.PenStyle.NoPen))
                self._add_to_vectors(ring)
                dot = QGraphicsEllipseItem(x - 5, y - 5, 10, 10)
                dot.setBrush(QBrush(QColor(OK)))
                dot.setPen(QPen(Qt.PenStyle.NoPen))
                self._add_to_vectors(dot)
                label_path = QPainterPath()
                you_font = QFont("Segoe UI", FONT_CAPTION)
                you_font.setWeight(QFont.Weight.DemiBold)
                fm = QFontMetrics(you_font)
                label_path.addText(x + 10, y - 14 + fm.ascent(), you_font, "You")
                halo = QGraphicsPathItem(label_path)
                halo_pen = QPen(QColor(7, 11, 20, 220), 3)
                halo_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                halo.setPen(halo_pen)
                halo.setBrush(QBrush(QColor("#E8EEF7")))
                self._add_to_vectors(halo)

            elif ann.kind == "dx_spot":
                d = ann.data
                pen_arc = QPen(QColor("#00E5FF"), 2, Qt.PenStyle.DashLine)
                for seg in d.get("paths", []):
                    if len(seg) < 2:
                        continue
                    path = QPainterPath()
                    path.moveTo(seg[0][0], seg[0][1])
                    for px, py in seg[1:]:
                        path.lineTo(px, py)
                    arc_item = QGraphicsPathItem(path)
                    arc_item.setPen(pen_arc)
                    self._add_to_vectors(arc_item)

                fx, fy, tx, ty = d["fx"], d["fy"], d["tx"], d["ty"]
                spotter = QGraphicsEllipseItem(fx - 5, fy - 5, 10, 10)
                spotter.setBrush(QBrush(QColor("#FF9800")))
                spotter.setPen(QPen(QColor("white")))
                self._add_to_vectors(spotter)

                color = QColor("#7B1FA2") if d.get("demo") else QColor("#AB47BC")
                target = QGraphicsEllipseItem(tx - 7, ty - 7, 14, 14)
                target.setBrush(QBrush(color))
                target.setPen(QPen(QColor("white"), 2))
                self._add_to_vectors(target)

                freq = d.get("freq", "?")
                age = d.get("age", 0)
                label = QGraphicsTextItem(f"{d.get('to')} {freq} MHz ({age}s)")
                label.setDefaultTextColor(QColor("#FFF59D"))
                label.setFont(QFont("Segoe UI", FONT_CAPTION))
                label.setPos(tx + 8, ty - 16)
                self._add_to_vectors(label)

                self._click_targets.append((tx, ty, float(freq), 18.0))

    def mouseDoubleClickEvent(self, event) -> None:
        self.view.resetTransform()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_anchor = event.pos()
        elif event.button() == Qt.MouseButton.LeftButton:
            sp = self.view.mapToScene(event.pos())
            for tx, ty, freq, radius in self._click_targets + self._live_click_targets:
                if (sp.x() - tx) ** 2 + (sp.y() - ty) ** 2 <= radius ** 2:
                    self.spot_clicked.emit(freq)
                    return
            self.map_clicked.emit(sp.x(), sp.y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_anchor is not None and event.buttons() & Qt.MouseButton.RightButton:
            delta = event.pos() - self._pan_anchor
            self._pan_anchor = event.pos()
            self.view.horizontalScrollBar().setValue(
                self.view.horizontalScrollBar().value() - delta.x()
            )
            self.view.verticalScrollBar().setValue(
                self.view.verticalScrollBar().value() - delta.y()
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_anchor = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_map_view()
        self._reposition_empty_overlay()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_map_view()

    def _fit_map_view(self) -> None:
        if self._base_item.pixmap() and not self._base_item.pixmap().isNull():
            r = self._base_item.boundingRect()
            if r.width() > 0 and r.height() > 0:
                self.view.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
