"""Map payload helpers for the Live Spots layer (arcs, heatmap, replay)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable

from orbitrx.spots.bandplan import band_info
from orbitrx.spots.models import Spot
from orbitrx.spots.settings import MAX_RENDERED_ARCS, REPLAY_BUCKET_MINUTES


def coords_to_pixels(lat: float, lon: float, canvas_width: int, canvas_height: int) -> tuple[float, float]:
    x = (lon + 180.0) * (canvas_width / 360.0)
    y = (90.0 - lat) * (canvas_height / 180.0)
    return x, y


SPOT_FRESH_OPACITY = 0.9
# P4: spots older than this fade to SPOT_STALE_OPACITY, so the live layer
# visually distinguishes a fresh catch from one that's aging out of relevance.
SPOT_STALE_AGE_MINUTES = 15
SPOT_STALE_OPACITY = 0.7


def _spot_age_minutes(observed_at_utc: str, now: datetime) -> float | None:
    if not observed_at_utc:
        return None
    try:
        observed = datetime.fromisoformat(observed_at_utc)
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (now - observed).total_seconds() / 60.0


def arcs_payload(spots: Iterable[Spot], limit: int = MAX_RENDERED_ARCS) -> list[dict]:
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for spot in sorted(spots, key=lambda s: s.snr_db, reverse=True)[:limit]:
        band, color = band_info(spot.frequency_hz)
        age_min = _spot_age_minutes(spot.observed_at_utc, now)
        opacity = SPOT_STALE_OPACITY if age_min is not None and age_min > SPOT_STALE_AGE_MINUTES else SPOT_FRESH_OPACITY
        out.append({
            "tx": [spot.tx_lat, spot.tx_lon],
            "rx": [spot.rx_lat, spot.rx_lon],
            "band": band,
            "color": color,
            "label": f"{spot.sender} > {spot.receiver} {band} {spot.snr_db:+.0f} dB",
            "opacity": opacity,
        })
    return out


def heatmap_payload(spots: Iterable[Spot], cell_deg: float = 5.0) -> list[list[float]]:
    """Bin TX and RX endpoints into lat/lon cells; returns [lat, lon, weight 0..1]."""
    counts: Counter[tuple[float, float]] = Counter()
    for spot in spots:
        for lat, lon in ((spot.tx_lat, spot.tx_lon), (spot.rx_lat, spot.rx_lon)):
            key = ((lat // cell_deg) * cell_deg + cell_deg / 2, (lon // cell_deg) * cell_deg + cell_deg / 2)
            counts[key] += 1
    if not counts:
        return []
    peak = max(counts.values())
    return [[lat, lon, round(n / peak, 3)] for (lat, lon), n in counts.items()]


def replay_windows(end_utc: datetime | None, hours: int, bucket_minutes: int = REPLAY_BUCKET_MINUTES) -> list[tuple[datetime, datetime]]:
    end = end_utc or datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    step = timedelta(minutes=bucket_minutes)
    windows = []
    cursor = start
    while cursor < end:
        windows.append((cursor, min(cursor + step, end)))
        cursor += step
    return windows
