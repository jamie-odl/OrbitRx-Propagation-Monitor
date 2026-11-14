<#
.SYNOPSIS
    Build the OrbitRx 5.2.0 local candidate on Jamie's own PC (never on
    employer equipment, VPN or a remote session -- see BUILD-RELEASE.md L1).

.DESCRIPTION
    Mirrors the .github/workflows/ci.yml "test" and "build-windows" jobs,
    step by step, against a clean checkout of a known commit, then packs a
    deterministic OrbitRx-Setup-<VERSION>.zip with tools/pack_setup_zip.py.

    This script never uploads, publishes, tags or pushes anything, and never
    contacts any network host at all during the build (dependencies install
    from the committed, fully hash-pinned packaging/requirements-windows-build.lock.txt,
    not from a live index). It never auto-installs Python or Inno Setup -- if
    either is missing or fails a pin check, it stops with a clear message.

    -CiInventory is REQUIRED (L5): this script will not build without the
    exact SHA's ship-set-inventory.txt from CI. See BUILD-RELEASE.md.

    IMPORTANT: a run of this script is a DRY RUN unless Jamie has explicitly
    been told otherwise. Its zip is not a publish candidate by itself -- see
    BUILD-RELEASE.md's "Dry run" note and L10.

    Run from a fresh clone, as described in BUILD-RELEASE.md. PowerShell
    5.1 and 7 are both supported.

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

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Pure helpers (path guard, provenance PII check, inventory header parse,
# hash/pin helpers, SHA/attestation validation, publisher-check logic) live in
# a dot-sourced file so tests/test_build_release_local_pwsh.py can call them
# directly with pwsh. See tools/build_release_local.helpers.ps1.
. (Join-Path $PSScriptRoot 'build_release_local.helpers.ps1')

# --- Local helpers that need real processes/files (not pure, not dot-sourced)

function Invoke-Checked {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$FailureMessage)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

function Invoke-CheckedTee {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$FailureMessage, [string]$OutputFile)
    & $FilePath @ArgumentList 2>&1 | Tee-Object -FilePath $OutputFile
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
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
        if ($dll.DirectoryName -ne (Join-Path $Root '_internal')) {
            throw "$($prop.Name) is not at _internal\$($prop.Name)."
        }
        $fileVersion = "$($dll.VersionInfo.FileVersion)".Trim()
        $dllHash = Get-Sha256Hex $dll.FullName
        if ($fileVersion -ne $prop.Value.file_version) {
            throw "$($prop.Name) FileVersion $fileVersion != pinned $($prop.Value.file_version)."
        }
        if ($dllHash -ne $prop.Value.sha256) {
            throw "$($prop.Name) sha256 $dllHash != pinned $($prop.Value.sha256)."
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

$managedDeviceWarning = $null
$dsregcmdDomainJoined = 'not available'
$dsregcmdAzureAdJoined = 'not available'
$dsregcmdEnterpriseJoined = 'not available'
$dsregcmdWorkplaceJoined = 'not available'
if (Get-Command dsregcmd -ErrorAction SilentlyContinue) {
    $dsregLines = @(& dsregcmd /status)
    $dsregFlags = ConvertFrom-DsregcmdStatus -Lines $dsregLines
    if ($dsregFlags.ContainsKey('DomainJoined')) { $dsregcmdDomainJoined = $dsregFlags['DomainJoined'] }
    if ($dsregFlags.ContainsKey('AzureAdJoined')) { $dsregcmdAzureAdJoined = $dsregFlags['AzureAdJoined'] }
    if ($dsregFlags.ContainsKey('EnterpriseJoined')) { $dsregcmdEnterpriseJoined = $dsregFlags['EnterpriseJoined'] }
    if ($dsregFlags.ContainsKey('WorkplaceJoined')) { $dsregcmdWorkplaceJoined = $dsregFlags['WorkplaceJoined'] }
    $managedStatus = Test-ManagedDeviceStatus -Flags $dsregFlags
    if ($managedStatus.Refuse) {
        throw $managedStatus.Message
    }
    if ($managedStatus.Warning) {
        Write-Warning $managedStatus.Warning
        $managedDeviceWarning = $managedStatus.Warning
    }
    Write-Host "MANAGED-DEVICE-CHECK: PASS (DomainJoined=$dsregcmdDomainJoined AzureAdJoined=$dsregcmdAzureAdJoined EnterpriseJoined=$dsregcmdEnterpriseJoined WorkplaceJoined=$dsregcmdWorkplaceJoined)"
}
else {
    Write-Host "MANAGED-DEVICE-CHECK: dsregcmd not available, skipping (recorded as 'not available' in provenance)"
}

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
if ($installerSha256 -ne $pins.python.installer_sha256) {
    throw "Python installer sha256 $installerSha256 != pinned $($pins.python.installer_sha256) (packaging/local_build_pins.json)."
}
if ($installerMd5 -ne $pins.python.installer_md5) {
    throw "Python installer md5 $installerMd5 != pinned $($pins.python.installer_md5) (packaging/local_build_pins.json)."
}
$installerSig = Get-AuthenticodeSignature -FilePath $PythonInstaller
if ($installerSig.Status -ne 'Valid') {
    throw "Python installer Authenticode signature status is $($installerSig.Status), expected Valid."
}
if ($installerSig.SignerCertificate.Subject -notmatch [regex]::Escape($pins.python.authenticode_signer_subject_contains)) {
    throw "Python installer signer subject '$($installerSig.SignerCertificate.Subject)' does not contain '$($pins.python.authenticode_signer_subject_contains)'."
}
$installerSignerSubject = $installerSig.SignerCertificate.Subject
$installerSignerThumbprint = $installerSig.SignerCertificate.Thumbprint
Write-Host "PYTHON-INSTALLER-PIN: PASS (sha256=$installerSha256)"

if (-not (Test-Path $PythonExe)) {
    throw "-PythonExe not found: '$PythonExe'. Install python-3.12.10-amd64.exe for the current user yourself; this script does not install it."
}
$pythonExeSig = Get-AuthenticodeSignature -FilePath $PythonExe
if ($pythonExeSig.Status -ne 'Valid') {
    throw "python.exe Authenticode signature status is $($pythonExeSig.Status), expected Valid."
}
if ($pythonExeSig.SignerCertificate.Subject -notmatch [regex]::Escape($pins.python.authenticode_signer_subject_contains)) {
    throw "python.exe signer subject '$($pythonExeSig.SignerCertificate.Subject)' does not contain '$($pins.python.authenticode_signer_subject_contains)'."
}
$pythonExeSignerSubject = $pythonExeSig.SignerCertificate.Subject
$pythonExeSignerThumbprint = $pythonExeSig.SignerCertificate.Thumbprint
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

# --- e. Full pytest suite and compileall, exactly as CI's test job -----------

Push-Location $repoRoot
try {
    $env:QT_QPA_PLATFORM = 'offscreen'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'compileall', '-q', 'app.py', 'orbitrx') -FailureMessage 'compileall failed'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pytest', '-q') -FailureMessage 'pytest failed'
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

    $outDir = Join-Path $BuildRoot 'out'
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
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
    Write-Host "SHIP-SET-GATE: PASS"

    Invoke-PublisherCheck -Exes @($exePath, $installerExePath) -ExpectedAppVersion $version

    $peCheckOut = Join-Path $outDir 'installer-publisher.txt'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pe_check.py', $peCheckOut, $exePath, $installerExePath) -FailureMessage 'tools/pe_check.py failed'
    Write-Host "PE-CHECK: PASS"

    # N6: the same static PYZ scan CI's "Scan the bundled PYZ" step runs, so
    # the local gates catch the same simulated-rig-leak class of bug. CI's
    # runtime gates (screenshot capture, fit, units, DX cluster edges) are
    # NOT repeated here -- see BUILD-RELEASE.md for why, and rely on the CI
    # run at this exact SHA for those.
    $pyzScanOut = Join-Path $outDir 'pyz-scan.txt'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\scan_pyz.py', $exePath, $pyzScanOut) -FailureMessage 'tools/scan_pyz.py failed'
    Write-Host "PYZ-SCAN: PASS"
}
finally {
    Pop-Location
}

# --- i. Pack with the deterministic packer, L5/L6 checks, determinism check -

Push-Location $repoRoot
try {
    $commitEpoch = (git show -s --format=%ct $ExpectedSha).Trim()
    $zipName = "OrbitRx-Setup-$version.zip"
    $zipPath = Join-Path $outDir $zipName
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
finally {
    Pop-Location
}

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
if ($managedDeviceWarning) {
    $provenanceLines += "Managed-device warning: $managedDeviceWarning"
}
$provenanceLines += @(
    "Python installer: $($pins.python.installer_filename) sha256=$installerSha256 md5=$installerMd5 signer='$installerSignerSubject' thumbprint=$installerSignerThumbprint",
    "python.exe: sha256=$pythonExeSha256 version=$pyVersionString signer='$pythonExeSignerSubject' thumbprint=$pythonExeSignerThumbprint",
    "pip: $pipVersionLine",
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

# --- Reminders for the steps this script does not and should not do ----------

Write-Host ""
Write-Host "REMINDER: this is a DRY RUN unless you have been told otherwise -- do not publish this zip. Send the provenance record and the out\ files to QA/Risk under L10 and wait for their review before anything is treated as a publish candidate (see BUILD-RELEASE.md)."
Write-Host "REMINDER (L7): run the HTTPS smoke test by hand -- launch dist\OrbitRxMonitor\OrbitRxMonitor.exe and confirm a live SWPC fetch succeeds. Capture a screenshot or a short note (what you saw, and the timestamp) as L7 evidence. This script does not launch the app for you."
Write-Host "REMINDER: run an antivirus scan over dist\OrbitRxMonitor, the installer and the zip before sharing them."
Write-Host "REMINDER (L9): append exactly this one line to both SUMS locations -- do NOT touch the existing 5.1.0 line:"
Write-Host "$zipSha256  $zipName"
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
