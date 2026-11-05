"""Release-exe self-capture hook (M3 evidence): grabs the rig wizard port dropdown
and the DX cluster settings page when ORBITRX_CAPTURE_DIR is set, with the simulated
rig never involved."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(autouse=True)
def _offline_services(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)


def test_capture_hook_writes_dropdown_and_settings_captures(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "capture"
    exit_code = run_release_capture_hook(out_dir)
    assert exit_code == 0

    dropdown_png = out_dir / "rig-wizard-release-dropdown.png"
    ports_txt = out_dir / "rig-wizard-release-ports.txt"
    settings_png = out_dir / "settings-dx-cluster.png"
    assert dropdown_png.is_file() and dropdown_png.stat().st_size > 0
    assert settings_png.is_file() and settings_png.stat().st_size > 0
    assert ports_txt.is_file()


def test_capture_hook_port_list_never_contains_simulated_rig(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "capture"
    run_release_capture_hook(out_dir)
    ports_text = (out_dir / "rig-wizard-release-ports.txt").read_text(encoding="utf-8")
    assert "Simulated" not in ports_text
