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

The caller's QT_QPA_PLATFORM=offscreen:configfile=... value is a path
relative to this process's starting cwd (the caller sets that as our
subprocess cwd), not an absolute one -- an absolute Windows path's drive
letter colon would otherwise split the platform plugin's ":"-separated
argument list, same reason tests/conftest.py avoids configfile on win32 for
its own (always-absolute-safe-on-posix) config. Qt's offscreen plugin
resolves that relative path, and synthesizes its screen(s) from it, during
QApplication/QGuiApplication construction below -- so the chdir() into this
probe's own private work dir (needed only so orbitrx's own config.json load
resolves) must happen *after* that construction, not before.
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

    from orbitrx.ui.dpi import set_high_dpi_rounding_policy
    set_high_dpi_rounding_policy()

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])

    work = harness.make_work_dir()
    os.chdir(work)
    harness.stub_controller_network(stub_weather=True)
    harness.suppress_modal_dialogs()

    from orbitrx.ui.theme import apply_theme
    apply_theme(app)

    from orbitrx.ui.qt_app import QtOrbitRxApplication, _save_button_fully_visible

    screen = app.primaryScreen()
    avail = screen.availableGeometry()

    win = QtOrbitRxApplication()

    # MAP_PROBE_SIZE="<w>x<h>" (optional): resize to a specific logical size
    # before measuring the map, so the map-coverage fields below reflect a
    # requested size rather than whatever fit_to_screen() defaulted to.
    map_probe_size = os.environ.get("MAP_PROBE_SIZE")
    if map_probe_size:
        req_w, req_h = (int(part) for part in map_probe_size.split("x"))
        win.resize(req_w, req_h)
        win.show()
        # A single resize() + processEvents() can leave the splitter/layout
        # reflow mid-settle (same reasoning as _wait_until() in
        # tests/test_map_dominant_layout.py): pump on real elapsed time,
        # not a fixed iteration count, so the map viewport/scene-fit measured
        # below is the final, settled one regardless of host speed.
        harness.pump(app, 0.5)

    dlg = win._build_settings_dialog()

    view = win.map_widget.view
    vp = view.viewport()
    scene_rect = win.map_widget._base_item.sceneBoundingRect()
    top_left = view.mapFromScene(scene_rect.topLeft())
    bottom_right = view.mapFromScene(scene_rect.bottomRight())
    transform = view.transform()

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
        "map_vp_w": vp.width(),
        "map_vp_h": vp.height(),
        "map_left": top_left.x(),
        "map_top": top_left.y(),
        "map_right": bottom_right.x(),
        "map_bottom": bottom_right.y(),
        "map_m11": transform.m11(),
        "map_m22": transform.m22(),
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
