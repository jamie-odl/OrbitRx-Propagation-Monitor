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

function Get-SubstDriveLetters {
    if (-not (Get-Command subst -ErrorAction SilentlyContinue)) { return @() }
    try {
        $out = & subst 2>$null
    }
    catch {
        return @()
    }
    $letters = @()
    foreach ($line in @($out)) {
        if ($line -match '^([A-Za-z]):\\?\s*=>') {
            $letters += $Matches[1].ToUpper()
        }
    }
    return $letters
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
    # Returns @{ Refuse = $bool; Message = ...; Warning = ... (or $null) }
    $joinKeys = @('DomainJoined', 'AzureAdJoined', 'EnterpriseJoined')
    $joined = @($joinKeys | Where-Object { $Flags.ContainsKey($_) -and $Flags[$_] -eq 'YES' })
    $result = [PSCustomObject]@{
        Refuse  = $joined.Count -gt 0
        Message = $null
        Warning = $null
    }
    if ($result.Refuse) {
        $result.Message = "This looks like a managed/employer device ($($joined -join ', ') = YES). L1 requires a personal kit; refusing to build here."
    }
    if ($Flags.ContainsKey('WorkplaceJoined') -and $Flags['WorkplaceJoined'] -eq 'YES') {
        $result.Warning = "WorkplaceJoined=YES: this PC is registered with a workplace account. Confirm this is still your own personal PC (L1) before continuing."
    }
    return $result
}
