"""Background PSKReporter poller feeding the Live Spots layer, replay cache and alerts."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from orbitrx.spots import database
from orbitrx.spots.alerts import evaluate_alerts
from orbitrx.spots.models import LocationInfo, Spot, UserSettings, WatchlistSettings
from orbitrx.spots.pskreporter import fetch_pskreporter_spots
from orbitrx.spots.settings import MAX_FETCH_SPOTS, clamp_poll_seconds

log = logging.getLogger("orbitrx.spots")


class SpotsService:
    def __init__(
        self,
        cfg: Any,
        on_spots: Callable[[list[Spot]], None] | None = None,
        on_alert: Callable[[str, str], None] | None = None,
        location: Callable[[], tuple[float | None, float | None]] | None = None,
        fetcher: Callable[..., list[Spot]] = fetch_pskreporter_spots,
    ) -> None:
        self.cfg = cfg
        self._on_spots = on_spots or (lambda _s: None)
        self._on_alert = on_alert or (lambda _t, _m: None)
        self._location = location or (lambda: (None, None))
        self._fetcher = fetcher
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.latest: list[Spot] = []
        self.last_fetch_monotonic: float | None = None
        self.last_error: str = ""

    @property
    def poll_seconds(self) -> int:
        return clamp_poll_seconds(self.cfg.get("pskreporter_poll_seconds", 300))

    def start(self) -> None:
        if not self.cfg.get("spots_enabled", True) or self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="pskreporter")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # F9: SQLite DDL (CREATE TABLE/INDEX) runs here, on this worker thread,
        # not in start() — start() is called from the UI thread during window
        # init and must never block on disk I/O.
        try:
            database.initialize_database()
        except Exception as exc:  # pragma: no cover - disk issues
            log.warning("Spots DB init failed: %s", exc)
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_seconds)

    def poll_once(self, force: bool = False) -> list[Spot]:
        """Fetch once, honouring the 5 minute floor unless this is the first fetch."""
        now = time.monotonic()
        if (not force and self.last_fetch_monotonic is not None
                and now - self.last_fetch_monotonic < self.poll_seconds):
            return self.snapshot()
        self.last_fetch_monotonic = now
        try:
            spots = self._fetcher(
                sender_callsign=(self.cfg.get("spots_callsign") or None),
                mode=self.cfg.get("spots_mode", "FT8"),
                max_spots=MAX_FETCH_SPOTS,
            )
            self.last_error = ""
        except Exception as exc:
            self.last_error = str(exc)
            log.warning("PSKReporter fetch failed: %s", exc)
            return self.snapshot()
        with self._lock:
            self.latest = list(spots)
        try:
            database.cache_spots(spots)
            database.prune_old_spots()
        except Exception as exc:
            log.warning("Spot cache failed: %s", exc)
        self._run_alerts(spots)
        self._on_spots(self.snapshot())
        return self.snapshot()

    def snapshot(self) -> list[Spot]:
        with self._lock:
            return list(self.latest)

    def replay(self, hours_back: float, window_minutes: int = 30) -> list[Spot]:
        end = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        start = end - timedelta(minutes=window_minutes)
        try:
            return database.load_spots_between(start, end, mode=self.cfg.get("spots_mode", "FT8") or None)
        except Exception as exc:
            log.warning("Replay load failed: %s", exc)
            return []

    def _run_alerts(self, spots: list[Spot]) -> None:
        if not self.cfg.get("spot_alerts_enabled", True):
            return
        lat, lon = self._location()
        if lat is None or lon is None:
            return
        settings = UserSettings()
        wl = self.cfg.get("watchlist", {}) or {}
        settings.watchlist = WatchlistSettings(
            callsigns=list(wl.get("callsigns", [])), countries=list(wl.get("countries", [])),
            prefixes=list(wl.get("prefixes", [])), regions=list(wl.get("regions", [])),
        )
        home = LocationInfo(lat, lon, "", "", "", "UTC", "orbitrx")
        try:
            for event in evaluate_alerts(spots, home, settings):
                database.save_alert_event(event)
                self._on_alert(event.title, event.message)
        except Exception as exc:
            log.warning("Spot alerts failed: %s", exc)
