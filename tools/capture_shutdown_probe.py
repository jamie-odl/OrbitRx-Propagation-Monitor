"""Run one capture and exit the way the frozen app does.

Usage: capture_shutdown_probe.py <output-dir> [--with-view]

Without --with-view this is the static-map capture. --with-view only builds a
QWebEngineView and shuts it down, for machines where the full window is not
what is under test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> None:
    out = Path(sys.argv[1])
    if "--with-view" in sys.argv:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication

        from orbitrx.ui.leaflet_map import WEBENGINE_AVAILABLE
        from orbitrx.ui.qt_app import exit_after_qapplication_deleted, quiet_capture_shutdown

        if not WEBENGINE_AVAILABLE:
            sys.stderr.write("Qt WebEngine is not importable\n")
            raise SystemExit(2)
        app = QApplication([])

        class _Holder:
            def __init__(self, web) -> None:
                self.map_widget = self
                self.web = web
                self._timer = None
                self._cluster_pulse_timer = None
                self._tray = None
                self.ctrl = None

            def close(self) -> None:
                self.web.close()

        holder = _Holder(QWebEngineView())
        holder.web.setHtml("<p>probe</p>")
        app.processEvents()
        quiet_capture_shutdown(app, holder, out / "shutdown-stage.txt")
        exit_after_qapplication_deleted(0, out / "shutdown-stage.txt")
        return
    from orbitrx.ui.qt_app import exit_after_qapplication_deleted, run_release_capture_hook

    code = run_release_capture_hook(out)
    exit_after_qapplication_deleted(code, out / "shutdown-stage.txt")


if __name__ == "__main__":
    main()
