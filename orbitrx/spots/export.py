"""Export helpers for CSV snapshots, ADIF, and text reports."""

from __future__ import annotations

import csv
from pathlib import Path

from orbitrx.spots.models import Spot


def _adif_field(name: str, value: str) -> str:
    text = str(value or "")
    return f"<{name}:{len(text)}>{text}"


def spot_to_adif_record(spot: Spot) -> str:
    record_parts = [
        _adif_field("CALL", spot.sender or spot.receiver or ""),
        _adif_field("STATION_CALLSIGN", spot.receiver or ""),
        _adif_field("MODE", spot.mode or ""),
        _adif_field("FREQ", f"{spot.frequency_hz / 1_000_000.0:.6f}"),
        _adif_field("RST_RCVD", f"{int(spot.snr_db):+d}"),
        _adif_field("RST_SENT", f"{int(spot.snr_db):+d}"),
    ]
    if spot.observed_at_utc:
        utc_text = spot.observed_at_utc.replace("-", "").replace(":", "")
        if "T" in utc_text:
            date_part, time_part = utc_text.split("T", 1)
            record_parts.append(_adif_field("QSO_DATE", date_part[:8]))
            record_parts.append(_adif_field("TIME_ON", time_part[:6]))
    record_parts.append("<EOR>")
    return "".join(record_parts)


def export_spots_to_csv(spots: list[Spot], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "observed_at_utc",
            "mode",
            "sender",
            "receiver",
            "frequency_hz",
            "snr_db",
            "tx_lat",
            "tx_lon",
            "rx_lat",
            "rx_lon",
            "flow_start_seconds",
            "source",
        ])
        for spot in spots:
            writer.writerow([
                spot.observed_at_utc,
                spot.mode,
                spot.sender,
                spot.receiver,
                spot.frequency_hz,
                spot.snr_db,
                spot.tx_lat,
                spot.tx_lon,
                spot.rx_lat,
                spot.rx_lon,
                spot.flow_start_seconds,
                spot.source,
            ])


def export_spots_to_adif(spots: list[Spot], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    header = "OrbitRx ADIF Export\n<EOH>\n"
    records = "\n".join(spot_to_adif_record(spot) for spot in spots)
    destination.write_text(header + records + ("\n" if records else ""), encoding="utf-8")


def append_spot_to_adif_log(spot: Spot, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_text("OrbitRx ADIF Bridge\n<EOH>\n", encoding="utf-8")
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(spot_to_adif_record(spot) + "\n")


def export_report(report_text: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report_text, encoding="utf-8")