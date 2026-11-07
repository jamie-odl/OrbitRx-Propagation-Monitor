"""Check an unpublished Windows onedir folder. Does not upload anything."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# PyInstaller 6 onedir, observed on windows-latest for commit ef8ebd6:
# the launcher is OrbitRxMonitor.exe and collected files live in _internal.
REQUIRED = (
    "OrbitRxMonitor.exe",
    "_internal/PySide6/Qt6Core.dll",
    "_internal/PySide6/Qt6WebEngineCore.dll",
    "_internal/ne_110m_dark.png",
    "_internal/LICENSE",
    "_internal/NOTICE",
    "_internal/PRIVACY.md",
    "_internal/third_party/qt/LICENSES/LGPL-3.0-only.txt",
    "_internal/third_party/qt/LICENSE.Chromium",
    "_internal/third_party/natural_earth/TERMS_OF_USE.txt",
)
FORBIDDEN = (
    "world_map.jpg",
    "static_basemap_v2.png",
    "static_basemap_v2.webp",
    "_internal/world_map.jpg",
    "_internal/static_basemap_v2.png",
    "_internal/static_basemap_v2.webp",
)


def check_layout(root: Path) -> list[str]:
    problems: list[str] = []
    if not root.is_dir():
        return [f"not a directory: {root}"]
    for rel in REQUIRED:
        if not (root / rel).is_file():
            problems.append(f"missing {rel}")
    for rel in FORBIDDEN:
        if (root / rel).exists():
            problems.append(f"legacy or nested art present: {rel}")
    exe = root / "OrbitRxMonitor.exe"
    for dll in ("Qt6Core.dll", "Qt6WebEngineCore.dll"):
        lib = root / dll
        if exe.is_file() and lib.is_file() and lib.resolve() == exe.resolve():
            problems.append(f"{dll} is not a separate file")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    problems = check_layout(args.root)
    if problems:
        print("onedir layout failed:")
        for item in problems:
            print(f"  {item}")
        return 1
    print(f"onedir layout ok: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
