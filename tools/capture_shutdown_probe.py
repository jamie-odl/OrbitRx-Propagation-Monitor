"""Run the static-map capture and exit the way the frozen app does.

Usage: capture_shutdown_probe.py <output-dir>

Historical note: this probe used to also exercise a bare QWebEngineView's
shutdown path (--with-view) because the frozen app's leaflet import loaded
Qt WebEngine even when only the static map was shown, and a prior Windows
build crashed (0xC0000005) tearing it down. Qt WebEngine is no longer part
of the app at all (Option B, 2026-11-09), so that path can no longer occur
and the probe no longer builds one.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> None:
    out = Path(sys.argv[1])
    # Same env the frozen exe uses in CI self-capture, so this exercises
    # exactly the shutdown path run_qt_app takes (run_capture_and_exit:
    # join every worker thread, delete every widget, delete QApplication,
    # then exit) -- not the old os._exit-while-Qt-alive path it replaced.
    os.environ["ORBITRX_CAPTURE_DIR"] = str(out)
    from orbitrx.ui.qt_app import run_capture_and_exit

    run_capture_and_exit(out)


if __name__ == "__main__":
    main()
