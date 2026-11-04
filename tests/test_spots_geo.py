from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.models import Spot
from orbitrx.spots.pskreporter import (
    filter_spots_near_location,
    initial_bearing_degrees,
    long_path_bearing_degrees,
    maidenhead_to_latlon,
)
from orbitrx.spots.bandplan import band_info
from orbitrx.spots.geo import coords_to_pixels


class GeoTests(unittest.TestCase):
    def test_coords_to_pixels_center(self) -> None:
        x, y = coords_to_pixels(0.0, 0.0, 360, 180)
        self.assertAlmostEqual(x, 180.0)
        self.assertAlmostEqual(y, 90.0)

    def test_maidenhead_decoder(self) -> None:
        latlon = maidenhead_to_latlon("IO92xp")
        self.assertIsNotNone(latlon)
        lat, lon = latlon or (0.0, 0.0)
        self.assertTrue(50.0 <= lat <= 53.0)
        self.assertTrue(-3.0 <= lon <= 0.5)

    def test_band_info(self) -> None:
        band, color = band_info(14_074_000)
        self.assertEqual(band, "20m")
        self.assertTrue(color.startswith("#"))

    def test_local_view_filter(self) -> None:
        spots = [
            Spot(51.5, -0.1, 51.6, -0.2, 14_074_000.0, "FT8", "G4ABC", "DL1XYZ", -8.0, 100),
            Spot(40.7, -74.0, 34.0, -118.2, 14_074_000.0, "FT8", "K2ABC", "W6XYZ", -12.0, 90),
        ]
        filtered = filter_spots_near_location(spots, 51.5, -0.1, 500.0)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].sender, "G4ABC")

    def test_bearing_helpers(self) -> None:
        short_path = initial_bearing_degrees(51.5, -0.1, 40.7, -74.0)
        long_path = long_path_bearing_degrees(51.5, -0.1, 40.7, -74.0)
        self.assertTrue(250.0 <= short_path <= 320.0)
        self.assertAlmostEqual((short_path + 180.0) % 360.0, long_path, places=3)


if __name__ == "__main__":
    unittest.main()
