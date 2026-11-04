"""Capture a real screenshot of the Rig setup wizard (M9 evidence).

Launches the actual RigWizardDialog against the real CatController serial-port
enumeration (orbitrx.cat.CatController.list_ports_detailed) -- it is never faked or
hardcoded, so the screenshot reflects whatever ports genuinely exist on the machine
running this script (none, if there are no COM ports, which is fine and expected on a
bare CI runner).

Usage:
    python tools/screenshot_rig_wizard.py [output_dir]

Writes two files into output_dir (default: the current directory):
    rig-wizard.png           -- QScreen.grabWindow of the dialog's frameGeometry,
                                 including the native window frame/title bar.
    rig-wizard-fallback.png  -- QWidget.grab() of just the dialog contents, as a
                                 fallback in case the frame grab comes back empty
                                 (e.g. under some remote-desktop/CI compositors).
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])

    from orbitrx.cat import CatController
    from orbitrx.config import AppConfig
    from orbitrx.ui.rig_wizard import RigWizardDialog
    from orbitrx.ui.theme import apply_theme

    apply_theme(app)

    cfg_path = Path(tempfile.gettempdir()) / "orbitrx_screenshot_config.json"
    cfg = AppConfig(path=cfg_path).load()
    cat = CatController(cfg)

    ports = cat.list_ports_detailed()
    print(f"Detected {len(ports)} real serial port(s): {ports}")

    dlg = RigWizardDialog(cfg, cat)
    dlg.show()

    # Let the window manager finish placing/decorating the window before grabbing it.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    dlg.raise_()
    dlg.activateWindow()
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    frame_path = out_dir / "rig-wizard.png"
    fallback_path = out_dir / "rig-wizard-fallback.png"

    fg = dlg.frameGeometry()
    screen = dlg.screen() or app.primaryScreen()
    frame_pixmap = screen.grabWindow(0, fg.x(), fg.y(), fg.width(), fg.height())
    frame_pixmap.save(str(frame_path))
    print(f"Saved {frame_path} ({frame_pixmap.width()}x{frame_pixmap.height()})")

    # Second capture with the port dropdown open, so the enumerated list is visible.
    dlg.port_combo.showPopup()
    deadline = time.time() + 1.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    rect = dlg.frameGeometry()
    popup = dlg.port_combo.view().window()
    if popup is not None and popup.isVisible():
        rect = rect.united(popup.frameGeometry())
    open_path = out_dir / "rig-wizard-dropdown.png"
    screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height()).save(str(open_path))
    print(f"Saved {open_path}")
    dlg.port_combo.hidePopup()

    fallback_pixmap = dlg.grab()
    fallback_pixmap.save(str(fallback_path))
    print(f"Saved {fallback_path} ({fallback_pixmap.width()}x{fallback_pixmap.height()})")

    dlg.reject()
    return 0


if __name__ == "__main__":
    sys.exit(main())
