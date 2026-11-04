from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from orbitrx.spots.models import Spot, WatchlistSettings
from orbitrx.spots.watchlist import is_watchlist_hit, spot_watchlist_tags, summarize_watchlist_hits


class WatchlistTests(unittest.TestCase):
    def test_spot_watchlist_tags(self) -> None:
        settings = WatchlistSettings(
            callsigns=["K1AAA"],
            countries=["United States"],
            prefixes=["JA"],
            regions=["Europe/Africa"],
            alerts_enabled=True,
        )
        spot = Spot(51.5, -0.1, 35.7, 139.7, 14_074_000.0, "FT8", "K1AAA", "JA1ZZZ", -10.0, 100)
        tags = spot_watchlist_tags(spot, settings)
        self.assertTrue(any(tag.startswith("CALL:K1AAA") for tag in tags))
        self.assertTrue(any(tag.startswith("DXCC:United States") for tag in tags))
        self.assertTrue(any(tag.startswith("PFX:JA") for tag in tags))
        self.assertTrue(any(tag.startswith("REG:Europe/Africa") for tag in tags))
        self.assertTrue(is_watchlist_hit(spot, settings))

    def test_summarize_watchlist_hits(self) -> None:
        settings = WatchlistSettings(callsigns=["K1AAA"], countries=[], prefixes=[], regions=[])
        spots = [
            Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "K1AAA", "G4ABC", -8.0, 100),
            Spot(48.8, 2.3, 52.5, 13.4, 21_074_000.0, "FT8", "DL1XYZ", "G4ABC", -12.0, 100),
        ]
        lines = summarize_watchlist_hits(spots, settings)
        self.assertIn("Watchlist items: 1", lines[0])
        self.assertIn("Hits in view: 1", lines[1])


if __name__ == "__main__":
    unittest.main()
