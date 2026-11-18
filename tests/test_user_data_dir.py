"""Settings/data files live in a per-user folder in frozen builds, not the cwd.

Jamie's 5.2.0 attempt-2 L7 launch (15 Nov 2026) crashed with
PermissionError: 'config.json' because the frozen exe was started from a folder
it could not write. Frozen builds now use %APPDATA%\\OrbitRx; source runs keep
the historical cwd-relative behaviour.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from orbitrx import paths

DATA_NAMES = (
    "config.json",
    "orbitrx.db",
    "weather_cache.json",
    "propagation_log.csv",
    "dx_spots_log.csv",
    "export.json",
    "cat_log.txt",
)


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    """Simulate the frozen onedir exe: exe folder, APPDATA and a separate cwd."""
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "OrbitRxMonitor.exe"))
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.chdir(cwd)
    return {"exe": exe_dir, "appdata": appdata, "cwd": cwd, "data": appdata / "OrbitRx"}


def test_source_run_keeps_cwd_relative_paths(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.user_data_dir() == Path()
    for name in DATA_NAMES:
        assert paths.user_data_path(name) == Path(name)
    from orbitrx.config import AppConfig
    assert AppConfig().path == Path("config.json")


def test_frozen_uses_appdata_orbitrx_and_creates_it(frozen):
    assert not frozen["data"].exists()
    assert paths.user_data_dir() == frozen["data"]
    assert frozen["data"].is_dir()
    for name in DATA_NAMES:
        assert paths.user_data_path(name) == frozen["data"] / name


def test_frozen_without_appdata_falls_back_to_exe_folder(frozen, monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert paths.user_data_dir().resolve() == frozen["exe"].resolve()
    assert paths.user_data_path("config.json").resolve() == (frozen["exe"] / "config.json").resolve()


def test_frozen_config_load_writes_to_appdata_not_cwd(frozen):
    from orbitrx.config import AppConfig
    cfg = AppConfig().load()
    assert cfg.path == frozen["data"] / "config.json"
    assert cfg.path.is_file()
    assert not (frozen["cwd"] / "config.json").exists()
    assert not (frozen["exe"] / "config.json").exists()


def test_frozen_migration_copies_legacy_file_once_and_never_moves_it(frozen):
    legacy = frozen["exe"] / "config.json"
    legacy.write_text('{"cat_port": "COM9"}', encoding="utf-8")
    from orbitrx.config import AppConfig
    cfg = AppConfig().load()
    assert cfg.get("cat_port") == "COM9"
    assert legacy.is_file(), "legacy file must be copied, not moved"
    assert (frozen["data"] / "config.json").is_file()
    # An existing new-location file is never overwritten by the legacy copy.
    cfg.set("cat_port", "COM5")
    legacy.write_text('{"cat_port": "COM1"}', encoding="utf-8")
    assert AppConfig().load().get("cat_port") == "COM5"


def test_frozen_storage_and_cat_files_resolve_under_appdata(frozen):
    from orbitrx.storage import DataStore
    store = DataStore()
    assert store.db_path == frozen["data"] / "orbitrx.db"
    assert store.db_path.is_file()
    store.log_propagation({"ts": "2026-11-15T17:00:00+00:00", "kp": 2.0})
    store.log_dx_spot("G0ABC", "K1XYZ", 14.074)
    store.save_weather_cache({"kp": 2.0})
    assert store.load_weather_cache() == {"kp": 2.0}
    exported = store.export_json_snapshot({"a": 1})
    assert exported == frozen["data"] / "export.json"
    for name in ("propagation_log.csv", "dx_spots_log.csv", "weather_cache.json", "export.json"):
        assert (frozen["data"] / name).is_file(), name
        assert not (frozen["cwd"] / name).exists(), name

    from orbitrx.cat import CatController
    from orbitrx.config import AppConfig
    CatController(AppConfig().load())._log("test line")
    assert (frozen["data"] / "cat_log.txt").is_file()
    assert not (frozen["cwd"] / "cat_log.txt").exists()


def test_user_chosen_export_path_is_still_honoured(frozen, tmp_path):
    from orbitrx.storage import DataStore
    store = DataStore()
    store.log_dx_spot("G0ABC", "K1XYZ", 14.074)
    dest = tmp_path / "chosen" / "dx_spots.csv"
    dest.parent.mkdir()
    store.export_dx_csv(dest)
    assert dest.is_file()
    assert not (frozen["data"] / "dx_spots.csv").exists()


def test_explicit_db_path_still_wins(frozen, tmp_path):
    from orbitrx.storage import DataStore
    explicit = tmp_path / "explicit.db"
    assert DataStore(db_path=explicit).db_path == explicit


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits; the Windows CI build job launches the exe from C:\\Windows\\System32 instead")
def test_frozen_config_load_works_from_unwritable_cwd(frozen, tmp_path, monkeypatch):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        if os.access(locked, os.W_OK):
            pytest.skip("running with privileges that ignore directory permissions")
        monkeypatch.chdir(locked)
        from orbitrx.config import AppConfig
        cfg = AppConfig().load()  # used to raise PermissionError: 'config.json'
        assert cfg.path == frozen["data"] / "config.json"
    finally:
        locked.chmod(0o700)
