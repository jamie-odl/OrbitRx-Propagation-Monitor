"""Rotor heading helpers and command formatting."""

from __future__ import annotations

from orbitrx.spots.models import LocationInfo, Spot
from orbitrx.spots.pskreporter import haversine_distance_miles, initial_bearing_degrees, long_path_bearing_degrees


def preferred_rotor_target(home_location: LocationInfo, spot: Spot) -> tuple[str, float, float]:
    tx_distance = haversine_distance_miles(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon)
    rx_distance = haversine_distance_miles(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon)
    if tx_distance >= rx_distance:
        target_callsign = spot.sender or "TX"
        target_lat, target_lon = spot.tx_lat, spot.tx_lon
    else:
        target_callsign = spot.receiver or "RX"
        target_lat, target_lon = spot.rx_lat, spot.rx_lon
    return target_callsign, target_lat, target_lon


def rotor_headings(home_location: LocationInfo, lat: float, lon: float) -> tuple[float, float]:
    short_path = initial_bearing_degrees(home_location.lat, home_location.lon, lat, lon)
    long_path = long_path_bearing_degrees(home_location.lat, home_location.lon, lat, lon)
    return short_path, long_path


def format_rotor_command(home_location: LocationInfo, spot: Spot) -> str:
    target_callsign, target_lat, target_lon = preferred_rotor_target(home_location, spot)
    short_path, long_path = rotor_headings(home_location, target_lat, target_lon)
    return f"ROTOR TARGET {target_callsign} | SHORT {short_path:.0f} | LONG {long_path:.0f}"