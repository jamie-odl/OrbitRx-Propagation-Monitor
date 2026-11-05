"""Theme contrast (M11) and type scale (S7)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from orbitrx.ui.theme import (
    BG, BG_ELEVATED, CHECK_BORDER, CONTROL_BORDER, FONT_BODY, FONT_CAPTION, FONT_SECTION, FONT_TITLE, QSS,
    SURFACE,
)


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    la, lb = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def test_control_border_meets_ui_contrast_minimum():
    assert _contrast_ratio(CONTROL_BORDER, BG) >= 3.0


def test_control_border_meets_contrast_minimum_against_field_background(): # M11
    """Fields render on SURFACE, not BG, so the border must also pass 3:1 against SURFACE."""
    assert _contrast_ratio(CONTROL_BORDER, SURFACE) >= 3.0


def test_checkbox_border_meets_ui_contrast_minimum():
    assert _contrast_ratio(CHECK_BORDER, BG) >= 3.0


def test_qss_uses_control_border_for_inputs_and_buttons():
    assert f"border: 1px solid {CONTROL_BORDER}" in QSS
    assert f"border: 1px solid {CHECK_BORDER}" in QSS


def test_qss_fields_selector_covers_lineedit_combobox_and_spinboxes(): # M11
    assert f"QLineEdit, QComboBox, QAbstractSpinBox {{ background: {BG_ELEVATED}; border: 1px solid {CONTROL_BORDER}" in QSS


def test_qss_styles_spinbox_up_down_buttons(): # N-new-2
    assert "QAbstractSpinBox::up-button" in QSS
    assert "QAbstractSpinBox::down-button" in QSS
    assert "QAbstractSpinBox::up-arrow" in QSS
    assert "QAbstractSpinBox::down-arrow" in QSS


def test_qss_spinbox_reserves_room_for_both_arrows(): # M3
    """padding-right makes space for the button column so it never overhangs the field,
    and both buttons sit fully inside the border with a visible separator."""
    assert "QAbstractSpinBox { padding-right: 20px; }" in QSS
    assert "subcontrol-origin: padding; width: 18px; border-left: 1px solid" in QSS
    assert "subcontrol-position: top right" in QSS
    assert "subcontrol-position: bottom right" in QSS


def test_qss_spinbox_buttons_use_padding_origin_so_border_wraps_whole_control(): # M3
    """subcontrol-origin: border (the old value) draws the outer frame only around the
    text content, leaving the button column outside it; "padding" keeps the buttons
    inside the already-reserved padding-right space, so the single border encloses both."""
    assert "subcontrol-origin: border" not in QSS


def test_type_scale_has_four_distinct_sizes():
    sizes = {FONT_CAPTION, FONT_BODY, FONT_SECTION, FONT_TITLE}
    assert len(sizes) == 4


def test_qss_only_uses_type_scale_font_sizes():
    used = {int(n) for n in re.findall(r"font-size:\s*(\d+)px", QSS)}
    allowed = {FONT_CAPTION, FONT_BODY, FONT_SECTION, FONT_TITLE}
    assert used <= allowed


def test_no_inline_font_size_below_caption_minimum(): # S2, S7
    """No caption anywhere (inline QSS, QFont, or HTML) may render smaller than
    FONT_CAPTION, whether expressed in px, pt, or via setPointSize(F)/setPixelSize."""
    ui_dir = Path(__file__).resolve().parents[1] / "orbitrx" / "ui"
    pt_minimum = FONT_CAPTION * 0.75  # 11px == 8.25pt at 96 DPI
    for path in ui_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for size in re.findall(r"font-size:\s*(\d+)px", text):
            assert int(size) >= FONT_CAPTION, f"{path.name}: font-size {size}px"
        for size in re.findall(r"font-size:\s*([\d.]+)pt", text):
            assert float(size) >= pt_minimum, f"{path.name}: font-size {size}pt"
        for size in re.findall(r"QFont\([^)]*?,\s*(\d+)\)", text):
            assert int(size) >= FONT_CAPTION, f"{path.name}: QFont size {size}"
        for size in re.findall(r"setPointSizeF?\(\s*([\d.]+)\s*\)", text):
            assert float(size) >= pt_minimum, f"{path.name}: setPointSize(F) {size}"
        for size in re.findall(r"setPixelSize\(\s*(\d+)\s*\)", text):
            assert int(size) >= FONT_CAPTION, f"{path.name}: setPixelSize {size}"


def test_qss_disables_dialog_button_box_icons(): # N-new-9
    assert "dialogbuttonbox-buttons-have-icons: 0" in QSS


def test_dialog_buttons_render_without_icons(): # N-new-9
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication, QDialogButtonBox
    from orbitrx.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    for combo in (
        QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
        QDialogButtonBox.StandardButton.Close,
    ):
        box = QDialogButtonBox(combo)
        box.ensurePolished()
        for btn in box.buttons():
            assert btn.icon().isNull(), btn.text()


def test_spinbox_inner_line_edit_has_no_own_border_and_arrows_never_vanish():  # M3
    from orbitrx.ui import theme
    qss = theme.QSS
    assert "QAbstractSpinBox QLineEdit" in qss and "border: none" in qss
    assert "spin-up-dim.svg" in qss and "spin-down-dim.svg" in qss
    assert "image: none" not in qss
