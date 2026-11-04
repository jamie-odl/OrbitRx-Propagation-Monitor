"""Propagation scoring and summary helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

from orbitrx.spots.models import BandCondition, LocationInfo, SpaceWeatherData, Spot
from orbitrx.spots.bandplan import band_info
from orbitrx.spots.dxcc import callsign_country, normalize_callsign
from orbitrx.spots.grayline import grayline_label, is_near_grayline
from orbitrx.spots.rotor import format_rotor_command
from orbitrx.spots.pskreporter import (
    haversine_distance_miles,
    initial_bearing_degrees,
    long_path_bearing_degrees,
)


def _region_name(lat: float, lon: float) -> str:
    if -170 <= lon <= -50 and lat >= 15:
        return "North America"
    if -90 <= lon <= -30 and lat < 15:
        return "South America"
    if -20 <= lon <= 60 and lat >= 10:
        return "Europe/Africa"
    if 60 <= lon <= 150 and lat >= -10:
        return "Asia"
    if 110 <= lon <= 180 and lat < -10:
        return "Oceania"
    return "Open Ocean"


def _bearing_bucket(home_lat: float, home_lon: float, lat: float, lon: float) -> str:
    if lat >= home_lat and lon >= home_lon:
        return "NE"
    if lat >= home_lat and lon < home_lon:
        return "NW"
    if lat < home_lat and lon >= home_lon:
        return "SE"
    return "SW"


def compute_top_operators_and_countries(spots: list[Spot], top_n: int = 10) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    operator_counts: Counter[str] = Counter()
    country_counts: Counter[str] = Counter()
    for spot in spots:
        for call in (spot.sender, spot.receiver):
            normalized = normalize_callsign(call)
            if not normalized:
                continue
            operator_counts.update([normalized])
            country_counts.update([callsign_country(normalized)])
    return operator_counts.most_common(top_n), country_counts.most_common(top_n)


def summarize_operator_activity(spots: list[Spot], callsign: str) -> list[str]:
    normalized = normalize_callsign(callsign)
    if not normalized:
        return ["No callsign selected."]

    matches = [spot for spot in spots if normalize_callsign(spot.sender) == normalized or normalize_callsign(spot.receiver) == normalized]
    if not matches:
        return [f"No activity in current view for {normalized}."]

    sent = sum(1 for spot in matches if normalize_callsign(spot.sender) == normalized)
    received = len(matches) - sent
    band_counts: Counter[str] = Counter()
    counterpart_country_counts: Counter[str] = Counter()
    snr_values: list[float] = []
    path_distances: list[float] = []
    latest_seen: datetime | None = None

    for spot in matches:
        band, _color = band_info(spot.frequency_hz)
        if band != "?":
            band_counts.update([band])
        snr_values.append(spot.snr_db)
        path_distances.append(haversine_distance_miles(spot.tx_lat, spot.tx_lon, spot.rx_lat, spot.rx_lon))

        counterpart = spot.receiver if normalize_callsign(spot.sender) == normalized else spot.sender
        counterpart_country_counts.update([callsign_country(counterpart)])

        if spot.observed_at_utc:
            try:
                observed = datetime.fromisoformat(spot.observed_at_utc)
                if latest_seen is None or observed > latest_seen:
                    latest_seen = observed
            except ValueError:
                pass

    top_bands = ", ".join(f"{band}:{count}" for band, count in band_counts.most_common(3)) or "--"
    top_countries = ", ".join(f"{country}:{count}" for country, count in counterpart_country_counts.most_common(3)) or "--"
    median_snr = float(median(snr_values)) if snr_values else 0.0
    median_path = float(median(path_distances)) if path_distances else 0.0
    last_seen_text = latest_seen.isoformat() if latest_seen is not None else "--"

    return [
        f"Callsign: {normalized}",
        f"Spots in view: {len(matches)}",
        f"Sent / Received: {sent} / {received}",
        f"Median SNR: {median_snr:+.1f} dB",
        f"Median path: {median_path:.0f} miles",
        f"Top bands: {top_bands}",
        f"Top counterpart countries: {top_countries}",
        f"Last seen UTC: {last_seen_text}",
    ]


def selected_spot_detail_lines(home_location: LocationInfo, spot: Spot) -> list[str]:
    band, _color = band_info(spot.frequency_hz)
    path_distance = haversine_distance_miles(spot.tx_lat, spot.tx_lon, spot.rx_lat, spot.rx_lon)
    tx_short = initial_bearing_degrees(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon)
    tx_long = long_path_bearing_degrees(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon)
    rx_short = initial_bearing_degrees(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon)
    rx_long = long_path_bearing_degrees(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon)
    observed_text = spot.observed_at_utc or "--"
    tx_grayline = grayline_label(spot.tx_lat, spot.tx_lon)
    rx_grayline = grayline_label(spot.rx_lat, spot.rx_lon)
    return [
        f"TX: {spot.sender or '?'} ({callsign_country(spot.sender)})",
        f"RX: {spot.receiver or '?'} ({callsign_country(spot.receiver)})",
        f"Band/Freq: {band} | {spot.frequency_hz / 1_000_000.0:.6f} MHz",
        f"Mode/SNR: {spot.mode or '--'} | {spot.snr_db:+.0f} dB",
        f"Path distance: {path_distance:.0f} miles",
        f"HOME->TX: {tx_short:.0f} deg short | {tx_long:.0f} deg long",
        f"HOME->RX: {rx_short:.0f} deg short | {rx_long:.0f} deg long",
        f"Grayline: TX {tx_grayline} | RX {rx_grayline}",
        format_rotor_command(home_location, spot),
        f"Seen UTC: {observed_text}",
    ]


def compute_band_conditions(spots: list[Spot], home_location: LocationInfo, weather: SpaceWeatherData) -> list[BandCondition]:
    grouped: dict[str, list[Spot]] = defaultdict(list)
    for spot in spots:
        band, _color = band_info(spot.frequency_hz)
        if band != "?":
            grouped[band].append(spot)

    conditions: list[BandCondition] = []
    kp_penalty = (weather.kp_index or 0.0) * 4.0
    solar_bonus = max(0.0, ((weather.solar_flux or 100.0) - 90.0) / 3.0)
    for band, band_spots in grouped.items():
        snr_values = [spot.snr_db for spot in band_spots]
        distances = [
            max(
                haversine_distance_miles(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon),
                haversine_distance_miles(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon),
            )
            for spot in band_spots
        ]
        spot_count = len(band_spots)
        median_snr = float(median(snr_values)) if snr_values else -30.0
        max_distance = max(distances) if distances else 0.0
        raw_score = (spot_count * 7.5) + (median_snr + 30.0) + min(max_distance / 140.0, 25.0) + solar_bonus - kp_penalty
        score = max(0, min(99, int(round(raw_score))))
        if score >= 70:
            status = "Open"
        elif score >= 45:
            status = "Usable"
        else:
            status = "Thin"
        conditions.append(BandCondition(band, score, status, spot_count, median_snr, max_distance))

    return sorted(conditions, key=lambda item: item.score, reverse=True)


def summarize_station_activity(spots: list[Spot], home_location: LocationInfo) -> list[str]:
    if not spots:
        return ["No cached activity yet", "Top heading: --", "Top region: --", "Median SNR: --"]

    distances = []
    heading_counts: Counter[str] = Counter()
    region_counts: Counter[str] = Counter()
    for spot in spots:
        remote_lat, remote_lon = (spot.tx_lat, spot.tx_lon)
        if haversine_distance_miles(home_location.lat, home_location.lon, spot.rx_lat, spot.rx_lon) > haversine_distance_miles(home_location.lat, home_location.lon, spot.tx_lat, spot.tx_lon):
            remote_lat, remote_lon = (spot.rx_lat, spot.rx_lon)
        distances.append(haversine_distance_miles(home_location.lat, home_location.lon, remote_lat, remote_lon))
        heading_counts.update([_bearing_bucket(home_location.lat, home_location.lon, remote_lat, remote_lon)])
        region_counts.update([_region_name(remote_lat, remote_lon)])

    best_heading = heading_counts.most_common(1)[0][0]
    best_region = region_counts.most_common(1)[0][0]
    median_distance = float(median(distances)) if distances else 0.0
    median_snr = float(median([spot.snr_db for spot in spots]))
    return [
        f"Median path: {median_distance:.0f} miles",
        f"Top heading: {best_heading}",
        f"Top region: {best_region}",
        f"Median SNR: {median_snr:+.0f} dB",
    ]


def summarize_grayline_activity(spots: list[Spot]) -> list[str]:
    if not spots:
        return ["Grayline paths: 0", "Best grayline band: --", "Grayline focus: --"]

    grayline_spots = [spot for spot in spots if is_near_grayline(spot.tx_lat, spot.tx_lon) or is_near_grayline(spot.rx_lat, spot.rx_lon)]
    if not grayline_spots:
        return ["Grayline paths: 0", "Best grayline band: --", "Grayline focus: none"]

    band_counts: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    for spot in grayline_spots:
        band_counts.update([band_info(spot.frequency_hz)[0]])
        labels.update([grayline_label(spot.tx_lat, spot.tx_lon), grayline_label(spot.rx_lat, spot.rx_lon)])

    return [
        f"Grayline paths: {len(grayline_spots)}",
        f"Best grayline band: {band_counts.most_common(1)[0][0]}",
        f"Grayline focus: {labels.most_common(1)[0][0]}",
    ]


def summarize_band_forecast(spots: list[Spot], band_conditions: list[BandCondition], weather: SpaceWeatherData) -> list[str]:
    if not spots or not band_conditions:
        return ["Best next band: --", "Opening likelihood: --", "Reason: Need more live spots"]

    solar_flux = weather.solar_flux if weather.solar_flux is not None else 100.0
    kp_index = weather.kp_index if weather.kp_index is not None else 3.0

    best_band = "--"
    best_score = float("-inf")
    for condition in band_conditions:
        projected = (
            condition.score
            + (condition.spot_count * 0.8)
            + ((solar_flux - 100.0) / 4.5)
            - (kp_index * 3.0)
            + ((condition.median_snr + 30.0) / 5.0)
        )
        if projected > best_score:
            best_score = projected
            best_band = condition.band

    if best_score >= 70:
        likelihood = "High"
    elif best_score >= 50:
        likelihood = "Moderate"
    else:
        likelihood = "Low"

    reason = f"Kp {kp_index:.1f}, SFI {solar_flux:.0f}, top score {best_score:.0f}"
    return [
        f"Best next band: {best_band}",
        f"Opening likelihood: {likelihood}",
        f"Reason: {reason}",
    ]


def build_report_text(
    spots: list[Spot],
    home_location: LocationInfo,
    weather: SpaceWeatherData,
    band_conditions: list[BandCondition],
    recent_alerts: list[str],
) -> str:
    lines = [
        "OrbitRx Report",
        f"Home: {home_location.city}, {home_location.country} ({home_location.lat:.2f}, {home_location.lon:.2f})",
        f"Visible spots: {len(spots)}",
        f"Space weather: Kp {weather.kp_index if weather.kp_index is not None else '--'}, SFI {weather.solar_flux if weather.solar_flux is not None else '--'}",
        "",
        "Band conditions:",
    ]
    for condition in band_conditions[:5]:
        lines.append(
            f"- {condition.band}: {condition.status} | score {condition.score} | {condition.spot_count} spots | median {condition.median_snr:+.0f} dB | max {condition.max_distance_miles:.0f} miles"
        )
    lines.append("")
    lines.append("Station activity:")
    for line in summarize_station_activity(spots, home_location):
        lines.append(f"- {line}")
    if recent_alerts:
        lines.append("")
        lines.append("Recent alerts:")
        for alert in recent_alerts[:5]:
            lines.append(f"- {alert}")
    return "\n".join(lines)