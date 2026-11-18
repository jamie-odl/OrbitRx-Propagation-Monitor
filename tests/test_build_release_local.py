"""Static checks on tools/build_release_local.ps1, its helpers file and its
pins file.

Pure text/JSON checks -- pwsh is not required for this file to run on
ubuntu. A real PowerShell parse-check lives in .github/workflows/ci.yml's
Windows leg (see test_ci_parse_checks_build_release_local_ps1 below).
Dynamic (pwsh-executed) checks of the helper functions and of the main
script's argument validation live in tests/test_build_release_local_pwsh.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "tools" / "build_release_local.ps1").read_text(encoding="utf-8")
HELPERS = (ROOT / "tools" / "build_release_local.helpers.ps1").read_text(encoding="utf-8")
COMBINED = SCRIPT + "\n" + HELPERS

NETWORK_AND_PUBLISH_COMMANDS = (
    "Invoke-WebRequest",
    "Invoke-RestMethod",
    "Start-BitsTransfer",
    "curl ",
    "curl.exe",
    "wget ",
    "wget.exe",
    "gh ",
    "git push",
    "git tag",
)

UK_POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b")
BUILD_RELEASE_MD = (ROOT / "BUILD-RELEASE.md").read_text(encoding="utf-8")
# Markdown line-wraps prose at ~80 columns, so a phrase spanning a wrap point
# has a newline (plus indentation) where a single space would be in running
# text; collapse all whitespace runs to one space before substring-matching
# such phrases.
BUILD_RELEASE_MD_FLAT = re.sub(r"\s+", " ", BUILD_RELEASE_MD)


def test_script_and_helpers_files_exist_and_are_ascii():
    assert (ROOT / "tools" / "build_release_local.ps1").is_file()
    assert (ROOT / "tools" / "build_release_local.helpers.ps1").is_file()
    SCRIPT.encode("ascii")  # raises if any non-ASCII character slipped in
    HELPERS.encode("ascii")


def test_main_script_dot_sources_the_helpers_file():
    assert "build_release_local.helpers.ps1" in SCRIPT
    assert re.search(r"^\.\s*\(Join-Path \$PSScriptRoot 'build_release_local\.helpers\.ps1'\)", SCRIPT, re.MULTILINE)


def test_refuses_onedrive_and_desktop_paths():
    assert "OneDrive" in COMBINED
    assert "Desktop" in COMBINED
    assert "GetFolderPath('Desktop')" in COMBINED
    assert "OneDriveConsumer" in COMBINED and "OneDriveCommercial" in COMBINED


def test_n4_guard_covers_reparse_points_and_subst_and_unc():
    assert "ReparsePoint" in HELPERS
    assert "Test-SubstOrNetworkDrivePath" in HELPERS
    assert "subst" in HELPERS.lower()
    assert "Win32_LogicalDisk" in HELPERS
    assert r"\\\\" in HELPERS or "StartsWith('\\\\\\\\')" in HELPERS or "'\\\\'" in HELPERS


def test_n4_path_guards_run_up_front_for_repo_root_buildroot_inventory_and_python_paths():
    section = SCRIPT.split("# --- N4:", 1)[1].split("# --- b.", 1)[0]
    assert "Assert-SafeBuildPath -Path $repoRoot" in section
    assert "Assert-SafeBuildPath -Path $BuildRoot" in section
    assert "Assert-SafeBuildPath -Path $CiInventory" in section
    assert "Assert-SafeBuildPath -Path $PythonExe" in section
    assert "Assert-SafeBuildPath -Path $PythonInstaller" in section


def test_n8_early_build_root_outside_userprofile_check():
    assert "Assert-BuildRootOutsideUserProfile" in HELPERS
    assert "Assert-BuildRootOutsideUserProfile" in SCRIPT
    # Must run before the clean-clone check (step b), i.e. early.
    assert SCRIPT.index("Assert-BuildRootOutsideUserProfile") < SCRIPT.index("# --- b.")


def test_m1_refuses_up_front_on_a_non_empty_buildroot_out():
    # M-1: before any build work (pip install, PyInstaller, the 20-40
    # minute build), refuse if -BuildRoot's out\ already exists and holds
    # something -- not just let the packer's own "<out>.pending" cleanup
    # (NEW-2/L-4a) silently leave a stale public zip behind. Must run after
    # the BuildRoot path guard (so $BuildRoot is known-safe) but before the
    # clean-clone check (step b), i.e. before any git/build work starts.
    assert "Assert-BuildRootOutsideUserProfile" in SCRIPT
    section = SCRIPT.split("Assert-BuildRootOutsideUserProfile -BuildRootFull $buildRootFull", 1)[1].split(
        "# --- b.", 1
    )[0]
    assert "$outDir = Join-Path $BuildRoot 'out'" in section
    assert "Get-ChildItem -LiteralPath $outDir -Force" in section
    assert "already exists and is not empty" in section
    assert "new, empty BuildRoot" in section
    assert "throw" in section
    # Only one definition of $outDir in the whole script -- section g (the
    # ship-set/PE/PYZ gates) must reuse it, not recompute it a second time.
    assert SCRIPT.count("$outDir = Join-Path $BuildRoot 'out'") == 1


def test_checks_head_against_expected_sha():
    assert "$ExpectedSha" in SCRIPT
    assert "git rev-parse HEAD" in SCRIPT
    assert "40-hex" in COMBINED or "{40}" in COMBINED


def test_requires_a_clean_working_tree_before_building():
    assert "git status --porcelain --ignored" in SCRIPT


def test_reads_the_python_installer_pin_from_the_pins_file_not_hardcoded():
    assert "packaging\\local_build_pins.json" in SCRIPT
    # P6: the sha256/md5 compare itself is a pure helper (Assert-
    # PythonInstallerHashesMatch, in HELPERS) so it can be tested with
    # synthetic hashes; the main script's call site passes $pins.python,
    # not the individual pin fields, as that helper's -PythonPin.
    assert "Assert-PythonInstallerHashesMatch -Sha256 $installerSha256 -Md5 $installerMd5 -PythonPin $pins.python" in SCRIPT
    assert "PythonPin.installer_sha256" in HELPERS
    assert "PythonPin.installer_md5" in HELPERS
    # The actual hash value must not be duplicated as a literal anywhere.
    pins = json.loads((ROOT / "packaging" / "local_build_pins.json").read_text(encoding="utf-8"))
    assert pins["python"]["installer_sha256"] not in COMBINED
    assert pins["python"]["installer_md5"] not in COMBINED


def test_checks_authenticode_signatures_for_python():
    assert "Get-AuthenticodeSignature" in SCRIPT
    assert "authenticode_signer_subject_contains" in SCRIPT
    # P8: the Status/signer-subject decision is a shared pure helper
    # (Assert-AuthenticodeSignatureValid, in HELPERS) so it can be tested
    # with a synthetic signature object.
    assert "[regex]::Escape($SignerSubjectContains)" in HELPERS
    # P8c2: the main script reads the pin at exactly one call site, which
    # forwards both already-retrieved signature objects by name to a
    # shared helper (Assert-PythonAndInstallerSignaturesValid, in HELPERS)
    # that itself calls Assert-AuthenticodeSignatureValid twice, once per
    # label -- see test_assert_python_and_installer_signatures_valid_* in
    # test_build_release_local_pwsh.py for the behavioural check that the
    # python.exe check really receives $pythonExeSig, not $installerSig.
    assert "Assert-PythonAndInstallerSignaturesValid -InstallerSignature $installerSig -PythonExeSignature $pythonExeSig -SignerSubjectContains $pins.python.authenticode_signer_subject_contains" in SCRIPT
    assert "Assert-PythonAndInstallerSignaturesValid" in HELPERS
    helper_body = HELPERS.split("function Assert-PythonAndInstallerSignaturesValid", 1)[1].split("\n}\n", 1)[0]
    assert helper_body.count("Assert-AuthenticodeSignatureValid") == 2
    assert "-Label 'Python installer'" in helper_body
    assert "-Label 'python.exe'" in helper_body


def test_n8_records_signer_thumbprints_in_provenance():
    assert "SignerCertificate.Thumbprint" in SCRIPT
    assert "installerSignerThumbprint" in SCRIPT
    assert "pythonExeSignerThumbprint" in SCRIPT


def test_attest_personal_kit_is_required():
    assert "[switch]$AttestPersonalKit" in SCRIPT
    assert "Assert-PersonalKitAttested" in SCRIPT
    assert "Assert-PersonalKitAttested" in HELPERS
    guard = HELPERS.split("function Assert-PersonalKitAttested", 1)
    assert len(guard) == 2
    assert "throw" in guard[1].split("}\n}")[0]


def test_n9_managed_device_heuristic_via_dsregcmd():
    assert "dsregcmd" in SCRIPT
    assert "ConvertFrom-DsregcmdStatus" in HELPERS
    assert "Test-ManagedDeviceStatus" in HELPERS
    assert "DomainJoined" in COMBINED and "AzureAdJoined" in COMBINED and "EnterpriseJoined" in COMBINED
    assert "WorkplaceJoined" in COMBINED
    assert "not available" in SCRIPT
    # The main script must not capture or print anything else from dsregcmd.
    assert "tenant" not in SCRIPT.lower()
    assert "DeviceId" not in SCRIPT
    assert "TenantId" not in SCRIPT
    assert "TenantName" not in SCRIPT


def test_l_b_managed_device_check_region_exists_and_covers_ruling_2():
    # Risk R3 Ruling 2 / L-B, in full: the call site must refuse on a
    # non-zero dsregcmd exit code, empty output, and dsregcmd missing on
    # Windows -- not just on a parsed YES (that part pre-dates this round).
    assert "# region managed-device-check" in SCRIPT
    assert "# endregion managed-device-check" in SCRIPT
    region = SCRIPT.split("# region managed-device-check", 1)[1].split("# endregion managed-device-check", 1)[0]
    assert "$IsWindows" in region
    assert "UNVERIFIED" in region
    assert "$LASTEXITCODE" in region
    assert "Stop and tell Risk" in region


def test_l_b_no_override_switch_or_env_var_bypasses_the_managed_device_check():
    # Risk R3 Ruling 2: no switch, parameter, environment variable or config
    # may bypass or downgrade the check; -AttestPersonalKit stays required
    # in addition to it, never a substitute.
    region = SCRIPT.split("# region managed-device-check", 1)[1].split("# endregion managed-device-check", 1)[0]
    lowered = region.lower()
    for forbidden in ("skipmanageddevicecheck", "skip-managed-device", "ignoremanageddevice", "bypassmanageddevice"):
        assert forbidden not in lowered
    assert "-AttestPersonalKit" in SCRIPT
    assert "Assert-PersonalKitAttested" in SCRIPT


def test_l_b_duplicate_yes_cannot_be_overwritten_by_a_later_no():
    # The core L-B fail-open bug: ConvertFrom-DsregcmdStatus must not let a
    # later clean line for the same key erase an earlier YES ("last value
    # wins"). The fix keeps a YES sticky once seen.
    fn = HELPERS.split("function ConvertFrom-DsregcmdStatus", 1)[1].split("\nfunction ", 1)[0]
    assert "-ne 'YES'" in fn or "-ne \"YES\"" in fn


def test_build_release_md_managed_device_wording_matches_ruling_2():
    assert "Access work or school is empty" in BUILD_RELEASE_MD_FLAT
    assert "a duplicate YES counts" in BUILD_RELEASE_MD_FLAT
    assert "exits non-zero, or its output is empty" in BUILD_RELEASE_MD_FLAT
    assert "UNVERIFIED" in BUILD_RELEASE_MD
    assert "cannot be bypassed, downgraded or skipped" in BUILD_RELEASE_MD_FLAT
    assert "Stop and tell Risk" in BUILD_RELEASE_MD_FLAT or "stop and tell Risk" in BUILD_RELEASE_MD_FLAT
    assert "Do not disconnect accounts" in BUILD_RELEASE_MD_FLAT
    assert "never the device ID, tenant name or tenant ID" in BUILD_RELEASE_MD_FLAT


def test_never_contacts_the_network_or_publishes():
    for needle in NETWORK_AND_PUBLISH_COMMANDS:
        assert needle not in SCRIPT, needle
        assert needle not in HELPERS, needle


def test_r_c_console_and_out_file_redaction_is_wired_up():
    # R-c: Format-RedactedText is the pure helper; Write-Host is shadowed so
    # every existing call site (and the top-level catch's own BUILD FAILED
    # line) is covered without being rewritten individually; Invoke-Checked
    # and Invoke-CheckedTee relay tool output through it; Set-RedactedFileText
    # rewrites the three out\ files the python tools write directly.
    assert "function Format-RedactedText" in HELPERS
    assert "function Write-Host" in SCRIPT
    assert "Format-RedactedText -Text \"$Object\"" in SCRIPT
    assert "Invoke-Checked" in SCRIPT and "ForEach-Object { Write-Host \"$_\" }" in SCRIPT
    assert "Invoke-CheckedTee" in SCRIPT and "Format-RedactedText -Text \"$_\"" in SCRIPT
    assert "Get-Command Format-RedactedText -ErrorAction SilentlyContinue" in SCRIPT
    for call in (
        "Set-RedactedFileText -Path $shipSetQtList",
        "Set-RedactedFileText -Path $shipSetTlsList",
        "Set-RedactedFileText -Path $peCheckOut",
        "Set-RedactedFileText -Path $pyzScanOut",
    ):
        assert call in SCRIPT, call
    # ship-set-inventory.txt (local) is the one out\ file deliberately left
    # unredacted (it is compared byte-for-byte via --compare-tree); confirm
    # the decision is documented at its construction site, not silently
    # dropped.
    assert "Set-RedactedFileText -Path $localInventoryPath" not in SCRIPT
    assert "deliberately NOT passed through" in re.sub(r"\s+", " ", SCRIPT)


def test_docstring_accurately_describes_the_one_network_access_pip_makes():
    # NEW-3: the script does reach a network host -- pip fetching the
    # hash-pinned wheels from PyPI -- so the header must say that, not
    # claim no network contact happens at all.
    assert "never contacts any network host" not in SCRIPT
    assert "PyPI" in SCRIPT
    assert "--require-hashes" in SCRIPT.split(".DESCRIPTION", 1)[1].split(".PARAMETER", 1)[0]
    # L-D: the header must not claim this is the *only* network touchpoint
    # -- several UI/capture tests also make non-asserting background
    # fetches, and that must be said too, not buried.
    assert "nothing else in" not in SCRIPT
    assert "Network access happens in three places" in re.sub(r"\s+", " ", SCRIPT)


def test_docstring_network_wording_lists_all_three_touchpoints_exactly(): # L-D
    # Risk round 4 (L-D): the header must list exactly pip's PyPI
    # hash-pinned downloads, Windows' own Authenticode CRL/OCSP lookups,
    # AND the UI/capture tests' tolerated-offline background fetches
    # (NOAA SWPC, hamqsl, PSKReporter, the contest calendar, the
    # api.github.com update check) -- not just the first two.
    description = SCRIPT.split(".DESCRIPTION", 1)[1].split(".PARAMETER", 1)[0]
    description_flat = re.sub(r"\s+", " ", description)
    assert "pip downloading the wheels" in description_flat
    assert "from PyPI" in description_flat
    assert "'not network'" in description_flat or '"not network"' in description_flat
    assert "CRL/OCSP" in description_flat
    assert "certificate revocation data" in description_flat
    for host_or_fetch in ("NOAA SWPC", "hamqsl", "PSKReporter", "contest calendar", "api.github.com"):
        assert host_or_fetch in description_flat, host_or_fetch
    assert "tolerates being offline" in description_flat
    assert "do not assert on the fetch" in description_flat


def test_does_not_auto_install_python_or_inno_setup():
    assert "choco install" not in SCRIPT
    assert "winget install" not in SCRIPT
    assert "does not install it" in SCRIPT or "does not install" in SCRIPT


def test_no_uk_postcode_in_script_or_checklist():
    assert not UK_POSTCODE_RE.search(SCRIPT)
    assert not UK_POSTCODE_RE.search(HELPERS)
    assert not UK_POSTCODE_RE.search(BUILD_RELEASE_MD)


def test_no_employer_names_other_than_the_required_obsidian_guard():
    """Like ci.yml's own publisher-check step, this script legitimately needs
    an "Obsidian Dynamics" string to guard against it appearing in a built
    exe's version info -- that is the one allowed exception."""
    before = HELPERS.split("Obsidian Dynamics found in", 1)[0]
    assert "throw" not in before[-5:]
    assert "match 'Obsidian'" in HELPERS


def test_provenance_record_has_a_self_check_for_pii():
    assert "USERNAME" in HELPERS and "COMPUTERNAME" in HELPERS
    assert "USERPROFILE" in HELPERS and "HOME" in HELPERS
    assert "UK postcode" in HELPERS
    assert "Get-ProvenanceUnsafeMarkers" in HELPERS
    assert "Get-ProvenanceUnsafeMarkers" in SCRIPT
    assert "Refusing to write it" in SCRIPT


def test_p10_provenance_self_check_runs_before_writing_the_file():
    # P10: the specific mutant to kill -- the self-check call-site removed
    # (or moved after the write, which would be just as useless).
    check_pos = SCRIPT.index("Get-ProvenanceUnsafeMarkers -Text $provenanceText")
    write_pos = SCRIPT.index("Set-Content -Path $provenancePath -Value $provenanceText")
    assert check_pos < write_pos


def test_p14_ship_set_check_runs_against_the_extracted_zip():
    # P14: the specific mutant to kill -- the extracted-zip ship_set --check
    # call-site removed (the one that validates OrbitRxMonitor/ once more
    # after unzipping, not the earlier onedir --check in section g).
    assert "'tools\\ship_set.py', '--check', (Join-Path $extractDir 'OrbitRxMonitor')" in SCRIPT
    assert "L6: ship_set --check failed on the extracted zip" in SCRIPT


def test_p15_determinism_self_check_compares_the_two_pack_hashes():
    # P15: the specific mutant to kill -- the two-hash comparison (or its
    # throw) removed, letting two differently-hashed repacks pass silently.
    assert "if ($zipSha256 -ne $zipSha256Repeat) {" in SCRIPT
    assert "DETERMINISM SELF-CHECK FAILED" in SCRIPT


def test_p19_qopensslbackend_is_refused_in_the_ship_set():
    # P19: the specific mutant to kill -- this refusal removed, letting the
    # legacy OpenSSL backend plugin slip into the ship set unnoticed.
    assert "-Filter qopensslbackend.dll" in SCRIPT
    assert "qopensslbackend.dll reached the ship set." in SCRIPT


def test_p20_shipped_notices_hash_is_compared_to_the_manifest():
    # P20: the specific mutant to kill -- the sha256 compare against the
    # manifest's recorded text removed, so a tampered/stale notices file
    # would go unnoticed.
    assert "$shippedHash = Get-Sha256Hex $shipped" in SCRIPT
    assert "if ($shippedHash -ne $Texts.$rel) {" in SCRIPT


def test_provenance_paths_are_relative_not_absolute():
    assert 'out\\$zipName' in SCRIPT or "out\\\"$zipName" in SCRIPT or '"out\\$' in SCRIPT
    assert "C:\\Users" not in SCRIPT
    assert "C:\\Users" not in HELPERS


def test_reuses_the_deterministic_packer_and_ship_set_tools():
    assert "tools\\pack_setup_zip.py" in SCRIPT
    assert "--expect-inventory" in SCRIPT
    assert "--verify" in SCRIPT
    assert "--compare-tree" in SCRIPT
    assert "tools\\ship_set.py" in SCRIPT
    assert "tools\\check_onedir_layout.py" in SCRIPT
    assert "tools\\pe_check.py" in SCRIPT
    assert "tools\\stamp_commit.py" in SCRIPT


def test_n6_runs_the_static_pyz_scan_locally():
    assert "tools\\scan_pyz.py" in SCRIPT
    assert "pyz-scan.txt" in SCRIPT
    assert "PYZ-SCAN: PASS" in SCRIPT


def test_l6_compares_the_extracted_tree_against_both_inventories():
    assert "'  L6-INVENTORY-MATCH: PASS'" in SCRIPT
    assert "--compare-tree" in SCRIPT and "--inventory" in SCRIPT
    assert "$CiInventory" in SCRIPT.split("--compare-tree", 1)[1]


def test_p13b_l6_ci_compare_call_uses_ci_inventory_not_local():
    # P13b: the specific mutant to kill -- the L6 call whose own
    # -FailureMessage says it checked against -CiInventory is pointed at
    # $localInventoryPath instead. Pair up each --compare-tree call's
    # --inventory argument with its own -FailureMessage text and check
    # them against each other, rather than just checking that each
    # variable name appears *somewhere* in the script (which a mutant
    # swapping the two calls' --inventory arguments would still pass).
    calls = re.findall(
        r"--compare-tree', \$extractedOnedir, '--inventory', (\$\w+)\) "
        r"-FailureMessage '([^']+)'",
        SCRIPT,
    )
    assert len(calls) == 2, f"expected exactly 2 L6 --compare-tree calls, found {len(calls)}"
    by_message = {message: inventory_var for inventory_var, message in calls}
    ci_message = next(m for m in by_message if "-CiInventory" in m)
    local_message = next(m for m in by_message if "local ship-set-inventory" in m)
    assert by_message[ci_message] == "$CiInventory"
    assert by_message[local_message] == "$localInventoryPath"


# --- NEW-2: a later L6/determinism failure must not leave the final zip --


def test_a_later_l6_or_determinism_failure_deletes_the_final_zip():
    section = SCRIPT.split("# --- i. Pack with the deterministic", 1)[1].split("# --- j.", 1)[0]
    assert "$zipPath = $null" in section
    catch_part = section.split("catch {", 1)[1].split("finally {", 1)[0]
    assert "Test-Path $zipPath" in catch_part
    assert "Remove-Item -Force $zipPath" in catch_part
    assert re.search(r"^\s*throw\s*$", catch_part, re.MULTILINE), "catch must re-throw, not swallow the error"


# --- L-4c/L-5 (item 5): a failure in the provenance write or its unsafe-
# marker self-check must still leave nothing at the public zip name. -------


def test_zip_is_built_pending_and_renamed_only_after_provenance_self_check():
    rename_pos = SCRIPT.index("Rename-Item -LiteralPath $zipPath -NewName $zipName")
    selfcheck_pos = SCRIPT.index("Get-ProvenanceUnsafeMarkers -Text $provenanceText")
    write_pos = SCRIPT.index("Set-Content -Path $provenancePath -Value $provenanceText")
    finalized_pos = SCRIPT.index("$zipFinalized = $true")
    assert selfcheck_pos < write_pos < rename_pos < finalized_pos
    assert '$zipPath = Join-Path $outDir "$zipName.pending"' in SCRIPT


def test_top_level_catch_removes_a_still_pending_zip_and_extracted_dir():
    catch_block = SCRIPT.rsplit("catch {", 1)[1]
    assert "-not $zipFinalized" in catch_block
    assert "Remove-Item -Force $zipPath" in catch_block
    assert "Remove-Item -Recurse -Force $extractDir" in catch_block
    # These must be declared before any throw-able step can run, so the
    # catch can always reference them under Set-StrictMode.
    declare_pos = SCRIPT.index("$zipFinalized = $false")
    first_risky_pos = SCRIPT.index("Assert-PersonalKitAttested -Attested:")
    assert declare_pos < first_risky_pos


def test_la_zippath_declared_above_the_top_level_try_not_just_near_its_top():
    # L-A: before this fix, $zipPath/$extractDir/$zipFinalized were declared
    # inside the top-level try but AFTER the helpers dot-source, so a
    # missing or unparsable helpers file made the catch crash on an unset
    # $zipPath under Set-StrictMode instead of printing a BUILD FAILED
    # line. They must be declared above `try {` entirely.
    try_pos = SCRIPT.index("\ntry {")
    declare_pos = SCRIPT.index("$zipPath = $null")
    dot_source_pos = SCRIPT.index(". (Join-Path $PSScriptRoot 'build_release_local.helpers.ps1')")
    assert declare_pos < try_pos < dot_source_pos
    assert SCRIPT.index("$extractDir = $null") < try_pos
    assert SCRIPT.index("$zipFinalized = $false") < try_pos


def test_inno_setup_version_is_read_from_file_version_info():
    assert "(Get-Item $Iscc).VersionInfo" in SCRIPT
    assert "ProductVersion" in SCRIPT


def test_restores_the_only_tracked_file_the_build_stamps():
    assert "orbitrx/_build_meta.py" in SCRIPT
    assert "git checkout -- orbitrx/_build_meta.py" in SCRIPT


def test_build_root_defaults_outside_the_clone():
    assert "C:\\build\\orbitrx-5.2.0-work" in SCRIPT
    assert "-BuildRoot" in SCRIPT


def test_l9_sums_reminder_does_not_overwrite_the_existing_line():
    assert "do NOT touch the existing 5.1.0 line" in SCRIPT or "do not touch the existing 5.1.0" in SCRIPT.lower()


def test_i3_sums_line_label_is_not_phrased_as_an_instruction():
    # I-3: "REMINDER (L9): append exactly this one line..." read like
    # something to do on every run, including a dry run, where doing so
    # would be wrong. It must be gone, replaced by a label.
    assert "REMINDER (L9)" not in SCRIPT
    assert "SUMS line for a QA/Risk-cleared build only (see marker):" in SCRIPT


def test_ci_parse_checks_build_release_local_ps1_and_helpers():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = ci.split("name: Parse-check tools/build_release_local.ps1", 1)
    assert len(step) == 2, "ci.yml has no parse-check step for the local build script"
    body = step[1].split("\n      - name:")[0]
    assert "[System.Management.Automation.Language.Parser]::ParseFile" in body
    assert "build_release_local.helpers.ps1" in body, "parse-check must also cover the helpers file"
    assert "PSScriptAnalyzer" in body
    assert "runner.os == 'Windows'" in step[0].splitlines()[-1] or "runner.os == 'Windows'" in body


def test_local_build_pins_are_consistent_with_the_distribution_manifest():
    pins = json.loads((ROOT / "packaging" / "local_build_pins.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "packaging" / "distribution_manifest.json").read_text(encoding="utf-8"))
    assert pins["python"]["version"] == "3.12.10"
    assert pins["python"]["version"] == manifest["ship_set"]["openssl"]["python"]
    assert re.fullmatch(r"[0-9a-f]{64}", pins["python"]["installer_sha256"])
    assert re.fullmatch(r"[0-9a-f]{32}", pins["python"]["installer_md5"])


def test_local_build_pins_file_has_no_employer_strings_or_postcode():
    pins_text = (ROOT / "packaging" / "local_build_pins.json").read_text(encoding="utf-8")
    assert "Obsidian Dynamics" not in pins_text
    assert not UK_POSTCODE_RE.search(pins_text)


# --- R1: -CiInventory is mandatory and its header is checked before building -


def test_ci_inventory_is_mandatory_not_optional():
    assert "[string]$CiInventory" in SCRIPT
    # The old "skip L5 with a warning" path must be gone.
    assert "is NOT yet satisfied" not in SCRIPT
    assert "-CiInventory is required" in SCRIPT


def test_ci_inventory_header_is_parsed_and_checked_before_building():
    assert "Get-ShipSetInventoryHeader" in HELPERS
    assert "Assert-CiInventoryMatchesBuild" in HELPERS
    assert "version=(?<version>" in HELPERS
    assert "commit=(?<commit>" in HELPERS
    # Must run before the dependency install / build steps (d, e, f).
    header_check_pos = SCRIPT.index("Get-ShipSetInventoryHeader -Path $CiInventory")
    assert header_check_pos < SCRIPT.index("# --- d.")
    assert header_check_pos < SCRIPT.index("# --- e.")
    assert header_check_pos < SCRIPT.index("# --- f.")


def test_ci_inventory_sha256_and_commit_recorded_in_provenance():
    assert "ciInventorySha256" in SCRIPT
    assert "CI ship-set-inventory.txt (-CiInventory) sha256" in SCRIPT


def test_l5_and_l6_compares_still_run_unconditionally():
    assert "L5-INVENTORY-MATCH: PASS" in SCRIPT
    # No "if ($CiInventory)" branches guarding L5/L6 any more -- it is
    # always given.
    assert "if ($CiInventory)" not in SCRIPT


# --- R2: dependencies install only from the committed, hash-pinned lock -----


def test_installs_only_from_the_committed_hash_pinned_lock():
    assert "[string]$Constraints" not in SCRIPT
    assert "requirements-windows-build.lock.txt" in SCRIPT
    assert "'--require-hashes', '--no-deps'" in SCRIPT
    assert "'-m', 'pip', 'check'" in SCRIPT
    assert "'-m', 'pip', 'install', '-r', $requirementsPath" not in SCRIPT


def test_lock_sha256_recorded_in_provenance():
    assert "lockSha256" in SCRIPT
    assert "requirements-windows-build.lock.txt sha256" in SCRIPT


def test_ci_build_windows_job_installs_from_the_same_lock_path():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build_job = ci.split("build-windows:", 1)[1]
    assert "packaging\\requirements-windows-build.lock.txt" in build_job
    assert "--require-hashes" in build_job
    assert "--no-deps" in build_job
    assert "pip check" in build_job
    assert "pip freeze" in build_job
    # The test job must still use plain requirements.txt (unpinned deps are
    # fine for running the test suite; only the Windows *build* needs the
    # fully-pinned, --no-deps lock).
    test_job = ci.split("build-windows:", 1)[0]
    assert "pip install -r requirements.txt" in test_job


def test_lock_file_is_consistent_with_requirements_txt():
    lock_path = ROOT / "packaging" / "requirements-windows-build.lock.txt"
    assert lock_path.is_file()
    lock_text = lock_path.read_text(encoding="utf-8")

    def normalize(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    lock_names = {
        normalize(m.group(1))
        for m in re.finditer(r"(?m)^([A-Za-z0-9_.-]+)==", lock_text)
    }
    requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    req_names = []
    for line in requirements_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=;\[\s]", line, maxsplit=1)[0]
        if name:
            req_names.append(name)

    for name in req_names:
        assert normalize(name) in lock_names, f"{name} (from requirements.txt) missing from the lock file"

    assert "pyside6-essentials==6.12.0" in lock_text.lower()

    # Every pin must be exact (==) and every package must carry at least
    # one --hash=sha256 entry.
    pin_lines = [
        line for line in lock_text.splitlines()
        if re.match(r"^[A-Za-z0-9_.-]+==", line)
    ]
    assert pin_lines, "lock file has no top-level pins"
    for line in pin_lines:
        assert "==" in line

    for block in re.split(r"(?m)^(?=[A-Za-z0-9_.-]+==)", lock_text)[1:]:
        assert "--hash=sha256:" in block, block.splitlines()[0]


# --- L-2: the local TESTS gate excludes network-marked tests; CI does not -


def test_network_marker_is_registered_in_pyproject():
    import tomllib

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    markers = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    assert any(m.startswith("network:") for m in markers), "no 'network' marker registered in pyproject.toml"


def test_local_tests_gate_excludes_network_marked_tests():
    assert "'-m', 'not network'" in SCRIPT


def test_ci_test_job_does_not_deselect_network_tests():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    test_job = ci.split("build-windows:", 1)[0]
    pytest_lines = [line for line in test_job.splitlines() if re.search(r"\bpytest\b", line)]
    assert pytest_lines, "no pytest invocation found in the test job"
    for line in pytest_lines:
        assert "not network" not in line, (
            "CI's test job must run the full suite, including network-marked tests, "
            f"unlike the local TESTS gate: {line}"
        )
        assert not re.search(r"-m\s+['\"]?not\b", line)


def test_live_noaa_test_is_marked_network():
    noaa_text = (ROOT / "tests" / "test_weather_fixtures.py").read_text(encoding="utf-8")
    marked = noaa_text.split("def test_live_noaa_populates_core_fields", 1)[0].splitlines()[-1]
    assert "pytest.mark.network" in marked


def test_lock_file_header_has_no_absolute_tmp_paths():
    lock_text = (ROOT / "packaging" / "requirements-windows-build.lock.txt").read_text(encoding="utf-8")
    header = "\n".join(lock_text.splitlines()[:3])
    assert "/tmp" not in header
    assert "packaging/requirements-windows-build.lock.txt" in header


def test_pins_constraint_file_matches_the_lock_top_level_versions():
    pins_text = (ROOT / "packaging" / "requirements-windows-build.pins.txt").read_text(encoding="utf-8")
    lock_text = (ROOT / "packaging" / "requirements-windows-build.lock.txt").read_text(encoding="utf-8").lower()
    for line in pins_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, version = line.partition("==")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        assert f"{normalized}=={version.lower()}" in lock_text, line


# --- N11: the zip/provenance file names are derived from VERSION -----------


def test_zip_and_provenance_names_are_derived_from_version_not_hardcoded():
    assert '"OrbitRx-Setup-$version.zip"' in SCRIPT
    assert '"OrbitRx-$version-PROVENANCE.txt"' in SCRIPT
    assert '"OrbitRx-Setup-5.2.0.zip"' not in SCRIPT
    assert '"OrbitRx-5.2.0-PROVENANCE.txt"' not in SCRIPT


# --- R4: the dry-run framing is explicit --------------------------------------


def test_dry_run_reminder_is_printed():
    assert "DRY RUN" in SCRIPT


# --- NEW-1: a top-level try/catch reports a terminating failure through the
# success stream (so Tee-Object sees it) and exits 1; the success path still
# exits 0. -----------------------------------------------------------------


def test_requires_statement_gates_powershell_7_4():
    # L-1/I-1: #Requires stops a below-7.4 host (including one that would
    # otherwise ignore the inline check below) before any of this script's
    # own code runs at all. Must appear before the param block. The floor
    # is 7.4, matching CI's own pwsh version -- not just major version 7.
    assert "#Requires -Version 7.4" in SCRIPT
    assert "#Requires -Version 7.0" not in SCRIPT
    assert SCRIPT.index("#Requires -Version 7.4") < SCRIPT.index("[CmdletBinding()]")


def test_inline_version_check_runs_before_strict_mode_and_dot_source():
    # L-1/I-1: fail closed even if a host somehow ignores #Requires, or the
    # dot-sourced helpers file below fails to load -- this plain check (no
    # dependency on the helpers file, so it survives a broken/missing one)
    # must run before Set-StrictMode and before the dot-source. It compares
    # the full version against 7.4, not just the Major component, so 7.0-7.3
    # refuse here too.
    needle = "$PSVersionTable.PSVersion -lt [version]'7.4'"
    gate_section = SCRIPT.split(needle, 1)[1].split("Set-StrictMode", 1)[0]
    assert "PowerShell 7.4 or later is required" in gate_section
    assert "BUILD FAILED" in gate_section
    assert "exit 1" in gate_section
    dot_source_line = ". (Join-Path $PSScriptRoot 'build_release_local.helpers.ps1')"
    assert SCRIPT.index(needle) < SCRIPT.index("Set-StrictMode -Version Latest")
    assert SCRIPT.index(needle) < SCRIPT.index(dot_source_line)
    assert "PSVersionTable.PSVersion.Major -lt 7" not in SCRIPT


def test_helpers_dot_source_is_guarded_and_inside_the_top_level_try():
    # L-1: a load failure (missing or unparsable helpers file) must be a
    # terminating error the top-level try/catch reports as a BUILD FAILED
    # line naming the file -- not an uncaught error that bypasses
    # Tee-Object -- so the dot-source itself must be inside the try,
    # preceded by a Test-Path check that names the file in its message.
    try_pos = SCRIPT.index("\ntry {")
    dot_source_pos = SCRIPT.index(". (Join-Path $PSScriptRoot 'build_release_local.helpers.ps1')")
    assert try_pos < dot_source_pos
    section = SCRIPT[try_pos:dot_source_pos]
    assert "Test-Path -LiteralPath $helpersPath" in section
    assert "Helpers file not found: $helpersPath" in section
    assert "throw" in section


def test_powershell_7_helper_check_still_used_inside_try():
    # NEW-5 (kept as a backstop, per L-1/I-1): Test-PowerShellVersionSupported
    # is still called from the main script, now after Set-StrictMode
    # (inside the top-level try, right after the dot-source), unlike the
    # plain inline check above which runs before it. I-1: it is passed the
    # full $PSVersionTable.PSVersion object, not just .Major, so it can
    # enforce the 7.4 floor too.
    assert "Test-PowerShellVersionSupported" in HELPERS
    assert "Test-PowerShellVersionSupported" in SCRIPT
    assert "Test-PowerShellVersionSupported -MajorVersion" not in SCRIPT
    gate_section = SCRIPT.split("Test-PowerShellVersionSupported -Version $PSVersionTable.PSVersion", 1)[1][:400]
    assert "PowerShell 7.4 or later is required" in gate_section
    assert SCRIPT.index("Test-PowerShellVersionSupported -Version $PSVersionTable.PSVersion") > SCRIPT.index("Set-StrictMode -Version Latest")


def test_script_body_is_wrapped_in_a_top_level_try_catch_with_explicit_exits():
    assert re.search(r"^try \{", SCRIPT, re.MULTILINE)
    assert re.search(r"^\}\ncatch \{", SCRIPT, re.MULTILINE)
    catch_block = SCRIPT.rsplit("catch {", 1)[1]
    assert "BUILD FAILED" in catch_block
    assert "Write-Output" in catch_block
    assert "exit 1" in catch_block
    # The success path (after the catch block) must still exit 0 explicitly,
    # not rely on whatever $LASTEXITCODE a native command last set.
    after_catch = catch_block.split("exit 1", 1)[1]
    assert "exit 0" in after_catch


def test_build_release_md_states_dry_run_up_front_and_in_steps():
    top = BUILD_RELEASE_MD.split("\n\n", 4)
    assert any("dry run" in block.lower() for block in top[:3])
    assert "L10" in BUILD_RELEASE_MD


# --- R3: BUILD-RELEASE.md content checks --------------------------------------


def test_build_release_md_documents_inno_setup_per_user_path():
    assert "LOCALAPPDATA" in BUILD_RELEASE_MD
    assert "-Iscc" in BUILD_RELEASE_MD


def test_build_release_md_documents_execution_policy():
    assert "Set-ExecutionPolicy" in BUILD_RELEASE_MD
    assert "-Scope Process" in BUILD_RELEASE_MD


def test_build_release_md_requires_pwsh_not_windows_powershell():
    assert "PowerShell 7" in BUILD_RELEASE_MD
    assert "pwsh -ExecutionPolicy Bypass -File" in BUILD_RELEASE_MD
    assert "powershell -ExecutionPolicy Bypass -File" not in BUILD_RELEASE_MD


def test_build_release_md_does_not_claim_nothing_half_built():
    assert "nothing is packed or left half-built" not in BUILD_RELEASE_MD
    assert "nothing half-built" not in BUILD_RELEASE_MD
    assert "_build_meta.py" in BUILD_RELEASE_MD
    assert "git clean -xdf" in BUILD_RELEASE_MD


def test_build_release_md_explains_l5_mandatory_artifact_retrieval():
    assert "release-exe-captures" in BUILD_RELEASE_MD
    assert "signed in" in BUILD_RELEASE_MD.lower() or "signed-in" in BUILD_RELEASE_MD.lower()
    assert "30 days" in BUILD_RELEASE_MD
    assert "mandatory" in BUILD_RELEASE_MD.lower()


def test_build_release_md_uses_a_placeholder_sha_not_a_real_commit():
    assert "<CLEARED_SHA>" in BUILD_RELEASE_MD
    assert "Chief of Staff" in BUILD_RELEASE_MD or "Risk clearance" in BUILD_RELEASE_MD
    # No real 40-hex commit SHA should be presented as "the" SHA to build.
    for sha in re.findall(r"\b[0-9a-f]{40}\b", BUILD_RELEASE_MD):
        assert False, f"BUILD-RELEASE.md names a concrete commit SHA ({sha}); use <CLEARED_SHA> instead"


def test_build_release_md_documents_tee_object_console_capture():
    assert "Tee-Object" in BUILD_RELEASE_MD
    assert "Start-Transcript" in BUILD_RELEASE_MD  # named as the thing NOT to use
    assert "build-console.txt" in BUILD_RELEASE_MD


# --- NEW-4: build-console.txt/out\ PII caveat, I-4/I-5/I-6 doc fixes --------


def test_build_release_md_warns_build_console_may_contain_username():
    assert "used to be able to end" in BUILD_RELEASE_MD
    assert "your Windows username" in BUILD_RELEASE_MD
    assert "QA and Risk" in BUILD_RELEASE_MD
    assert "never published" in BUILD_RELEASE_MD.lower() or "never publish" in BUILD_RELEASE_MD.lower()
    assert "C:\\build\\..." in BUILD_RELEASE_MD or "C:\\build\\" in BUILD_RELEASE_MD
    assert "prefer that over Downloads" in BUILD_RELEASE_MD_FLAT


def test_build_release_md_documents_the_auto_redaction_and_the_b4_manual_scan():
    # R-c (Risk round): the script now auto-redacts $env:USERNAME/
    # USERPROFILE/COMPUTERNAME from console output and out\ files, but that
    # is pattern-matching on those specific values, not a human review --
    # BUILD-RELEASE.md must still call out the manual B4 redaction scan.
    assert "auto-redacts" in BUILD_RELEASE_MD_FLAT
    assert "<user>" in BUILD_RELEASE_MD and "<profile>" in BUILD_RELEASE_MD and "<host>" in BUILD_RELEASE_MD
    assert "B4" in BUILD_RELEASE_MD
    assert "redaction scan" in BUILD_RELEASE_MD_FLAT
    assert "is not a human review" in BUILD_RELEASE_MD_FLAT or "not a human review" in BUILD_RELEASE_MD_FLAT


def test_build_release_md_i4_recommends_append_or_per_attempt_filenames():
    assert "-Append" in BUILD_RELEASE_MD
    assert "attempt2" in BUILD_RELEASE_MD or "per-attempt" in BUILD_RELEASE_MD.lower()


def test_build_release_md_i5_send_back_list_reference_is_correct():
    # The intro's forward-reference must point at the step that actually
    # contains the "Send to QA/Risk (L10):" bullet list, not a step number
    # that doesn't.
    intro = re.sub(r"\s+", " ", BUILD_RELEASE_MD.split("## Prerequisites", 1)[0])
    match = re.search(r"step (\d+)'s send-back list", intro)
    assert match, "intro paragraph does not reference a step's send-back list"
    referenced_step = match.group(1)
    steps_section = BUILD_RELEASE_MD.split("## Steps", 1)[1]
    step_text = steps_section.split(f"\n{referenced_step}. ", 1)
    assert len(step_text) == 2, f"no step {referenced_step} found in the Steps section"
    assert "Send to QA/Risk (L10):" in step_text[1].split("\n1", 1)[0] or "Send to QA/Risk (L10):" in step_text[1][:2000]


def test_build_release_md_i6_chief_of_staff_supplies_the_dry_run_sha_too():
    assert "dry-run SHA too" in BUILD_RELEASE_MD or "dry run SHA too" in BUILD_RELEASE_MD
    assert "Chief of Staff" in BUILD_RELEASE_MD
    sha_section = BUILD_RELEASE_MD.split("**Which SHA?**", 1)[1]
    assert "Chief of Staff" in sha_section
    assert "CI run" in sha_section


def test_build_release_md_lists_everything_to_send_back():
    for needle in (
        "PROVENANCE",
        "build-console.txt",
        "ship-set-inventory.txt",
        "installer-publisher.txt",
        "ship-set-qt.txt",
        "ship-set-tls.txt",
        "pyz-scan",
        "L7",
        "antivirus",
    ):
        assert needle in BUILD_RELEASE_MD


# --- item 7 (QA round 3, L-7 doc fixes): step 13 example, -PythonInstaller
# wording, PowerShell 7.4+ prerequisite, step 14 no-BUILD-FAILED note, the
# local TESTS gate skipping the network-marked live NOAA test. -------------


def test_build_release_md_step13_example_uses_build_inputs_not_downloads():
    step13 = BUILD_RELEASE_MD.split("\n13. ", 1)[1].split("\n14. ", 1)[0]
    assert r"C:\build\inputs\python-3.12.10-amd64.exe" in step13
    assert r"C:\build\inputs\ship-set-inventory.txt" in step13
    assert r"C:\Downloads\python-3.12.10-amd64.exe" not in step13
    assert r"C:\Downloads\ship-set-inventory.txt" not in step13
    assert "put" in step13.lower() and r"C:\build\inputs" in step13


def test_build_release_md_explains_pythoninstaller_has_no_default():
    step13 = BUILD_RELEASE_MD.split("\n13. ", 1)[1].split("\n14. ", 1)[0]
    assert "`-PythonInstaller` has no default" in step13
    assert "must always be passed explicitly" in step13


def test_build_release_md_prerequisite_pins_powershell_7_4_and_winget():
    prereqs = BUILD_RELEASE_MD.split("## Prerequisites", 1)[1].split("## Steps", 1)[0]
    assert "PowerShell 7.4" in prereqs
    assert "winget install --id Microsoft.PowerShell" in prereqs
    assert "pwsh -v" in prereqs


def test_build_release_md_step14_explains_a_missing_build_failed_line():
    step14_flat = re.sub(r"\s+", " ", BUILD_RELEASE_MD.split("\n14. ", 1)[1].split("\n15. ", 1)[0])
    assert "no `BUILD FAILED` line" in step14_flat or "no BUILD FAILED line" in step14_flat
    assert "command line itself was wrong" in step14_flat
    assert "mistyped" in step14_flat


def test_build_release_md_mentions_the_local_tests_gate_skips_the_live_noaa_test():
    step14_flat = re.sub(r"\s+", " ", BUILD_RELEASE_MD.split("\n14. ", 1)[1].split("\n15. ", 1)[0])
    assert "network-marked" in step14_flat
    assert "NOAA" in step14_flat
    assert "CI" in step14_flat
    # R-d (Risk round): this is a deliberate departure from "run CI's exact
    # suite" -- it must be surfaced for Risk to review, not buried.
    assert "Risk asked to review" in step14_flat


# --- Next fix round (risk-r3.md / qa-9a817f1.md): M-1, L-A, I-1, I-3, C6. ----


def test_c6_pip_and_pyinstaller_caches_point_under_buildroot():
    assert "$env:PIP_CACHE_DIR = $pipCacheDir" in SCRIPT
    assert "$env:PYINSTALLER_CONFIG_DIR = $pyinstallerConfigDir" in SCRIPT
    assert "Join-Path $BuildRoot 'cache\\pip'" in SCRIPT
    assert "Join-Path $BuildRoot 'cache\\pyinstaller'" in SCRIPT
    # Must run before the venv (and so before pip/PyInstaller are ever
    # invoked), and must not touch $env:TEMP/$env:TMP (see the region's own
    # comment for why: Format-RedactedText reads those fresh on every call).
    assert SCRIPT.index("$env:PIP_CACHE_DIR = $pipCacheDir") < SCRIPT.index("$venvDir = Join-Path $BuildRoot 'venv'")
    assert "$env:TEMP =" not in SCRIPT
    assert "$env:TMP =" not in SCRIPT
    assert "pip=$pipCacheDir pyinstaller=$pyinstallerConfigDir" in SCRIPT


def test_c6_provenance_records_the_cache_locations_under_buildroot():
    assert "Tool caches (C6):" in SCRIPT
    assert "pip=$pipCacheDir pyinstaller=$pyinstallerConfigDir" in SCRIPT
    provenance_section = SCRIPT.split("$provenanceLines = @(", 1)[1].split("$provenanceText =", 1)[0]
    assert "Tool caches (C6)" in provenance_section


def test_build_release_md_documents_the_new_empty_buildroot_requirement():
    # M-1: deleting -BuildRoot before every attempt is now mandatory, not
    # just a failure-recovery preference, because the script itself refuses
    # on a non-empty out\.
    assert "new, empty `-BuildRoot`" in BUILD_RELEASE_MD or "new, empty -BuildRoot" in BUILD_RELEASE_MD_FLAT
    step14 = BUILD_RELEASE_MD.split("\n14. ", 1)[1].split("\n15. ", 1)[0]
    assert "not optional" in step14
    assert "M-1" in step14 or "M-1" in BUILD_RELEASE_MD


def test_build_release_md_documents_tool_caches_under_buildroot():
    assert "PIP_CACHE_DIR" in BUILD_RELEASE_MD
    assert "PYINSTALLER_CONFIG_DIR" in BUILD_RELEASE_MD


# --- Risk R3 Ruling 1, condition B3-c (risk-r3.md section 3/5; qa-9a817f1.md
# L-E/M6/M7): the TESTS gate's exact pytest arguments, the network-scope
# check, the pytest-summary self-check, -CiRunId, and the provenance line. --


def test_ci_run_id_parameter_is_required_and_digits_only():
    assert "[ValidatePattern('^[0-9]+$')]" in SCRIPT
    param_block = SCRIPT.split("param(", 1)[1].split(")\n\n", 1)[0]
    assert "[string]$CiRunId" in param_block
    assert "-CiRunId is required" in SCRIPT
    # Like -PythonInstaller, no default value -- the script's own check
    # (not just the pattern) is what refuses an omitted value.
    assert "[string]$CiRunId = " not in SCRIPT


def test_ci_run_id_check_runs_after_ci_inventory_checks_but_before_build_work():
    ci_inventory_check_pos = SCRIPT.index("-CiInventory file not found")
    ci_run_id_check_pos = SCRIPT.index("-CiRunId is required")
    n4_guards_pos = SCRIPT.index("# --- N4:")
    assert ci_inventory_check_pos < ci_run_id_check_pos < n4_guards_pos


def test_tests_gate_region_exists_and_is_well_formed():
    assert "# region tests-gate" in SCRIPT
    assert "# endregion tests-gate" in SCRIPT
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    assert "Push-Location $repoRoot" in region
    assert "Pop-Location" in region


def test_tests_gate_uses_the_exact_reviewed_pytest_arguments():
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    # B3-c: --collect-only scope check, with --strict-markers.
    assert "'-m', 'pytest', '--collect-only', '-q', '-m', 'network', '--strict-markers'" in region
    # B3-c: the gate itself, with --strict-markers added (it was missing
    # before this fix) -- this is also the exact substring
    # test_local_tests_gate_excludes_network_marked_tests (below) depends on.
    assert "'-m', 'pytest', '-q', '-m', 'not network', '--strict-markers'" in region


def test_tests_gate_checks_the_network_scope_before_running_the_gate():
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    assert region.index("Assert-ExactlyOneNetworkTestCollected") < region.index("$pytestArgs = @(")


def test_tests_gate_wraps_the_collected_ids_call_to_avoid_the_empty_array_to_null_bug():
    # The exact mutant class this guards: PowerShell collapses a function's
    # empty-array return to $null across the call boundary, which would
    # turn "zero network tests collected" into "one blank id collected"
    # inside Assert-ExactlyOneNetworkTestCollected instead of refusing with
    # a clear message (see Invoke-PublisherCheck's own "@(...)" comment for
    # the same class of bug elsewhere in this script).
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    assert "@(Get-PytestCollectedTestIds -Lines $networkCollectLines)" in region


def test_tests_gate_refuses_on_a_nonzero_pytest_exit_code_and_on_a_dirty_summary():
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    assert "if ($pytestExitCode -ne 0)" in region
    assert "Assert-PytestGateSummaryClean -Counts $pytestCounts" in region


def test_tests_gate_pytest_parsing_helpers_are_defined_in_helpers():
    for fn in (
        "function Get-PytestCollectedTestIds",
        "function Assert-ExactlyOneNetworkTestCollected",
        "function Get-PytestSummaryCounts",
        "function Assert-PytestGateSummaryClean",
    ):
        assert fn in HELPERS, fn


def test_tests_gate_provenance_line_matches_risk_r3_b3c_format_exactly():
    region = SCRIPT.split("# region tests-gate", 1)[1].split("# endregion tests-gate", 1)[0]
    expected = (
        '"pytest -q -m `"not network`" --strict-markers; '
        "$($pytestCounts.Passed) passed, $($pytestCounts.Skipped) skipped, "
        "1 deselected: tests/test_weather_fixtures.py::test_live_noaa_populates_core_fields; "
        'CI $CiRunId at this SHA ran it: PASSED ubuntu+windows"'
    )
    assert expected in region
    assert '$testsGateSummary = ' in region
    assert 'Write-Host "TESTS: PASS ($testsGateSummary)"' in SCRIPT


def test_provenance_gate_results_cites_the_tests_gate_summary_not_a_bare_pass():
    provenance_section = SCRIPT.split("$provenanceLines = @(", 1)[1].split("$provenanceText =", 1)[0]
    assert '"  TESTS: PASS ($testsGateSummary)"' in provenance_section
    assert "'  TESTS: PASS'," not in provenance_section


def test_build_release_md_documents_the_ci_run_id_parameter():
    assert "-CiRunId" in BUILD_RELEASE_MD
    step13 = BUILD_RELEASE_MD.split("\n13. ", 1)[1].split("\n14. ", 1)[0]
    assert "-CiRunId" in step13
    ci_run_id_section = BUILD_RELEASE_MD.split("-CiRunId", 1)[1][:400]
    assert "the CI run id that produced" in ci_run_id_section or "CI run id that produced" in BUILD_RELEASE_MD_FLAT
    assert "CoS" in BUILD_RELEASE_MD_FLAT or "Chief of Staff" in BUILD_RELEASE_MD_FLAT
    assert "with the SHA" in BUILD_RELEASE_MD_FLAT


def test_build_release_md_step14_and_17_state_the_pytest_summary_requirement():
    step14_flat = re.sub(r"\s+", " ", BUILD_RELEASE_MD.split("\n14. ", 1)[1].split("\n15. ", 1)[0])
    assert "0 failed" in step14_flat
    assert "exactly 1 deselected" in step14_flat
    step17 = BUILD_RELEASE_MD.split("\n17. ", 1)[1].split("\n18. ", 1)[0]
    step17_flat = re.sub(r"\s+", " ", step17)
    assert "0 failed" in step17_flat
    assert "exactly 1 deselected" in step17_flat


def test_build_release_md_step17_send_back_list_includes_l5_l6_result_files():
    step17 = BUILD_RELEASE_MD.split("\n17. ", 1)[1].split("\n18. ", 1)[0]
    send_back = step17.split("Send to QA/Risk (L10):", 1)[1]
    for needle in (
        "l5-pack-result.txt",
        "l6-verify.txt",
        "l6-compare-tree-local.txt",
        "l6-compare-tree-ci.txt",
    ):
        assert needle in send_back, needle
    assert "whichever exist" in send_back
    assert "C6" in BUILD_RELEASE_MD
