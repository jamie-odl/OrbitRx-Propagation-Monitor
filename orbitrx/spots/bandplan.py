"""Band mapping helpers shared across services and UI."""

from __future__ import annotations


def band_info(frequency_hz: float) -> tuple[str, str]:
    mhz = frequency_hz / 1_000_000.0
    if 13.8 <= mhz <= 14.5:
        return "20m", "#7CFF7C"
    if 27.0 <= mhz <= 30.0:
        return "10m", "#FF9A4D"
    if 20.5 <= mhz <= 22.5:
        return "15m", "#95FF78"
    if 6.8 <= mhz <= 7.4:
        return "40m", "#65F3FF"
    if 49.0 <= mhz <= 54.5:
        return "6m", "#ffde59"
    return "?", "#C4D1E0"