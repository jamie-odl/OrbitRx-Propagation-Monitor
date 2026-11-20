"""Phase 1 threading/responsiveness fixes: batched config saves, Test CAT off
the UI thread (main window + rig wizard), map rebuilds off the UI thread with
coalescing, and the history-plot query off the UI thread. Each test proves the
UI thread stays responsive (a 5ms heartbeat keeps ticking) while the slow work
runs, not just that the feature "works" eventually.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

MAX_HEARTBEAT_GAP_MS = 100.0


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """RigWizardDialog pops a modal QMessageBox.information() on a successful
    Test CAT; a real click will never come in this offscreen test process, so
    it would hang forever waiting for one (same reason tools/ui_timing.py
    suppresses it)."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))


def _max_heartbeat_gap_ms(app, action, settle: float = 0.02, follow: float = 1.5, heartbeat_ms: int = 5) -> float:
    """Longest gap (ms) between ticks of a heartbeat_ms QTimer while `action()`
    runs and for `follow` seconds afterward -- same technique as
    tools/ui_timing.py's measure_ui_block, duplicated locally so this test
    doesn't depend on a CLI tool's internals."""
    from PySide6.QtCore import QTimer

    ticks: list[float] = []
    timer = QTimer()
    timer.setInterval(heartbeat_ms)
    timer.timeout.connect(lambda: ticks.append(time.perf_counter()))
    timer.start()
    try:
        deadline = time.monotonic() + settle
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.002)
        ticks.append(time.perf_counter())
        action()
        ticks.append(time.perf_counter())
        deadline = time.monotonic() + follow
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.002)
    finally:
        timer.stop()
    ticks.sort()
    if len(ticks) < 2:
        return 0.0
    return max((b - a) * 1000.0 for a, b in zip(ticks[:-1], ticks[1:]))


def _pump(app, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)


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


# ---------------------------------------------------------------------------
# 1. Batched config saves
# ---------------------------------------------------------------------------


def test_set_many_updates_in_memory_without_saving(tmp_path):
    from orbitrx.config import AppConfig

    cfg = AppConfig(path=tmp_path / "c.json").load()
    saved_before = cfg.path.read_text(encoding="utf-8")
    cfg.set_many({"spots_callsign": "W1AW", "cat_baud": 19200})
    assert cfg.get("spots_callsign") == "W1AW"
    assert cfg.get("cat_baud") == 19200
    assert cfg.path.read_text(encoding="utf-8") == saved_before  # no write yet


def test_flush_writes_once_after_set_many(tmp_path, monkeypatch):
    from orbitrx.config import AppConfig

    cfg = AppConfig(path=tmp_path / "c.json").load()
    calls = []
    orig_save = cfg.save
    monkeypatch.setattr(cfg, "save", lambda: (calls.append(True), orig_save())[-1])

    cfg.set_many({"spots_callsign": "W1AW", "cat_baud": 19200, "dx_cluster_callsign": "G0ABC"})
    cfg.flush()
    assert len(calls) == 1

    reloaded = AppConfig(path=cfg.path).load()
    assert reloaded.get("spots_callsign") == "W1AW"
    assert reloaded.get("cat_baud") == 19200
    assert reloaded.get("dx_cluster_callsign") == "G0ABC"


def test_flush_is_a_noop_when_nothing_pending(tmp_path, monkeypatch):
    from orbitrx.config import AppConfig

    cfg = AppConfig(path=tmp_path / "c.json").load()
    calls = []
    monkeypatch.setattr(cfg, "save", lambda: calls.append(True))
    cfg.flush()
    assert calls == []


def test_set_is_unchanged_single_immediate_write(tmp_path, monkeypatch):
    """Backward compatibility: existing callers of cfg.set() still get exactly
    one save() per call, as before."""
    from orbitrx.config import AppConfig

    cfg = AppConfig(path=tmp_path / "c.json").load()
    calls = []
    orig_save = cfg.save
    monkeypatch.setattr(cfg, "save", lambda: (calls.append(True), orig_save())[-1])
    cfg.set("spots_callsign", "W1AW")
    assert len(calls) == 1
    assert cfg.get("spots_callsign") == "W1AW"


def test_apply_settings_dialog_writes_config_exactly_once(window, monkeypatch):
    import orbitrx.config as config_mod

    dlg = window._build_settings_dialog()
    dlg.fields["spots_callsign"].setText("W1AW")

    calls = []
    orig_save = config_mod.AppConfig.save

    def counting_save(self):
        calls.append(True)
        return orig_save(self)

    monkeypatch.setattr(config_mod.AppConfig, "save", counting_save)
    window._apply_settings_dialog(dlg)
    assert len(calls) == 1
    assert window.ctrl.cfg.get("spots_callsign") == "W1AW"


# ---------------------------------------------------------------------------
# 2. CAT tune off the UI thread (main window Settings + rig wizard)
# ---------------------------------------------------------------------------


def _slow_tune(delay: float, result: str = "Sent CAT: 14.2 MHz"):
    def tune(freq, confirm=None):
        time.sleep(delay)
        return result

    return tune


def _slow_probe(delay: float, result: str = "ok\nRead 14.200000 MHz"):
    def probe(*_args, **_kwargs):
        time.sleep(delay)
        return result

    return probe


def test_settings_test_cat_does_not_block_ui_thread(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(window.ctrl.cat, "probe", _slow_probe(0.3))
    dlg = window._build_settings_dialog(initial_page="Rig")
    app = QApplication.instance()

    gap = _max_heartbeat_gap_ms(app, dlg.test_cat_btn.click, follow=0.8)
    assert gap < MAX_HEARTBEAT_GAP_MS

    _pump(app, 0.5)
    assert dlg.test_cat_btn.isEnabled() is True


def test_settings_test_cat_cancel_ignores_late_result(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(window.ctrl.cat, "probe", _slow_probe(0.3))
    dlg = window._build_settings_dialog(initial_page="Rig")
    app = QApplication.instance()

    dlg.test_cat_btn.click()
    assert dlg.test_cat_btn.isEnabled() is False
    worker_thread = dlg._cat_runner._thread
    dlg.test_cat_cancel_btn.click()
    assert dlg.test_cat_btn.isEnabled() is True
    assert dlg.test_cat_result.text() == "Cancelled"

    # The worker is still sleeping; its eventual result must be dropped, not
    # overwrite the "Cancelled" status or crash on a since-cleaned-up runner.
    # Join it deterministically instead of guessing a sleep margin, then pump
    # once to deliver its (now-stale) queued result.
    worker_thread.join(timeout=60.0)
    assert not worker_thread.is_alive()
    app.processEvents()
    assert dlg.test_cat_result.text() == "Cancelled"


def test_settings_test_cat_timeout(window, monkeypatch):
    import orbitrx.ui.qt_app as qt_app
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(qt_app, "CAT_TEST_TIMEOUT_S", 0.05)
    monkeypatch.setattr(window.ctrl.cat, "probe", _slow_probe(2.0))
    dlg = window._build_settings_dialog(initial_page="Rig")
    app = QApplication.instance()

    dlg.test_cat_btn.click()
    # deadline is only a hang guard -- the timeout itself fires at 0.05s, so
    # this exits almost immediately on any runner.
    deadline = time.time() + 60.0
    while dlg.test_cat_btn.isEnabled() is False and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert dlg.test_cat_btn.isEnabled() is True
    assert "Timed out" in dlg.test_cat_result.text()


def test_rig_wizard_test_cat_does_not_block_ui_thread(window, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from orbitrx.ui.rig_wizard import RigWizardDialog

    monkeypatch.setattr(window.ctrl.cat, "tune", _slow_tune(0.3))
    dlg = RigWizardDialog(window.ctrl.cfg, window.ctrl.cat, window)
    app = QApplication.instance()

    gap = _max_heartbeat_gap_ms(app, dlg._test_cat, follow=0.8)
    assert gap < MAX_HEARTBEAT_GAP_MS

    dlg._cat_runner._thread.join(timeout=60.0)
    assert not dlg._cat_runner._thread.is_alive()
    app.processEvents()
    assert dlg.test_btn.isEnabled() is True
    assert "Sent CAT" in dlg.status_text.text()


def test_rig_wizard_test_cat_cancel_and_timeout(window, monkeypatch):
    import orbitrx.ui.rig_wizard as rig_wizard
    from PySide6.QtWidgets import QApplication
    from orbitrx.ui.rig_wizard import RigWizardDialog

    app = QApplication.instance()

    # Cancel.
    monkeypatch.setattr(window.ctrl.cat, "tune", _slow_tune(0.3))
    dlg = RigWizardDialog(window.ctrl.cfg, window.ctrl.cat, window)
    dlg._test_cat()
    assert dlg.test_btn.isEnabled() is False
    worker_thread = dlg._cat_runner._thread
    dlg.cancel_test_btn.click()
    assert dlg.test_btn.isEnabled() is True
    assert dlg.status_text.text() == "Cancelled"
    # Join the still-sleeping worker deterministically, then pump once to
    # deliver its (now-stale) queued result and confirm it's dropped.
    worker_thread.join(timeout=60.0)
    assert not worker_thread.is_alive()
    app.processEvents()
    assert dlg.status_text.text() == "Cancelled"  # late result dropped

    # Timeout.
    monkeypatch.setattr(rig_wizard, "CAT_TEST_TIMEOUT_S", 0.05)
    monkeypatch.setattr(window.ctrl.cat, "tune", _slow_tune(2.0))
    dlg2 = RigWizardDialog(window.ctrl.cfg, window.ctrl.cat, window)
    dlg2._test_cat()
    # deadline is only a hang guard -- the timeout itself fires at 0.05s, so
    # this exits almost immediately on any runner.
    deadline = time.time() + 60.0
    while dlg2.test_btn.isEnabled() is False and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert dlg2.test_btn.isEnabled() is True
    assert "Timed out" in dlg2.status_text.text()


def test_cat_test_survives_dialog_deletion_before_worker_finishes(window, monkeypatch):
    """No crash on deleted widgets: the dialog (and its CatTestRunner/invoker)
    can be torn down while a slow tune() is still sleeping on its thread."""
    from PySide6.QtWidgets import QApplication
    from orbitrx.ui.rig_wizard import RigWizardDialog

    monkeypatch.setattr(window.ctrl.cat, "tune", _slow_tune(0.3))
    dlg = RigWizardDialog(window.ctrl.cfg, window.ctrl.cat, window)
    app = QApplication.instance()

    dlg._test_cat()
    worker_thread = dlg._cat_runner._thread
    dlg.deleteLater()
    app.processEvents()
    # The worker thread is still sleeping (0.3s) when its dialog is gone; join
    # it deterministically and pump once to deliver its result -- this must
    # not raise.
    worker_thread.join(timeout=60.0)
    assert not worker_thread.is_alive()
    app.processEvents()


# ---------------------------------------------------------------------------
# 3. Map rebuild off the UI thread, coalesced
# ---------------------------------------------------------------------------


def test_map_rebuild_does_not_block_ui_thread(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    def slow_build_scene(self, state, layers, spots, coordinates):
        time.sleep(0.2)
        return orig_build_scene(state, layers, spots, coordinates)

    orig_build_scene = window.renderer.build_scene
    monkeypatch.setattr(type(window.renderer), "build_scene", slow_build_scene)
    app = QApplication.instance()

    gap = _max_heartbeat_gap_ms(app, window._refresh_map, follow=0.8)
    assert gap < MAX_HEARTBEAT_GAP_MS


def test_weather_and_dx_bursts_coalesce_into_at_most_two_rebuilds(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    # Neutralize the deferred startup callback (QTimer.singleShot(200, ...)):
    # it would otherwise sneak in an unrelated extra rebuild while this test
    # pumps the event loop, same reason test_ui_smoke.py's slider-drag test
    # disables it.
    window._startup = lambda: None
    starts = []
    orig_start = window.map_widget._start_rebuild

    def counting_start(gen, args):
        starts.append(gen)
        return orig_start(gen, args)

    monkeypatch.setattr(window.map_widget, "_start_rebuild", counting_start)
    app = QApplication.instance()
    starts.clear()

    gap = _max_heartbeat_gap_ms(
        app,
        lambda: [window._schedule_map_rebuild() for _ in range(10)],
        follow=1.0,
    )
    assert gap < MAX_HEARTBEAT_GAP_MS
    assert len(starts) <= 2


def test_spot_beep_burst_coalesces_through_the_same_debounce(window, monkeypatch):
    window._startup = lambda: None  # see comment above
    starts = []
    orig_start = window.map_widget._start_rebuild

    def counting_start(gen, args):
        starts.append(gen)
        return orig_start(gen, args)

    monkeypatch.setattr(window.map_widget, "_start_rebuild", counting_start)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    starts.clear()

    for _ in range(10):
        window._spot_beep({"from": "W1AW", "to": "G0ABC", "freq": 14.2, "time": time.time()})
    _pump(app, 1.0)
    assert len(starts) <= 2


# ---------------------------------------------------------------------------
# 4. History plot query off the UI thread
# ---------------------------------------------------------------------------


def _slow_query(delay: float, rows: list[dict]):
    def query_propagation(q):
        time.sleep(delay)
        return rows

    return query_propagation


_SAMPLE_ROWS = [
    {"ts": "2026-11-04T19:00:00+00:00", "kp": 2.0, "flux": 110},
    {"ts": "2026-11-04T20:00:00+00:00", "kp": 2.2, "flux": 112},
    {"ts": "2026-11-04T21:00:00+00:00", "kp": 2.4, "flux": 114},
]


def test_history_plot_shows_loading_state_and_does_not_block(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(window.ctrl.store, "query_propagation", _slow_query(0.3, _SAMPLE_ROWS))
    app = QApplication.instance()

    gap = _max_heartbeat_gap_ms(app, window._refresh_plot_tab, settle=0.01, follow=0.1)
    assert gap < MAX_HEARTBEAT_GAP_MS
    assert window.plot_placeholder.text() == "Loading…"

    window._plot_query_thread.join(timeout=60.0)
    assert not window._plot_query_thread.is_alive()
    # deadline is only a hang guard: the worker has already joined, this just
    # waits for its queued delivery to be processed.
    deadline = time.time() + 60.0
    while window.plot_container.count() < 2 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.plot_container.count() == 2


def test_history_plot_drops_a_stale_result(window, monkeypatch):
    """Firing Refresh twice in a row must only ever apply the second (newer)
    result -- the first query's eventual rows are superseded and dropped."""
    from PySide6.QtWidgets import QApplication

    calls = {"n": 0}

    def query_propagation(q):
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(0.3)
            return [{"ts": "2026-11-01T00:00:00+00:00", "kp": 9.0, "flux": 300}]
        return _SAMPLE_ROWS

    monkeypatch.setattr(window.ctrl.store, "query_propagation", query_propagation)
    app = QApplication.instance()

    window._refresh_plot_tab()
    first_gen = window._plot_request_gen
    first_thread = window._plot_query_thread  # captured before the second call overwrites it
    window._refresh_plot_tab()
    second_gen = window._plot_request_gen
    assert second_gen != first_gen

    deadline = time.time() + 60.0
    while getattr(window, "_plot_last_handled_gen", None) != second_gen and time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)

    # Let the first (slow, stale) query's result arrive too -- joined
    # deterministically instead of guessing a sleep margin over its 0.3s
    # delay, then pumped once to deliver its (now-stale) queued result.
    first_thread.join(timeout=60.0)
    assert not first_thread.is_alive()
    app.processEvents()
    canvas = window.plot_container.itemAt(0).widget()
    ax = canvas.figure.get_axes()[0]
    assert ax.get_ylim() == (0.0, 9.0)  # the dual-axis chart from the second query
    kp_line = ax.get_lines()[0]
    assert list(kp_line.get_ydata()) == pytest.approx([2.0, 2.2, 2.4])
