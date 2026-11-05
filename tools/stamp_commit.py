"""Stamp orbitrx/_build_meta.py with the current short SHA (N4).

Usage:
    python tools/stamp_commit.py [SHA]
If SHA is omitted, uses git rev-parse --short HEAD (or ORBITRX_COMMIT_SHA).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "orbitrx" / "_build_meta.py"


def resolve_sha(arg: str | None) -> str:
    if arg:
        return arg.strip()[:12]
    env = (os.environ.get("ORBITRX_COMMIT_SHA") or "").strip()
    if env:
        return env[:12]
    out = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()[:12]


def main(argv: list[str]) -> int:
    sha = resolve_sha(argv[1] if len(argv) > 1 else None)
    META.write_text(
        '"""Build-time metadata. COMMIT_SHA is stamped by tools/stamp_commit.py / CI."""\n'
        f'COMMIT_SHA = "{sha}"\n',
        encoding="utf-8",
    )
    print(f"Stamped COMMIT_SHA={sha} into {META.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
