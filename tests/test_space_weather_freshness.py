"""P4-7 (SPEC §9 item 1 / §10): the space-weather panel header's freshness
stamp -- Never updated / Refreshing… / Updated hh:mm / Stale · hh:mm -- must
be driven entirely by the controller's real fetch state, never a sample.
"""

from __future__ import annotations

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")


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


def test_never_updated_before_first_fetch(window):
    assert window.ctrl.state.last_weather_update is None
    assert window._space_weather_freshness_text() == "Never updated"


def test_updated_hhmm_after_a_live_fetch(window):
    now = datetime.datetime.now(datetime.timezone.utc)
    window.ctrl.state.last_weather_update = now
    window.ctrl.state.last_weather_success_update = now
    window.ctrl.state.weather_last_fetch_ok = True
    assert window._space_weather_freshness_text() == f"Updated {now.strftime('%H:%M')}"


def test_refreshing_while_a_fetch_is_in_flight(window):
    window.ctrl.state.weather_fetch_in_progress = True
    assert window._space_weather_freshness_text() == "Refreshing…"


def test_stale_when_last_fetch_failed_but_last_good_data_exists(window):
    good = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    window.ctrl.state.last_weather_update = good
    window.ctrl.state.last_weather_success_update = good
    window.ctrl.state.weather_last_fetch_ok = False
    assert window._space_weather_freshness_text() == f"Stale · {good.strftime('%H:%M')}"


def test_trigger_weather_refresh_flips_header_to_refreshing_immediately(window, monkeypatch):
    """fetch_weather() flips state.weather_fetch_in_progress synchronously
    before handing the network call to a worker thread -- _trigger_weather_refresh
    must read that back and update the header label before returning, not
    wait for the (stubbed-out, in this fixture) async result."""
    calls = []
    monkeypatch.setattr(window.ctrl, "fetch_weather", lambda: calls.append(1) or setattr(
        window.ctrl.state, "weather_fetch_in_progress", True
    ))
    window._trigger_weather_refresh()
    assert calls == [1]
    assert window._freshness_lbl.text() == "Refreshing…"


def test_apply_weather_marks_live_fetch_ok_and_records_success_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController

    ctrl = OrbitRxController()
    ctrl._apply_weather({"kp_index": 2.0, "flux": 110.0}, offline=False)

    assert ctrl.state.weather_last_fetch_ok is True
    assert ctrl.state.last_weather_success_update == ctrl.state.last_weather_update


def test_apply_weather_offline_cache_fallback_marks_fetch_not_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController

    ctrl = OrbitRxController()
    ctrl._apply_weather({"kp_index": 2.0, "flux": 110.0}, offline=False)
    first_success = ctrl.state.last_weather_success_update

    ctrl._apply_weather({"kp_index": 2.0, "flux": 110.0}, offline=True)

    assert ctrl.state.weather_last_fetch_ok is False
    # A cache-fallback apply does not count as a new live success.
    assert ctrl.state.last_weather_success_update == first_success


def test_total_failure_with_no_cache_marks_stale_without_touching_last_update(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    import orbitrx.ui.controller as controller_mod

    ctrl = OrbitRxController()
    ctrl._apply_weather({"kp_index": 2.0, "flux": 110.0}, offline=False)
    good_update = ctrl.state.last_weather_update
    ctrl.state.weather_last_fetch_ok = True

    ctrl.cfg.data["offline_cache_enabled"] = False
    monkeypatch.setattr(
        controller_mod, "fetch_space_weather_data",
        lambda: (_ for _ in ()).throw(RuntimeError("NOAA down")),
    )
    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)

    assert ctrl.state.weather_last_fetch_ok is False
    assert ctrl.state.last_weather_update == good_update  # untouched, still "last-good"
