<#
.SYNOPSIS
    Build the OrbitRx 5.2.0 local candidate on Jamie's own PC (never on
    employer equipment, VPN or a remote session -- see BUILD-RELEASE.md L1).

.DESCRIPTION
    Mirrors the .github/workflows/ci.yml "test" and "build-windows" jobs,
    step by step, against a clean checkout of a known commit, then packs a
    deterministic OrbitRx-Setup-5.2.0.zip with tools/pack_setup_zip.py.

    This script never uploads, publishes, tags or pushes anything, and never
    contacts any network host other than pip's package index during
    "pip install". It never auto-installs Python or Inno Setup -- if either
    is missing or fails a pin check, it stops with a clear message.

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
    stays clean). Must not be under OneDrive or Desktop either.

.PARAMETER Constraints
    Optional hash-pinned requirements file. If given, installs with
    "pip install --require-hashes -r Constraints" instead of requirements.txt.

.PARAMETER Iscc
    Path to Inno Setup 6's ISCC.exe. Never installed by this script.

.PARAMETER CiInventory
    Optional path to the ship-set-inventory.txt downloaded from the exact
    SHA's CI run (release-exe-captures artifact). Enforces L5 if given.

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
    [string]$Constraints,
    [string]$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [string]$CiInventory,
    [switch]$AttestPersonalKit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --- Helpers -----------------------------------------------------------------

function Test-OneDriveOrDesktopPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    foreach ($envVar in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
        if ($envVar -and $Path.StartsWith($envVar, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop -and $Path.StartsWith($desktop, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    foreach ($segment in ($Path -split '[\\/]')) {
        if ($segment -ieq 'OneDrive') { return $true }
        if ($segment -ieq 'Desktop') { return $true }
    }
    return $false
}

function Assert-SafeBuildPath {
    param([string]$Path, [string]$Label)
    if (Test-OneDriveOrDesktopPath $Path) {
        throw "$Label ('$Path') is under OneDrive or Desktop. Use a plain local folder instead (see BUILD-RELEASE.md)."
    }
}

function Get-Sha256Hex {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower()
}

function Get-Md5Hex {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm MD5).Hash.ToLower()
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$ArgumentList, [string]$FailureMessage)
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

function Get-ProvenanceUnsafeMarkers {
    param([string]$Text)
    $found = @()
    foreach ($var in @($env:USERNAME, $env:COMPUTERNAME, $env:USERPROFILE, $env:HOME)) {
        if ($var -and $var.Trim().Length -gt 0 -and $Text.ToLower().Contains($var.ToLower())) {
            $found += $var
        }
    }
    # Simplified UK postcode pattern: one or two letters, a digit, an
    # optional letter or digit, optional whitespace, a digit, two letters.
    if ($Text -match '(?i)\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b') {
        $found += 'UK-postcode-pattern'
    }
    return $found
}

# --- a. Refuse to run from a forbidden location -------------------------------

if (-not $AttestPersonalKit) {
    throw "AttestPersonalKit must be passed: run this only after confirming the build is on your own personal PC, not employer equipment, VPN or a remote session (BUILD-RELEASE.md L1)."
}

$buildStartUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Assert-SafeBuildPath -Path $repoRoot -Label 'Repo root'
Assert-SafeBuildPath -Path $BuildRoot -Label 'Build root (-BuildRoot)'

Write-Host "Repo root: $repoRoot"
Write-Host "Build root: $BuildRoot"

# --- b. Clean clone at the exact expected SHA ---------------------------------

if (-not $ExpectedSha -or $ExpectedSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw "-ExpectedSha is required and must be a full 40-hex commit SHA."
}
$ExpectedSha = $ExpectedSha.ToLower()

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
    $dllHash = Get-Sha256Hex $dllPath
    $pinEntry = $opensslPin.dlls.$dllName
    if ($dllHash -ne $pinEntry.sha256) {
        throw "$dllName sha256 $dllHash != manifest pin $($pinEntry.sha256)."
    }
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

# --- d. Fresh venv in BuildRoot, install requirements.txt as CI does ----------

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
$constraintsSha256 = $null
if ($Constraints) {
    if (-not (Test-Path $Constraints)) {
        throw "-Constraints file not found: '$Constraints'."
    }
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pip', 'install', '--require-hashes', '-r', $Constraints) -FailureMessage 'pip install --require-hashes failed'
    $constraintsSha256 = Get-Sha256Hex $Constraints
}
else {
    Invoke-Checked -FilePath $venvPython -ArgumentList @('-m', 'pip', 'install', '-r', $requirementsPath) -FailureMessage 'pip install -r requirements.txt failed'
}

$pipFreezeText = (& $venvPython -m pip freeze) -join "`n"
$pipFreezeBytes = [System.Text.Encoding]::UTF8.GetBytes($pipFreezeText)
$pipFreezeSha256 = [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($pipFreezeBytes)).Replace('-', '').ToLower()
Write-Host "DEPENDENCIES: PASS (requirements.txt sha256=$requirementsSha256, pip freeze sha256=$pipFreezeSha256)"

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
        if ("$($versionInfo.CompanyName) $($versionInfo.LegalCopyright)" -match 'Obsidian') {
            throw "Obsidian Dynamics found in $exePath version info."
        }
        if ("$($versionInfo.CompanyName)".Trim() -ne 'thevenom') {
            throw "Unexpected CompanyName in $exePath."
        }
        $fileVersion = "$($versionInfo.FileVersion)".Trim()
        if ($fileVersion -ne $ExpectedAppVersion -and $fileVersion -ne "$ExpectedAppVersion.0") {
            throw "Unexpected FileVersion '$fileVersion' in $exePath (expected $ExpectedAppVersion or $ExpectedAppVersion.0)."
        }
    }
    Write-Host "PUBLISHER-CHECK: PASS"
}

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
    if (-not $CiInventory) {
        Write-Warning "L5 is NOT yet satisfied: no -CiInventory was given. The packed zip's OrbitRxMonitor/ contents will not be compared against the exact SHA's CI ship-set-inventory.txt. Do this before any upload."
    }

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
}
finally {
    Pop-Location
}

# --- i. Pack with the deterministic packer, L6 checks, determinism self-check -

Push-Location $repoRoot
try {
    $commitEpoch = (git show -s --format=%ct $ExpectedSha).Trim()
    $zipPath = Join-Path $outDir 'OrbitRx-Setup-5.2.0.zip'
    $packArgs = @(
        'tools\pack_setup_zip.py',
        '--onedir', $onedirRoot,
        '--installer', $installerExePath,
        '--out', $zipPath,
        '--epoch', $commitEpoch
    )
    if ($CiInventory) {
        $packArgs += @('--expect-inventory', $CiInventory)
    }
    Invoke-Checked -FilePath $venvPython -ArgumentList $packArgs -FailureMessage 'deterministic pack failed (if -CiInventory was given, this may be an L5 mismatch)'
    if ($CiInventory) {
        Write-Host "L5-INVENTORY-MATCH: PASS"
    }

    $extractDir = Join-Path $outDir 'extracted'
    if (Test-Path $extractDir) {
        Remove-Item -Recurse -Force $extractDir
    }
    Expand-Archive -Path $zipPath -DestinationPath $extractDir
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\ship_set.py', '--check', (Join-Path $extractDir 'OrbitRxMonitor')) -FailureMessage 'L6: ship_set --check failed on the extracted zip'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--verify', $zipPath, '--onedir', $onedirRoot, '--installer', $installerExePath, '--epoch', $commitEpoch) -FailureMessage 'L6: packer --verify failed'
    Write-Host "L6-PRE-UPLOAD-CHECK: PASS"

    $extractedOnedir = Join-Path $extractDir 'OrbitRxMonitor'
    Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--compare-tree', $extractedOnedir, '--inventory', $localInventoryPath) -FailureMessage 'L6: extracted zip tree did not match the local ship-set-inventory.txt'
    if ($CiInventory) {
        Invoke-Checked -FilePath $venvPython -ArgumentList @('tools\pack_setup_zip.py', '--compare-tree', $extractedOnedir, '--inventory', $CiInventory) -FailureMessage 'L6: extracted zip tree did not match -CiInventory'
    }
    Write-Host "L6-INVENTORY-MATCH: PASS"

    $zipPathRepeat = Join-Path $outDir 'OrbitRx-Setup-5.2.0.repack-check.zip'
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

Write-Host ""
Write-Host "OrbitRxMonitor.exe sha256: $exeSha256"
Write-Host "OrbitRxMonitor-Setup.exe sha256: $installerSha256Final"
Write-Host "onedir file count: $onedirFileCount"
Write-Host "zip sha256: $zipSha256"
Write-Host "zip size: $zipSize bytes"

$l5Line = if ($CiInventory) { '  L5-INVENTORY-MATCH: PASS' } else { '  L5-INVENTORY-MATCH: NOT RUN (no -CiInventory given)' }

$provenanceLines = @(
    'OrbitRx 5.2.0 local build provenance',
    "SHA: $ExpectedSha",
    "tree: $headTree",
    "VERSION: $version",
    "Build start (UTC): $buildStartUtc",
    "Build end (UTC): $buildEndUtc",
    'Built on personal PC, not employer equipment (attested by builder)',
    "Python installer: $($pins.python.installer_filename) sha256=$installerSha256 md5=$installerMd5 signer contains '$($pins.python.authenticode_signer_subject_contains)'",
    "python.exe: sha256=$pythonExeSha256 version=$pyVersionString",
    "pip: $pipVersionLine",
    "requirements.txt sha256: $requirementsSha256"
)
if ($constraintsSha256) {
    $provenanceLines += "constraints file sha256: $constraintsSha256"
}
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
    $l5Line,
    '  L6-PRE-UPLOAD-CHECK: PASS',
    '  L6-INVENTORY-MATCH: PASS',
    '  DETERMINISM-SELF-CHECK: PASS',
    '',
    "OrbitRxMonitor.exe sha256: $exeSha256",
    "OrbitRxMonitor-Setup.exe sha256: $installerSha256Final",
    "onedir file count: $onedirFileCount",
    "zip sha256: $zipSha256",
    "zip size: $zipSize bytes",
    'zip path: out\OrbitRx-Setup-5.2.0.zip'
)
$provenanceText = ($provenanceLines -join "`r`n")

$unsafeMarkers = Get-ProvenanceUnsafeMarkers -Text $provenanceText
if ($unsafeMarkers.Count -gt 0) {
    throw "Provenance text self-check failed: it contains $($unsafeMarkers -join ', '). Refusing to write it."
}

$provenancePath = Join-Path $outDir 'OrbitRx-5.2.0-PROVENANCE.txt'
Set-Content -Path $provenancePath -Value $provenanceText -Encoding utf8
Write-Host ""
Write-Host "Wrote provenance record: $provenancePath"

# --- Reminders for the steps this script does not and should not do ----------

Write-Host ""
Write-Host "REMINDER (L7): run the HTTPS smoke test by hand -- launch dist\OrbitRxMonitor\OrbitRxMonitor.exe and confirm a live SWPC fetch succeeds. This script does not launch the app for you."
Write-Host "REMINDER: run an antivirus scan over dist\OrbitRxMonitor, the installer and the zip before sharing them."
Write-Host "REMINDER (L9): append exactly this one line to both SUMS locations -- do NOT touch the existing 5.1.0 line:"
Write-Host "$zipSha256  OrbitRx-Setup-5.2.0.zip"
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
