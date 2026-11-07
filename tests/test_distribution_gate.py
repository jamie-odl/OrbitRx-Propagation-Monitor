"""Packaged Natural Earth map, onedir layout, and the closed release gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from orbitrx.paths import EXCLUDED_BASEMAP_NAMES, PACKAGED_BASEMAP_NAME, resolve_map_path
from tools.check_distribution_manifest import main as gate_main
from tools.render_natural_earth_candidate import (
    DATASET_SHA256,
    FORBIDDEN,
    HEIGHT,
    WIDTH,
    load_dataset,
    render_land,
)

ROOT = Path(__file__).resolve().parents[1]
MAP_SHA256 = "552ba27ce43dcb838ed13fe59df8b5305d92d40702f33ceadf038392135db183"


def test_dev_and_gate_use_the_natural_earth_map_only():
    assert PACKAGED_BASEMAP_NAME == "ne_110m_dark.png"
    assert "world_map.jpg" in EXCLUDED_BASEMAP_NAMES
    assert gate_main([]) == 0
    assert gate_main(["--release"]) == 1
    manifest = json.loads((ROOT / "packaging" / "distribution_manifest.json").read_text(encoding="utf-8"))
    assert manifest["packaged_basemap_sha256"] == MAP_SHA256
    assert "qt-source-offer-not-published-by-copyright-holder" in manifest["release_blockers"]
    assert "windows-onedir-build-not-executed" in manifest["release_blockers"]


def test_frozen_bundle_ignores_legacy_art_sitting_beside_the_exe(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "world_map.jpg").write_bytes(b"\xff" * 20_000)
    (bundle / "static_basemap_v2.png").write_bytes(b"\x00" * 20_000)
    (bundle / PACKAGED_BASEMAP_NAME).write_bytes(Path(ROOT / "basemap" / PACKAGED_BASEMAP_NAME).read_bytes())
    monkeypatch.setattr("orbitrx.paths.bundled_root", lambda: bundle)
    monkeypatch.setattr("orbitrx.paths.project_root", lambda: tmp_path / "missing")
    chosen = resolve_map_path()
    assert chosen.name == PACKAGED_BASEMAP_NAME
    assert chosen.parent == bundle


def test_source_checkout_does_not_fall_back_to_legacy_files(tmp_path, monkeypatch):
    (tmp_path / "world_map.jpg").write_bytes(b"\xff" * 20_000)
    (tmp_path / "static_basemap_v2.png").write_bytes(b"\x00" * 20_000)
    monkeypatch.setattr("orbitrx.paths.bundled_root", lambda: None)
    monkeypatch.setattr("orbitrx.paths.project_root", lambda: tmp_path)
    chosen = resolve_map_path()
    assert chosen.name == PACKAGED_BASEMAP_NAME
    assert not chosen.is_file()


def test_docs_and_ci_match_the_present_map_and_stay_unpublished():
    map_doc = (ROOT / "docs" / "MAP_IMAGE.md").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    deps = (ROOT / "docs" / "DEPENDENCY_LICENCES.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    draft = (ROOT / "docs" / "QT_SOURCE_OFFER_DRAFT.md").read_text(encoding="utf-8")
    spec = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "ensure_map_image" in map_doc
    assert "is not called by the app" not in map_doc
    assert "That was not done" not in map_doc
    assert "Historical `orbitrx/paths.py`" in map_doc
    assert "does not choose one" not in deps
    assert "does not choose LicenseRef-Qt-Commercial, LGPL, or GPL" not in notice
    assert "private prospective packaging route is LGPL-3.0-only" in notice
    assert "not a commercial grant" in notice
    assert "win10toast imports it" not in notice
    assert "omnirig.py" in notice and "win32com.client" in notice
    assert "alerts.py" in notice
    assert "140.0.7339.264" in draft and "151.0.7922.108" in draft
    assert draft.startswith("# DRAFT")
    assert not (ROOT / "third_party" / "qt" / "LICENSES" / "LicenseRef-Qt-Commercial.txt").exists()
    assert "('basemap/ne_110m_dark.png', '.')" in spec
    assert "next to the executable" in readme
    assert "OrbitRx-windows-unsigned" not in ci
    assert "dist/OrbitRxMonitor/" not in ci
    assert "release-exe-captures" in ci
    assert "upload-artifact" not in release
    assert "check_distribution_manifest.py --release" in release


def test_scan_pyz_resolves_an_onedir_folder(tmp_path):
    from tools.scan_pyz import resolve_scan_target

    folder = tmp_path / "OrbitRxMonitor"
    folder.mkdir()
    exe = folder / "OrbitRxMonitor.exe"
    exe.write_bytes(b"MZ")
    assert resolve_scan_target(folder) == exe
    assert resolve_scan_target(exe) == exe
    text = (ROOT / "tools" / "scan_pyz.py").read_text(encoding="utf-8")
    assert "exclude_binaries=True" in text
    assert "One-file archives are not what OrbitRxMonitor.spec builds" in text


def test_renderer_matches_the_committed_png_and_refuses_legacy_names():
    image = render_land(load_dataset(), WIDTH, HEIGHT)
    committed = Image.open(ROOT / "basemap" / "ne_110m_dark.png")
    assert image.size == committed.size == (2400, 1200)
    assert image.tobytes() == committed.tobytes()
    digest = hashlib.sha256((ROOT / "basemap" / "ne_110m_dark.png").read_bytes()).hexdigest()
    assert digest == MAP_SHA256
    raw = (ROOT / "third_party" / "natural_earth" / "ne_110m_land.geojson").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DATASET_SHA256
    assert "world_map.jpg" in FORBIDDEN
    provenance = json.loads((ROOT / "basemap" / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["pillow"] == "13.0.0"
    assert provenance["output_sha256"] == MAP_SHA256
    assert (ROOT / "docs" / "basemap_ne_110m_preview.png").is_file()
