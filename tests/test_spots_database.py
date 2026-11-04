from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.models import AlertEvent, Spot
from orbitrx.spots import database


class DatabaseTests(unittest.TestCase):
    def test_cache_and_load_spots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            with patch.object(database, "DATABASE_PATH", db_path):
                database.initialize_database()
                observed = datetime.now(timezone.utc)
                database.cache_spots(
                    [
                        Spot(51.5, -0.1, 52.0, 0.1, 14_074_000.0, "FT8", "G4ABC", "DL1XYZ", -8.0, 100, observed.isoformat(), "pskreporter")
                    ]
                )
                loaded = database.load_spots_between(observed - timedelta(minutes=5), observed + timedelta(minutes=5), mode="FT8")
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].sender, "G4ABC")

    def test_save_recent_alert(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            with patch.object(database, "DATABASE_PATH", db_path):
                database.initialize_database()
                database.save_alert_event(
                    AlertEvent(
                        title="Long-Path Opening",
                        message="20m reached 2000 miles.",
                        severity="warning",
                        event_key="opening-20m",
                        created_at_utc=datetime.now(timezone.utc).isoformat(),
                    )
                )
                alerts = database.get_recent_alerts(limit=2)
                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0].event_key, "opening-20m")