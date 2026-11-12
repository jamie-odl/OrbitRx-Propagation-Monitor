"""Packaging: app icon, PyInstaller spec, Inno Setup metadata (M12, N1)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_icon_file_exists_with_multiple_sizes():
    from PIL import Image
    path = ROOT / "assets" / "orbitrx.ico"
    assert path.is_file()
    img = Image.open(path)
    sizes = img.info.get("sizes") or {img.size}
    assert len(sizes) >= 4
    assert (256, 256) in sizes


def test_pyinstaller_spec_references_icon_and_excludes_unused_qt_modules():
    text = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    assert "icon='assets/orbitrx.ico'" in text
    assert "assets/orbitrx.ico" in text  # bundled as a data file too
    for unused in ["Qt3DCore", "QtQuick3D", "QtMultimedia", "QtCharts", "QtBluetooth", "QtSensors", "QtSql", "QtTest"]:
        assert unused in text
    # Option B (2026-11-09): the Leaflet/WebEngine map view is gone, so none of
    # its Chromium-backed stack may ship any more -- it must be excluded, and
    # must never be a hiddenimport.
    excludes_block = text.split("excludes = [")[1].split("]")[0]
    for excluded in ["QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngineQuick", "QtWebChannel", "QtQml", "QtQuick"]:
        assert f"'PySide6.{excluded}'" in excludes_block
    hiddenimports_line = text.split("hiddenimports = [")[1].split("]")[0]
    for forbidden in ["QtWebEngineWidgets", "QtWebChannel"]:
        assert f"PySide6.{forbidden}" not in hiddenimports_line


def test_inno_setup_has_publisher_version_and_icon():
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    assert "AppPublisher=thevenom" in text
    assert "VersionInfoVersion=" in text
    assert "VersionInfoCompany=thevenom" in text
    assert "VersionInfoProductName=OrbitRx Propagation Monitor" in text
    assert "SetupIconFile=..\\assets\\orbitrx.ico" in text
    assert "SignTool" not in text  # M12: no signing


def test_inno_setup_has_copyright_matching_about(): # I2
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    assert "AppCopyright=Copyright (C) 2026 thevenom" in text


def test_inno_setup_default_version_matches_version_file():
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert f'#define AppVer "{version}"' in text


def test_spec_references_generated_version_info_file(): # I3
    text = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    assert "make_version_info" in text
    assert "version=str(VERSION_INFO_FILE)" in text


def test_spec_disables_upx_for_the_main_exe(): # I4
    text = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    assert "upx=False" in text


def test_version_tuple4_pads_and_truncates_to_four_ints():
    from tools.make_version_info import version_tuple4
    assert version_tuple4("5.1.0") == (5, 1, 0, 0)
    assert version_tuple4("5.1") == (5, 1, 0, 0)
    assert version_tuple4("5.1.0.3") == (5, 1, 0, 3)


def test_build_version_info_text_has_expected_fields_and_parses():
    import ast
    from tools.make_version_info import build_version_info_text

    text = build_version_info_text("5.1.0")
    tree = ast.parse(text, mode="exec")
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr)
    assert "u'CompanyName', u'thevenom'" in text
    assert "u'ProductName', u'OrbitRx Propagation Monitor'" in text
    assert "u'LegalCopyright', u'Copyright (C) 2026 thevenom'" in text
    assert "u'FileVersion', u'5.1.0.0'" in text
    assert "u'ProductVersion', u'5.1.0'" in text
    assert "filevers=(5, 1, 0, 0)" in text


def test_screenshot_rig_wizard_tool_exists_and_uses_real_enumeration(): # M9 evidence
    path = ROOT / "tools" / "screenshot_rig_wizard.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "list_ports_detailed" in text
    assert "frameGeometry" in text
    assert "grabWindow" in text
    assert ".grab()" in text  # dialog.grab() fallback


def test_ci_has_windows_screenshot_job():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-screenshot:" in text
    assert "runs-on: windows-latest" in text
    assert "screenshot_rig_wizard.py" in text
    assert "rig-wizard-windows-screenshot" in text
    assert "com0com" in text
    assert "continue-on-error: true" in text
    assert "list_ports -v" in text


def test_ci_release_build_self_captures_and_checks_for_simulated_rig(): # M3
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ORBITRX_CAPTURE_DIR" in text
    assert "QT_SCALE_FACTOR" in text
    assert "ORBITRX_TEST_SIMULATED_RIG" in text
    assert "rig-wizard-release-ports.txt" in text
    assert "Simulated" in text
    assert "measure_field_edges.py" in text
    assert "release-exe-captures" in text
    assert "OrbitRx-windows-unsigned" not in text
    evidence = text.split("name: release-exe-captures")[1].split("retention-days:")[0]
    assert "release-shots/" in evidence
    assert "dist/" not in evidence


def test_ci_never_uploads_a_ship_set_artifact():
    """The repository is public, so any Actions artifact is downloadable by any
    signed-in GitHub user. No workflow that runs on main or feat/** may upload
    the onedir build, the exe, the installer or a zip of them. Uploads are
    limited to pytest XML, rig-wizard screenshots and release-shots/ (text and
    PNG captures, including a text-only ship-set inventory)."""
    import re

    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "OrbitRx-windows-unsigned" not in text
    assert "OrbitRx-native-prototype-unsigned" not in text
    assert "dist-zip" not in text
    names = re.findall(r"uses: actions/upload-artifact@v4\n(?:.*\n)*?\s+name: (\S+)", text)
    assert sorted(set(names)) == sorted({
        "pytest-${{", "rig-wizard-windows-screenshot", "release-exe-captures",
    }), names
    for block in text.split("uses: actions/upload-artifact@v4")[1:]:
        upload = block.split("\n      - ")[0]
        path_part = upload.split("path:", 1)[1]
        for banned in ("dist", ".exe", ".zip", "OrbitRxMonitor"):
            assert banned not in path_part, (banned, upload)
    inventory = text.split("name: Ship-set inventory")[1].split("\n      - ")[0]
    assert "upload-artifact" not in inventory
    assert "release-shots" in inventory

    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "upload-artifact" not in release
    assert "OrbitRx-native-prototype-unsigned" not in release
    assert "OrbitRx-windows-unsigned" not in release


def test_write_version_info_reads_version_file(tmp_path):
    from tools.make_version_info import write_version_info

    version_file = tmp_path / "VERSION"
    version_file.write_text("9.2.1\n", encoding="utf-8")
    out = write_version_info(version_file, tmp_path / "file_version_info.txt")
    assert out.is_file()
    assert "filevers=(9, 2, 1, 0)" in out.read_text(encoding="utf-8")


def test_publisher_is_thevenom_everywhere_and_never_obsidian_dynamics():
    """Founder override (05 Nov 2026): publisher / author is the pseudonym thevenom."""
    root = Path(__file__).resolve().parents[1]
    sources = {
        "installer/OrbitRxMonitor.iss": ("AppPublisher=thevenom", "VersionInfoCompany=thevenom",
                                         "AppCopyright=Copyright (C) 2026 thevenom"),
        "tools/make_version_info.py": ('COMPANY_NAME = "thevenom"',
                                       'LEGAL_COPYRIGHT = "Copyright (C) 2026 thevenom"'),
        "orbitrx/ui/about.py": ("Copyright &copy; 2026 thevenom",),
        "LICENSE": ("Copyright (C) 2026 thevenom",),
        "NOTICE": ("Copyright (C) 2026 thevenom",),
        "README.md": ("Copyright (C) 2026 thevenom", "unsigned", "SHA256SUMS"),
        ".github/workflows/ci.yml": ("Publisher check (thevenom", "ne 'thevenom'"),
    }
    for rel, needles in sources.items():
        text = (root / rel).read_text(encoding="utf-8")
        # ci.yml must keep an Obsidian rejection guard; other ship surfaces must not name it.
        if rel.endswith("ci.yml"):
            assert "Obsidian" in text and "throw" in text
        else:
            assert "Obsidian Dynamics" not in text, rel
        for needle in needles:
            assert needle in text, (rel, needle)


def test_about_has_verify_download_link_to_sha256sums():  # M6 (BRIEF-TO-9)
    from orbitrx.ui import about
    html = about._about_html()
    assert "Verify download" in html
    assert about.RELEASES_URL in html
    assert "SHA256SUMS.txt" in html
    assert "unsigned" in html
