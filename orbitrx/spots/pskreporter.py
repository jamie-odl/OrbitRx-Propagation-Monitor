"""PSKReporter service and XML parsing."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Iterable
import xml.etree.ElementTree as ET

from urllib.error import URLError
from urllib.request import Request, urlopen

from orbitrx.spots.settings import PSKREPORTER_FLOW_START_SECONDS, USER_AGENT
from orbitrx.spots.models import Spot


def maidenhead_to_latlon(locator: str) -> tuple[float, float] | None:
    if not locator:
        return None
    grid = locator.strip().upper()
    if len(grid) < 4:
        return None
    try:
        lon = -180.0 + (ord(grid[0]) - ord("A")) * 20.0
        lat = -90.0 + (ord(grid[1]) - ord("A")) * 10.0
        lon += int(grid[2]) * 2.0
        lat += int(grid[3]) * 1.0
        lon_center = lon + 1.0
        lat_center = lat + 0.5
        if len(grid) >= 6 and grid[4].isalpha() and grid[5].isalpha():
            lon += (ord(grid[4]) - ord("A")) * (5.0 / 60.0)
            lat += (ord(grid[5]) - ord("A")) * (2.5 / 60.0)
            lon_center = lon + (2.5 / 60.0)
            lat_center = lat + (1.25 / 60.0)
        return lat_center, lon_center
    except (ValueError, IndexError):
        return None


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_miles * c


def initial_bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    y = math.sin(dlon_rad) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad)) - (
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    )
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def long_path_bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return (initial_bearing_degrees(lat1, lon1, lat2, lon2) + 180.0) % 360.0


def filter_spots_near_location(spots: Iterable[Spot], home_lat: float, home_lon: float, radius_miles: float) -> list[Spot]:
    filtered: list[Spot] = []
    for spot in spots:
        if haversine_distance_miles(home_lat, home_lon, spot.tx_lat, spot.tx_lon) <= radius_miles:
            filtered.append(spot)
            continue
        if haversine_distance_miles(home_lat, home_lon, spot.rx_lat, spot.rx_lon) <= radius_miles:
            filtered.append(spot)
    return filtered


def parse_spot_elements(elements: Iterable[ET.Element], max_spots: int) -> list[Spot]:
    spots: list[Spot] = []
    for report in elements:
        try:
            rx_lat = float(report.get("receiverSiteLat", "nan"))
            rx_lon = float(report.get("receiverSiteLon", "nan"))
            tx_lat = float(report.get("senderSiteLat", "nan"))
            tx_lon = float(report.get("senderSiteLon", "nan"))

            if math.isnan(rx_lat) or math.isnan(rx_lon):
                decoded = maidenhead_to_latlon(report.get("receiverLocator", ""))
                if decoded:
                    rx_lat, rx_lon = decoded
            if math.isnan(tx_lat) or math.isnan(tx_lon):
                decoded = maidenhead_to_latlon(report.get("senderLocator", ""))
                if decoded:
                    tx_lat, tx_lon = decoded
            if any(math.isnan(v) for v in (rx_lat, rx_lon, tx_lat, tx_lon)):
                continue

            spots.append(
                Spot(
                    rx_lat=rx_lat,
                    rx_lon=rx_lon,
                    tx_lat=tx_lat,
                    tx_lon=tx_lon,
                    frequency_hz=float(report.get("frequency", 0.0) or 0.0),
                    mode=report.get("mode", ""),
                    sender=report.get("senderCallsign", ""),
                    receiver=report.get("receiverCallsign", ""),
                    snr_db=float(report.get("sNR", 0.0) or 0.0),
                    flow_start_seconds=int(report.get("flowStartSeconds", 0) or 0),
                )
            )
            if len(spots) >= max_spots:
                break
        except (TypeError, ValueError):
            continue
    return spots


def parse_spots_from_xml(xml_text: str, max_spots: int = 300) -> list[Spot]:
    root = ET.fromstring(xml_text)
    return parse_spot_elements(root.findall('.//receptionReport'), max_spots=max_spots)


def fetch_pskreporter_spots(
    sender_callsign: str | None = None,
    flow_start_seconds: int = PSKREPORTER_FLOW_START_SECONDS,
    mode: str = "FT8",
    max_spots: int = 300,
    timeout: int = 12,
) -> list[Spot]:
    query_variants: list[list[str]] = []
    base = [f"flowStartSeconds=-{abs(flow_start_seconds)}"]
    if sender_callsign:
        query_variants.append(base + [f"senderCallsign={sender_callsign}"])
    if mode:
        query_variants.append(base + [f"mode={mode}"])
    query_variants.append(base)

    last_error: Exception | None = None
    headers = {"User-Agent": USER_AGENT}
    response = None
    for query_parts in query_variants:
        url = "https://retrieve.pskreporter.info/query?" + "&".join(query_parts)
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as resp:
                response = resp.read().decode("utf-8", errors="replace")
            break
        except (URLError, OSError, ValueError) as exc:
            last_error = exc
            response = None
            continue

    if response is None:
        if last_error is not None:
            raise last_error
        raise RuntimeError("PSKReporter request failed")

    observed_at_utc = datetime.now(timezone.utc).isoformat()
    parsed = parse_spots_from_xml(response, max_spots=max_spots)
    return [
        Spot(
            rx_lat=spot.rx_lat,
            rx_lon=spot.rx_lon,
            tx_lat=spot.tx_lat,
            tx_lon=spot.tx_lon,
            frequency_hz=spot.frequency_hz,
            mode=spot.mode,
            sender=spot.sender,
            receiver=spot.receiver,
            snr_db=spot.snr_db,
            flow_start_seconds=spot.flow_start_seconds,
            observed_at_utc=observed_at_utc,
            source="pskreporter",
        )
        for spot in parsed
    ]
