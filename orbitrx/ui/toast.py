"""Non-blocking, non-modal toast notifications (P2B).

A toast is a plain child QLabel, not a window: it never steals focus, never
spins a nested event loop, and is clipped to its parent's bounds for free, so
it behaves correctly in compact mode and at small window sizes. ToastManager
owns exactly one reusable label per parent -- a new message replaces whatever
is currently showing -- and coalesces repeats of the same message within
`dedup_window_s` so a flaky connection retrying every few seconds does not
spam the user with one toast per retry.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from orbitrx.ui.theme import ACCENT, BG_ELEVATED, ERR, FONT_CAPTION, OK, TEXT, WARN

DEFAULT_TOAST_DURATION_MS = 4000
DEFAULT_DEDUP_WINDOW_S = 20.0

_KIND_COLORS = {"error": ERR, "warning": WARN, "info": ACCENT, "ok": OK}


class ToastManager(QObject):
    """Anchors a single auto-dismissing toast to the bottom-right corner of
    `parent`. Callers must already be on the UI thread (route worker-thread
    failures through the same _UiInvoker/UiInvoker pattern used for every
    other controller callback before calling show_toast)."""

    def __init__(
        self,
        parent: QWidget,
        duration_ms: int = DEFAULT_TOAST_DURATION_MS,
        dedup_window_s: float = DEFAULT_DEDUP_WINDOW_S,
    ) -> None:
        super().__init__(parent)
        self._parent = parent
        self._duration_ms = duration_ms
        self._dedup_window_s = dedup_window_s
        self._last_shown: dict[str, float] = {}
        # Test/caller-visible count of toasts actually shown (i.e. not
        # coalesced as a duplicate) -- lets tests assert on spam suppression
        # without reaching into timer internals.
        self.shown_count = 0

        self._label = QLabel(parent)
        self._label.setObjectName("toastLabel")
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(360)
        self._label.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._label.hide)

    def show_toast(self, message: str, kind: str = "error") -> None:
        now = time.monotonic()
        last = self._last_shown.get(message)
        if last is not None and (now - last) < self._dedup_window_s:
            return  # identical message shown too recently -- coalesced, not spammed
        self._last_shown[message] = now
        self.shown_count += 1

        color = _KIND_COLORS.get(kind, ERR)
        self._label.setStyleSheet(
            f"background: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {color}; "
            f"border-radius: 8px; padding: 8px 12px; font-size: {FONT_CAPTION}px;"
        )
        self._label.setText(message)
        self._label.adjustSize()
        self._reposition()
        self._label.show()
        self._label.raise_()
        self._timer.start(self._duration_ms)

    def _reposition(self) -> None:
        margin = 12
        bottom_reserve = 28  # roughly one status-bar height, so it never overlaps it
        x = max(margin, self._parent.width() - self._label.width() - margin)
        y = max(margin, self._parent.height() - self._label.height() - margin - bottom_reserve)
        self._label.move(x, y)

    def reposition(self) -> None:
        """Re-anchor the toast after the parent resizes, a no-op while hidden."""
        if self._label.isVisible():
            self._reposition()

    def is_visible(self) -> bool:
        return self._label.isVisible()

    def current_text(self) -> str:
        return self._label.text()

    def dismiss(self) -> None:
        self._timer.stop()
        self._label.hide()
