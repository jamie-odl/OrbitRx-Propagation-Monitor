"""Shrink/position windows and dialogs to fit the available screen geometry.

Used by the main window and every top-level dialog so that on a small or
scaled-up display (e.g. a 683x485 logical desktop) controls like the Settings
dialog's Save button stay reachable instead of being pushed off-screen.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

Rect = tuple[int, int, int, int]


def clamp_rect(want_w: int, want_h: int, avail: Rect, min_w: int, min_h: int) -> Rect:
    """Fit a `want_w`x`want_h` rect inside `avail` (x, y, w, h).

    Shrinks to fit within `avail`, never below `min_w`/`min_h` unless `avail`
    itself is smaller than that minimum (in which case `avail`'s own size wins).
    The result is centred inside `avail`.
    """
    ax, ay, aw, ah = avail
    eff_min_w = min(min_w, aw)
    eff_min_h = min(min_h, ah)
    w = min(max(want_w, eff_min_w), aw)
    h = min(max(want_h, eff_min_h), ah)
    x = ax + (aw - w) // 2
    y = ay + (ah - h) // 2
    return (x, y, w, h)


def _available_geometry(widget) -> QRect:
    screen = widget.screen() or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def fit_to_screen(widget, min_w: int, min_h: int) -> Rect:
    """Clamp `widget`'s current size to its screen's available geometry.

    Sets a minimum size (capped to the available geometry, so a widget is
    never left with a minimum bigger than the screen it is on) and an
    explicit, centred geometry.
    """
    avail = _available_geometry(widget)
    avail_rect: Rect = (avail.x(), avail.y(), avail.width(), avail.height())
    x, y, w, h = clamp_rect(widget.width(), widget.height(), avail_rect, min_w, min_h)
    widget.setMinimumSize(min(min_w, avail.width()), min(min_h, avail.height()))
    widget.setGeometry(x, y, w, h)
    return (x, y, w, h)
