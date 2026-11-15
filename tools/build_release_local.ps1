<#
.SYNOPSIS
    Build the OrbitRx 5.2.0 local candidate on Jamie's own PC (never on
    employer equipment, VPN or a remote session -- see BUILD-RELEASE.md L1).

.DESCRIPTION
    Mirrors the .github/workflows/ci.yml "test" and "build-windows" jobs,
    step by step, against a clean checkout of a known commit, then packs a
    deterministic OrbitRx-Setup-<VERSION>.zip with tools/pack_setup_zip.py.

    This script never uploads, publishes, tags or pushes anything. The one
    network access it makes is pip downloading the wheels listed in the
    committed, fully hash-pinned packaging/requirements-windows-build.lock.txt
    from PyPI (--require-hashes enforces that every downloaded wheel matches
    the pinned hash, not a live index's current contents). The local TESTS
    gate (step e) runs the pytest suite with -m "not network", excluding
    the one test that makes a live network call (CI's test job still runs
    the full suite, including that test, at this SHA); nothing else in this
    script touches the network, except that Get-AuthenticodeSignature may
    let Windows itself fetch certificate revocation data in the background.
    It never auto-installs Python or Inno Setup -- if either is missing or
    fails a pin check, it stops with a clear message.

    -CiInventory is REQUIRED (L5): this script will not build without the
    exact SHA's ship-set-inventory.txt from CI. See BUILD-RELEASE.md.

    IMPORTANT: a run of this script is a DRY RUN unless Jamie has explicitly
    been told otherwise. Its zip is not a publish candidate by itself -- see
    BUILD-RELEASE.md's "Dry run" note and L10.

    Run from a fresh clone, as described in BUILD-RELEASE.md. PowerShell 7
    (pwsh) is required; it refuses to run on Windows PowerShell 5.1 with a
    clear message rather than failing partway through.

.PARAMETER ExpectedSha
    Full 40-hex commit SHA the clone's HEAD must already be checked out to.

.PARAMETER ExpectedVersion
    The VERSION file must contain exactly this string. Default "5.2.0".

.PARAMETER PythonInstaller
    Path to a downloaded python-3.12.10-amd64.exe (from python.org). Checked
    against packaging/local_build_pins.json; never installed by this script.

.PARAMETER PythonExe
    Path to the already-installed python.org CPython 3.12.10 python.exe.

.PARAMETER BuildRoot
    A folder OUTSIDE the clone for the venv and build output (so the clone
    stays clean). Must not be under OneDrive or Desktop, on a subst/mapped or
    UNC drive, behind a reparse point, or under $env:USERPROFILE.

.PARAMETER Iscc
    Path to Inno Setup 6's ISCC.exe. Never installed by this script.

.PARAMETER CiInventory
    REQUIRED path to the ship-set-inventory.txt downloaded from the exact
    SHA's CI run (release-exe-captures artifact). Enforces L5. Its header
    line (version=<v> commit=<sha>) must match -ExpectedSha/-ExpectedVersion
    exactly, checked before any build work starts.

.PARAMETER AttestPersonalKit
    Required switch. Passing it is the builder's attestation that this
    build is running on personal equipment, not an employer's.
#>

#Requires -Version 7.4

[CmdletBinding()]
param(
    [string]$ExpectedSha,
    [string]$ExpectedVersion = "5.2.0",
    [string]$PythonInstaller,
    [string]$PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    [string]$BuildRoot = "C:\build\orbitrx-5.2.0-work",
    [string]$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$CiInventory,
    [switch]$AttestPersonalKit
)

# --- L-1/I-1: fail closed even if a host somehow ignores the #Requires
# statement above, or the dot-sourced helpers file below fails to load for
# any reason. This inline check is plain syntax that also parses under
# Windows PowerShell 5.1, so a 5.1 user gets this script's own clear
# message here -- before Set-StrictMode, before the dot-source, before
# anything written for 7.4 -- rather than depending on #Requires alone or
# hitting a confusing parse/strict-mode error partway into a step written
# for 7.4. I-1: the floor is the full version 7.4 (compared, not just the
# Major component), so 7.0-7.3 refuse here too, same as 5.1/6.x.
if ($PSVersionTable.PSVersion -lt [version]'7.4') {
    Write-Output "BUILD FAILED: PowerShell 7.4 or later is required (run with pwsh; found $($PSVersionTable.PSVersion)). Install PowerShell 7.4 or later and run this script with pwsh, not Windows PowerShell 5.1's powershell.exe -- see BUILD-RELEASE.md's Prerequisites."
    exit 1
}

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- L-4c/L-5/L-A: declared ABOVE the top-level try (not just near its top),
# so the catch at the bottom of this script can always reference them (under
# Set-StrictMode) however early a failure happens -- including a failure in
# the very first thing the try does, the dot-source of the helpers file just
# below. Before this fix (L-A), these were declared inside the try but after
# the dot-source, so a missing or unparsable helpers file made the catch
# itself crash on an unset variable ("$zipPath cannot be retrieved because
# it has not been set") instead of printing a BUILD FAILED line. They stay
# $null/$false here, and the catch's cleanup is simply a no-op, until
# section i (the pack) actually runs.
$zipPath = $null
$extractDir = $null
$zipFinalized = $false

# --- Everything below runs inside one top-level try/catch so that a
# terminating error -- however deep the throw -- still prints a single
# "BUILD FAILED: ..." line to the SUCCESS output stream (Write-Output)
# before the script exits. That matters because Jamie's documented
# invocation is `... *>&1 | Tee-Object -FilePath build-console.txt`: an
# uncaught terminating error cuts off the pipeline before Tee-Object ever
# sees it (only the interactive host prints it), so build-console.txt --
# the file sent to QA/Risk -- would otherwise be missing the one line that
# explains why the dry run failed. Catching it here and reporting it with
# Write-Output keeps the script's own execution "successful" from
# PowerShell's point of view, so the message is carried by *>&1 just like
# any other output. The dot-source of the helpers file (below) is inside
# this try too (L-1): a missing or unparsable helpers file is then just
# another terminating error the catch below reports as a BUILD FAILED line
# naming that file, instead of an uncaught error that bypasses Tee-Object.
try {

# --- Pure helpers (path guard, provenance PII check, inventory header parse,
# hash/pin helpers, SHA/attestation validation, publisher-check logic,
# PowerShell-version-support decision) live in a dot-sourced file so
# tests/test_build_release_local_pwsh.py can call them directly with pwsh.
# See tools/build_release_local.helpers.ps1.
$helpersPath = Join-Path $PSScriptRoot 'build_release_local.helpers.ps1'
if (-not (Test-Path -LiteralPath $helpersPath)) {
    throw "Helpers file not found: $helpersPath"
}
. (Join-Path $PSScriptRoot 'build_release_local.helpers.ps1')

# --- NEW-5/I-1: PowerShell 7.4 (pwsh) is required. This is a second,
# helper-based check: the plain inline check above already stops a
# below-7.4 host long before this point, but Test-PowerShellVersionSupported
# is kept here too (it is still the function tests/test_build_release_local_pwsh.py
# exercises directly) as a backstop and so it stays a used, not dead, helper.
if (-not (Test-PowerShellVersionSupported -Version $PSVersionTable.PSVersion)) {
    throw "PowerShell 7.4 or later is required (found $($PSVersionTable.PSVersion)). Install PowerShell 7.4 or later and run this script with pwsh, not Windows PowerShell 5.1's powershell.exe -- see BUILD-RELEASE.md's Prerequisites."
}

# --- Local helpers that need real processes/files (not pure, not dot-sourced)

# R-c: shadows the Write-Host cmdlet for the rest of this script (a function
# always wins over a same-named cmdlet in its own scope, and try/catch do not
# introduce a new scope, so this also covers the top-level catch far below).
# Every existing Write-Host call site is covered without rewriting each one,
# and this is also what reaches build-console.txt: Jamie's documented
# invocation pipes this whole script's output via `*>&1 | Tee-Object`, and
# `*>&1` merges Write-Host's Information stream into that pipe.
function Write-Host {
    param(
        [Parameter(Position = 0, ValueFromPipeline = $true)]
        [object]$Object,
        [switch]$NoNewline
    )
    Microsoft.PowerShell.Utility\Write-Host -Object (Format-RedactedText -Text "$Object") -NoNewline:$NoNewline
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$FailureMessage)
    # R-c: relayed tool output (pip, pytest, PyInstaller, ISCC, the python
    # tools) is captured and re-emitted via the redacting Write-Host above,
    # rather than left to flow to the console directly -- same reason as
    # Invoke-CheckedTee below. This does not disturb $LASTEXITCODE: only a
    # native executable sets it, and nothing after `&` here is native.
    & $FilePath @ArgumentList 2>&1 | ForEach-Object { Write-Host "$_" }
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

function Invoke-CheckedTee {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$FailureMessage, [string]$OutputFile)
    # R-c: redact before Tee-Object, so both the console-bound copy and
    # $OutputFile (one of the out\ gate-result files) get the redacted text,
    # not the raw one. $LASTEXITCODE is unaffected (see Invoke-Checked).
    & $FilePath @ArgumentList 2>&1 | ForEach-Object { Format-RedactedText -Text "$_" } | Tee-Object -FilePath $OutputFile
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

function Set-RedactedFileText {
    # R-c: ship_set.py/pe_check.py/scan_pyz.py write their out\ files
    # directly (not relayed via this script's own streams), so those files
    # are redacted in place, immediately after each tool call and before
    # anything later hashes them for the provenance record.
    param([string]$Path)
    $text = Get-Content -LiteralPath $Path -Raw
    Set-Content -LiteralPath $Path -Value (Format-RedactedText -Text $text) -NoNewline -Encoding utf8
}

function Invoke-OpenSslPinCheck {
    param([string]$Root, [psobject]$Pin, [string]$VenvPython)
    $pyVer = (& $VenvPython -c "import platform; print(platform.python_version())").Trim()
    if ($pyVer -ne $Pin.python) {
        throw "Build Python is $pyVer, manifest pins $($Pin.python)."
    }
    $expectedNames = @($Pin.dlls.PSObject.Properties.Name | ForEach-Object { $_.ToLower() } | Sort-Object)
    $found = @(Get-ChildItem -Path $Root -Recurse -File | Where-Object { $_.Name -match '^(libcrypto|libssl|libeay|ssleay|openssl).*\.dll$' })
    $foundNames = @($found | ForEach-Object { $_.Name.ToLower() } | Sort-Object)
    if (($foundNames -join ',') -ne ($expectedNames -join ',')) {
        throw "OpenSSL DLL set changed: expected $($expectedNames -join ', '), found $($foundNames -join ', ')."
    }
    foreach ($prop in $Pin.dlls.PSObject.Properties) {
        $dll = $found | Where-Object { $_.Name -ieq $prop.Name } | Select-Object -First 1
        if (-not $dll) {
            throw "$($prop.Name) missing from ship set."
        }
        $fileVersion = "$($dll.VersionInfo.FileVersion)".Trim()
        $dllHash = Get-Sha256Hex $dll.FullName
        # @(...): same empty-array-collapses-to-$null guard as Invoke-PublisherCheck.
        $problems = @(Get-OpenSslDllPinProblems -DllName $prop.Name -DirectoryName $dll.DirectoryName -ExpectedDirectory (Join-Path $Root '_internal') -FileVersion $fileVersion -Sha256 $dllHash -PinEntry $prop.Value)
        if ($problems.Count -gt 0) {
            throw ($problems -join ' ')
        }
    }
    if (Get-ChildItem -Path $Root -Recurse -File -Filter qopensslbackend.dll) {
        throw 'qopensslbackend.dll reached the ship set.'
    }
    Write-Host "OPENSSL-PIN: PASS"
}

function Invoke-ShippedNoticesCheck {
    param([string]$Root, [psobject]$Texts, [string]$VenvPython)
    foreach ($rel in @('third_party/python/LICENSE.txt', 'third_party/qt/QT_THIRD_PARTY_ATTRIBUTIONS.txt', 'third_party/openssl/LICENSE.txt')) {
        $shipped = Join-Path $Root ('_internal/' + $rel)
        if (-not (Test-Path $shipped)) {
            throw "$rel is not in the onedir at _internal/$rel."
        }
        $shippedHash = Get-Sha256Hex $shipped
        if ($shippedHash -ne $Texts.$rel) {
            throw "_internal/$rel sha256 $shippedHash != manifest $($Texts.$rel)."
        }
    }
    $base = (& $VenvPython -c "import sys; print(sys.base_prefix)").Trim()
    $runnerLicence = Join-Path $base 'LICENSE.txt'
    if (-not (Test-Path $runnerLicence)) {
        throw "Build interpreter has no LICENSE.txt at $runnerLicence."
    }
    if ((Get-Sha256Hex $runnerLicence) -ne $Texts.'third_party/python/LICENSE.txt') {
        throw "Vendored third_party/python/LICENSE.txt differs from the build interpreter's LICENSE.txt."
    }
    Write-Host "SHIPPED-NOTICES: PASS"
}

function Invoke-PublisherCheck {
    param([string[]]$Exes, [string]$ExpectedAppVersion)
    foreach ($exePath in $Exes) {
        $versionInfo = (Get-Item $exePath).VersionInfo
        # @(...): a function returning an empty array collapses to $null across
        # the call boundary in PowerShell; under Set-StrictMode that would make
        # the very next ".Count" throw on every clean run (the common case).
        $problems = @(Test-PublisherVersionInfo -VersionInfo $versionInfo -ExpectedAppVersion $ExpectedAppVersion -Label $exePath)
        if ($problems.Count -gt 0) {
            throw ($problems -join ' ')
        }
    }
    Write-Host "PUBLISHER-CHECK: PASS"
}

# --- a. Attestation, employer-device heuristic (N9), SHA format ------------

Assert-PersonalKitAttested -Attested:([bool]$AttestPersonalKit)

$dsregcmdDomainJoined = 'not available'
$dsregcmdAzureAdJoined = 'not available'
$dsregcmdEnterpriseJoined = 'not available'
$dsregcmdWorkplaceJoined = 'not available'
# region managed-device-check
# Risk R3 Ruling 2 (L-B), in full. Refuses (BUILD FAILED, exit 1, "Stop and
# tell Risk.") when:
#   1. any of the 4 flags reads YES anywhere (ConvertFrom-DsregcmdStatus /
#      Test-ManagedDeviceStatus: duplicates count, no "last value wins");
#   2. dsregcmd exits non-zero, or its output is empty (checked here);
#   3. fewer than all 4 keys parse (Test-ManagedDeviceStatus);
#   4. any of the 4 values is anything other than exactly YES or NO, e.g.
#      "YES (Contoso)" or a localised word -- UNVERIFIED, which refuses
#      (ConvertFrom-DsregcmdStatus / Test-ManagedDeviceStatus);
#   5. dsregcmd is missing on this Windows PC (checked here). It ships in
#      System32 on Windows 10/11, so its absence here is itself abnormal.
#      "Missing, so skip" is allowed only when -not $IsWindows, for the
#      test harness; a real build cannot run there anyway.
# No override: no switch, parameter, environment variable or config
# anywhere bypasses or downgrades this check. -AttestPersonalKit
# (Assert-PersonalKitAttested, above) is a required attestation in
# addition to this check, never a substitute for it.
$dsregcmdCommand = Get-Command dsregcmd -ErrorAction SilentlyContinue
if (-not $dsregcmdCommand) {
    if ($IsWindows) {
        throw "MANAGED-DEVICE-CHECK: dsregcmd is missing on this Windows PC, which is itself abnormal. L1 requires a verified personal-kit check. Stop and tell Risk."
    }
    Write-Host "MANAGED-DEVICE-CHECK: dsregcmd not available, skipping (only allowed off Windows, for the test harness; recorded as 'not available' in provenance)"
}
else {
    $dsregLines = @(& dsregcmd /status)
    $dsregExitCode = $LASTEXITCODE
    $dsregHasOutput = (@($dsregLines | Where-Object { $_ -and "$_".Trim() -ne '' })).Count -gt 0
    if ($dsregExitCode -ne 0) {
        throw "MANAGED-DEVICE-CHECK: UNVERIFIED (dsregcmd exited with code $dsregExitCode). L1 requires a verified personal-kit check. Stop and tell Risk."
    }
    if (-not $dsregHasOutput) {
        throw "MANAGED-DEVICE-CHECK: UNVERIFIED (dsregcmd produced no output). L1 requires a verified personal-kit check. Stop and tell Risk."
    }
    $dsregFlags = ConvertFrom-DsregcmdStatus -Lines $dsregLines
    $managedStatus = Test-ManagedDeviceStatus -Flags $dsregFlags
    if ($managedStatus.Refuse) {
        throw $managedStatus.Message
    }
    $dsregcmdDomainJoined = $dsregFlags['DomainJoined']
    $dsregcmdAzureAdJoined = $dsregFlags['AzureAdJoined']
    $dsregcmdEnterpriseJoined = $dsregFlags['EnterpriseJoined']
    $dsregcmdWorkplaceJoined = $dsregFlags['WorkplaceJoined']
    Write-Host "MANAGED-DEVICE-CHECK: PASS (DomainJoined=$dsregcmdDomainJoined AzureAdJoined=$dsregcmdAzureAdJoined EnterpriseJoined=$dsregcmdEnterpriseJoined WorkplaceJoined=$dsregcmdWorkplaceJoined)"
}
# endregion managed-device-check

$ExpectedSha = Assert-ValidExpectedSha -Sha $ExpectedSha

if (-not $CiInventory) {
    throw "-CiInventory is required (L5): download ship-set-inventory.txt from the exact -ExpectedSha's CI run (the release-exe-captures artifact) and pass it here. See BUILD-RELEASE.md."
}
if (-not (Test-Path $CiInventory)) {
    throw "-CiInventory file not found: '$CiInventory'."
}

$buildStartUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# --- N4: path guards up front, before any other work ------------------------

Assert-SafeBuildPath -Path $repoRoot -Label 'Repo root' | Out-Null
$buildRootFull = Assert-SafeBuildPath -Path $BuildRoot -Label 'Build root (-BuildRoot)'
Assert-SafeBuildPath -Path $CiInventory -Label '-CiInventory' | Out-Null
Assert-SafeBuildPath -Path $PythonExe -Label '-PythonExe' | Out-Null
if ($PythonInstaller) {
    Assert-SafeBuildPath -Path $PythonInstaller -Label '-PythonInstaller' | Out-Null
}
Assert-BuildRootOutsideUserProfile -BuildRootFull $buildRootFull

# --- M-1: refuse up front, before any build work (pip install, PyInstaller,
# the 20-40 minute build) starts, if a previous run's out\ is still sitting
# under this BuildRoot. Without this, a stale public
# out\OrbitRx-Setup-<v>.zip from an earlier *successful* run survives a
# failing re-run (left under the public name), and even a *passing* re-run
# fails at the very last step (Rename-Item: file already exists) after the
# new provenance record has already been written -- leaving the old zip
# next to a provenance record that describes a different zip. The packer's
# own stale-"<name>.pending" removal (NEW-2/L-4a) is unaffected and stays;
# this is a separate, earlier check on the public name's directory.
$outDir = Join-Path $BuildRoot 'out'
if ((Test-Path -LiteralPath $outDir) -and @(Get-ChildItem -LiteralPath $outDir -Force).Count -gt 0) {
    throw "-BuildRoot's out\ folder ('$outDir') already exists and is not empty. Delete the whole -BuildRoot folder ('$BuildRoot') and start this run with a new, empty BuildRoot -- see BUILD-RELEASE.md."
}

Write-Host "Repo root: $repoRoot"
Write-Host "Build root: $BuildRoot"

# --- b. Clean clone at the exact expected SHA, then VERSION -----------------

Push-Location $repoRoot
try {
    $headSha = (git rev-parse HEAD).Trim().ToLower()
    if ($headSha -ne $ExpectedSha) {
        throw "HEAD is $headSha, expected $ExpectedSha (-ExpectedSha). Check out the exact commit before building."
    }
    $porcelain = git status --porcelain --ignored
    if ($porcelain) {
        throw "Working tree is not clean (untracked or ignored files present before the build). The clone must be freshly checked out -- see BUILD-RELEASE.md.`n$porcelain"
    }
    $headTree = (git rev-parse 'HEAD^{tree}').Trim()
    $version = (Get-Content (Join-Path $repoRoot 'VERSION')).Trim()
    if ($version -ne $ExpectedVersion) {
        throw "VERSION is '$version', expected '$ExpectedVersion' (-ExpectedVersion)."
    }
}
finally {
    Pop-Location
}
Write-Host "CLEAN-CLONE-CHECK: PASS (HEAD=$headSha tree=$headTree VERSION=$version)"

# --- R1 (L5 mandatory): parse and check the CI inventory header BEFORE any
# build work starts, so a wrong/stale inventory fails fast, not after a
# 20-40 minute build.

$ciInventoryHeader = Get-ShipSetInventoryHeader -Path $CiInventory
Assert-CiInventoryMatchesBuild -Header $ciInventoryHeader -ExpectedSha $ExpectedSha -ExpectedVersion $ExpectedVersion
$ciInventorySha256 = Get-Sha256Hex $CiInventory
Write-Host "CI-INVENTORY-HEADER-CHECK: PASS (version=$($ciInventoryHeader.Version) commit=$($ciInventoryHeader.Commit) sha256=$ciInventorySha256)"

# --- c. Python installer and interpreter pins ---------------------------------

if (-not $PythonInstaller -or -not (Test-Path $PythonInstaller)) {
    throw "-PythonInstaller not found: '$PythonInstaller'. Download python-3.12.10-amd64.exe from python.org yourself; this script does not fetch it."
}
$pins = Get-Content (Join-Path $repoRoot 'packaging\local_build_pins.json') -Raw | ConvertFrom-Json

$installerSha256 = Get-Sha256Hex $PythonInstaller
$installerMd5 = Get-Md5Hex $PythonInstaller
Assert-PythonInstallerHashesMatch -Sha256 $installerSha256 -Md5 $installerMd5 -PythonPin $pins.python
$installerSig = Get-AuthenticodeSignature -FilePath $PythonInstaller

if (-not (Test-Path $PythonExe)) {
    throw "-PythonExe not found: '$PythonExe'. Install python-3.12.10-amd64.exe for the current user yourself; this script does not install it."
}
$pythonExeSig = Get-AuthenticodeSignature -FilePath $PythonExe

# P8c2: one shared helper call, fed both already-retrieved signature
# objects by name -- so the python.exe check cannot accidentally be passed
# $installerSig a second time instead of $pythonExeSig (see
# Assert-PythonAndInstallerSignaturesValid in build_release_local.helpers.ps1).
Assert-PythonAndInstallerSignaturesValid -InstallerSignature $installerSig -PythonExeSignature $pythonExeSig -SignerSubjectContains $pins.python.authenticode_signer_subject_contains
$installerSignerSubject = $installerSig.SignerCertificate.Subject
$installerSignerThumbprint = $installerSig.SignerCertificate.Thumbprint
$pythonExeSignerSubject = $pythonExeSig.SignerCertificate.Subject
$pythonExeSignerThumbprint = $pythonExeSig.SignerCertificate.Thumbprint
Write-Host "PYTHON-INSTALLER-PIN: PASS (sha256=$installerSha256)"

$pyVersionString = (& $PythonExe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])").Trim()
if ($pyVersionString -ne $pins.python.version) {
    throw "python.exe reports $pyVersionString, pinned $($pins.python.version)."
}
$pyBits = (& $PythonExe -c "import struct; print(struct.calcsize('P') * 8)").Trim()
if ($pyBits -ne '64') {
    throw "python.exe is $pyBits-bit; a 64-bit interpreter is required."
}

$manifest = Get-Content (Join-Path $repoRoot 'packaging\distribution_manifest.json') -Raw | ConvertFrom-Json
$opensslPin = $manifest.ship_set.openssl
$pyBasePrefix = (& $PythonExe -c "import sys; print(sys.base_prefix)").Trim()
foreach ($dllName in $opensslPin.dlls.PSObject.Properties.Name) {
    $dllPath = Join-Path (Join-Path $pyBasePrefix 'DLLs') $dllName
    if (-not (Test-Path $dllPath)) {
        throw "Build interpreter is missing $dllPath."
    }
    Assert-Sha256Match -Path $dllPath -Expected $opensslPin.dlls.$dllName.sha256 -Label $dllName | Out-Null
}
$pythonLicence = Join-Path $pyBasePrefix 'LICENSE.txt'
$repoLicence = Join-Path $repoRoot 'third_party\python\LICENSE.txt'
if (-not (Test-Path $pythonLicence)) {
    throw "Build interpreter has no LICENSE.txt at $pythonLicence."
}
if ((Get-Sha256Hex $pythonLicence) -ne (Get-Sha256Hex $repoLicence)) {
    throw "python.exe's LICENSE.txt differs from third_party/python/LICENSE.txt."
}
$pythonExeSha256 = Get-Sha256Hex $PythonExe
Write-Host "PYTHON-EXE-PIN: PASS (sha256=$pythonExeSha256 version=$pyVersionString)"

# --- d. Fresh venv in BuildRoot, install from the committed hash-pinned lock -

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

# region tool-caches
# (tests/test_build_release_local_pwsh.py extracts this region the same way
# as the pack-l6/provenance-finalize regions, to exercise it standalone
# against a fake -BuildRoot without needing a real pip/PyInstaller run.)
#
# C6: redirect pip's and PyInstaller's own caches to folders under
# -BuildRoot, scoped to this process only ($env: here sets a process-block
# variable, not the user/machine environment -- it is gone as soon as this
# script exits, and nothing below persists it). Deliberately NOT touched:
# $env:TEMP/$env:TMP. Format-RedactedText (R-c) reads $env:USERPROFILE/
# LOCALAPPDATA/APPDATA/TEMP fresh on every call, so overriding $env:TEMP
# here would silently change what counts as "this PC's temp folder" for
# every redaction call after this point -- real temp-path leakage from
# tools that ignore our override (or ran before it) would then go
# unredacted. Pip and PyInstaller are the two known, directly-configurable
# cache writers (via PIP_CACHE_DIR/PYINSTALLER_CONFIG_DIR); redirecting
# those two is a clear win without that redaction regression.
$pipCacheDir = Join-Path $BuildRoot 'cache\pip'
$pyinstallerConfigDir = Join-Path $BuildRoot 'cache\pyinstaller'
New-Item -ItemType Directory -Force -Path $pipCacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $pyinstallerConfigDir | Out-Null
$env:PIP_CACHE_DIR = $pipCacheDir
$env:PYINSTALLER_CONFIG_DIR = $pyinstallerConfigDir
Write-Host "TOOL-CACHES: PASS (pip=$pipCacheDir pyinstaller=$pyinstallerConfigDir, both under -BuildRoot)"
# endregion tool-caches

$venvDir = Join-Path $BuildRoot 'venv'
if (Test-Path $venvDir) {
    Remove-Item -Recurse -Force $venvDir
}
Invoke-Checked -FilePath $PythonExe -ArgumentList @('-m', 'venv', $venvDir) -FailureMessage 'python -m venv failed'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$venvPyinstaller = Join-Path $venvDir 'Scripts\pyinstaller.exe'

$pipVersionLine = (& $venvPython -m pip --version).Trim()

$requirementsPath = Join-Path $repoRoot 'requirements.txt'
$requirementsSha256 = Get-Sha256Hex $requirementsPath

# R2: the Windows build only ever installs from the committed, fully
# hash-pinned lock file -- never from requirements.txt directly and never
# from an arbitrary file passed on the command line. --no-deps is safe only
# because the lock lists every transitive dependency; "pip check" then
# proves that closure is complete and consistent.
$lockPath = Join-Path $repoRoot 'packaging\requirements-windows-build.lock.txt'
if (-not (Test-Path $lockPath)) {
    throw "Committed lock file not found: $lockPath. This script only installs from packaging\requirements-windows-build.lock.txt (R2)."
}
$lockSha256 = Get-Sha256Hex $lockPath
Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pip', 'install', '--require-hashes', '--no-deps', '-r', $lockPath) -FailureMessage 'pip install --require-hashes --no-deps -r packaging\requirements-windows-build.lock.txt failed'
Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pip', 'check') -FailureMessage 'pip check failed after installing from the hash-pinned lock'

$pipFreezeText = (& $venvPython -m pip freeze) -join "`n"
$pipFreezeBytes = [System.Text.Encoding]::UTF8.GetBytes($pipFreezeText)
$pipFreezeSha256 = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($pipFreezeBytes)).Replace('-', '').ToLower()
Write-Host "DEPENDENCIES: PASS (requirements.txt sha256=$requirementsSha256, lock sha256=$lockSha256, pip freeze sha256=$pipFreezeSha256)"

# --- e. pytest suite (network-marked tests excluded) and compileall, as in
# CI's test job -- except CI runs the full suite including the
# network-marked live NOAA test (registered in pyproject.toml); this local
# gate excludes it with -m "not network" so a dry run on a disconnected or
# flaky-network PC does not fail on something CI has already proven passes
# at this exact SHA.

Push-Location $repoRoot
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'compileall', '-q', 'app.py', 'orbitrx') -FailureMessage 'compileall failed'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pytest', '-q', '-m', 'not network') -FailureMessage 'pytest failed'
}
finally {
    Pop-Location
}
Write-Host "TESTS: PASS"

# --- f. Stamp commit, PyInstaller, Inno Setup --------------------------------

Push-Location $repoRoot
try {
    $shortSha = $ExpectedSha.Substring(0, 7)
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\stamp_commit.py', $shortSha) -FailureMessage 'tools/stamp_commit.py failed'

    Invoke-Checked -FilePath $venvPyinstaller -ArgumentList @('OrbitRxMonitor.spec', '--noconfirm') -FailureMessage 'pyinstaller failed'
    if (-not (Test-Path 'dist\OrbitRxMonitor\OrbitRxMonitor.exe')) {
        throw 'dist\OrbitRxMonitor\OrbitRxMonitor.exe is missing after pyinstaller.'
    }

    $verNumericRaw = & $venvPython -c "from tools.make_version_info import version_tuple4; print('.'.join(str(n) for n in version_tuple4('$version')))"
    if ($LASTEXITCODE -ne 0) {
        throw 'tools/make_version_info.version_tuple4 failed'
    }
    $verNumeric = $verNumericRaw.Trim()

    if (-not (Test-Path $Iscc)) {
        throw "Inno Setup compiler not found at '$Iscc'. Install Inno Setup 6 yourself first (see BUILD-RELEASE.md); this script does not install it."
    }
    $pyinstallerVersion = (& $venvPython -c "import PyInstaller; print(PyInstaller.__version__)").Trim()
    $isccVersionInfo = (Get-Item $Iscc).VersionInfo
    $isccVersionLine = if ($isccVersionInfo.ProductVersion) {
        $isccVersionInfo.ProductVersion
    }
    elseif ($isccVersionInfo.FileVersion) {
        $isccVersionInfo.FileVersion
    }
    else {
        'unknown'
    }

    Invoke-Checked -FilePath $Iscc -ArgumentList @("/DAppVer=$version", "/DAppVerNumeric=$verNumeric", 'installer\OrbitRxMonitor.iss') -FailureMessage 'ISCC (Inno Setup) failed'
    if (-not (Test-Path 'dist\OrbitRxMonitor-Setup.exe')) {
        throw 'dist\OrbitRxMonitor-Setup.exe is missing after ISCC.'
    }

    # stamp_commit.py intentionally modifies the tracked orbitrx/_build_meta.py.
    # Confirm that is the ONLY tracked-file change the build introduced (dist/
    # and build/ are gitignored, so PyInstaller/ISCC output never shows here).
    $statusLines = @(git status --porcelain | Where-Object { $_ -and $_.Trim().Length -gt 0 })
    $unexpected = @($statusLines | Where-Object { $_ -notmatch '^\s*M\s+orbitrx/_build_meta\.py\s*$' })
    if ($unexpected.Count -gt 0) {
        throw "Unexpected working-tree changes after the build (expected only orbitrx/_build_meta.py to be modified):`n$($unexpected -join "`n")"
    }
    if ($statusLines.Count -eq 0) {
        throw 'orbitrx/_build_meta.py was not modified by tools/stamp_commit.py as expected.'
    }
    Write-Host "BUILD-META-CHECK: PASS (only orbitrx/_build_meta.py modified)"
}
finally {
    Pop-Location
}
Write-Host "BUILD: PASS (PyInstaller $pyinstallerVersion, $isccVersionLine)"

# --- g. CI-equivalent gates ----------------------------------------------------

Push-Location $repoRoot
try {
    $onedirRoot = (Resolve-Path 'dist\OrbitRxMonitor').Path
    $exePath = Join-Path $onedirRoot 'OrbitRxMonitor.exe'
    $installerExePath = (Resolve-Path 'dist\OrbitRxMonitor-Setup.exe').Path

    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\check_onedir_layout.py', $onedirRoot) -FailureMessage 'onedir layout check failed'
    Write-Host "ONEDIR-LAYOUT: PASS"

    Get-FileHash $exePath, $installerExePath -Algorithm SHA256 |
        ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } |
        Out-File 'dist\SHA256SUMS.txt' -Encoding ascii

    # M-1: $outDir itself is already set (near the top, right after the N4
    # path guards), so the up-front empty-BuildRoot check above and this
    # directory are guaranteed to agree on the same path.
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    # R-c: ship-set-inventory.txt is deliberately NOT passed through
    # Format-RedactedText -- it is compared byte-for-byte later (--compare-
    # tree, against both this file and -CiInventory), and every line
    # written into it below is either a sha256+leaf-filename pair, a path
    # relative to $onedirRoot, or a FileVersion/ProductName/sha256 triple --
    # none of which can contain $env:USERPROFILE/USERNAME/COMPUTERNAME.
    $localInventoryPath = Join-Path $outDir 'ship-set-inventory.txt'
    "version=$version commit=$ExpectedSha" | Out-File $localInventoryPath -Encoding utf8
    Get-Content 'dist\SHA256SUMS.txt' | Out-File $localInventoryPath -Append -Encoding utf8
    Get-ChildItem -Path $onedirRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
        "{0}`t{1}" -f $_.FullName.Substring($onedirRoot.Length + 1).Replace('\', '/'), $_.Length
    } | Out-File $localInventoryPath -Append -Encoding utf8
    foreach ($dllName in $opensslPin.dlls.PSObject.Properties.Name) {
        $dll = Get-ChildItem -Path $onedirRoot -Recurse -Filter $dllName -File -ErrorAction SilentlyContinue | Select-Object -First 1
        $line = if ($dll) {
            $v = $dll.VersionInfo
            "$dllName FileVersion=$($v.FileVersion) ProductName=$($v.ProductName) sha256=$(Get-Sha256Hex $dll.FullName)"
        }
        else {
            "$dllName not found in ship set"
        }
        $line | Out-File $localInventoryPath -Append -Encoding utf8
    }
    Write-Host "Wrote local ship-set-inventory.txt: $localInventoryPath"

    Invoke-OpenSslPinCheck -Root $onedirRoot -Pin $opensslPin -VenvPython $venvPython
    Invoke-ShippedNoticesCheck -Root $onedirRoot -Texts $manifest.present_texts -VenvPython $venvPython

    $shipSetQtList = Join-Path $outDir 'ship-set-qt.txt'
    $shipSetTlsList = Join-Path $outDir 'ship-set-tls.txt'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\ship_set.py', '--check', $onedirRoot, '--write-qt-list', $shipSetQtList, '--write-tls-list', $shipSetTlsList) -FailureMessage 'ship-set gate failed'
    Set-RedactedFileText -Path $shipSetQtList
    Set-RedactedFileText -Path $shipSetTlsList
    Write-Host "SHIP-SET-GATE: PASS"

    Invoke-PublisherCheck -Exes @($exePath, $installerExePath) -ExpectedAppVersion $version

    # region pe-check-redact
    # (tests/test_build_release_local_pwsh.py extracts this region the same
    # way as the pack-l6/provenance-finalize regions, to exercise the real
    # call site behaviourally: does out\installer-publisher.txt actually
    # get redacted, not just the Set-RedactedFileText function in isolation?)
    $peCheckOut = Join-Path $outDir 'installer-publisher.txt'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pe_check.py', $peCheckOut, $exePath, $installerExePath) -FailureMessage 'tools/pe_check.py failed'
    Set-RedactedFileText -Path $peCheckOut
    # endregion pe-check-redact
    Write-Host "PE-CHECK: PASS"

    # N6: the same static PYZ scan CI's "Scan the bundled PYZ" step runs, so
    # the local gates catch the same simulated-rig-leak class of bug. CI's
    # runtime gates (screenshot capture, fit, units, DX cluster edges) are
    # NOT repeated here -- see BUILD-RELEASE.md for why, and rely on the CI
    # run at this exact SHA for those.
    $pyzScanOut = Join-Path $outDir 'pyz-scan.txt'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\scan_pyz.py', $exePath, $pyzScanOut) -FailureMessage 'tools/scan_pyz.py failed'
    Set-RedactedFileText -Path $pyzScanOut
    Write-Host "PYZ-SCAN: PASS"
}
finally {
    Pop-Location
}

# --- i. Pack with the deterministic packer, L5/L6 checks, determinism check -

# NEW-2: tools\pack_setup_zip.py itself never leaves a ready zip at $zipPath
# unless its own L5 --expect-inventory check passed (it writes to a
# "<out>.partial" and only renames to the final name once verify and the
# inventory compare both pass, deleting the partial on any failure). The
# catch below covers the remaining case: a *later* check in this section
# (L6's re-extract/verify/compare-tree, or the determinism self-check)
# finding a problem with a zip that did pass L5 -- that zip must not survive
# as the final $zipPath either, so it is deleted before the error
# propagates.
#
# L-4c/L-5: $zipPath itself is built under a "<name>.pending" name here and
# stays that way across the whole provenance section below -- it is renamed to its real
# public $zipName only as the very last step, once the provenance record
# has been written AND its own unsafe-marker self-check has passed (see
# "$zipFinalized" near the end of section j). That closes the remaining
# gap NEW-2 did not cover: a failure in the provenance write/self-check,
# which runs after this try/catch has already exited cleanly, must still
# leave nothing at the public $zipName. The top-level catch at the bottom
# of this script deletes the still-pending file (and out\extracted) for
# exactly that case.
#
# region pack-l6
# (tests/test_build_release_local_pwsh.py extracts this whole region by its
# start/end marker comments via plain text slicing -- validated as
# parseable PowerShell with the AST parser -- and runs it standalone with
# stubbed tools\pack_setup_zip.py / tools\ship_set.py, to exercise
# N2e/P14/P15 behaviourally without a real Windows build.)
$zipPath = $null
$extractDir = $null
$zipFinalized = $false
Push-Location $repoRoot
try {
    $commitEpoch = (git show -s --format=%ct $ExpectedSha).Trim()
    $zipName = "OrbitRx-Setup-$version.zip"
    $zipFinalPath = Join-Path $outDir $zipName
    $zipPath = Join-Path $outDir "$zipName.pending"
    $packArgs = @(
        'tools\pack_setup_zip.py',
        '--onedir', $onedirRoot,
        '--installer', $installerExePath,
        '--out', $zipPath,
        '--epoch', $commitEpoch,
        '--expect-inventory', $CiInventory
    )
    $packResultOut = Join-Path $outDir 'l5-pack-result.txt'
    Invoke-CheckedTee -FilePath $venvPython -ArgumentList $packArgs -FailureMessage 'deterministic pack failed (this may be an L5 ship-set-inventory mismatch)' -OutputFile $packResultOut
    Write-Host "L5-INVENTORY-MATCH: PASS"

    $extractDir = Join-Path $outDir 'extracted'
    if (Test-Path $extractDir) {
        Remove-Item -Recurse -Force $extractDir
    }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\ship_set.py', '--check', (Join-Path $extractDir 'OrbitRxMonitor')) -FailureMessage 'L6: ship_set --check failed on the extracted zip'
    $l6VerifyOut = Join-Path $outDir 'l6-verify.txt'
    Invoke-CheckedTee -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--verify', $zipPath, '--onedir', $onedirRoot, '--installer', $installerExePath, '--epoch', $commitEpoch) -FailureMessage 'L6: packer --verify failed' -OutputFile $l6VerifyOut
    Write-Host "L6-PRE-UPLOAD-CHECK: PASS"

    $extractedOnedir = Join-Path $extractDir 'OrbitRxMonitor'
    $l6CompareLocalOut = Join-Path $outDir 'l6-compare-tree-local.txt'
    Invoke-CheckedTee -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--compare-tree', $extractedOnedir, '--inventory', $localInventoryPath) -FailureMessage 'L6: extracted zip tree did not match the local ship-set-inventory.txt' -OutputFile $l6CompareLocalOut
    $l6CompareCiOut = Join-Path $outDir 'l6-compare-tree-ci.txt'
    Invoke-CheckedTee -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--compare-tree', $extractedOnedir, '--inventory', $CiInventory) -FailureMessage 'L6: extracted zip tree did not match -CiInventory' -OutputFile $l6CompareCiOut
    Write-Host "L6-INVENTORY-MATCH: PASS"

    $zipPathRepeat = Join-Path $outDir "OrbitRx-Setup-$version.repack-check.zip"
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--onedir', $onedirRoot, '--installer', $installerExePath, '--out', $zipPathRepeat, '--epoch', $commitEpoch) -FailureMessage 'determinism self-check (second pack) failed'
    $zipSha256 = Get-Sha256Hex $zipPath
    $zipSha256Repeat = Get-Sha256Hex $zipPathRepeat
    Remove-Item -Force $zipPathRepeat
    if ($zipSha256 -ne $zipSha256Repeat) {
        throw "DETERMINISM SELF-CHECK FAILED: two packs of the same inputs produced different sha256 ($zipSha256 vs $zipSha256Repeat)."
    }
    Write-Host "DETERMINISM-SELF-CHECK: PASS (sha256=$zipSha256)"
}
catch {
    if ($zipPath -and (Test-Path $zipPath)) {
        Remove-Item -Force $zipPath
    }
    throw
}
finally {
    Pop-Location
}
# endregion pack-l6

# --- j. Provenance record -------------------------------------------------------

$onedirFileCount = @(Get-ChildItem -Path $onedirRoot -Recurse -File).Count
$exeSha256 = Get-Sha256Hex $exePath
$installerSha256Final = Get-Sha256Hex $installerExePath
$zipSize = (Get-Item $zipPath).Length
$buildEndUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')

# N8: hash every gate output file written to out\ so the provenance record
# can be cross-checked against them without needing the binaries themselves.
$gateOutputFiles = [ordered]@{
    'ship-set-inventory.txt (local)'   = $localInventoryPath
    'ship-set-inventory.txt (CI, -CiInventory)' = $CiInventory
    'ship-set-qt.txt'                  = $shipSetQtList
    'ship-set-tls.txt'                 = $shipSetTlsList
    'installer-publisher.txt (pe_check)' = $peCheckOut
    'pyz-scan.txt'                     = $pyzScanOut
    'l5-pack-result.txt'               = $packResultOut
    'l6-verify.txt'                    = $l6VerifyOut
    'l6-compare-tree-local.txt'        = $l6CompareLocalOut
    'l6-compare-tree-ci.txt'           = $l6CompareCiOut
}

Write-Host ""
Write-Host "OrbitRxMonitor.exe sha256: $exeSha256"
Write-Host "OrbitRxMonitor-Setup.exe sha256: $installerSha256Final"
Write-Host "onedir file count: $onedirFileCount"
Write-Host "zip sha256: $zipSha256"
Write-Host "zip size: $zipSize bytes"

$provenanceLines = @(
    "OrbitRx $version local build provenance",
    "SHA: $ExpectedSha",
    "tree: $headTree",
    "VERSION: $version",
    "Build start (UTC): $buildStartUtc",
    "Build end (UTC): $buildEndUtc",
    'Built on personal PC, not employer equipment (attested by builder)',
    "Managed-device heuristic (dsregcmd): DomainJoined=$dsregcmdDomainJoined AzureAdJoined=$dsregcmdAzureAdJoined EnterpriseJoined=$dsregcmdEnterpriseJoined WorkplaceJoined=$dsregcmdWorkplaceJoined"
)
$provenanceLines += @(
    "Python installer: $($pins.python.installer_filename) sha256=$installerSha256 md5=$installerMd5 signer='$installerSignerSubject' thumbprint=$installerSignerThumbprint",
    "python.exe: sha256=$pythonExeSha256 version=$pyVersionString signer='$pythonExeSignerSubject' thumbprint=$pythonExeSignerThumbprint",
    "pip: $pipVersionLine",
    "Tool caches (C6): pip=$pipCacheDir pyinstaller=$pyinstallerConfigDir (both under -BuildRoot, not a personal path)",
    "requirements.txt sha256: $requirementsSha256",
    "packaging/requirements-windows-build.lock.txt sha256: $lockSha256",
    "CI ship-set-inventory.txt (-CiInventory) sha256: $ciInventorySha256 commit=$($ciInventoryHeader.Commit) version=$($ciInventoryHeader.Version)"
)
$provenanceLines += "pip freeze sha256: $pipFreezeSha256"
$provenanceLines += 'pip freeze:'
$provenanceLines += ($pipFreezeText -split "`n")
$provenanceLines += @(
    "PyInstaller version: $pyinstallerVersion",
    "Inno Setup: $isccVersionLine",
    "PowerShell version: $($PSVersionTable.PSVersion.ToString())",
    "OS version: $([Environment]::OSVersion.VersionString)",
    '',
    'Gate results:',
    '  CLEAN-CLONE-CHECK: PASS',
    '  CI-INVENTORY-HEADER-CHECK: PASS',
    '  PYTHON-INSTALLER-PIN: PASS',
    '  PYTHON-EXE-PIN: PASS',
    '  TESTS: PASS',
    '  BUILD-META-CHECK: PASS',
    '  ONEDIR-LAYOUT: PASS',
    '  OPENSSL-PIN: PASS',
    '  SHIPPED-NOTICES: PASS',
    '  SHIP-SET-GATE: PASS',
    '  PUBLISHER-CHECK: PASS',
    '  PE-CHECK: PASS',
    '  PYZ-SCAN: PASS',
    '  L5-INVENTORY-MATCH: PASS',
    '  L6-PRE-UPLOAD-CHECK: PASS',
    '  L6-INVENTORY-MATCH: PASS',
    '  DETERMINISM-SELF-CHECK: PASS',
    '',
    "OrbitRxMonitor.exe sha256: $exeSha256",
    "OrbitRxMonitor-Setup.exe sha256: $installerSha256Final",
    "onedir file count: $onedirFileCount",
    "zip sha256: $zipSha256",
    "zip size: $zipSize bytes",
    "zip path: out\$zipName",
    '',
    'Gate output files (sha256):'
)
foreach ($label in $gateOutputFiles.Keys) {
    $path = $gateOutputFiles[$label]
    $provenanceLines += "  $label : sha256=$(Get-Sha256Hex $path)"
}
$provenanceText = ($provenanceLines -join "`r`n")

# region provenance-finalize
# (tests/test_build_release_local_pwsh.py extracts this region the same way
# as the pack-l6 region above, to exercise P10's self-check call site
# behaviourally: does it really block the write and the rename when
# $provenanceText contains an unsafe marker?)
#
# @(...): same empty-array-collapses-to-$null guard as Invoke-PublisherCheck
# above -- without it, a clean provenance text (the common case) would make
# the ".Count" check below throw under Set-StrictMode instead of passing.
$unsafeMarkers = @(Get-ProvenanceUnsafeMarkers -Text $provenanceText)
if ($unsafeMarkers.Count -gt 0) {
    throw "Provenance text self-check failed: it contains $($unsafeMarkers -join ', '). Refusing to write it."
}

$provenancePath = Join-Path $outDir "OrbitRx-$version-PROVENANCE.txt"
Set-Content -Path $provenancePath -Value $provenanceText -Encoding utf8
Write-Host ""
Write-Host "Wrote provenance record: $provenancePath"

# --- L-4c/L-5: only now -- after the provenance record has been written
# and the unsafe-marker self-check above has passed -- promote the pending
# zip to its public $zipName. This is the very last step of the validated-
# artifact path; any failure before this point (including the self-check
# or the write itself) leaves nothing at all under the public name. See
# the top-level catch at the bottom of this script, which removes the
# still-pending file (and out\extracted) if this rename never ran.
Rename-Item -LiteralPath $zipPath -NewName $zipName
$zipPath = $zipFinalPath
$zipFinalized = $true
# endregion provenance-finalize

# --- Reminders for the steps this script does not and should not do ----------

Write-Host ""
Write-Host "REMINDER: this is a DRY RUN unless you have been told otherwise -- do not publish this zip. Send the provenance record and the out\ files to QA/Risk under L10 and wait for their review before anything is treated as a publish candidate (see BUILD-RELEASE.md)."
Write-Host "REMINDER (L7): run the HTTPS smoke test by hand -- launch dist\OrbitRxMonitor\OrbitRxMonitor.exe and confirm a live SWPC fetch succeeds. Capture a screenshot or a short note (what you saw, and the timestamp) as L7 evidence. This script does not launch the app for you."
Write-Host "REMINDER: run an antivirus scan over dist\OrbitRxMonitor, the installer and the zip before sharing them."
# region sums-line
# I-3: worded as a label for what follows, not an instruction to act now --
# "append exactly this one line" read like something to do on every run,
# including a dry run, where doing so would be wrong (see the DRY-RUN ONLY
# marker printed right below, which this line hands off to).
Write-Host "SUMS line for a QA/Risk-cleared build only (see marker): if and when this becomes that build, append it exactly as printed to both SUMS locations -- do NOT touch the existing 5.1.0 line:"
# R-b (Risk round): the script cannot know whether this run is the cleared
# build, so this marker is printed unconditionally, immediately before the
# SUMS line it guards -- there is no flag to suppress it.
Write-Host "DRY-RUN ONLY -- NOT FOR PUBLICATION: do not append this line anywhere unless this run is the QA/Risk-cleared <CLEARED_SHA> build and Jamie has given the publish go (P8)."
Write-Host "$zipSha256  $zipName"
# endregion sums-line
Write-Host "REMINDER: do not upload anything until Jamie's explicit publish go (P8) and the N1 acceptance (P9). This script never uploads, publishes, tags or pushes."

# --- Restore the one tracked file the build stamped ---------------------------

# Safe because the BUILD-META-CHECK step above already confirmed this is the
# ONLY tracked file the build modified. The already-built exe keeps the
# stamped short SHA baked into its frozen bytecode, so checking this out
# does not un-stamp the binary -- it only leaves the clone's working tree
# clean again, matching the pre-build invariant checked in step b.
Push-Location $repoRoot
try {
    git checkout -- orbitrx/_build_meta.py
}
finally {
    Pop-Location
}
Write-Host "Restored orbitrx/_build_meta.py; the clone's working tree is clean again."

}
catch {
    # L-4c/L-5 (item 5): a failure anywhere after section i's own
    # catch/finally -- including the provenance write and its unsafe-marker
    # self-check -- must still leave nothing at the public $zipName. $zipPath
    # holds the still-pending file until $zipFinalized is set $true (the
    # very last step of the validated-artifact path, right after the
    # provenance record is written and self-checked), so deleting it here
    # whenever it was not finalized covers that whole window. out\extracted
    # is removed too (I-3) rather than left behind for a failed run.
    if ($zipPath -and -not $zipFinalized -and (Test-Path $zipPath)) {
        Remove-Item -Force $zipPath
    }
    if ($extractDir -and (Test-Path $extractDir)) {
        Remove-Item -Recurse -Force $extractDir
    }
    # L-3: name the file the error was actually thrown from (e.g. the
    # dot-sourced helpers file, not always this script), not just a line
    # number with no file -- Split-Path -Leaf keeps the line short and free
    # of any local path (see N8's "no absolute paths in provenance" rule).
    $failingLine = if ($_.InvocationInfo) { $_.InvocationInfo.ScriptLineNumber } else { 'unknown' }
    $failingFile = if ($_.InvocationInfo -and $_.InvocationInfo.ScriptName) {
        Split-Path -Leaf $_.InvocationInfo.ScriptName
    }
    elseif ($PSCommandPath) {
        Split-Path -Leaf $PSCommandPath
    }
    else {
        'build_release_local.ps1'
    }
    # R-c: an exception's own message can carry a path under this PC's
    # profile (e.g. a bad -PythonExe argument) -- redact it too, but guard
    # the call in case the very first thing to fail was dot-sourcing the
    # helpers file itself (Format-RedactedText then would not exist yet).
    $buildFailedLine = "BUILD FAILED: $($_.Exception.Message) (${failingFile}:${failingLine})"
    if (Get-Command Format-RedactedText -ErrorAction SilentlyContinue) {
        $buildFailedLine = Format-RedactedText -Text $buildFailedLine
    }
    Write-Output $buildFailedLine
    exit 1
}
exit 0
