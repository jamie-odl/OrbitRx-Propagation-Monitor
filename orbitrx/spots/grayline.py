"""Grayline and solar terminator helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import math


def _utc_datetime(moment_utc: datetime | None = None) -> datetime:
    moment = moment_utc or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def solar_declination_degrees(moment_utc: datetime | None = None) -> float:
    moment = _utc_datetime(moment_utc)
    day_of_year = moment.timetuple().tm_yday
    hour = moment.hour + (moment.minute / 60.0) + (moment.second / 3600.0)
    gamma = (2.0 * math.pi / 365.0) * ((day_of_year - 1) + ((hour - 12.0) / 24.0))
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    return math.degrees(decl)


def subsolar_longitude_degrees(moment_utc: datetime | None = None) -> float:
    moment = _utc_datetime(moment_utc)
    utc_hours = moment.hour + (moment.minute / 60.0) + (moment.second / 3600.0)
    return ((12.0 - utc_hours) * 15.0 + 180.0) % 360.0 - 180.0


def solar_altitude_degrees(lat: float, lon: float, moment_utc: datetime | None = None) -> float:
    decl_deg = solar_declination_degrees(moment_utc)
    subsolar_lon = subsolar_longitude_degrees(moment_utc)
    hour_angle_deg = lon - subsolar_lon
    lat_rad = math.radians(lat)
    decl_rad = math.radians(decl_deg)
    hour_angle_rad = math.radians(hour_angle_deg)
    altitude = math.asin(
        (math.sin(lat_rad) * math.sin(decl_rad))
        + (math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad))
    )
    return math.degrees(altitude)


def grayline_distance_degrees(lat: float, lon: float, moment_utc: datetime | None = None) -> float:
    return abs(solar_altitude_degrees(lat, lon, moment_utc))


def is_near_grayline(lat: float, lon: float, moment_utc: datetime | None = None, threshold_degrees: float = 8.0) -> bool:
    return grayline_distance_degrees(lat, lon, moment_utc) <= threshold_degrees


def grayline_label(lat: float, lon: float, moment_utc: datetime | None = None) -> str:
    altitude = solar_altitude_degrees(lat, lon, moment_utc)
    if abs(altitude) <= 8.0:
        return "Grayline"
    if altitude > 0:
        return "Daylight"
    return "Night"