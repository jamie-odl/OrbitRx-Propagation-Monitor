"""Pure display-formatting helpers shared by the Qt UI.

Kept dependency-free (no Qt imports) so they are cheap to unit test.
"""

from __future__ import annotations

import datetime

NONE_TEXT = "n/a"

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


def concise_date_offset_formats() -> list[str]:
    """ConciseDateFormatter offset_formats using "dd MMM yyyy" day order (N-new-7),
    consistent with format_iso_utc elsewhere instead of matplotlib's default "yyyy-MMM-dd".
    """
    return ["", "%Y", "%b %Y", "%d %b %Y", "%d %b %Y", "%d %b %Y %H:%M"]


def history_plot_date_format(lo: datetime.datetime, hi: datetime.datetime) -> str:
    """matplotlib tick format for the history plot x-axis (M4): every tick shows
    hours and minutes, with the day added once the range spans more than a day.
    """
    span_hours = (hi - lo).total_seconds() / 3600.0
    return "%H:%M" if span_hours <= 24 else "%d %b %H:%M"


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
