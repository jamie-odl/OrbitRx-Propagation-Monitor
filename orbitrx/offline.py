"""CI and capture runs must not collect live spot or weather data."""

from __future__ import annotations

import os

# Fixed space-weather sample. No callsigns.
FIXTURE_WEATHER = {
    "kp_index": 2.0,
    "flux": 120.0,
    "a_index": 8,
    "a_index_source": "fixture",
    "solar_wind_speed": 400,
    "bz": 0.0,
    "sunspot_observed": 80,
    "sunspot_predicted": 80,
    "time_utc": "00:00",
    "kp_forecast": "2",
    "alerts": [],
    "solar_forecast": "fixture",
}


def offline_fixture() -> bool:
    """True when this process must not open NOAA, PSKReporter, or a cluster."""
    return os.environ.get("ORBITRX_OFFLINE_FIXTURE") == "1" or bool(os.environ.get("ORBITRX_CAPTURE_DIR"))
