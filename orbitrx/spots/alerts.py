"""Alert evaluation helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from orbitrx.spots.settings import LOCAL_VIEW_RADIUS_MILES
from orbitrx.spots.models import AlertEvent, LocationInfo, Spot, UserSettings
from orbitrx.spots.bandplan import band_info
from orbitrx.spots.database import was_alert_recent
from orbitrx.spots.pskreporter import filter_spots_near_location, haversine_distance_miles


def evaluate_alerts(spots: list[Spot], home_location: LocationInfo, settings: UserSettings) -> list[AlertEvent]:
    if not settings.alert_settings.enabled or not spots:
        return []

    alerts: list[AlertEvent] = []
    now = datetime.now(timezone.utc).isoformat()
    local_spots = filter_spots_near_location(spots, home_location.lat, home_location.lon, LOCAL_VIEW_RADIUS_MILES)
    if len(local_spots) >= settings.alert_settings.local_spot_threshold:
        key = f"local-threshold-{settings.alert_settings.local_spot_threshold}"
        if not was_alert_recent(key):
            alerts.append(
                AlertEvent(
                    title="Local Band Activity",
                    message=f"{len(local_spots)} spots are active within {LOCAL_VIEW_RADIUS_MILES:.0f} miles of HOME.",
                    severity="info",
                    event_key=key,
                    created_at_utc=now,
                )
            )

    strongest_local = max((spot for spot in local_spots), key=lambda spot: spot.snr_db, default=None)
    if strongest_local is not None and strongest_local.snr_db >= settings.alert_settings.strong_signal_threshold_db:
        band, _color = band_info(strongest_local.frequency_hz)
        key = f"strong-snr-{band}-{int(strongest_local.snr_db)}"
        if not was_alert_recent(key):
            alerts.append(
                AlertEvent(
                    title="Strong Local Copy",
                    message=f"{band} produced {strongest_local.snr_db:+.0f} dB near HOME: {strongest_local.sender} -> {strongest_local.receiver}.",
                    severity="success",
                    event_key=key,
                    created_at_utc=now,
                )
            )

    furthest_spot = None
    furthest_distance = 0.0
    for spot in spots:
        distance = max(
            haversine_distance_miles(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon),
            haversine_distance_miles(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon),
        )
        if distance > furthest_distance:
            furthest_distance = distance
            furthest_spot = spot
    if furthest_spot is not None and furthest_distance >= settings.alert_settings.distance_opening_miles:
        band, _color = band_info(furthest_spot.frequency_hz)
        key = f"distance-opening-{band}-{int(furthest_distance // 100)}"
        if not was_alert_recent(key):
            alerts.append(
                AlertEvent(
                    title="Long-Path Opening",
                    message=f"{band} reached {furthest_distance:.0f} miles from HOME: {furthest_spot.sender} -> {furthest_spot.receiver}.",
                    severity="warning",
                    event_key=key,
                    created_at_utc=now,
                )
            )

    return alerts