"""ToastManager (P2B): a non-blocking, non-modal overlay that auto-dismisses
and coalesces repeats of the same message so a flaky connection retrying
every few seconds doesn't spam the user with one toast per retry."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


def _pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


@pytest.fixture
def parent():
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance() or QApplication([])
    w = QWidget()
    w.resize(400, 300)
    w.show()
    app.processEvents()
    yield w
    w.deleteLater()
    app.processEvents()


def test_show_toast_displays_message(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent)
    toasts.show_toast("Something failed", kind="error")
    assert toasts.is_visible()
    assert "Something failed" in toasts.current_text()


def test_toast_never_takes_focus_policy(parent):
    """A toast must never steal focus -- it is a plain label, not a window."""
    from PySide6.QtCore import Qt

    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent)
    toasts.show_toast("boom", kind="error")
    assert toasts._label.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert not toasts._label.isWindow()


def test_duplicate_errors_are_coalesced(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent, dedup_window_s=30.0)
    toasts.show_toast("DX cluster disconnected", kind="warning")
    toasts.show_toast("DX cluster disconnected", kind="warning")
    toasts.show_toast("DX cluster disconnected", kind="warning")
    assert toasts.shown_count == 1


def test_distinct_messages_are_not_coalesced(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent, dedup_window_s=30.0)
    toasts.show_toast("Weather update failed", kind="error")
    toasts.show_toast("Map failed to load", kind="error")
    assert toasts.shown_count == 2
    assert "Map failed to load" in toasts.current_text()


def test_toast_reappears_once_dedup_window_elapses(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent, dedup_window_s=0.05)
    toasts.show_toast("retry failed", kind="error")
    time.sleep(0.08)
    toasts.show_toast("retry failed", kind="error")
    assert toasts.shown_count == 2


def test_toast_auto_dismisses_after_short_timeout(parent):
    from PySide6.QtWidgets import QApplication

    from orbitrx.ui.toast import ToastManager

    app = QApplication.instance()
    toasts = ToastManager(parent, duration_ms=50)
    toasts.show_toast("temporary error", kind="error")
    assert toasts.is_visible()
    _pump(app, 0.3)
    assert not toasts.is_visible()


def test_reposition_keeps_toast_within_parent_bounds(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent)
    toasts.show_toast("a reasonably short message", kind="info")
    geo = toasts._label.geometry()
    assert geo.x() >= 0
    assert geo.y() >= 0
    assert geo.x() + geo.width() <= parent.width()
    assert geo.y() + geo.height() <= parent.height()

    parent.resize(200, 150)
    toasts.reposition()
    geo = toasts._label.geometry()
    assert geo.x() + geo.width() <= parent.width()
    assert geo.y() + geo.height() <= parent.height()


def test_dismiss_hides_immediately(parent):
    from orbitrx.ui.toast import ToastManager

    toasts = ToastManager(parent, duration_ms=60000)
    toasts.show_toast("hang on", kind="error")
    assert toasts.is_visible()
    toasts.dismiss()
    assert not toasts.is_visible()
