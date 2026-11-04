"""Single dark theme for every OrbitRx window and dialog."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0F1720"
SURFACE = "#16212C"
BORDER = "#26394A"
# Interactive control boundaries need >=3:1 contrast against BG (M11); BORDER above is
# for decorative containers (group boxes) only and is intentionally darker/subtler.
CONTROL_BORDER = "#5B6B7C"  # ~3.4:1 on BG
CHECK_BORDER = "#7A8896"  # ~4.9:1 on BG
TEXT = "#E3EAF2"
MUTED = "#8FA3B5"
ACCENT = "#4FC3F7"
OK = "#81C784"
WARN = "#FFB74D"
ERR = "#E57373"

# Type scale (S7): caption/body/section/title are the only four sizes used app-wide.
FONT_CAPTION = 11
FONT_BODY = 13
FONT_SECTION = 15
FONT_TITLE = 20

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: {FONT_BODY}px; }}
QDialog, QMainWindow {{ background: {BG}; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 6px; margin-top: 10px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {MUTED}; font-size: {FONT_CAPTION}px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: 4px; padding: 4px 6px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border-color: {ACCENT}; }}
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
QCheckBox:disabled {{ color: #55687A; }}
QCheckBox::indicator:disabled {{ border-color: #33475A; background: {BG}; }}
QListWidget {{ background: {SURFACE}; border: 1px solid {CONTROL_BORDER}; border-radius: 4px; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; }}
QLabel#banner {{ background: {SURFACE}; color: {TEXT}; padding: 8px; border-radius: 4px; font-size: {FONT_SECTION}px; font-weight: 600; }}
QLabel#banner[state="error"] {{ background: #4A1C1C; color: #FFCDD2; }}
QLabel#muted {{ color: {MUTED}; font-size: {FONT_CAPTION}px; }}
QLabel a {{ color: {ACCENT}; }}
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
