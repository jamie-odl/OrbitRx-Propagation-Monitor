"""Determinism tests for tools/pack_setup_zip.py's Option-B mode (two-root
zip: OrbitRxMonitor/ onedir + OrbitRxMonitor-Setup.exe installer).

Pure stdlib, synthetic bytes only -- no real PE binaries are built or
downloaded. Must pass on ubuntu-latest and windows-latest.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import zipfile
from pathlib import Path

import pytest

from tools.pack_setup_zip import (
    FIXED_EXTERNAL_ATTR,
    INSTALLER_ARCNAME,
    ONEDIR_PREFIX,
    build_deterministic_zip,
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


# --- epoch rounding / clamping ------------------------------------------------


def test_odd_epoch_rounds_down_to_an_even_second():
    odd = epoch_to_dos_date_time(1700000005)  # ends in an odd second
    even = epoch_to_dos_date_time(1700000004)  # one second earlier, even
    assert odd == even
    assert odd[5] % 2 == 0


def test_pre_1980_epoch_clamps_to_the_dos_epoch():
    assert epoch_to_dos_date_time(0) == (1980, 1, 1, 0, 0, 0)
    assert epoch_to_dos_date_time(-100000) == (1980, 1, 1, 0, 0, 0)
    assert epoch_to_dos_date_time(315532799) == (1980, 1, 1, 0, 0, 0)  # one second before
    assert epoch_to_dos_date_time(315532800) == (1980, 1, 1, 0, 0, 0)  # exactly at it


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
