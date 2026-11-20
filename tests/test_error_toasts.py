"""P2B: previously-silent UI-facing failures (weather fetch, DX cluster
disconnect, geolocation, update check, exports, CAT test, map load) now
surface a concise, non-blocking toast instead of being swallowed -- and none
of them pop a modal dialog to do it."""

from __future__ import annotations

import os
import threading
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
def no_modals(monkeypatch):
    """Fails the test loudly if any of these failure paths pops a modal."""
    from PySide6.QtWidgets import QMessageBox

    def _boom(*_a, **_k):
        raise AssertionError("a modal dialog was opened for a failure that should only toast")

    monkeypatch.setattr(QMessageBox, "information", staticmethod(_boom))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_boom))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(_boom))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(_boom))


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
    win.show()
    app.processEvents()
    yield win
    win.ctrl.stop()
    win.close()


# ---------------------------------------------------------------------------
# Controller-level: weather fetch and geolocation failures are relayed via
# the new on_error callback instead of only being logged.
# ---------------------------------------------------------------------------


def test_weather_fetch_failure_calls_on_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    import orbitrx.ui.controller as controller_mod

    errors = []
    ctrl = OrbitRxController(on_error=errors.append)
    ctrl.cfg.data["offline_cache_enabled"] = False
    monkeypatch.setattr(
        controller_mod, "fetch_space_weather_data", lambda: (_ for _ in ()).throw(RuntimeError("NOAA down"))
    )

    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)

    assert errors, "weather fetch failure never reached on_error"
    assert "NOAA down" in errors[0]


def test_geolocation_failure_calls_on_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    import orbitrx.ui.controller as controller_mod

    errors = []
    ctrl = OrbitRxController(on_error=errors.append)
    ctrl.cfg.data["home_lat"] = None
    ctrl.cfg.data["home_lon"] = None
    ctrl.cfg.data["ip_geolocation_enabled"] = True

    def boom(*_a, **_k):
        raise OSError("network unreachable")

    monkeypatch.setattr(controller_mod.urllib.request, "urlopen", boom)

    ctrl.refresh_location()
    ctrl._location_thread.join(timeout=5)

    assert errors, "geolocation failure never reached on_error"
    assert ctrl.state.location_source == "unset"


def test_weather_fetch_failure_toasts_once_per_episode(tmp_path, monkeypatch):
    """P5-r6 (e): a second, third, ... consecutive fetch failure must not
    toast again -- the no-data banner already says so for as long as the
    episode lasts. Only the failure that *starts* a new episode (the first
    one after a success, or the very first attempt) toasts; a live success
    in between resets the episode so the next failure toasts again."""
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    import orbitrx.ui.controller as controller_mod

    errors = []
    ctrl = OrbitRxController(on_error=errors.append)
    ctrl.cfg.data["offline_cache_enabled"] = False
    monkeypatch.setattr(
        controller_mod, "fetch_space_weather_data", lambda: (_ for _ in ()).throw(RuntimeError("NOAA down"))
    )

    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)
    assert len(errors) == 1, errors

    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)
    assert len(errors) == 1, "a second consecutive failure toasted again"

    monkeypatch.setattr(
        controller_mod,
        "fetch_space_weather_data",
        lambda: {"kp_index": 2.0, "flux": 110.0, "time_utc": "2026-01-01 00:00"},
    )
    monkeypatch.setattr(controller_mod, "fetch_solar_xml", lambda: None)
    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)
    assert len(errors) == 1, "a successful fetch must never toast"
    assert ctrl.state.weather_last_fetch_ok is True

    monkeypatch.setattr(
        controller_mod, "fetch_space_weather_data", lambda: (_ for _ in ()).throw(RuntimeError("NOAA down again"))
    )
    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)
    assert len(errors) == 2, "the first failure of a new episode (after a success) must toast"


def test_weather_fetch_success_does_not_call_on_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    import orbitrx.ui.controller as controller_mod

    errors = []
    ctrl = OrbitRxController(on_error=errors.append)
    monkeypatch.setattr(
        controller_mod,
        "fetch_space_weather_data",
        lambda: {"kp_index": 2.0, "flux": 110.0, "time_utc": "2026-01-01 00:00"},
    )
    monkeypatch.setattr(controller_mod, "fetch_solar_xml", lambda: None)

    ctrl.fetch_weather()
    ctrl._weather_thread.join(timeout=5)

    assert errors == []


# ---------------------------------------------------------------------------
# UI-level wiring: each previously-silent path now shows a toast and opens
# no modal dialog.
# ---------------------------------------------------------------------------


def test_controller_error_callback_shows_toast(window, no_modals):
    window._on_controller_error("Weather update failed: boom")
    assert window._toasts.is_visible()
    assert "Weather update failed" in window._toasts.current_text()


def test_spot_alert_shows_toast(window, no_modals):
    """P5-r6 (a): the "Alerts / No active alerts" side-panel box is gone
    (not in SPEC §9), but a DX-spot alert (orbitrx/spots/alerts.py's
    evaluate_alerts(), relayed through controller._spot_alert) must still
    reach the user -- now as an in-app toast instead of only a list item."""
    from PySide6.QtWidgets import QApplication

    window.ctrl._spot_alert("Local Band Activity", "5 spots are active within 50 miles of HOME.")
    # _on_alert is wrapped by the same queued _UiInvoker every other
    # controller callback uses (P1), so it only actually runs on the next
    # event-loop turn, not synchronously.
    _pump(QApplication.instance(), 0.2)
    assert window._toasts.is_visible()
    assert "Local Band Activity" in window._toasts.current_text()
    assert "5 spots" in window._toasts.current_text()


def test_cluster_reconnect_after_connected_shows_toast(window, no_modals):
    window._set_cluster("connected")
    assert not window._toasts.is_visible()
    window._set_cluster("reconnecting")
    assert window._toasts.is_visible()
    assert "reconnecting" in window._toasts.current_text() or "disconnected" in window._toasts.current_text()


def test_cluster_initial_connect_attempt_does_not_toast(window, no_modals):
    window._set_cluster("connecting")
    window._set_cluster("reconnecting")
    assert not window._toasts.is_visible()


def test_map_load_failure_shows_toast(window, no_modals):
    window._on_map_load_failed(FileNotFoundError("basemap.jpg missing"))
    assert window._toasts.is_visible()
    assert "basemap.jpg missing" in window._toasts.current_text()


def test_update_check_error_shows_toast(window, no_modals):
    window._on_update_check_error("could not reach GitHub")
    assert window._toasts.is_visible()
    assert "could not reach GitHub" in window._toasts.current_text()


def test_export_json_failure_shows_toast_not_modal(window, no_modals, monkeypatch):
    monkeypatch.setattr(window.ctrl, "export_json", lambda: (_ for _ in ()).throw(OSError("disk full")))
    window._export_json()
    assert window._toasts.is_visible()
    assert "disk full" in window._toasts.current_text()


def test_export_dx_failure_shows_toast_not_modal(window, no_modals, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("dx.csv", "")))
    monkeypatch.setattr(
        window.ctrl.store, "export_dx_csv", lambda path: (_ for _ in ()).throw(OSError("disk full"))
    )
    window._export_dx()
    assert window._toasts.is_visible()


def test_save_fig_failure_shows_toast_not_modal(window, no_modals, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("history.png", "")))

    class _BoomFig:
        def savefig(self, *_a, **_k):
            raise OSError("disk full")

    window._save_fig(_BoomFig())
    assert window._toasts.is_visible()


def test_settings_cat_test_failure_shows_toast_and_rig_status(window, no_modals, monkeypatch):
    """A failed Test CAT stays inline. It does not also raise a toast."""
    monkeypatch.setattr(
        window.ctrl.cat, "probe",
        lambda **_kwargs: "error\nCould not open serial port",
    )

    dlg = window._build_settings_dialog()
    dlg.show()
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance()
    dlg.test_cat_btn.click()
    _pump(qapp, 1.0)

    assert not dlg._toasts.is_visible()
    assert "Could not open serial port" in dlg.test_cat_result.text()
    assert "error" in window._status_rig_lbl.text().lower() or "fail" in window._status_rig_lbl.text().lower()
    # A port scan can select a different port than the snapshot. Discard that
    # without opening the unsaved-changes prompt, which would block the test.
    dlg._snapshot = dlg._collect()
    dlg.reject()


def test_rig_wizard_cat_test_failure_shows_toast_and_calls_on_rig_status(window, no_modals, monkeypatch):
    from orbitrx.ui.rig_wizard import RigWizardDialog
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(window.ctrl.cat, "tune", lambda freq, confirm=None: "Could not open serial port")

    seen = []
    dlg = RigWizardDialog(window.ctrl.cfg, window.ctrl.cat, window, on_rig_status=lambda ok, detail: seen.append((ok, detail)))
    dlg.show()
    qapp = QApplication.instance()
    dlg._test_cat()
    _pump(qapp, 1.0)

    assert dlg._toasts.is_visible()
    assert seen and seen[-1][0] is False
    dlg.reject()


# ---------------------------------------------------------------------------
# P3: destroying the window must not crash a still-outstanding toast timer or
# a worker-thread result queued for delivery via _UiInvoker.
# ---------------------------------------------------------------------------


def test_destroying_window_drops_pending_toast_and_queued_status_update(tmp_path, monkeypatch, capfd):
    """Regression for repeated "libshiboken: Internal C++ object ... already
    deleted" RuntimeErrors seen in CI. The main window's own _UiInvoker used
    to have no QObject parent, so it outlived the window (kept alive only by
    a plain Python reference) -- a worker-thread result arriving after the
    window was torn down (the same forced, synchronous `shiboken6.delete()`
    the suite's autouse teardown fixture uses once a background thread
    outlasts its join timeout) would still fire and touch widgets -- the
    toast's QLabel, a status label -- whose C++ objects were already gone.
    _UiInvoker is now parented to its window, so Qt drops any such
    still-queued delivery together with the window instead of running it."""
    import shiboken6

    monkeypatch.chdir(tmp_path)
    from PySide6.QtWidgets import QApplication

    import orbitrx.spots.service as svc
    monkeypatch.setattr(svc.SpotsService, "start", lambda self: None)
    import orbitrx.dx as dx
    monkeypatch.setattr(dx.DxClusterService, "start", lambda self: None)
    from orbitrx.ui.controller import OrbitRxController
    monkeypatch.setattr(OrbitRxController, "refresh_location", lambda self: None)
    import orbitrx.ui.controller as controller_mod

    app = QApplication.instance() or QApplication([])
    from orbitrx.ui.qt_app import QtOrbitRxApplication
    win = QtOrbitRxApplication()
    win.show()
    app.processEvents()

    # A toast whose auto-dismiss timer is still outstanding when the window
    # is destroyed below.
    win._toasts._duration_ms = 50
    win._toasts.show_toast("about to go away", kind="info")
    assert win._toasts.is_visible()

    # Settle the startup map load first so only the weather fetch below is
    # in flight -- this test is about that race, not an unrelated one.
    if win._map_load_thread is not None:
        win._map_load_thread.join(timeout=60.0)
    win.map_widget.join_rebuild_thread(timeout=60.0)
    app.processEvents()

    # A weather-fetch worker whose result (a queued call into
    # _refresh_labels_and_map, which sets label text) is still pending.
    release = threading.Event()

    def slow_fetch():
        release.wait(timeout=60.0)
        return {"kp_index": 2.0, "flux": 110.0, "time_utc": "2026-01-01 00:00"}

    monkeypatch.setattr(controller_mod, "fetch_space_weather_data", slow_fetch)
    monkeypatch.setattr(controller_mod, "fetch_solar_xml", lambda: None)
    win.ctrl.fetch_weather()
    weather_thread = win.ctrl._weather_thread

    win.ctrl.stop()
    # Same forcible, synchronous deletion the suite's own autouse
    # _cleanup_orbitrx_qt_windows fixture falls back to (tests/conftest.py)
    # when a straggler worker outlasts its join timeout -- the toast's QLabel
    # and the window's status labels are gone the instant this returns.
    shiboken6.delete(win)

    # Only now does the weather worker's queued delivery actually arrive --
    # the thread has already finished by the join() below, so this is just
    # pumping the event loop to flush whatever it already posted, not
    # waiting on further work to complete.
    release.set()
    weather_thread.join(timeout=60.0)
    assert not weather_thread.is_alive()
    _pump(app, 0.5)

    out, err = capfd.readouterr()
    assert "already deleted" not in err, err
    assert "already deleted" not in out, out
