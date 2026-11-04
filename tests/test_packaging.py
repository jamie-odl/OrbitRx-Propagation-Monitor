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
    assert "AppPublisher=Obsidian Dynamics (Jamie Sibley)" in text
    assert "VersionInfoVersion=" in text
    assert "VersionInfoCompany=Obsidian Dynamics" in text
    assert "VersionInfoProductName=OrbitRx Propagation Monitor" in text
    assert "SetupIconFile=..\\assets\\orbitrx.ico" in text
    assert "SignTool" not in text  # M12: no signing


def test_inno_setup_default_version_matches_version_file():
    text = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert f'#define AppVer "{version}"' in text
