"""Single dark theme for every OrbitRx window and dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0F1720"
SURFACE = "#16212C"
BORDER = "#26394A"
# Interactive control boundaries need >=3:1 contrast against BOTH the window bg and the
# field's own bg (M11); BORDER above is for decorative containers (group boxes) only and
# is intentionally darker/subtler.
CONTROL_BORDER = "#6B8094"  # ~4.4:1 on BG, ~4.0:1 on SURFACE
CHECK_BORDER = "#7A8896"  # ~4.9:1 on BG
TEXT = "#E3EAF2"
MUTED = "#9AA7B4"  # ~6.9:1 on BG (S2)
ACCENT = "#4FC3F7"
OK = "#81C784"
WARN = "#FFB74D"
ERR = "#E57373"

# P1/P4: a second, slightly cooler muted tone for secondary hint text and map
# attribution, distinct from the general-purpose MUTED above.
MUTED_SECONDARY = "#8FA3B8"

# M3/M1: the card look shared by band tiles and the leaflet "tiles unavailable"
# overlay -- same background, border and 8px radius wherever a floating card
# sits over the map.
CARD_BG = "#1A2332"
CARD_TEXT = "#E3F2FD"
CARD_STYLE = f"background: {CARD_BG}; border: 1px solid {CHECK_BORDER}; border-radius: 8px;"

# S2: the "No spots in this window" map overlay, legible at arm's length on top of
# either map backend (>= 7:1 contrast between the text and its own pill background).
EMPTY_OVERLAY_STYLE = (
    "color: #C9D1D9; font-size: 13px; background: rgba(15,23,32,0.85); "
    "border-radius: 14px; padding: 8px 14px;"
)

# Type scale (S7): caption/body/section/title are the only four sizes used app-wide.
FONT_CAPTION = 11
FONT_BODY = 13
FONT_SECTION = 15
FONT_TITLE = 20


def _assets_dir() -> Path:
    """ui/assets, from the PyInstaller bundle if frozen, else next to this file."""
    from orbitrx.paths import bundled_root

    bundle = bundled_root()
    if bundle and (bundle / "orbitrx" / "ui" / "assets").is_dir():
        return bundle / "orbitrx" / "ui" / "assets"
    return Path(__file__).resolve().parent / "assets"


ASSETS_DIR = _assets_dir()
_SPIN_UP_ICON = (ASSETS_DIR / "spin-up.svg").as_posix()
_SPIN_DOWN_ICON = (ASSETS_DIR / "spin-down.svg").as_posix()
_SPIN_UP_DIM = (ASSETS_DIR / "spin-up-dim.svg").as_posix()
_SPIN_DOWN_DIM = (ASSETS_DIR / "spin-down-dim.svg").as_posix()

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: {FONT_BODY}px; }}
QDialog, QMainWindow {{ background: {BG}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 6px; margin-top: 10px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {MUTED}; font-size: {FONT_CAPTION}px; }}
QLineEdit, QComboBox, QAbstractSpinBox {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: 4px; padding: 4px 6px; }}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{ border-color: {ACCENT}; }}
QAbstractSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: padding; width: 18px; border-left: 1px solid {CONTROL_BORDER}; background: {SURFACE};
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 4px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 4px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {BORDER}; }}
QAbstractSpinBox::up-arrow {{ image: url({_SPIN_UP_ICON}); width: 8px; height: 8px; }}
QAbstractSpinBox::down-arrow {{ image: url({_SPIN_DOWN_ICON}); width: 8px; height: 8px; }}
QAbstractSpinBox QLineEdit {{ border: none; background: transparent; padding: 0; margin: 0; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url({_SPIN_UP_DIM}); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url({_SPIN_DOWN_DIM}); }}
QPushButton {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: 4px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; }}
QTabBar::tab {{ background: {SURFACE}; padding: 6px 14px; border: 1px solid {BORDER}; border-bottom: none; }}
QTabBar::tab:selected {{ background: {BG}; color: {ACCENT}; }}
QScrollArea {{ border: none; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {CHECK_BORDER}; border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled {{ color: #6B7F92; }}
QCheckBox::indicator:disabled {{ border-color: #33475A; background: {BG}; }}
QListWidget {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: 4px; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}
QLabel#banner {{ background: {SURFACE}; color: {TEXT}; padding: 8px; border-radius: 4px; font-size: {FONT_SECTION}px; font-weight: 600; }}
QLabel#banner[state="error"] {{ background: #4A1C1C; color: #FFCDD2; }}
QLabel#muted {{ color: {MUTED}; font-size: {FONT_CAPTION}px; }}
QLabel a {{ color: {ACCENT}; }}
QDialogButtonBox {{ dialogbuttonbox-buttons-have-icons: 0; }}
"""


def apply_theme(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    pal = QPalette()
    for role, colour in [
        (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, SURFACE), (QPalette.ColorRole.AlternateBase, BG),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, BG), (QPalette.ColorRole.Link, ACCENT),
        (QPalette.ColorRole.ToolTipBase, SURFACE), (QPalette.ColorRole.ToolTipText, TEXT),
    ]:
        pal.setColor(role, QColor(colour))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
