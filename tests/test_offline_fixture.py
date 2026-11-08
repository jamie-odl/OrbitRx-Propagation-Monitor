import os

from orbitrx.offline import offline_fixture
from orbitrx.ui.controller import OrbitRxController


def test_capture_env_disables_live_services(monkeypatch, tmp_path):
    monkeypatch.setenv("ORBITRX_CAPTURE_DIR", str(tmp_path / "shots"))
    monkeypatch.chdir(tmp_path)
    assert offline_fixture()
    ctrl = OrbitRxController()
    started = {"dx": 0, "spots": 0}
    monkeypatch.setattr(ctrl._dx, "start", lambda: started.__setitem__("dx", 1))
    monkeypatch.setattr(ctrl.spots, "start", lambda: started.__setitem__("spots", 1))
    ctrl.start()
    assert started == {"dx": 0, "spots": 0}

    def explode():
        raise AssertionError("live weather fetch")

    monkeypatch.setattr("orbitrx.ui.controller.fetch_space_weather_data", explode)
    monkeypatch.setattr("orbitrx.ui.controller.fetch_solar_xml", explode)
    ctrl.fetch_weather()
    assert ctrl.state.kp_index == 2.0
    assert ctrl.state.flux == 120.0


def test_offline_fixture_is_off_by_default(monkeypatch):
    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)
    monkeypatch.delenv("ORBITRX_OFFLINE_FIXTURE", raising=False)
    assert offline_fixture() is False
    assert "ORBITRX_CAPTURE_DIR" not in os.environ or os.environ.get("ORBITRX_CAPTURE_DIR") == ""
