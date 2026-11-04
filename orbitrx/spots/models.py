"""Typed application models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ManualLocation:
    lat: float = 0.0
    lon: float = 0.0
    grid_square: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    timezone: str = "UTC"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ManualLocation":
        payload = payload or {}
        return cls(
            lat=float(payload.get("lat", 0.0) or 0.0),
            lon=float(payload.get("lon", 0.0) or 0.0),
            grid_square=str(payload.get("grid_square", "") or ""),
            city=str(payload.get("city", "") or ""),
            region=str(payload.get("region", "") or ""),
            country=str(payload.get("country", "") or ""),
            timezone=str(payload.get("timezone", "UTC") or "UTC"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StationProfile:
    operator_name: str = ""
    antenna: str = ""
    power_watts: int = 100
    preferred_band: str = "20m"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "StationProfile":
        payload = payload or {}
        return cls(
            operator_name=str(payload.get("operator_name", "") or ""),
            antenna=str(payload.get("antenna", "") or ""),
            power_watts=int(payload.get("power_watts", 100) or 100),
            preferred_band=str(payload.get("preferred_band", "20m") or "20m"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AlertSettings:
    enabled: bool = True
    desktop_popups: bool = True
    distance_opening_miles: float = 1500.0
    local_spot_threshold: int = 8
    strong_signal_threshold_db: float = -5.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AlertSettings":
        payload = payload or {}
        return cls(
            enabled=bool(payload.get("enabled", True)),
            desktop_popups=bool(payload.get("desktop_popups", True)),
            distance_opening_miles=float(payload.get("distance_opening_miles", 1500.0) or 1500.0),
            local_spot_threshold=int(payload.get("local_spot_threshold", 8) or 8),
            strong_signal_threshold_db=float(payload.get("strong_signal_threshold_db", -5.0) or -5.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CatControlSettings:
    enabled: bool = False
    rig_number: int = 1
    tune_on_map_click: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "CatControlSettings":
        payload = payload or {}
        return cls(
            enabled=bool(payload.get("enabled", False)),
            rig_number=max(1, min(2, int(payload.get("rig_number", 1) or 1))),
            tune_on_map_click=bool(payload.get("tune_on_map_click", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WatchlistSettings:
    callsigns: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)
    alerts_enabled: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "WatchlistSettings":
        payload = payload or {}
        return cls(
            callsigns=[str(item).upper() for item in (payload.get("callsigns") or []) if str(item).strip()],
            countries=[str(item) for item in (payload.get("countries") or []) if str(item).strip()],
            prefixes=[str(item).upper() for item in (payload.get("prefixes") or []) if str(item).strip()],
            regions=[str(item) for item in (payload.get("regions") or []) if str(item).strip()],
            alerts_enabled=bool(payload.get("alerts_enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "callsigns": self.callsigns,
            "countries": self.countries,
            "prefixes": self.prefixes,
            "regions": self.regions,
            "alerts_enabled": self.alerts_enabled,
        }


@dataclass(slots=True)
class LayoutPreferences:
    active_layout: str = "Operator"
    dense_cards: bool = False
    saved_layouts: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LayoutPreferences":
        payload = payload or {}
        saved = payload.get("saved_layouts")
        if not isinstance(saved, dict):
            saved = {}
        return cls(
            active_layout=str(payload.get("active_layout", "Operator") or "Operator"),
            dense_cards=bool(payload.get("dense_cards", False)),
            saved_layouts={str(name): dict(layout) for name, layout in saved.items() if isinstance(layout, dict)},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_layout": self.active_layout,
            "dense_cards": self.dense_cards,
            "saved_layouts": self.saved_layouts,
        }


@dataclass(slots=True)
class VisualPreferences:
    theme_mode: str = "Day Ops"
    map_style: str = "Satellite"
    map_brightness: float = 1.08
    map_saturation: float = 1.12
    dx_line_thickness: float = 4.0
    dx_line_fade_pct: int = 72
    clutter_reduction: bool = True
    show_grayline_overlay: bool = True
    show_band_haze: bool = True
    region_focus: str = "Global"
    panel_order: list[str] = field(default_factory=list)
    popout_geometries: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "VisualPreferences":
        payload = payload or {}
        return cls(
            theme_mode=str(payload.get("theme_mode", "Day Ops") or "Day Ops"),
            map_style=str(payload.get("map_style", "Satellite") or "Satellite"),
            map_brightness=float(payload.get("map_brightness", 1.08) or 1.08),
            map_saturation=float(payload.get("map_saturation", 1.12) or 1.12),
            dx_line_thickness=float(payload.get("dx_line_thickness", 4.0) or 4.0),
            dx_line_fade_pct=int(payload.get("dx_line_fade_pct", 72) or 72),
            clutter_reduction=bool(payload.get("clutter_reduction", True)),
            show_grayline_overlay=bool(payload.get("show_grayline_overlay", True)),
            show_band_haze=bool(payload.get("show_band_haze", True)),
            region_focus=str(payload.get("region_focus", "Global") or "Global"),
            panel_order=[str(item) for item in (payload.get("panel_order") or []) if str(item).strip()],
            popout_geometries={
                str(name): str(value)
                for name, value in (payload.get("popout_geometries") or {}).items()
                if str(name).strip() and str(value).strip()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UserSettings:
    callsign: str = ""
    strict_privacy_mode: bool = False
    use_manual_location: bool = False
    manual_location: ManualLocation = field(default_factory=ManualLocation)
    station_profile: StationProfile = field(default_factory=StationProfile)
    alert_settings: AlertSettings = field(default_factory=AlertSettings)
    cat_control: CatControlSettings = field(default_factory=CatControlSettings)
    watchlist: WatchlistSettings = field(default_factory=WatchlistSettings)
    layout_preferences: LayoutPreferences = field(default_factory=LayoutPreferences)
    visual_preferences: VisualPreferences = field(default_factory=VisualPreferences)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "UserSettings":
        payload = payload or {}
        return cls(
            callsign=str(payload.get("callsign", "") or ""),
            strict_privacy_mode=bool(payload.get("strict_privacy_mode", False)),
            use_manual_location=bool(payload.get("use_manual_location", False)),
            manual_location=ManualLocation.from_dict(payload.get("manual_location")),
            station_profile=StationProfile.from_dict(payload.get("station_profile")),
            alert_settings=AlertSettings.from_dict(payload.get("alert_settings")),
            cat_control=CatControlSettings.from_dict(payload.get("cat_control")),
            watchlist=WatchlistSettings.from_dict(payload.get("watchlist")),
            layout_preferences=LayoutPreferences.from_dict(payload.get("layout_preferences")),
            visual_preferences=VisualPreferences.from_dict(payload.get("visual_preferences")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "callsign": self.callsign,
            "strict_privacy_mode": self.strict_privacy_mode,
            "use_manual_location": self.use_manual_location,
            "manual_location": self.manual_location.to_dict(),
            "station_profile": self.station_profile.to_dict(),
            "alert_settings": self.alert_settings.to_dict(),
            "cat_control": self.cat_control.to_dict(),
            "watchlist": self.watchlist.to_dict(),
            "layout_preferences": self.layout_preferences.to_dict(),
            "visual_preferences": self.visual_preferences.to_dict(),
        }


@dataclass(slots=True)
class LocationInfo:
    lat: float
    lon: float
    city: str
    region: str
    country: str
    timezone: str
    source: str
    is_fallback: bool = False


@dataclass(slots=True)
class Spot:
    rx_lat: float
    rx_lon: float
    tx_lat: float
    tx_lon: float
    frequency_hz: float
    mode: str
    sender: str
    receiver: str
    snr_db: float
    flow_start_seconds: int
    observed_at_utc: str = ""
    source: str = "pskreporter"


@dataclass(slots=True)
class SpaceWeatherData:
    kp_index: float | None = None
    solar_flux: float | None = None
    status: str = "fallback"
    message: str = "Space weather unavailable"


@dataclass(slots=True)
class BandCondition:
    band: str
    score: int
    status: str
    spot_count: int
    median_snr: float
    max_distance_miles: float


@dataclass(slots=True)
class AlertEvent:
    title: str
    message: str
    severity: str
    event_key: str
    created_at_utc: str


@dataclass(slots=True)
class AppDiagnostics:
    cached_spot_count: int
    last_cached_at_utc: str
    database_path: str
    settings_path: str
    log_path: str
    update_status: str
