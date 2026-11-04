from __future__ import annotations

import datetime
import json
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from orbitrx.alerts import check_alarms
from orbitrx.cat import CatController
from orbitrx.config import AppConfig
from orbitrx.contests import get_next_contest
from orbitrx.dx import DxClusterService
from orbitrx.logger import setup_logging
from orbitrx.map_renderer import MapLayers
from orbitrx.dx import resolve_target_position
from orbitrx.hamqsl import fetch_solar_xml, hamqsl_path_muf
from orbitrx.propagation import band_chip, band_grid, bands_summary, estimate_muf, flux_trend_arrow
from orbitrx.state import AppState
from orbitrx.storage import DataStore
from orbitrx.ui.formatting import decimal_hours_to_hhmm, format_iso_utc, format_source_label, format_value
from orbitrx.utils import estimate_location, local_time_at_lon, sun_times
from orbitrx.weather import fetch_space_weather_data
from orbitrx.alerts import show_toast
from orbitrx.spots.service import SpotsService

try:
    import platform
    if platform.system() == "Windows":
        import winsound
    else:
        winsound = None
except Exception:
    winsound = None


class OrbitRxController:
    """UI-agnostic application logic."""

    def __init__(
        self,
        on_status: Callable[[str], None] | None = None,
        on_weather: Callable[[], None] | None = None,
        on_dx: Callable[[], None] | None = None,
        on_cluster: Callable[[str], None] | None = None,
        on_alarm_excellent: Callable[[], None] | None = None,
        on_alarm_storm: Callable[[], None] | None = None,
        on_band_beep: Callable[[dict], None] | None = None,
    ) -> None:
        self.log = setup_logging()
        self.cfg = AppConfig().load()
        self.state = AppState()
        self.store = DataStore(log_max_mb=int(self.cfg.get("log_max_mb", 10)))
        self.cat = CatController(self.cfg)
        self._on_status = on_status or (lambda _s: None)
        self._on_weather = on_weather or (lambda: None)
        self._on_dx = on_dx or (lambda: None)
        self._on_cluster = on_cluster or (lambda _s: None)
        self._on_alarm_excellent = on_alarm_excellent or (lambda: None)
        self._on_alarm_storm = on_alarm_storm or (lambda: None)
        self._on_band_beep = on_band_beep or (lambda _s: None)

        self._dx = DxClusterService(
            self.state,
            self.cfg,
            on_spot=self._schedule_dx_ui,
            on_status=self._on_cluster,
            on_band_alert=self._on_band_beep,
            store=self.store,
        )

        self.on_live_spots: Callable[[], None] = lambda: None
        self.spots = SpotsService(
            self.cfg,
            on_spots=lambda _s: self.on_live_spots(),
            on_alert=self._spot_alert,
            location=lambda: (self.state.user_lat, self.state.user_lon),
        )

    def _spot_alert(self, title: str, message: str) -> None:
        show_toast(f"OrbitRx: {title}", message)
        self._on_status(f"{title}: {message}")

    def start(self) -> None:
        self._dx.start()
        self.spots.start()

    def stop(self) -> None:
        self.cat.disconnect()
        self._dx.stop()
        self.spots.stop()

    def layers_from_config(self) -> MapLayers:
        ml = self.cfg.get("map_layers", {})
        return MapLayers(
            greyline=ml.get("greyline", True),
            night=ml.get("night", True),
            dx_arcs=ml.get("dx_arcs", True),
            aurora=ml.get("aurora", True),
            grid=ml.get("grid", False),
        )

    def seed_demo_spots(self) -> None:
        if not self.cfg.get("show_demo_spots", True):
            return
        demos = [
            {"from": "W5XYZ", "to": "PY2AB", "freq": 28.456, "time": time.time(), "demo": True},
            {"from": "VE3ABC", "to": "XU7AJ", "freq": 21.285, "time": time.time(), "demo": True},
        ]
        with self.state.dx_lock:
            for s in demos:
                self.state.dx_coordinates.setdefault(s["from"], estimate_location(s["from"]))
                self.state.dx_coordinates.setdefault(s["to"], estimate_location(s["to"]))
            self.state.latest_dx_spots.extend(demos)

    def get_spots_snapshot(self) -> tuple[list[dict], dict[str, tuple[float, float]]]:
        with self.state.dx_lock:
            return list(self.state.latest_dx_spots), dict(self.state.dx_coordinates)

    def _schedule_dx_ui(self) -> None:
        if not self.state.dx_update_pending:
            self.state.dx_update_pending = True
            threading.Timer(0.5, self._update_dx).start()

    def _update_dx(self) -> None:
        self.state.dx_update_pending = False
        self.state.prune_dx_spots()
        self._on_dx()

    def refresh_location(self) -> None:
        """Use the manual home position; IP geolocation only when the user opted in."""
        home_lat, home_lon = self.cfg.get("home_lat"), self.cfg.get("home_lon")
        if home_lat is not None and home_lon is not None:
            try:
                self.state.user_lat = float(home_lat)
                self.state.user_lon = float(home_lon)
            except (TypeError, ValueError):
                self.log.warning("Invalid home_lat/home_lon in config")
            self._on_weather()
            return
        if not self.cfg.get("ip_geolocation_enabled", False):
            self._on_weather()
            return

        def worker():
            try:
                r = urllib.request.urlopen("https://ipinfo.io/json", timeout=5)
                info = json.loads(r.read())
                if "loc" in info:
                    la, lo = info["loc"].split(",")
                    self.state.user_lat = float(la)
                    self.state.user_lon = float(lo)
            except Exception as e:
                self.log.warning("Location failed: %s", e)
                self.state.user_lat = None
                self.state.user_lon = None
            self._on_weather()
        threading.Thread(target=worker, daemon=True).start()

    def fetch_weather(self) -> None:
        if self.state.weather_fetch_in_progress:
            return
        self.state.weather_fetch_in_progress = True

        def worker():
            try:
                data = fetch_space_weather_data()
                if self.cfg.get("offline_cache_enabled"):
                    self.store.save_weather_cache(data)
                offline = False
            except Exception as e:
                self.log.warning("Weather fetch failed: %s", e)
                data = self.store.load_weather_cache() if self.cfg.get("offline_cache_enabled") else None
                offline = True
                if not data:
                    self._on_status(f"Weather error: {e}")
                    self.state.weather_fetch_in_progress = False
                    return
            try:
                self._apply_weather(data, offline)
            except Exception:
                self.log.exception("Applying weather data failed")
                self._on_status("Space weather update failed, see logs/orbitrx.log")
            finally:
                self.state.weather_fetch_in_progress = False

        threading.Thread(target=worker, daemon=True).start()

    def _apply_weather(self, data: dict[str, Any], offline: bool = False) -> None:
        self.state.kp_index = float(data.get("kp_index", 0))
        self.state.flux = data.get("flux")
        self.state.a_index = data.get("a_index")
        self.state.a_index_source = data.get("a_index_source")
        self.state.solar_wind_speed = data.get("solar_wind_speed")
        self.state.bz = data.get("bz")
        self.state.sunspot_observed = data.get("sunspot_observed")
        self.state.sunspot_predicted = data.get("sunspot_predicted")
        self.state.time_utc = data.get("time_utc", "--")
        self.state.kp_forecast = data.get("kp_forecast", "--")
        self.state.alerts = data.get("alerts", [])
        self.state.solar_forecast = data.get("solar_forecast", "--")
        self.state.flux_trend = flux_trend_arrow(self.store.recent_flux(5))
        muf, luf = estimate_muf(self.state.flux, self.state.kp_index)
        self.state.muf, self.state.luf = muf, luf
        self.state.band_grid = band_grid(self.state.flux, self.state.kp_index)
        self.state.bands_summary = bands_summary(self.state.flux, self.state.kp_index)
        hamqsl = fetch_solar_xml()
        if hamqsl and hamqsl.get("bands"):
            self.state.hamqsl_band_hint = " | ".join(hamqsl["bands"][:4])
        else:
            self.state.hamqsl_band_hint = ""
        if self.state.user_lat and self.state.user_lon:
            tlat, tlon, src = self._path_target()
            self.state.path_muf, muf_src = hamqsl_path_muf(
                self.state.flux, self.state.kp_index,
                self.state.user_lat, self.state.user_lon, tlat, tlon, hamqsl,
            )
            self.state.path_muf_label = f"{src} ({muf_src})"
        else:
            self.state.path_muf = None
            self.state.path_muf_label = None
        self.state.last_weather_update = datetime.datetime.now(datetime.timezone.utc)
        ss = self.state.sunspot_observed or self.state.sunspot_predicted
        self.store.log_propagation({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kp": self.state.kp_index, "flux": self.state.flux, "sunspot": ss,
            "muf": muf, "luf": luf, "band_cond": self.state.bands_summary,
            "lat": self.state.user_lat, "lon": self.state.user_lon,
            "a_index": self.state.a_index,
            "solar_wind": self.state.solar_wind_speed, "bz": self.state.bz,
        })
        el, sl = check_alarms(
            self.state.kp_index, self.state.muf,
            float(self.cfg.get("alert_kp_threshold", 2)),
            float(self.cfg.get("alert_muf_threshold", 28)),
            float(self.cfg.get("storm_kp_threshold", 7)),
            self.state.alert_excellent_last, self.state.alert_storm_last,
            self._on_alarm_excellent, self._on_alarm_storm,
        )
        self.state.alert_excellent_last = el
        self.state.alert_storm_last = sl
        if offline:
            self._on_status("Offline: NOAA unreachable, showing cached space weather")
        self._on_weather()

    def _path_target(self) -> tuple[float, float, str]:
        callsign = (self.cfg.get("target_dx_callsign") or "").strip()
        if callsign:
            try:
                lat, lon, src = resolve_target_position(callsign, self.cfg, self.state)
                return lat, lon, callsign if src == "qrz" else f"{callsign}~prefix"
            except ValueError:
                pass
        tlat = self.cfg.get("target_dx_lat")
        tlon = self.cfg.get("target_dx_lon")
        if tlat is not None and tlon is not None:
            return float(tlat), float(tlon), "configured"
        return 35.68, 139.65, "JA default"

    def last_updated_text(self) -> str:
        parts = []
        w = self.state.last_weather_update
        d = self.state.last_dx_update
        if w:
            parts.append(f"Weather updated {w.strftime('%H:%M')} UTC")
        if d:
            parts.append(f"DX updated {d.strftime('%H:%M')} UTC")
        return " · ".join(parts) if parts else "Last updated: never"

    def coord_source_summary(self, callsign: str) -> str:
        src = self.state.dx_coord_source.get(callsign, "")
        if src == "qrz":
            return "QRZ"
        if src == "prefix":
            return "prefix"
        return ""

    def tune_radio(self, freq: float, confirm: Callable[[str], bool] | None) -> str:
        return self.cat.tune(freq, confirm=confirm)

    def spot_beep(self, _spot: dict) -> None:
        if self.cfg.get("dx_spot_sound_alert") and winsound:
            winsound.MessageBeep(winsound.MB_OK)

    def export_json(self) -> Path:
        return self.store.export_json_snapshot({
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kp_index": self.state.kp_index,
            "solar_flux": self.state.flux,
            "muf_mhz": self.state.muf,
            "path_muf_mhz": self.state.path_muf,
            "band_grid": self.state.band_grid,
            "user_location": {"lat": self.state.user_lat, "lon": self.state.user_lon},
        })

    def weather_labels(self) -> dict[str, str]:
        s = self.state
        ss = s.sunspot_observed or s.sunspot_predicted
        grid = " ".join(f"{band_chip(v)}{k}" for k, v in s.band_grid.items())
        loc = f"You: {s.user_lat:.3f}, {s.user_lon:.3f}" if s.user_lat else "You: n/a"
        sr_txt = ss_txt = "n/a"
        if s.user_lat and s.user_lon:
            sr, ssun = sun_times(s.user_lat, s.user_lon, datetime.datetime.now(datetime.timezone.utc))
            if sr:
                sr_txt, ss_txt = decimal_hours_to_hhmm(sr), decimal_hours_to_hhmm(ssun)
        with s.dx_lock:
            vis = list(s.latest_dx_spots[:2])
        dx_parts = []
        for x in vis:
            tag = "[DEMO] " if x.get("demo") else ""
            to_cs = x.get("to", "")
            src = self.coord_source_summary(to_cs)
            src_tag = f" [{src}]" if src else ""
            dx_parts.append(f"{tag}{x['from']}→{to_cs}{src_tag} {x['freq']} MHz")
        dx = " | ".join(dx_parts) or "n/a"
        nc = get_next_contest()
        a_src = format_source_label(getattr(s, "a_index_source", None))
        a_txt = format_value(s.a_index, fmt="{:g}")
        if a_src:
            a_txt = f"{a_txt} ({a_src})"
        path_muf_txt = f"Path MUF: {format_value(s.path_muf)} MHz"
        if s.path_muf_label:
            path_muf_txt += f" → {s.path_muf_label}"
        return {
            "kp": f"Kp: {s.kp_index:.2f}",
            "kp_forecast": f"Kp Forecast: {s.kp_forecast}",
            "solar": f"Solar Flux: {format_value(s.flux)} {s.flux_trend}".rstrip(),
            "sunspot": f"Sunspot: {ss:.1f}" if ss else "Sunspot: n/a",
            "a_index": f"A-index: {a_txt}",
            "solar_wind": f"Wind: {format_value(s.solar_wind_speed, unit=' km/s')}  "
                            f"Bz: {format_value(s.bz, unit=' nT')}",
            "time": f"NOAA data: {format_iso_utc(s.time_utc)}",
            "bands": f"Bands: {s.bands_summary}",
            "band_grid": f"Per-band: {grid}",
            "muf": f"MUF: {format_value(s.muf)} / LUF: {format_value(s.luf)} MHz",
            "path_muf": path_muf_txt,
            "hamqsl": f"HamQSL: {s.hamqsl_band_hint or 'n/a'}",
            "sunrise": f"Sunrise UTC: {sr_txt}",
            "sunset": f"Sunset UTC: {ss_txt}",
            "alerts": "Alerts:\n" + ("\n".join(s.alerts[:3]) or "none"),
            "location": loc,
            "solar_forecast": f"27-Day: {s.solar_forecast}",
            "contest": f"Next: {nc['name']}" if nc else "Next: none",
            "dx": f"DX: {dx}",
        }

    def map_click_latlon(self, x: float, y: float, renderer) -> str:
        lat, lon = renderer.map_to_world(x, y)
        return f"{lat:.1f}°, {lon:.1f}° → local ~{local_time_at_lon(lon)}"
