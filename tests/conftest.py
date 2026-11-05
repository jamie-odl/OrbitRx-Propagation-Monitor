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
    """Skip Python/Qt interpreter teardown, which can crash in Qt's global
    destructors (QtWebEngine) after every test has already passed. Reports
    (including --junitxml) are written before this hook runs."""
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    if sys.platform == "win32":
        # Windows' C runtime _exit runs DLL detach handlers, which triggers
        # the same QtWebEngine shutdown crash; TerminateProcess does not.
        import ctypes
        ctypes.windll.kernel32.TerminateProcess(
            ctypes.windll.kernel32.GetCurrentProcess(), _exit_status,
        )
    os._exit(_exit_status)
