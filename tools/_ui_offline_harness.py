"""Shared offline/deterministic setup for tools/ui_screenshots.py, tools/ui_timing.py
and tests/test_ui_tools.py.

Not a CLI entry point itself -- just the plumbing those three files all need:
getting the repo importable, running the Qt app offscreen with no real network
access, and a slow-serial stub for CAT timing. Every patch here mirrors the
monkeypatches already used by tests/test_small_screen_fit.py and
tests/test_settings_dialog.py, so this keeps working the same way those do.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


def ensure_repo_on_path() -> Path:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def offline_env() -> None:
    """Must run before the first `import orbitrx...`."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Gate already used in production (orbitrx.offline.offline_fixture): makes
    # fetch_weather/controller.start() take their synchronous, no-network path.
    os.environ.setdefault("ORBITRX_OFFLINE_FIXTURE", "1")
    # Must happen before either tool constructs its QApplication below.
    from orbitrx.ui.dpi import set_high_dpi_rounding_policy
    set_high_dpi_rounding_policy()


def make_work_dir() -> Path:
    """A private cwd with a config.json that never touches the network even if
    every monkeypatch below were somehow skipped: a real home position (so
    refresh_location takes the manual-position branch) and IP geolocation /
    update checks turned off."""
    work = Path(tempfile.mkdtemp(prefix="orbitrx-ui-tools-"))
    (work / "config.json").write_text(
        '{"map_backend":"static","check_updates_on_launch":false,'
        '"home_lat":51.5081,"home_lon":-0.1281,"ip_geolocation_enabled":false,'
        '"minimize_to_tray":false,"show_demo_spots":false}',
        encoding="utf-8",
    )
    return work


def stub_controller_network(stub_weather: bool = True) -> None:
    """Best-effort monkeypatch of every network-touching entry point the
    controller/UI can reach. Each patch is independent and wrapped so a
    renamed/removed attribute (future threading refactor) is skipped rather
    than fatal.

    stub_weather=False leaves OrbitRxController.fetch_weather alone, for the
    map-rebuild timing measurement, which needs the real (offline-fixture-gated)
    call path to exercise the actual rebuild.
    """
    try:
        import orbitrx.spots.service as svc
        svc.SpotsService.start = lambda self: None
    except Exception:
        pass
    try:
        import orbitrx.dx as dx
        dx.DxClusterService.start = lambda self: None
    except Exception:
        pass
    try:
        from orbitrx.ui.controller import OrbitRxController
        OrbitRxController.refresh_location = lambda self: None
        if stub_weather:
            OrbitRxController.fetch_weather = lambda self: None
    except Exception:
        pass
    try:
        import orbitrx.ui.qt_app as qt_app
        qt_app.QtOrbitRxApplication._alarm_excellent = lambda self: None
        qt_app.QtOrbitRxApplication._alarm_storm = lambda self: None
        qt_app.check_github_release = lambda *_a, **_k: {}
    except Exception:
        pass


def patch_window_fit_avail(width: int, height: int) -> None:
    """Same technique as tests/test_small_screen_fit.py's `small_avail` fixture,
    generalized to any target size: Qt's offscreen platform defaults to an
    800x800 screen, which would silently clamp a requested 1280x800 window, so
    every captured/timed size gets its own emulated available geometry."""
    try:
        import orbitrx.ui.window_fit as window_fit
        from PySide6.QtCore import QRect
    except Exception:
        return
    rect = QRect(0, 0, width, height)
    window_fit._available_geometry = lambda widget: rect


def pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


def pump_until(app, predicate, timeout: float = 3.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` while pumping the event loop, for up to `timeout`
    seconds -- for waiting on a real async result (a worker thread flipping a
    state flag) instead of a fixed sleep that's either too slow or flaky
    under load. Returns whether `predicate()` was true before the deadline."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        app.processEvents()
        time.sleep(interval)
    return predicate()


def drive_weather_fetch_failure(app, ctrl, timeout: float = 3.0) -> bool:
    """Drives OrbitRxController.fetch_weather() down its real network-failure
    path -- used by tools/ui_screenshots.py to capture the genuine SPEC §10
    "no usable data"/"stale" states instead of faking widget text. Monkeypatches
    `fetch_space_weather_data` (as imported into orbitrx.ui.controller) to
    raise, and disables `offline_fixture()` for the duration of the
    `fetch_weather()` call only -- both patches, plus a forced
    `offline_cache_enabled=False` on this controller's config, are restored
    before returning so nothing else in the process keeps seeing them. Must
    never open the network: the real `fetch_space_weather_data` is never
    called.

    `ctrl.fetch_weather` must already resolve to the real method (callers
    that disabled it process-wide via stub_controller_network(stub_weather=True)
    need to rebind it on this one controller instance first). Returns whether
    the failure was actually applied (`weather_fetch_in_progress` false and
    `weather_last_fetch_ok` false) before `timeout` elapses."""
    import orbitrx.ui.controller as controller_mod

    orig_fetch = controller_mod.fetch_space_weather_data
    orig_offline_fixture = controller_mod.offline_fixture
    had_cache_key = "offline_cache_enabled" in ctrl.cfg.data
    orig_cache_flag = ctrl.cfg.data.get("offline_cache_enabled")

    def _raise_unreachable(*_args, **_kwargs):
        raise ConnectionError("source unreachable")

    controller_mod.fetch_space_weather_data = _raise_unreachable
    ctrl.cfg.data["offline_cache_enabled"] = False
    try:
        controller_mod.offline_fixture = lambda: False
        try:
            ctrl.fetch_weather()
        finally:
            controller_mod.offline_fixture = orig_offline_fixture
        return pump_until(
            app,
            lambda: not ctrl.state.weather_fetch_in_progress and not ctrl.state.weather_last_fetch_ok,
            timeout=timeout,
        )
    finally:
        controller_mod.fetch_space_weather_data = orig_fetch
        if had_cache_key:
            ctrl.cfg.data["offline_cache_enabled"] = orig_cache_flag
        else:
            ctrl.cfg.data.pop("offline_cache_enabled", None)


def teardown_window(app, win) -> None:
    """Stop background work and drop the window, tolerating a missing/renamed
    quiet_capture_shutdown by falling back to the same steps by hand."""
    try:
        from orbitrx.ui.qt_app import quiet_capture_shutdown
        quiet_capture_shutdown(app, win, None)
    except Exception:
        try:
            if getattr(win, "ctrl", None) is not None:
                win.ctrl.stop()
            win.close()
        except Exception:
            pass
    try:
        win.deleteLater()
        if app is not None:
            app.processEvents()
    except Exception:
        pass


def suppress_modal_dialogs() -> None:
    """RigWizardDialog's Test CAT pops a modal QMessageBox.information() on a
    successful tune -- harmless interactively, but it calls exec() and would
    hang this (headless, unattended) process forever waiting for a click that
    never comes. Patched globally for the process lifetime, which is fine: a
    one-shot CLI tool never needs a real modal answered."""
    try:
        from PySide6.QtWidgets import QMessageBox
    except Exception:
        return
    no_op = staticmethod(lambda *a, **k: None)
    QMessageBox.information = no_op
    QMessageBox.warning = no_op
    QMessageBox.critical = no_op
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)


def make_slow_serial(delay: float):
    """A pyserial.Serial stand-in whose open/write/read each block for `delay`
    seconds, emulating a serial port with a rig on the other end that never
    answers."""

    class _SlowSerial:
        def __init__(self, *_args, **_kwargs) -> None:
            time.sleep(delay)
            self.is_open = True

        def write(self, data) -> int:
            time.sleep(delay)
            return len(data)

        def read(self, size: int = 1) -> bytes:
            time.sleep(delay)
            return b""

        def close(self) -> None:
            self.is_open = False

    return _SlowSerial


def patch_slow_cat_serial(delay: float) -> bool:
    """Patch orbitrx.cat's pyserial handle so CatController.connect()/tune()
    block for `delay` seconds per open/write instead of touching real hardware.
    Returns False (no-op) if the CAT module shape has changed enough that the
    patch point can't be found."""
    try:
        import orbitrx.cat as cat
    except Exception:
        return False
    if getattr(cat, "serial", None) is None:
        return False
    try:
        cat.serial.Serial = make_slow_serial(delay)
        cat.CAT_AVAILABLE = True
        return True
    except Exception:
        return False
