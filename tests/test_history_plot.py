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


def test_hist_date_display_format_has_no_iso_date(window): # S1
    assert window.hist_date.displayFormat() == "dd MMM yyyy"


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


def test_plot_x_axis_ticks_show_hours_and_minutes(window, monkeypatch): # M4
    rows = [
        {"ts": "2026-11-04T21:30:00+00:00", "kp": 2.0, "flux": 110},
        {"ts": "2026-11-04T23:00:00+00:00", "kp": 2.5, "flux": 115},
    ]
    monkeypatch.setattr(window.ctrl.store, "query_propagation", lambda q: rows)
    window.tabs.setCurrentIndex(1)
    window._refresh_plot_tab()
    canvas = window.plot_container.itemAt(0).widget()
    ax = canvas.figure.get_axes()[0]
    assert ax.xaxis.get_major_formatter().fmt == "%H:%M"


def test_plot_x_axis_ticks_include_day_for_multi_day_range(window, monkeypatch): # M4, regression
    rows = [
        {"ts": "2026-11-02T00:00:00+00:00", "kp": 2.0, "flux": 110},
        {"ts": "2026-11-04T23:00:00+00:00", "kp": 2.5, "flux": 115},
    ]
    monkeypatch.setattr(window.ctrl.store, "query_propagation", lambda q: rows)
    window.tabs.setCurrentIndex(1)
    window._refresh_plot_tab()
    canvas = window.plot_container.itemAt(0).widget()
    ax = canvas.figure.get_axes()[0]
    assert ax.xaxis.get_major_formatter().fmt == "%d %b %H:%M"


def test_no_data_shows_placeholder_not_crash(window):
    window.tabs.setCurrentIndex(1)
    window.hist_date.setDate(window.hist_date.date().addYears(-5))
    window._refresh_plot_tab()
    assert "No data" in window.plot_placeholder.text()


def test_short_range_ticks_are_unique_hh_mm():  # M4
    import datetime
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.dates import AutoDateLocator, DateFormatter
    from orbitrx.ui.formatting import history_plot_date_format, pad_datetime_range, widen_to_min_span
    t0 = datetime.datetime(2026, 11, 4, 23, 29, 10)
    times = [t0, t0 + datetime.timedelta(seconds=70)]
    lo, hi = widen_to_min_span(*pad_datetime_range(times[0], times[1]))
    fig, ax = plt.subplots()
    ax.plot(times, [1, 2])
    ax.xaxis.set_major_locator(AutoDateLocator(maxticks=7))
    fmt = history_plot_date_format(lo, hi)
    assert fmt == "%H:%M"
    ax.xaxis.set_major_formatter(DateFormatter(fmt))
    ax.set_xlim(lo, hi)
    fig.canvas.draw()
    labels = [t.get_text() for t in ax.get_xticklabels() if t.get_text()]
    plt.close(fig)
    assert len(labels) >= 2
    assert len(labels) == len(set(labels))
    assert all(len(l) == 5 and l[2] == ":" for l in labels)
