from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.models import LocationInfo, SpaceWeatherData, Spot
from orbitrx.spots.analytics import (
    callsign_country,
    compute_band_conditions,
    compute_top_operators_and_countries,
    selected_spot_detail_lines,
    summarize_band_forecast,
    summarize_grayline_activity,
    summarize_operator_activity,
    summarize_station_activity,
)


class AnalyticsTests(unittest.TestCase):
    def test_compute_band_conditions(self) -> None:
        home = LocationInfo(51.5, -0.1, "London", "", "UK", "UTC", "manual")
        weather = SpaceWeatherData(kp_index=2.0, solar_flux=140.0, status="ok", message="updated")
        spots = [
            Spot(51.5, -0.1, 52.0, 0.1, 14_074_000.0, "FT8", "G4ABC", "DL1XYZ", -8.0, 100),
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "G4ABC", "K2ABC", -12.0, 95),
        ]
        conditions = compute_band_conditions(spots, home, weather)
        self.assertTrue(conditions)
        self.assertEqual(conditions[0].band, "20m")

    def test_summarize_station_activity(self) -> None:
        home = LocationInfo(51.5, -0.1, "London", "", "UK", "UTC", "manual")
        spots = [Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "G4ABC", "K2ABC", -10.0, 100)]
        summary = summarize_station_activity(spots, home)
        self.assertEqual(len(summary), 4)
        self.assertIn("Median path", summary[0])

    def test_top_operators_and_countries(self) -> None:
        spots = [
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100),
            Spot(48.8, 2.3, 52.5, 13.4, 14_074_000.0, "FT8", "DL1XYZ", "K1AAA", -12.0, 100),
            Spot(35.7, 139.7, -33.8, 151.2, 21_074_000.0, "FT8", "JA1ZZZ", "VK2QQQ", -5.0, 100),
        ]
        operators, countries = compute_top_operators_and_countries(spots, top_n=10)
        self.assertTrue(operators)
        self.assertEqual(operators[0][0], "K1AAA")
        self.assertGreaterEqual(operators[0][1], 2)
        country_names = [name for name, _count in countries]
        self.assertIn("United States", country_names)

    def test_callsign_country_prefixes(self) -> None:
        self.assertEqual(callsign_country("K1ABC"), "United States")
        self.assertEqual(callsign_country("JA1AAA"), "Japan")
        self.assertEqual(callsign_country("VK2XYZ"), "Australia")

    def test_summarize_operator_activity(self) -> None:
        spots = [
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100, "2026-03-29T10:00:00+00:00"),
            Spot(48.8, 2.3, 52.5, 13.4, 14_074_000.0, "FT8", "DL1XYZ", "K1AAA", -12.0, 100, "2026-03-29T10:05:00+00:00"),
        ]
        lines = summarize_operator_activity(spots, "K1AAA")
        self.assertTrue(any("Spots in view: 2" in line for line in lines))
        self.assertTrue(any("Top bands:" in line for line in lines))

    def test_selected_spot_detail_lines(self) -> None:
        home = LocationInfo(51.5, -0.1, "London", "", "UK", "UTC", "manual")
        spot = Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100, "2026-03-29T10:00:00+00:00")
        lines = selected_spot_detail_lines(home, spot)
        self.assertTrue(any("TX: K1AAA (United States)" in line for line in lines))
        self.assertTrue(any("Path distance:" in line for line in lines))
        self.assertTrue(any("HOME->TX:" in line for line in lines))
        self.assertTrue(any("Grayline:" in line for line in lines))
        self.assertTrue(any("ROTOR TARGET" in line for line in lines))

    def test_summarize_grayline_activity(self) -> None:
        spots = [
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100),
            Spot(48.8, 2.3, 52.5, 13.4, 21_074_000.0, "FT8", "DL1XYZ", "JA1AAA", -12.0, 100),
        ]
        with patch("orbitrx.spots.analytics.is_near_grayline", side_effect=[True, False, False, False]), patch(
            "orbitrx.spots.analytics.grayline_label",
            side_effect=["Grayline", "Night"],
        ):
            lines = summarize_grayline_activity(spots)
        self.assertEqual(lines[0], "Grayline paths: 1")
        self.assertIn("Best grayline band: 20m", lines[1])
        self.assertIn("Grayline focus: Grayline", lines[2])

    def test_summarize_band_forecast(self) -> None:
        home = LocationInfo(51.5, -0.1, "London", "", "UK", "UTC", "manual")
        weather = SpaceWeatherData(kp_index=1.0, solar_flux=150.0, status="ok", message="updated")
        spots = [
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100),
            Spot(51.5, -0.1, 35.7, 139.7, 21_074_000.0, "FT8", "JA1AAA", "G4ABC", -10.0, 100),
        ]
        conditions = compute_band_conditions(spots, home, weather)
        lines = summarize_band_forecast(spots, conditions, weather)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("Best next band:"))
        self.assertTrue(lines[1].startswith("Opening likelihood:"))