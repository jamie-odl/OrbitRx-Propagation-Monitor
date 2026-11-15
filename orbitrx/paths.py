from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# The only basemap the app loads. Unknown-provenance JPEG and v2 images stay
# in the git tree for history and are never selected, even if they sit beside
# the executable.
PACKAGED_BASEMAP_NAME = "ne_110m_dark.png"
EXCLUDED_BASEMAP_NAMES = (
    "static_basemap_v2.png",
    "static_basemap_v2.webp",
    "world_map.jpg",
)


def project_root() -> Path:
    """Directory containing app.py, or the onedir folder when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


APP_DATA_DIRNAME = "OrbitRx"


def user_data_dir() -> Path:
    """Folder for settings and data files (config.json, orbitrx.db, CSV logs).

    Frozen builds use %APPDATA%\\OrbitRx (created on demand) so the app never
    depends on the launch folder being writable; if APPDATA is unset or the
    folder cannot be created they fall back to the exe folder. Source runs keep
    the historical behaviour: a relative path, i.e. the current directory.
    """
    if not getattr(sys, "frozen", False):
        return Path()
    appdata = os.environ.get("APPDATA")
    if appdata:
        folder = Path(appdata) / APP_DATA_DIRNAME
        try:
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        except OSError:
            pass
    return project_root()


def user_data_path(name: str) -> Path:
    """Path of a named data file under user_data_dir().

    Frozen builds copy (never move) a same-named file left next to the exe by
    an earlier version the first time the new location has none.
    """
    path = user_data_dir() / name
    if getattr(sys, "frozen", False) and not path.exists():
        legacy = project_root() / name
        try:
            if legacy.is_file() and legacy.resolve() != path.resolve():
                shutil.copy2(legacy, path)
        except OSError:
            pass
    return path


def bundled_root() -> Path | None:
    """PyInstaller extraction / onedir folder."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def _candidate_paths() -> list[Path]:
    name = PACKAGED_BASEMAP_NAME
    found: list[Path] = []
    bundle = bundled_root()
    if bundle:
        found.append(bundle / name)
    root = project_root()
    found.append(root / "basemap" / name)
    found.append(root / name)
    return found


def resolve_map_path() -> Path:
    """Return the Natural Earth basemap, never a legacy JPEG or v2 file."""
    for path in _candidate_paths():
        if path.name in EXCLUDED_BASEMAP_NAMES:
            continue
        if path.is_file() and path.stat().st_size > 10_000:
            return path
    root = project_root()
    return root / "basemap" / PACKAGED_BASEMAP_NAME


def ensure_map_image() -> Path:
    """Return the packaged basemap, regenerating it from the pinned dataset if needed."""
    path = resolve_map_path()
    if path.is_file() and path.stat().st_size > 10_000 and path.name == PACKAGED_BASEMAP_NAME:
        return path
    try:
        from tools.render_natural_earth_candidate import (
            HEIGHT,
            PACKAGED_PATH,
            WIDTH,
            load_dataset,
            render_land,
            save_png,
        )

        save_png(render_land(load_dataset(), WIDTH, HEIGHT), PACKAGED_PATH)
        return PACKAGED_PATH
    except Exception:
        return path
