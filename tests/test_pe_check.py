import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pe_check  # noqa: E402


def _fake_pe(security=(0, 0), company="thevenom"):
    data = bytearray(0x400)
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    opt = 0x80 + 24
    struct.pack_into("<H", data, opt, 0x20B)
    base = opt + 112
    struct.pack_into("<I", data, base - 4, 16)
    struct.pack_into("<II", data, base + 8 * 4, *security)
    blob = b""
    for k, v in (("CompanyName", company), ("LegalCopyright", "Copyright (C) 2026 thevenom")):
        key = k.encode("utf-16-le") + b"\0\0"
        while (len(blob) + len(key)) % 4:
            blob += b"\0"
        blob += key
        while len(blob) % 4:
            blob += b"\0"
        blob += v.encode("utf-16-le") + b"\0\0\0\0"
    return bytes(data) + blob


def test_clean_unsigned_exe_passes(tmp_path):
    p = tmp_path / "a.exe"
    p.write_bytes(_fake_pe())
    ok, lines = pe_check.check(p)
    assert ok, lines
    assert "  security_dir rva=0x0 size=0" in lines


def test_bogus_security_entry_fails(tmp_path):
    p = tmp_path / "a.exe"
    p.write_bytes(_fake_pe(security=(0x436B0, 28)))
    assert not pe_check.check(p)[0]


def test_obsidian_publisher_fails(tmp_path):
    p = tmp_path / "a.exe"
    p.write_bytes(_fake_pe(company="Obsidian" + " Dynamics"))
    assert not pe_check.check(p)[0]
