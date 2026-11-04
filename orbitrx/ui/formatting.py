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
