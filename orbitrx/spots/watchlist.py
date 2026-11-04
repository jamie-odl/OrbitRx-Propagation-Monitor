"""Watchlist matching and summary helpers."""

from __future__ import annotations

from collections import Counter

from orbitrx.spots.models import Spot, WatchlistSettings
from orbitrx.spots.bandplan import band_info
from orbitrx.spots.dxcc import callsign_country, normalize_callsign


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


def spot_watchlist_tags(spot: Spot, watchlist: WatchlistSettings) -> list[str]:
    tags: list[str] = []
    sender = normalize_callsign(spot.sender)
    receiver = normalize_callsign(spot.receiver)

    callsigns = {item.upper() for item in watchlist.callsigns if item.strip()}
    prefixes = {item.upper() for item in watchlist.prefixes if item.strip()}
    countries = {item for item in watchlist.countries if item.strip()}
    regions = {item for item in watchlist.regions if item.strip()}

    for call in (sender, receiver):
        if call and call in callsigns:
            tags.append(f"CALL:{call}")
    for call in (sender, receiver):
        if not call:
            continue
        for prefix in prefixes:
            if call.startswith(prefix):
                tags.append(f"PFX:{prefix}")
    for country in (callsign_country(sender), callsign_country(receiver)):
        if country in countries:
            tags.append(f"DXCC:{country}")
    for region in (_region_name(spot.tx_lat, spot.tx_lon), _region_name(spot.rx_lat, spot.rx_lon)):
        if region in regions:
            tags.append(f"REG:{region}")

    unique = sorted(set(tags))
    return unique


def is_watchlist_hit(spot: Spot, watchlist: WatchlistSettings) -> bool:
    return bool(spot_watchlist_tags(spot, watchlist))


def summarize_watchlist_hits(spots: list[Spot], watchlist: WatchlistSettings) -> list[str]:
    if not spots:
        return ["Watchlist items: 0", "Hits in view: 0", "Top hit band: --", "Top matched tag: --"]

    total_items = len(watchlist.callsigns) + len(watchlist.countries) + len(watchlist.prefixes) + len(watchlist.regions)
    hit_spots = []
    tag_counts: Counter[str] = Counter()
    band_counts: Counter[str] = Counter()

    for spot in spots:
        tags = spot_watchlist_tags(spot, watchlist)
        if not tags:
            continue
        hit_spots.append(spot)
        tag_counts.update(tags)
        band_counts.update([band_info(spot.frequency_hz)[0]])

    if not hit_spots:
        return [
            f"Watchlist items: {total_items}",
            "Hits in view: 0",
            "Top hit band: --",
            "Top matched tag: --",
        ]

    return [
        f"Watchlist items: {total_items}",
        f"Hits in view: {len(hit_spots)}",
        f"Top hit band: {band_counts.most_common(1)[0][0]}",
        f"Top matched tag: {tag_counts.most_common(1)[0][0]}",
    ]
