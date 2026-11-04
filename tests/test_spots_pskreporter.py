from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.pskreporter import parse_spots_from_xml


class PSKReporterParsingTests(unittest.TestCase):
    def test_parse_fixture(self) -> None:
        fixture = (PROJECT_ROOT / "tests" / "data" / "pskreporter_sample.xml").read_text(encoding="utf-8")
        spots = parse_spots_from_xml(fixture, max_spots=10)
        self.assertEqual(len(spots), 2)
        self.assertEqual(spots[0].sender, "G7XYZ")
        self.assertEqual(int(spots[0].snr_db), -12)
        self.assertAlmostEqual(spots[0].frequency_hz, 14_074_000.0)


if __name__ == "__main__":
    unittest.main()
