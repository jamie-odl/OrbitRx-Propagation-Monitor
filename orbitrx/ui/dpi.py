"""Explicit high-DPI scale-factor rounding policy.

Qt6's implicit default is fragile across mixed-DPI multi-monitor setups, so
every entry point that constructs a QApplication/QGuiApplication calls
`set_high_dpi_rounding_policy()` first to pin `PassThrough` (fractional scale
factors applied as-is, no rounding to the nearest integer).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


def set_high_dpi_rounding_policy() -> None:
    """Set `PassThrough` as the high-DPI scale-factor rounding policy.

    Must run before any QApplication/QGuiApplication instance is constructed
    -- Qt only warns and ignores the call otherwise -- so this is a no-op
    once an application instance already exists, rather than emitting that
    warning on every later call (e.g. from a second entry-point helper, or a
    test session that already has an app).
    """
    if QGuiApplication.instance() is not None:
        return
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
