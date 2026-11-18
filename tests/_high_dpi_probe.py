"""Subprocess probe for tests/test_high_dpi_fit.py.

Builds the main window and Settings dialog against a real simulated screen
(a fixed logical size and device pixel ratio supplied via the caller's
QT_QPA_PLATFORM=offscreen:configfile=... environment) and writes a JSON
report of their fitted geometry to the path given as argv[1].

Run out-of-process (rather than against the shared pytest-session
QApplication) because Qt's high-DPI scale factor is latched in from the
platform plugin when the first QApplication/QGuiApplication is constructed
and cannot be changed afterwards -- exactly the ordering
orbitrx.ui.dpi.set_high_dpi_rounding_policy() exists to protect. Not matched
by pytest's test_*.py collection pattern, so this file is not collected as a
test module itself.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out_path = Path(sys.argv[1])

    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import _ui_offline_harness as harness

    harness.offline_env()
    work = harness.make_work_dir()
    os.chdir(work)
    harness.stub_controller_network(stub_weather=True)
    harness.suppress_modal_dialogs()

    from orbitrx.ui.dpi import set_high_dpi_rounding_policy
    set_high_dpi_rounding_policy()

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    from orbitrx.ui.theme import apply_theme
    apply_theme(app)

    from orbitrx.ui.qt_app import QtOrbitRxApplication, _save_button_fully_visible

    screen = app.primaryScreen()
    avail = screen.availableGeometry()

    win = QtOrbitRxApplication()
    dlg = win._build_settings_dialog()

    report = {
        "device_pixel_ratio": screen.devicePixelRatio(),
        "rounding_policy": str(QGuiApplication.highDpiScaleFactorRoundingPolicy()),
        "avail_w": avail.width(),
        "avail_h": avail.height(),
        "win_w": win.width(),
        "win_h": win.height(),
        "win_min_w": win.minimumWidth(),
        "win_min_h": win.minimumHeight(),
        "dlg_w": dlg.width(),
        "dlg_h": dlg.height(),
        "save_button_visible": _save_button_fully_visible(dlg),
    }

    try:
        win.ctrl.stop()
    except Exception:
        pass
    win.deleteLater()
    app.processEvents()

    out_path.write_text(json.dumps(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
