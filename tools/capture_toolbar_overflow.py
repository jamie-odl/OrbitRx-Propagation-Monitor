"""Capture the toolbar » overflow popup with Export actions visible.

Grabs the QMenu widget itself (not a flaky Xvfb screen composite) and also
writes a composite PNG of the main window with the menu painted on top so
Founder eyes can see Export grouping in one frame.

Usage:
    DISPLAY=:4 QT_QPA_PLATFORM=xcb python tools/capture_toolbar_overflow.py OUT_DIR
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, Qt, QPoint
    from PySide6.QtGui import QPainter, QImage

    app = QApplication.instance() or QApplication(sys.argv)

    # Work in a temp config dir next to out
    work = out_dir / "_overflow_work"
    work.mkdir(exist_ok=True)
    os.chdir(work)
    (work / "config.json").write_text(
        '{"map_backend":"static","check_updates_on_launch":false,'
        '"home_lat":51.5081,"home_lon":-0.1281,"ip_geolocation_enabled":false}',
        encoding="utf-8",
    )

    # Ensure repo importable
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from orbitrx.ui.theme import apply_theme
    from orbitrx.ui.qt_app import QtOrbitRxApplication

    apply_theme(app)
    QtOrbitRxApplication._alarm_excellent = lambda self: None  # type: ignore
    QtOrbitRxApplication._alarm_storm = lambda self: None  # type: ignore
    win = QtOrbitRxApplication()
    win.resize(1100, 720)
    win.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()

    btn = win._toolbar_overflow
    menu = btn.menu()
    assert menu is not None
    labels = [a.text() for a in menu.actions()]
    (out_dir / "12-toolbar-overflow-actions.txt").write_text(
        "\n".join(labels) + "\n", encoding="utf-8"
    )

    # Popup at button; grab menu widget + composite onto window
    pos = btn.mapToGlobal(QPoint(0, btn.height()))
    menu.popup(pos)
    app.processEvents()
    time.sleep(0.25)
    app.processEvents()

    # Direct menu grab (works without compositor painting onto root window)
    menu_img = menu.grab()
    menu_path = out_dir / "12-toolbar-overflow-menu.png"
    ok_menu = menu_img.save(str(menu_path))

    # Composite: window grab + menu pixmap at global offset
    win_img = win.grab()
    composite = win_img.copy()
    painter = QPainter(composite)
    # Map menu global pos into window coords
    top_left = win.mapFromGlobal(menu.pos())
    painter.drawPixmap(top_left, menu_img)
    painter.end()
    comp_path = out_dir / "12-main-toolbar-overflow-popup.png"
    ok_comp = composite.save(str(comp_path))

    menu.close()
    win.close()
    print(f"menu_saved={ok_menu} composite_saved={ok_comp} actions={labels}")
    print(f"wrote {menu_path} ({menu_path.stat().st_size if menu_path.exists() else 0} bytes)")
    print(f"wrote {comp_path} ({comp_path.stat().st_size if comp_path.exists() else 0} bytes)")
    return 0 if ok_menu and ok_comp and "Export snapshot" in labels else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "overflow-out")))
