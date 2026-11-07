"""Check an unpublished Windows onedir folder. Does not upload anything."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED = (
    "OrbitRxMonitor.exe",
    "Qt6Core.dll",
    "Qt6WebEngineCore.dll",
    "ne_110m_dark.png",
    "LICENSE",
    "NOTICE",
    "PRIVACY.md",
    "third_party/qt/LICENSES/LGPL-3.0-only.txt",
    "third_party/qt/LICENSE.Chromium",
    "third_party/natural_earth/TERMS_OF_USE.txt",
)
FORBIDDEN = (
    "world_map.jpg",
    "static_basemap_v2.png",
    "static_basemap_v2.webp",
    "basemap/ne_110m_dark.png",
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
