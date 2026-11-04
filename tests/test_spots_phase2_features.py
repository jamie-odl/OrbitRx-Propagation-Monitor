from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.models import LocationInfo, Spot
from orbitrx.spots.export import append_spot_to_adif_log, export_spots_to_adif, spot_to_adif_record
from orbitrx.spots.grayline import grayline_label, is_near_grayline, solar_altitude_degrees
from orbitrx.spots.rotor import format_rotor_command


class Phase2FeatureTests(unittest.TestCase):
    def test_grayline_helpers(self) -> None:
        moment = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)
        altitude = solar_altitude_degrees(0.0, 90.0, moment)
        self.assertAlmostEqual(altitude, 0.0, delta=3.0)
        self.assertTrue(is_near_grayline(0.0, 90.0, moment))
        self.assertEqual(grayline_label(0.0, 90.0, moment), "Grayline")

    def test_rotor_command_format(self) -> None:
        home = LocationInfo(51.5, -0.1, "London", "", "UK", "UTC", "manual")
        spot = Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100)
        command = format_rotor_command(home, spot)
        self.assertIn("ROTOR TARGET K1AAA", command)
        self.assertIn("SHORT", command)
        self.assertIn("LONG", command)

    def test_adif_export_helpers(self) -> None:
        spot = Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100, "2026-03-29T10:00:00+00:00")
        record = spot_to_adif_record(spot)
        self.assertIn("<CALL:5>K1AAA", record)
        self.assertIn("<MODE:3>FT8", record)
        self.assertIn("<QSO_DATE:8>20260329", record)
        self.assertTrue(record.endswith("<EOR>"))

        with TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "snapshot.adi"
            bridge_path = Path(temp_dir) / "bridge.adi"

            export_spots_to_adif([spot], export_path)
            append_spot_to_adif_log(spot, bridge_path)

            export_text = export_path.read_text(encoding="utf-8")
            bridge_text = bridge_path.read_text(encoding="utf-8")
            self.assertIn("OrbitRx ADIF Export", export_text)
            self.assertIn("<CALL:5>K1AAA", export_text)
            self.assertIn("OrbitRx ADIF Bridge", bridge_text)
            self.assertIn("<CALL:5>K1AAA", bridge_text)


if __name__ == "__main__":
    unittest.main()