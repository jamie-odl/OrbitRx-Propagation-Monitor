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

    def _stop_window(win) -> None:
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
        try:
            win.close()
        except Exception:
            pass

    for widget in list(app.topLevelWidgets()):
        try:
            if shiboken6.isValid(widget) and isinstance(widget, QtOrbitRxApplication):
                _stop_window(widget)
        except Exception:
            pass
    app.processEvents()

    for widget in list(app.topLevelWidgets()):
        try:
            if shiboken6.isValid(widget):
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
def _cleanup_orbitrx_qt_windows():
    yield
    _destroy_leftover_qt_windows()
