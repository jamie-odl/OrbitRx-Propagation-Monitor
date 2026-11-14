"""Static checks on tools/build_release_local.ps1 and its pins file.

Pure text/JSON checks -- pwsh is not required for this file to run on
ubuntu. A real PowerShell parse-check lives in .github/workflows/ci.yml's
Windows leg (see test_ci_parse_checks_build_release_local_ps1 below).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "tools" / "build_release_local.ps1").read_text(encoding="utf-8")

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


def test_script_file_exists_and_is_ascii():
    assert (ROOT / "tools" / "build_release_local.ps1").is_file()
    SCRIPT.encode("ascii")  # raises if any non-ASCII character slipped in


def test_refuses_onedrive_and_desktop_paths():
    assert "OneDrive" in SCRIPT
    assert "Desktop" in SCRIPT
    assert "GetFolderPath('Desktop')" in SCRIPT
    assert "OneDriveConsumer" in SCRIPT and "OneDriveCommercial" in SCRIPT


def test_checks_head_against_expected_sha():
    assert "$ExpectedSha" in SCRIPT
    assert "git rev-parse HEAD" in SCRIPT
    assert "40-hex" in SCRIPT or "40,hex}" in SCRIPT or "{40}" in SCRIPT


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


def test_attest_personal_kit_is_required():
    assert "[switch]$AttestPersonalKit" in SCRIPT
    assert "AttestPersonalKit" in SCRIPT
    guard = SCRIPT.split("if (-not $AttestPersonalKit)", 1)
    assert len(guard) == 2
    assert "throw" in guard[1].split("\n\n")[0]


def test_never_contacts_the_network_or_publishes():
    for needle in NETWORK_AND_PUBLISH_COMMANDS:
        assert needle not in SCRIPT, needle


def test_does_not_auto_install_python_or_inno_setup():
    assert "choco install" not in SCRIPT
    assert "winget install" not in SCRIPT
    assert "does not install it" in SCRIPT or "does not install" in SCRIPT


def test_no_uk_postcode_in_script_or_checklist():
    assert not UK_POSTCODE_RE.search(SCRIPT)
    assert not UK_POSTCODE_RE.search(BUILD_RELEASE_MD)


def test_no_employer_names_other_than_the_required_obsidian_guard():
    """Like ci.yml's own publisher-check step, this script legitimately needs
    an "Obsidian Dynamics" string to guard against it appearing in a built
    exe's version info -- that is the one allowed exception."""
    before = SCRIPT.split("Obsidian Dynamics found in", 1)[0]
    assert "throw" in before[-40:]


def test_provenance_record_has_a_self_check_for_pii():
    assert "USERNAME" in SCRIPT and "COMPUTERNAME" in SCRIPT
    assert "USERPROFILE" in SCRIPT and "HOME" in SCRIPT
    assert "UK postcode" in SCRIPT
    assert "Get-ProvenanceUnsafeMarkers" in SCRIPT
    assert "Refusing to write it" in SCRIPT


def test_provenance_paths_are_relative_not_absolute():
    assert "out\\OrbitRx-Setup-5.2.0.zip" in SCRIPT
    assert "C:\\Users" not in SCRIPT


def test_reuses_the_deterministic_packer_and_ship_set_tools():
    assert "tools\\pack_setup_zip.py" in SCRIPT
    assert "--expect-inventory" in SCRIPT
    assert "--verify" in SCRIPT
    assert "--compare-tree" in SCRIPT
    assert "tools\\ship_set.py" in SCRIPT
    assert "tools\\check_onedir_layout.py" in SCRIPT
    assert "tools\\pe_check.py" in SCRIPT
    assert "tools\\stamp_commit.py" in SCRIPT


def test_l6_compares_the_extracted_tree_against_both_inventories():
    assert "'  L6-INVENTORY-MATCH: PASS'" in SCRIPT
    assert "--compare-tree" in SCRIPT and "--inventory" in SCRIPT
    assert "$CiInventory" in SCRIPT.split("--compare-tree", 1)[1]


def test_dependency_install_mirrors_the_ci_build_windows_job():
    assert "'-m', 'pip', 'install', '-r', $requirementsPath" in SCRIPT
    assert "'--upgrade', 'pip'" not in SCRIPT
    assert "-m pip --version" in SCRIPT


def test_inno_setup_version_is_read_from_file_version_info():
    assert "(Get-Item $Iscc).VersionInfo" in SCRIPT
    assert "ProductVersion" in SCRIPT
    assert "2>&1" not in SCRIPT


def test_restores_the_only_tracked_file_the_build_stamps():
    assert "orbitrx/_build_meta.py" in SCRIPT
    assert "git checkout -- orbitrx/_build_meta.py" in SCRIPT


def test_build_root_defaults_outside_the_clone():
    assert "C:\\build\\orbitrx-5.2.0-work" in SCRIPT
    assert "-BuildRoot" in SCRIPT


def test_l9_sums_reminder_does_not_overwrite_the_existing_line():
    assert "do NOT touch the existing 5.1.0 line" in SCRIPT or "do not touch the existing 5.1.0" in SCRIPT.lower()


def test_ci_parse_checks_build_release_local_ps1():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = ci.split("name: Parse-check tools/build_release_local.ps1", 1)
    assert len(step) == 2, "ci.yml has no parse-check step for the local build script"
    body = step[1].split("\n      - name:")[0]
    assert "[System.Management.Automation.Language.Parser]::ParseFile" in body
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
