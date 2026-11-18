"""Measure UI-thread timing and blocking for the main window, offscreen and
offline.

Usage:
    python tools/ui_timing.py [--runs 5] [--json OUT] [--cat-delay 2.0]

Measures (median of --runs runs, in ms, unless noted):
    settings_open_ms       trigger -> Settings dialog shown, events processed
    settings_apply_ms      Apply Settings (accept the dialog)
    config_writes          how many times AppConfig.save() ran during Apply
    menu_<name>_ms         trigger -> that toolbar/overflow menu's popup shown
    cat_test_main_ui_block_max_ms     longest UI-thread gap while the Settings
                                      dialog's Test CAT runs against an
                                      unresponsive port
    cat_test_wizard_ui_block_max_ms   same, for the rig wizard's Test CAT
    weather_rebuild_ui_block_max_ms / weather_rebuild_wall_ms
    dx_rebuild_ui_block_max_ms / dx_rebuild_wall_ms

Exits 0 always; a measurement whose hook can't be found reports "n/a" with a
reason instead of crashing, so this keeps working across future threading
refactors of orbitrx.ui.qt_app.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ui_offline_harness as harness

FIXTURE_SIZE = (1280, 800)


def measure_ui_block(app, action, settle: float = 0.05, follow: float = 3.0, heartbeat_ms: int = 5) -> float:
    """Longest gap (ms) between consecutive ticks of a `heartbeat_ms` QTimer
    while `action()` runs. `action` is called as a plain, synchronous Python
    call -- if it blocks the Python/Qt event loop, the heartbeat simply can't
    tick during that time, which is exactly the thing being measured."""
    from PySide6.QtCore import QTimer

    ticks: list[float] = []
    timer = QTimer()
    timer.setInterval(heartbeat_ms)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()
    try:
        harness.pump(app, settle)
        ticks.append(time.perf_counter())
        action()
        ticks.append(time.perf_counter())
        harness.pump(app, follow)
    finally:
        timer.stop()
    ticks.sort()
    if len(ticks) < 2:
        return 0.0
    return max((b - a) * 1000.0 for a, b in zip(ticks[:-1], ticks[1:]))


def _map_png_bytes(widget) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    widget.grab().save(buf, "PNG")
    return bytes(buf.data())


def measure_rebuild(app, win, trigger, heartbeat_ms: int = 5) -> tuple[float, float]:
    """(ui_block_max_ms, wall_ms) for a rebuild `trigger` that is expected to
    update win.map_widget's rendered pixels. The heartbeat keeps running
    through the synchronous trigger() call *and* the wait-for-pixmap-change
    polling below, so a rebuild that (today, or after a future refactor) runs
    as a deferred/queued call during processEvents() is still caught, not
    just a rebuild that happens inline."""
    from PySide6.QtCore import QTimer

    map_widget = getattr(win, "map_widget", None)
    if map_widget is None:
        return 0.0, 0.0
    before = _map_png_bytes(map_widget)

    ticks: list[float] = []
    timer = QTimer()
    timer.setInterval(heartbeat_ms)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()
    try:
        harness.pump(app, 0.02)
        t0 = time.perf_counter()
        ticks.append(t0)
        trigger()
        ticks.append(time.perf_counter())
        deadline = time.perf_counter() + 3.0
        after = _map_png_bytes(map_widget)
        while after == before and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.005)
            after = _map_png_bytes(map_widget)
        ticks.append(time.perf_counter())
    finally:
        timer.stop()
    wall_ms = (ticks[-1] - t0) * 1000.0
    ticks.sort()
    block_ms = max((b - a) * 1000.0 for a, b in zip(ticks[:-1], ticks[1:])) if len(ticks) >= 2 else 0.0
    return block_ms, wall_ms


def _settings_test_cat_button(dlg):
    from PySide6.QtWidgets import QPushButton

    for btn in dlg.findChildren(QPushButton):
        if btn.text().strip() == "Test CAT":
            return btn
    return None


def time_settings_open_close(app, win, runs: int) -> tuple[list[float], list[float], list[int]]:
    open_ms, apply_ms, writes = [], [], []
    import orbitrx.config as config_mod

    orig_save = config_mod.AppConfig.save
    counter = {"n": 0}

    def counting_save(self):
        counter["n"] += 1
        return orig_save(self)

    for _ in range(runs):
        t0 = time.perf_counter()
        dlg = win._build_settings_dialog()
        dlg.show()
        harness.pump(app, 0.02)
        open_ms.append((time.perf_counter() - t0) * 1000.0)

        config_mod.AppConfig.save = counting_save
        counter["n"] = 0
        t1 = time.perf_counter()
        win._apply_settings_dialog(dlg)
        apply_ms.append((time.perf_counter() - t1) * 1000.0)
        writes.append(counter["n"])
        config_mod.AppConfig.save = orig_save

        dlg.close()
        harness.pump(app, 0.01)
    return open_ms, apply_ms, writes


def time_menus(app, win, runs: int) -> dict[str, list[float]]:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QToolButton
    import re

    toolbar = getattr(win, "_toolbar", None)
    if toolbar is None:
        return {}
    results: dict[str, list[float]] = {}
    for btn in toolbar.findChildren(QToolButton):
        menu = btn.menu() if hasattr(btn, "menu") else None
        if menu is None:
            continue
        name = re.sub(r"[^A-Za-z0-9]+", "_", btn.objectName() or btn.text() or "menu").strip("_") or "menu"
        times: list[float] = []
        for _ in range(runs):
            pos = btn.mapToGlobal(QPoint(0, btn.height()))
            t0 = time.perf_counter()
            menu.popup(pos)
            harness.pump(app, 0.01)
            times.append((time.perf_counter() - t0) * 1000.0)
            menu.close()
            harness.pump(app, 0.01)
        results[name] = times
    return results


def build_window(app, width: int, height: int):
    harness.patch_window_fit_avail(width, height)
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    win = QtOrbitRxApplication()
    win.resize(width, height)
    win.show()
    harness.pump(app, 0.3)
    return win


def run_measurements(runs: int, cat_delay: float) -> dict:
    results: dict[str, dict] = {}

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        from orbitrx.ui.theme import apply_theme
        apply_theme(app)
    except Exception:
        pass

    harness.stub_controller_network(stub_weather=False)
    harness.suppress_modal_dialogs()

    win = build_window(app, *FIXTURE_SIZE)
    try:
        open_ms, apply_ms, writes = time_settings_open_close(app, win, runs)
        results["settings_open_ms"] = {"median": statistics.median(open_ms), "samples": open_ms}
        results["settings_apply_ms"] = {"median": statistics.median(apply_ms), "samples": apply_ms}
        results["config_writes"] = {"median": statistics.median(writes), "samples": writes}

        for name, times in time_menus(app, win, runs).items():
            results[f"menu_{name}_ms"] = {"median": statistics.median(times), "samples": times}

        cat_available = harness.patch_slow_cat_serial(cat_delay)
        if not cat_available:
            results["cat_test_main_ui_block_max_ms"] = {"na": True, "reason": "serial stub not patchable"}
            results["cat_test_wizard_ui_block_max_ms"] = {"na": True, "reason": "serial stub not patchable"}
        else:
            dlg = win._build_settings_dialog(initial_page="Rig")
            dlg.show()
            harness.pump(app, 0.05)
            btn = _settings_test_cat_button(dlg)
            if btn is None:
                results["cat_test_main_ui_block_max_ms"] = {"na": True, "reason": "Test CAT button not found"}
            else:
                results["cat_test_main_ui_block_max_ms"] = {"value": measure_ui_block(app, btn.click)}
            dlg.close()
            harness.pump(app, 0.02)

            from orbitrx.cat import CatController
            from orbitrx.ui.rig_wizard import RigWizardDialog

            wizard = RigWizardDialog(win.ctrl.cfg, CatController(win.ctrl.cfg))
            wizard.show()
            harness.pump(app, 0.05)
            wbtn = _settings_test_cat_button(wizard)
            if wbtn is None:
                results["cat_test_wizard_ui_block_max_ms"] = {"na": True, "reason": "Test CAT button not found"}
            else:
                results["cat_test_wizard_ui_block_max_ms"] = {"value": measure_ui_block(app, wbtn.click)}
            wizard.close()
            harness.pump(app, 0.02)

        from orbitrx.offline import FIXTURE_WEATHER

        weather_block, weather_wall = measure_rebuild(app, win, win.ctrl.fetch_weather)
        results["weather_rebuild_ui_block_max_ms"] = {"value": weather_block}
        results["weather_rebuild_wall_ms"] = {"value": weather_wall}

        update_dx = getattr(win.ctrl, "_update_dx", None)
        if callable(update_dx):
            dx_block, dx_wall = measure_rebuild(app, win, update_dx)
            results["dx_rebuild_ui_block_max_ms"] = {"value": dx_block}
            results["dx_rebuild_wall_ms"] = {"value": dx_wall}
        else:
            results["dx_rebuild_ui_block_max_ms"] = {"na": True, "reason": "controller._update_dx not found"}
            results["dx_rebuild_wall_ms"] = {"na": True, "reason": "controller._update_dx not found"}
    finally:
        harness.teardown_window(app, win)

    return results


def _fmt(entry: dict) -> str:
    if "value" in entry:
        return f"{entry['value']:.1f}"
    if "median" in entry:
        return f"{entry['median']:.1f}"
    return f"n/a ({entry.get('reason', 'unavailable')})"


def print_table(results: dict) -> None:
    name_w = max(len(k) for k in results) + 2
    print(f"{'metric':<{name_w}} value")
    print("-" * (name_w + 10))
    for key, entry in results.items():
        print(f"{key:<{name_w}} {_fmt(entry)}")


def main(argv: list[str] | None = None) -> int:
    harness.ensure_repo_on_path()
    harness.offline_env()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--json", default=None)
    parser.add_argument("--cat-delay", type=float, default=2.0,
                         help="Seconds the stubbed serial port blocks on open/write/read")
    args = parser.parse_args(argv)

    work_dir = harness.make_work_dir()
    os.chdir(work_dir)

    results = run_measurements(max(1, args.runs), args.cat_delay)

    print_table(results)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
