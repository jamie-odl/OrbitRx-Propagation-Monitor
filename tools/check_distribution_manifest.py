"""Check vendored licence texts and refuse a release while blockers remain.

``--release`` is the gate. It exits 1 while packaging/distribution_manifest.json
lists an open blocker. Copying LGPL or GPL text into third_party/ does not
clear those blockers. This command does not upload a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "distribution_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def missing_texts(manifest: dict) -> list[str]:
    missing: list[str] = []
    for rel, expected in manifest["present_texts"].items():
        path = ROOT / rel
        if not path.is_file():
            missing.append(f"missing {rel}")
            continue
        if expected is None:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            missing.append(f"hash mismatch {rel}")
    return missing


def packaged_map_ok() -> list[str]:
    problems: list[str] = []
    spec = (ROOT / "OrbitRxMonitor.spec").read_text(encoding="utf-8")
    iss = (ROOT / "installer" / "OrbitRxMonitor.iss").read_text(encoding="utf-8")
    if "('world_map.jpg', '.')" not in spec:
        problems.append("spec does not package world_map.jpg")
    if "static_basemap_v2" in spec:
        problems.append("spec packages a v2 basemap")
    if 'Source: "..\\world_map.jpg"' not in iss:
        problems.append("installer does not package world_map.jpg")
    if "static_basemap_v2" in iss:
        problems.append("installer packages a v2 basemap")
    if "third_party\\qt\\LICENSES" not in iss and "third_party/qt/LICENSES" not in iss:
        problems.append("installer does not copy Qt licence texts")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)
    manifest = load_manifest()
    problems = missing_texts(manifest) + packaged_map_ok()
    blockers = list(manifest["release_blockers"])
    if problems:
        print("distribution manifest files are incomplete:")
        for item in problems:
            print(f"  {item}")
        return 1
    print("vendored licence texts match the manifest")
    print("packaged basemap is world_map.jpg; v2 images are not in the spec or installer")
    if blockers:
        print("release blockers still open:")
        for item in blockers:
            print(f"  {item}")
        if args.release:
            print("release gate: blocked. no upload was attempted.")
            return 1
    elif args.release:
        print("release gate: no blockers recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
