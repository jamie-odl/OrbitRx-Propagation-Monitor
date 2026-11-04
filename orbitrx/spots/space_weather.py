"""Adapter: OrbitRx's NOAA weather state feeds the spots analytics (single source)."""

from __future__ import annotations

from typing import Any

from orbitrx.spots.models import SpaceWeatherData


def from_orbitrx_state(state: Any) -> SpaceWeatherData:
    data = SpaceWeatherData()
    kp = getattr(state, "kp_index", None)
    flux = getattr(state, "flux", None)
    data.kp_index = float(kp) if kp is not None else None
    try:
        data.solar_flux = float(flux) if flux is not None else None
    except (TypeError, ValueError):
        data.solar_flux = None
    if data.kp_index is not None or data.solar_flux is not None:
        data.status = "ok"
        data.message = "From OrbitRx NOAA feed"
    return data
