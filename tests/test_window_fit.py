"""orbitrx.ui.window_fit: clamp_rect pure logic and fit_to_screen widget wiring."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from orbitrx.ui.window_fit import clamp_rect


def test_clamp_rect_keeps_want_size_when_it_fits_within_avail():
    rect = clamp_rect(720, 520, (0, 0, 1920, 1080), 520, 380)
    assert rect == (600, 280, 720, 520)


def test_clamp_rect_shrinks_to_avail_when_want_exceeds_it():
    # Logical-pixel small desktop, e.g. 683x485: wanted 720x520 does not fit.
    rect = clamp_rect(720, 520, (0, 0, 683, 485), 520, 380)
    x, y, w, h = rect
    assert w == 683
    assert h == 485
    assert x == 0 and y == 0


def test_clamp_rect_never_shrinks_below_min_when_avail_has_room():
    rect = clamp_rect(300, 200, (0, 0, 1024, 728), 520, 380)
    x, y, w, h = rect
    assert w == 520
    assert h == 380
    # Centred inside avail.
    assert x == (1024 - 520) // 2
    assert y == (728 - 380) // 2


def test_clamp_rect_uses_avail_size_when_avail_smaller_than_min():
    rect = clamp_rect(900, 700, (10, 20, 400, 300), 520, 380)
    assert rect == (10, 20, 400, 300)


def test_clamp_rect_centres_within_offset_avail_origin():
    rect = clamp_rect(640, 440, (100, 50, 1024, 728), 640, 440)
    x, y, w, h = rect
    assert (x, y) == (100 + (1024 - 640) // 2, 50 + (728 - 440) // 2)
    assert (w, h) == (640, 440)


def test_clamp_rect_large_avail_large_want_both_fit():
    rect = clamp_rect(1440, 860, (0, 0, 2560, 1440), 640, 440)
    assert rect == (560, 290, 1440, 860)


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_fit_to_screen_shrinks_widget_on_small_available_geometry(app, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    import orbitrx.ui.window_fit as window_fit

    widget = QWidget()
    widget.resize(720, 520)
    monkeypatch.setattr(window_fit, "_available_geometry", lambda w: QRect(0, 0, 683, 485))

    result = window_fit.fit_to_screen(widget, 520, 380)
    assert result == (0, 0, 683, 485)
    assert widget.width() == 683
    assert widget.height() == 485
    assert widget.minimumWidth() == 520
    assert widget.minimumHeight() == 380


def test_fit_to_screen_leaves_widget_unchanged_on_large_available_geometry(app, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    import orbitrx.ui.window_fit as window_fit

    widget = QWidget()
    widget.resize(720, 520)
    monkeypatch.setattr(window_fit, "_available_geometry", lambda w: QRect(0, 0, 1024, 728))

    window_fit.fit_to_screen(widget, 520, 380)
    assert widget.width() == 720
    assert widget.height() == 520


def test_fit_to_screen_minimum_size_capped_to_tiny_available_geometry(app, monkeypatch):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    import orbitrx.ui.window_fit as window_fit

    widget = QWidget()
    widget.resize(720, 520)
    monkeypatch.setattr(window_fit, "_available_geometry", lambda w: QRect(0, 0, 400, 300))

    window_fit.fit_to_screen(widget, 520, 380)
    assert widget.minimumWidth() == 400
    assert widget.minimumHeight() == 300
    assert widget.width() == 400
    assert widget.height() == 300


def test_client_avail_reserves_frame_and_title_bar():
    from orbitrx.ui.window_fit import client_avail, clamp_rect

    # 150% on 1024x768 with a taskbar: 683x480 logical; frame 8/31/8/8.
    inner = client_avail((0, 0, 683, 480), (8, 31, 8, 8))
    assert inner == (8, 31, 667, 441)
    x, y, w, h = clamp_rect(720, 520, inner, 520, 380)
    # The whole window (client plus frame) stays inside the available area.
    assert x - 8 >= 0 and y - 31 >= 0
    assert x + w + 8 <= 683 and y + h + 8 <= 480
