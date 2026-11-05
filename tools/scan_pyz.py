"""Scan a PyInstaller one-file exe's bundled PYZ for the simulated-rig gate.

Usage: scan_pyz.py <exe> <out.txt>

Opens the exe's CArchive, finds the PYZ, and decompresses the raw marshalled
module data for orbitrx.ui.rig_wizard (no unmarshal, so it works with any
host Python version). Asserts the module contains the gate's environment
variable name and its refusal message, i.e. the gate logic is bundled and the
simulated rig is refused unless ORBITRX_TEST_SIMULATED_RIG=1 is set. Also
reports every bundled module whose code mentions "Simulated rig".
"""
from __future__ import annotations

import sys
import zlib
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

GATE_MODULE = "orbitrx.ui.rig_wizard"
REQUIRED = [b"ORBITRX_TEST_SIMULATED_RIG", b"is for screenshots/tests only"]


def _raw_pyz_modules(exe: Path):
    car = CArchiveReader(str(exe))
    pyz_name = next(n for n, e in car.toc.items() if n.endswith(".pyz") or e[-1] == "z")
    data = car.extract(pyz_name)
    # PYZ layout: magic(4) + pyc magic(4) + toc offset(4, big-endian), then entries.
    import marshal
    toc_off = int.from_bytes(data[8:12], "big")
    toc = marshal.loads(data[toc_off:])
    if isinstance(toc, list):
        toc = dict(toc)
    for name, entry in toc.items():
        typ, off, length = entry[0], entry[1], entry[2]
        if typ in (0, 1, 3):  # module, package, namespace pkg / data
            try:
                yield name, zlib.decompress(data[off:off + length])
            except zlib.error:
                continue


def main(argv: list[str]) -> int:
    exe, out = Path(argv[1]), Path(argv[2])
    lines, found_gate, mentions = [], False, []
    for name, raw in _raw_pyz_modules(exe):
        if b"Simulated rig" in raw:
            mentions.append(name)
        if name == GATE_MODULE:
            found_gate = True
            for needle in REQUIRED:
                ok = needle in raw
                lines.append(f"{GATE_MODULE}: contains {needle.decode()!r}: {ok}")
                if not ok:
                    found_gate = False
    lines.append(f"modules mentioning 'Simulated rig': {mentions}")
    verdict = found_gate and mentions == [GATE_MODULE]
    lines.append("PYZ-SCAN: " + ("PASS (gate bundled; simulated rig only in the gated module)" if verdict else "FAIL"))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
