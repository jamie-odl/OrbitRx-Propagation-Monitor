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
    # Must never exclude modules QtWebEngine needs.
    for required in ["QtWebEngineWidgets", "QtWebChannel"]:
        assert f"'PySide6.{required}'" not in text.split("excludes = [")[1].split("]")[0]


def test_inno_setup_has_publisher_version_and_icon():
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    assert "AppPublisher=Jamie Sibley" in text
    assert "VersionInfoVersion=" in text
    assert "VersionInfoCompany=Jamie Sibley" in text
    assert "VersionInfoProductName=OrbitRx Propagation Monitor" in text
    assert "SetupIconFile=..\\assets\\orbitrx.ico" in text
    assert "SignTool" not in text  # M12: no signing


def test_inno_setup_has_copyright_matching_about(): # I2
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    assert "AppCopyright=Copyright (C) 2026 Jamie Sibley" in text


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
    assert "u'CompanyName', u'Jamie Sibley'" in text
    assert "u'ProductName', u'OrbitRx Propagation Monitor'" in text
    assert "u'LegalCopyright', u'Copyright (C) 2026 Jamie Sibley'" in text
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
    # The signed/unsigned exe artifact must still contain only the three release files.
    unsigned_block = text.split("name: OrbitRx-windows-unsigned")[1].split("retention-days:")[0]
    assert "release-shots" not in unsigned_block


def test_write_version_info_reads_version_file(tmp_path):
    from tools.make_version_info import write_version_info

    version_file = tmp_path / "VERSION"
    version_file.write_text("9.2.1\n", encoding="utf-8")
    out = write_version_info(version_file, tmp_path / "file_version_info.txt")
    assert out.is_file()
    assert "filevers=(9, 2, 1, 0)" in out.read_text(encoding="utf-8")


def test_publisher_is_jamie_sibley_everywhere_and_never_obsidian_dynamics():
    """Jamie's decision (05 Nov 2026): the publisher is Jamie Sibley personally."""
    root = Path(__file__).resolve().parents[1]
    sources = {
        "installer/OrbitRxMonitor.iss": ("AppPublisher=Jamie Sibley", "VersionInfoCompany=Jamie Sibley",
                                         "AppCopyright=Copyright (C) 2026 Jamie Sibley"),
        "tools/make_version_info.py": ('COMPANY_NAME = "Jamie Sibley"',
                                       'LEGAL_COPYRIGHT = "Copyright (C) 2026 Jamie Sibley"'),
        "orbitrx/ui/about.py": ("Copyright &copy; 2026 Jamie Sibley",),
        "LICENSE": ("Copyright (C) 2026 Jamie Sibley",),
        "NOTICE": ("Copyright (C) 2026 Jamie Sibley",),
        "README.md": ("Copyright (C) 2026 Jamie Sibley", "unsigned", "SHA256SUMS"),
    }
    for rel, needles in sources.items():
        text = (root / rel).read_text(encoding="utf-8")
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
