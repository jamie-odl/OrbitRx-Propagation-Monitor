"""Tests for the Matrix merge: spots service, settings, privacy defaults, packaging."""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

import orbitrx
from orbitrx.cat import CatController
from orbitrx.config import DEFAULT_CONFIG, AppConfig
from orbitrx.spots import database
from orbitrx.spots.geo import arcs_payload, heatmap_payload, replay_windows
from orbitrx.spots.models import Spot
from orbitrx.spots.service import SpotsService
from orbitrx.spots.settings import PSKREPORTER_MIN_POLL_SECONDS, clamp_poll_seconds
from orbitrx.spots.space_weather import from_orbitrx_state

ROOT = Path(__file__).resolve().parents[1]


def _spot(snr: float = -10.0) -> Spot:
    return Spot(51.5, -0.1, 40.7, -74.0, 14_074_000.0, "FT8", "G4ABC", "K1AAA", snr, 100,
                "2026-11-04T20:00:00+00:00", "pskreporter")


class _Cfg(dict):
    def get(self, key, default=None):  # noqa: D401 - dict-compatible
        return super().get(key, DEFAULT_CONFIG.get(key, default))


def test_poll_interval_never_below_five_minutes():
    assert PSKREPORTER_MIN_POLL_SECONDS == 300
    assert clamp_poll_seconds(10) == 300
    assert clamp_poll_seconds("garbage") == 300
    assert clamp_poll_seconds(900) == 900
    assert SpotsService(_Cfg(pskreporter_poll_seconds=1)).poll_seconds == 300


def test_service_respects_poll_floor_and_survives_offline():
    calls = []

    def ok_fetch(**kwargs):
        calls.append(kwargs)
        return [_spot()]

    with TemporaryDirectory() as tmp, patch.object(database, "DATABASE_PATH", Path(tmp) / "s.db"):
        database.initialize_database()
        svc = SpotsService(_Cfg(), fetcher=ok_fetch)
        assert len(svc.poll_once()) == 1
        svc.poll_once()  # inside 5 min window: must not hit the network again
        assert len(calls) == 1

        def boom(**_kwargs):
            raise OSError("network down")

        svc._fetcher = boom
        result = svc.poll_once(force=True)
        assert svc.last_error == "network down"
        assert len(result) == 1  # keeps last good data


def test_spots_service_start_does_not_init_database_on_caller_thread():
    """F9: start() is called from the UI thread during window init; the
    SQLite DDL must happen on the worker thread, not block the caller."""
    import threading
    import time

    main_thread = threading.current_thread()
    init_threads = []
    release = threading.Event()
    real_init = database.initialize_database

    def slow_init():
        init_threads.append(threading.current_thread())
        release.wait(timeout=5)
        real_init()

    with TemporaryDirectory() as tmp, patch.object(database, "DATABASE_PATH", Path(tmp) / "s.db"), \
            patch.object(database, "initialize_database", slow_init):
        svc = SpotsService(
            _Cfg(spots_enabled=True, pskreporter_poll_seconds=100000),
            fetcher=lambda **kwargs: [],
        )

        t0 = time.perf_counter()
        svc.start()
        call_duration = time.perf_counter() - t0
        assert call_duration < 1.0  # start() must return immediately

        deadline = time.time() + 5
        while not init_threads and time.time() < deadline:
            time.sleep(0.01)
        assert init_threads and init_threads[0] is not main_thread

        release.set()
        svc.stop()


def test_ip_geolocation_is_off_by_default():
    assert DEFAULT_CONFIG["ip_geolocation_enabled"] is False


def test_rig_control_setting_selects_backend():
    with TemporaryDirectory() as tmp:
        cfg = AppConfig(path=Path(tmp) / "c.json").load()
        cat = CatController(cfg)
        assert cat.backend() == "serial"
        cfg.set("rig_control", "omnirig")
        assert cat.backend() == "omnirig"
        cfg.set("rig_control", "nonsense")
        assert cat.backend() == "serial"
        cfg.set("rig_control", "omnirig")
        cfg.set("cat_confirm_before_tune", False)
        msg = cat.tune(14.074)
        assert isinstance(msg, str) and msg  # no crash off Windows / without OmniRig


def test_live_layer_payloads():
    arcs = arcs_payload([_spot(-20), _spot(5)], limit=1)
    assert len(arcs) == 1 and arcs[0]["band"] == "20m" and "+5 dB" in arcs[0]["label"]
    heat = heatmap_payload([_spot(), _spot()])
    assert heat and max(c[2] for c in heat) == 1.0
    assert heatmap_payload([]) == []
    assert len(replay_windows(None, hours=2, bucket_minutes=30)) == 4


def test_space_weather_single_source_adapter():
    class S:
        kp_index = 3.0
        flux = "150"
    data = from_orbitrx_state(S())
    assert data.kp_index == 3.0 and data.solar_flux == 150.0 and data.status == "ok"


def test_version_file_matches_package():
    assert (ROOT / "VERSION").read_text().strip() == orbitrx.__version__
    assert f"## [{orbitrx.__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_this_build_is_5_2_0_and_never_identifies_as_5_1_0():
    """F1 follow-up: this build must identify as the plain, PEP 440-valid
    5.2.0 everywhere an operator or CI gate would look at identity, and
    must never be mistaken for the 5.1.0 release."""
    import tomllib

    assert orbitrx.__version__ == "5.2.0"
    assert (ROOT / "VERSION").read_text().strip() == "5.2.0"
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "5.2.0"

    try:
        from packaging.version import Version
        Version(orbitrx.__version__)  # raises InvalidVersion if not PEP 440
    except ImportError:
        assert re.fullmatch(r"\d+\.\d+\.\d+", orbitrx.__version__)

    from tools.make_version_info import version_tuple4
    assert version_tuple4(orbitrx.__version__) == (5, 2, 0, 0)

    iss = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    assert '#define AppVer "5.2.0"' in iss
    assert '#define AppVerNumeric "5.2.0.0"' in iss
    assert "5.1.0" not in iss

    qt_app = (ROOT / "orbitrx" / "ui" / "qt_app.py").read_text(encoding="utf-8")
    assert 'setWindowTitle(f"OrbitRx Propagation Monitor {__version__}")' in qt_app
    assert "prototype" not in qt_app

    about = (ROOT / "orbitrx" / "ui" / "about.py").read_text(encoding="utf-8")
    assert "prototype" not in about

    for rel in ("VERSION", "pyproject.toml", "orbitrx/__init__.py", "installer/OrbitRxMonitor.iss"):
        assert "5.1.0" not in (ROOT / rel).read_text(encoding="utf-8"), rel


@pytest.mark.parametrize("name", ["LICENSE", "NOTICE", "PRIVACY.md", "CHANGELOG.md", "README.md"])
def test_release_docs_exist_without_em_dashes(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert text.strip()
    assert "\u2014" not in text


def test_license_is_mit_jamie_sibley():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text and "thevenom" in text


def test_buy_me_a_coffee_uses_jamie_url():
    about = (ROOT / "orbitrx" / "ui" / "about.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "TODO-placeholder" not in about
    assert "buymeacoffee.com/TODO" not in about
    assert "buymeacoffee.com/thevenom" in about or "buymeacoffee.com/thevenom" in about.replace("https://", "")
    assert "buymeacoffee.com/thevenom" in about
    assert "buymeacoffee.com/thevenom" in readme


def test_removed_legacy_files():
    for name in ["_check.py", "inspect_noaa.py", "orbitrx/ui/tk_app.py"]:
        assert not (ROOT / name).exists()


def test_no_em_dashes_in_ui_strings():
    for path in (ROOT / "orbitrx" / "ui").glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#"):
                continue
            assert "\u2014" not in line, f"{path.name}: {line.strip()}"


def test_no_debug_prints_in_package():
    for path in (ROOT / "orbitrx").rglob("*.py"):
        assert not re.search(r"^\s*print\(", path.read_text(encoding="utf-8"), re.M), path


def test_noaa_alert_summary_is_one_line():
    from orbitrx.weather import summarise_alert
    msg = "Space Weather Message Code: WATA20\r\nSerial Number: 1135\r\n\r\nWATCH: Geomagnetic Storm Category G1 Predicted\r\n..."
    out = summarise_alert(msg, "2026-11-04 19:04:00.000")
    assert out == "2026-11-04 19:04 UTC  WATCH: Geomagnetic Storm Category G1 Predicted"
    assert "\n" not in out


def test_night_mask_dark_opposite_sun():
    import math
    from orbitrx.map_renderer import MapRenderer
    mask = MapRenderer._night_mask(360, 180, 0.0, 0.0)
    assert mask.getpixel((180, 90))[3] == 0          # sub-solar point is lit
    assert mask.getpixel((5, 90))[3] > 100           # antipode is dark
    assert math.isclose(mask.size[0], 360)


def test_sun_marker_wraps_at_left_edge(): # S4
    from orbitrx.map_renderer import MapRenderer
    anns = MapRenderer._wrap_sun_marker(2.0, 100.0, 900)
    assert [a.kind for a in anns] == ["sun", "sun"]
    assert anns[0].data == {"x": 2.0, "y": 100.0}
    assert anns[1].data == {"x": 902.0, "y": 100.0}  # wrapped copy near the right edge


def test_sun_marker_wraps_at_right_edge(): # S4
    from orbitrx.map_renderer import MapRenderer
    anns = MapRenderer._wrap_sun_marker(898.0, 100.0, 900)
    assert len(anns) == 2
    assert anns[1].data == {"x": -2.0, "y": 100.0}  # wrapped copy near the left edge


def test_sun_marker_not_wrapped_away_from_both_edges(): # S4
    from orbitrx.map_renderer import MapRenderer
    anns = MapRenderer._wrap_sun_marker(450.0, 100.0, 900)
    assert len(anns) == 1


def test_weather_labels_drops_redundant_per_band_row(tmp_path, monkeypatch): # S6
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    ctrl = OrbitRxController()
    labels = ctrl.weather_labels()
    assert "band_grid" not in labels
    assert not any("Per-band" in v for v in labels.values())


def test_solar_flux_trend_word_shown_whenever_a_value_exists(tmp_path, monkeypatch): # S7
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    ctrl = OrbitRxController()

    ctrl.state.flux = 111.0
    ctrl.state.flux_trend = ""  # no previous reading yet
    assert ctrl.weather_labels()["solar"] == "Solar Flux: 111.0 → (steady)"

    ctrl.state.flux_trend = "↑ (rising)"
    assert ctrl.weather_labels()["solar"] == "Solar Flux: 111.0 ↑ (rising)"

    ctrl.state.flux = None
    ctrl.state.flux_trend = ""
    assert ctrl.weather_labels()["solar"] == "Solar Flux: n/a"


def test_path_muf_label_has_no_unit_when_missing(tmp_path, monkeypatch): # S2
    monkeypatch.chdir(tmp_path)
    from orbitrx.ui.controller import OrbitRxController
    ctrl = OrbitRxController()

    ctrl.state.path_muf = None
    ctrl.state.path_muf_label = None
    assert ctrl.weather_labels()["path_muf"] == "Path MUF: n/a"

    ctrl.state.path_muf = 21.4
    ctrl.state.path_muf_label = None
    assert ctrl.weather_labels()["path_muf"] == "Path MUF: 21.4 MHz"


def test_default_dx_cluster_callsign_is_blank():
    from orbitrx.config import DEFAULT_CONFIG
    assert DEFAULT_CONFIG["dx_cluster_callsign"] == ""
    example = (ROOT / "config.example.json").read_text(encoding="utf-8")
    assert '"dx_cluster_callsign": ""' in example
