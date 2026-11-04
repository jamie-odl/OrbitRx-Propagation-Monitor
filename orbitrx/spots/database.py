"""SQLite-backed cache for spots and alerts."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3

from orbitrx.spots.settings import ALERT_COOLDOWN_MINUTES, DATABASE_PATH, REPLAY_RETENTION_HOURS
from orbitrx.spots.models import AlertEvent, Spot


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at_utc TEXT NOT NULL,
                mode TEXT NOT NULL,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                frequency_hz REAL NOT NULL,
                snr_db REAL NOT NULL,
                tx_lat REAL NOT NULL,
                tx_lon REAL NOT NULL,
                rx_lat REAL NOT NULL,
                rx_lon REAL NOT NULL,
                flow_start_seconds INTEGER NOT NULL,
                source TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_spots_observed_at ON spots(observed_at_utc);
            CREATE INDEX IF NOT EXISTS idx_spots_mode_observed_at ON spots(mode, observed_at_utc);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at_utc TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL,
                event_key TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at_utc);
            CREATE INDEX IF NOT EXISTS idx_alerts_key_created_at ON alerts(event_key, created_at_utc);
            """
        )
        connection.commit()


def prune_old_spots(retention_hours: int = REPLAY_RETENTION_HOURS) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
    with closing(_connect()) as connection:
        connection.execute("DELETE FROM spots WHERE observed_at_utc < ?", (cutoff,))
        connection.commit()


def cache_spots(spots: list[Spot]) -> None:
    if not spots:
        return
    with closing(_connect()) as connection:
        connection.executemany(
            """
            INSERT INTO spots (
                observed_at_utc, mode, sender, receiver, frequency_hz, snr_db,
                tx_lat, tx_lon, rx_lat, rx_lon, flow_start_seconds, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
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
                )
                for spot in spots
            ],
        )
        connection.commit()


def load_spots_between(start_utc: datetime, end_utc: datetime, mode: str | None = None, limit: int = 1000) -> list[Spot]:
    query = (
        "SELECT observed_at_utc, mode, sender, receiver, frequency_hz, snr_db, "
        "tx_lat, tx_lon, rx_lat, rx_lon, flow_start_seconds, source "
        "FROM spots WHERE observed_at_utc BETWEEN ? AND ?"
    )
    params: list[object] = [start_utc.isoformat(), end_utc.isoformat()]
    if mode:
        query += " AND mode = ?"
        params.append(mode)
    query += " ORDER BY observed_at_utc DESC LIMIT ?"
    params.append(limit)

    with closing(_connect()) as connection:
        rows = connection.execute(query, params).fetchall()

    return [
        Spot(
            rx_lat=float(row["rx_lat"]),
            rx_lon=float(row["rx_lon"]),
            tx_lat=float(row["tx_lat"]),
            tx_lon=float(row["tx_lon"]),
            frequency_hz=float(row["frequency_hz"]),
            mode=str(row["mode"]),
            sender=str(row["sender"]),
            receiver=str(row["receiver"]),
            snr_db=float(row["snr_db"]),
            flow_start_seconds=int(row["flow_start_seconds"]),
            observed_at_utc=str(row["observed_at_utc"]),
            source=str(row["source"]),
        )
        for row in rows
    ]


def get_cached_spot_count() -> int:
    with closing(_connect()) as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM spots").fetchone()
    return int(row["total"] if row else 0)


def get_last_cached_at() -> str:
    with closing(_connect()) as connection:
        row = connection.execute("SELECT MAX(observed_at_utc) AS last_cached_at FROM spots").fetchone()
    return str(row["last_cached_at"] or "") if row else ""


def was_alert_recent(event_key: str, cooldown_minutes: int = ALERT_COOLDOWN_MINUTES) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).isoformat()
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT 1 FROM alerts WHERE event_key = ? AND created_at_utc >= ? LIMIT 1",
            (event_key, cutoff),
        ).fetchone()
    return row is not None


def save_alert_event(alert: AlertEvent) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            "INSERT INTO alerts (created_at_utc, title, message, severity, event_key) VALUES (?, ?, ?, ?, ?)",
            (alert.created_at_utc, alert.title, alert.message, alert.severity, alert.event_key),
        )
        connection.commit()


def get_recent_alerts(limit: int = 5) -> list[AlertEvent]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT created_at_utc, title, message, severity, event_key FROM alerts ORDER BY created_at_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        AlertEvent(
            title=str(row["title"]),
            message=str(row["message"]),
            severity=str(row["severity"]),
            event_key=str(row["event_key"]),
            created_at_utc=str(row["created_at_utc"]),
        )
        for row in rows
    ]