"""Deterministic process-ending teardown for the Windows self-capture path.

orbitrx.ui.qt_app.run_capture_and_exit (used by the frozen exe's self-capture
and by tools/capture_shutdown_probe.py) replaces an earlier design where the
capture hook called os._exit itself while Qt objects -- top-level dialogs,
worker threads, QApplication -- were still alive. That crashed or hung on
Windows (CI runs 42876091854, 42878248609, 42881812414). These tests run the
real subprocess path these CI jobs depend on, plus the in-process guarantees
(no os._exit on the capture path, faulthandler armed only in capture mode,
normal exit/close-to-tray never touching the capture teardown) that are cheap
to assert without spawning a process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

ROOT = Path(__file__).resolve().parents[1]


def _subprocess_env() -> dict:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_probe_stage_log_shows_the_full_teardown_order(tmp_path):
    """threads-joined, widgets-deleted, qapplication-deleted, process-exit must
    appear in that order after window-closed, and no non-main thread may still
    be alive once teardown says threads are joined."""
    out = tmp_path / "order"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "capture_shutdown_probe.py"), str(out)],
        env=_subprocess_env(), timeout=90, capture_output=True, text=True, check=False,
    )
    stage_path = out / "shutdown-stage.txt"
    stage = stage_path.read_text(encoding="utf-8") if stage_path.is_file() else "<missing>"
    assert proc.returncode == 0, f"returncode={proc.returncode}\nstderr={proc.stderr}\nstage={stage}"
    lines = stage.strip().splitlines()
    assert "threads-joined" in lines, (
        f"expected no stragglers (daemon worker threads must all be joined before "
        f"widgets are deleted); got: {lines}"
    )
    required = ["window-closed", "threads-joined", "widgets-deleted", "qapplication-deleted", "process-exit"]
    positions = [lines.index(name) for name in required]
    assert positions == sorted(positions), f"stage order wrong: {lines}"
    assert lines[-1] == "process-exit"


def test_probe_never_calls_os_exit(tmp_path):
    """No part of the capture-process path -- hook or real teardown -- may
    call os._exit while Qt objects could still be alive; run in a subprocess
    since monkeypatching a C-level builtin only holds for that process."""
    out = tmp_path / "no-os-exit"
    out.mkdir()
    script = out / "probe_no_os_exit.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, sys
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            sys.path.insert(0, {str(ROOT)!r})

            def _forbidden(code):
                sys.stderr.write("os._exit was called on the capture path\\n")
                raise SystemExit(97)

            import orbitrx.ui.qt_app as qt_app
            qt_app.os._exit = _forbidden

            out_dir = sys.argv[1]
            os.environ["ORBITRX_CAPTURE_DIR"] = out_dir
            qt_app.run_capture_and_exit(out_dir)
            """
        ),
        encoding="utf-8",
    )
    capture_dir = out / "capture"
    proc = subprocess.run(
        [sys.executable, str(script), str(capture_dir)],
        env=_subprocess_env(), timeout=90, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, f"returncode={proc.returncode}\nstderr={proc.stderr}"


def test_faulthandler_watchdog_armed_only_in_capture_mode(tmp_path, monkeypatch):
    """faulthandler must not be touched by the in-process hook path pytest
    itself relies on; only run_capture_and_exit arms it."""
    import orbitrx.ui.qt_app as qt_app

    calls = {"enable": 0, "later": 0, "cancel": 0}
    monkeypatch.setattr(qt_app.faulthandler, "enable", lambda **_: calls.__setitem__("enable", calls["enable"] + 1))
    monkeypatch.setattr(
        qt_app.faulthandler, "dump_traceback_later", lambda *a, **k: calls.__setitem__("later", calls["later"] + 1)
    )
    monkeypatch.setattr(
        qt_app.faulthandler, "cancel_dump_traceback_later", lambda: calls.__setitem__("cancel", calls["cancel"] + 1)
    )
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)
    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)

    qt_app.run_release_capture_hook(tmp_path / "no-watchdog")
    assert calls == {"enable": 0, "later": 0, "cancel": 0}


def test_probe_faulthandler_file_is_created_only_by_the_real_teardown(tmp_path):
    """The subprocess path (which does call run_capture_and_exit) must create
    faulthandler.txt, proving the watchdog was armed there -- the counterpart
    to the in-process test above showing it is never armed by the bare hook."""
    out = tmp_path / "watchdog-armed"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "capture_shutdown_probe.py"), str(out)],
        env=_subprocess_env(), timeout=90, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "faulthandler.txt").is_file()


def test_normal_exit_and_close_to_tray_never_run_the_capture_teardown(tmp_path, monkeypatch):
    """shutdown_capture_process/_delete_qapplication must never run on the
    normal app-exit or close-to-tray paths: QApplication must still be valid
    (not deleted) afterward."""
    import shiboken6
    from PySide6.QtWidgets import QApplication

    import orbitrx.ui.qt_app as qt_app

    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)
    monkeypatch.delenv("ORBITRX_TEST_SIMULATED_RIG", raising=False)

    app = QApplication.instance() or QApplication([])
    win = qt_app.QtOrbitRxApplication()
    win.ctrl.cfg.set("minimize_to_tray", True)
    if win._tray is None:
        win._setup_tray()
    if win._tray is not None:
        win._tray.show()
    win.show()
    app.processEvents()
    win.close()  # minimize-to-tray: closeEvent must ignore this
    app.processEvents()
    assert shiboken6.isValid(app)
    assert shiboken6.isValid(win)

    win.ctrl.cfg.set("minimize_to_tray", False)
    win.close()  # real close now
    app.processEvents()
    assert shiboken6.isValid(app)
