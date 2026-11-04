"""History plot: date axis clutter fix and dual Kp/SFI axes (M2, S1, S2)."""

from __future__ import annotations

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")
matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "fetch_weather", lambda self: None)
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    yield win
    win.ctrl.stop()
    win.deleteLater()
    app.processEvents()


def test_hist_date_is_a_calendar_popup_date_edit(window):
    from PySide6.QtWidgets import QDateEdit
    assert isinstance(window.hist_date, QDateEdit)
    assert window.hist_date.calendarPopup() is True


def test_plot_builds_dual_axes_for_kp_and_sfi(window):
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(5):
        window.ctrl.store.log_propagation({
            "ts": (now - datetime.timedelta(hours=i)).isoformat(),
            "kp": 2.0 + i * 0.1, "flux": 110 + i,
        })
    window.tabs.setCurrentIndex(1)
    window._refresh_plot_tab()
    assert window.plot_container.count() == 2
    canvas = window.plot_container.itemAt(0).widget()
    fig = canvas.figure
    axes = fig.get_axes()
    assert len(axes) == 2
    kp_ax, sfi_ax = axes
    assert kp_ax.get_ylim() == (0.0, 9.0)
    assert sfi_ax.get_ylim() == (50.0, 300.0)


def test_plot_legend_uses_dark_theme_colors(window):
    now = datetime.datetime.now(datetime.timezone.utc)
    for i in range(3):
        window.ctrl.store.log_propagation({
            "ts": (now - datetime.timedelta(hours=i)).isoformat(),
            "kp": 3.0, "flux": 150,
        })
    window.tabs.setCurrentIndex(1)
    window._refresh_plot_tab()
    canvas = window.plot_container.itemAt(0).widget()
    legend = canvas.figure.get_axes()[0].get_legend()
    assert legend is not None
    for text in legend.get_texts():
        assert text.get_color().lower() in ("#e3eaf2", "e3eaf2")


def test_no_data_shows_placeholder_not_crash(window):
    window.tabs.setCurrentIndex(1)
    window.hist_date.setDate(window.hist_date.date().addYears(-5))
    window._refresh_plot_tab()
    assert "No data" in window.plot_placeholder.text()
