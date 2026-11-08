"""Reject a package tree that contains a runtime profile.

The onedir that is zipped must never have been launched. Launching writes
config, caches, logs, and spot databases next to the executable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_FILES = (
    "config.json",
    "orbitrx.db",
    "orbitrx.db.bak",
    "weather_cache.json",
    "propagation_log.csv",
)
ROOT_DIRS = ("logs", "data")


def runtime_residue(root: Path) -> list[str]:
    """Return paths that must not ship. Empty means the tree is pristine."""
    if not root.is_dir():
        return [f"not a directory: {root}"]
    found: list[str] = []
    for name in ROOT_FILES:
        if (root / name).exists():
            found.append(name)
    for name in ROOT_DIRS:
        path = root / name
        if path.exists():
            found.append(name + "/")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    found = runtime_residue(args.root)
    if found:
        print("pristine payload check failed:")
        for item in found:
            print(f"  {item}")
        return 1
    print(f"pristine payload ok: {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
