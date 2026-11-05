"""Single dark theme for every OrbitRx window and dialog (REDESIGN-BRIEF-SOLID-9)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Design tokens (M2)
BG = "#0B1220"                 # --bg-app
SURFACE = "#121A2B"            # --bg-panel
BG_ELEVATED = "#1A2438"        # --bg-elevated
BG_MAP_MATTE = "#070B14"       # --bg-map-matte
BORDER = "#243044"             # --border-subtle (decorative)
BORDER_STRONG = "#3A4A66"      # --border-strong
# Interactive control borders must stay >=3:1 on BG and SURFACE (tests/test_theme.py).
CONTROL_BORDER = "#6B7A90"     # --text-muted family; ~3:1+ on panel/app
CHECK_BORDER = "#7A8896"
TEXT = "#E8EEF7"               # --text-primary
MUTED = "#9AA8BC"              # --text-secondary
TEXT_MUTED = "#6B7A90"         # --text-muted
ACCENT = "#5B8CFF"             # --accent (replaces electric cyan)
ACCENT_SOFT = "#1E2F55"        # --accent-soft
OK = "#3DDC97"                 # --ok
WARN = "#F0B429"               # --warn
ERR = "#F07178"                # --bad
BAD = ERR
GREYLINE = "#FF8A4C"           # --greyline
NIGHT_VEIL = (8, 14, 28, 140)  # ~rgba(8,14,28,0.55)
SPOT_LINE = (120, 180, 255, 140)
HEAT = (240, 113, 120, 71)     # ~0.28 alpha

MUTED_SECONDARY = TEXT_MUTED

CARD_BG = BG_ELEVATED
CARD_TEXT = TEXT
CARD_STYLE = (
    f"background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px;"
)

EMPTY_OVERLAY_STYLE = (
    "color: #C9D1D9; font-size: 13px; background: rgba(15,23,32,0.85); "
    "border-radius: 14px; padding: 8px 14px;"
)

FONT_CAPTION = 11
FONT_BODY = 13
FONT_SECTION = 15
FONT_TITLE = 20

# Aliases used across the app
PANEL = SURFACE


def _assets_dir() -> Path:
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
QToolBar {{
    background: {BG}; border: none; border-bottom: 1px solid {BORDER};
    spacing: 4px; padding: 4px 8px; min-height: 40px;
}}
QToolBar QToolButton {{
    color: {MUTED}; font-size: 13; font-weight: 500; padding: 6px 10px;
    border: none; border-radius: 6px; background: transparent;
}}
QToolBar QToolButton:hover {{ color: {TEXT}; background: {ACCENT_SOFT}; }}
QToolBar::separator {{ background: {BORDER}; width: 1px; height: 16px; margin: 0 6px; }}
QGroupBox {{
    border: none; margin-top: 16px; padding-top: 4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 0; color: {MUTED};
    font-size: {FONT_CAPTION}px; font-weight: 600;
}}
QLineEdit, QComboBox, QAbstractSpinBox {{ background: {BG_ELEVATED}; border: 1px solid {CONTROL_BORDER};
    border-radius: 8px; padding: 4px 8px; min-height: 24px;
}}
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {{
    border-color: {ACCENT};
}}
QAbstractSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: padding; width: 18px; border-left: 1px solid {CONTROL_BORDER};
    background: {BG_ELEVATED};
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 8px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 8px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {BORDER_STRONG}; }}
QAbstractSpinBox::up-arrow {{ image: url({_SPIN_UP_ICON}); width: 8px; height: 8px; }}
QAbstractSpinBox::down-arrow {{ image: url({_SPIN_DOWN_ICON}); width: 8px; height: 8px; }}
QAbstractSpinBox::up-arrow:disabled {{ image: url({_SPIN_UP_DIM}); }}
QAbstractSpinBox::down-arrow:disabled {{ image: url({_SPIN_DOWN_DIM}); }}
QPushButton {{
    background: transparent; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    color: {TEXT}; padding: 6px 14px; min-height: 20px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#primaryButton, QPushButton[primary="true"] {{
    background: {ACCENT}; color: {BG}; border: none; font-weight: 600;
}}
QPushButton#primaryButton:hover, QPushButton[primary="true"]:hover {{
    background: #7AA0FF;
}}
QTabWidget::pane {{ border: none; background: {BG}; top: -1px; }}
QTabBar::tab {{
    background: {BG}; color: {MUTED}; padding: 8px 14px; margin-right: 2px;
    border: none; min-height: 20px;
}}
QTabBar::tab:selected {{
    color: {TEXT}; border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER_STRONG}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}}
QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {CHECK_BORDER}; background: {BG_ELEVATED};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QListWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    outline: none; padding: 4px;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; color: {MUTED}; }}
QListWidget::item:selected {{
    background: {ACCENT_SOFT}; color: {TEXT};
    border-left: 3px solid {ACCENT};
}}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 5px; min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QLabel#muted, QLabel#bannerHint {{ color: {TEXT_MUTED}; font-size: {FONT_CAPTION}px; }}
QLabel#panelTitle {{ color: {TEXT}; font-size: {FONT_SECTION}px; font-weight: 600; }}
QLabel#sectionLabel {{
    color: {MUTED}; font-size: {FONT_CAPTION}px; font-weight: 600;
}}
QLabel a {{ color: {ACCENT}; text-decoration: none; }}
QToolButton#switchMapButton, QToolButton#helpChip {{
    color: {MUTED}; border: 1px solid {BORDER}; border-radius: 14px;
    padding: 4px 10px; background: transparent;
}}
QToolButton#switchMapButton:hover, QToolButton#helpChip:hover {{
    color: {TEXT}; border-color: {ACCENT};
}}
QToolButton#layerChip {{
    color: {MUTED}; border: 1px solid {BORDER}; border-radius: 14px;
    padding: 4px 10px; background: transparent; font-size: 13px;
}}
QToolButton#layerChip:checked {{
    color: {TEXT}; background: {ACCENT_SOFT}; border-color: {ACCENT};
}}
QToolButton#layerChip:disabled {{ opacity: 0.45; }}
QStatusBar {{ background: {BG}; color: {TEXT_MUTED}; font-size: 11px; border-top: 1px solid {BORDER}; }}
QDialogButtonBox {{ dialogbuttonbox-buttons-have-icons: 0; }}
QDialogButtonBox QPushButton {{ min-width: 72px; }}
QAbstractSpinBox QLineEdit {{ border: none; background: transparent; padding: 0px; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    mapping = [
        (QPalette.ColorRole.Window, BG),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, BG_ELEVATED),
        (QPalette.ColorRole.AlternateBase, SURFACE),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.Button, SURFACE),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, BG),
        (QPalette.ColorRole.Link, ACCENT),
        (QPalette.ColorRole.ToolTipBase, BG_ELEVATED),
        (QPalette.ColorRole.ToolTipText, TEXT),
    ]
    for role, color in mapping:
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(QSS)


def theme_token_dump() -> str:
    """Evidence dump for screens-v10/10-theme-tokens.txt."""
    tokens = {
        "--bg-app": BG,
        "--bg-panel": SURFACE,
        "--bg-elevated": BG_ELEVATED,
        "--bg-map-matte": BG_MAP_MATTE,
        "--border-subtle": BORDER,
        "--border-strong": BORDER_STRONG,
        "--text-primary": TEXT,
        "--text-secondary": MUTED,
        "--text-muted": TEXT_MUTED,
        "--accent": ACCENT,
        "--accent-soft": ACCENT_SOFT,
        "--ok": OK,
        "--warn": WARN,
        "--bad": ERR,
        "--greyline": GREYLINE,
        "--control-border": CONTROL_BORDER,
    }
    return "\n".join(f"{k}={v}" for k, v in tokens.items()) + "\n"
