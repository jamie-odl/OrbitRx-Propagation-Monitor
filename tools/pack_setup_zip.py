"""Pack an OrbitRx installer into a one-member zip.

Default mode is for a future build. It uses the input file's own
modification time. It does not reproduce OrbitRx-Setup-5.1.0.zip.

``--historical-observed`` forces the DOS timestamp, Unix mode and ZIP
versions measured on the published 5.1.0 zip. Together with raw deflate
level 9, that wrapper reproduces

    bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b

when the input is the installer whose SHA-256 is

    4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8

That is a reconstruction of the archive that was downloaded. It is not
a command that was stored in git, and running it on any other bytes
does not claim to be that release.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

HISTORICAL_ZIP_SHA256 = "bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b"
HISTORICAL_EXE_SHA256 = "4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8"
HISTORICAL_DOS_TIME = 20601  # 2026-11-05 10:03:50
HISTORICAL_DOS_DATE = 23909
MEMBER_NAME = b"OrbitRxMonitor-Setup.exe"


def deflate_raw_level9(data: bytes) -> bytes:
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def dos_time_date(when: datetime) -> tuple[int, int]:
    if when.tzinfo is not None:
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    time_value = (when.hour << 11) | (when.minute << 5) | (when.second // 2)
    date_value = ((when.year - 1980) << 9) | (when.month << 5) | when.day
    return time_value, date_value


def zip_stored_observed_layout(data: bytes, dos_time: int, dos_date: int) -> bytes:
    """One-member ZIP: Unix 2.0, mode 0100644, no extra field, raw deflate level 9."""
    name = MEMBER_NAME
    comp = deflate_raw_level9(data)
    crc = zlib.crc32(data) & 0xFFFFFFFF
    local = struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        20,
        0,
        8,
        dos_time,
        dos_date,
        crc,
        len(comp),
        len(data),
        len(name),
        0,
    ) + name + comp
    central = struct.pack(
        "<IHHHHHHIIIHHHHHII",
        0x02014B50,
        0x0314,
        20,
        0,
        8,
        dos_time,
        dos_date,
        crc,
        len(comp),
        len(data),
        len(name),
        0,
        0,
        0,
        0,
        0x81A40000,
        0,
    ) + name
    eocd = struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, 1, 1, len(central), len(local), 0)
    return local + central + eocd


def historical_observed_zip(data: bytes) -> bytes:
    return zip_stored_observed_layout(data, HISTORICAL_DOS_TIME, HISTORICAL_DOS_DATE)


def future_zip(data: bytes, when: datetime) -> bytes:
    dos_time, dos_date = dos_time_date(when)
    return zip_stored_observed_layout(data, dos_time, dos_date)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--historical-observed",
        action="store_true",
        help="Use the 2026-11-05 10:03:50 headers measured on the published zip.",
    )
    args = parser.parse_args(argv)
    data = args.installer.read_bytes()
    if args.historical_observed:
        blob = historical_observed_zip(data)
        print("historical-observed wrapper; this does not create a new release")
    else:
        when = datetime.fromtimestamp(args.installer.stat().st_mtime, timezone.utc)
        blob = future_zip(data, when)
        print("future wrapper; timestamp comes from the input file, not 2026-11-05")
    args.output.write_bytes(blob)
    exe_sha = hashlib.sha256(data).hexdigest()
    zip_sha = hashlib.sha256(blob).hexdigest()
    print(f"installer sha256 {exe_sha}")
    print(f"zip sha256       {zip_sha}")
    if args.historical_observed and exe_sha == HISTORICAL_EXE_SHA256:
        print("known installer: published zip match" if zip_sha == HISTORICAL_ZIP_SHA256 else "KNOWN INSTALLER DID NOT MATCH")
        return 0 if zip_sha == HISTORICAL_ZIP_SHA256 else 1
    if zip_sha == HISTORICAL_ZIP_SHA256 and exe_sha != HISTORICAL_EXE_SHA256:
        print("unexpected collision with the published zip digest", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
