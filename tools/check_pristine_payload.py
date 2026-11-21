"""Reject a package tree that contains a runtime profile.

The onedir that is zipped must never have been launched. Launching writes
config, caches, logs, and spot databases next to the executable. ``--zip``
applies the same rule to the OrbitRxMonitor folder stored in a release zip.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT_FILES = (
    "config.json",
    "orbitrx.db",
    "orbitrx.db.bak",
    "weather_cache.json",
    "propagation_log.csv",
)
ROOT_DIRS = ("logs", "data")
DEFAULT_ZIP_PREFIX = "OrbitRxMonitor"


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


def zip_runtime_residue(zip_path: Path, prefix: str = DEFAULT_ZIP_PREFIX) -> list[str]:
    """Return runtime paths stored under prefix inside a zip. Empty means clean."""
    if not zip_path.is_file():
        return [f"not a file: {zip_path}"]
    folder = prefix.replace("\\", "/").strip("/")
    head = folder + "/"
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = [info.filename.replace("\\", "/") for info in archive.infolist()]
    except zipfile.BadZipFile:
        return [f"not a zip: {zip_path}"]
    if not any(name == head + "OrbitRxMonitor.exe" or name.startswith(head) for name in names):
        return [f"zip has no {folder}/ payload"]
    found: list[str] = []
    for name in ROOT_FILES:
        rel = head + name
        if rel in names:
            found.append(name)
    for name in ROOT_DIRS:
        rel = head + name
        if any(item == rel or item.startswith(rel + "/") for item in names):
            found.append(name + "/")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path)
    parser.add_argument("--zip", type=Path, dest="zip_path")
    parser.add_argument("--prefix", default=DEFAULT_ZIP_PREFIX)
    args = parser.parse_args(argv)
    if args.zip_path is not None:
        found = zip_runtime_residue(args.zip_path, args.prefix)
        label = str(args.zip_path)
    elif args.root is not None:
        found = runtime_residue(args.root)
        label = str(args.root)
    else:
        parser.error("give a folder, or --zip")
        return 2
    if found:
        print("pristine payload check failed:")
        for item in found:
            print(f"  {item}")
        return 1
    print(f"pristine payload ok: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
