"""Determinism tests for tools/pack_setup_zip.py's Option-B mode (two-root
zip: OrbitRxMonitor/ onedir + OrbitRxMonitor-Setup.exe installer).

Pure stdlib, synthetic bytes only -- no real PE binaries are built or
downloaded. Must pass on ubuntu-latest and windows-latest.
"""

from __future__ import annotations

import calendar
import hashlib
import os
import struct
import sys
import time
import zipfile
from pathlib import Path

import pytest

from tools.pack_setup_zip import (
    FIXED_EXTERNAL_ATTR,
    INSTALLER_ARCNAME,
    ONEDIR_PREFIX,
    PackError,
    build_deterministic_zip,
    collect_onedir_members,
    compare_inventory,
    compare_tree_to_inventory,
    epoch_to_dos_date_time,
    main,
    parse_ci_inventory,
    verify_zip_layout,
)

EPOCH = 1731456789  # arbitrary fixed "commit time", used as SOURCE_DATE_EPOCH throughout


def _make_onedir(root: Path) -> Path:
    onedir = root / "OrbitRxMonitor"
    (onedir / "_internal" / "nested").mkdir(parents=True)
    (onedir / "a.txt").write_bytes(b"alpha file contents\n")
    (onedir / "_internal" / "b.bin").write_bytes(bytes(range(256)))
    (onedir / "_internal" / "nested" / "c.dat").write_bytes(b"c" * 1000)
    return onedir


def _make_installer(root: Path) -> Path:
    installer = root / "installer" / "OrbitRxMonitor-Setup.exe"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"FAKE-NOT-A-REAL-PE-INSTALLER-PAYLOAD\x00" * 10)
    return installer


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pack(tmp_path: Path, onedir: Path, installer: Path, name: str, epoch: int = EPOCH) -> Path:
    out = tmp_path / name
    build_deterministic_zip(onedir, installer, out, epoch)
    return out


# --- byte-identity invariants -----------------------------------------------


def test_two_runs_are_byte_identical(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out1 = _pack(tmp_path, onedir, installer, "out1.zip")
    out2 = _pack(tmp_path, onedir, installer, "out2.zip")
    assert _sha256(out1) == _sha256(out2)


def test_byte_identity_is_independent_of_mtimes(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    baseline = _pack(tmp_path, onedir, installer, "baseline.zip")

    now = time.time()
    for path in [*onedir.rglob("*"), installer]:
        if path.is_file():
            os.utime(path, (now - 999999, now - 12345))

    touched = _pack(tmp_path, onedir, installer, "touched.zip")
    assert _sha256(baseline) == _sha256(touched)


def test_byte_identity_is_independent_of_file_creation_order(tmp_path):
    installer = _make_installer(tmp_path)

    forward = tmp_path / "forward" / "OrbitRxMonitor"
    (forward / "_internal" / "nested").mkdir(parents=True)
    (forward / "a.txt").write_bytes(b"alpha file contents\n")
    (forward / "_internal" / "b.bin").write_bytes(bytes(range(256)))
    (forward / "_internal" / "nested" / "c.dat").write_bytes(b"c" * 1000)

    reverse = tmp_path / "reverse" / "OrbitRxMonitor"
    (reverse / "_internal" / "nested").mkdir(parents=True)
    (reverse / "_internal" / "nested" / "c.dat").write_bytes(b"c" * 1000)
    (reverse / "_internal" / "b.bin").write_bytes(bytes(range(256)))
    (reverse / "a.txt").write_bytes(b"alpha file contents\n")

    out_forward = _pack(tmp_path, forward, installer, "forward.zip")
    out_reverse = _pack(tmp_path, reverse, installer, "reverse.zip")
    assert _sha256(out_forward) == _sha256(out_reverse)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod/umask semantics are POSIX-only")
def test_byte_identity_is_independent_of_permissions_and_umask(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    baseline = _pack(tmp_path, onedir, installer, "baseline.zip")

    old_umask = os.umask(0o077)
    try:
        for path in [*onedir.rglob("*"), installer]:
            if path.is_file():
                os.chmod(path, 0o640)
    finally:
        os.umask(old_umask)

    changed = _pack(tmp_path, onedir, installer, "changed.zip")
    assert _sha256(baseline) == _sha256(changed)


def test_byte_identity_is_independent_of_absolute_input_location(tmp_path):
    onedir_a = _make_onedir(tmp_path / "location-one" / "deep" / "path")
    installer_a = _make_installer(tmp_path / "location-one" / "deep" / "path")
    onedir_b = _make_onedir(tmp_path / "somewhere-else-entirely")
    installer_b = _make_installer(tmp_path / "somewhere-else-entirely")

    out_a = _pack(tmp_path, onedir_a, installer_a, "a.zip")
    out_b = _pack(tmp_path, onedir_b, installer_b, "b.zip")
    assert _sha256(out_a) == _sha256(out_b)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="time.tzset is POSIX-only")
def test_byte_identity_is_independent_of_host_timezone(tmp_path, monkeypatch):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)

    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    utc_zip = _pack(tmp_path, onedir, installer, "utc.zip")

    monkeypatch.setenv("TZ", "Pacific/Kiritimati")  # UTC+14, far from UTC
    time.tzset()
    try:
        other_zip = _pack(tmp_path, onedir, installer, "other.zip")
    finally:
        monkeypatch.delenv("TZ", raising=False)
        time.tzset()

    assert _sha256(utc_zip) == _sha256(other_zip)


# --- layout / shape invariants ----------------------------------------------


def test_entries_sorted_no_dir_entries_fixed_attrs_and_deflate(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    expected_dt = epoch_to_dos_date_time(EPOCH)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        assert names == sorted(names, key=lambda n: n.encode("utf-8"))
        assert not any(n.endswith("/") for n in names)
        for info in zf.infolist():
            assert info.extra == b""
            assert info.comment == b""
            assert info.date_time == expected_dt
            assert info.create_system == 0
            assert info.create_version == 20
            assert info.extract_version == 20
            assert info.external_attr == FIXED_EXTERNAL_ATTR
            assert info.compress_type == zipfile.ZIP_DEFLATED
        assert zf.comment == b""
        assert zf.testzip() is None


def test_zip_root_is_exactly_onedir_prefix_plus_installer(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    expected = {
        INSTALLER_ARCNAME,
        f"{ONEDIR_PREFIX}a.txt",
        f"{ONEDIR_PREFIX}_internal/b.bin",
        f"{ONEDIR_PREFIX}_internal/nested/c.dat",
    }
    assert names == expected
    assert verify_zip_layout(out, expect_epoch=EPOCH) == []


def test_symlinks_are_rejected(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    link = onedir / "link.txt"
    try:
        link.symlink_to(onedir / "a.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported/permitted in this environment")

    with pytest.raises(Exception):
        build_deterministic_zip(onedir, installer, tmp_path / "out.zip", EPOCH)


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows-only concept (N10)")
def test_windows_junction_directory_is_rejected(tmp_path):
    import subprocess

    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    target = tmp_path / "junction-target"
    target.mkdir()
    (target / "inside.txt").write_bytes(b"should never be packed\n")
    junction = onedir / "_internal" / "linked"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"mklink /J unavailable or refused: {result.stderr.strip()}")

    with pytest.raises(Exception):
        build_deterministic_zip(onedir, installer, tmp_path / "out.zip", EPOCH)


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows-only concept (N10)")
def test_windows_junction_as_onedir_root_is_rejected(tmp_path):
    import subprocess

    real_onedir = _make_onedir(tmp_path / "real")
    installer = _make_installer(tmp_path)
    junction_root = tmp_path / "OrbitRxMonitor-junction"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction_root), str(real_onedir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"mklink /J unavailable or refused: {result.stderr.strip()}")

    with pytest.raises(Exception):
        build_deterministic_zip(junction_root, installer, tmp_path / "out.zip", EPOCH)


# --- epoch rounding / clamping ------------------------------------------------


def test_odd_epoch_rounds_down_to_an_even_second():
    odd = epoch_to_dos_date_time(1700000005)  # ends in an odd second
    even = epoch_to_dos_date_time(1700000004)  # one second earlier, even
    assert odd == even
    assert odd[5] % 2 == 0


def test_pre_1980_epoch_clamps_to_the_dos_epoch():
    assert epoch_to_dos_date_time(0) == (1980, 1, 1, 0, 0, 0)  # pre-1980, positive epoch
    assert epoch_to_dos_date_time(-100000) == (1980, 1, 1, 0, 0, 0)  # negative epoch
    assert epoch_to_dos_date_time(315532799) == (1980, 1, 1, 0, 0, 0)  # one second before
    assert epoch_to_dos_date_time(315532800) == (1980, 1, 1, 0, 0, 0)  # exactly at it


def test_far_negative_epoch_does_not_reach_gmtime_unclamped():
    # Regression: windows-latest's gmtime() raises OSError for a negative
    # value, so the clamp must happen on the int epoch before gmtime runs,
    # not on its result.
    assert epoch_to_dos_date_time(-(2**31)) == (1980, 1, 1, 0, 0, 0)


def test_out_of_range_high_epoch_raises_value_error():
    # One second past the last date the DOS year field (7 bits, 1980-2107)
    # can represent.
    too_high = calendar.timegm((2108, 1, 1, 0, 0, 0, 0, 0, 0))
    with pytest.raises(ValueError):
        epoch_to_dos_date_time(too_high)
    # The boundary itself must still succeed.
    assert epoch_to_dos_date_time(too_high - 1) == (2107, 12, 31, 23, 59, 58)


# --- --expect-inventory -------------------------------------------------------


def _write_inventory(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_expect_inventory_passes_on_a_matching_inventory(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "aaaa  OrbitRxMonitor.exe",
        "bbbb  OrbitRxMonitor-Setup.exe",
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    assert compare_inventory(out, inventory) == []


def test_expect_inventory_fails_on_a_size_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t999",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    problems = compare_inventory(out, inventory)
    assert any("size mismatch" in p and "a.txt" in p for p in problems)


def test_expect_inventory_fails_on_a_name_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
        "_internal/nested/not-really-there.dat\t5",
    ])
    problems = compare_inventory(out, inventory)
    assert any("missing from zip" in p and "not-really-there.dat" in p for p in problems)


def test_expect_inventory_excludes_both_shipped_exes(tmp_path):
    """OrbitRxMonitor.exe is in the inventory's tab-separated listing (it
    lives inside the onedir CI's inventory step walks); OrbitRxMonitor-Setup.exe
    never is (it lives outside that root). Neither is compared."""
    onedir = _make_onedir(tmp_path)
    (onedir / "OrbitRxMonitor.exe").write_bytes(b"x" * 42)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "OrbitRxMonitor.exe\t999999",  # deliberately wrong size: must be ignored
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    assert compare_inventory(out, inventory) == []


def test_expect_inventory_cli_mode_exits_nonzero_on_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, ["a.txt\t999"])

    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH), "--expect-inventory", str(inventory),
    ])
    assert rc == 1


# --- NEW-2: an inventory mismatch (or any other pack-mode failure) must
# leave neither the final zip name nor its "<out>.partial" scratch file on
# disk -- a caller must never be able to mistake a half-checked pack for a
# good one. ---------------------------------------------------------------


def test_expect_inventory_mismatch_leaves_no_final_zip_and_no_partial(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, ["a.txt\t999"])  # deliberately wrong size

    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH), "--expect-inventory", str(inventory),
    ])
    assert rc == 1
    assert not out.exists(), "final zip must not exist after an inventory mismatch"
    assert not out.with_name(out.name + ".partial").exists(), "partial scratch file must be cleaned up"


def test_a_stale_partial_from_a_failed_attempt_does_not_survive_a_later_success(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    partial = out.with_name(out.name + ".partial")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, ["a.txt\t999"])
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH), "--expect-inventory", str(inventory),
    ])
    assert rc == 1
    assert not partial.exists()

    # A subsequent successful pack (no --expect-inventory) must still
    # succeed and must not leave the scratch file behind either.
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH),
    ])
    assert rc == 0
    assert out.exists()
    assert not partial.exists()


def test_post_write_verification_failure_leaves_no_final_zip_and_no_partial(tmp_path, monkeypatch):
    import tools.pack_setup_zip as pack_module

    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"

    monkeypatch.setattr(pack_module, "verify_zip_layout", lambda *a, **k: ["synthetic problem"])
    rc = pack_module.main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH),
    ])
    assert rc == 1
    assert not out.exists()
    assert not out.with_name(out.name + ".partial").exists()


def test_run_pack_always_builds_at_the_partial_path_not_the_final_name(tmp_path, monkeypatch):
    # N2d: the specific mutant to kill -- build_deterministic_zip pointed at
    # args.out directly instead of "<out>.partial". Spy on the real
    # function's out_path argument (not just the end state) so the mutant
    # is caught even if some other step would coincidentally also leave the
    # final name absent.
    import tools.pack_setup_zip as pack_module

    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    partial = out.with_name(out.name + ".partial")

    real_build = pack_module.build_deterministic_zip
    seen_out_paths = []

    def spy(onedir_arg, installer_arg, out_path, epoch):
        seen_out_paths.append(out_path)
        return real_build(onedir_arg, installer_arg, out_path, epoch)

    monkeypatch.setattr(pack_module, "build_deterministic_zip", spy)
    rc = pack_module.main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH),
    ])
    assert rc == 0
    assert seen_out_paths == [partial]
    assert out.exists()
    assert not partial.exists()


def test_a_pre_existing_final_zip_is_removed_even_when_the_new_pack_fails(tmp_path):
    # L-4a/c: a stale zip from an earlier successful pack must not survive
    # under the final name after a *later* failed attempt at the same path.
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    out.write_bytes(b"stale zip bytes from an earlier successful pack")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, ["a.txt\t999"])  # deliberately wrong size
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH), "--expect-inventory", str(inventory),
    ])
    assert rc == 1
    assert not out.exists(), "a failed re-pack must not leave an earlier zip under the final name"
    assert not out.with_name(out.name + ".partial").exists()


def test_a_stale_pre_existing_partial_is_removed_before_a_fresh_pack_starts(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    partial = out.with_name(out.name + ".partial")
    partial.write_bytes(b"stale partial bytes from a crashed earlier run")

    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH),
    ])
    assert rc == 0
    assert out.exists()
    assert not partial.exists()
    # The stale bytes must not have ended up inside the real zip somehow.
    with zipfile.ZipFile(out) as zf:
        assert INSTALLER_ARCNAME in zf.namelist()


def test_partial_is_cleaned_up_even_on_an_exception_type_not_explicitly_anticipated(tmp_path, monkeypatch):
    # L-4a: try/finally (not just an except PackError/ValueError clause)
    # deletes "<out>.partial" for ANY exception raised while packing, so a
    # bug class this code does not anticipate still never leaves scratch
    # state behind.
    import tools.pack_setup_zip as pack_module

    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    partial = out.with_name(out.name + ".partial")

    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic unexpected failure")

    monkeypatch.setattr(pack_module, "verify_zip_layout", boom)
    with pytest.raises(RuntimeError):
        pack_module.main([
            "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
            "--epoch", str(EPOCH),
        ])
    assert not partial.exists()
    assert not out.exists()


# --- L-4a/b: a missing/unreadable ship-set-inventory.txt (not just a bad
# value in it) must fail closed through PackError, with a clean message,
# in every mode that reads one -- never a traceback. ------------------------


def test_parse_ci_inventory_raises_pack_error_on_a_missing_file(tmp_path):
    with pytest.raises(PackError):
        parse_ci_inventory(tmp_path / "does-not-exist.txt")


def test_parse_ci_inventory_raises_pack_error_on_invalid_utf8(tmp_path):
    bad = tmp_path / "bad-encoding.txt"
    bad.write_bytes(b"version=5.2.0 commit=abc\xff\xfe\x80\x81not valid utf-8\n")
    with pytest.raises(PackError):
        parse_ci_inventory(bad)


def test_parse_ci_inventory_raises_pack_error_on_a_directory(tmp_path):
    a_directory = tmp_path / "inventory-is-actually-a-dir"
    a_directory.mkdir()
    with pytest.raises(PackError):
        parse_ci_inventory(a_directory)


def test_pack_mode_with_a_missing_expect_inventory_file_exits_cleanly_no_traceback(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    missing_inventory = tmp_path / "does-not-exist.txt"

    rc = main([
        "--onedir", str(onedir), "--installer", str(installer), "--out", str(out),
        "--epoch", str(EPOCH), "--expect-inventory", str(missing_inventory),
    ])
    assert rc == 1
    assert not out.exists()
    assert not out.with_name(out.name + ".partial").exists()
    captured = capsys.readouterr()
    assert "pack failed" in captured.err
    assert "not found" in captured.err


def test_compare_tree_cli_mode_with_a_missing_inventory_exits_cleanly_no_traceback(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    missing_inventory = tmp_path / "does-not-exist.txt"
    rc = main(["--compare-tree", str(onedir), "--inventory", str(missing_inventory)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "pack failed" in captured.err
    assert "not found" in captured.err


# --- L-4b: --verify on a missing/unreadable zip exits 1 cleanly, no traceback -


def test_verify_mode_on_a_missing_zip_exits_cleanly_no_traceback(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.zip"
    rc = main(["--verify", str(missing)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "verify failed" in captured.err


def test_verify_mode_on_an_unreadable_zip_exits_cleanly_no_traceback(tmp_path, capsys):
    not_a_zip = tmp_path / "not-a-zip.zip"
    not_a_zip.write_bytes(b"this is not a zip file at all, just plain bytes")
    rc = main(["--verify", str(not_a_zip)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "verify failed" in captured.err


def test_parse_ci_inventory_ignores_non_tab_lines(tmp_path):
    inventory = tmp_path / "inv.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=abc",
        "aaaa  OrbitRxMonitor.exe",
        "libcrypto-3.dll FileVersion=3.0.16 ProductName=OpenSSL sha256=bbbb",
        "a.txt\t20",
    ])
    assert parse_ci_inventory(inventory) == {"a.txt": 20}


# --- --compare-tree (L6) ------------------------------------------------------


def test_compare_tree_passes_on_a_matching_tree(tmp_path):
    onedir = _make_onedir(tmp_path)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    assert compare_tree_to_inventory(onedir, inventory) == []


def test_compare_tree_fails_on_a_size_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t999",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    problems = compare_tree_to_inventory(onedir, inventory)
    assert any("size mismatch" in p and "a.txt" in p for p in problems)


def test_compare_tree_fails_on_a_name_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
        "_internal/nested/not-really-there.dat\t5",
    ])
    problems = compare_tree_to_inventory(onedir, inventory)
    assert any("missing from tree" in p and "not-really-there.dat" in p for p in problems)


def test_compare_tree_excludes_the_onedir_exe(tmp_path):
    onedir = _make_onedir(tmp_path)
    (onedir / "OrbitRxMonitor.exe").write_bytes(b"x" * 42)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "OrbitRxMonitor.exe\t999999",  # deliberately wrong size: must be ignored
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    assert compare_tree_to_inventory(onedir, inventory) == []


def test_compare_tree_cli_mode_exits_nonzero_on_mismatch(tmp_path):
    onedir = _make_onedir(tmp_path)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, ["a.txt\t999"])

    rc = main(["--compare-tree", str(onedir), "--inventory", str(inventory)])
    assert rc == 1


def test_compare_tree_cli_mode_passes_on_a_matching_tree(tmp_path):
    onedir = _make_onedir(tmp_path)

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    rc = main(["--compare-tree", str(onedir), "--inventory", str(inventory)])
    assert rc == 0


def test_compare_tree_cli_mode_requires_inventory(tmp_path):
    onedir = _make_onedir(tmp_path)
    rc = main(["--compare-tree", str(onedir)])
    assert rc == 2


# --- CLI epoch sources ---------------------------------------------------------


def test_epoch_can_come_from_source_date_epoch_env_var(tmp_path, monkeypatch):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out_explicit = tmp_path / "explicit.zip"
    out_env = tmp_path / "env.zip"

    rc = main([
        "--onedir", str(onedir), "--installer", str(installer),
        "--out", str(out_explicit), "--epoch", str(EPOCH),
    ])
    assert rc == 0

    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    rc = main(["--onedir", str(onedir), "--installer", str(installer), "--out", str(out_env)])
    assert rc == 0
    assert _sha256(out_explicit) == _sha256(out_env)


def test_pack_without_any_epoch_source_fails_closed(tmp_path, monkeypatch):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    rc = main(["--onedir", str(onedir), "--installer", str(installer), "--out", str(tmp_path / "out.zip")])
    assert rc == 1


# --- verify mode ---------------------------------------------------------------


def test_verify_mode_passes_on_a_clean_pack_and_fails_on_a_tampered_one(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = tmp_path / "out.zip"
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer),
        "--out", str(out), "--epoch", str(EPOCH),
    ])
    assert rc == 0
    rc = main(["--verify", str(out), "--onedir", str(onedir), "--installer", str(installer), "--epoch", str(EPOCH)])
    assert rc == 0

    # Tamper: add an extra file directly to the zip (bypassing the packer).
    with zipfile.ZipFile(out, "a") as zf:
        zf.writestr(f"{ONEDIR_PREFIX}extra.txt", "surprise")
    rc = main(["--verify", str(out), "--onedir", str(onedir), "--installer", str(installer), "--epoch", str(EPOCH)])
    assert rc == 1


# --- legacy single-installer mode still works ---------------------------------


def test_legacy_single_installer_mode_is_unaffected(tmp_path):
    installer = tmp_path / "OrbitRxMonitor-Setup.exe"
    installer.write_bytes(b"legacy installer bytes")
    out = tmp_path / "legacy.zip"

    rc = main([str(installer), "-o", str(out)])
    assert rc == 0
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["OrbitRxMonitor-Setup.exe"]


# --- non-integer / out-of-range --epoch and SOURCE_DATE_EPOCH fail closed,
# with a clean message, in every mode -- never a traceback (QA Sec.7 INFO) --


def test_verify_mode_rejects_a_non_integer_epoch_cleanly(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    rc = main(["--verify", str(out), "--epoch", "not-a-number"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "failed" in captured.err
    assert "not-a-number" in captured.err


def test_verify_mode_rejects_an_out_of_range_epoch_cleanly(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    too_high = calendar.timegm((2108, 1, 1, 0, 0, 0, 0, 0, 0))
    rc = main(["--verify", str(out), "--epoch", str(too_high)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "failed" in captured.err


def test_verify_mode_rejects_a_non_integer_source_date_epoch_env_cleanly(tmp_path, monkeypatch, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "also-not-a-number")
    rc = main(["--verify", str(out)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "failed" in captured.err
    assert "also-not-a-number" in captured.err


def test_pack_mode_rejects_a_non_integer_epoch_cleanly(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer),
        "--out", str(tmp_path / "out.zip"), "--epoch", "nope",
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "pack failed" in captured.err
    assert "nope" in captured.err


def test_pack_mode_rejects_an_out_of_range_epoch_cleanly(tmp_path, capsys):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    too_high = calendar.timegm((2108, 1, 1, 0, 0, 0, 0, 0, 0))
    rc = main([
        "--onedir", str(onedir), "--installer", str(installer),
        "--out", str(tmp_path / "out.zip"), "--epoch", str(too_high),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert "pack failed" in captured.err


# --- N7a: negative tests chosen to kill specific mutants in verify_zip_layout
# and compare_tree_to_inventory ------------------------------------------------


def _manual_option_b_zip(root: Path, out_path: Path, modify=None) -> Path:
    """Build an Option-B-shaped zip the same way build_deterministic_zip
    does, but allow a hook to mutate one member's ZipInfo before it is
    written -- used to construct zips that deviate from the fixed shape in
    exactly one way, so verify_zip_layout's specific checks can be tested in
    isolation."""
    onedir = _make_onedir(root)
    installer = _make_installer(root)
    members = collect_onedir_members(onedir)
    members.append((INSTALLER_ARCNAME, installer))
    members.sort(key=lambda m: m[0].encode("utf-8"))
    date_time = epoch_to_dos_date_time(EPOCH)
    with zipfile.ZipFile(out_path, "w", allowZip64=True) as zf:
        for arcname, src in members:
            data = src.read_bytes()
            info = zipfile.ZipInfo(arcname, date_time=date_time)
            info.create_system = 0
            info.create_version = 20
            info.extract_version = 20
            info.external_attr = FIXED_EXTERNAL_ATTR
            if modify is not None:
                modify(arcname, info)
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out_path


def test_verify_rejects_an_extra_field(tmp_path):
    def modify(arcname, info):
        if arcname.endswith("a.txt"):
            info.extra = b"\x01\x02\x00\x00"

    out = _manual_option_b_zip(tmp_path / "src", tmp_path / "extra.zip", modify)
    problems = verify_zip_layout(out, expect_epoch=EPOCH)
    assert any("extra field" in p for p in problems)


def test_verify_rejects_wrong_external_attr(tmp_path):
    def modify(arcname, info):
        if arcname.endswith("a.txt"):
            info.external_attr = 0x81A40000  # a plausible Unix-mode value, not FIXED_EXTERNAL_ATTR

    out = _manual_option_b_zip(tmp_path / "src", tmp_path / "attr.zip", modify)
    problems = verify_zip_layout(out, expect_epoch=EPOCH)
    assert any("external_attr" in p for p in problems)


def test_verify_rejects_directory_entries(tmp_path):
    onedir = _make_onedir(tmp_path)
    installer = _make_installer(tmp_path)
    out = _pack(tmp_path, onedir, installer, "out.zip")

    with zipfile.ZipFile(out, "a") as zf:
        zf.writestr(f"{ONEDIR_PREFIX}_internal/newdir/", "")
    problems = verify_zip_layout(out, expect_epoch=EPOCH)
    assert any("directory entry present" in p for p in problems)


def test_verify_rejects_a_corrupted_crc_in_a_stored_member(tmp_path):
    # Uses an uncompressed (ZIP_STORED) member rather than a deflated one:
    # flipping a byte inside a deflate stream usually corrupts the Huffman
    # coding itself and raises a zlib decode error rather than exercising
    # the CRC check. A stored member's "compressed" bytes are the raw data,
    # so one flipped byte changes the content without breaking decoding,
    # cleanly exercising zf.testzip()'s CRC comparison.
    out = tmp_path / "stored.zip"
    data = b"alpha file contents\n"
    with zipfile.ZipFile(out, "w", allowZip64=True) as zf:
        info = zipfile.ZipInfo(f"{ONEDIR_PREFIX}a.txt", date_time=epoch_to_dos_date_time(EPOCH))
        info.create_system = 0
        info.external_attr = FIXED_EXTERNAL_ATTR
        zf.writestr(info, data, compress_type=zipfile.ZIP_STORED)
        installer_info = zipfile.ZipInfo(INSTALLER_ARCNAME, date_time=epoch_to_dos_date_time(EPOCH))
        installer_info.create_system = 0
        installer_info.external_attr = FIXED_EXTERNAL_ATTR
        zf.writestr(installer_info, b"installer bytes", compress_type=zipfile.ZIP_STORED)

    with zipfile.ZipFile(out) as zf:
        offset = zf.getinfo(f"{ONEDIR_PREFIX}a.txt").header_offset

    raw = bytearray(out.read_bytes())
    # Local file header: signature(4) version(2) flags(2) method(2) time(2)
    # date(2) crc(4) compsize(4) uncompsize(4) namelen(2) extralen(2) = 30
    # bytes, then the filename, then the extra field, then the (stored, so
    # uncompressed) data. Flip one data byte without touching any header
    # field -- CRC checking (zf.testzip(), run by verify_zip_layout) must
    # then fail, while the archive otherwise stays readable.
    name_len = struct.unpack_from("<H", raw, offset + 26)[0]
    extra_len = struct.unpack_from("<H", raw, offset + 28)[0]
    data_start = offset + 30 + name_len + extra_len
    raw[data_start] ^= 0xFF
    out.write_bytes(bytes(raw))

    problems = verify_zip_layout(out, expect_epoch=EPOCH)
    assert any("CRC" in p for p in problems)


def test_compare_tree_rejects_an_extra_file_not_in_the_inventory(tmp_path):
    onedir = _make_onedir(tmp_path)
    (onedir / "unexpected.txt").write_bytes(b"surprise")

    inventory = tmp_path / "ship-set-inventory.txt"
    _write_inventory(inventory, [
        "version=5.2.0 commit=deadbeefcafe",
        "a.txt\t20",
        "_internal/b.bin\t256",
        "_internal/nested/c.dat\t1000",
    ])
    problems = compare_tree_to_inventory(onedir, inventory)
    assert any("not in inventory" in p and "unexpected.txt" in p for p in problems)


def test_compresslevel_is_exactly_9_not_a_lower_level():
    """Chosen data where zlib level 6 and level 9 raw-deflate outputs
    differ in length, so a mutant that lowers compresslevel to 6 (or any
    other non-9 value) is actually caught -- a level-insensitive payload
    would let that mutant through silently."""
    import zlib

    data = b"".join(
        f"line-{i % 50:04d}-padding-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n".encode()
        for i in range(3000)
    )
    level6 = zlib.compressobj(6, zlib.DEFLATED, -15)
    out6 = level6.compress(data) + level6.flush()
    level9 = zlib.compressobj(9, zlib.DEFLATED, -15)
    out9 = level9.compress(data) + level9.flush()
    assert out6 != out9, "test data is not compresslevel-sensitive; pick different data"

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        onedir = tmp_path / "OrbitRxMonitor"
        onedir.mkdir()
        (onedir / "level-sensitive.bin").write_bytes(data)
        installer = tmp_path / "OrbitRxMonitor-Setup.exe"
        installer.write_bytes(b"installer bytes\x00" * 4)
        out = tmp_path / "out.zip"
        build_deterministic_zip(onedir, installer, out, EPOCH)
        with zipfile.ZipFile(out) as zf:
            info = zf.getinfo(f"{ONEDIR_PREFIX}level-sensitive.bin")
            assert zf.read(info.filename) == data
            # Compare the raw compressed bytes (not the decompressed content)
            # against a from-scratch level 9 compression of the same data.
            offset = info.header_offset
            raw = out.read_bytes()
            name_len = struct.unpack_from("<H", raw, offset + 26)[0]
            extra_len = struct.unpack_from("<H", raw, offset + 28)[0]
            data_start = offset + 30 + name_len + extra_len
            comp_bytes = raw[data_start:data_start + info.compress_size]
    assert comp_bytes == out9
    assert comp_bytes != out6
