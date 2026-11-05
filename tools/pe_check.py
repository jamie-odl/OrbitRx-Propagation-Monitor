"""Report PE security-directory and VersionInfo fields for unsigned release exes.

Usage: python tools/pe_check.py OUT.txt EXE [EXE ...]
Fails (exit 1) unless every exe has IMAGE_DIRECTORY_ENTRY_SECURITY = 0/0,
CompanyName "Jamie Sibley" and no "Obsidian" anywhere in its version strings.
Pure-stdlib parser so it runs on any CI runner.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path


def data_directories(data: bytes) -> list[tuple[int, int]]:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    base = opt + (112 if magic == 0x20B else 96)
    count = struct.unpack_from("<I", data, base - 4)[0]
    return [struct.unpack_from("<II", data, base + 8 * i) for i in range(count)]


def version_string(data: bytes, key: str) -> str | None:
    needle = key.encode("utf-16-le") + b"\0\0"
    i = data.find(needle)
    if i < 0:
        return None
    j = i + len(needle)
    while j % 4:
        j += 1
    end = data.find(b"\0\0", j)
    while end >= 0 and (end - j) % 2:
        end = data.find(b"\0\0", end + 1)
    return data[j:end].decode("utf-16-le", "replace").strip()


def check(path: Path) -> tuple[bool, list[str]]:
    data = path.read_bytes()
    dirs = data_directories(data)
    sec = dirs[4] if len(dirs) > 4 else (0, 0)
    dbg = dirs[6] if len(dirs) > 6 else (0, 0)
    fields = {k: version_string(data, k) for k in
              ("CompanyName", "LegalCopyright", "ProductName", "FileVersion")}
    obsidian = b"Obsidian".decode() in " ".join(v or "" for v in fields.values())
    lines = [f"{path.name}:",
             f"  security_dir rva=0x{sec[0]:x} size={sec[1]}",
             f"  debug_dir rva=0x{dbg[0]:x} size={dbg[1]} (CodeView debug entry, not a signature)"]
    lines += [f"  {k}={v}" for k, v in fields.items()]
    ok = sec == (0, 0) and fields["CompanyName"] == "Jamie Sibley" and not obsidian
    lines.append(f"  RESULT: {'PASS' if ok else 'FAIL'}")
    return ok, lines


def main(argv: list[str]) -> int:
    out, exes = Path(argv[1]), [Path(a) for a in argv[2:]]
    allok, report = True, []
    for exe in exes:
        ok, lines = check(exe)
        allok &= ok
        report += lines
    report.append(f"PE-CHECK: {'PASS' if allok else 'FAIL'}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
