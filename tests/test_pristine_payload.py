from pathlib import Path

from tools.check_pristine_payload import runtime_residue


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
