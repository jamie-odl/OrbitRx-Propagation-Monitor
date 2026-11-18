"""Grab PNGs of the main window, Settings dialog and every toolbar/overflow menu,
offscreen and offline, at two sizes.

Usage:
    python tools/ui_screenshots.py --out DIR

Writes (into DIR):
    main_<size>.png
    settings_<size>.png
    menu_<name>_<size>.png   (one per toolbar QToolButton that has a menu)

for size in ("1280x800", "683x485"). Exits 0 and prints the files it wrote,
one per line; a widget/attribute this build no longer has is skipped rather
than treated as fatal, so this keeps working across future threading
refactors of orbitrx.ui.qt_app.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ui_offline_harness as harness

SIZES = [("1280x800", 1280, 800), ("683x485", 683, 485)]


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned or "menu"


def _toolbar_menus(win) -> list[tuple[str, object, object]]:
    """(slug, button, menu) for every toolbar QToolButton with a popup menu."""
    toolbar = getattr(win, "_toolbar", None)
    if toolbar is None:
        return []
    try:
        from PySide6.QtWidgets import QToolButton
    except Exception:
        return []
    menus = []
    seen_slugs: set[str] = set()
    for btn in toolbar.findChildren(QToolButton):
        menu = btn.menu() if hasattr(btn, "menu") else None
        if menu is None:
            continue
        name = btn.objectName() or btn.text() or "menu"
        slug = _slug(name)
        while slug in seen_slugs:
            slug += "_"
        seen_slugs.add(slug)
        menus.append((slug, btn, menu))
    return menus


def capture_size(app, out_dir: Path, label: str, width: int, height: int) -> list[Path]:
    from PySide6.QtCore import QPoint

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

        main_path = out_dir / f"main_{label}.png"
        win.grab().save(str(main_path))
        written.append(main_path)

        build_dialog = getattr(win, "_build_settings_dialog", None)
        if callable(build_dialog):
            try:
                dlg = build_dialog()
                dlg.show()
                harness.pump(app, 0.2)
                settings_path = out_dir / f"settings_{label}.png"
                dlg.grab().save(str(settings_path))
                written.append(settings_path)
                dlg.reject()
                harness.pump(app, 0.05)
            except Exception as exc:
                print(f"warning: settings dialog capture failed: {exc}", file=sys.stderr)

        for slug, btn, menu in _toolbar_menus(win):
            try:
                pos = btn.mapToGlobal(QPoint(0, btn.height()))
                menu.popup(pos)
                harness.pump(app, 0.15)
                menu_path = out_dir / f"menu_{slug}_{label}.png"
                menu.grab().save(str(menu_path))
                written.append(menu_path)
                menu.close()
                harness.pump(app, 0.05)
            except Exception as exc:
                print(f"warning: menu '{slug}' capture failed: {exc}", file=sys.stderr)
    finally:
        harness.teardown_window(app, win)

    return written


def main(argv: list[str] | None = None) -> int:
    harness.ensure_repo_on_path()
    harness.offline_env()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Directory to write PNGs into")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

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
            written.extend(capture_size(app, out_dir, label, width, height))
        except Exception as exc:
            print(f"warning: capture at {label} failed: {exc}", file=sys.stderr)

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
