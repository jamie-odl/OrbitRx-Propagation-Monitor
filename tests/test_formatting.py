"""Tests for the pure UI formatting helpers (M7: no raw internal values in the UI)."""

from __future__ import annotations

import datetime

from orbitrx.ui.formatting import (
    concise_date_offset_formats,
    decimal_hours_to_hhmm,
    format_hour_offset,
    format_iso_utc,
    format_map_hud_datetime,
    format_replay_offset,
    format_source_label,
    format_value,
    history_plot_date_format,
    pad_datetime_range,
)


def test_format_value_none_is_n_slash_a():
    assert format_value(None) == "n/a"
    assert format_value(None, unit=" MHz") == "n/a"


def test_format_value_formats_and_appends_unit():
    assert format_value(100.0, unit=" km/s") == "100.0 km/s"
    assert format_value(28, unit=" MHz", fmt="{:.0f}") == "28 MHz"


def test_decimal_hours_to_hhmm():
    assert decimal_hours_to_hhmm(7.44) == "07:26"
    assert decimal_hours_to_hhmm(0.0) == "00:00"
    assert decimal_hours_to_hhmm(23.999) == "00:00"
    assert decimal_hours_to_hhmm(None) == "n/a"


def test_format_iso_utc_handles_z_suffix():
    assert format_iso_utc("2026-11-04T15:00:00Z") == "04 Nov 15:00 UTC"


def test_format_iso_utc_handles_offset_and_space_separated():
    assert format_iso_utc("2026-11-04T15:00:00+00:00") == "04 Nov 15:00 UTC"
    assert format_iso_utc("2026-11-04 15:00:00") == "04 Nov 15:00 UTC"


def test_format_iso_utc_none_or_dashes():
    assert format_iso_utc(None) == "n/a"
    assert format_iso_utc("--") == "n/a"
    assert format_iso_utc("") == "n/a"


def test_format_source_label_maps_internal_identifiers():
    assert format_source_label("NOAA a_running") == "NOAA A-index (running estimate)"
    assert format_source_label("Kyoto Dst est.") == "Kyoto Dst (estimated)"
    assert "_" not in format_source_label("NOAA a_running")


def test_format_source_label_empty():
    assert format_source_label(None) == ""
    assert format_source_label("") == ""


def test_format_source_label_passthrough_for_unknown():
    assert format_source_label("Some other source") == "Some other source"


def test_pad_datetime_range_pads_each_side():
    lo = datetime.datetime(2026, 11, 4, 0, 0, tzinfo=datetime.timezone.utc)
    hi = datetime.datetime(2026, 11, 4, 10, 0, tzinfo=datetime.timezone.utc)
    plo, phi = pad_datetime_range(lo, hi, frac=0.05)
    assert plo < lo and phi > hi
    assert (lo - plo) == (phi - hi)
    assert (lo - plo) == datetime.timedelta(hours=0.5)


def test_pad_datetime_range_single_point_still_pads():
    t = datetime.datetime(2026, 11, 4, 12, 0, tzinfo=datetime.timezone.utc)
    plo, phi = pad_datetime_range(t, t)
    assert plo < t < phi


def test_format_hour_offset_is_integer_with_space(): # S6
    assert format_hour_offset(0) == "+0 h"
    assert format_hour_offset(3) == "+3 h"
    assert format_hour_offset(48) == "+48 h"


def test_format_replay_offset_live_or_integer_hours(): # S6
    assert format_replay_offset(0) == "Live"
    assert format_replay_offset(2) == "-2 h"
    assert format_replay_offset(48) == "-48 h"


def test_concise_date_offset_formats_use_day_month_year_order(): # N-new-7
    formats = concise_date_offset_formats()
    assert formats[3] == "%d %b %Y"
    import datetime
    d = datetime.datetime(2026, 11, 4)
    assert d.strftime(formats[3]) == "04 Nov 2026"


def test_history_plot_date_format_is_hh_mm_within_a_day(): # M4
    lo = datetime.datetime(2026, 11, 4, 21, 30, tzinfo=datetime.timezone.utc)
    hi = datetime.datetime(2026, 11, 4, 23, 0, tzinfo=datetime.timezone.utc)
    fmt = history_plot_date_format(lo, hi)
    assert fmt == "%H:%M"
    assert hi.strftime(fmt) == "23:00"


def test_history_plot_date_format_adds_day_beyond_a_day(): # M4
    lo = datetime.datetime(2026, 11, 2, 0, 0, tzinfo=datetime.timezone.utc)
    hi = datetime.datetime(2026, 11, 4, 23, 0, tzinfo=datetime.timezone.utc)
    fmt = history_plot_date_format(lo, hi)
    assert fmt == "%d %b %H:%M"
    assert hi.strftime(fmt) == "04 Nov 23:00"


def test_format_map_hud_datetime_has_no_iso_date(): # S1
    dt = datetime.datetime(2026, 11, 4, 23, 1, tzinfo=datetime.timezone.utc)
    text = format_map_hud_datetime(dt)
    assert text == "04 Nov 2026 23:01 UTC"
    assert "2026-11-04" not in text


def test_humanize_iso_dates_in_alert_text():  # S1
    from orbitrx.ui.formatting import humanize_iso_dates
    out = humanize_iso_dates("2026-11-04 19:04 UTC  WATCH: Geomagnetic Storm")
    assert out.startswith("04 Nov 19:04 UTC")
    assert "2026-11-04" not in out
