"""Packaged map, vendored texts, and the release gate.

The gate must fail while the Qt election and the map-licence decisions
are open. It does not download a release or hash the public zip URL.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from orbitrx.paths import PACKAGED_BASEMAP_NAME, SOURCE_BASEMAP_NAMES, resolve_map_path
from tools.check_distribution_manifest import main as gate_main
from tools.render_natural_earth_candidate import FORBIDDEN, render_land

ROOT = Path(__file__).resolve().parents[1]


def test_source_search_and_packaged_name_stay_distinct():
    assert SOURCE_BASEMAP_NAMES[0] == "static_basemap_v2.png"
    assert PACKAGED_BASEMAP_NAME == "world_map.jpg"
    assert gate_main([]) == 0
    assert gate_main(["--release"]) == 1


def test_frozen_bundle_with_only_jpeg_does_not_select_v2(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "world_map.jpg").write_bytes(b"\xff" * 20_000)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr("orbitrx.paths.bundled_root", lambda: bundle)
    monkeypatch.setattr("orbitrx.paths.project_root", lambda: empty)
    chosen = resolve_map_path()
    assert chosen.name == "world_map.jpg"
    assert chosen.parent == bundle


def test_source_checkout_still_prefers_v2_when_present(tmp_path, monkeypatch):
    for name, size in (
        ("static_basemap_v2.png", 20_000),
        ("static_basemap_v2.webp", 20_000),
        ("world_map.jpg", 20_000),
    ):
        (tmp_path / name).write_bytes(b"\x00" * size)
    monkeypatch.setattr("orbitrx.paths.bundled_root", lambda: None)
    monkeypatch.setattr("orbitrx.paths.project_root", lambda: tmp_path)
    assert resolve_map_path().name == "static_basemap_v2.png"


def test_candidate_renderer_is_deterministic_and_cannot_replace_artwork(tmp_path):
    geojson = {
        "features": [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-10, -10],
                        [10, -10],
                        [10, 10],
                        [-10, 10],
                        [-10, -10],
                    ]],
                }
            }
        ]
    }
    first = render_land(geojson, 36, 18)
    second = render_land(geojson, 36, 18)
    assert first.tobytes() == second.tobytes()
    assert first.getpixel((18, 9)) == (28, 42, 58)
    assert first.getpixel((0, 0)) == (10, 22, 40)
    assert "world_map.jpg" in FORBIDDEN
    script = (ROOT / "tools" / "render_natural_earth_candidate.py").read_text(encoding="utf-8")
    assert "not the packaged basemap" in script
    manifest = json.loads((ROOT / "packaging" / "distribution_manifest.json").read_text(encoding="utf-8"))
    assert "qt-licence-election" in manifest["release_blockers"]
    assert "qtwebengine-chromium-third-party-credits-file" in manifest["release_blockers"]
    assert "pystray" in manifest["not_in_frozen_exe"]
    image = Image.open(ROOT / "static_basemap_v2.png")
    assert image.size == (2400, 1200)
