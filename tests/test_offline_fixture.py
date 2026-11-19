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


def test_offline_fixture_kp_forecast_matches_current_kp_decimal_precision(monkeypatch, tmp_path):
    """P5-r8/SPEC §10: Kp and its forecast must use the same precision --
    the fixture's kp_forecast used to be a bare "2" next to "Kp: 2.0",
    reading as if the two were formatted inconsistently."""
    monkeypatch.setenv("ORBITRX_CAPTURE_DIR", str(tmp_path / "shots"))
    monkeypatch.chdir(tmp_path)
    ctrl = OrbitRxController()
    ctrl.fetch_weather()

    assert ctrl.weather_labels()["kp"] == f"Kp: {ctrl.state.kp_index:.1f}"
    assert ctrl.state.kp_forecast == f"{ctrl.state.kp_index:.1f}"


def test_offline_fixture_is_off_by_default(monkeypatch):
    monkeypatch.delenv("ORBITRX_CAPTURE_DIR", raising=False)
    monkeypatch.delenv("ORBITRX_OFFLINE_FIXTURE", raising=False)
    assert offline_fixture() is False
    assert "ORBITRX_CAPTURE_DIR" not in os.environ or os.environ.get("ORBITRX_CAPTURE_DIR") == ""
