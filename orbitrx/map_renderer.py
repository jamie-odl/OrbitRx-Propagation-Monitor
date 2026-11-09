from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from orbitrx.propagation import aurora_oval_lat
from orbitrx.utils import great_circle_points


@dataclass
class MapLayers:
    greyline: bool = True
    night: bool = True
    dx_arcs: bool = True
    aurora: bool = True
    grid: bool = False


@dataclass
class MapAnnotation:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class MapScene:
    """Static raster layers + vector annotations for the UI to paint."""
    width: int
    height: int
    base_rgba: Image.Image
    overlay_rgba: Image.Image
    declination_deg: float
    sun_lon_deg: float
    hour_utc: float
    annotations: list[MapAnnotation]
    # P3: the greyline terminator as a point list (not baked into overlay_rgba), so
    # the Qt widget can stroke it with a cosmetic pen that stays a constant logical
    # width at every zoom level instead of scaling with the raster.
    terminator: list[tuple[float, float]] = field(default_factory=list)


class MapRenderer:
    """Builds cached map layers; DX vectors are separate for fast refresh."""

    def __init__(self, width: int = 900, height: int = 720) -> None:
        self.width = width
        self.height = height
        self._overlay_cache_key: tuple | None = None
        self._cached_overlay: Image.Image | None = None
        self._base_source: Image.Image | None = None

    def set_base_map(self, image: Image.Image | None) -> None:
        if image is None:
            self._base_source = None
            return
        self._base_source = self.prepare_base_map(image)

    def prepare_base_map(self, image: Image.Image) -> Image.Image:
        """Scale a raw basemap image to this renderer's size. Pure PIL work with
        no Qt/state side effects, so it's safe to call off the UI thread (F7);
        pair with set_prescaled_base_map() to assign the result back."""
        return image.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def set_prescaled_base_map(self, image: Image.Image) -> None:
        """Assign a basemap already produced by prepare_base_map()."""
        self._base_source = image

    def base_rgba_image(self) -> Image.Image:
        """RGBA base layer for the Qt widget (world map or placeholder)."""
        if self._base_source is not None:
            return self._base_source.copy().convert("RGBA")
        return Image.new("RGBA", (self.width, self.height), (16, 24, 32, 255))

    def world_to_map(self, lat: float, lon: float) -> tuple[float, float]:
        w, h = self.width, self.height
        x = ((lon + 180) / 360) * w
        y = (h / 2) - ((lat / 90) * (h / 2))
        return x, y

    def map_to_world(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.width, self.height
        lon = (x / w) * 360 - 180
        lat = 90 - (y / (h / 2)) * 90
        return max(-90.0, min(90.0, lat)), lon

    @staticmethod
    def _night_mask(w: int, h: int, decl_rad: float, sun_lon_rad: float) -> Image.Image:
        """Smooth night-side shading from solar elevation on a coarse grid, upscaled."""
        gw, gh = 360, 180
        sin_d, cos_d = math.sin(decl_rad), math.cos(decl_rad)
        alpha = bytearray(gw * gh)
        for j in range(gh):
            lat = math.radians(90 - (j + 0.5))
            sl, cl = math.sin(lat) * sin_d, math.cos(lat) * cos_d
            row = j * gw
            for i in range(gw):
                lon = math.radians(-180 + i + 0.5)
                elev = sl + cl * math.cos(lon - sun_lon_rad)  # sin(solar elevation)
                # civil twilight blend: full dark below -6 degrees
                alpha[row + i] = int(min(1.0, -elev / 0.105) * 120) if elev < 0 else 0
        mask = Image.frombytes("L", (gw, gh), bytes(alpha)).resize((w, h), Image.BILINEAR)
        # M1: night veil only (rgba 8,14,28 @ ~0.55), no second heavy blue wash.
        veil = Image.new("RGBA", (w, h), (8, 14, 28, 0))
        # Remap legacy 0..120 mask into 0..140 (~0.55) without numpy.
        a = mask.point(lambda p: min(140, int(p * 140 / 120)))
        veil.putalpha(a)
        return veil

    @staticmethod
    def _wrap_sun_marker(x: float, y: float, width: int, radius: float = 16.0) -> list[MapAnnotation]:
        """Sun annotation(s), plus a wrapped copy so the marker is never clipped at the
        map's left/right edge (S4): the glow drawn in the Qt widget has radius 16px.
        """
        anns = [MapAnnotation("sun", {"x": x, "y": y})]
        if x - radius < 0:
            anns.append(MapAnnotation("sun", {"x": x + width, "y": y}))
        elif x + radius > width:
            anns.append(MapAnnotation("sun", {"x": x - width, "y": y}))
        return anns

    def _terminator_lat(self, lon_deg: float, decl_rad: float, sun_lon_rad: float) -> float:
        lon_rad = math.radians(lon_deg)
        tan_dec = math.tan(decl_rad)
        if abs(tan_dec) < 0.0001:
            tan_dec = 0.0001
        tan_lat = -math.cos(lon_rad - sun_lon_rad) / tan_dec
        return math.degrees(math.atan(tan_lat))

    def _terminator_points(self, decl_rad: float, sun_lon_rad: float, step: int = 2) -> list[tuple[float, float]]:
        w, h = self.width, self.height
        points: list[tuple[float, float]] = []
        for x in range(0, w + 1, step):
            lon_deg = (x / w) * 360 - 180
            lat_deg = self._terminator_lat(lon_deg, decl_rad, sun_lon_rad)
            y = h / 2 - (lat_deg / 90) * (h / 2)
            y = max(0.0, min(float(h - 1), y))
            points.append((float(x), y))
        return points

    def _build_overlay(
        self,
        offset_hours: float,
        layers: MapLayers,
        kp: float,
    ) -> tuple[Image.Image, float, float, float]:
        w, h = self.width, self.height
        now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=offset_hours)
        day_of_year = now.timetuple().tm_yday
        # Minute resolution is enough for greyline; avoids redraw/flicker every second.
        hour_utc = now.hour + now.minute / 60.0
        declination_deg = -23.44 * math.cos(math.radians((360 / 365.25) * (day_of_year + 10)))
        decl_rad = math.radians(declination_deg)
        sun_lon_deg = 180 - (hour_utc * 15)
        sun_lon_rad = math.radians(sun_lon_deg)

        cache_key = (
            round(offset_hours, 2),
            layers.greyline,
            layers.night,
            layers.aurora,
            layers.grid,
            round(kp, 1),
            w,
            h,
        )
        if self._overlay_cache_key == cache_key and self._cached_overlay is not None:
            return self._cached_overlay, declination_deg, sun_lon_deg, hour_utc

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)

        if layers.grid:
            grid_color = (80, 120, 160, 50)
            for lat in range(-60, 61, 30):
                y = int(h / 2 - (lat / 90) * (h / 2))
                od.line([(0, y), (w, y)], fill=grid_color, width=1)
            for lon in range(-180, 181, 30):
                x = int((lon + 180) / 360 * w)
                od.line([(x, 0), (x, h)], fill=grid_color, width=1)

        if layers.night:
            overlay.alpha_composite(self._night_mask(w, h, decl_rad, sun_lon_rad))

        # P3: the greyline itself is drawn as a vector by the Qt widget (cosmetic
        # pen, constant logical width at every zoom), not baked into this raster.

        if layers.aurora and kp >= 4:
            # M1: thin elliptical stroke, no filled polar blob.
            oval_lat = aurora_oval_lat(kp)
            y_n = int(h / 2 - (oval_lat / 90) * (h / 2))
            y_s = int(h / 2 + (oval_lat / 90) * (h / 2))
            stroke = (61, 220, 151, 115)  # rgba(61,220,151,0.45)
            # Northern oval across the map width
            od.ellipse([(-w * 0.05, y_n - 18), (w * 1.05, y_n + 18)], outline=stroke, width=2)
            od.ellipse([(-w * 0.05, y_s - 18), (w * 1.05, y_s + 18)], outline=stroke, width=2)

        self._overlay_cache_key = cache_key
        self._cached_overlay = overlay
        return overlay, declination_deg, sun_lon_deg, hour_utc

    def build_scene(
        self,
        state: Any,
        layers: MapLayers,
        spots: list[dict[str, Any]],
        coordinates: dict[str, tuple[float, float]],
    ) -> MapScene:
        w, h = self.width, self.height
        if self._base_source is not None:
            base = self._base_source.copy().convert("RGBA")
        else:
            base = Image.new("RGBA", (w, h), (16, 24, 32, 255))

        overlay, decl_deg, sun_lon_deg, hour_utc = self._build_overlay(
            state.slider_offset_hours, layers, float(state.kp_index)
        )
        terminator: list[tuple[float, float]] = []
        if layers.greyline:
            terminator = self._terminator_points(math.radians(decl_deg), math.radians(sun_lon_deg))

        annotations: list[MapAnnotation] = []
        sun_lon_wrapped = (sun_lon_deg + 180) % 360 - 180
        sx, sy = self.world_to_map(decl_deg, sun_lon_wrapped)
        annotations.extend(self._wrap_sun_marker(sx, sy, w))

        if state.user_lat is not None and state.user_lon is not None:
            ux, uy = self.world_to_map(state.user_lat, state.user_lon)
            annotations.append(MapAnnotation("user", {"x": ux, "y": uy}))

        if layers.dx_arcs:
            for spot in spots:
                fpos = coordinates.get(spot.get("from", ""))
                tpos = coordinates.get(spot.get("to", ""))
                if not fpos or not tpos:
                    continue
                paths = self._gc_map_paths(fpos, tpos)
                fx, fy = self.world_to_map(fpos[0], fpos[1])
                tx, ty = self.world_to_map(tpos[0], tpos[1])
                annotations.append(MapAnnotation("dx_spot", {
                    "from": spot.get("from"),
                    "to": spot.get("to"),
                    "freq": spot.get("freq"),
                    "demo": spot.get("demo", False),
                    "age": max(0, int(__import__("time").time() - spot.get("time", 0))),
                    "fx": fx, "fy": fy, "tx": tx, "ty": ty,
                    "paths": paths,
                }))

        return MapScene(
            width=w,
            height=h,
            base_rgba=base,
            overlay_rgba=overlay,
            declination_deg=decl_deg,
            sun_lon_deg=sun_lon_deg,
            hour_utc=hour_utc,
            annotations=annotations,
            terminator=terminator,
        )

    def _gc_map_paths(
        self,
        fpos: tuple[float, float],
        tpos: tuple[float, float],
    ) -> list[list[tuple[float, float]]]:
        gc = great_circle_points(fpos[0], fpos[1], tpos[0], tpos[1], steps=32)
        segments: list[list[tuple[float, float]]] = []
        segment: list[tuple[float, float]] = []
        prev_lon: float | None = None
        for la, lo in gc:
            x, y = self.world_to_map(la, lo)
            if prev_lon is not None and abs(lo - prev_lon) > 180:
                if segment:
                    segments.append(segment)
                segment = []
            segment.append((x, y))
            prev_lon = lo
        if segment:
            segments.append(segment)
        return segments

    def pil_to_rgb_composite(self, scene: MapScene) -> Image.Image:
        return Image.alpha_composite(scene.base_rgba, scene.overlay_rgba).convert("RGB")
