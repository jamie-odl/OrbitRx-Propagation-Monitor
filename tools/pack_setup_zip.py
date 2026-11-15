"""Pack an OrbitRx installer into a zip.

Legacy mode (a bare ``installer`` argument) packs a one-member zip.
Default mode is for a future build: it uses the input file's own
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

That 5 November archive is superseded. The live OrbitRx-Setup-5.1.0.zip
since 9 November 2026 is LIVE_ZIP_SHA256 (onedir plus installer, built
from 9ca6178). This tool does not produce that zip. See docs/SETUP_ZIP.md.

Option-B mode (``--onedir DIR --installer EXE --out ZIP --epoch N``)
builds a two-root zip for a local 5.2.0 build: ``OrbitRxMonitor/`` (the
onedir's contents, unmodified) plus a top-level ``OrbitRxMonitor-Setup.exe``.
It is deterministic -- see ``build_deterministic_zip`` and
``epoch_to_dos_date_time`` below for the exact rules, and
docs/SETUP_ZIP.md for the summary. In short:

* members are files only -- no directory entries are ever written;
* members are sorted by their archive path, compared bytewise on the
  UTF-8, forward-slash-separated name;
* every member is ``ZIP_DEFLATED`` at compresslevel 9;
* every member's DOS date/time is the same fixed value, derived from
  the given epoch expressed in UTC (``time.gmtime``), with the 2-second
  granularity of the DOS format rounded down and dates before
  1980-01-01 clamped forward to it. The stored time is therefore the
  commit time in UTC, not the host's local time zone;
* ``create_system`` (0, MS-DOS/FAT) and ``external_attr`` (0x20, the FAT
  "archive" bit alone -- the value ``zipfile`` itself would give a plain
  file written on Windows, and nonzero so the library's own
  ``_open_to_write`` cannot replace a falsy 0 with a Unix permission
  default) are fixed, not host-derived;
* no extra fields, no archive or per-member comments, no data
  descriptors (the output file is written seekable, so the library
  never falls back to one).

``--verify ZIP`` re-opens an existing zip and checks that shape, optionally
cross-checking it against ``--onedir``/``--installer`` sources.
``--expect-inventory PATH`` (pack mode) compares the zip's
``OrbitRxMonitor/`` member sizes against a CI ``ship-set-inventory.txt``
file, excluding ``OrbitRxMonitor.exe`` (one of the two exes CI's Risk L5
note says to exclude; the other, the installer, is never listed by name
in that file's tab-separated section, so it is excluded by construction).

``--compare-tree DIR --inventory FILE`` (L6) runs that same size
comparison against an already-extracted ``OrbitRxMonitor/`` directory tree
instead of a zip -- used to re-check the zip's contents once more after it
has been unpacked.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import os
import struct
import sys
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

ONEDIR_ROOT_NAME = "OrbitRxMonitor"
ONEDIR_PREFIX = ONEDIR_ROOT_NAME + "/"
INSTALLER_ARCNAME = "OrbitRxMonitor-Setup.exe"
# L5: CI's ship-set-inventory.txt tab-separated listing is rooted at the
# onedir and so includes OrbitRxMonitor.exe, but never OrbitRxMonitor-Setup.exe
# (the installer lives outside that root). Both are excluded from the
# --expect-inventory size comparison; this is the one CI does list.
INVENTORY_EXCLUDED_NAMES = frozenset({"OrbitRxMonitor.exe"})
# FAT "archive" attribute bit only. Must be nonzero: zipfile's own
# _open_to_write() treats a falsy external_attr as "unset" and replaces it
# with a Unix permission default (0o600 << 16), which would make the
# output depend on that library behaviour rather than on this fixed value.
FIXED_EXTERNAL_ATTR = 0x20


class PackError(Exception):
    """Fail closed: anything that would make the zip non-deterministic or
    unsafe (a symlink, a missing epoch, a layout mismatch) raises this
    instead of silently proceeding."""

# Live public 5.1.0 zip since 9 Nov 2026 (not produced by this tool).
LIVE_ZIP_SHA256 = "d6a3aebf3c79389949ce3ca4abe2b865fe6d1ce4346aa409ba610b053c609c6f"
# Superseded 5 Nov 2026 installer-only archive.
HISTORICAL_ZIP_SHA256 = "bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b"
HISTORICAL_EXE_SHA256 = "4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8"
HISTORICAL_DOS_TIME = 20601  # 2026-11-05 10:03:50
HISTORICAL_DOS_DATE = 23909
MEMBER_NAME = b"OrbitRxMonitor-Setup.exe"
ROOT = Path(__file__).resolve().parents[1]


def default_zip_name(version: str) -> str:
    return f"OrbitRx-Setup-{version}.zip"


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


def _run_legacy(args: argparse.Namespace) -> int:
    if args.output is None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        args.output = Path(default_zip_name(version))
    data = args.legacy_installer.read_bytes()
    if args.historical_observed:
        blob = historical_observed_zip(data)
        print("historical-observed wrapper; this does not create a new release")
    else:
        when = datetime.fromtimestamp(args.legacy_installer.stat().st_mtime, timezone.utc)
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


# --- Option-B: deterministic two-root zip (onedir + installer) -------------

# 1980-01-01 00:00:00 UTC: the earliest date the ZIP DOS format can represent.
DOS_EPOCH = 315532800
# 2107-12-31 23:59:59 UTC: the latest date it can represent (the DOS date's
# year field is 7 bits, 1980 + 127 = 2107). ``calendar.timegm`` is pure
# arithmetic -- unlike ``time.gmtime``/``datetime.fromtimestamp`` it never
# makes a platform time_t call, so computing this bound can't itself hit the
# same kind of OSError this clamp exists to avoid.
DOS_EPOCH_MAX = calendar.timegm((2107, 12, 31, 23, 59, 59, 0, 0, 0))


def epoch_to_dos_date_time(epoch: int) -> tuple[int, int, int, int, int, int]:
    """UTC (GMT) DOS date/time for ``epoch``, used as the single fixed
    timestamp for every member. DOS time stores seconds // 2, so an odd
    second is rounded down here explicitly (rather than relying on the
    zipfile module to truncate it); the epoch is clamped forward to
    DOS_EPOCH (1980-01-01 00:00:00 UTC, the earliest date the ZIP format
    can represent) *before* it reaches ``time.gmtime`` -- some platforms
    (observed on windows-latest CI) raise OSError out of ``gmtime`` for a
    negative value, so the clamp cannot be applied to its result. Epochs
    past the last representable DOS date (2107-12-31 23:59:59 UTC, the
    7-bit year field's limit) fail closed with ValueError rather than
    risking the same kind of platform error for an out-of-range high
    value. ``time.gmtime`` is used, not the host's local time zone, so
    this value never depends on where the build runs."""
    if epoch < DOS_EPOCH:
        epoch = DOS_EPOCH
    elif epoch > DOS_EPOCH_MAX:
        raise ValueError(
            f"epoch {epoch} is after 2107-12-31 23:59:59 UTC, the latest "
            "date the ZIP DOS format can represent"
        )
    t = time.gmtime(epoch)
    return (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec - (t.tm_sec % 2))


def _parse_int_epoch(label: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise PackError(f"{label} must be an integer, got {raw!r}") from None


def resolve_optional_epoch(epoch: str | None, source_date_epoch: str | None) -> int | None:
    """Resolve --epoch / --source-date-epoch / $SOURCE_DATE_EPOCH (in that
    priority order) to an int, or None if none were given. Never lets a raw
    ``int()`` ``ValueError`` escape -- every bad value is reported as a
    ``PackError`` with a clean message instead."""
    for label, raw in (("--epoch", epoch), ("--source-date-epoch", source_date_epoch)):
        if raw is not None:
            return _parse_int_epoch(label, raw)
    env = os.environ.get("SOURCE_DATE_EPOCH")
    if env:
        return _parse_int_epoch("SOURCE_DATE_EPOCH", env)
    return None


def resolve_epoch(epoch: str | None, source_date_epoch: str | None) -> int:
    value = resolve_optional_epoch(epoch, source_date_epoch)
    if value is None:
        raise PackError(
            "an epoch is required for a deterministic pack: pass --epoch, "
            "--source-date-epoch, or set SOURCE_DATE_EPOCH"
        )
    return value


def _is_reparse_point(path: Path) -> bool:
    """True for a Windows junction or any other reparse point. Checked
    separately from ``Path.is_symlink()`` because a directory junction is
    not reported as a symlink by Python before 3.12 (and not always even on
    3.12+ -- ``os.path.isjunction`` and the raw attribute bit are both
    checked, so this is robust either way (N10)."""
    try:
        if hasattr(os.path, "isjunction") and os.path.isjunction(path):
            return True
    except OSError:
        pass
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is not None:
        FILE_ATTRIBUTE_REPARSE_POINT = 0x400
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    return False


def _reject_non_regular(path: Path) -> None:
    if path.is_symlink():
        raise PackError(f"refusing to pack a symlink: {path}")
    if _is_reparse_point(path):
        raise PackError(f"refusing to pack a junction/reparse point: {path}")
    if not path.is_file():
        raise PackError(f"refusing to pack a non-regular file: {path}")


def collect_onedir_members(onedir: Path) -> list[tuple[str, Path]]:
    """``(archive_path, source_path)`` pairs for every file under
    ``onedir``, archive paths prefixed with ``OrbitRxMonitor/``. Symlinks
    and junctions/reparse points (files or directories) and anything that is
    not a regular file are rejected, not silently skipped (N10)."""
    if onedir.is_symlink() or _is_reparse_point(onedir) or not onedir.is_dir():
        raise PackError(f"not a directory: {onedir}")
    members: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(onedir, followlinks=False):
        base = Path(dirpath)
        for name in dirnames:
            full = base / name
            if full.is_symlink():
                raise PackError(f"refusing to pack a symlinked directory: {full}")
            if _is_reparse_point(full):
                raise PackError(f"refusing to pack a junction/reparse point directory: {full}")
        for name in filenames:
            full = base / name
            _reject_non_regular(full)
            rel = full.relative_to(onedir).as_posix()
            members.append((ONEDIR_PREFIX + rel, full))
    return members


def build_deterministic_zip(
    onedir: Path, installer: Path, out_path: Path, epoch: int
) -> list[tuple[str, Path]]:
    """Write the Option-B zip and return the sorted ``(archive_path,
    source_path)`` members that were packed. See the module docstring for
    the determinism rules this enforces."""
    _reject_non_regular(installer)
    members = collect_onedir_members(onedir)
    members.append((INSTALLER_ARCNAME, installer))
    members.sort(key=lambda m: m[0].encode("utf-8"))
    date_time = epoch_to_dos_date_time(epoch)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", allowZip64=True) as zf:
        zf.comment = b""
        for arcname, src in members:
            data = src.read_bytes()
            info = zipfile.ZipInfo(arcname, date_time=date_time)
            info.create_system = 0    # MS-DOS/FAT: fixed, not host-derived (this ships to Windows).
            info.create_version = 20  # Deflate's minimum version; fixed.
            info.extract_version = 20
            info.external_attr = FIXED_EXTERNAL_ATTR
            info.comment = b""
            info.extra = b""
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return members


def verify_zip_layout(zip_path: Path, expect_epoch: int | None = None) -> list[str]:
    """Check that ``zip_path`` has exactly the Option-B shape: the two
    roots, no directory entries, a single fixed timestamp (optionally
    checked against ``expect_epoch``), and the fixed attrs/fields
    ``build_deterministic_zip`` writes. Returns a list of problems; empty
    means the zip passes."""
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            problems.append("duplicate member names")
        if names != sorted(names, key=lambda n: n.encode("utf-8")):
            problems.append("members are not sorted by their bytewise UTF-8 archive path")
        expected_dt = epoch_to_dos_date_time(expect_epoch) if expect_epoch is not None else None
        seen_dts: set[tuple[int, int, int, int, int, int]] = set()
        saw_installer = False
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                problems.append(f"directory entry present: {name}")
                continue
            if name == INSTALLER_ARCNAME:
                saw_installer = True
            elif not (name.startswith(ONEDIR_PREFIX) and len(name) > len(ONEDIR_PREFIX)):
                problems.append(f"unexpected root entry: {name}")
            if info.compress_type != zipfile.ZIP_DEFLATED:
                problems.append(f"{name}: not ZIP_DEFLATED")
            if info.create_system != 0:
                problems.append(f"{name}: create_system {info.create_system} != 0")
            if info.external_attr != FIXED_EXTERNAL_ATTR:
                problems.append(
                    f"{name}: external_attr 0x{info.external_attr:x} != 0x{FIXED_EXTERNAL_ATTR:x}"
                )
            if info.extra:
                problems.append(f"{name}: has an extra field")
            if info.comment:
                problems.append(f"{name}: has a per-member comment")
            seen_dts.add(info.date_time)
            if expected_dt is not None and info.date_time != expected_dt:
                problems.append(f"{name}: date_time {info.date_time} != expected {expected_dt}")
        if not saw_installer:
            problems.append(f"{INSTALLER_ARCNAME} is missing from the zip root")
        if len(seen_dts) > 1:
            problems.append(f"members do not share one fixed timestamp: {sorted(seen_dts)}")
        if zf.comment:
            problems.append("zip has an archive comment")
        bad_member = zf.testzip()
        if bad_member is not None:
            problems.append(f"CRC check failed for {bad_member}")
    return problems


def verify_against_sources(zip_path: Path, onedir: Path, installer: Path) -> list[str]:
    """Cross-check ``zip_path``'s member names and sizes against the exact
    onedir tree and installer it is supposed to contain."""
    _reject_non_regular(installer)
    expected_members = collect_onedir_members(onedir)
    expected_members.append((INSTALLER_ARCNAME, installer))
    expected = {name: src.stat().st_size for name, src in expected_members}
    with zipfile.ZipFile(zip_path) as zf:
        actual = {info.filename: info.file_size for info in zf.infolist()}
    problems: list[str] = []
    for rel in sorted(set(expected) - set(actual)):
        problems.append(f"missing from zip: {rel} (expected {expected[rel]} bytes)")
    for rel in sorted(set(actual) - set(expected)):
        problems.append(f"unexpected in zip: {rel} ({actual[rel]} bytes)")
    for rel in sorted(set(expected) & set(actual)):
        if expected[rel] != actual[rel]:
            problems.append(f"size mismatch for {rel}: zip has {actual[rel]}, source has {expected[rel]}")
    return problems


def parse_ci_inventory(path: Path) -> dict[str, int]:
    """Parse the tab-separated ``relpath<TAB>size`` lines CI's
    "Ship-set inventory" step writes into ship-set-inventory.txt (see
    .github/workflows/ci.yml). Other lines in that file (the version/commit
    header, the SHA256SUMS.txt lines, the OpenSSL DLL report lines) contain
    no tab character and are ignored here.

    L-4a/b: a missing file, any other OSError (permission denied, a
    directory passed by mistake, ...) or a file that is not valid UTF-8
    fails closed with a clean PackError, not a traceback -- this is read
    both by the pack-mode --expect-inventory path and by --compare-tree,
    and both call sites must exit 1 with a message, not crash."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PackError(f"ship-set-inventory file not found: {path}") from None
    except UnicodeDecodeError as exc:
        raise PackError(f"ship-set-inventory file {path} is not valid UTF-8: {exc}") from None
    except OSError as exc:
        raise PackError(f"could not read ship-set-inventory file {path}: {exc}") from None
    entries: dict[str, int] = {}
    for line in text.splitlines():
        if "\t" not in line:
            continue
        rel, _, size_text = line.rpartition("\t")
        if rel and size_text.isdigit():
            entries[rel] = int(size_text)
    return entries


def zip_onedir_sizes(zip_path: Path) -> dict[str, int]:
    sizes: dict[str, int] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.filename.startswith(ONEDIR_PREFIX):
                rel = info.filename[len(ONEDIR_PREFIX):]
                if rel:
                    sizes[rel] = info.file_size
    return sizes


def _exclude_shipped_exes(sizes: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in sizes.items() if k not in INVENTORY_EXCLUDED_NAMES}


def _diff_sizes(expected: dict[str, int], actual: dict[str, int], actual_label: str) -> list[str]:
    problems: list[str] = []
    for rel in sorted(set(expected) - set(actual)):
        problems.append(f"missing from {actual_label}: {rel} (inventory has {expected[rel]} bytes)")
    for rel in sorted(set(actual) - set(expected)):
        problems.append(f"not in inventory: {rel} ({actual_label} has {actual[rel]} bytes)")
    for rel in sorted(set(expected) & set(actual)):
        if expected[rel] != actual[rel]:
            problems.append(
                f"size mismatch for {rel}: {actual_label} has {actual[rel]}, inventory has {expected[rel]}"
            )
    return problems


def compare_inventory(zip_path: Path, inventory_path: Path) -> list[str]:
    """L5: compare the zip's ``OrbitRxMonitor/`` member sizes against a
    CI-produced ship-set-inventory.txt, excluding the two shipped exes (see
    INVENTORY_EXCLUDED_NAMES and the module docstring)."""
    expected = _exclude_shipped_exes(parse_ci_inventory(inventory_path))
    actual = _exclude_shipped_exes(zip_onedir_sizes(zip_path))
    return _diff_sizes(expected, actual, "zip")


def tree_file_sizes(root: Path) -> dict[str, int]:
    """``relpath -> size`` for every regular file under ``root``, using the
    same forward-slash-separated, root-relative convention as the zip's
    ``OrbitRxMonitor/`` member names and the CI inventory file."""
    sizes: dict[str, int] = {}
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in filenames:
            full = base / name
            sizes[full.relative_to(root).as_posix()] = full.stat().st_size
    return sizes


def compare_tree_to_inventory(root: Path, inventory_path: Path) -> list[str]:
    """L6: compare an extracted ``OrbitRxMonitor/`` directory tree's
    relative file list and sizes against a ship-set-inventory.txt, excluding
    the two shipped exes (see INVENTORY_EXCLUDED_NAMES and compare_inventory
    above, which does the same comparison against a zip instead of a
    directory)."""
    expected = _exclude_shipped_exes(parse_ci_inventory(inventory_path))
    actual = _exclude_shipped_exes(tree_file_sizes(root))
    return _diff_sizes(expected, actual, "tree")


def _run_pack(args: argparse.Namespace) -> int:
    if args.onedir is None or args.installer is None or args.out is None:
        print("--onedir, --installer and --out are all required together", file=sys.stderr)
        return 2
    # NEW-2 / L-4a,c: never leave a ready-made zip at the final name unless
    # it has already passed verify_zip_layout and (when given) the L5
    # --expect-inventory compare. Build and check it at "<out>.partial"
    # first; only os.replace() it to args.out once every check has passed.
    # A pre-existing final zip (or a stale partial left by an earlier,
    # interrupted attempt) is deleted before a pack starts, so a failed run
    # never leaves an *earlier* zip sitting under the final name either.
    # The partial is deleted in `finally` so it is never left behind for
    # ANY exception along the way, not just the ones this function
    # anticipates with an explicit except clause.
    partial_path = args.out.with_name(args.out.name + ".partial")
    args.out.unlink(missing_ok=True)
    partial_path.unlink(missing_ok=True)
    try:
        try:
            epoch = resolve_epoch(args.epoch, args.source_date_epoch)
            build_deterministic_zip(args.onedir, args.installer, partial_path, epoch)
            problems = verify_zip_layout(partial_path, expect_epoch=epoch)
            if not problems and args.expect_inventory is not None:
                problems = compare_inventory(partial_path, args.expect_inventory)
                inventory_checked = True
            else:
                inventory_checked = False
        except (PackError, ValueError) as exc:
            print(f"pack failed: {exc}", file=sys.stderr)
            return 1
        if problems:
            if inventory_checked:
                print(f"ship-set-inventory mismatch against {args.expect_inventory}:", file=sys.stderr)
            else:
                print("post-write verification failed:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        os.replace(partial_path, args.out)
    finally:
        partial_path.unlink(missing_ok=True)
    with zipfile.ZipFile(args.out) as zf:
        member_count = len(zf.namelist())
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"wrote {args.out} ({member_count} members)")
    print(f"sha256 {digest}")
    if args.expect_inventory is not None:
        print(f"ship-set-inventory match: {args.expect_inventory}")
    return 0


def _run_compare_tree(args: argparse.Namespace) -> int:
    if args.inventory is None:
        print("--compare-tree requires --inventory", file=sys.stderr)
        return 2
    if not args.compare_tree.is_dir():
        print(f"--compare-tree directory not found: {args.compare_tree}", file=sys.stderr)
        return 1
    try:
        problems = compare_tree_to_inventory(args.compare_tree, args.inventory)
    except (PackError, ValueError) as exc:
        print(f"pack failed: {exc}", file=sys.stderr)
        return 1
    if problems:
        print(f"tree/inventory mismatch for {args.compare_tree} against {args.inventory}:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"tree matches inventory: {args.compare_tree}")
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    try:
        expect_epoch = resolve_optional_epoch(args.epoch, args.source_date_epoch)
        problems = verify_zip_layout(args.verify, expect_epoch=expect_epoch)
    except (PackError, ValueError, OSError, zipfile.BadZipFile) as exc:
        # L-4b: a missing or unreadable zip (OSError from zipfile.ZipFile's
        # own open, or zipfile.BadZipFile for one that opens but is not a
        # valid archive) must exit 1 cleanly here too, not raise past this
        # function as a traceback.
        print(f"verify failed for {args.verify}: {exc}", file=sys.stderr)
        return 1
    if (args.onedir is None) != (args.installer is None):
        problems.append("--verify needs --onedir and --installer together, or neither")
    elif args.onedir is not None and args.installer is not None:
        problems += verify_against_sources(args.verify, args.onedir, args.installer)
    if problems:
        print(f"verify failed for {args.verify}:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"verify ok: {args.verify}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "legacy_installer", metavar="installer", type=Path, nargs="?", default=None,
        help="Legacy one-member mode: path to OrbitRxMonitor-Setup.exe.",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Legacy mode output. Defaults to OrbitRx-Setup-<VERSION>.zip in the current directory.",
    )
    parser.add_argument(
        "--historical-observed", action="store_true",
        help="Legacy mode: use the 2026-11-05 10:03:50 headers measured on the published zip.",
    )
    parser.add_argument("--onedir", type=Path, default=None, help="Option-B: the PyInstaller onedir root.")
    parser.add_argument("--installer", type=Path, default=None, help="Option-B: the installer exe.")
    parser.add_argument("--out", type=Path, default=None, help="Option-B: output zip path.")
    parser.add_argument(
        "--epoch", type=str, default=None,
        help="Option-B: unix seconds, e.g. commit time. Validated as an integer by this "
        "tool (not by argparse), so a bad value fails closed with a clean message "
        "in every mode, not a traceback.",
    )
    parser.add_argument(
        "--source-date-epoch", dest="source_date_epoch", type=str, default=None,
        help="Option-B: same as --epoch; also read from $SOURCE_DATE_EPOCH if neither is given.",
    )
    parser.add_argument(
        "--expect-inventory", type=Path, default=None,
        help="Option-B pack mode: fail unless this matches a CI ship-set-inventory.txt (L5).",
    )
    parser.add_argument(
        "--verify", type=Path, default=None, metavar="ZIP",
        help="Verify mode: check ZIP's layout instead of packing.",
    )
    parser.add_argument(
        "--compare-tree", type=Path, default=None, metavar="DIR",
        help="L6: compare DIR (an extracted OrbitRxMonitor/ tree) against --inventory instead of packing.",
    )
    parser.add_argument(
        "--inventory", type=Path, default=None, metavar="FILE",
        help="Used with --compare-tree: a ship-set-inventory.txt to compare DIR against.",
    )
    args = parser.parse_args(argv)

    if args.compare_tree is not None:
        return _run_compare_tree(args)
    if args.verify is not None:
        return _run_verify(args)
    if args.onedir is not None or args.installer is not None or args.out is not None:
        return _run_pack(args)
    if args.legacy_installer is None:
        parser.error("installer is required (or use --onedir/--installer/--out, or --verify)")
    return _run_legacy(args)


if __name__ == "__main__":
    raise SystemExit(main())
