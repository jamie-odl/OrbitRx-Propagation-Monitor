from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orbitrx.paths import user_data_path

DEFAULT_CONFIG: dict[str, Any] = {
    "cat_port": "COM3",
    "cat_baud": 9600,
    "cat_timeout": 0.5,
    "cat_rig_profile": "kenwood",
    "cat_confirm_before_tune": True,
    "dx_cluster_host": "dxc.ve7cc.net",
    "dx_cluster_port": 23,
    "dx_cluster_callsign": "",
    "dx_cluster_nodes": [
        {"name": "VE7CC", "host": "dxc.ve7cc.net", "port": 23},
        {"name": "NC7J", "host": "nc7j.com", "port": 7373},
    ],
    "dx_filter_bands_mhz": [],
    "dx_filter_continents": [],
    "dx_spot_sound_alert": True,
    "dx_dedup_seconds": 30,
    "qrz_api_key": "",
    "alert_kp_threshold": 2,
    "alert_muf_threshold": 28,
    "storm_kp_threshold": 7,
    "refresh_interval_seconds": 60,
    "target_dx_lat": None,
    "target_dx_lon": None,
    "theme": "dark",
    "window_geometry": "1300x700",
    "map_layers": {"greyline": True, "night": True, "dx_arcs": True, "aurora": True, "grid": False,
                   "spot_arcs": True, "spot_heatmap": False},
    "log_max_mb": 10,
    "offline_cache_enabled": True,
    "show_demo_spots": False,
    "map_backend": "static",
    "target_dx_callsign": "",
    "minimize_to_tray": True,
    "check_updates_on_launch": True,
    "rig_profiles": [],
    # Rig control backend: "serial" (pyserial CAT) or "omnirig" (Windows OmniRig COM)
    "rig_control": "serial",
    "omnirig_rig_number": 1,
    # Location: manual lat/lon by default; IP geolocation is opt-in (privacy)
    "ip_geolocation_enabled": False,
    "home_lat": 51.5081,  # London centre (Trafalgar Sq); never a private home
    "home_lon": -0.1281,
    # Live Spots (PSKReporter). Poll interval is clamped to 300 s minimum.
    "spots_enabled": True,
    "spots_mode": "FT8",
    "spots_callsign": "",
    "pskreporter_poll_seconds": 300,
    "spot_alerts_enabled": True,
    "watchlist": {"callsigns": [], "countries": [], "prefixes": [], "regions": []},
}


# The old Settings spin boxes used -90 / -180 as the "not set" sentinel.
# That pair is the South Pole on the date line, so it must not stay stored
# as a real coordinate. A lone -90 or a lone -180 is left alone.
_UNSET_LAT = -90.0
_UNSET_LON = -180.0
_COORD_PAIRS = (("home_lat", "home_lon"), ("target_dx_lat", "target_dx_lon"))


def _number_equals(value: Any, target: float) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return float(value) == target
    if isinstance(value, str):
        try:
            return float(value.strip()) == target
        except ValueError:
            return False
    return False


def migrate_unset_coordinates(data: dict[str, Any]) -> bool:
    """Rewrite a stored sentinel pair (-90, -180) to null. Returns True if changed."""
    changed = False
    for lat_key, lon_key in _COORD_PAIRS:
        if _number_equals(data.get(lat_key), _UNSET_LAT) and _number_equals(data.get(lon_key), _UNSET_LON):
            data[lat_key] = None
            data[lon_key] = None
            changed = True
    return changed


@dataclass
class AppConfig:
    path: Path = field(default_factory=lambda: user_data_path("config.json"))
    data: dict[str, Any] = field(default_factory=lambda: deepcopy(DEFAULT_CONFIG))
    _dirty: bool = field(default=False, init=False, repr=False, compare=False)

    def load(self) -> AppConfig:
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            merged = deepcopy(DEFAULT_CONFIG)
            merged.update(loaded)
            if migrate_unset_coordinates(merged):
                self.data = merged
                self.save()
            else:
                self.data = merged
        else:
            self.save()
        return self

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        self._dirty = False

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Single-key update, saved immediately. Kept for every existing caller
        that expects one write per call; batch multiple keys with set_many()
        + flush() instead when a single combined write matters (e.g. the
        Settings dialog's Apply button)."""
        self.data[key] = value
        self.save()

    def set_many(self, mapping: dict[str, Any]) -> None:
        """Update several keys in memory without writing to disk. Pair with an
        explicit flush() so a batch of changes costs exactly one write instead
        of one per key."""
        self.data.update(mapping)
        self._dirty = True

    def flush(self) -> None:
        """Write to disk if set_many() left unsaved changes; a no-op otherwise."""
        if self._dirty:
            self.save()
