from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass
from typing import Any

from PIL import Image

from orbitrx.map_renderer import MapLayers, MapRenderer, MapScene
from orbitrx.ui.formatting import format_hour_offset, format_map_hud_datetime
from orbitrx.ui.theme import (
    EMPTY_OVERLAY_STYLE, FONT_CAPTION, GREYLINE, MAP_CLUSTER_PILL_STYLE, MAP_LEGEND_STYLE,
    MAP_OCEAN, MUTED, OK, SPOT, WARN,
)

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
    from orbitrx.ui.async_utils import UiInvoker
    QT_AVAILABLE = True

    class SmoothGraphicsView(QGraphicsView):
        def wheelEvent(self, event) -> None:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)

except ImportError:
    QT_AVAILABLE = False
    SmoothGraphicsView = None  # type: ignore


@dataclass
class _MapStateSnapshot:
    """The handful of AppState fields build_scene() reads, copied out before
    handing off to the rebuild worker thread (P1): the live AppState object is
    owned and mutated by the UI thread and must never be touched off it."""

    slider_offset_hours: float
    kp_index: float
    user_lat: float | None
    user_lon: float | None


# Native port of the Leaflet setLiveSpots JS: same caps so a big PSKReporter
# window never swamps the view.
MAX_LIVE_ARCS = 200
MAX_LIVE_HEAT_CELLS = 40

# P4-8 (SPEC §7 / owner decision (e)): longitude is never cropped, only
# latitude, and only up to this many degrees off either pole (aurora stays
# visible) -- see _padded_scene_rect(). The vertical centre bias used while
# cropping, per SPEC §7's centre rule ("about 10N, because the populated,
# HF-relevant latitudes sit north of the equator").
MAX_POLE_CROP_DEG = 15.0
MAP_CENTER_LAT_DEG = 10.0

# Map-pane width below which the three-item in-map legend no longer fits
# comfortably and is replaced by the single greyline-timestamp caption
# (SPEC §7's 683-wide behaviour) -- same breakpoint _MapControlStrip already
# collapses the layer-chip row at (qt_app.py's _SINGLE_ROW_MIN_WIDTH).
LEGEND_COMPACT_WIDTH = 820


def _pil_to_qimage(img: Image.Image) -> QImage:
    """PIL -> QImage with an explicit buffer copy so Qt never holds dangling
    memory. QImage (unlike QPixmap) has no GUI-thread affinity, so this half
    of the conversion is safe to run on a background thread (F7)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    stride = img.width * 4
    qimg = QImage(data, img.width, img.height, stride, QImage.Format.Format_RGBA8888)
    return qimg.copy()


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(_pil_to_qimage(img))


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

        # P1: build_scene()'s PIL compositing runs on a worker thread; at most one
        # runs at a time, with a newer request while one is in flight coalescing
        # into a single pending rebuild (the latest state wins, nothing queues up).
        self._invoker = UiInvoker(self)
        self._rebuild_running = False
        self._pending_rebuild: tuple[int, tuple] | None = None
        self._rebuild_generation = 0
        # Exposed so callers (tests, shutdown teardown) can join the latest
        # rebuild worker before tearing down this widget or its renderer.
        self._rebuild_thread: threading.Thread | None = None

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
        # Ocean-coloured fill behind the scene (SPEC §7: "a MAP_OCEAN
        # background, so there is never pure black"). Before P4-8 this brush
        # was only a pre-fit fallback, invisible once running; _fit_scene_rect()
        # now deliberately leaves ocean-coloured margin visible around the
        # basemap whenever the viewport's aspect ratio doesn't exactly match
        # the basemap's own 2:1 (see _padded_scene_rect), so this colour is
        # genuinely on-screen, not just a placeholder.
        self.view.setBackgroundBrush(QBrush(QColor(MAP_OCEAN)))
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

        # P4-8 (SPEC §10 / "Cluster disconnected"): a second centred pill,
        # stacked above the no-spots pill when both are visible at once --
        # driven only by the real DX-cluster connection state (qt_app.py's
        # _render_cluster_label calls set_cluster_pill()), never a sample.
        self._cluster_pill = QLabel("", self)
        self._cluster_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cluster_pill.setWordWrap(False)
        self._cluster_pill.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cluster_pill.setStyleSheet(MAP_CLUSTER_PILL_STYLE)
        self._cluster_pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._cluster_pill.hide()

        # P4-8 (SPEC §7): bottom-left in-map legend (Greyline/Night/DX spot),
        # replaced by the greyline timestamp caption alone once the pane is
        # narrower than LEGEND_COMPACT_WIDTH. Both are static/real -- the
        # legend names colours, the caption's text comes from the same real
        # `meta` string _apply_scene() already computes.
        self._legend_lbl = QLabel("", self)
        self._legend_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._legend_lbl.setWordWrap(False)
        self._legend_lbl.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._legend_lbl.setStyleSheet(MAP_LEGEND_STYLE)
        self._legend_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._legend_lbl.setText(
            f'<span style="color:{GREYLINE}">●</span> Greyline &nbsp;&nbsp; '
            f'<span style="color:{MUTED}">■</span> Night &nbsp;&nbsp; '
            f'<span style="color:{SPOT}">●</span> DX spot'
        )

        self._legend_caption_lbl = QLabel("", self)
        self._legend_caption_lbl.setWordWrap(False)
        self._legend_caption_lbl.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._legend_caption_lbl.setStyleSheet(MAP_LEGEND_STYLE)
        self._legend_caption_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._legend_caption_lbl.hide()
        self._greyline_meta_text = ""
        self._repositioning_legend = False
        self._reposition_legend()

    def set_empty_overlay(self, text: str) -> None:
        self._empty_overlay.setText(text)
        self._empty_overlay.setVisible(bool(text))
        self._reposition_center_pills()
        if text:
            self._empty_overlay.raise_()

    def set_cluster_pill(self, text: str) -> None:
        self._cluster_pill.setText(text)
        self._cluster_pill.setVisible(bool(text))
        self._reposition_center_pills()
        if text:
            self._cluster_pill.raise_()

    def _reposition_empty_overlay(self) -> None:
        """Kept as the pre-existing public-ish entry point (resizeEvent,
        set_empty_overlay) -- now repositions every in-map overlay, not just
        the no-spots pill, since the cluster pill and legend share the same
        geometry-on-resize concern."""
        self._reposition_center_pills()
        self._reposition_legend()

    def _reposition_center_pills(self) -> None:
        """Stacks the cluster pill above the no-spots pill when both are
        visible at once (S2: a centred pill, not a label stretched across the
        whole map), rather than overlapping them."""
        gap = 8
        self._empty_overlay.adjustSize()
        self._cluster_pill.adjustSize()
        cluster_visible = self._cluster_pill.isVisible()
        empty_visible = self._empty_overlay.isVisible()
        total_h = 0
        if cluster_visible:
            total_h += self._cluster_pill.height()
        if cluster_visible and empty_visible:
            total_h += gap
        if empty_visible:
            total_h += self._empty_overlay.height()
        y = (self.height() - total_h) // 2
        if cluster_visible:
            self._cluster_pill.move((self.width() - self._cluster_pill.width()) // 2, y)
            y += self._cluster_pill.height() + gap
        if empty_visible:
            self._empty_overlay.move((self.width() - self._empty_overlay.width()) // 2, y)

    def _reposition_legend(self) -> None:
        """SPEC §7: bottom-left legend at full width, swapped for the
        greyline timestamp caption alone once the pane gets too narrow for
        all three legend entries (same breakpoint the control strip's layer
        chips collapse to a menu at).

        Round 8: showing/hiding a previously-hidden child here (setVisible()
        on either label) can make Qt flush a pending ancestor LayoutRequest
        synchronously -- if this widget is itself mid-resize (e.g. a splitter
        correcting an in-flight geometry change), that flush re-enters this
        same method with a *different* self.width() before the outer call's
        own branch has finished applying. Looping until self.width() stops
        moving mid-call (guarded against the reentrant call doing the same
        work twice) makes the final applied state always match this widget's
        actual settled width, instead of an interleaving of two widths'
        decisions."""
        if self._repositioning_legend:
            return
        self._repositioning_legend = True
        try:
            inset = 12
            # Bounded, not `while True`: every observed case settles after
            # one extra reentrant level, and a hard cap means a future,
            # unrelated layout change could at worst leave a stale width's
            # decision applied for one frame rather than hang the UI thread.
            for _ in range(8):
                width_before = self.width()
                compact = width_before < LEGEND_COMPACT_WIDTH
                if compact:
                    self._legend_lbl.hide()
                    self._legend_caption_lbl.setText(self._greyline_meta_text)
                    self._legend_caption_lbl.setVisible(bool(self._greyline_meta_text))
                    self._legend_caption_lbl.adjustSize()
                    self._legend_caption_lbl.move(8, self.height() - self._legend_caption_lbl.height() - 8)
                else:
                    self._legend_caption_lbl.hide()
                    self._legend_lbl.setVisible(True)
                    self._legend_lbl.adjustSize()
                    self._legend_lbl.move(inset, self.height() - self._legend_lbl.height() - inset)
                if self.width() == width_before:
                    break
        finally:
            self._repositioning_legend = False

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
        self._assign_base_pixmap(_pil_to_qpixmap(base_rgba), base_rgba.width, base_rgba.height)

    def set_base_map_from_qimage(self, qimage: QImage) -> None:
        """Like set_base_map, but for a QImage a background thread already
        decoded/scaled (F7): only the cheap QPixmap wrap + scene assignment
        below needs the GUI thread."""
        self._assign_base_pixmap(QPixmap.fromImage(qimage), qimage.width(), qimage.height())

    def _assign_base_pixmap(self, pixmap: QPixmap, w: int, h: int) -> None:
        if pixmap.isNull():
            raise RuntimeError("Base map pixmap conversion failed")
        self._base_pixmap = pixmap
        self._base_item.setPixmap(pixmap)
        self._base_item.setPos(0, 0)
        self.scene.setSceneRect(0, 0, w, h)
        self._fit_scene_rect(QRectF(0, 0, w, h))
        self._view_fitted = True

    def _padded_scene_rect(self, image_rect: QRectF, viewport_aspect: float) -> QRectF:
        """P4-8 -- owner decision (e) overrides SPEC §7's longitude crop: the
        full -180..180 range must stay on-screen at every window size, with
        only latitude ever cropped, capped at MAX_POLE_CROP_DEG per pole.

        Returns a rect in the same scene coordinates as image_rect, with
        `viewport_aspect` as its own width/height ratio, built one of two
        ways:
        - If the viewport is proportionally taller than the 2:1 basemap (the
          common 1280x800 case), the rect is *wider* than the image in scene
          terms -- really it pads the image's height so the aspect matches,
          adding ocean-coloured margin above/below (painted by the view's own
          MAP_OCEAN background brush, since nothing is drawn there) rather
          than ever touching width/longitude.
        - If the viewport is proportionally wider than 2:1 (e.g. 683x485),
          latitude crops instead, biased toward MAP_CENTER_LAT_DEG per SPEC
          §7's centre rule, but never by more than MAX_POLE_CROP_DEG off
          either pole; if even that budget-capped crop can't reach the
          viewport's aspect (an extreme, rare window shape), the remainder is
          made up by padding width with ocean margin instead of cropping
          latitude further -- longitude is still never cropped.
        """
        img_w, img_h = image_rect.width(), image_rect.height()
        if img_w <= 0 or img_h <= 0 or viewport_aspect <= 0:
            return image_rect
        img_aspect = img_w / img_h

        deg_per_px_lat = 180.0 / img_h
        max_crop_px = MAX_POLE_CROP_DEG / deg_per_px_lat
        min_visible_h = max(1.0, img_h - 2 * max_crop_px)

        if viewport_aspect <= img_aspect:
            padded_w = img_w
            padded_h = img_w / viewport_aspect
        else:
            desired_h = img_w / viewport_aspect
            if desired_h >= min_visible_h:
                padded_w = img_w
                padded_h = desired_h
            else:
                padded_h = min_visible_h
                padded_w = padded_h * viewport_aspect

        x0 = image_rect.x() - (padded_w - img_w) / 2.0
        if padded_h >= img_h:
            y0 = image_rect.y() - (padded_h - img_h) / 2.0
        else:
            # Biasing the crop window toward MAP_CENTER_LAT_DEG can't be
            # allowed to push either pole's own crop past max_crop_px even
            # though the *total* north+south crop is within budget (e.g. an
            # unclamped bias could zero out the north crop while doubling
            # the south one) -- clamp the north-side crop individually so
            # both poles stay within budget, same as the symmetric fallback
            # above already guarantees.
            total_crop_px = img_h - padded_h
            center_y_local = img_h / 2.0 - (MAP_CENTER_LAT_DEG / 90.0) * (img_h / 2.0)
            top_local_natural = center_y_local - padded_h / 2.0
            lo = max(0.0, total_crop_px - max_crop_px)
            hi = min(total_crop_px, max_crop_px)
            top_local = max(lo, min(top_local_natural, hi))
            y0 = image_rect.y() + top_local

        return QRectF(x0, y0, padded_w, padded_h)

    def _fit_scene_rect(self, rect: QRectF) -> None:
        """Fits `rect` (the real basemap's bounding rect) into the viewport
        via a scene rect padded to the viewport's own aspect ratio
        (_padded_scene_rect) rather than cropping whichever axis the
        viewport's own aspect overshoots (the old unconditional
        KeepAspectRatioByExpanding behaviour, which cropped longitude at
        1280x800 -- see p4-findings.md "(e) Map framing"). Once the padded
        rect's aspect matches the viewport's, KeepAspectRatio (contain) and
        KeepAspectRatioByExpanding (cover) are identical, since there's
        nothing left to crop or letterbox; KeepAspectRatio is used as the
        "fit exactly" intent. The view is still scaled uniformly (m11==m22),
        so overlays/markers drawn in the same scene coordinates as the
        basemap never drift out of alignment."""
        if rect.width() <= 0 or rect.height() <= 0:
            return
        vp = self.view.viewport()
        vp_w, vp_h = vp.width(), vp.height()
        if vp_w <= 0 or vp_h <= 0:
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            return
        padded = self._padded_scene_rect(rect, vp_w / vp_h)
        self.view.fitInView(padded, Qt.AspectRatioMode.KeepAspectRatio)

    def _overlay_refresh_key(self, scene: MapScene, snapshot: _MapStateSnapshot) -> tuple:
        return (
            round(scene.sun_lon_deg, 1),
            round(scene.declination_deg, 1),
            round(snapshot.slider_offset_hours, 1),
            self._layers.greyline,
            self._layers.night,
            self._layers.aurora,
            self._layers.grid,
            round(float(snapshot.kp_index), 1),
        )

    def _update_overlay_from_qimage(self, scene: MapScene, snapshot: _MapStateSnapshot, qimage: QImage) -> None:
        key = self._overlay_refresh_key(scene, snapshot)
        if key == self._overlay_key and self._overlay_pixmap is not None:
            return
        pixmap = QPixmap.fromImage(qimage)
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
        """Dispatches to a worker thread (P1): build_scene()'s PIL compositing and
        the PIL->QImage conversion never run on the UI thread. Only the final
        QImage (and the lightweight vector annotation data) comes back here,
        where it's turned into a QPixmap (QPixmap is UI-thread only) and painted.
        """
        snapshot = _MapStateSnapshot(
            slider_offset_hours=state.slider_offset_hours,
            kp_index=state.kp_index,
            user_lat=state.user_lat,
            user_lon=state.user_lon,
        )
        args = (snapshot, list(spots), dict(coordinates), vectors_only, self._layers)
        self._rebuild_generation += 1
        gen = self._rebuild_generation
        if self._rebuild_running:
            self._pending_rebuild = (gen, args)
            return
        self._start_rebuild(gen, args)

    def _start_rebuild(self, gen: int, args: tuple) -> None:
        snapshot, spots, coordinates, vectors_only, layers = args
        need_base = self._base_pixmap is None or self._base_item.pixmap().isNull()
        self._rebuild_running = True
        deliver = self._invoker.wrap(lambda result: self._on_scene_built(gen, args, result))

        def worker() -> None:
            scene = self.renderer.build_scene(snapshot, layers, spots, coordinates)
            overlay_qimage = None if vectors_only else _pil_to_qimage(scene.overlay_rgba)
            base_qimage = _pil_to_qimage(scene.base_rgba) if need_base else None
            deliver((scene, overlay_qimage, base_qimage))

        self._rebuild_thread = threading.Thread(target=worker, daemon=True, name="map-rebuild")
        self._rebuild_thread.start()

    def join_rebuild_thread(self, timeout: float = 2.0) -> bool:
        """Blocks until no rebuild worker is in flight, or `timeout` elapses.
        Must be called on the UI thread: a finished worker's result is only
        delivered (clearing _rebuild_running, and possibly starting a new
        worker for a coalesced pending request) via a queued call that needs
        this thread's event loop pumped, so this pumps processEvents() while
        waiting rather than blocking the loop out. Returns True once idle,
        False if still rebuilding when the timeout elapsed."""
        import time

        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        deadline = time.monotonic() + timeout
        while self._rebuild_running or (self._rebuild_thread is not None and self._rebuild_thread.is_alive()):
            if time.monotonic() > deadline:
                return False
            thread = self._rebuild_thread
            if thread is not None and thread.is_alive():
                thread.join(timeout=0.05)
            if app is not None:
                app.processEvents()
            else:
                time.sleep(0.01)
        return True

    def _on_scene_built(self, gen: int, args: tuple, result: tuple) -> None:
        snapshot, _spots, _coordinates, vectors_only, _layers = args
        scene, overlay_qimage, base_qimage = result
        self._apply_scene(scene, overlay_qimage, base_qimage, snapshot, vectors_only)
        self._rebuild_running = False
        if self._pending_rebuild is not None:
            next_gen, next_args = self._pending_rebuild
            self._pending_rebuild = None
            self._start_rebuild(next_gen, next_args)

    def _apply_scene(
        self,
        scene: MapScene,
        overlay_qimage: QImage | None,
        base_qimage: QImage | None,
        snapshot: _MapStateSnapshot,
        vectors_only: bool,
    ) -> None:
        self._scene_data = scene

        if base_qimage is not None:
            self._assign_base_pixmap(QPixmap.fromImage(base_qimage), base_qimage.width(), base_qimage.height())

        if not vectors_only and overlay_qimage is not None:
            self._update_overlay_from_qimage(scene, snapshot, overlay_qimage)

        self._draw_vectors(scene)
        offset = snapshot.slider_offset_hours
        now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=offset)
        extra = f"  ({format_hour_offset(offset)})" if offset else ""
        # SPEC §6.2/§12 callout 1: "Greyline · <date> <time> UTC" -- this
        # caption now drives the map header (G3), not just the in-map legend
        # and status bar, so its separator matches the mockup exactly.
        meta = f"Greyline · {format_map_hud_datetime(now)}{extra}"
        self.hud.setText("")  # gestures live on the help chip; meta under the title
        self.hud.hide()
        self._greyline_meta_text = meta
        self._reposition_legend()
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
        # P4-8 (SPEC §7): "Double-click reset returns to this [cover]
        # framing, not to contain" -- resetTransform() alone would leave the
        # view at a raw 1:1 scale instead of the padded/cropped fit
        # _fit_map_view() establishes, so re-run that fit instead of just
        # clearing the transform.
        self._fit_map_view()
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
        self._reposition_empty_overlay()

    def _fit_map_view(self) -> None:
        if self._base_item.pixmap() and not self._base_item.pixmap().isNull():
            r = self._base_item.boundingRect()
            if r.width() > 0 and r.height() > 0:
                self._fit_scene_rect(r)
