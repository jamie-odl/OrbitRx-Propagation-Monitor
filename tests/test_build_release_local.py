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


def test_checks_head_against_expected_sha():
    assert "$ExpectedSha" in SCRIPT
    assert "git rev-parse HEAD" in SCRIPT
    assert "40-hex" in COMBINED or "{40}" in COMBINED


def test_requires_a_clean_working_tree_before_building():
    assert "git status --porcelain --ignored" in SCRIPT


def test_reads_the_python_installer_pin_from_the_pins_file_not_hardcoded():
    assert "packaging\\local_build_pins.json" in SCRIPT
    assert "$pins.python.installer_sha256" in SCRIPT
    assert "$pins.python.installer_md5" in SCRIPT
    # The actual hash value must not be duplicated as a literal in the script.
    pins = json.loads((ROOT / "packaging" / "local_build_pins.json").read_text(encoding="utf-8"))
    assert pins["python"]["installer_sha256"] not in SCRIPT
    assert pins["python"]["installer_md5"] not in SCRIPT


def test_checks_authenticode_signatures_for_python():
    assert "Get-AuthenticodeSignature" in SCRIPT
    assert "authenticode_signer_subject_contains" in SCRIPT
    # The signer-subject check itself must read the pin, not a hardcoded literal.
    checks = SCRIPT.count("[regex]::Escape($pins.python.authenticode_signer_subject_contains)")
    assert checks >= 2, "expected both the installer and python.exe signer checks to read the pin"


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


def test_never_contacts_the_network_or_publishes():
    for needle in NETWORK_AND_PUBLISH_COMMANDS:
        assert needle not in SCRIPT, needle
        assert needle not in HELPERS, needle


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
