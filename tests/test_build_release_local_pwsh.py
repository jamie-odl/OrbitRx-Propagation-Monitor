"""Dynamic (pwsh-executed) checks for tools/build_release_local.ps1 and its
dot-sourced tools/build_release_local.helpers.ps1.

Skipped entirely if pwsh is not on PATH (shutil.which('pwsh')) -- GitHub's
ubuntu-latest and windows-latest runners both ship pwsh, so this file runs
in CI's "test" job on every OS. Windows-only behaviours (GetFolderPath
Desktop, subst, junctions via New-Item -ItemType Junction) are skipped on
non-Windows hosts.

Static (text-only) checks of the same two files live in
tests/test_build_release_local.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_release_local.ps1"
HELPERS = ROOT / "tools" / "build_release_local.helpers.ps1"

PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(PWSH is None, reason="pwsh is not on PATH")

# Prepended to every -Command we run: forces plain, uncoloured, non-wrapped
# error rendering so a thrown message's text is not interrupted by ANSI SGR
# codes or pwsh's ConciseView "     | " line-wrap continuation gutters (both
# of which it emits in CI's non-interactive, no-real-console runs). $PSStyle
# only exists on PowerShell 7.2+, hence the guard.
_PWSH_PLAIN_OUTPUT_PREAMBLE = (
    "if ($PSStyle) { $PSStyle.OutputRendering = 'PlainText' }\n"
    "$ErrorView = 'NormalView'\n"
)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def run_pwsh(command: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    full_command = _PWSH_PLAIN_OUTPUT_PREAMBLE + command
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", full_command],
        cwd=cwd, capture_output=True, text=True, env=env,
    )


def run_helper(body: str) -> subprocess.CompletedProcess:
    command = f". '{HELPERS}'\n{body}"
    return run_pwsh(command)


def combined_text(result: subprocess.CompletedProcess) -> str:
    """stdout+stderr with ANSI escapes stripped and pwsh's error-pretty-
    printer line wrapping undone, so a multi-word phrase from a thrown
    message can be matched even when pwsh split it across lines (with a
    '     | ' continuation prefix) and/or coloured it with SGR codes."""
    text = result.stdout + result.stderr
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = re.sub(r"\n\s*\|\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# --- Hash / pin comparison helpers -------------------------------------------


def test_get_sha256_hex_matches_a_known_digest(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world")
    import hashlib
    expected = hashlib.sha256(b"hello world").hexdigest()
    result = run_helper(f"Write-Host (Get-Sha256Hex '{f}')")
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout


def test_assert_sha256_match_throws_on_mismatch(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world")
    result = run_helper(f"Assert-Sha256Match -Path '{f}' -Expected 'deadbeef' -Label 'thing'")
    assert result.returncode != 0
    text = combined_text(result)
    assert "thing sha256" in text
    assert "!=" in text
    assert "pinned deadbeef" in text


# --- SHA / attestation validation --------------------------------------------


@pytest.mark.parametrize("bad_sha", ["", "not-a-sha", "abc123", "x" * 40, "a" * 39, "a" * 41])
def test_assert_valid_expected_sha_rejects_bad_shas(bad_sha):
    result = run_helper(f"Assert-ValidExpectedSha -Sha '{bad_sha}'")
    assert result.returncode != 0
    assert "40-hex" in combined_text(result)


def test_assert_valid_expected_sha_accepts_and_lowercases_a_good_sha():
    sha = "ABCDEF0123456789abcdef0123456789abcdef01"
    result = run_helper(f"Write-Host (Assert-ValidExpectedSha -Sha '{sha}')")
    assert result.returncode == 0, result.stderr
    assert sha.lower() in result.stdout


def test_assert_personal_kit_attested_throws_when_false():
    result = run_helper("Assert-PersonalKitAttested -Attested:$false")
    assert result.returncode != 0
    assert "AttestPersonalKit must be passed" in combined_text(result)


def test_assert_personal_kit_attested_passes_when_true():
    result = run_helper("Assert-PersonalKitAttested -Attested:$true; Write-Host OK")
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --- R1: ship-set-inventory.txt header parsing -------------------------------


def test_get_ship_set_inventory_header_parses_a_good_header(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("version=5.2.0 commit=" + "a" * 40 + "\nmore\n", encoding="utf-8")
    result = run_helper(
        f"$h = Get-ShipSetInventoryHeader -Path '{inv}'; Write-Host \"$($h.Version)|$($h.Commit)\""
    )
    assert result.returncode == 0, result.stderr
    assert f"5.2.0|{'a' * 40}" in result.stdout


def test_get_ship_set_inventory_header_rejects_a_bad_header(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("not a header line\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


def test_get_ship_set_inventory_header_rejects_a_missing_file(tmp_path):
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{tmp_path / 'nope.txt'}'")
    assert result.returncode != 0
    assert "not found" in combined_text(result)


def test_assert_ci_inventory_matches_build_rejects_wrong_commit():
    header = "[PSCustomObject]@{ Version = '5.2.0'; Commit = 'a' * 40 -join '' }"
    result = run_helper(
        f"$h = {header}; Assert-CiInventoryMatchesBuild -Header $h -ExpectedSha ('b' * 40) -ExpectedVersion '5.2.0'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "does not" in text
    assert "match -ExpectedSha" in text


def test_assert_ci_inventory_matches_build_rejects_wrong_version():
    header = "[PSCustomObject]@{ Version = '5.1.0'; Commit = 'a' * 40 -join '' }"
    result = run_helper(
        f"$h = {header}; Assert-CiInventoryMatchesBuild -Header $h -ExpectedSha ('a' * 40) -ExpectedVersion '5.2.0'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "does not" in text
    assert "match -ExpectedVersion" in text


def test_assert_ci_inventory_matches_build_passes_on_a_match():
    header = "[PSCustomObject]@{ Version = '5.2.0'; Commit = 'a' * 40 -join '' }"
    result = run_helper(
        f"$h = {header}; Assert-CiInventoryMatchesBuild -Header $h -ExpectedSha ('A' * 40) -ExpectedVersion '5.2.0'; Write-Host OK"
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --- Provenance PII self-check ------------------------------------------------


def test_get_provenance_unsafe_markers_flags_a_uk_postcode_pattern():
    # ZZ99 9ZZ is the UK's reserved non-geographic placeholder postcode
    # (used for overseas/no-fixed-abode records), not a real address.
    result = run_helper(
        "$m = Get-ProvenanceUnsafeMarkers -Text 'some text ZZ99 9ZZ more text'; Write-Host ($m -join ',')"
    )
    assert result.returncode == 0, result.stderr
    assert "UK-postcode-pattern" in result.stdout


def test_get_provenance_unsafe_markers_is_clean_on_safe_text():
    # @(...): an empty array returned from a function collapses to $null
    # across the call boundary in PowerShell -- wrap so .Count is always
    # valid, exactly as build_release_local.ps1 itself must (and does).
    result = run_helper(
        "$m = @(Get-ProvenanceUnsafeMarkers -Text 'OrbitRx 5.2.0 provenance, sha256=abcdef'); "
        "Write-Host \"COUNT=$($m.Count)\""
    )
    assert result.returncode == 0, result.stderr
    assert "COUNT=0" in result.stdout


def test_get_provenance_unsafe_markers_flags_username_env_var():
    result = run_pwsh(
        f". '{HELPERS}'\n"
        "$env:USERNAME = 'jamietestuser'\n"
        "$m = Get-ProvenanceUnsafeMarkers -Text 'built by jamietestuser on this PC'\n"
        "Write-Host ($m -join ',')"
    )
    assert result.returncode == 0, result.stderr
    assert "jamietestuser" in result.stdout


# --- N4: path guard -----------------------------------------------------------


def test_test_onedrive_or_desktop_path_flags_onedrive_segment():
    result = run_helper(
        r"Write-Host (Test-OneDriveOrDesktopPath -Path 'C:\Users\jamie\OneDrive - Acme\build')"
    )
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout


def test_test_onedrive_or_desktop_path_flags_desktop_segment():
    result = run_helper(r"Write-Host (Test-OneDriveOrDesktopPath -Path 'C:\Users\jamie\Desktop\build')")
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout


def test_test_onedrive_or_desktop_path_is_false_for_a_plain_path():
    result = run_helper(r"Write-Host (Test-OneDriveOrDesktopPath -Path 'C:\build\orbitrx-work')")
    assert result.returncode == 0, result.stderr
    assert "False" in result.stdout


def test_test_subst_or_network_drive_path_flags_unc():
    result = run_helper(r"Write-Host (Test-SubstOrNetworkDrivePath -Path '\\server\share\build')")
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout


def test_test_subst_or_network_drive_path_is_false_for_a_plain_path():
    result = run_helper(r"Write-Host (Test-SubstOrNetworkDrivePath -Path 'C:\build\orbitrx-work')")
    assert result.returncode == 0, result.stderr
    assert "False" in result.stdout


def test_test_path_has_reparse_point_ancestor_is_false_for_a_plain_dir(tmp_path):
    result = run_helper(f"Write-Host (Test-PathHasReparsePointAncestor -Path '{tmp_path}')")
    assert result.returncode == 0, result.stderr
    assert "False" in result.stdout


def test_assert_safe_build_path_rejects_onedrive(tmp_path):
    fake = tmp_path / "OneDrive - Something" / "build"
    result = run_helper(f"Assert-SafeBuildPath -Path '{fake}' -Label 'thing'")
    assert result.returncode != 0
    assert "OneDrive or Desktop" in combined_text(result)


def test_assert_safe_build_path_accepts_a_plain_path(tmp_path):
    ok = tmp_path / "plain-build-dir"
    result = run_helper(f"Assert-SafeBuildPath -Path '{ok}' -Label 'thing'; Write-Host DONE")
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


def test_assert_build_root_outside_userprofile_rejects_when_inside(tmp_path, monkeypatch):
    profile = tmp_path / "home" / "jamie"
    profile.mkdir(parents=True)
    build_root = profile / "build"
    result = run_pwsh(
        f". '{HELPERS}'\n"
        f"$env:USERPROFILE = '{profile}'\n"
        f"Assert-BuildRootOutsideUserProfile -BuildRootFull '{build_root}'"
    )
    assert result.returncode != 0
    assert "USERPROFILE" in combined_text(result)


def test_assert_build_root_outside_userprofile_accepts_when_outside(tmp_path):
    profile = tmp_path / "home" / "jamie"
    profile.mkdir(parents=True)
    build_root = tmp_path / "build"
    result = run_pwsh(
        f". '{HELPERS}'\n"
        f"$env:USERPROFILE = '{profile}'\n"
        f"Assert-BuildRootOutsideUserProfile -BuildRootFull '{build_root}'\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="GetFolderPath('Desktop') is meaningful on Windows only")
def test_test_onedrive_or_desktop_path_matches_real_desktop_folder():
    result = run_helper(
        "$d = [Environment]::GetFolderPath('Desktop'); "
        "Write-Host (Test-OneDriveOrDesktopPath -Path (Join-Path $d 'sub'))"
    )
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows-only concept (N10)")
def test_test_path_has_reparse_point_ancestor_detects_a_junction(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    junction = tmp_path / "link"
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"mklink /J unavailable or refused: {result.stderr.strip()}")
    probe = run_helper(f"Write-Host (Test-PathHasReparsePointAncestor -Path '{junction / 'inside'}')")
    assert probe.returncode == 0, probe.stderr
    assert "True" in probe.stdout


def test_convert_from_subst_output_parses_canned_subst_text():
    # Real `subst` (no args) output format: "<letter>:\: => <path>" -- the
    # colon appears both before AND after the backslash. This is a pure
    # parse function, so it is exercised with canned text on every OS, not
    # just Windows (where the only live source of this text is itself).
    lines = [
        r"Z:\: => C:\Users\runneradmin\AppData\Local\Temp\subst-target",
        r"Y:\: => D:\other\path",
        "not a subst line",
    ]
    ps_array = "@(" + ",".join(f"'{line}'" for line in lines) + ")"
    result = run_helper(f"Write-Host ((ConvertFrom-SubstOutput -Lines {ps_array}) -join ',')")
    assert result.returncode == 0, result.stderr
    assert "Z,Y" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="subst is a Windows-only concept")
def test_get_subst_drive_letters_sees_a_live_subst(tmp_path):
    target = tmp_path / "subst-target"
    target.mkdir()
    letter = None
    for candidate in "ZYXWVUT":
        probe = subprocess.run(["subst", f"{candidate}:", str(target)], capture_output=True, text=True)
        if probe.returncode == 0:
            letter = candidate
            break
    if letter is None:
        pytest.skip("no free drive letter available for subst")
    try:
        result = run_helper(f"Write-Host (Test-SubstOrNetworkDrivePath -Path '{letter}:\\')")
        assert result.returncode == 0, result.stderr
        assert "True" in result.stdout
    finally:
        subprocess.run(["subst", f"{letter}:", "/D"], capture_output=True, text=True)


# --- Publisher-check logic ----------------------------------------------------


def _version_info(company="thevenom", copyright_="Copyright (C) 2026 thevenom", file_version="5.2.0"):
    return (
        "[PSCustomObject]@{ CompanyName = '" + company + "'; LegalCopyright = '" + copyright_
        + "'; FileVersion = '" + file_version + "' }"
    )


def test_publisher_version_info_accepts_a_good_exe():
    # @(...): see the comment on test_get_provenance_unsafe_markers_is_clean_on_safe_text.
    result = run_helper(
        f"$v = {_version_info()}; "
        "$p = @(Test-PublisherVersionInfo -VersionInfo $v -ExpectedAppVersion '5.2.0' -Label 'x.exe'); "
        "Write-Host \"COUNT=$($p.Count)\""
    )
    assert result.returncode == 0, result.stderr
    assert "COUNT=0" in result.stdout


def test_publisher_version_info_accepts_the_dot_zero_suffixed_file_version():
    result = run_helper(
        f"$v = {_version_info(file_version='5.2.0.0')}; "
        "$p = @(Test-PublisherVersionInfo -VersionInfo $v -ExpectedAppVersion '5.2.0' -Label 'x.exe'); "
        "Write-Host \"COUNT=$($p.Count)\""
    )
    assert result.returncode == 0, result.stderr
    assert "COUNT=0" in result.stdout


def test_publisher_version_info_flags_obsidian():
    result = run_helper(
        f"$v = {_version_info(copyright_='Copyright (C) 2026 Obsidian Dynamics')}; "
        "$p = Test-PublisherVersionInfo -VersionInfo $v -ExpectedAppVersion '5.2.0' -Label 'x.exe'; "
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "Obsidian Dynamics found in x.exe" in result.stdout


def test_publisher_version_info_flags_wrong_company():
    result = run_helper(
        f"$v = {_version_info(company='SomeoneElse')}; "
        "$p = Test-PublisherVersionInfo -VersionInfo $v -ExpectedAppVersion '5.2.0' -Label 'x.exe'; "
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "Unexpected CompanyName" in result.stdout


def test_publisher_version_info_flags_wrong_file_version():
    result = run_helper(
        f"$v = {_version_info(file_version='9.9.9')}; "
        "$p = Test-PublisherVersionInfo -VersionInfo $v -ExpectedAppVersion '5.2.0' -Label 'x.exe'; "
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "Unexpected FileVersion" in result.stdout


# --- N9: employer/managed-device heuristic -----------------------------------


def test_convert_from_dsregcmd_status_parses_yes_no_lines():
    lines = [
        "            AzureAdJoined : YES",
        "          EnterpriseJoined : NO",
        "             DomainJoined : NO",
        "          WorkplaceJoined : NO",
        "             IgnoredLine : whatever",
    ]
    ps_array = "@(" + ",".join(f"'{line}'" for line in lines) + ")"
    result = run_helper(
        f"$f = ConvertFrom-DsregcmdStatus -Lines {ps_array}; "
        "Write-Host \"$($f['AzureAdJoined'])|$($f['EnterpriseJoined'])|$($f['DomainJoined'])|$($f['WorkplaceJoined'])\""
    )
    assert result.returncode == 0, result.stderr
    assert "YES|NO|NO|NO" in result.stdout


def test_managed_device_status_refuses_on_domain_joined():
    result = run_helper(
        "$f = @{ DomainJoined = 'YES'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'NO' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "managed/employer device" in result.stdout


def test_managed_device_status_only_warns_on_workplace_joined():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'YES' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Warning)\""
    )
    assert result.returncode == 0, result.stderr
    assert "False|" in result.stdout
    assert "WorkplaceJoined=YES" in result.stdout


def test_managed_device_status_is_clean_when_nothing_is_joined():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'NO' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|refuse-msg=$($r.Message)|warn=$($r.Warning)\""
    )
    assert result.returncode == 0, result.stderr
    assert "False|refuse-msg=|warn=" in result.stdout


# --- Main script: bad-input early exits, never reaching pip/pyinstaller -----


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _is_under(path: str, ancestor: str) -> bool:
    if not path or not ancestor:
        return False
    try:
        return Path(path).resolve().is_relative_to(Path(ancestor).resolve())
    except (OSError, ValueError):
        return str(Path(path)).lower().startswith(str(Path(ancestor)).lower())


def _make_non_profile_base() -> Path:
    """A fresh directory outside $env:USERPROFILE to host the fake repo and
    -BuildRoot for the main-script tests below. On Windows, pytest's own
    tmp_path lives under C:\\Users\\<runner>\\AppData\\Local\\Temp -- i.e.
    under USERPROFILE -- which makes Assert-BuildRootOutsideUserProfile
    refuse the build before the check each of these tests exists to exercise
    even runs. Prefer $env:RUNNER_TEMP (GitHub-hosted Windows runners set it
    to a non-profile path, e.g. D:\\a\\_temp); fall back to a unique folder
    at the system drive root."""
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    userprofile = os.environ.get("USERPROFILE", "")
    name = f"orx-pwsh-test-{uuid.uuid4().hex[:12]}"
    if runner_temp and not _is_under(runner_temp, userprofile):
        base = Path(runner_temp) / name
    else:
        system_drive = os.environ.get("SystemDrive", "C:")
        base = Path(f"{system_drive}\\{name}")
    try:
        base.mkdir(parents=True)
    except OSError as exc:
        pytest.skip(f"cannot create a non-profile base directory ({base}) for BuildRoot tests: {exc}")
    return base


@pytest.fixture
def non_profile_tmp_path(tmp_path):
    """Like tmp_path, but outside $env:USERPROFILE on Windows (see
    _make_non_profile_base); on other platforms this is just tmp_path, which
    pytest already manages and cleans up itself."""
    if sys.platform != "win32":
        yield tmp_path
        return
    base = _make_non_profile_base()
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def fake_repo(non_profile_tmp_path):
    """A minimal git repo with just enough of this repo's shape (VERSION,
    tools/build_release_local.ps1 + helpers, packaging/local_build_pins.json)
    for the main script's early checks to run against -- without needing a
    real clone, dependencies, PyInstaller or Inno Setup. Every scenario this
    fixture backs fails before section c (Python installer pins) or earlier,
    so pip/pyinstaller are never reached. Lives under non_profile_tmp_path
    (not plain tmp_path) so the N4 path guards never refuse the repo root
    itself on Windows."""
    repo = non_profile_tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")

    tools_dir = repo / "tools"
    tools_dir.mkdir()
    shutil.copy(SCRIPT, tools_dir / "build_release_local.ps1")
    shutil.copy(HELPERS, tools_dir / "build_release_local.helpers.ps1")

    packaging_dir = repo / "packaging"
    packaging_dir.mkdir()
    real_pins = json.loads((ROOT / "packaging" / "local_build_pins.json").read_text(encoding="utf-8"))
    (packaging_dir / "local_build_pins.json").write_text(json.dumps(real_pins), encoding="utf-8")

    (repo / "VERSION").write_text("5.2.0\n", encoding="utf-8")

    _git(repo, "add", "-A")
    commit = _git(repo, "commit", "-q", "-m", "initial")
    assert commit.returncode == 0, commit.stderr
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert len(sha) == 40
    return repo, sha


def _write_inventory(path: Path, version: str, commit: str) -> None:
    path.write_text(f"version={version} commit={commit}\n", encoding="utf-8")


def _run_script(repo: Path, extra_args: list[str], build_root: Path) -> subprocess.CompletedProcess:
    args = " ".join(extra_args)
    script_call = (
        f"& '{repo / 'tools' / 'build_release_local.ps1'}' {args} "
        f"-BuildRoot '{build_root}'"
    )
    # try/catch so a thrown error always yields a clean non-zero exit code
    # (rather than depending on a stale $LASTEXITCODE from some earlier
    # native command, or on the host's default uncaught-exception handling).
    command = (
        "try {\n"
        f"    {script_call}\n"
        "    if ($null -eq $LASTEXITCODE) { exit 0 } else { exit $LASTEXITCODE }\n"
        "} catch {\n"
        "    Write-Error $_.Exception.Message\n"
        "    exit 1\n"
        "}"
    )
    return run_pwsh(command, cwd=repo)


def test_main_script_requires_attest_personal_kit(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'"], non_profile_tmp_path / "build-root"
    )
    assert result.returncode != 0
    assert "AttestPersonalKit must be passed" in combined_text(result)


def test_main_script_rejects_a_non_hex_sha(fake_repo, tmp_path, non_profile_tmp_path):
    repo, _sha = fake_repo
    result = _run_script(
        repo, ["-ExpectedSha not-a-real-sha", "-AttestPersonalKit"], non_profile_tmp_path / "build-root"
    )
    assert result.returncode != 0
    assert "40-hex" in combined_text(result)


def test_main_script_rejects_a_wrong_sha(fake_repo, tmp_path, non_profile_tmp_path):
    repo, _sha = fake_repo
    wrong_sha = "f" * 40
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", wrong_sha)
    result = _run_script(
        repo, [f"-ExpectedSha {wrong_sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root",
    )
    assert result.returncode != 0
    assert "HEAD is" in combined_text(result)
    assert "expected" in combined_text(result)


def test_main_script_rejects_a_dirty_tree(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    (repo / "untracked.txt").write_text("surprise\n", encoding="utf-8")
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root",
    )
    assert result.returncode != 0
    assert "Working tree is not clean" in combined_text(result)


def test_main_script_requires_ci_inventory(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", "-AttestPersonalKit"], non_profile_tmp_path / "build-root"
    )
    assert result.returncode != 0
    assert "-CiInventory is required" in combined_text(result)


def test_main_script_rejects_a_ci_inventory_with_the_wrong_commit(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", "c" * 40)  # well-formed, but not this build's commit
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root",
    )
    assert result.returncode != 0
    assert "does not match -ExpectedSha" in combined_text(result)


def test_main_script_rejects_a_bad_installer_hash_without_reaching_pip_or_pyinstaller(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    fake_installer = tmp_path / "python-3.12.10-amd64.exe"
    fake_installer.write_bytes(b"not the real python.org installer bytes")
    result = _run_script(
        repo,
        [
            f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit",
            f"-PythonInstaller '{fake_installer}'",
        ],
        non_profile_tmp_path / "build-root",
    )
    assert result.returncode != 0
    combined = combined_text(result)
    assert "Python installer sha256" in combined
    assert "!=" in combined
    assert "pinned" in combined
    # The failure must happen before any dependency install or build step.
    assert "pip" not in combined.lower()
    assert "pyinstaller" not in combined.lower()
