from orbitrx.propagation import (
    band_condition, band_grid, estimate_muf, flux_trend_arrow, voacap_lite_path_muf,
)


def test_estimate_muf():
    muf, luf = estimate_muf(150, 2)
    assert muf is not None and muf > 20
    assert luf is not None


def test_band_condition_open():
    assert band_condition(14.0, 200, 0) == "OPEN"
    assert band_condition(14.0, 160, 1) in ("OPEN", "FAIR")


def test_path_muf():
    m = voacap_lite_path_muf(150, 2, 40.0, -74.0, 35.0, 139.0)
    assert m is not None and m > 0


def test_band_grid_keys():
    g = band_grid(150, 2)
    assert "10m" in g and "20m" in g


def test_flux_trend_arrow_labels_the_direction(): # N-new-8
    assert flux_trend_arrow([100, 110]) == "↑ (rising)"
    assert flux_trend_arrow([110, 100]) == "↓ (falling)"
    assert flux_trend_arrow([100, 101]) == "→ (steady)"
    # Too little history: show nothing, never a bare "--" placeholder (M7).
    assert flux_trend_arrow([100]) == ""
    assert "--" not in flux_trend_arrow([])
