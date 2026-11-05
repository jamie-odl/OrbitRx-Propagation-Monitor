"""Shrink/position windows and dialogs to fit the available screen geometry.

Used by the main window and every top-level dialog so that on a small or
scaled-up display (e.g. a 683x485 logical desktop) controls like the Settings
dialog's Save button stay reachable instead of being pushed off-screen.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtGui import QGuiApplication

Rect = tuple[int, int, int, int]


# Window-frame allowance used before a window is shown (when Qt cannot yet
# report its real title bar and borders). Typical Windows 10/11 values.
DEFAULT_FRAME: tuple[int, int, int, int] = (8, 31, 8, 8)  # left, top, right, bottom


def client_avail(avail: Rect, frame: tuple[int, int, int, int]) -> Rect:
    """The area the client (content) rect may occupy so that the whole window,
    frame and title bar included, stays inside `avail`."""
    ax, ay, aw, ah = avail
    fl, ft, fr, fb = frame
    return (ax + fl, ay + ft, max(0, aw - fl - fr), max(0, ah - ft - fb))


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
    avail_rect = client_avail((avail.x(), avail.y(), avail.width(), avail.height()), _frame_margins(widget))
    x, y, w, h = clamp_rect(widget.width(), widget.height(), avail_rect, min_w, min_h)
    widget.setMinimumSize(min(min_w, avail_rect[2]), min(min_h, avail_rect[3]))
    widget.setGeometry(x, y, w, h)
    if not getattr(widget, "_fit_refit_installed", False):
        # Re-fit once on first show, when the real frame size is known.
        widget._fit_refit = _RefitOnShow(widget, min_w, min_h)
        widget.installEventFilter(widget._fit_refit)
        widget._fit_refit_installed = True
    return (x, y, w, h)


def _frame_margins(widget) -> tuple[int, int, int, int]:
    if widget.isVisible():
        fg, g = widget.frameGeometry(), widget.geometry()
        m = (g.x() - fg.x(), g.y() - fg.y(), fg.right() - g.right(), fg.bottom() - g.bottom())
        if any(m):
            return m
    if QGuiApplication.platformName() in ("offscreen", "minimal"):
        return (0, 0, 0, 0)
    return DEFAULT_FRAME


class _RefitOnShow(QObject):
    def __init__(self, widget, min_w: int, min_h: int) -> None:
        super().__init__(widget)
        self._args = (min_w, min_h)
        self._done = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if not self._done and event.type() == QEvent.Type.Show:
            self._done = True
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda: fit_to_screen(obj, *self._args))
        return False
