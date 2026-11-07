"""Scan the PYZ inside an OrbitRx PyInstaller executable.

Usage: scan_pyz.py <exe-or-onedir> <out.txt>

The onedir spec passes the PYZ to EXE() and sets exclude_binaries=True.
The PYZ stays in the executable's CArchive. Qt DLLs and datas, including
ne_110m_dark.png, sit beside that executable and are not inside it.
Pass either dist/OrbitRxMonitor/OrbitRxMonitor.exe or the onedir folder.

One-file archives are not what OrbitRxMonitor.spec builds. This scanner
does not look for a sibling PYZ-00.pyz.
"""
from __future__ import annotations

import sys
import zlib
from pathlib import Path

GATE_MODULE = "orbitrx.ui.rig_wizard"
REQUIRED = [b"ORBITRX_TEST_SIMULATED_RIG", b"is for screenshots/tests only"]


def resolve_scan_target(path: Path) -> Path:
    """Return the executable whose CArchive holds the PYZ."""
    if path.is_dir():
        for name in ("OrbitRxMonitor.exe", "OrbitRxMonitor"):
            candidate = path / name
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(f"{path} is an onedir folder without OrbitRxMonitor.exe")
    return path


def _raw_pyz_modules(exe: Path):
    from PyInstaller.archive.readers import CArchiveReader

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
    exe, out = resolve_scan_target(Path(argv[1])), Path(argv[2])
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
