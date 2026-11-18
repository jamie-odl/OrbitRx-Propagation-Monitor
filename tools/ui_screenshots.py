"""Grab PNGs of the main window, Settings dialog and every menu-bar menu,
offscreen and offline, at two sizes.

Usage:
    python tools/ui_screenshots.py --out DIR
    python tools/ui_screenshots.py --out DIR --scale 1.5

Writes (into DIR):
    main_<size>.png
    statusbar_<size>.png        (crop of the main window's status bar)
    settings_<size>.png
    menubar_<name>_<size>.png   (one per File/View/Tools/Help menu, composited
                                 onto the whole main window)

for size in ("1280x800", "683x485"). Exits 0 and prints the files it wrote,
one per line; a widget/attribute this build no longer has is skipped rather
than treated as fatal, so this keeps working across future threading
refactors of orbitrx.ui.qt_app.

--scale re-runs the same captures again with QT_SCALE_FACTOR set, so every
filename gets a _<pct>pct suffix (e.g. main_1280x800_150pct.png) -- this must
happen in a fresh subprocess, since Qt only reads QT_SCALE_FACTOR when its
QGuiApplication is constructed. ORBITRX_UI_SCREENSHOTS_SCALE marks that child
process so it does not try to spawn a scaled child of its own.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ui_offline_harness as harness

SIZES = [("1280x800", 1280, 800), ("683x485", 683, 485)]
_SCALE_ENV_VAR = "ORBITRX_UI_SCREENSHOTS_SCALE"


def _scale_suffix(scale: float) -> str:
    return f"_{round(scale * 100)}pct"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned or "menu"


def _menu_bar_menus(win) -> list[tuple[str, object]]:
    """(slug, QMenu) for every top-level menu on the main window's menu bar."""
    menu_bar = getattr(win, "menuBar", None)
    if menu_bar is None:
        return []
    bar = menu_bar()
    if bar is None:
        return []
    menus = []
    seen_slugs: set[str] = set()
    for action in bar.actions():
        menu = action.menu()
        if menu is None:
            continue
        name = menu.objectName() or action.text() or "menu"
        slug = _slug(name)
        while slug in seen_slugs:
            slug += "_"
        seen_slugs.add(slug)
        menus.append((slug, menu))
    return menus


def _composite_menu_open(app, win, menu) -> object:
    """Render the whole window plus the given (already-open) popup menu
    composited at its on-screen position, as one QPixmap."""
    from PySide6.QtGui import QPainter

    action = menu.menuAction()
    menu_bar = win.menuBar()
    rect = menu_bar.actionGeometry(action)
    pos = menu_bar.mapToGlobal(rect.bottomLeft())
    menu.popup(pos)
    harness.pump(app, 0.15)

    menu_pixmap = menu.grab()
    composite = win.grab()
    top_left = win.mapFromGlobal(menu.pos())
    painter = QPainter(composite)
    painter.drawPixmap(top_left, menu_pixmap)
    painter.end()

    menu.close()
    harness.pump(app, 0.05)
    return composite


def capture_size(
    app, out_dir: Path, label: str, width: int, height: int, suffix: str = ""
) -> list[Path]:
    written: list[Path] = []
    harness.patch_window_fit_avail(width, height)

    try:
        from orbitrx.ui.qt_app import QtOrbitRxApplication
    except Exception as exc:
        print(f"warning: could not import QtOrbitRxApplication: {exc}", file=sys.stderr)
        return written

    win = QtOrbitRxApplication()
    try:
        win.resize(width, height)
        win.show()
        harness.pump(app, 0.3)
        # window_fit's one-shot post-show refit (_RefitOnShow) re-measures the
        # window's frame margins now that it's actually visible; the offscreen
        # platform can report a few px of (meaningless, since nothing is ever
        # drawn around it) frame once realized, shrinking the window below the
        # exact size just requested. That refit only ever fires once per Show
        # event, already consumed above, so reasserting the exact size here is
        # never re-clamped by it, and main_<size>.png comes out exactly
        # width x height.
        win.resize(width, height)
        harness.pump(app, 0.05)

        main_path = out_dir / f"main_{label}{suffix}.png"
        win.grab().save(str(main_path))
        written.append(main_path)

        status_bar = getattr(win, "statusBar", None)
        if callable(status_bar):
            try:
                bar = status_bar()
                if bar is not None and bar.isVisible():
                    statusbar_path = out_dir / f"statusbar_{label}{suffix}.png"
                    bar.grab().save(str(statusbar_path))
                    written.append(statusbar_path)
            except Exception as exc:
                print(f"warning: status bar capture failed: {exc}", file=sys.stderr)

        build_dialog = getattr(win, "_build_settings_dialog", None)
        if callable(build_dialog):
            try:
                dlg = build_dialog()
                dlg.show()
                harness.pump(app, 0.2)
                settings_path = out_dir / f"settings_{label}{suffix}.png"
                dlg.grab().save(str(settings_path))
                written.append(settings_path)
                dlg.reject()
                harness.pump(app, 0.05)
            except Exception as exc:
                print(f"warning: settings dialog capture failed: {exc}", file=sys.stderr)

        for slug, menu in _menu_bar_menus(win):
            try:
                composite = _composite_menu_open(app, win, menu)
                menu_path = out_dir / f"menubar_{slug}_{label}{suffix}.png"
                composite.save(str(menu_path))
                written.append(menu_path)
            except Exception as exc:
                print(f"warning: menubar '{slug}' capture failed: {exc}", file=sys.stderr)
    finally:
        harness.teardown_window(app, win)

    return written


def _run_all_captures(out_dir: Path, suffix: str = "") -> list[Path]:
    """The in-process capture pass: one real QApplication, every SIZES entry,
    writing files with the given filename suffix."""
    work_dir = harness.make_work_dir()
    os.chdir(work_dir)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        from orbitrx.ui.theme import apply_theme
        apply_theme(app)
    except Exception:
        pass

    harness.stub_controller_network(stub_weather=True)
    harness.suppress_modal_dialogs()

    written: list[Path] = []
    for label, width, height in SIZES:
        try:
            written.extend(capture_size(app, out_dir, label, width, height, suffix=suffix))
        except Exception as exc:
            print(f"warning: capture at {label} failed: {exc}", file=sys.stderr)
    return written


def _spawn_scaled_capture(out_dir: Path, scale: float) -> list[Path]:
    """QT_SCALE_FACTOR is only read when Qt's QGuiApplication is constructed,
    which has already happened in this process -- so the scaled pass has to
    run in a fresh subprocess instead."""
    env = dict(os.environ)
    env["QT_SCALE_FACTOR"] = str(scale)
    env[_SCALE_ENV_VAR] = str(scale)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--out", str(out_dir)]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return []
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    harness.ensure_repo_on_path()
    harness.offline_env()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Directory to write PNGs into")
    parser.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Also capture at this Qt scale factor (e.g. 1.5 for 150%%), via a "
        "subprocess with QT_SCALE_FACTOR set; those files get a _<pct>pct suffix",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    child_scale = os.environ.get(_SCALE_ENV_VAR)
    if child_scale is not None:
        # We are the subprocess _spawn_scaled_capture launched: this process's
        # QGuiApplication already sees QT_SCALE_FACTOR, so just capture once
        # under the suffixed names and return -- no further spawning.
        written = _run_all_captures(out_dir, suffix=_scale_suffix(float(child_scale)))
        for path in written:
            print(path)
        return 0

    written: list[Path] = list(_run_all_captures(out_dir))

    if args.scale is not None:
        written.extend(_spawn_scaled_capture(out_dir, args.scale))

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
