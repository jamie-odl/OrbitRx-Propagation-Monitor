"""Give the headless offscreen platform a desktop-sized screen.

Qt's offscreen plugin defaults to an 800 px wide screen, which clamps any
window resize above that and makes desktop-size layout tests meaningless.
Small-screen behaviour is tested explicitly at 667x441 and on the real
1024x768 Windows runner.
"""
import os
import sys
from pathlib import Path

# POSIX only: on Windows the drive colon ("C:") would split the platform
# plugin's ":"-separated argument list, and tests chdir to a temp dir on
# another drive, so a relative path cannot be used either.
if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and sys.platform != "win32":
    _cfg = Path(__file__).resolve().parent / "data" / "offscreen-1920x1200.json"
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={_cfg}"

# Must run before any test in the session constructs its first QApplication.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbitrx.ui.dpi import set_high_dpi_rounding_policy  # noqa: E402

set_high_dpi_rounding_policy()

import gc
gc.disable()


_exit_status = 0


def pytest_sessionfinish(session, exitstatus):
    global _exit_status
    _exit_status = int(exitstatus)


def pytest_unconfigure(config):
    """Skip Python/Qt interpreter teardown, which used to crash in Qt's global
    QtWebEngine destructors after every test had already passed, back when the
    app still loaded WebEngine. Qt WebEngine is gone now, but the process-exit
    hook stays as cheap insurance against any other Qt global-destructor crash.
    Reports (including --junitxml) are written before this hook runs."""
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == "win32":
        # Windows' C runtime _exit runs DLL detach handlers, which used to
        # trigger the same QtWebEngine shutdown crash; TerminateProcess does not.
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.GetCurrentProcess.argtypes = []
        k32.TerminateProcess.restype = wintypes.BOOL
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        sys.stdout.flush()
        sys.stderr.flush()
        k32.TerminateProcess(k32.GetCurrentProcess(), _exit_status)
    os._exit(_exit_status)

import pytest


def _destroy_leftover_qt_windows() -> None:
    """Drop OrbitRx windows, timers, trays and matplotlib figures left behind
    by a test. deleteLater() plus one processEvents() is not enough: each
    leaked QMainWindow keeps pulse/startup/refresh timers alive, and later
    QtOrbitRxApplication() construction (which processes events) gets steadily
    slower. After ~20 history-plot windows the F7 1.0s budget is already
    missed; after a full suite it stretches to 8-10s even though Image.open
    itself is off the UI thread."""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        import shiboken6
        from orbitrx.ui.qt_app import QtOrbitRxApplication
    except Exception:
        return

    def _join_background_threads(win, app) -> bool:
        """Join every worker thread this window may have started before it is
        closed/deleted. Without this, a stale worker from one test (e.g. the
        history-query thread, or the one-shot map-load thread every window
        starts in __init__) can still be running when the next test's window
        starts a new one, or when this fixture's own plt.close("all") below
        touches matplotlib on the main thread -- matplotlib is not
        thread-safe, so an overlap there is a FreeType/Agg segfault risk, not
        just a slow test.

        Returns True only if every tracked thread actually finished within
        its bounded join -- the caller must not shiboken6.delete() a widget
        when this is False (see _destroy_leftover_qt_windows below): deleting
        the C++ side of a QWidget while its own worker thread is still
        running build_scene()/_pil_to_qimage() against `self` is a
        use-after-free, not just a slow-test annoyance -- this is the root
        cause nailed down for the intermittent
        "Garbage-collecting ... map_renderer._terminator_points" segfault
        (p4-r11): the join here used to be fire-and-forget, so a slow CI run
        (three threads contending for the GIL: this join, the map-rebuild
        worker, and -- before p4-r11's conftest fix below -- a real
        contests.py network thread) could time out and the caller would
        delete the widget anyway."""
        joined = True
        for name in ("_map_load_thread", "_update_check_thread", "_plot_query_thread"):
            thread = getattr(win, name, None)
            if thread is not None and thread.is_alive():
                try:
                    thread.join(timeout=2.0)
                except Exception:
                    pass
                if thread.is_alive():
                    joined = False
        map_widget = getattr(win, "map_widget", None)
        join_rebuild = getattr(map_widget, "join_rebuild_thread", None)
        if join_rebuild is not None:
            try:
                if not join_rebuild(timeout=2.0):
                    joined = False
            except Exception:
                pass
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass
        ctrl = getattr(win, "ctrl", None)
        if ctrl is not None:
            try:
                if ctrl.join_background_threads(timeout=2.0):
                    joined = False
            except Exception:
                pass
        return joined

    def _stop_window(win) -> bool:
        for name in (
            "_timer",
            "_cluster_pulse_timer",
            "_slider_refresh_timer",
            "_replay_refresh_timer",
            "_layers_save_timer",
        ):
            timer = getattr(win, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
        tray = getattr(win, "_tray", None)
        if tray is not None:
            try:
                tray.hide()
            except Exception:
                pass
            try:
                win._tray = None
            except Exception:
                pass
        ctrl = getattr(win, "ctrl", None)
        if ctrl is not None:
            try:
                ctrl.cfg.set("minimize_to_tray", False)
            except Exception:
                pass
            try:
                ctrl.stop()
            except Exception:
                pass
        joined = _join_background_threads(win, app)
        try:
            win.close()
        except Exception:
            pass
        return joined

    # Round 10 (p4-r11): only shiboken6.delete() a widget whose background
    # threads are confirmed finished (_stop_window's return value) -- a
    # widget left over from a slow/straggling thread is left alive (just
    # hidden) instead, and gets swept up by *this same fixture* on a later
    # test once that thread has actually finished. See _join_background_
    # threads' docstring for the use-after-free this prevents.
    safe_to_delete = []
    for widget in list(app.topLevelWidgets()):
        try:
            if shiboken6.isValid(widget) and isinstance(widget, QtOrbitRxApplication):
                if _stop_window(widget):
                    safe_to_delete.append(widget)
                else:
                    widget.hide()
        except Exception:
            pass
    app.processEvents()

    for widget in safe_to_delete:
        try:
            if shiboken6.isValid(widget):
                shiboken6.delete(widget)
        except Exception:
            pass
    app.processEvents()

    # Any other, non-OrbitRx-window top-level widget (dialogs, tooltips)
    # left over -- these never owned a background render/network thread, so
    # deleting them unconditionally is unchanged from before this round.
    for widget in list(app.topLevelWidgets()):
        try:
            if shiboken6.isValid(widget) and not isinstance(widget, QtOrbitRxApplication):
                shiboken6.delete(widget)
        except Exception:
            pass
    app.processEvents()

    try:
        import matplotlib.pyplot as plt
        plt.close("all")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _no_real_network_contest_refresh(monkeypatch):
    """Round 10 (p4-r11): orbitrx.contests.fetch_upcoming_contests() is called
    synchronously from weather_labels() on every weather/DX refresh (P1-safe:
    it never blocks), but a stale/missing cache makes it kick off a real
    background thread (orbitrx/contests.py::_start_cache_refresh) that does a
    genuine urllib HTTPS GET against contestcalendar.com. CI's own crash
    report named this exact thread as one of three concurrently running
    during the test-suite segfault -- whether or not it's the fault, a test
    run has no business making real network calls at all. Stubbed at the
    app-behaviour boundary (the thread-spawning function), not by changing
    fetch_upcoming_contests()'s own real caching/fallback logic, which stays
    exercised as-is; _CACHE stays None so every call falls back to the
    static UPCOMING_CONTESTS list, exactly like a fresh install with no
    network yet."""
    import orbitrx.contests as contests

    monkeypatch.setattr(contests, "_start_cache_refresh", lambda: None)
    yield


@pytest.fixture(autouse=True)
def _cleanup_orbitrx_qt_windows():
    yield
    _destroy_leftover_qt_windows()
