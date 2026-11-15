<#
.SYNOPSIS
    Pure(r) helper functions for tools/build_release_local.ps1, split out so
    tests/test_build_release_local_pwsh.py can dot-source this file and call
    each function directly with pwsh, without running the whole build.

    Every function here avoids network access and avoids mutating anything
    outside of what its caller explicitly passes in (no writes to the real
    filesystem beyond reading paths the caller names). Functions that need a
    real file on disk (hashing, Get-Item for attributes) still only read.
#>

Set-StrictMode -Version Latest

# --- NEW-5: PowerShell version gate -------------------------------------------
# A pure boolean decision (no $PSVersionTable read here) so pwsh-driven tests
# can exercise the >=7 boundary with synthetic major-version numbers, without
# needing an actual Windows PowerShell 5.1 engine to run it on.

function Test-PowerShellVersionSupported {
    param([int]$MajorVersion)
    return $MajorVersion -ge 7
}

# --- Hash / pin comparison helpers -------------------------------------------

function Get-Sha256Hex {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLower()
}

function Get-Md5Hex {
    param([string]$Path)
    return (Get-FileHash -Path $Path -Algorithm MD5).Hash.ToLower()
}

function Assert-Sha256Match {
    param([string]$Path, [string]$Expected, [string]$Label)
    $actual = Get-Sha256Hex $Path
    if ($actual -ne $Expected) {
        throw "$Label sha256 $actual != pinned $Expected."
    }
    return $actual
}

# P6: both the sha256 AND the md5 of the Python installer must match the
# pin -- pulled out as its own function (taking already-computed hash
# strings, not a path) so a test can assert the md5 half of this check
# fires even when sha256 alone would already have failed first.

function Assert-PythonInstallerHashesMatch {
    param([string]$Sha256, [string]$Md5, [psobject]$PythonPin)
    if ($Sha256 -ne $PythonPin.installer_sha256) {
        throw "Python installer sha256 $Sha256 != pinned $($PythonPin.installer_sha256) (packaging/local_build_pins.json)."
    }
    if ($Md5 -ne $PythonPin.installer_md5) {
        throw "Python installer md5 $Md5 != pinned $($PythonPin.installer_md5) (packaging/local_build_pins.json)."
    }
}

# P8: shared by both the installer's and python.exe's Authenticode checks,
# taking a signature-status object (as Get-AuthenticodeSignature would
# return) rather than a path, so tests can exercise both the Status and the
# signer-subject half of this check with synthetic objects -- no real
# Authenticode-signed binary required.

function Assert-AuthenticodeSignatureValid {
    param([psobject]$Signature, [string]$Label, [string]$SignerSubjectContains)
    if ($Signature.Status -ne 'Valid') {
        throw "$Label Authenticode signature status is $($Signature.Status), expected Valid."
    }
    if ($Signature.SignerCertificate.Subject -notmatch [regex]::Escape($SignerSubjectContains)) {
        throw "$Label signer subject '$($Signature.SignerCertificate.Subject)' does not contain '$SignerSubjectContains'."
    }
}

# P8c2: the main script's single call site for both of the above, taking
# both already-retrieved signature objects by name. Pulling this into one
# function (rather than two separate call-site statements) means a mutant
# that feeds the python.exe check $InstallerSignature a second time instead
# of $PythonExeSignature can be caught by calling this function directly
# with a good installer signature and a bad python.exe signature.

function Assert-PythonAndInstallerSignaturesValid {
    param([psobject]$InstallerSignature, [psobject]$PythonExeSignature, [string]$SignerSubjectContains)
    Assert-AuthenticodeSignatureValid -Signature $InstallerSignature -Label 'Python installer' -SignerSubjectContains $SignerSubjectContains
    Assert-AuthenticodeSignatureValid -Signature $PythonExeSignature -Label 'python.exe' -SignerSubjectContains $SignerSubjectContains
}

# P12: the per-DLL half of the OpenSSL ship-set pin check (directory,
# FileVersion, sha256), taking already-computed values rather than a real
# file on disk, so a test can assert the sha256 half specifically fires
# even when the other two would pass.

function Get-OpenSslDllPinProblems {
    param([string]$DllName, [string]$DirectoryName, [string]$ExpectedDirectory, [string]$FileVersion, [string]$Sha256, [psobject]$PinEntry)
    $problems = @()
    if ($DirectoryName -ne $ExpectedDirectory) {
        $problems += "$DllName is not at _internal\$DllName."
    }
    if ($FileVersion -ne $PinEntry.file_version) {
        $problems += "$DllName FileVersion $FileVersion != pinned $($PinEntry.file_version)."
    }
    if ($Sha256 -ne $PinEntry.sha256) {
        $problems += "$DllName sha256 $Sha256 != pinned $($PinEntry.sha256)."
    }
    return $problems
}

# --- Attestation / SHA argument validation -----------------------------------

function Assert-ValidExpectedSha {
    param([string]$Sha)
    if (-not $Sha -or $Sha -notmatch '^[0-9a-fA-F]{40}$') {
        throw "-ExpectedSha is required and must be a full 40-hex commit SHA."
    }
    return $Sha.ToLower()
}

function Assert-PersonalKitAttested {
    param([bool]$Attested)
    if (-not $Attested) {
        throw "AttestPersonalKit must be passed: run this only after confirming the build is on your own personal PC, not employer equipment, VPN or a remote session (BUILD-RELEASE.md L1)."
    }
}

# --- Ship-set-inventory.txt header parse (R1) --------------------------------

function Get-ShipSetInventoryHeader {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "-CiInventory file not found: '$Path'."
    }
    $firstLine = Get-Content -LiteralPath $Path -TotalCount 1
    if ($firstLine -notmatch '^version=(?<version>\S+)\s+commit=(?<commit>[0-9a-fA-F]{40})$') {
        throw "CiInventory header line '$firstLine' does not match 'version=<v> commit=<40-hex-sha>' (file: $Path)."
    }
    return [PSCustomObject]@{
        Version = $Matches['version']
        Commit  = $Matches['commit'].ToLower()
    }
}

function Assert-CiInventoryMatchesBuild {
    param([psobject]$Header, [string]$ExpectedSha, [string]$ExpectedVersion)
    if ($Header.Commit -ne $ExpectedSha.ToLower()) {
        throw "-CiInventory commit ($($Header.Commit)) does not match -ExpectedSha ($($ExpectedSha.ToLower()))."
    }
    if ($Header.Version -ne $ExpectedVersion) {
        throw "-CiInventory version ($($Header.Version)) does not match -ExpectedVersion ($ExpectedVersion)."
    }
}

# --- Provenance PII self-check -----------------------------------------------

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

# --- R-c: console/out\ redaction of this PC's identity -----------------------
# Unlike Get-ProvenanceUnsafeMarkers above (which fails the build closed if a
# marker slips into the provenance record), this is a best-effort rewrite
# applied to ordinary console output and gate-output text files, which are
# expected to exist and be read even on a dry run.

function Format-RedactedText {
    param([string]$Text)
    if ($null -eq $Text) { return $Text }

    # USERPROFILE/LOCALAPPDATA/APPDATA/TEMP all map to <profile>, each
    # matched by its own literal value (a redirected profile can make these
    # differ rather than nest under USERPROFILE) regardless of length -- an
    # empty value is skipped outright, since PowerShell's -replace with an
    # empty pattern matches between every character. USERNAME/COMPUTERNAME
    # map to <user>/<host>; below 3 characters they are too easy to collide
    # with ordinary text, so those are only redacted as a whole \name\ or
    # /name/ path segment.
    $entries = @()
    foreach ($value in @($env:USERPROFILE, $env:LOCALAPPDATA, $env:APPDATA, $env:TEMP)) {
        if ($value) {
            $entries += [PSCustomObject]@{ Value = $value; With = '<profile>'; WholeSegmentOnly = $false }
        }
    }
    if ($env:USERNAME) {
        $entries += [PSCustomObject]@{ Value = $env:USERNAME; With = '<user>'; WholeSegmentOnly = ($env:USERNAME.Length -lt 3) }
    }
    if ($env:COMPUTERNAME) {
        $entries += [PSCustomObject]@{ Value = $env:COMPUTERNAME; With = '<host>'; WholeSegmentOnly = ($env:COMPUTERNAME.Length -lt 3) }
    }

    $result = $Text
    # Longest value first, so a longer, more specific match (e.g. a
    # redirected LOCALAPPDATA) is consumed before a shorter one (e.g.
    # USERPROFILE) that might otherwise overlap it.
    foreach ($entry in ($entries | Sort-Object { $_.Value.Length } -Descending)) {
        $pattern = [regex]::Escape($entry.Value)
        if ($entry.WholeSegmentOnly) {
            $pattern = '(?<=[\\/])' + $pattern + '(?=[\\/])'
        }
        $result = $result -replace $pattern, $entry.With
    }
    return $result
}

# --- Path guard (N4): OneDrive, Desktop, reparse points, subst/UNC ----------

function Resolve-FullBuildPath {
    param([string]$Path, [string]$WorkingDirectory)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [IO.Path]::IsPathRooted($expanded)) {
        $base = if ($WorkingDirectory) { $WorkingDirectory } else { (Get-Location).Path }
        $expanded = [IO.Path]::GetFullPath((Join-Path $base $expanded))
    }
    else {
        $expanded = [IO.Path]::GetFullPath($expanded)
    }
    # Walk up to the nearest existing ancestor and ask Get-Item for its
    # long-path / 8.3-expanded FullName, then re-append the non-existing tail.
    $probe = $expanded
    $tail = @()
    while ($probe -and -not (Test-Path -LiteralPath $probe)) {
        $parent = Split-Path $probe -Parent
        if (-not $parent -or $parent -eq $probe) { break }
        $tail = @((Split-Path $probe -Leaf)) + $tail
        $probe = $parent
    }
    if (Test-Path -LiteralPath $probe) {
        $probeFull = (Get-Item -LiteralPath $probe -Force).FullName
        $expanded = if ($tail.Count -gt 0) { Join-Path $probeFull ($tail -join [IO.Path]::DirectorySeparatorChar) } else { $probeFull }
    }
    return $expanded
}

function Test-PathHasReparsePointAncestor {
    param([string]$Path)
    $current = $Path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                return $true
            }
        }
        $parent = Split-Path $current -Parent
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
    return $false
}

function ConvertFrom-SubstOutput {
    # subst with no arguments lists each mapping as "<letter>:\: => <path>"
    # (the colon appears both before and after the backslash); the pattern
    # below also accepts "<letter>: => <path>" in case some locale or
    # Windows build drops the backslash or the second colon.
    param([string[]]$Lines)
    $letters = @()
    foreach ($line in @($Lines)) {
        if ($line -match '^([A-Za-z]):\\?:?\s*=>') {
            $letters += $Matches[1].ToUpper()
        }
    }
    return $letters
}

function Get-SubstDriveLetters {
    if (-not (Get-Command subst -ErrorAction SilentlyContinue)) { return @() }
    try {
        $out = & subst 2>$null
    }
    catch {
        return @()
    }
    return ConvertFrom-SubstOutput -Lines $out
}

function Test-SubstOrNetworkDrivePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if ($Path.StartsWith('\\')) { return $true }  # UNC, including \\?\UNC\
    if ($Path -match '^([A-Za-z]):') {
        $letter = $Matches[1].ToUpper()
        if ((Get-SubstDriveLetters) -contains $letter) { return $true }
        if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
            try {
                $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='${letter}:'" -ErrorAction Stop
                if ($disk -and $disk.DriveType -eq 4) { return $true }
            }
            catch {
                # Win32_LogicalDisk unavailable (non-Windows test host); the
                # subst-list check above already ran.
            }
        }
    }
    return $false
}

function Test-OneDriveOrDesktopPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    $candidates = @()
    foreach ($envVar in @($env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial)) {
        if ($envVar) { $candidates += $envVar }
    }
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        if ($desktop) { $candidates += $desktop }
    }
    catch { }
    if ($env:USERPROFILE) { $candidates += (Join-Path $env:USERPROFILE 'Desktop') }
    foreach ($c in $candidates) {
        if ($Path.StartsWith($c, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($segment in ($Path -split '[\\/]')) {
        $trimmed = $segment.TrimEnd(' ', '.')
        if ($trimmed -ilike 'OneDrive*') { return $true }
        if ($trimmed -ieq 'Desktop') { return $true }
    }
    return $false
}

function Assert-SafeBuildPath {
    param([string]$Path, [string]$Label, [string]$WorkingDirectory)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label is empty."
    }
    $full = Resolve-FullBuildPath -Path $Path -WorkingDirectory $WorkingDirectory
    if (Test-SubstOrNetworkDrivePath -Path $full) {
        throw "$Label ('$full') is on a subst/mapped drive or a UNC network path. Use a plain local folder on a real local drive instead (see BUILD-RELEASE.md)."
    }
    if (Test-PathHasReparsePointAncestor -Path $full) {
        throw "$Label ('$full') has a reparse point (junction or symlink) somewhere in its ancestry. Use a plain local folder instead (see BUILD-RELEASE.md)."
    }
    if (Test-OneDriveOrDesktopPath -Path $full) {
        throw "$Label ('$full') is under OneDrive or Desktop. Use a plain local folder instead (see BUILD-RELEASE.md)."
    }
    return $full
}

function Assert-BuildRootOutsideUserProfile {
    param([string]$BuildRootFull)
    if ($env:USERPROFILE) {
        $profileFull = [IO.Path]::GetFullPath($env:USERPROFILE)
        if ($BuildRootFull.StartsWith($profileFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "-BuildRoot ('$BuildRootFull') is under `$env:USERPROFILE ('$profileFull'). Use a BuildRoot outside your user profile (e.g. C:\build\...) -- the provenance self-check at the end would otherwise fail because your username/profile path would leak into it."
        }
    }
}

# --- Publisher-check logic (on a versioninfo-like object) -------------------

function Test-PublisherVersionInfo {
    param([psobject]$VersionInfo, [string]$ExpectedAppVersion, [string]$Label)
    $problems = @()
    $companyAndCopyright = "$($VersionInfo.CompanyName) $($VersionInfo.LegalCopyright)"
    if ($companyAndCopyright -match 'Obsidian') {
        $problems += "Obsidian Dynamics found in $Label version info."
    }
    if ("$($VersionInfo.CompanyName)".Trim() -ne 'thevenom') {
        $problems += "Unexpected CompanyName in $Label."
    }
    $fileVersion = "$($VersionInfo.FileVersion)".Trim()
    if ($fileVersion -ne $ExpectedAppVersion -and $fileVersion -ne "$ExpectedAppVersion.0") {
        $problems += "Unexpected FileVersion '$fileVersion' in $Label (expected $ExpectedAppVersion or $ExpectedAppVersion.0)."
    }
    return $problems
}

# --- Employer/managed-device heuristic (N9) ----------------------------------

function ConvertFrom-DsregcmdStatus {
    param([string[]]$Lines)
    $flags = @{}
    foreach ($line in $Lines) {
        if ($line -match '^\s*(?<name>AzureAdJoined|EnterpriseJoined|DomainJoined|WorkplaceJoined)\s*:\s*(?<value>YES|NO)\s*$') {
            $flags[$Matches['name']] = $Matches['value']
        }
    }
    return $flags
}

function Test-ManagedDeviceStatus {
    param([hashtable]$Flags)
    # Returns @{ Refuse = $bool; Message = ... (or $null) }
    # Risk round R-a: WorkplaceJoined=YES used to only warn; it now refuses
    # like the other three flags -- a workplace/school account on this PC
    # means it is not a personal kit, full stop.
    $joinKeys = @('DomainJoined', 'AzureAdJoined', 'EnterpriseJoined', 'WorkplaceJoined')
    $joined = @($joinKeys | Where-Object { $Flags.ContainsKey($_) -and $Flags[$_] -eq 'YES' })
    $result = [PSCustomObject]@{
        Refuse  = $joined.Count -gt 0
        Message = $null
    }
    if ($result.Refuse) {
        $result.Message = "This PC has a work/school account or is managed ($($joined -join ', ') = YES). L1 requires personal kit. Stop and tell Risk."
    }
    return $result
}
