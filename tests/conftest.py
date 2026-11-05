"""Give the headless offscreen platform a desktop-sized screen.

Qt's offscreen plugin defaults to an 800 px wide screen, which clamps any
window resize above that and makes desktop-size layout tests meaningless.
Small-screen behaviour is tested explicitly at 667x441 and on the real
1024x768 Windows runner.
"""
import os
from pathlib import Path

if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    cfg = Path(__file__).parent / "data" / "offscreen-1920x1200.json"
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={cfg}"


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
    os._exit(_exit_status)
