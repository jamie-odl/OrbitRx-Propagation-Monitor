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


def test_capture_hook_writes_fit_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "capture"
    exit_code = run_release_capture_hook(out_dir)
    assert exit_code == 0

    settings_full_png = out_dir / "settings-full.png"
    main_png = out_dir / "main-window.png"
    fit_txt = out_dir / "fit.txt"
    assert settings_full_png.is_file() and settings_full_png.stat().st_size > 0
    assert main_png.is_file() and main_png.stat().st_size > 0
    assert fit_txt.is_file()

    line = fit_txt.read_text(encoding="utf-8").strip()
    parts = dict(p.split("=", 1) for p in line.split())
    assert set(parts) == {
        "avail", "settings", "save_visible", "settings_frame_on_screen", "main",
        "main_frame_on_screen", "main_hscroll", "controls_reachable",
        "about_frame_on_screen", "wizard_frame_on_screen",
    }
    for key in ("avail", "settings", "main"):
        w, h = parts[key].split("x")
        assert int(w) > 0 and int(h) > 0
    assert parts["save_visible"] == "True"
    assert parts["settings_frame_on_screen"] in ("True", "False")
    assert parts["main_frame_on_screen"] in ("True", "False")
    assert parts["controls_reachable"] == "True"  # M1: Settings/Rig/About always reachable


def test_capture_hook_port_list_never_contains_simulated_rig(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "capture"
    run_release_capture_hook(out_dir)
    ports_text = (out_dir / "rig-wizard-release-ports.txt").read_text(encoding="utf-8")
    assert "Simulated" not in ports_text


def test_capture_hook_default_has_no_simulated_rig_and_writes_about_and_wizard(tmp_path, monkeypatch):
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "shots"
    assert run_release_capture_hook(out_dir) == 0
    assert "Simulated" not in (out_dir / "rig-wizard-release-ports.txt").read_text(encoding="utf-8")
    assert (out_dir / "about.png").is_file()
    assert (out_dir / "rig-wizard.png").is_file()


def test_capture_hook_negative_control_lists_simulated_rig(tmp_path, monkeypatch):
    """S3: with the test-only switch on, the same hook must list the simulated rig,
    which proves the CI gate (grep for 'Simulated') can actually fail."""
    monkeypatch.setenv("ORBITRX_TEST_SIMULATED_RIG", "1")
    from orbitrx.ui.qt_app import run_release_capture_hook

    out_dir = tmp_path / "neg"
    assert run_release_capture_hook(out_dir) == 0
    ports = (out_dir / "rig-wizard-release-ports.txt").read_text(encoding="utf-8")
    assert ports.strip()
    assert "Simulated" in ports


def test_capture_hook_never_exits_the_process_even_with_capture_dir_set(tmp_path, monkeypatch):
    """The hook itself must never end the process, regardless of
    ORBITRX_CAPTURE_DIR: only run_capture_and_exit (used by the frozen exe's
    self-capture and tools/capture_shutdown_probe.py) performs the real
    process-ending teardown, and it does so after this returns, not inside
    it. This replaces an earlier design where the hook called os._exit
    itself while Qt objects were still alive (Windows CI runs 42876091854 /
    42881812414 hung or crashed doing exactly that)."""
    def fake_exit(code):
        raise AssertionError(f"hook must never call os._exit (code={code})")

    import orbitrx.ui.qt_app as qt_app
    monkeypatch.setattr(qt_app.os, "_exit", fake_exit)
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    out_dir = tmp_path / "capture-exit"
    monkeypatch.setenv("ORBITRX_CAPTURE_DIR", str(out_dir))

    exit_code = qt_app.run_release_capture_hook(out_dir)
    assert exit_code == 0
    stage = (out_dir / "shutdown-stage.txt").read_text(encoding="utf-8")
    assert "window-closed" in stage
    assert "qapplication-deleted" not in stage
    assert "process-exit" not in stage

    from PySide6.QtWidgets import QApplication
    import shiboken6
    assert shiboken6.isValid(QApplication.instance())


def test_non_capture_exit_path_and_close_to_tray_never_call_os_exit(tmp_path, monkeypatch):
    """Normal app exit and close-to-tray must never reach os._exit. The
    capture-only os._exit is gated on ORBITRX_CAPTURE_DIR."""
    calls = []

    def fake_exit(code):
        calls.append(code)
        raise SystemExit(code)

    import orbitrx.ui.qt_app as qt_app
    monkeypatch.setattr(qt_app.os, "_exit", fake_exit)
    monkeypatch.setattr(os, "_exit", fake_exit)
    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)

    out_dir = tmp_path / "no-capture"
    assert qt_app.run_release_capture_hook(out_dir) == 0
    assert calls == []
    stage = (out_dir / "shutdown-stage.txt").read_text(encoding="utf-8")
    assert "window-closed" in stage
    assert "process-exit" not in stage

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    win = qt_app.QtOrbitRxApplication()
    win.ctrl.cfg.set("minimize_to_tray", True)
    if win._tray is None:
        win._setup_tray()
    if win._tray is not None:
        win._tray.show()
    win.show()
    app.processEvents()
    win.close()
    app.processEvents()
    assert calls == []
