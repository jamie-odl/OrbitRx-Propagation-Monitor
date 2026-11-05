"""Pure display-formatting helpers shared by the Qt UI.

Kept dependency-free (no Qt imports) so they are cheap to unit test.
"""

from __future__ import annotations

import datetime
import statistics

NONE_TEXT = "n/a"

# M4: fallback "expected weather poll interval" used by insert_gap_breaks when the
# caller has no better estimate (e.g. no config available). Mirrors a plausible
# real-world space-weather refresh cadence.
EXPECTED_POLL_S = 15 * 60

# M4: floor below which a gap is never considered a break, regardless of how
# short the expected poll interval is.
MIN_GAP_BREAK_S = 30 * 60

# Internal/raw source identifiers -> human-readable labels (M7: no leaking
# internal identifiers like "a_running" into the UI).
NOAA_SOURCE_LABELS: dict[str, str] = {
    "a_running": "NOAA A-index (running estimate)",
    "NOAA a_running": "NOAA A-index (running estimate)",
    "Kyoto Dst est.": "Kyoto Dst (estimated)",
}


def format_value(value, unit: str = "", none_text: str = NONE_TEXT, fmt: str = "{:.1f}") -> str:
    """Format a numeric value, or none_text when value is None/empty."""
    if value is None or value == "":
        return none_text
    try:
        text = fmt.format(value)
    except (ValueError, TypeError):
        text = str(value)
    return f"{text}{unit}" if unit else text


def fmt(value, unit: str) -> str:
    """The one value+unit formatter for every stat row (M5): "n/a" for a missing or
    non-numeric value (never "n/a <unit>"), else one decimal place plus its unit.
    """
    if value is None or isinstance(value, bool):
        return NONE_TEXT
    try:
        return f"{float(value):.1f} {unit}"
    except (TypeError, ValueError):
        return NONE_TEXT


def decimal_hours_to_hhmm(hours: float | None) -> str:
    """Convert decimal hours (e.g. 7.44) to a 24h clock string ("07:26")."""
    if hours is None:
        return NONE_TEXT
    hours = float(hours) % 24
    total_minutes = round(hours * 60) % (24 * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h:02d}:{m:02d}"


def format_iso_utc(iso: str | None) -> str:
    """Format an ISO-8601 timestamp (or NOAA-style raw string) as "dd MMM HH:mm UTC"."""
    if not iso or iso == "--":
        return NONE_TEXT
    text = str(iso).strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            return text
    return dt.strftime("%d %b %H:%M") + " UTC"


def format_source_label(raw: str | None) -> str:
    """Map an internal source identifier to a readable label (empty stays empty)."""
    if not raw:
        return ""
    return NOAA_SOURCE_LABELS.get(raw, raw)


def format_hour_offset(hours: float) -> str:
    """Forward time-offset slider readout, e.g. 0 -> "+0 h", 3 -> "+3 h" (S6)."""
    return f"+{int(round(hours))} h"


def format_replay_offset(hours: float) -> str:
    """Spot-replay slider readout, e.g. 0 -> "Live", 2 -> "-2 h" (S6)."""
    h = int(round(hours))
    return "Live" if h == 0 else f"-{h} h"


def format_no_spots_message(hours_ago: float = 0) -> str:
    """Empty-replay-window map overlay text (S1), e.g. 0 -> "No spots in this window",
    6 -> "No spots in this window (6 h ago)"."""
    h = int(round(hours_ago))
    return "No spots in this window" if h == 0 else f"No spots in this window ({h} h ago)"


def concise_date_offset_formats() -> list[str]:
    """ConciseDateFormatter offset_formats using "dd MMM yyyy" day order (N-new-7),
    consistent with format_iso_utc elsewhere instead of matplotlib's default "yyyy-MMM-dd".
    """
    return ["", "%Y", "%b %Y", "%d %b %Y", "%d %b %Y", "%d %b %Y %H:%M"]


def history_plot_date_format(lo: datetime.datetime, hi: datetime.datetime) -> str:
    """matplotlib tick format for the history plot x-axis: hours and minutes within a
    day (M4), the day added once the range spans more than a day, and date-only daily
    ticks once the range reaches 36 h so "dd MMM" labels never repeat "00:00" (S3).
    """
    span_hours = (hi - lo).total_seconds() / 3600.0
    if span_hours <= 24:
        return "%H:%M"
    if span_hours < 36:
        return "%d %b %H:%M"
    return "%d %b"


def format_map_hud_datetime(dt: datetime.datetime) -> str:
    """Map HUD timestamp with no ISO date, e.g. "04 Nov 2026 23:01 UTC" (S1)."""
    return dt.strftime("%d %b %Y %H:%M") + " UTC"


def pad_datetime_range(
    lo: datetime.datetime, hi: datetime.datetime, frac: float = 0.05
) -> tuple[datetime.datetime, datetime.datetime]:
    """Pad a [lo, hi] datetime range by frac on each side (M2: plot axis range)."""
    if lo == hi:
        delta = datetime.timedelta(minutes=30)
        return lo - delta, hi + delta
    span = hi - lo
    pad = span * frac
    return lo - pad, hi + pad


_ISO_STAMP = __import__("re").compile(r"\b(\d{4})-(\d{2})-(\d{2})([ T])(\d{2}:\d{2})")


def humanize_iso_dates(text: str) -> str:
    """Rewrite "2026-11-04 19:04" style stamps inside free text as "04 Nov 19:04"."""
    def _sub(m):
        try:
            dt = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        return dt.strftime("%d %b ") + m.group(5)
    return _ISO_STAMP.sub(_sub, text)


def insert_gap_breaks(
    times: list[datetime.datetime],
    values: list[float],
    poll_interval_s: float = EXPECTED_POLL_S,
    min_gap_s: float = MIN_GAP_BREAK_S,
) -> tuple[list[datetime.datetime], list[float]]:
    """Insert a NaN point at the midpoint of any gap between consecutive `times` that
    exceeds max(3 * median_dt, 3 * poll_interval_s, min_gap_s), so a matplotlib line
    plotted through the result breaks only across a real outage, not across ordinary
    poll jitter (M2/M4). The median term means a feed that normally polls faster (or
    slower) than `poll_interval_s` still gets a threshold scaled to its own typical
    spacing, not just the configured interval.

    With fewer than 4 samples there isn't enough history to tell a real outage from
    jitter, so everything is connected.
    """
    if len(times) < 4:
        return list(times), list(values)
    deltas = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
    median_dt = statistics.median(deltas)
    threshold = max(3 * median_dt, 3 * poll_interval_s, min_gap_s)
    out_times = [times[0]]
    out_values = [values[0]]
    for i in range(1, len(times)):
        gap = (times[i] - times[i - 1]).total_seconds()
        if gap > threshold:
            out_times.append(times[i - 1] + (times[i] - times[i - 1]) / 2)
            out_values.append(float("nan"))
        out_times.append(times[i])
        out_values.append(values[i])
    return out_times, out_values


def widen_to_min_span(
    lo: datetime.datetime, hi: datetime.datetime, minutes: int = 60
) -> tuple[datetime.datetime, datetime.datetime]:
    """Widen a short plot range to at least `minutes`, centred, so HH:mm ticks are
    never duplicated (M4)."""
    span = hi - lo
    need = datetime.timedelta(minutes=minutes)
    if span >= need:
        return lo, hi
    mid = lo + span / 2
    return mid - need / 2, mid + need / 2
