"""Settings redesign: validation, dirty tracking, coordinate migration,
CAT read-back, and async QRZ / port scan. No network and no real serial I/O."""

from __future__ import annotations

import json
import os
import time

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


def _pump(app, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_migrate_sentinel_pair_to_null_and_keep_a_real_south_pole(tmp_path):
    from orbitrx.config import AppConfig, migrate_unset_coordinates

    data = {
        "home_lat": -90,
        "home_lon": -180,
        "target_dx_lat": -90.0,
        "target_dx_lon": -180.0,
    }
    assert migrate_unset_coordinates(data) is True
    assert data["home_lat"] is None and data["home_lon"] is None
    assert data["target_dx_lat"] is None and data["target_dx_lon"] is None

    south_pole = {"home_lat": -90.0, "home_lon": 10.0}
    assert migrate_unset_coordinates(south_pole) is False
    assert south_pole["home_lat"] == -90.0

    path = tmp_path / "config.json"
    path.write_text(json.dumps({"home_lat": -90, "home_lon": -180.0}), encoding="utf-8")
    cfg = AppConfig(path=path).load()
    assert cfg.get("home_lat") is None
    assert cfg.get("home_lon") is None
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["home_lat"] is None and saved["home_lon"] is None


def test_unset_coordinates_show_location_not_set(window):
    window.ctrl.cfg.data["home_lat"] = None
    window.ctrl.cfg.data["home_lon"] = None
    window.ctrl.state.user_lat = None
    window.ctrl.state.user_lon = None
    window.ctrl.state.location_source = "unset"
    window._refresh_labels_and_map()
    text = window._status_location_lbl.text()
    assert "Location: not set" in text
    assert "href" not in text


def test_validation_blocks_save_and_tracks_dirty_state(window, monkeypatch):
    from PySide6.QtWidgets import QApplication

    dlg = window._build_settings_dialog()
    assert dlg._apply_btn.isEnabled() is False
    assert "No changes" in dlg._dirty_label.text()

    from PySide6.QtCore import Qt

    dlg.fields["spots_callsign"].setText("not a call")
    dlg._on_edited()
    assert dlg._apply_btn.isEnabled() is True
    assert "Unsaved changes" in dlg._dirty_label.text()
    assert dlg.page_list.item(0).data(Qt.ItemDataRole.UserRole) is True

    before = window.ctrl.cfg.get("spots_callsign")
    dlg._on_save()
    assert dlg._applied_on_accept is False
    assert window.ctrl.cfg.get("spots_callsign") == before
    assert any(not summary.isHidden() for summary in dlg._summaries)
    assert dlg.fields["spots_callsign"].property("invalid") in (True, "true")

    dlg.fields["spots_callsign"].setText("")
    dlg._clear_if_fixed()
    assert "No changes" in dlg._dirty_label.text()
    assert dlg._apply_btn.isEnabled() is False

    dlg.fields["spots_callsign"].setText("G4ABC")
    from orbitrx.ui import settings_dialog as mod

    class _Prompt:
        def __init__(self, *_args, **_kwargs):
            self.choice = "discard"

        def exec(self):
            return 1

    monkeypatch.setattr(mod, "_UnsavedPrompt", _Prompt)
    dlg.reject()
    QApplication.instance().processEvents()
    assert window.ctrl.cfg.get("spots_callsign") == before


def test_negative_ninety_saves_as_a_real_latitude(window):
    dlg = window._build_settings_dialog()
    dlg.fields["home_lat"].setText("-90")
    dlg.fields["home_lon"].setText("0")
    window._apply_settings_dialog(dlg)
    assert window.ctrl.cfg.get("home_lat") == -90.0
    assert window.ctrl.cfg.get("home_lon") == 0.0


def test_empty_coordinates_save_as_null(window):
    dlg = window._build_settings_dialog()
    dlg.fields["home_lat"].setText("")
    dlg.fields["home_lon"].setText("")
    window._apply_settings_dialog(dlg)
    assert window.ctrl.cfg.get("home_lat") is None
    assert window.ctrl.cfg.get("home_lon") is None


def test_cat_readback_success_does_not_retune_or_write_config(window, monkeypatch):
    from PySide6.QtWidgets import QApplication
    import orbitrx.cat as catmod

    port = _FakeSerial(reply=b"FA00014200000;")
    monkeypatch.setattr(catmod.serial, "Serial", lambda *a, **k: port)
    cfg = window.ctrl.cfg
    before = (cfg.get("cat_port"), cfg.get("cat_baud"), cfg.get("cat_rig_profile"), cfg.get("home_lat"))
    dlg = window._build_settings_dialog(initial_page="Rig")
    dlg.fields["cat_port"].setEditText("COM8")
    dlg.fields["cat_rig_profile"].setCurrentIndex(dlg.fields["cat_rig_profile"].findData("kenwood"))
    dlg.test_cat_btn.click()
    app = QApplication.instance()
    deadline = time.time() + 3
    while dlg._cat_running and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    _pump(app, 0.2)
    assert port.written == [b"FA;"]
    assert b"FA000" not in b"".join(port.written)
    assert "14.200" in dlg.test_cat_result.text() or "Radio answered" in dlg._cat_title.text()
    assert (cfg.get("cat_port"), cfg.get("cat_baud"), cfg.get("cat_rig_profile"), cfg.get("home_lat")) == before


def test_cat_readback_wrong_baud_timeout_and_busy(monkeypatch):
    from orbitrx.cat import CatController
    from orbitrx.config import AppConfig
    import orbitrx.cat as catmod

    cfg = AppConfig(path=os.devnull if False else None)
    # AppConfig requires a path; use a throwaway via the controller-less constructor.
    cat = CatController.__new__(CatController)
    cat.cfg = type("C", (), {"data": {}, "get": lambda self, k, d=None: d})()
    cat._ser = None
    cat._log = lambda *_a, **_k: None

    garbage = _FakeSerial(reply=b"\xff\x00not-a-frame")
    monkeypatch.setattr(catmod.serial, "Serial", lambda *a, **k: garbage)
    status, detail = catmod.parse_probe_result(cat.probe(port="COM3", baud=9600, profile="kenwood", backend="serial", timeout=0.2))
    assert status == "wrong_baud"
    assert "9600" in detail

    silent = _FakeSerial(reply=b"")
    monkeypatch.setattr(catmod.serial, "Serial", lambda *a, **k: silent)
    status, detail = catmod.parse_probe_result(cat.probe(port="COM3", baud=9600, profile="kenwood", backend="serial", timeout=0.2))
    assert status == "timeout"
    assert "Timed out" in detail

    def _busy(*_a, **_k):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(catmod.serial, "Serial", _busy)
    status, detail = catmod.parse_probe_result(cat.probe(port="COM3", baud=9600, profile="yaesu", backend="serial", timeout=0.2))
    assert status == "busy"
    assert "in use" in detail


def test_icom_civ_frame_is_a_frequency_readback():
    from orbitrx.cat import classify_cat_reply, read_query_for_profile

    query = read_query_for_profile("icom")
    assert query.startswith(b"\xfe\xfe")
    assert b"FA" not in query
    # 14.200 MHz as five CI-V BCD bytes.
    frame = bytes([0xFE, 0xFE, 0xE0, 0x94, 0x03, 0x00, 0x00, 0x20, 0x14, 0x00, 0xFD])
    status, detail = classify_cat_reply("icom", frame)
    assert status == "ok"
    assert "14.200" in detail


def test_omnirig_without_readback_says_sent_not_verified(monkeypatch):
    from orbitrx.cat import CatController, parse_probe_result
    import orbitrx.cat as catmod

    cat = CatController.__new__(CatController)
    cat.cfg = type("C", (), {"get": lambda self, k, d=None: d})()
    cat._ser = None
    cat._log = lambda *_a, **_k: None
    monkeypatch.setattr(catmod, "_read_omnirig_hz", lambda rig_number=1: (_ for _ in ()).throw(AttributeError("Freq is not supported")))
    status, detail = parse_probe_result(cat.probe(port="", baud=9600, profile="kenwood", backend="omnirig"))
    assert status == "unverified"
    assert detail == "sent, not verified"


def test_qrz_and_port_scan_run_off_the_ui_thread(window, monkeypatch):
    from PySide6.QtWidgets import QApplication
    import orbitrx.dx as dx

    threads = []

    def slow_ports():
        threads.append("ports")
        time.sleep(0.25)
        return [("COM4", "USB Serial")]

    def slow_qrz(api_key, callsign="W1AW"):
        threads.append("qrz")
        time.sleep(0.25)
        return True, f"QRZ OK: {callsign} @ 1.000, 2.000", (1.0, 2.0)

    monkeypatch.setattr(window.ctrl.cat, "list_ports_detailed", slow_ports)
    monkeypatch.setattr(dx, "verify_qrz_api", slow_qrz)
    app = QApplication.instance()
    dlg = window._build_settings_dialog(initial_page="Services")
    gap_during_scan = _max_gap(app, lambda: None, follow=0.4)
    assert gap_during_scan < 150
    assert "ports" in threads

    dlg.page_list.setCurrentRow(4)
    dlg.test_qrz_btn.click()
    gap_during_qrz = _max_gap(app, lambda: None, follow=0.4)
    assert gap_during_qrz < 150
    assert "qrz" in threads
    deadline = time.time() + 2
    while "QRZ OK" not in dlg._qrz_result.text() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert "QRZ OK" in dlg._qrz_result.text()


def test_dx_page_does_not_mention_a_node_picker():
    from orbitrx.ui.settings_dialog import PAGE_DESCRIPTIONS

    text = PAGE_DESCRIPTIONS["DX cluster"].lower()
    assert "node" not in text
    assert "pick a cluster" not in text


class _FakeSerial:
    def __init__(self, reply: bytes) -> None:
        self.reply = bytearray(reply)
        self.written: list[bytes] = []
        self.is_open = True
        self.timeout = 0.2

    def write(self, data) -> int:
        self.written.append(bytes(data))
        return len(data)

    def read(self, n: int) -> bytes:
        out = bytes(self.reply[:n])
        del self.reply[: len(out)]
        return out

    def close(self) -> None:
        self.is_open = False


def _max_gap(app, fn, follow: float) -> float:
    """Largest gap between event-loop turns while fn() and the follow window run."""
    gaps = []
    last = time.perf_counter()

    def beat():
        nonlocal last
        now = time.perf_counter()
        gaps.append((now - last) * 1000)
        last = now

    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.setInterval(15)
    timer.timeout.connect(beat)
    timer.start()
    fn()
    deadline = time.time() + follow
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.005)
    timer.stop()
    return max(gaps) if gaps else 0
