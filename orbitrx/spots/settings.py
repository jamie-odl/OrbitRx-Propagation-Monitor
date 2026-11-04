"""Constants for the live spots package."""

from __future__ import annotations

from orbitrx import __version__
from orbitrx.paths import project_root

DATA_DIR = project_root() / "data"
DATABASE_PATH = DATA_DIR / "orbitrx_spots.db"

# PSKReporter asks clients not to poll more often than every 5 minutes.
PSKREPORTER_MIN_POLL_SECONDS = 300
PSKREPORTER_FLOW_START_SECONDS = 900
MAX_FETCH_SPOTS = 300
MAX_RENDERED_ARCS = 80
LOCAL_VIEW_RADIUS_MILES = 500.0
REPLAY_RETENTION_HOURS = 24 * 7
REPLAY_BUCKET_MINUTES = 30
ALERT_COOLDOWN_MINUTES = 30
USER_AGENT = f"OrbitRx/{__version__}"


def clamp_poll_seconds(value: object) -> int:
    """Return a PSKReporter poll interval that never goes below the 5 minute floor."""
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        seconds = PSKREPORTER_MIN_POLL_SECONDS
    return max(PSKREPORTER_MIN_POLL_SECONDS, seconds)
