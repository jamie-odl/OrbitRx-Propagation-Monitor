"""Lock the published-channel record and the facts in this tree it cites.

The digests are observations from 7 November 2026. They are not produced by
running a rebuild in this test.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from orbitrx import __version__
from orbitrx.config import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = (ROOT / "docs" / "RELEASE_CHANNELS.md").read_text(encoding="utf-8")
NOTICES = (ROOT / "docs" / "NOTICES.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
START = (ROOT / "START_HERE.txt").read_text(encoding="utf-8")
ISS = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
RELEASE_YML = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
LEAFLET = (ROOT / "orbitrx" / "ui" / "leaflet_map.py").read_text(encoding="utf-8")

ZIP_SHA256 = "bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b"
SETUP_SHA256 = "4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8"
GITHUB_EXE_SHA256 = "5bd2485d0821bb2c61fda8de15d6dda5ac25eb19e6ff6de65cd33e6961afc57b"
MAP_SHA256 = "13e99d0a8fe7bc6e0eaac39aaf1358d2613370cc5d89ff1d6e6c989310324695"
MATCHING_COMMIT = "304db03d99604af20da0b49ee2f3894ab17e2cc9"
TAG_COMMIT = "6a3e1c60794b22e460222fb4673c556b000e9cad"
CARTO_TILE = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"


def test_this_tree_stays_on_5_0_0_source_metadata():
    assert __version__ == "5.0.0"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "5.0.0"' in pyproject
    assert "AppVersion=5.0.0" in ISS
    assert "OutputBaseFilename=OrbitRxMonitor-Setup" in ISS
    assert "OrbitRx-Setup-5.1.0" not in ISS
    assert not (ROOT / "LICENSE").exists()


def test_channels_record_both_digests_and_the_real_source_commits():
    assert ZIP_SHA256 in CHANNELS
    assert SETUP_SHA256 in CHANNELS
    assert GITHUB_EXE_SHA256 in CHANNELS
    assert MATCHING_COMMIT in CHANNELS
    assert TAG_COMMIT in CHANNELS
    assert "not `main`" in CHANNELS or "not on `main`" in CHANNELS
    assert "HTTP 410" in CHANNELS
    assert "OrbitRx-Setup-5.1.0.zip" in CHANNELS
    assert "does not run Inno Setup" in CHANNELS


def test_this_tree_map_and_location_match_the_channel_note():
    assert DEFAULT_CONFIG["map_backend"] == "static"
    assert "home_lat" not in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["qrz_api_key"] == ""
    assert CARTO_TILE in LEAFLET
    assert CARTO_TILE in CHANNELS
    assert "51.5081" in CHANNELS
    assert "-0.1281" in CHANNELS
    assert "ipinfo.io" in CHANNELS


def test_release_workflow_does_not_sign_or_build_the_website_zip():
    assert "signtool" not in RELEASE_YML.lower()
    assert "authenticode" not in RELEASE_YML.lower()
    assert "OrbitRx-Setup-5.1.0" not in RELEASE_YML
    assert "OrbitRxMonitor.spec" in RELEASE_YML


def test_notices_do_not_grant_a_licence_for_this_branch():
    assert "does not grant a licence" in NOTICES
    assert "Permission is hereby granted" not in NOTICES
    assert "Permission is hereby granted" not in README
    assert "Copyright (C) 2026 thevenom" in NOTICES
    assert "not copied here" in NOTICES
    assert MAP_SHA256 in NOTICES
    digest = hashlib.sha256((ROOT / "world_map.jpg").read_bytes()).hexdigest()
    assert digest == MAP_SHA256
    assert "Creative Commons Zero" in NOTICES
    assert "classifier" in NOTICES


def test_readme_and_start_here_point_at_the_record_without_personal_paths():
    assert "docs/RELEASE_CHANNELS.md" in README
    assert "docs/NOTICES.md" in README
    assert "docs/RELEASE_CHANNELS.md" in START
    for blob in (README, START, CHANNELS, NOTICES):
        lowered = blob.lower()
        assert "onedrive" not in lowered
        assert "\\users\\" not in lowered
        assert "jamiesibley" not in lowered
        assert "odl.local" not in lowered
    assert "sible" not in START.lower()
    assert "CAT_PORT" not in README
    assert "top of `app.py`" not in README
