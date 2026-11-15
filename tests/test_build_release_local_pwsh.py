"""Dynamic (pwsh-executed) checks for tools/build_release_local.ps1 and its
dot-sourced tools/build_release_local.helpers.ps1.

Skipped entirely if pwsh is not on PATH (shutil.which('pwsh')) -- GitHub's
ubuntu-latest and windows-latest runners both ship pwsh, so this file runs
in CI's "test" job on every OS. Windows-only behaviours (GetFolderPath
Desktop, subst, junctions via New-Item -ItemType Junction) are skipped on
non-Windows hosts.

Static (text-only) checks of the same two files live in
tests/test_build_release_local.py.

QA round 3, item 6: stubs/fakes used by the behavioural (real-code-path)
tests below, since this suite cannot run a real Windows build:
  - N5b/N5c (PowerShell-7 inline gate): the gate's `if` statement is
    extracted from the real script text via the PowerShell AST
    (_extract_ast_node_text), then its one free variable
    ($PSVersionTable, which cannot be overridden -- it is Constant+
    AllScope) is textually renamed to $FakeVersionTable, which the test
    sets to a synthetic [pscustomobject]. The condition and body text
    themselves are the real, unmodified source.
  - P8c2 (python.exe vs installer signature): Assert-
    PythonAndInstallerSignaturesValid (the real helper, dot-sourced) is
    called with synthetic [PSCustomObject] signature objects standing in
    for what Get-AuthenticodeSignature would return -- no real
    Authenticode-signed binary. The main script's own call site for this
    helper is additionally extracted via the PowerShell AST
    (_extract_ast_node_text, CommandAst) and executed with the same
    synthetic signatures, so a mutant that swaps which variable the call
    site feeds to -PythonExeSignature is caught by running that exact
    statement, not just by grepping for its text.
  - P12c/P19 (OpenSSL pin check): Invoke-OpenSslPinCheck (the real
    function, extracted from the main script via AST) is run against a
    fake onedir directory tree (plain files standing in for DLLs) and a
    synthetic pin object; -VenvPython points at the real Python running
    this test (sys.executable), since the function only shells out to it
    for `platform.python_version()`.
  - P20 (shipped notices check): Invoke-ShippedNoticesCheck (extracted the
    same way) is run against a fake onedir with plain text files standing
    in for the real notice files.
  - N2e/P14/P15 (pack/L6/determinism section): the "pack-l6" region is
    extracted from the main script via its region-comment markers, then
    run standalone in a fresh fake git repo with
    tools\\pack_setup_zip.py / tools\\ship_set.py replaced by small Python
    stub scripts (written to files whose literal name contains a
    backslash, since the real script invokes them with a Windows-style
    relative path even on this non-Windows test host) that fake
    success/failure and, for the determinism check, deliberately write
    two different zip byte-contents.
  - P10 (provenance self-check): the "provenance-finalize" region is
    extracted the same way and run with a synthetic $provenanceText
    containing the UK-postcode-shaped placeholder ZZ99 9ZZ (not a real
    postcode) as the injected unsafe marker.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
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


# --- AST-based extraction helpers (item 6: behavioural tests of real code
# paths this suite otherwise cannot reach without a Windows build) ----------


def _assert_parses_as_powershell(text: str) -> None:
    """Fails loudly (rather than silently running malformed PowerShell) if
    a text fragment assembled by the helpers below does not parse."""
    result = run_pwsh(
        "$errors = $null\n"
        f"[System.Management.Automation.Language.Parser]::ParseInput(@'\n{text}\n'@, [ref]$null, [ref]$errors) | Out-Null\n"
        "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Host $_.ToString() }; exit 1 }\n"
    )
    assert result.returncode == 0, f"extracted text does not parse as PowerShell:\n{combined_text(result)}"


def _extract_ast_node_text(node_type: str, predicate: str) -> str:
    """Runs PowerShell's own parser over tools/build_release_local.ps1 and
    returns the .Extent.Text of the first AST node of `node_type` whose
    extent text matches `predicate` (a regex, pwsh -match syntax). Fails
    (rather than returning empty text) if the node is missing -- e.g. if a
    mutant removed it -- so a test built on this helper reports that as a
    failure instead of silently exercising nothing."""
    command = (
        f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}', [ref]$null, [ref]$null)\n"
        "$node = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.%s] -and $n.Extent.Text -match '%s' }, $true) | Select-Object -First 1\n"
        "if (-not $node) { Write-Error 'AST node not found'; exit 1 }\n"
        "Write-Output $node.Extent.Text\n"
    ) % (node_type, predicate.replace("'", "''"))
    result = run_pwsh(command)
    assert result.returncode == 0, f"AST extraction failed for {node_type}/{predicate}: {combined_text(result)}"
    return result.stdout


def _extract_function_text(name: str) -> str:
    return _extract_ast_node_text("FunctionDefinitionAst", rf"^function\s+{re.escape(name)}\b")


def _extract_region_text(region_name: str) -> str:
    """Plain text slicing between "# region <name>" / "# endregion <name>"
    markers in tools/build_release_local.ps1, validated (not merely
    assumed) to parse as standalone PowerShell -- the AST-parse step is
    what catches a mutant that corrupts the region rather than just
    removing a marker."""
    script_text = SCRIPT.read_text(encoding="utf-8")
    start_marker = f"# region {region_name}"
    end_marker = f"# endregion {region_name}"
    assert start_marker in script_text, f"start marker {start_marker!r} not found"
    assert end_marker in script_text, f"end marker {end_marker!r} not found"
    body = script_text.split(start_marker, 1)[1].split(end_marker, 1)[0]
    _assert_parses_as_powershell(body)
    return body


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


# X3: the header regex must require a full 40-hex commit and must be
# anchored at both ends -- a loosened version (shorter SHA accepted, or no
# ^/$ anchors) would let a truncated or embedded-in-garbage header through.


def test_get_ship_set_inventory_header_rejects_a_short_sha(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("version=5.2.0 commit=abc1234\nmore\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


def test_get_ship_set_inventory_header_rejects_a_39_char_sha(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("version=5.2.0 commit=" + "a" * 39 + "\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


def test_get_ship_set_inventory_header_rejects_leading_garbage_before_version(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("xxx version=5.2.0 commit=" + "a" * 40 + "\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


def test_get_ship_set_inventory_header_rejects_trailing_garbage_after_commit(tmp_path):
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("version=5.2.0 commit=" + "a" * 40 + "xyz\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


def test_get_ship_set_inventory_header_rejects_a_41_char_sha(tmp_path):
    # 41 hex characters is not a valid 40-hex SHA either -- must still be
    # rejected (guards against a mutant that changes {40} to {40,}).
    inv = tmp_path / "ship-set-inventory.txt"
    inv.write_text("version=5.2.0 commit=" + "a" * 41 + "\n", encoding="utf-8")
    result = run_helper(f"Get-ShipSetInventoryHeader -Path '{inv}'")
    assert result.returncode != 0
    assert "does not match" in combined_text(result)


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


# --- P6: Python installer sha256 + md5 pin (as a pure helper) ---------------


GOOD_SHA256 = "aa" * 32
GOOD_MD5 = "bb" * 16


def _python_pin(sha256=GOOD_SHA256, md5=GOOD_MD5):
    return "[PSCustomObject]@{ installer_sha256 = '" + sha256 + "'; installer_md5 = '" + md5 + "' }"


def test_assert_python_installer_hashes_match_passes_when_both_match():
    result = run_helper(
        f"$pin = {_python_pin()}\n"
        f"Assert-PythonInstallerHashesMatch -Sha256 '{GOOD_SHA256}' -Md5 '{GOOD_MD5}' -PythonPin $pin\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


def test_assert_python_installer_hashes_match_rejects_wrong_sha256():
    result = run_helper(
        f"$pin = {_python_pin()}\n"
        f"Assert-PythonInstallerHashesMatch -Sha256 'deadbeef' -Md5 '{GOOD_MD5}' -PythonPin $pin"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "Python installer sha256" in text
    assert "!=" in text


def test_assert_python_installer_hashes_match_rejects_wrong_md5_even_when_sha256_matches():
    # P6: this is the specific mutant to kill -- the md5 half of the check
    # removed entirely. A matching sha256 alone must not be enough to pass.
    result = run_helper(
        f"$pin = {_python_pin()}\n"
        f"Assert-PythonInstallerHashesMatch -Sha256 '{GOOD_SHA256}' -Md5 'deadbeef' -PythonPin $pin"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "Python installer md5" in text
    assert "!=" in text


# --- P8: Authenticode signature + signer-subject check (as a pure helper) ---


def _signature(status="Valid", subject="CN=Python Software Foundation, O=Python Software Foundation"):
    return "[PSCustomObject]@{ Status = '" + status + "'; SignerCertificate = [PSCustomObject]@{ Subject = '" + subject + "' } }"


def test_assert_authenticode_signature_valid_passes_on_a_good_signature():
    result = run_helper(
        f"$sig = {_signature()}\n"
        "Assert-AuthenticodeSignatureValid -Signature $sig -Label 'thing' "
        "-SignerSubjectContains 'Python Software Foundation'\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


def test_assert_authenticode_signature_valid_rejects_a_non_valid_status():
    result = run_helper(
        f"$sig = {_signature(status='NotSigned')}\n"
        "Assert-AuthenticodeSignatureValid -Signature $sig -Label 'thing' "
        "-SignerSubjectContains 'Python Software Foundation'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "thing Authenticode signature status is NotSigned" in text
    assert "expected Valid" in text


def test_assert_authenticode_signature_valid_rejects_wrong_signer_even_when_status_is_valid():
    # P8: this is the specific mutant to kill -- the python.exe check
    # dropped. A Valid status alone must not be enough; the signer subject
    # must also contain the pinned substring.
    result = run_helper(
        f"$sig = {_signature(subject='CN=Someone Else')}\n"
        "Assert-AuthenticodeSignatureValid -Signature $sig -Label 'python.exe' "
        "-SignerSubjectContains 'Python Software Foundation'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "python.exe signer subject" in text
    assert "does not contain" in text


# --- P12: OpenSSL per-DLL pin check (as a pure helper) -----------------------


GOOD_DLL_SHA256 = "cc" * 32


def _dll_pin_entry(file_version="3.0.16", sha256=GOOD_DLL_SHA256):
    return "[PSCustomObject]@{ file_version = '" + file_version + "'; sha256 = '" + sha256 + "' }"


def test_get_openssl_dll_pin_problems_is_clean_on_a_full_match():
    result = run_helper(
        f"$pin = {_dll_pin_entry()}\n"
        "$p = @(Get-OpenSslDllPinProblems -DllName 'libcrypto-3.dll' -DirectoryName 'C:\\onedir\\_internal' "
        f"-ExpectedDirectory 'C:\\onedir\\_internal' -FileVersion '3.0.16' -Sha256 '{GOOD_DLL_SHA256}' "
        "-PinEntry $pin)\n"
        "Write-Host \"COUNT=$($p.Count)\""
    )
    assert result.returncode == 0, result.stderr
    assert "COUNT=0" in result.stdout


def test_get_openssl_dll_pin_problems_flags_wrong_sha256_even_when_version_and_dir_match():
    # P12: this is the specific mutant to kill -- the sha256 compare
    # removed. A matching FileVersion and directory alone must not be
    # enough to pass.
    result = run_helper(
        f"$pin = {_dll_pin_entry()}\n"
        "$p = Get-OpenSslDllPinProblems -DllName 'libcrypto-3.dll' -DirectoryName 'C:\\onedir\\_internal' "
        "-ExpectedDirectory 'C:\\onedir\\_internal' -FileVersion '3.0.16' -Sha256 'deadbeef' "
        "-PinEntry $pin\n"
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "libcrypto-3.dll sha256" in result.stdout
    assert "!=" in result.stdout


def test_get_openssl_dll_pin_problems_flags_wrong_directory():
    result = run_helper(
        f"$pin = {_dll_pin_entry()}\n"
        "$p = Get-OpenSslDllPinProblems -DllName 'libcrypto-3.dll' -DirectoryName 'C:\\wrong\\place' "
        f"-ExpectedDirectory 'C:\\onedir\\_internal' -FileVersion '3.0.16' -Sha256 '{GOOD_DLL_SHA256}' "
        "-PinEntry $pin\n"
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "is not at _internal" in result.stdout


def test_get_openssl_dll_pin_problems_flags_wrong_file_version():
    result = run_helper(
        f"$pin = {_dll_pin_entry()}\n"
        "$p = Get-OpenSslDllPinProblems -DllName 'libcrypto-3.dll' -DirectoryName 'C:\\onedir\\_internal' "
        f"-ExpectedDirectory 'C:\\onedir\\_internal' -FileVersion '9.9.9' -Sha256 '{GOOD_DLL_SHA256}' "
        "-PinEntry $pin\n"
        "Write-Host ($p -join '|')"
    )
    assert result.returncode == 0, result.stderr
    assert "FileVersion" in result.stdout
    assert "!=" in result.stdout


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
    assert "work/school account or is managed" in result.stdout


def test_managed_device_status_refuses_on_azure_ad_joined_alone():
    # X9: this is the specific mutant to kill -- AzureAdJoined dropped from
    # the refuse list. DomainJoined/EnterpriseJoined being NO must not be
    # enough to let an Azure AD-joined machine through.
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'YES'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'NO' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "work/school account or is managed" in result.stdout
    assert "AzureAdJoined" in result.stdout


def test_managed_device_status_refuses_on_enterprise_joined_alone():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'YES'; WorkplaceJoined = 'NO' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "work/school account or is managed" in result.stdout
    assert "EnterpriseJoined" in result.stdout


def test_managed_device_status_refuses_on_workplace_joined_alone():
    # R-a (Risk round): WorkplaceJoined=YES used to only warn; it must now
    # refuse on its own, same as the other three join flags -- a work/school
    # account on this PC means it is not a personal kit.
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'YES' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "WorkplaceJoined" in result.stdout
    assert "work/school account or is managed" in result.stdout
    assert "Stop and tell Risk" in result.stdout


def test_managed_device_status_is_clean_when_nothing_is_joined():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'NO' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|refuse-msg=$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "False|refuse-msg=" in result.stdout


# --- L-B (Risk R3 Ruling 2): ConvertFrom-DsregcmdStatus parsing robustness,
# and Test-ManagedDeviceStatus's UNVERIFIED-means-refuse rules 3/4. ----------


def test_convert_from_dsregcmd_status_is_case_insensitive_and_whitespace_tolerant():
    lines = [
        "azureadjoined:yes",
        "\tenterprisejoined\t:\tno\t",
        "   DOMAINJOINED   :   NO   ",
        "WorkPlaceJoined : no",
    ]
    ps_array = "@(" + ",".join(f"'{line}'" for line in lines) + ")"
    result = run_helper(
        f"$f = ConvertFrom-DsregcmdStatus -Lines {ps_array}; "
        "Write-Host \"$($f['AzureAdJoined'])|$($f['EnterpriseJoined'])|$($f['DomainJoined'])|$($f['WorkplaceJoined'])\""
    )
    assert result.returncode == 0, result.stderr
    assert "YES|NO|NO|NO" in result.stdout


def test_convert_from_dsregcmd_status_tolerates_a_trailing_cr():
    # A line that still carries a trailing \r (e.g. CRLF output that was not
    # cleanly pre-split) must still parse, not be dropped as "no match".
    line = "WorkplaceJoined : YES\r"
    result = run_helper(f"$f = ConvertFrom-DsregcmdStatus -Lines @('{line}'); Write-Host \"$($f['WorkplaceJoined'])\"")
    assert result.returncode == 0, result.stderr
    assert "YES" in result.stdout.strip().splitlines()[-1]


def test_convert_from_dsregcmd_status_a_duplicate_yes_cannot_be_overwritten_by_a_later_no():
    # The core L-B bug: the old implementation let whichever line for a key
    # came last win, so "YES" then "NO" silently became "NO". That must no
    # longer happen in either order.
    result_yes_then_no = run_helper(
        "$f = ConvertFrom-DsregcmdStatus -Lines @('WorkplaceJoined : YES', 'WorkplaceJoined : NO'); "
        "Write-Host \"$($f['WorkplaceJoined'])\""
    )
    assert result_yes_then_no.returncode == 0, result_yes_then_no.stderr
    assert result_yes_then_no.stdout.strip().splitlines()[-1] == "YES"

    result_no_then_yes = run_helper(
        "$f = ConvertFrom-DsregcmdStatus -Lines @('WorkplaceJoined : NO', 'WorkplaceJoined : YES'); "
        "Write-Host \"$($f['WorkplaceJoined'])\""
    )
    assert result_no_then_yes.returncode == 0, result_no_then_yes.stderr
    assert result_no_then_yes.stdout.strip().splitlines()[-1] == "YES"


def test_convert_from_dsregcmd_status_marks_a_non_yes_no_value_unverified():
    result = run_helper(
        "$f = ConvertFrom-DsregcmdStatus -Lines @('WorkplaceJoined : YES (Contoso)'); "
        "Write-Host \"$($f['WorkplaceJoined'])\""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "UNVERIFIED"


def test_convert_from_dsregcmd_status_unverified_value_is_sticky_against_a_later_clean_no():
    result = run_helper(
        "$f = ConvertFrom-DsregcmdStatus -Lines @('WorkplaceJoined : JA', 'WorkplaceJoined : NO'); "
        "Write-Host \"$($f['WorkplaceJoined'])\""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "UNVERIFIED"


def test_convert_from_dsregcmd_status_a_key_that_never_appears_is_left_out():
    # "Workplace Joined" (a space in the key) must not match -- the key
    # stays entirely absent, which Test-ManagedDeviceStatus treats as
    # "fewer than all 4 keys parsed" (refuse), not as a silent default.
    result = run_helper(
        "$f = ConvertFrom-DsregcmdStatus -Lines @('Workplace Joined : YES'); "
        "Write-Host \"ContainsKey=$($f.ContainsKey('WorkplaceJoined'))\""
    )
    assert result.returncode == 0, result.stderr
    assert "ContainsKey=False" in result.stdout


def test_managed_device_status_refuses_as_unverified_when_a_key_is_missing():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO' }; "  # WorkplaceJoined absent
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "UNVERIFIED" in result.stdout
    assert "WorkplaceJoined" in result.stdout
    # Must not be worded as the YES/"work-school account" refusal.
    assert "= YES" not in result.stdout


def test_managed_device_status_refuses_as_unverified_for_a_garbled_value():
    result = run_helper(
        "$f = @{ DomainJoined = 'NO'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'UNVERIFIED' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "UNVERIFIED" in result.stdout
    assert "WorkplaceJoined" in result.stdout


def test_managed_device_status_yes_takes_priority_in_the_message_over_unverified():
    result = run_helper(
        "$f = @{ DomainJoined = 'YES'; AzureAdJoined = 'NO'; EnterpriseJoined = 'NO'; WorkplaceJoined = 'UNVERIFIED' }; "
        "$r = Test-ManagedDeviceStatus -Flags $f; "
        "Write-Host \"$($r.Refuse)|$($r.Message)\""
    )
    assert result.returncode == 0, result.stderr
    assert "True|" in result.stdout
    assert "DomainJoined" in result.stdout
    assert "= YES" in result.stdout


# --- L-B: the real "managed-device-check" call site in the main script,
# with a mocked dsregcmd (a PowerShell function, which Get-Command resolves
# ahead of any real dsregcmd.exe on PATH) and $IsWindows faked via
# Set-Variable (it is ReadOnly but not Constant, unlike $PSVersionTable, so
# it can be overridden directly -- no textual rename trick needed). --------


def _dsregcmd_mock(lines=None, exit_code=0):
    lines = lines or []
    writes = "\n".join(f"    Write-Output '{line}'" for line in lines)
    return "function dsregcmd {\n" + (writes + "\n" if writes else "") + f"    $global:LASTEXITCODE = {exit_code}\n" + "}\n"


def _run_managed_device_check_region(is_windows, mock=None, clear_path=False):
    region_text = _extract_region_text("managed-device-check")
    harness = (
        f". '{HELPERS}'\n"
        f"Set-Variable -Name IsWindows -Value ${'true' if is_windows else 'false'} -Force\n"
        + ("$env:PATH = ''\n" if clear_path else "")
        + (mock + "\n" if mock else "")
        + "$dsregcmdDomainJoined = 'not available'\n"
        "$dsregcmdAzureAdJoined = 'not available'\n"
        "$dsregcmdEnterpriseJoined = 'not available'\n"
        "$dsregcmdWorkplaceJoined = 'not available'\n"
        "try {\n"
        f"{region_text}\n"
        "    Write-Host 'REGION-COMPLETED-OK'\n"
        "} catch {\n"
        "    Write-Host \"REGION-THREW: $($_.Exception.Message)\"\n"
        "    exit 1\n"
        "}\n"
    )
    return run_pwsh(harness)


_ALL_NO = ["DomainJoined : NO", "AzureAdJoined : NO", "EnterpriseJoined : NO", "WorkplaceJoined : NO"]


@pytest.mark.parametrize("flag", ["DomainJoined", "AzureAdJoined", "EnterpriseJoined", "WorkplaceJoined"])
def test_managed_device_check_region_refuses_on_yes_for_each_flag(flag):
    lines = [f"{name} : {'YES' if name == flag else 'NO'}" for name in
             ("DomainJoined", "AzureAdJoined", "EnterpriseJoined", "WorkplaceJoined")]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert flag in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_on_nonzero_exit():
    result = _run_managed_device_check_region(True, _dsregcmd_mock(_ALL_NO, exit_code=1))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "UNVERIFIED" in text
    assert "exited with code 1" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_on_empty_output():
    result = _run_managed_device_check_region(True, _dsregcmd_mock([]))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "UNVERIFIED" in text
    assert "no output" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_when_fewer_than_four_keys_parse():
    result = _run_managed_device_check_region(True, _dsregcmd_mock(_ALL_NO[:3]))  # WorkplaceJoined missing
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "UNVERIFIED" in text
    assert "WorkplaceJoined" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_on_a_non_yes_no_value():
    lines = ["DomainJoined : NO", "AzureAdJoined : NO", "EnterpriseJoined : NO", "WorkplaceJoined : YES (Contoso)"]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "UNVERIFIED" in text
    assert "WorkplaceJoined" in text
    assert "Contoso" not in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_on_a_duplicate_yes_then_no():
    lines = ["WorkplaceJoined : YES", "DomainJoined : NO", "AzureAdJoined : NO",
             "EnterpriseJoined : NO", "WorkplaceJoined : NO"]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "WorkplaceJoined" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_refuses_on_a_case_variant_yes():
    lines = ["domainjoined : no", "azureadjoined : no", "enterprisejoined : no", "workplacejoined : yes"]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "WorkplaceJoined" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_tolerates_tabs_and_crlf_but_still_refuses_on_yes():
    lines = ["DomainJoined\t:\tNO", "AzureAdJoined : NO\r", "   EnterpriseJoined   :   NO   ", "WorkplaceJoined:YES\r"]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "WorkplaceJoined" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_tolerates_tabs_and_crlf_and_passes_on_all_no():
    lines = ["DomainJoined\t:\tNO", "AzureAdJoined : NO\r", "   EnterpriseJoined   :   NO   ", "WorkplaceJoined:NO\r"]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    assert result.returncode == 0, text
    assert "REGION-COMPLETED-OK" in result.stdout
    assert "MANAGED-DEVICE-CHECK: PASS" in text


def test_managed_device_check_region_refuses_when_dsregcmd_missing_on_windows():
    result = _run_managed_device_check_region(True, mock=None, clear_path=True)
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "dsregcmd is missing" in text
    assert "Stop and tell Risk" in text


def test_managed_device_check_region_skips_when_dsregcmd_missing_off_windows():
    result = _run_managed_device_check_region(False, mock=None, clear_path=True)
    text = combined_text(result)
    assert result.returncode == 0, text
    assert "REGION-COMPLETED-OK" in result.stdout
    assert "not available" in text


def test_managed_device_check_region_passes_when_all_four_are_no():
    result = _run_managed_device_check_region(True, _dsregcmd_mock(_ALL_NO))
    text = combined_text(result)
    assert result.returncode == 0, text
    assert "REGION-COMPLETED-OK" in result.stdout
    assert "MANAGED-DEVICE-CHECK: PASS" in text
    assert "DomainJoined=NO" in text
    assert "AzureAdJoined=NO" in text
    assert "EnterpriseJoined=NO" in text
    assert "WorkplaceJoined=NO" in text


@pytest.mark.parametrize("joined_flag", [None, "WorkplaceJoined"])
def test_managed_device_check_region_output_never_contains_tenant_or_device_data(joined_flag):
    tenant_id = "11111111-2222-3333-4444-555555555555"
    device_id = "66666666-7777-8888-9999-000000000000"
    tenant_name = "Example-Tenant-Name"
    lines = [
        f"TenantId : {tenant_id}",
        f"TenantName : {tenant_name}",
        f"DeviceId : {device_id}",
        f"DomainJoined : {'YES' if joined_flag == 'DomainJoined' else 'NO'}",
        "AzureAdJoined : NO",
        "EnterpriseJoined : NO",
        f"WorkplaceJoined : {'YES' if joined_flag == 'WorkplaceJoined' else 'NO'}",
    ]
    result = _run_managed_device_check_region(True, _dsregcmd_mock(lines))
    text = combined_text(result)
    if joined_flag is None:
        assert result.returncode == 0, text
        assert "MANAGED-DEVICE-CHECK: PASS" in text
    else:
        assert result.returncode != 0, text
        assert "Stop and tell Risk" in text
    assert tenant_id not in text
    assert device_id not in text
    assert tenant_name not in text


# --- NEW-5/I-1: PowerShell version gate, floor 7.4 (full version, not just
# major) -----------------------------------------------------------------


@pytest.mark.parametrize("version", ["1.0", "2.0", "3.0", "4.0", "5.1", "6.0", "6.2", "7.0", "7.1", "7.2", "7.3"])
def test_powershell_version_supported_rejects_below_7_4(version):
    result = run_helper(f"Write-Host (Test-PowerShellVersionSupported -Version ([version]'{version}'))")
    assert result.returncode == 0, result.stderr
    assert "False" in result.stdout


@pytest.mark.parametrize("version", ["7.4", "7.4.6", "7.5", "8.0", "9.0"])
def test_powershell_version_supported_accepts_7_4_and_above(version):
    result = run_helper(f"Write-Host (Test-PowerShellVersionSupported -Version ([version]'{version}'))")
    assert result.returncode == 0, result.stderr
    assert "True" in result.stdout


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


# --- M-1: refuse up front, before any build work, if -BuildRoot's out\ is
# already non-empty; proceed normally when it is empty or missing. ----------


def test_main_script_refuses_when_buildroot_out_is_not_empty(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    inv.write_text("not a real ship-set-inventory header\n", encoding="utf-8")
    build_root = non_profile_tmp_path / "build-root"
    stale_out = build_root / "out"
    stale_out.mkdir(parents=True)
    stale_zip = stale_out / "OrbitRx-Setup-5.2.0.zip"
    stale_zip.write_bytes(b"stale zip from an earlier run")
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"],
        build_root, console,
    )
    assert result.returncode != 0, combined_text(result)
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "already exists and is not empty" in console_text
    assert "new, empty BuildRoot" in console_text
    # Refused before any build work: the stale file is untouched, and this
    # ran well before the CI-inventory-header-check that the malformed
    # inv.txt above would otherwise have failed on.
    assert stale_zip.read_bytes() == b"stale zip from an earlier run"
    assert "CI-INVENTORY-HEADER-CHECK" not in console_text


def test_main_script_proceeds_past_buildroot_check_when_out_is_missing(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    build_root = non_profile_tmp_path / "build-root"  # does not exist at all
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"], build_root,
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "already exists and is not empty" not in text
    # Proceeds past the M-1 check to the next gate (no -PythonInstaller given).
    assert "-PythonInstaller not found" in text


def test_main_script_proceeds_past_buildroot_check_when_out_is_empty(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    build_root = non_profile_tmp_path / "build-root"
    (build_root / "out").mkdir(parents=True)
    result = _run_script(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"], build_root,
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "already exists and is not empty" not in text
    assert "-PythonInstaller not found" in text


# --- L-A: a missing or unparsable helpers file must still give a BUILD
# FAILED line (not a StrictMode crash on an unset $zipPath in the catch). ---


def test_main_script_reports_build_failed_when_helpers_file_is_missing(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    (repo / "tools" / "build_release_local.helpers.ps1").unlink()
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    assert console.is_file()
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "Helpers file not found" in console_text
    # The old bug (L-A): the catch itself crashed on $zipPath before it was
    # ever assigned, so this StrictMode message must NOT appear.
    assert "cannot be retrieved because it has not been set" not in console_text


def test_main_script_reports_build_failed_when_helpers_file_is_unparsable(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    helpers_path = repo / "tools" / "build_release_local.helpers.ps1"
    helpers_path.write_text("function Oops( {\n", encoding="utf-8")  # deliberately malformed
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    assert console.is_file()
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "cannot be retrieved because it has not been set" not in console_text


# --- NEW-1: a terminating failure must still reach build-console.txt when
# run exactly as BUILD-RELEASE.md documents it: `*>&1 | Tee-Object -FilePath
# build-console.txt`. An uncaught `throw` short-circuits that pipeline
# before Tee-Object ever sees it (only the interactive host would show it),
# which would lose the dry run's failure reason for whoever reviews
# build-console.txt. The script must catch it itself and report it through
# the success stream instead. ----------------------------------------------


def _run_script_through_tee(
    repo: Path, extra_args: list[str], build_root: Path, console_path: Path
) -> subprocess.CompletedProcess:
    """Runs the script through the exact pipeline shape BUILD-RELEASE.md
    documents, so this test exercises the real invocation -- not a
    try/catch wrapper (like _run_script above) that would mask the bug
    NEW-1 exists to catch."""
    args = " ".join(extra_args)
    command = (
        f"& '{repo / 'tools' / 'build_release_local.ps1'}' {args} "
        f"-BuildRoot '{build_root}' *>&1 | Tee-Object -FilePath '{console_path}'\n"
        "exit $LASTEXITCODE"
    )
    return run_pwsh(command, cwd=repo)


def test_build_failed_reaches_console_file_through_tee_on_wrong_ci_inventory_commit(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", "c" * 40)  # well-formed, but not this build's commit
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    assert console.is_file()
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "does not match -ExpectedSha" in console_text


def test_build_failed_reaches_console_file_through_tee_on_missing_attest_personal_kit(
    fake_repo, tmp_path, non_profile_tmp_path
):
    repo, sha = fake_repo
    inv = tmp_path / "inv.txt"
    _write_inventory(inv, "5.2.0", sha)
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", f"-CiInventory '{inv}'"],
        non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    assert console.is_file()
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "AttestPersonalKit must be passed" in console_text


def test_build_failed_message_includes_a_script_line_number(fake_repo, tmp_path, non_profile_tmp_path):
    repo, sha = fake_repo
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}"], non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    # L-3: a leaf .ps1 file name plus a line number, not just a bare number.
    # (This scenario's first failing check, AttestPersonalKit, is thrown
    # from the dot-sourced helpers file, so that is the name reported here
    # -- see InvocationInfo.ScriptName's documented behaviour: it names the
    # file the throw actually executed in, not the main script.)
    assert re.search(r"\(build_release_local\.helpers\.ps1:\d+\)", console_text)


def test_build_failed_message_names_the_main_script_when_the_throw_is_there(
    fake_repo, tmp_path, non_profile_tmp_path
):
    # L-3: a terminating error thrown directly from the main script's own
    # body (not a dot-sourced helper function) must name *that* file --
    # confirming the file name in "BUILD FAILED: ... (<file>:<line>)" really
    # tracks the throw's actual source file rather than always printing a
    # single hardcoded name.
    repo, sha = fake_repo
    console = tmp_path / "build-console.txt"
    result = _run_script_through_tee(
        repo, [f"-ExpectedSha {sha}", "-AttestPersonalKit"],
        non_profile_tmp_path / "build-root", console,
    )
    assert result.returncode != 0, combined_text(result)
    console_text = console.read_text(encoding="utf-8", errors="replace")
    assert "BUILD FAILED" in console_text
    assert "-CiInventory is required" in console_text
    assert re.search(r"\(build_release_local\.ps1:\d+\)", console_text)


# --- N5b/N5c/I-1: the plain inline PowerShell-version gate, exercised via
# its real extracted condition/body text (see module docstring). Floor is
# the full version 7.4, not just major version 7. ---------------------------


def _run_inline_version_gate(version: str) -> subprocess.CompletedProcess:
    gate_text = _extract_ast_node_text("IfStatementAst", r"PSVersionTable\.PSVersion -lt \[version\]'7\.4'")
    faked = gate_text.replace("$PSVersionTable", "$FakeVersionTable")
    command = (
        f"$FakeVersionTable = [pscustomobject]@{{ PSVersion = [version]'{version}' }}\n"
        f"{faked}\n"
        "Write-Host 'GATE-DID-NOT-EXIT'\n"
    )
    return run_pwsh(command)


@pytest.mark.parametrize("version", ["1.0", "5.1", "6.0", "7.0", "7.3"])
def test_inline_version_gate_stops_below_7_4(version):
    result = _run_inline_version_gate(version)
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "BUILD FAILED" in text
    assert "PowerShell 7.4 or later is required" in text
    assert "GATE-DID-NOT-EXIT" not in result.stdout


@pytest.mark.parametrize("version", ["7.4", "7.4.6", "7.5", "8.0"])
def test_inline_version_gate_allows_7_4_and_above(version):
    result = _run_inline_version_gate(version)
    assert result.returncode == 0, combined_text(result)
    assert "GATE-DID-NOT-EXIT" in result.stdout
    assert "BUILD FAILED" not in result.stdout


# --- P8c2: the main script's single call site must check python.exe's own
# signature, not a reused copy of the installer's. ---------------------------


def test_assert_python_and_installer_signatures_valid_rejects_a_bad_pythonexe_signature():
    # P8c2: the specific mutant to kill -- the python.exe check call site
    # fed $installerSig a second time instead of $pythonExeSig. A GOOD
    # installer signature must not be enough to pass when python.exe's own
    # signature is bad.
    good = _signature()
    bad = _signature(subject="CN=Someone Else")
    result = run_helper(
        f"$good = {good}\n$bad = {bad}\n"
        "Assert-PythonAndInstallerSignaturesValid -InstallerSignature $good -PythonExeSignature $bad "
        "-SignerSubjectContains 'Python Software Foundation'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "python.exe signer subject" in text
    assert "does not contain" in text


def test_assert_python_and_installer_signatures_valid_rejects_a_bad_installer_signature():
    good = _signature()
    bad = _signature(subject="CN=Someone Else")
    result = run_helper(
        f"$good = {good}\n$bad = {bad}\n"
        "Assert-PythonAndInstallerSignaturesValid -InstallerSignature $bad -PythonExeSignature $good "
        "-SignerSubjectContains 'Python Software Foundation'"
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "Python installer signer subject" in text
    assert "does not contain" in text


def test_assert_python_and_installer_signatures_valid_passes_when_both_good():
    good = _signature()
    result = run_helper(
        f"$good = {good}\n"
        "Assert-PythonAndInstallerSignaturesValid -InstallerSignature $good -PythonExeSignature $good "
        "-SignerSubjectContains 'Python Software Foundation'\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout


def _run_python_signature_check_call_site(
    installer_sig_expr: str, pythonexe_sig_expr: str, signer_subject_contains: str
) -> subprocess.CompletedProcess:
    """Extracts the main script's own call site for Assert-
    PythonAndInstallerSignaturesValid via the PowerShell AST -- so a mutant
    that swaps which variable the call site feeds to -PythonExeSignature
    changes what this test actually executes, unlike the tests above (which
    call the helper directly with hand-picked arguments and so cannot see a
    call-site bug) -- and runs that exact statement with synthetic signature
    objects standing in for $installerSig / $pythonExeSig."""
    call_text = _extract_ast_node_text("CommandAst", r"Assert-PythonAndInstallerSignaturesValid")
    command = (
        f". '{HELPERS}'\n"
        f"$installerSig = {installer_sig_expr}\n"
        f"$pythonExeSig = {pythonexe_sig_expr}\n"
        "$pins = [PSCustomObject]@{ python = [PSCustomObject]@{ "
        f"authenticode_signer_subject_contains = '{signer_subject_contains}' }} }}\n"
        f"{call_text}\n"
        "Write-Host DONE"
    )
    return run_pwsh(command)


def test_p8c2_real_call_site_rejects_a_bad_pythonexe_signature_with_a_good_installer_signature():
    # P8c2: the specific mutant to kill -- the real call site in
    # build_release_local.ps1 feeds $installerSig a second time instead of
    # $pythonExeSig to the -PythonExeSignature parameter. A GOOD installer
    # signature must not be enough to pass when python.exe's own signature
    # is bad, and this must be true of the real statement executed, not
    # just a helper called directly with hand-picked arguments.
    result = _run_python_signature_check_call_site(
        installer_sig_expr=_signature(),
        pythonexe_sig_expr=_signature(subject="CN=Someone Else"),
        signer_subject_contains="Python Software Foundation",
    )
    assert result.returncode != 0
    text = combined_text(result)
    assert "python.exe signer subject" in text
    assert "does not contain" in text


def test_p8c2_real_call_site_passes_when_both_signatures_are_good():
    result = _run_python_signature_check_call_site(
        installer_sig_expr=_signature(),
        pythonexe_sig_expr=_signature(),
        signer_subject_contains="Python Software Foundation",
    )
    assert result.returncode == 0, combined_text(result)
    assert "DONE" in result.stdout


# --- R-c (Risk round): Format-RedactedText (pure helper, HELPERS) and the
# real console/out\ redaction call sites (Write-Host shadow, Invoke-Checked,
# Invoke-CheckedTee, Set-RedactedFileText -- all in the main script). -------


def test_format_redacted_text_replaces_username_profile_and_computername():
    result = run_helper(
        "$env:USERNAME = 'testuser'\n"
        "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        "$env:COMPUTERNAME = 'TESTHOST'\n"
        "Write-Host (Format-RedactedText -Text "
        "'C:\\Users\\testuser\\Downloads\\python.exe on TESTHOST as testuser')"
    )
    assert result.returncode == 0, result.stderr
    assert "<profile>" in result.stdout
    assert "<user>" in result.stdout
    assert "<host>" in result.stdout
    assert "testuser" not in result.stdout
    assert "TESTHOST" not in result.stdout


def test_format_redacted_text_also_redacts_localappdata_appdata_and_temp():
    result = run_helper(
        "$env:USERNAME = ''\n$env:USERPROFILE = ''\n$env:COMPUTERNAME = ''\n"
        "$env:LOCALAPPDATA = 'D:\\redirected\\profile\\AppData\\Local'\n"
        "$env:APPDATA = 'D:\\redirected\\profile\\AppData\\Roaming'\n"
        "$env:TEMP = 'D:\\redirected\\profile\\AppData\\Local\\Temp'\n"
        "Write-Host (Format-RedactedText -Text "
        "'cache at D:\\redirected\\profile\\AppData\\Local, roaming at "
        "D:\\redirected\\profile\\AppData\\Roaming, tmp at "
        "D:\\redirected\\profile\\AppData\\Local\\Temp\\x.tmp')"
    )
    assert result.returncode == 0, result.stderr
    assert "redirected" not in result.stdout
    assert result.stdout.count("<profile>") >= 3


def test_format_redacted_text_ignores_empty_env_values_without_mangling_text():
    # An empty env value must be skipped outright: PowerShell's -replace
    # with an empty pattern matches between every character, which would
    # otherwise corrupt completely unrelated text.
    result = run_helper(
        "$env:USERNAME = ''\n$env:USERPROFILE = ''\n$env:COMPUTERNAME = ''\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "Write-Host (Format-RedactedText -Text 'plain text unaffected')\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "plain text unaffected" in result.stdout
    assert "DONE" in result.stdout


def test_format_redacted_text_only_redacts_short_names_as_a_whole_path_segment():
    result = run_helper(
        "$env:USERNAME = 'jo'\n$env:COMPUTERNAME = 'pc'\n"
        "$env:USERPROFILE = ''\n$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "Write-Host (Format-RedactedText -Text "
        "'path \\jo\\docs\\ and /pc/share/ but jotting jo2 and pcworld are untouched')"
    )
    assert result.returncode == 0, result.stderr
    assert "<user>" in result.stdout
    assert "<host>" in result.stdout
    assert "jotting jo2" in result.stdout
    assert "pcworld" in result.stdout


# --- L-C (Risk round 4): USERDOMAIN/USERDNSDOMAIN/LOGONSERVER/OneDrive*,
# the `/` form, the 8.3 short-profile form (injected), the URL-encoded
# form, and an explicit case-mismatch. ---------------------------------------


_CLEAR_NEW_REDACTION_ENV_VARS = (
    "$env:USERDOMAIN = ''\n$env:USERDNSDOMAIN = ''\n$env:LOGONSERVER = ''\n"
    "$env:OneDrive = ''\n$env:OneDriveCommercial = ''\n$env:OneDriveConsumer = ''\n"
)


def test_format_redacted_text_redacts_userdomain_userdnsdomain_and_logonserver():
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n$env:USERPROFILE = ''\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "$env:OneDrive = ''\n$env:OneDriveCommercial = ''\n$env:OneDriveConsumer = ''\n"
        "$env:USERDOMAIN = 'CONTOSO'\n$env:USERDNSDOMAIN = 'corp.contoso.example'\n"
        "$env:LOGONSERVER = '\\\\DC01'\n"
        "Write-Host (Format-RedactedText -Text "
        "'domain CONTOSO, dns corp.contoso.example, logon server \\\\DC01\\share')"
    )
    assert result.returncode == 0, result.stderr
    assert "<domain>" in result.stdout
    assert "<dnsdomain>" in result.stdout
    assert "<logonserver>" in result.stdout
    assert "CONTOSO" not in result.stdout
    assert "corp.contoso.example" not in result.stdout
    assert "DC01" not in result.stdout


def test_format_redacted_text_redacts_onedrive_env_values():
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n$env:USERPROFILE = ''\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "$env:USERDOMAIN = ''\n$env:USERDNSDOMAIN = ''\n$env:LOGONSERVER = ''\n"
        "$env:OneDrive = 'C:\\Users\\testuser\\OneDrive - Contoso Ltd'\n"
        "$env:OneDriveCommercial = 'C:\\Users\\testuser\\OneDrive - Contoso Ltd'\n"
        "$env:OneDriveConsumer = 'C:\\Users\\testuser\\OneDrive'\n"
        "Write-Host (Format-RedactedText -Text "
        "'synced at C:\\Users\\testuser\\OneDrive - Contoso Ltd\\docs and "
        "C:\\Users\\testuser\\OneDrive\\photos')"
    )
    assert result.returncode == 0, result.stderr
    assert "<profile>" in result.stdout
    assert "OneDrive" not in result.stdout
    assert "Contoso" not in result.stdout


def test_format_redacted_text_matches_the_forward_slash_form_of_a_path_value():
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS
        + "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "Write-Host (Format-RedactedText -Text "
        "'backslash C:\\Users\\testuser\\Downloads and slash C:/Users/testuser/Downloads')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("<profile>") >= 2
    assert "testuser" not in result.stdout


def test_format_redacted_text_matches_an_injected_8_3_short_profile_path():
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS
        + "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "$fakeShort = { param($p) 'C:\\Users\\TESTUS~1' }\n"
        "Write-Host (Format-RedactedText -GetShortPathFunc $fakeShort -Text "
        "'long C:\\Users\\testuser\\Downloads and short C:\\Users\\TESTUS~1\\Downloads')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("<profile>") >= 2
    assert "testuser" not in result.stdout
    assert "TESTUS~1" not in result.stdout


def test_format_redacted_text_does_not_call_the_short_path_resolver_off_windows_by_default():
    # Get-Windows83ShortPath (the real default resolver) returns $null
    # whenever -not $IsWindows, which this non-Windows test host already
    # is -- confirms the default wiring is itself safe without an
    # injected override, not just that an override works when supplied.
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS
        + "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "Write-Host (Format-RedactedText -Text 'C:\\Users\\testuser\\Downloads')\n"
        "Write-Host DONE"
    )
    assert result.returncode == 0, result.stderr
    assert "<profile>" in result.stdout
    assert "DONE" in result.stdout


def test_format_redacted_text_matches_url_encoded_forms():
    result = run_helper(
        "$env:USERNAME = ''\n$env:COMPUTERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS
        + "$env:USERPROFILE = 'C:\\Users\\jamie sibley'\n"
        "$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "$full = [uri]::EscapeDataString('C:\\Users\\jamie sibley')\n"
        "$spaceOnly = 'C:\\Users\\jamie%20sibley'\n"
        "Write-Host (Format-RedactedText -Text \"full=$full space=$spaceOnly\")"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("<profile>") >= 2
    assert "jamie" not in result.stdout


def test_format_redacted_text_is_case_insensitive_on_a_case_mismatch():
    # L-C/R5: a mutant that narrows the replace to case-sensitive must be
    # caught here -- the env value's own case ('Jamie') differs from both
    # occurrences in the text being redacted.
    result = run_helper(
        "$env:USERNAME = 'Jamie'\n$env:COMPUTERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS
        + "$env:USERPROFILE = ''\n$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "Write-Host (Format-RedactedText -Text 'seen as JAMIE and also jamie')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("<user>") == 2
    assert "JAMIE" not in result.stdout
    assert "jamie" not in result.stdout


def test_format_redacted_text_userdomain_equal_to_computername_still_fully_redacts():
    # Risk R3 note: on a personal PC USERDOMAIN often equals COMPUTERNAME --
    # confirm that coincidence does not leave the raw value behind (either
    # placeholder winning is fine; a raw leak is not).
    result = run_helper(
        "$env:USERNAME = ''\n"
        + _CLEAR_NEW_REDACTION_ENV_VARS.replace("$env:USERDOMAIN = ''\n", "")
        + "$env:USERPROFILE = ''\n$env:LOCALAPPDATA = ''\n$env:APPDATA = ''\n$env:TEMP = ''\n"
        "$env:COMPUTERNAME = 'MYPC01'\n$env:USERDOMAIN = 'MYPC01'\n"
        "Write-Host (Format-RedactedText -Text 'host MYPC01 and domain MYPC01')"
    )
    assert result.returncode == 0, result.stderr
    assert "MYPC01" not in result.stdout
    assert ("<host>" in result.stdout) or ("<domain>" in result.stdout)


# --- L-C (Risk round 4): raw stderr of direct native calls is routed
# through the redactor, via Receive-RedactedNativeOutput. --------------------


def test_receive_redacted_native_output_redacts_stderr_keeps_stdout_and_exit_code(tmp_path):
    # L-C: the specific mutant to kill -- a call site's `2>&1 | Receive-
    # RedactedNativeOutput` removed (or the function's ErrorRecord branch
    # removed), letting a native tool's raw stderr reach the console/
    # build-console.txt unredacted. A real external process (python,
    # exactly like the call sites this backs) is used so the stderr-
    # becomes-an-ErrorRecord behaviour under `2>&1` is the real mechanism,
    # not a simulated one.
    write_host_fn = _extract_function_text("Write-Host")
    receive_fn = _extract_function_text("Receive-RedactedNativeOutput")
    stub = tmp_path / "stub_stderr_tool.py"
    stub.write_text(
        "import sys\n"
        "print(r'C:\\Users\\testuser\\Downloads\\python.exe', file=sys.stderr)\n"
        "print('clean-stdout-line')\n"
        "sys.exit(5)\n",
        encoding="utf-8",
    )
    command = (
        f". '{HELPERS}'\n{write_host_fn}\n{receive_fn}\n"
        "$env:USERNAME = 'testuser'\n$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"$captured = (& '{sys.executable}' '{stub}' 2>&1 | Receive-RedactedNativeOutput) -join \"`n\"\n"
        "Write-Host \"EXIT=$LASTEXITCODE\"\n"
        "Write-Host \"CAPTURED=$captured\""
    )
    result = run_pwsh(command)
    text = combined_text(result)
    assert "<profile>" in text
    assert "testuser" not in text
    assert "EXIT=5" in text
    assert "CAPTURED=clean-stdout-line" in text


def test_git_rev_parse_head_call_site_redacts_a_mocked_stderr_line(tmp_path):
    # L-C: run the main script's own `$headSha = (...)` statement
    # (extracted via AST, not retyped) with `git` mocked as a PowerShell
    # function -- Get-Command resolves a function ahead of any real git on
    # PATH, the same trick the existing dsregcmd mocks use -- so a
    # genuinely routed call site (not just Receive-RedactedNativeOutput in
    # isolation) is shown to redact stderr while still returning the real
    # commit sha on stdout.
    write_host_fn = _extract_function_text("Write-Host")
    receive_fn = _extract_function_text("Receive-RedactedNativeOutput")
    head_sha_stmt = _extract_ast_node_text("AssignmentStatementAst", r"^\$headSha =")
    sha = "a" * 40
    git_mock = (
        "function git {\n"
        "    Write-Error 'fatal: unable to read config for C:\\Users\\testuser'\n"
        f"    Write-Output '{sha}'\n"
        "    $global:LASTEXITCODE = 0\n"
        "}\n"
    )
    command = (
        f". '{HELPERS}'\n{write_host_fn}\n{receive_fn}\n{git_mock}\n"
        "$env:USERNAME = 'testuser'\n$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"{head_sha_stmt}\n"
        "Write-Host \"HEAD=$headSha\""
    )
    result = run_pwsh(command)
    text = combined_text(result)
    assert "<profile>" in text
    assert "testuser" not in text
    assert f"HEAD={sha}" in result.stdout


def test_invoke_openssl_pin_check_redacts_python_stderr(tmp_path):
    # L-C: same mutant class as the git test above, for the `& $VenvPython
    # -c "..." 2>&1 | Receive-RedactedNativeOutput` call sites -- the
    # fake interpreter is a .ps1 stub (not a real python.exe) so it can
    # emit a fixed stderr line regardless of which -c one-liner the real,
    # unmodified function text passes it.
    root = tmp_path / "onedir"
    (root / "_internal").mkdir(parents=True)
    dll = root / "_internal" / "libcrypto-3.dll"
    dll.write_bytes(b"fake openssl dll bytes for the pin check test\n")
    real_hash = hashlib.sha256(dll.read_bytes()).hexdigest()

    fake_venv_python = tmp_path / "fake-venv-python-stderr.ps1"
    fake_venv_python.write_text(
        "Write-Error 'profile at C:\\Users\\testuser in use'\n"
        f"Write-Output '{platform.python_version()}'\n",
        encoding="utf-8",
    )
    command = (
        f". '{HELPERS}'\n"
        f"{_extract_function_text('Write-Host')}\n"
        f"{_extract_function_text('Receive-RedactedNativeOutput')}\n"
        f"{_extract_function_text('Invoke-OpenSslPinCheck')}\n"
        "$env:USERNAME = 'testuser'\n$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"$pin = {_openssl_pin_expr('', real_hash)}\n"
        f"Invoke-OpenSslPinCheck -Root '{root}' -Pin $pin -VenvPython '{fake_venv_python}'\n"
        "Write-Host DONE"
    )
    result = run_pwsh(command)
    text = combined_text(result)
    assert result.returncode == 0, text
    assert "<profile>" in text
    assert "testuser" not in text
    assert "DONE" in result.stdout


def test_invoke_checked_redacts_relayed_tool_output_and_still_passes(tmp_path):
    # R-c: the specific mutant to kill -- Invoke-Checked's relayed-output
    # pipe no longer re-emitted through the redacting Write-Host, letting a
    # tool's own stdout/stderr reach the console raw.
    write_host_fn = _extract_function_text("Write-Host")
    invoke_checked_fn = _extract_function_text("Invoke-Checked")
    stub = tmp_path / "stub_tool.py"
    stub.write_text(
        "print(r'loaded python from C:\\Users\\testuser\\Downloads\\python.exe for testuser')\n",
        encoding="utf-8",
    )
    command = (
        f". '{HELPERS}'\n{write_host_fn}\n{invoke_checked_fn}\n"
        "$env:USERNAME = 'testuser'\n$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"Invoke-Checked -FilePath '{sys.executable}' -ArgumentList @('{stub}') -FailureMessage 'stub failed'\n"
        "Write-Host DONE"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    assert "<profile>" in result.stdout
    assert "<user>" in result.stdout
    assert "testuser" not in result.stdout
    assert "DONE" in result.stdout


def test_invoke_checked_still_fails_the_gate_on_a_nonzero_exit_after_redaction(tmp_path):
    # R-c: confirms redacting the relayed output does not disturb
    # $LASTEXITCODE -- the native tool's own non-zero exit must still throw.
    write_host_fn = _extract_function_text("Write-Host")
    invoke_checked_fn = _extract_function_text("Invoke-Checked")
    stub = tmp_path / "stub_tool_fail.py"
    stub.write_text("import sys\nprint('stub failing on purpose')\nsys.exit(7)\n", encoding="utf-8")
    command = (
        f". '{HELPERS}'\n{write_host_fn}\n{invoke_checked_fn}\n"
        f"Invoke-Checked -FilePath '{sys.executable}' -ArgumentList @('{stub}') -FailureMessage 'stub failed'\n"
        "Write-Host DID-NOT-THROW"
    )
    result = run_pwsh(command)
    assert result.returncode != 0
    text = combined_text(result)
    assert "stub failed" in text
    assert "exit code 7" in text
    assert "DID-NOT-THROW" not in result.stdout


def test_invoke_checked_tee_redacts_both_the_console_copy_and_the_output_file(tmp_path):
    # R-c: the specific mutant to kill -- the ForEach-Object redaction stage
    # removed from Invoke-CheckedTee's pipeline, letting the raw text reach
    # either the console or $OutputFile (one of the out\ gate-result
    # files).
    invoke_checked_tee_fn = _extract_function_text("Invoke-CheckedTee")
    stub = tmp_path / "stub_tee.py"
    stub.write_text(
        "print(r'result at C:\\Users\\testuser\\AppData\\Local\\Temp\\pack.zip for testuser')\n",
        encoding="utf-8",
    )
    out_file = tmp_path / "l6-result.txt"
    command = (
        f". '{HELPERS}'\n{invoke_checked_tee_fn}\n"
        "$env:USERNAME = 'testuser'\n$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        "$env:LOCALAPPDATA = 'C:\\Users\\testuser\\AppData\\Local'\n"
        "$env:TEMP = 'C:\\Users\\testuser\\AppData\\Local\\Temp'\n"
        f"Invoke-CheckedTee -FilePath '{sys.executable}' -ArgumentList @('{stub}') "
        f"-FailureMessage 'stub failed' -OutputFile '{out_file}'"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    assert "<profile>" in result.stdout
    assert "testuser" not in result.stdout
    file_text = out_file.read_text(encoding="utf-8")
    assert "<profile>" in file_text
    assert "testuser" not in file_text


def test_invoke_checked_tee_still_fails_the_gate_on_a_nonzero_exit_after_redaction(tmp_path):
    invoke_checked_tee_fn = _extract_function_text("Invoke-CheckedTee")
    stub = tmp_path / "stub_tee_fail.py"
    stub.write_text("import sys\nprint('tee stub failing')\nsys.exit(3)\n", encoding="utf-8")
    out_file = tmp_path / "l6-result-fail.txt"
    command = (
        f". '{HELPERS}'\n{invoke_checked_tee_fn}\n"
        f"Invoke-CheckedTee -FilePath '{sys.executable}' -ArgumentList @('{stub}') "
        f"-FailureMessage 'tee stub failed' -OutputFile '{out_file}'\n"
        "Write-Host DID-NOT-THROW"
    )
    result = run_pwsh(command)
    assert result.returncode != 0
    text = combined_text(result)
    assert "tee stub failed" in text
    assert "exit code 3" in text
    assert "DID-NOT-THROW" not in result.stdout


def test_pe_check_redact_region_actually_redacts_the_out_file(tmp_path):
    # R-c: the specific mutant to kill -- the real call site's
    # Set-RedactedFileText line removed from section g, leaving
    # out\installer-publisher.txt raw even though Set-RedactedFileText
    # itself (tested above) still works fine in isolation. Run the region
    # completely unmodified (same trick as the pack-l6 region tests): a
    # real file at the literal relative name 'tools\pe_check.py' is what
    # the region's own `& $venvPython 'tools\pe_check.py' ...` resolves to,
    # with $venvPython pointing at this test's own interpreter.
    write_host_fn = _extract_function_text("Write-Host")
    invoke_checked_fn = _extract_function_text("Invoke-Checked")
    set_redacted_fn = _extract_function_text("Set-RedactedFileText")
    region_text = _extract_region_text("pe-check-redact")

    repo = tmp_path / "repo"
    repo.mkdir()
    _write_literal_backslash_file(
        repo, "tools\\pe_check.py",
        "import sys, pathlib\n"
        "out = pathlib.Path(sys.argv[1])\n"
        "out.write_text('exe at C:\\\\Users\\\\testuser\\\\build\\\\OrbitRxMonitor.exe\\n', encoding='utf-8')\n",
    )
    out_dir = repo / "out"
    out_dir.mkdir()
    out_file = out_dir / "installer-publisher.txt"
    command = (
        f". '{HELPERS}'\n{write_host_fn}\n{invoke_checked_fn}\n{set_redacted_fn}\n"
        "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"$venvPython = '{sys.executable}'\n"
        f"$outDir = '{out_dir}'\n"
        f"$exePath = '{repo / 'fake.exe'}'\n"
        f"$installerExePath = '{repo / 'fake-installer.exe'}'\n"
        f"{region_text}\n"
        "Write-Host REGION-DONE"
    )
    result = run_pwsh(command, cwd=repo)
    assert result.returncode == 0, combined_text(result)
    assert "REGION-DONE" in result.stdout
    file_text = out_file.read_text(encoding="utf-8")
    assert "<profile>" in file_text
    assert "testuser" not in file_text


def test_set_redacted_file_text_rewrites_a_gate_output_file_in_place(tmp_path):
    # R-c: covers the ship-set-qt/ship-set-tls/pe-check/pyz-scan files,
    # which the python tools write directly (not relayed via this script's
    # own streams), so they are redacted in place after each tool call.
    set_redacted_fn = _extract_function_text("Set-RedactedFileText")
    target = tmp_path / "ship-set-qt.txt"
    target.write_text("Qt6Core.dll shipped from C:\\Users\\testuser\\build\n", encoding="utf-8")
    command = (
        f". '{HELPERS}'\n{set_redacted_fn}\n"
        "$env:USERPROFILE = 'C:\\Users\\testuser'\n"
        f"Set-RedactedFileText -Path '{target}'\n"
        "Write-Host DONE"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    text = target.read_text(encoding="utf-8")
    assert "<profile>" in text
    assert "testuser" not in text


# --- P12c/P19: Invoke-OpenSslPinCheck, the real function (extracted from the
# main script), run against a fake onedir tree. -------------------------------


def _run_openssl_pin_check(root: Path, pin_expr: str, venv_python: str | None = None) -> subprocess.CompletedProcess:
    fn_text = _extract_function_text("Invoke-OpenSslPinCheck")
    # L-C: the function's own `& $VenvPython -c "..." 2>&1 | Receive-
    # RedactedNativeOutput` call needs this function defined too.
    receive_redacted_native_output = _extract_function_text("Receive-RedactedNativeOutput")
    command = (
        f". '{HELPERS}'\n{receive_redacted_native_output}\n{fn_text}\n"
        f"$pin = {pin_expr}\n"
        f"Invoke-OpenSslPinCheck -Root '{root}' -Pin $pin -VenvPython '{venv_python or sys.executable}'\n"
        "Write-Host DONE"
    )
    return run_pwsh(command)


def _openssl_pin_expr(file_version: str, sha256: str) -> str:
    return (
        "[PSCustomObject]@{ python = '" + platform.python_version() + "'; "
        "dlls = [PSCustomObject]@{ 'libcrypto-3.dll' = [PSCustomObject]@{ "
        f"file_version = '{file_version}'; sha256 = '{sha256}' }} }} }}"
    )


def test_invoke_openssl_pin_check_passes_when_the_measured_hash_matches_the_pin(tmp_path):
    root = tmp_path / "onedir"
    (root / "_internal").mkdir(parents=True)
    dll = root / "_internal" / "libcrypto-3.dll"
    dll.write_bytes(b"fake openssl dll bytes for the pin check test\n")
    real_hash = hashlib.sha256(dll.read_bytes()).hexdigest()

    # On a non-Windows test host, VersionInfo.FileVersion is empty for any
    # plain file (there is no real PE version resource to parse) -- pin an
    # empty file_version to match that, so only the sha256 half is live.
    result = _run_openssl_pin_check(root, _openssl_pin_expr("", real_hash))
    assert result.returncode == 0, combined_text(result)
    assert "DONE" in result.stdout


def test_invoke_openssl_pin_check_rejects_a_dll_whose_measured_hash_differs_from_the_pin(tmp_path):
    # P12c: the specific mutant to kill -- the call site passes the pin's
    # own sha256 as the "measured" value instead of the real Get-Sha256Hex
    # of the file found on disk, which would make this comparison
    # vacuously match itself no matter what the file actually contains.
    root = tmp_path / "onedir"
    (root / "_internal").mkdir(parents=True)
    dll = root / "_internal" / "libcrypto-3.dll"
    dll.write_bytes(b"fake openssl dll bytes for the pin check test\n")
    real_hash = hashlib.sha256(dll.read_bytes()).hexdigest()
    wrong_hash = "f" * 64
    assert wrong_hash != real_hash

    result = _run_openssl_pin_check(root, _openssl_pin_expr("", wrong_hash))
    assert result.returncode != 0
    text = combined_text(result)
    assert "libcrypto-3.dll sha256" in text
    assert "!=" in text


def test_invoke_openssl_pin_check_rejects_qopensslbackend_dll_presence(tmp_path):
    # P19: the specific mutant to kill -- this refusal removed from the
    # real call site, letting the legacy OpenSSL backend plugin slip into
    # the ship set unnoticed.
    root = tmp_path / "onedir"
    (root / "_internal").mkdir(parents=True)
    dll = root / "_internal" / "libcrypto-3.dll"
    dll.write_bytes(b"fake openssl dll bytes\n")
    real_hash = hashlib.sha256(dll.read_bytes()).hexdigest()
    (root / "_internal" / "qopensslbackend.dll").write_bytes(b"legacy backend plugin\n")

    result = _run_openssl_pin_check(root, _openssl_pin_expr("", real_hash))
    assert result.returncode != 0
    assert "qopensslbackend.dll reached the ship set." in combined_text(result)


# --- P20: Invoke-ShippedNoticesCheck, the real function, run against a fake
# onedir with plain text files standing in for the real notice files. --------


NOTICE_RELS = (
    "third_party/python/LICENSE.txt",
    "third_party/qt/QT_THIRD_PARTY_ATTRIBUTIONS.txt",
    "third_party/openssl/LICENSE.txt",
)


def _write_fake_notices(root: Path) -> dict:
    contents = {}
    for i, rel in enumerate(NOTICE_RELS):
        content = f"notice text #{i}\n".encode()
        path = root / "_internal" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        contents[rel] = content
    return contents


def _texts_expr(hashes: dict) -> str:
    parts = [f"'{rel}' = '{h}'" for rel, h in hashes.items()]
    return "[PSCustomObject]@{ " + "; ".join(parts) + " }"


def test_invoke_shipped_notices_check_rejects_a_tampered_notices_hash(tmp_path):
    # P20: the specific mutant to kill -- the sha256 compare against the
    # manifest's recorded text removed, so a tampered/stale notices file
    # would go unnoticed by the real call site.
    root = tmp_path / "onedir"
    contents = _write_fake_notices(root)
    hashes = {rel: hashlib.sha256(content).hexdigest() for rel, content in contents.items()}
    tampered_rel = "third_party/qt/QT_THIRD_PARTY_ATTRIBUTIONS.txt"
    hashes[tampered_rel] = "f" * 64

    fn_text = _extract_function_text("Invoke-ShippedNoticesCheck")
    # L-C: the function's own `& $VenvPython -c "..." 2>&1 | Receive-
    # RedactedNativeOutput` call needs this function defined too.
    receive_redacted_native_output = _extract_function_text("Receive-RedactedNativeOutput")
    command = (
        f". '{HELPERS}'\n{receive_redacted_native_output}\n{fn_text}\n"
        f"$texts = {_texts_expr(hashes)}\n"
        f"Invoke-ShippedNoticesCheck -Root '{root}' -Texts $texts -VenvPython '{sys.executable}'"
    )
    result = run_pwsh(command)
    assert result.returncode != 0
    text = combined_text(result)
    assert tampered_rel.split("/")[-1] in text or "QT_THIRD_PARTY_ATTRIBUTIONS" in text
    assert "sha256" in text
    assert "!=" in text


def test_invoke_shipped_notices_check_passes_when_all_hashes_match(tmp_path):
    # The function's last check reads the *build interpreter's own*
    # LICENSE.txt (sys.base_prefix) and compares it to the pinned python
    # notice hash too -- sys.executable's real base_prefix on this test
    # host has no reason to contain one, so -VenvPython here is a tiny
    # stub that reports a fake base_prefix directory this test controls,
    # containing a LICENSE.txt with exactly the pinned content. The stub
    # is a .ps1 (not a '#!/bin/sh' script) so pwsh's own `&` call operator
    # runs it directly on both Linux and Windows, with no shebang/chmod
    # involved either way.
    root = tmp_path / "onedir"
    contents = _write_fake_notices(root)
    hashes = {rel: hashlib.sha256(content).hexdigest() for rel, content in contents.items()}

    fake_base_prefix = tmp_path / "fake-base-prefix"
    fake_base_prefix.mkdir()
    (fake_base_prefix / "LICENSE.txt").write_bytes(contents["third_party/python/LICENSE.txt"])
    fake_venv_python = tmp_path / "fake-venv-python.ps1"
    fake_base_prefix_literal = str(fake_base_prefix).replace("'", "''")
    fake_venv_python.write_text(f"Write-Output '{fake_base_prefix_literal}'\n", encoding="utf-8")

    fn_text = _extract_function_text("Invoke-ShippedNoticesCheck")
    receive_redacted_native_output = _extract_function_text("Receive-RedactedNativeOutput")
    command = (
        f". '{HELPERS}'\n{receive_redacted_native_output}\n{fn_text}\n"
        f"$texts = {_texts_expr(hashes)}\n"
        f"Invoke-ShippedNoticesCheck -Root '{root}' -Texts $texts -VenvPython '{fake_venv_python}'"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    assert "SHIPPED-NOTICES: PASS" in result.stdout


# --- C6: the "tool-caches" region (section d), extracted from the main
# script and run standalone against a fake -BuildRoot. -----------------------


def test_tool_caches_region_points_pip_and_pyinstaller_caches_under_buildroot(tmp_path):
    region_text = _extract_region_text("tool-caches")
    build_root = tmp_path / "build-root"
    command = (
        f"$BuildRoot = '{build_root}'\n"
        f"{region_text}\n"
        "Write-Output \"PIP_CACHE_DIR=$env:PIP_CACHE_DIR\"\n"
        "Write-Output \"PYINSTALLER_CONFIG_DIR=$env:PYINSTALLER_CONFIG_DIR\"\n"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    assert "TOOL-CACHES: PASS" in result.stdout
    pip_match = re.search(r"PIP_CACHE_DIR=(.+)", result.stdout)
    pyi_match = re.search(r"PYINSTALLER_CONFIG_DIR=(.+)", result.stdout)
    assert pip_match and pyi_match, result.stdout
    pip_dir = Path(pip_match.group(1).strip())
    pyi_dir = Path(pyi_match.group(1).strip())
    # Both env vars must point at real, already-created directories under
    # -BuildRoot (not the host's default %LOCALAPPDATA%/%TEMP% locations),
    # and be distinct from each other.
    assert pip_dir.is_dir()
    assert pyi_dir.is_dir()
    assert pip_dir.is_relative_to(build_root)
    assert pyi_dir.is_relative_to(build_root)
    assert pip_dir != pyi_dir


def test_tool_caches_region_does_not_touch_temp_or_tmp(tmp_path):
    # Deliberate choice (see the region's own comment): redirecting
    # $env:TEMP/$env:TMP would change what Format-RedactedText treats as
    # "this PC's temp folder" for every redaction call after this point.
    region_text = _extract_region_text("tool-caches")
    build_root = tmp_path / "build-root"
    command = (
        "$env:TEMP = '/original/temp'\n"
        "$env:TMP = '/original/tmp'\n"
        f"$BuildRoot = '{build_root}'\n"
        f"{region_text}\n"
        "Write-Output \"TEMP=$env:TEMP\"\n"
        "Write-Output \"TMP=$env:TMP\"\n"
    )
    result = run_pwsh(command)
    assert result.returncode == 0, combined_text(result)
    assert "TEMP=/original/temp" in result.stdout
    assert "TMP=/original/tmp" in result.stdout


# --- N2e/P14/P15: the "pack-l6" region (section i), extracted from the main
# script and run standalone in a fake git repo with stubbed tool scripts. ----


def _write_literal_backslash_file(root: Path, leaf_with_backslash: str, content: str) -> None:
    # The real script invokes these with a Windows-style relative path
    # (e.g. 'tools\pack_setup_zip.py') unmodified. On a non-Windows test
    # host, Python opens that literal filename (backslash is just an
    # ordinary character in a POSIX file name, not a separator) relative
    # to the process's cwd, so a real *file* whose name contains a
    # backslash is what the stub needs there. On Windows, backslash *is*
    # the path separator, so the same literal string instead resolves to
    # a real subdirectory ('tools\pack_setup_zip.py' -> tools/pack_setup_zip.py)
    # which must actually exist. Either way, the extracted region's own
    # unmodified `& $venvPython 'tools\pack_setup_zip.py' ...` call
    # resolves to our stub, with no change to the extracted text at all.
    if os.name == "nt":
        target = root / Path(*leaf_with_backslash.split("\\"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    else:
        (root / leaf_with_backslash).write_text(content, encoding="utf-8")


def _make_pack_l6_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "placeholder.txt").write_text("placeholder\n", encoding="utf-8")
    _git(repo, "add", "-A")
    commit = _git(repo, "commit", "-q", "-m", "initial")
    assert commit.returncode == 0, commit.stderr
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert len(sha) == 40
    return repo, sha


def _run_pack_l6_region(
    repo: Path, sha: str, pack_stub: str, ship_set_stub: str, extra_harness: str = ""
) -> subprocess.CompletedProcess:
    _write_literal_backslash_file(repo, "tools\\pack_setup_zip.py", pack_stub)
    _write_literal_backslash_file(repo, "tools\\ship_set.py", ship_set_stub)

    out_dir = repo / "out"
    out_dir.mkdir(exist_ok=True)
    onedir_root = repo / "fake-onedir"
    onedir_root.mkdir(exist_ok=True)
    installer_exe = repo / "fake-installer.exe"
    installer_exe.write_bytes(b"fake installer bytes")
    ci_inventory = repo / "fake-ci-inventory.txt"
    ci_inventory.write_text(f"version=5.2.0 commit={sha}\n", encoding="utf-8")
    local_inventory = repo / "fake-local-inventory.txt"
    local_inventory.write_text(f"version=5.2.0 commit={sha}\n", encoding="utf-8")

    region_text = _extract_region_text("pack-l6")
    invoke_checked = _extract_function_text("Invoke-Checked")
    invoke_checked_tee = _extract_function_text("Invoke-CheckedTee")
    # L-C: the region's own `$commitEpoch = (git show ... 2>&1 | Receive-
    # RedactedNativeOutput) ...` line needs this function defined too, same
    # as Invoke-Checked/Invoke-CheckedTee above.
    receive_redacted_native_output = _extract_function_text("Receive-RedactedNativeOutput")

    harness = (
        f". '{HELPERS}'\n"
        f"{invoke_checked}\n{invoke_checked_tee}\n{receive_redacted_native_output}\n"
        f"{extra_harness}\n"
        f"$repoRoot = '{repo}'\n"
        f"$ExpectedSha = '{sha}'\n"
        "$version = '5.2.0'\n"
        f"$outDir = '{out_dir}'\n"
        f"$onedirRoot = '{onedir_root}'\n"
        f"$installerExePath = '{installer_exe}'\n"
        f"$CiInventory = '{ci_inventory}'\n"
        f"$localInventoryPath = '{local_inventory}'\n"
        f"$venvPython = '{sys.executable}'\n"
        "try {\n"
        f"{region_text}\n"
        "    Write-Host 'REGION-COMPLETED-OK'\n"
        "} catch {\n"
        "    Write-Host \"REGION-THREW: $($_.Exception.Message)\"\n"
        "    exit 1\n"
        "}\n"
    )
    return run_pwsh(harness, cwd=repo)


_PACK_STUB_ALWAYS_OK = """\
import sys, zipfile
args = sys.argv[1:]
if "--verify" in args or "--compare-tree" in args:
    sys.exit(0)
if "--out" in args:
    out = args[args.index("--out") + 1]
    with zipfile.ZipFile(out, "w") as zf:
        # A fixed date_time: zipfile defaults to the current local time,
        # which would make two otherwise-identical calls produce different
        # bytes (and so a different sha256) purely from invocation timing
        # -- not what this stub is simulating.
        dt = (1980, 1, 1, 0, 0, 0)
        zf.writestr(zipfile.ZipInfo("OrbitRxMonitor/dummy.txt", date_time=dt), b"same content every time")
        zf.writestr(zipfile.ZipInfo("OrbitRxMonitor-Setup.exe", date_time=dt), b"fake installer bytes")
    sys.exit(0)
sys.exit(1)
"""

_SHIP_SET_STUB_ALWAYS_OK = "import sys\nsys.exit(0)\n"


def test_pack_l6_region_succeeds_when_every_tool_call_passes(tmp_path):
    # Positive control for the three tests below: proves the harness
    # itself (fake repo, stubs, pre-set variables) exercises the real
    # region successfully when nothing is wrong, so a failure reported by
    # the other tests is attributable to the specific mutant/condition
    # under test, not to a broken harness.
    repo, sha = _make_pack_l6_repo(tmp_path)
    result = _run_pack_l6_region(repo, sha, _PACK_STUB_ALWAYS_OK, _SHIP_SET_STUB_ALWAYS_OK)
    text = combined_text(result)
    assert result.returncode == 0, text
    assert "REGION-COMPLETED-OK" in result.stdout
    pending = repo / "out" / "OrbitRx-Setup-5.2.0.zip.pending"
    assert pending.exists(), "section i leaves the pending zip for section j to finalize"


def test_pack_l6_region_ship_set_failure_on_extracted_tree_removes_the_pending_zip(tmp_path):
    # P14: the real ship_set.py --check call in this region only ever
    # targets the extracted tree (the onedir-root check lives in section g,
    # outside this region) -- fail it and confirm (a) the failure reaches
    # the caller and (b) it was really invoked against the *extracted*
    # OrbitRxMonitor tree, by having the stub record its own argv.
    repo, sha = _make_pack_l6_repo(tmp_path)
    marker = repo / "ship-set-argv.txt"
    ship_set_stub = (
        "import sys, pathlib\n"
        f"pathlib.Path(r'{marker}').write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        "sys.exit(1)\n"
    )
    result = _run_pack_l6_region(repo, sha, _PACK_STUB_ALWAYS_OK, ship_set_stub)
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "ship_set --check failed on the extracted zip" in text

    assert marker.exists(), "ship_set.py stub was never invoked"
    argv_text = marker.read_text(encoding="utf-8")
    assert "extracted" in argv_text
    assert argv_text.rstrip().endswith("OrbitRxMonitor")

    pending = repo / "out" / "OrbitRx-Setup-5.2.0.zip.pending"
    assert not pending.exists(), "a failed L6 check must not leave the pending zip behind"


def test_pack_l6_region_later_compare_tree_failure_removes_the_pending_zip(tmp_path):
    # N2e: a check that runs *after* the zip has already been written and
    # passed L5 (here, --compare-tree) must still delete the pending zip
    # when it fails -- this is section i's own local catch, exercised by
    # actually making a later step fail rather than just reading its text.
    repo, sha = _make_pack_l6_repo(tmp_path)
    pack_stub = _PACK_STUB_ALWAYS_OK.replace(
        'if "--verify" in args or "--compare-tree" in args:\n    sys.exit(0)',
        'if "--compare-tree" in args:\n    sys.exit(1)\nif "--verify" in args:\n    sys.exit(0)',
    )
    result = _run_pack_l6_region(repo, sha, pack_stub, _SHIP_SET_STUB_ALWAYS_OK)
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "L6" in text and "did not match" in text

    pending = repo / "out" / "OrbitRx-Setup-5.2.0.zip.pending"
    assert not pending.exists(), "a later L6 compare-tree failure must not leave the pending zip behind"


def test_pack_l6_region_determinism_mismatch_removes_the_pending_zip(tmp_path):
    # P15: the specific mutant to kill -- the two-hash comparison (or its
    # throw) removed. Feed it two packs that are genuinely different (the
    # stub writes different bytes on its 1st vs 2nd --out call) and confirm
    # the real comparison catches it and the pending zip is removed.
    repo, sha = _make_pack_l6_repo(tmp_path)
    counter = repo / "pack-call-count.txt"
    pack_stub = (
        "import sys, zipfile, pathlib\n"
        "args = sys.argv[1:]\n"
        "if '--verify' in args or '--compare-tree' in args:\n"
        "    sys.exit(0)\n"
        f"counter = pathlib.Path(r'{counter}')\n"
        "count = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(count))\n"
        "out = args[args.index('--out') + 1]\n"
        "content = b'zip-content-v1' if count == 1 else b'zip-content-v2-DIFFERENT'\n"
        "with zipfile.ZipFile(out, 'w') as zf:\n"
        "    zf.writestr('OrbitRxMonitor/dummy.txt', content)\n"
        "    zf.writestr('OrbitRxMonitor-Setup.exe', b'fake installer bytes')\n"
        "sys.exit(0)\n"
    )
    result = _run_pack_l6_region(repo, sha, pack_stub, _SHIP_SET_STUB_ALWAYS_OK)
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "DETERMINISM SELF-CHECK FAILED" in text

    pending = repo / "out" / "OrbitRx-Setup-5.2.0.zip.pending"
    assert not pending.exists(), "a determinism self-check failure must not leave the pending zip behind"


# --- P10: the "provenance-finalize" region (end of section j), run
# standalone with a synthetic unsafe marker in $provenanceText. --------------


def _run_provenance_finalize_region(
    out_dir: Path, provenance_text: str, pending_zip: Path, zip_name: str, final_zip: Path
) -> subprocess.CompletedProcess:
    region_text = _extract_region_text("provenance-finalize")
    provenance_text_literal = provenance_text.replace("'", "''")
    harness = (
        f". '{HELPERS}'\n"
        f"$outDir = '{out_dir}'\n"
        "$version = '5.2.0'\n"
        f"$provenanceText = '{provenance_text_literal}'\n"
        f"$zipPath = '{pending_zip}'\n"
        f"$zipName = '{zip_name}'\n"
        f"$zipFinalPath = '{final_zip}'\n"
        "$zipFinalized = $false\n"
        "try {\n"
        f"{region_text}\n"
        "    Write-Host 'REGION-COMPLETED-OK'\n"
        "} catch {\n"
        "    Write-Host \"REGION-THREW: $($_.Exception.Message)\"\n"
        "    exit 1\n"
        "}\n"
    )
    return run_pwsh(harness, cwd=out_dir)


def test_provenance_finalize_region_blocks_on_an_unsafe_marker(tmp_path):
    # P10: the specific mutant to kill -- the self-check `if` condition
    # forced to $false (or the call site removed), letting an unsafe
    # provenance record reach disk and the zip get promoted to its public
    # name anyway. ZZ99 9ZZ is the UK's reserved placeholder postcode (not
    # a real one), used here purely to trigger the postcode-shaped pattern
    # the self-check scans for.
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    pending_zip = out_dir / "OrbitRx-Setup-5.2.0.zip.pending"
    pending_zip.write_bytes(b"a pending zip that has already passed L5/L6/determinism")
    final_zip = out_dir / "OrbitRx-Setup-5.2.0.zip"
    provenance_path = out_dir / "OrbitRx-5.2.0-PROVENANCE.txt"

    result = _run_provenance_finalize_region(
        out_dir, "some provenance text with address ZZ99 9ZZ in it",
        pending_zip, "OrbitRx-Setup-5.2.0.zip", final_zip,
    )
    text = combined_text(result)
    assert result.returncode != 0, text
    assert "REGION-THREW" in result.stdout
    assert "Provenance text self-check failed" in text
    assert "UK-postcode-pattern" in text

    assert not provenance_path.exists(), "an unsafe provenance record must never be written to disk"
    assert pending_zip.exists(), "the pending zip must not be renamed when the self-check fails"
    assert not final_zip.exists(), "no file may exist under the public zip name"


def test_provenance_finalize_region_writes_and_renames_on_clean_text(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    pending_zip = out_dir / "OrbitRx-Setup-5.2.0.zip.pending"
    pending_zip.write_bytes(b"a pending zip that has already passed L5/L6/determinism")
    final_zip = out_dir / "OrbitRx-Setup-5.2.0.zip"
    provenance_path = out_dir / "OrbitRx-5.2.0-PROVENANCE.txt"

    result = _run_provenance_finalize_region(
        out_dir, "OrbitRx 5.2.0 local build provenance, sha256=abcdef, clean text",
        pending_zip, "OrbitRx-Setup-5.2.0.zip", final_zip,
    )
    assert result.returncode == 0, combined_text(result)
    assert "REGION-COMPLETED-OK" in result.stdout
    assert provenance_path.exists()
    assert final_zip.exists()
    assert not pending_zip.exists()


# --- R-b (Risk round): the "sums-line" region -- the SUMS line the script
# prints at the end must always be preceded by a clearly-marked "do not
# publish unless cleared" warning, since the script cannot know whether this
# run is the cleared build. ---------------------------------------------------


def _run_sums_line_region(zip_sha256: str, zip_name: str) -> subprocess.CompletedProcess:
    region_text = _extract_region_text("sums-line")
    command = (
        f"$zipSha256 = '{zip_sha256}'\n"
        f"$zipName = '{zip_name}'\n"
        f"{region_text}\n"
    )
    return run_pwsh(command)


def test_sums_line_region_prints_the_not_for_publication_marker_immediately_before_the_sums_line():
    # R-b: the specific mutant to kill -- the marker Write-Host removed (or
    # moved away from directly above the SUMS line), which would let the
    # SUMS line print unguarded.
    zip_sha256 = "a" * 64
    zip_name = "OrbitRxMonitor-5.2.0-Setup.zip"
    result = _run_sums_line_region(zip_sha256, zip_name)
    assert result.returncode == 0, combined_text(result)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    marker_idx = next(i for i, line in enumerate(lines) if "DRY-RUN ONLY" in line)
    assert "NOT FOR PUBLICATION" in lines[marker_idx]
    assert "<CLEARED_SHA>" in lines[marker_idx]
    assert "P8" in lines[marker_idx]
    assert marker_idx + 1 < len(lines), "the SUMS line must immediately follow the marker"
    assert lines[marker_idx + 1] == f"{zip_sha256}  {zip_name}"


def test_sums_line_region_labels_rather_than_instructs(tmp_path):
    # I-3: the old "REMINDER (L9): append exactly this one line..." wording
    # read as an instruction to act now, including during a dry run, where
    # appending it would be wrong. It must now read as a label for what the
    # marker+SUMS line below are, not a command, and the old wording must
    # be gone.
    zip_sha256 = "b" * 64
    zip_name = "OrbitRxMonitor-5.2.0-Setup.zip"
    result = _run_sums_line_region(zip_sha256, zip_name)
    assert result.returncode == 0, combined_text(result)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    label_idx = next(i for i, line in enumerate(lines) if "SUMS line for a QA/Risk-cleared build only" in line)
    assert "(see marker)" in lines[label_idx]
    marker_idx = next(i for i, line in enumerate(lines) if "DRY-RUN ONLY" in line)
    assert label_idx < marker_idx
    assert "REMINDER (L9)" not in combined_text(result)
