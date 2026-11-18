"""Explicit high-DPI scale-factor rounding policy (orbitrx.ui.dpi), set at
every app entry point before its QApplication/QGuiApplication is built."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


def test_set_high_dpi_rounding_policy_sets_passthrough_before_app_exists(monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    import orbitrx.ui.dpi as dpi

    calls = []
    monkeypatch.setattr(QGuiApplication, "instance", staticmethod(lambda: None))
    monkeypatch.setattr(
        QGuiApplication, "setHighDpiScaleFactorRoundingPolicy",
        staticmethod(lambda policy: calls.append(policy)),
    )

    dpi.set_high_dpi_rounding_policy()

    assert calls == [Qt.HighDpiScaleFactorRoundingPolicy.PassThrough]


def test_set_high_dpi_rounding_policy_is_noop_once_an_app_exists(monkeypatch):
    from PySide6.QtGui import QGuiApplication

    import orbitrx.ui.dpi as dpi

    calls = []
    monkeypatch.setattr(QGuiApplication, "instance", staticmethod(lambda: object()))
    monkeypatch.setattr(
        QGuiApplication, "setHighDpiScaleFactorRoundingPolicy",
        staticmethod(lambda policy: calls.append(policy)),
    )

    dpi.set_high_dpi_rounding_policy()

    assert calls == []


def test_session_rounding_policy_is_passthrough():
    """tests/conftest.py applies the policy before any test in the session
    builds its first QApplication; this pins the effective, session-wide
    result of that call."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    assert (
        QGuiApplication.highDpiScaleFactorRoundingPolicy()
        == Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
