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
    assert "final-public-candidate-gate-pending" in manifest["release_blockers"]
    assert "corresponding-source-archive-not-publicly-hosted" not in manifest["release_blockers"]
    assert "windows-onedir-build-not-executed" not in manifest["release_blockers"]
    # Option B (2026-11-09): WebEngine/Chromium are no longer shipped, so the
    # corresponding-source offer covers only the plain Qt/PySide6 libraries this
    # build still ships; chromium_credits is gone and the WebEngine archives
    # moved to the historical "superseded" list (webengine_removed explains why).
    hosted = manifest["corresponding_source"]["entries"]
    hosted_names = {item["name"] for item in hosted}
    assert hosted_names == {
        "pyside-setup-everywhere-src-6.12.0.tar.xz",
        "qt-everywhere-src-6.12.0.tar.xz",
    }
    hosted_sha256 = {item["name"]: item["sha256"] for item in hosted}
    assert hosted_sha256["pyside-setup-everywhere-src-6.12.0.tar.xz"] == (
        "099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751"
    )
    assert hosted_sha256["qt-everywhere-src-6.12.0.tar.xz"] == (
        "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165"
    )
    superseded = manifest["corresponding_source"]["superseded"]
    assert "qtwebengine-everywhere-src-6.140.0-rc.tar.xz" in superseded
    assert "THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt" in superseded
    assert "chromium_credits" not in manifest
    evidence = manifest["windows_onedir_evidence"]
    assert evidence["run"] == "42362357356"
    assert evidence["static_process_exit"] == 0
    assert evidence["interactive_process_exit"] == 0
    assert "windows-static-capture-exit-0xC0000005-on-42359055614" not in manifest["release_blockers"]
    assert "qtwebengine-gn-about-credits-not-generated-for-submodule-71a2fa55" not in manifest["release_blockers"]
    assert manifest["webengine_removed"]["branch"] == "feat/native-map-no-webengine-2026-11-09"


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
    assert "packaging route is LGPL-3.0-only" in notice
    assert "private prospective" not in notice
    assert "not a commercial grant" in notice
    assert "win10toast imports it" not in notice
    assert "omnirig.py" in notice and "win32com.client" in notice
    assert "alerts.py" in notice
    assert "140.0.7339.264" in draft and "151.0.7922.108" in draft
    assert draft.startswith("> **Superseded (13 November 2026).**")
    assert "\n# Verified corresponding source offer\n" in draft
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
    assert manifest["qtwebengine"]["this_tarball_contains_chromium_tree"] is False
    assert manifest["qtwebengine"]["chromium_tar_retained_separately"] is True
    chromium = manifest["retained_source"]["qtwebengine_chromium"]
    assert chromium["sha256"] == "d258e5a92def26ba37ebea5463c5ea2a0674fded471bf2b6f5ecaf8771fbe865"
    assert chromium["gitlinks"] == 0
    assert chromium["bytes"] == 3819509760
    assert "Not a published source offer" in manifest["purpose"] or "Not a published source offer" in manifest["purpose"]
    assert "not a published source offer" in manifest["purpose"].lower()
    for item in manifest["files"]:
        path = ROOT / "third_party" / "corresponding-source" / item["name"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"]


def test_capture_process_exits_zero_for_the_static_capture(tmp_path):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    probe = ROOT / "tools" / "capture_shutdown_probe.py"
    out = tmp_path / "static"
    proc = subprocess.run(
        [sys.executable, str(probe), str(out)],
        env=env,
        timeout=90,
        capture_output=True,
        text=True,
        check=False,
    )
    stage_path = out / "shutdown-stage.txt"
    fault_path = out / "faulthandler.txt"
    stage = stage_path.read_text(encoding="utf-8") if stage_path.is_file() else "<missing>"
    fault = fault_path.read_text(encoding="utf-8") if fault_path.is_file() else "<missing>"
    diagnostics = (
        f"returncode={proc.returncode}\nstderr={proc.stderr}\n"
        f"--- shutdown-stage.txt ---\n{stage}\n--- faulthandler.txt ---\n{fault}"
    )
    assert proc.returncode == 0, diagnostics
    lines = stage.strip().splitlines()
    # Order proves threads were joined and widgets deleted before QApplication
    # itself, and that the process ended normally afterward (see
    # orbitrx.ui.qt_app.shutdown_capture_process / run_capture_and_exit).
    thread_stage = next(
        (l for l in lines if l == "threads-joined" or l.startswith("threads-still-alive:")), None
    )
    assert thread_stage == "threads-joined", diagnostics
    required_order = ["window-closed", thread_stage, "widgets-deleted", "qapplication-deleted", "process-exit"]
    positions = [lines.index(name) for name in required_order]
    assert positions == sorted(positions), diagnostics
    assert lines[-1] == "process-exit", diagnostics


def test_about_snapshot_matches_the_offline_basemap_wording():
    html = (ROOT / "orbitrx" / "ui" / "about.py").read_text(encoding="utf-8")
    assert "offline basemap (NOTICE)." in html
    assert "OrbitRx dark basemap" not in html
    assert "Leaflet" not in html


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
    assert "windows-private-candidate" in text
    assert "retention-days: 1" in text
    assert "OrbitRx-windows-unsigned" not in text
    assert "OrbitRx-Setup-5.1.0" not in text
    recorded = json.loads((ROOT / "packaging" / "windows_private_candidate.json").read_text(encoding="utf-8"))
    assert recorded["not_a_receipt_for_the_current_tip"] is True
    assert recorded["role"] == "historical"
    assert "check_pristine_payload.py" in text
    assert "dist-smoke" in text
    assert "ORBITRX_RECEIPT" in text
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
    (root / "_internal" / "ne_110m_dark.png").write_bytes(b"x")
    (root / "_internal" / "LICENSE").write_bytes(b"x")
    (root / "_internal" / "NOTICE").write_bytes(b"x")
    (root / "_internal" / "PRIVACY.md").write_bytes(b"x")
    (root / "_internal" / "third_party" / "qt" / "LICENSES").mkdir(parents=True)
    (root / "_internal" / "third_party" / "qt" / "LICENSES" / "LGPL-3.0-only.txt").write_text("lgpl", encoding="utf-8")
    (root / "_internal" / "third_party" / "natural_earth").mkdir(parents=True)
    (root / "_internal" / "third_party" / "natural_earth" / "TERMS_OF_USE.txt").write_text("pd", encoding="utf-8")
    assert check_layout(root) == []
    (root / "world_map.jpg").write_bytes(b"nope")
    assert any("world_map" in item for item in check_layout(root))


def test_onedir_layout_checker_rejects_webengine_leftovers(tmp_path):
    """Option B (2026-11-09): a WebEngine DLL or vendored notice reaching the
    onedir folder is a packaging regression, not a legacy-art false positive."""
    from tools.check_onedir_layout import check_layout

    root = tmp_path / "OrbitRxMonitor"
    (root / "_internal" / "PySide6").mkdir(parents=True)
    (root / "OrbitRxMonitor.exe").write_bytes(b"x")
    (root / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(b"x")
    (root / "_internal" / "ne_110m_dark.png").write_bytes(b"x")
    (root / "_internal" / "LICENSE").write_bytes(b"x")
    (root / "_internal" / "NOTICE").write_bytes(b"x")
    (root / "_internal" / "PRIVACY.md").write_bytes(b"x")
    (root / "_internal" / "third_party" / "qt" / "LICENSES").mkdir(parents=True)
    (root / "_internal" / "third_party" / "qt" / "LICENSES" / "LGPL-3.0-only.txt").write_text("lgpl", encoding="utf-8")
    (root / "_internal" / "third_party" / "natural_earth").mkdir(parents=True)
    (root / "_internal" / "third_party" / "natural_earth" / "TERMS_OF_USE.txt").write_text("pd", encoding="utf-8")
    assert check_layout(root) == []
    (root / "_internal" / "PySide6" / "Qt6WebEngineCore.dll").write_bytes(b"nope")
    assert any("Qt6WebEngineCore.dll" in item for item in check_layout(root))


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


# --- P2 (Risk screen of 161d6e5): published source-offer doc ----------------


def test_qt_source_offer_doc_is_published_and_split_by_release():
    offer = (ROOT / "docs" / "QT_SOURCE_OFFER.md").read_text(encoding="utf-8")
    assert offer.startswith("# Qt corresponding source (published)\n")
    for gone in ("Stage 2 draft", "NOT published", "must not be\ncopied",
                 "until hosting actually\nexists", "Text ready to publish once hosting exists"):
        assert gone not in offer, gone
    assert "### 5.2.0\n" in offer
    assert "### 5.1.0 (WebEngine era) only\n" in offer
    five_two = offer.split("### 5.2.0\n")[1].split("### 5.1.0")[0]
    five_one = offer.split("### 5.1.0 (WebEngine era) only\n")[1].split("### Open item")[0]
    assert "pyside-setup-everywhere-src-6.12.0.tar.xz" in five_two
    assert "qt-everywhere-src-6.12.0.tar.xz" in five_two
    assert "qtwebengine" not in five_two
    assert "the offer in NOTICE" in five_two
    assert "same two archives above plus this one" in five_one
    qtwe_rows = [l for l in five_one.splitlines() if l.startswith("| `qtwebengine-everywhere-src-6.140.0-rc.tar.xz`")]
    assert len(qtwe_rows) == 1
    assert "Covers the WebEngine-era 5.1.0 binary only; 5.2.0 ships no Qt WebEngine." in qtwe_rows[0]
    # The 5.1.0-only sentence lives on the qtwebengine row only.
    assert offer.count("WebEngine-era 5.1.0 binary only") == 1
    open_item = offer.split("### Open item (5.1.0 only, not part of 5.2.0)\n")[1].split("## ")[0]
    assert "chromium_attributions.qdoc" in open_item
    assert "not part of the\n5.2.0 offer" in open_item
    assert "stay hosted, unchanged, for as long as copies of 5.1.0 are\noffered" in offer


def test_superseded_draft_is_kept_and_no_doc_points_to_it_as_current():
    draft = ROOT / "docs" / "QT_SOURCE_OFFER_DRAFT.md"
    assert draft.is_file()
    assert "docs/QT_SOURCE_OFFER.md" in draft.read_text(encoding="utf-8")[:400]
    distribution = (ROOT / "docs" / "DISTRIBUTION.md").read_text(encoding="utf-8")
    for line in distribution.splitlines():
        if "QT_SOURCE_OFFER_DRAFT.md" in line:
            for chunk in line.split("QT_SOURCE_OFFER_DRAFT.md")[1:]:
                assert chunk.lstrip("`").lstrip().startswith(("is superseded", ")")), chunk[:60]
