"""Packaged Natural Earth map, onedir layout, and the closed release gate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
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
    assert "windows-onedir-build-not-executed" not in manifest["release_blockers"]
    evidence = manifest["windows_onedir_evidence"]
    assert evidence["run"] == "42362357356"
    assert evidence["static_process_exit"] == 0
    assert evidence["interactive_process_exit"] == 0
    assert "windows-static-capture-exit-0xC0000005-on-42359055614" not in manifest["release_blockers"]
    assert "qtwebengine-gn-about-credits-not-generated-for-submodule-71a2fa55" in manifest["release_blockers"]


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


def test_corresponding_source_archives_match_their_manifest():
    manifest = json.loads(
        (ROOT / "third_party" / "corresponding-source" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["qtwebengine"]["chromium_version_base"] == "140.0.7339.264"
    assert manifest["qtwebengine"]["chromium_security_patches_through"] == "151.0.7922.108"
    assert "Not a published source offer" in manifest["purpose"] or "Not a published source offer" in manifest["purpose"]
    assert "not a published source offer" in manifest["purpose"].lower()
    for item in manifest["files"]:
        path = ROOT / "third_party" / "corresponding-source" / item["name"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"]


def test_capture_process_exits_zero_for_static_and_webengine_view(tmp_path):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    probe = ROOT / "tools" / "capture_shutdown_probe.py"
    for name, extra in (("static", []), ("webengine", ["--with-view"])):
        out = tmp_path / name
        proc = subprocess.run(
            [sys.executable, str(probe), str(out), *extra],
            env=env,
            timeout=90,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        stage = (out / "shutdown-stage.txt").read_text(encoding="utf-8")
        assert "qapplication-deleted" in stage
        assert stage.strip().splitlines()[-1] == "process-exit"


def test_about_snapshot_matches_the_offline_basemap_wording():
    html = (ROOT / "orbitrx" / "ui" / "about.py").read_text(encoding="utf-8")
    assert "offline basemap (NOTICE), Leaflet" in html
    assert "OrbitRx dark basemap" not in html


def test_text_files_stay_lf_so_windows_hashes_match():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in attributes
    for rel in ("LICENSE", "third_party/natural_earth/ne_110m_land.geojson"):
        assert b"\r" not in (ROOT / rel).read_bytes()


def test_private_windows_workflow_does_not_upload_distributables():
    text = (ROOT / ".github" / "workflows" / "windows-private-validation.yml").read_text(encoding="utf-8")
    assert "cursor/shipped-5-1-0-notices-2d8d" in text
    assert "runs-on: windows-latest" in text
    assert "windows-private-validation-logs" in text
    assert "OrbitRx-windows-unsigned" not in text
    assert "dist/" not in text.split("name: windows-private-validation-logs")[1].split("retention-days:")[0]
    assert "Remove-Item -Recurse -Force dist" in text
    assert 'throw "static smoke exit' in text
    assert 'throw "leaflet smoke exit' in text
    assert "continue-on-error: true" not in text
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "upload-artifact" not in release


def test_onedir_layout_checker_accepts_sibling_dlls(tmp_path):
    from tools.check_onedir_layout import check_layout

    root = tmp_path / "OrbitRxMonitor"
    (root / "_internal" / "PySide6").mkdir(parents=True)
    (root / "OrbitRxMonitor.exe").write_bytes(b"x")
    (root / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(b"x")
    (root / "_internal" / "PySide6" / "Qt6WebEngineCore.dll").write_bytes(b"x")
    (root / "_internal" / "ne_110m_dark.png").write_bytes(b"x")
    (root / "_internal" / "LICENSE").write_bytes(b"x")
    (root / "_internal" / "NOTICE").write_bytes(b"x")
    (root / "_internal" / "PRIVACY.md").write_bytes(b"x")
    (root / "_internal" / "third_party" / "qt" / "LICENSES").mkdir(parents=True)
    (root / "_internal" / "third_party" / "qt" / "LICENSES" / "LGPL-3.0-only.txt").write_text("lgpl", encoding="utf-8")
    (root / "_internal" / "third_party" / "qt" / "LICENSE.Chromium").write_text("bsd", encoding="utf-8")
    (root / "_internal" / "third_party" / "natural_earth").mkdir(parents=True)
    (root / "_internal" / "third_party" / "natural_earth" / "TERMS_OF_USE.txt").write_text("pd", encoding="utf-8")
    assert check_layout(root) == []
    (root / "world_map.jpg").write_bytes(b"nope")
    assert any("world_map" in item for item in check_layout(root))


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
