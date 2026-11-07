from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    """Directory containing app.py / the exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_root() -> Path | None:
    """PyInstaller onefile extraction folder."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


# Source checkouts search in this order. OrbitRxMonitor.spec and the Inno
# script package only PACKAGED_BASEMAP_NAME, so the frozen exe never sees
# the v2 files and resolves the JPEG. Do not treat that as a licence finding.
SOURCE_BASEMAP_NAMES = ("static_basemap_v2.png", "static_basemap_v2.webp", "world_map.jpg")
PACKAGED_BASEMAP_NAME = "world_map.jpg"


def resolve_map_path() -> Path:
    """Find a local basemap. v2 is preferred only when that file is present."""
    names = SOURCE_BASEMAP_NAMES
    search: list[Path] = []
    bundle = bundled_root()
    if bundle:
        search.extend(bundle / n for n in names)
    root = project_root()
    search.extend([root / n for n in names])
    search.extend([Path.cwd() / n for n in names])
    for path in search:
        if path.is_file() and path.stat().st_size > 10_000:
            return path
    return root / "static_basemap_v2.png"


def ensure_map_image() -> Path:
    """Return path to static basemap, generating a fallback if missing."""
    path = resolve_map_path()
    if path.is_file() and path.stat().st_size > 10_000:
        return path

    target = project_root() / "static_basemap_v2.png"
    try:
        from generate_map import generate_world_map

        generate_world_map(1800, 900)
    except Exception:
        pass
    if target.is_file():
        return target
    legacy = project_root() / "world_map.jpg"
    if legacy.is_file():
        return legacy
    return target
