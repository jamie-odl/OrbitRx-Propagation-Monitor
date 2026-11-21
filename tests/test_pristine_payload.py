import zipfile
from pathlib import Path

from tools.check_pristine_payload import runtime_residue, zip_runtime_residue


def test_pristine_tree_is_accepted(tmp_path: Path):
    root = tmp_path / "OrbitRxMonitor"
    (root / "_internal").mkdir(parents=True)
    (root / "OrbitRxMonitor.exe").write_bytes(b"x")
    assert runtime_residue(root) == []


def test_runtime_profile_is_rejected(tmp_path: Path):
    root = tmp_path / "OrbitRxMonitor"
    root.mkdir()
    (root / "config.json").write_text('{"map_backend":"leaflet"}', encoding="utf-8")
    (root / "orbitrx.db").write_bytes(b"sqlite")
    (root / "weather_cache.json").write_text("{}", encoding="utf-8")
    (root / "propagation_log.csv").write_text("ts\n", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "orbitrx.log").write_text("live\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "orbitrx_spots.db").write_bytes(b"db")
    found = set(runtime_residue(root))
    assert "config.json" in found
    assert "orbitrx.db" in found
    assert "weather_cache.json" in found
    assert "propagation_log.csv" in found
    assert "logs/" in found
    assert "data/" in found


def _zip_with(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "OrbitRx-5.2.0-win-x64.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    return path


def test_clean_release_zip_is_accepted(tmp_path: Path):
    path = _zip_with(tmp_path, [
        "OrbitRxMonitor/OrbitRxMonitor.exe",
        "OrbitRxMonitor/_internal/NOTICE",
        "OrbitRxMonitor-Setup.exe",
        "SHA256SUMS.txt",
    ])
    assert zip_runtime_residue(path) == []


def test_release_zip_with_runtime_files_is_rejected(tmp_path: Path):
    path = _zip_with(tmp_path, [
        "OrbitRxMonitor/OrbitRxMonitor.exe",
        "OrbitRxMonitor/logs/orbitrx.log",
        "OrbitRxMonitor/data/orbitrx_spots.db",
        "OrbitRxMonitor/config.json",
    ])
    found = set(zip_runtime_residue(path))
    assert "logs/" in found
    assert "data/" in found
    assert "config.json" in found


def test_ci_launches_a_copy_and_requires_a_pristine_folder_zip_and_installer():
    text = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build = text.split("  build-windows:")[1]
    capture = build.split("name: Self-capture")[1].split("\n      - name:")[0]
    assert "dist-smoke\\OrbitRxMonitor\\OrbitRxMonitor.exe" in capture
    assert "dist\\OrbitRxMonitor\\OrbitRxMonitor.exe" not in capture
    unwritable = build.split("name: Launch the release exe")[1].split("\n      - name:")[0]
    assert "dist-smoke\\OrbitRxMonitor\\OrbitRxMonitor.exe" in unwritable
    assert build.index("name: Stage a launch copy") < build.index("name: Self-capture")
    assert build.count("check_pristine_payload.py dist\\OrbitRxMonitor") >= 2
    assert "check_pristine_payload.py --zip" in build
    installer = build.split("name: Check the installer payload is pristine")[1].split("\n      - name:")[0]
    assert "/VERYSILENT" in installer
    assert "check_pristine_payload.py" in installer
    assert build.index("name: Check the installer payload is pristine") < build.index("name: Pack OrbitRx-5.2.0-win-x64.zip")
    pack = build.split("name: Pack OrbitRx-5.2.0-win-x64.zip")[1]
    assert "check_pristine_payload.py dist\\OrbitRxMonitor" in pack
    assert "check_pristine_payload.py --zip" in pack
