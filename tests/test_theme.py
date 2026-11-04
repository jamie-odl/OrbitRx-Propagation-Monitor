"""Theme contrast (M11) and type scale (S7)."""

from __future__ import annotations

import re

from orbitrx.ui.theme import (
    BG, CHECK_BORDER, CONTROL_BORDER, FONT_BODY, FONT_CAPTION, FONT_SECTION, FONT_TITLE, QSS,
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


def test_checkbox_border_meets_ui_contrast_minimum():
    assert _contrast_ratio(CHECK_BORDER, BG) >= 3.0


def test_qss_uses_control_border_for_inputs_and_buttons():
    assert f"border: 1px solid {CONTROL_BORDER}" in QSS
    assert f"border: 1px solid {CHECK_BORDER}" in QSS


def test_type_scale_has_four_distinct_sizes():
    sizes = {FONT_CAPTION, FONT_BODY, FONT_SECTION, FONT_TITLE}
    assert len(sizes) == 4


def test_qss_only_uses_type_scale_font_sizes():
    used = {int(n) for n in re.findall(r"font-size:\s*(\d+)px", QSS)}
    allowed = {FONT_CAPTION, FONT_BODY, FONT_SECTION, FONT_TITLE}
    assert used <= allowed
