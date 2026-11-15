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

# --- NEW-5/I-1: PowerShell version gate ---------------------------------------
# A pure boolean decision (no $PSVersionTable read here) so pwsh-driven tests
# can exercise the >=7.4 boundary with synthetic [version] objects, without
# needing an actual Windows PowerShell 5.1 (or 7.0-7.3) engine to run it on.
# I-1: the floor is the full version 7.4, not just major version 7 -- every
# 7.x release below 7.4 (7.0, 7.1, 7.2, 7.3) must refuse too, to match CI's
# own pwsh version and this script's #Requires/inline-check floor.

function Test-PowerShellVersionSupported {
    param([version]$Version)
    return $Version -ge [version]'7.4'
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

# --- Employer/managed-device heuristic (N9, Risk R3 Ruling 2 / L-B) ---------

function ConvertFrom-DsregcmdStatus {
    param([string[]]$Lines)
    # Returns a hashtable of canonical key name -> 'YES' / 'NO' / 'UNVERIFIED'.
    # A key with no occurrences anywhere in $Lines is left out of the
    # hashtable entirely -- Test-ManagedDeviceStatus treats a missing key
    # the same as an UNVERIFIED one (fewer than all 4 keys parsed).
    #
    # Both failure modes are sticky across repeated/duplicate lines for the
    # same key, so a later line can never quietly clear an earlier one:
    #   - once a key sees an exact 'YES' (case-insensitive, trimmed), it
    #     stays 'YES' no matter what later lines for that key say -- the
    #     old "last value wins" behaviour let a later 'NO' line erase an
    #     earlier 'YES', which is exactly the fail-open bug L-B closes.
    #   - once a key sees a value that is anything other than exactly YES
    #     or NO (tabs/whitespace tolerated, but e.g. 'YES (Contoso)' or a
    #     localised word do not count), it is pinned to 'UNVERIFIED' and a
    #     later clean 'NO' line cannot clear that either.
    # Key matching is case-insensitive (PowerShell's -match already is) and
    # tolerant of tabs/CRLF (`\s` in the key/value pattern, plus an
    # explicit `\r` strip below for lines that arrive as a single
    # CRLF-joined blob rather than a pre-split array).
    $canonicalNames = @('WorkplaceJoined', 'AzureAdJoined', 'DomainJoined', 'EnterpriseJoined')
    $resolved = @{}
    foreach ($rawLine in $Lines) {
        $line = "$rawLine" -replace "`r", ''
        if ($line -match '^\s*(?<name>WorkplaceJoined|AzureAdJoined|DomainJoined|EnterpriseJoined)\s*:\s*(?<value>.*?)\s*$') {
            $canonicalName = $canonicalNames | Where-Object { $_ -ieq $Matches['name'] } | Select-Object -First 1
            $value = $Matches['value'].Trim()
            if ($value -ieq 'YES') {
                $resolved[$canonicalName] = 'YES'
            }
            elseif ($resolved[$canonicalName] -ne 'YES') {
                if ($value -ieq 'NO') {
                    if ($resolved[$canonicalName] -ne 'UNVERIFIED') {
                        $resolved[$canonicalName] = 'NO'
                    }
                }
                else {
                    $resolved[$canonicalName] = 'UNVERIFIED'
                }
            }
        }
    }
    return $resolved
}

function Test-ManagedDeviceStatus {
    param([hashtable]$Flags)
    # Returns @{ Refuse = $bool; Message = ... (or $null) }
    # Risk R3 Ruling 2 (L-B): refuse (UNVERIFIED means refuse) when any of
    # the 4 flags is YES anywhere (rule 1, checked first and named
    # specifically), or when fewer than all 4 keys parsed to exactly YES or
    # NO (rules 3/4 -- ConvertFrom-DsregcmdStatus already turns a garbled
    # value into 'UNVERIFIED', and a key missing from $Flags entirely reads
    # as $null here, which is neither 'YES' nor 'NO'). Rules 2 (non-zero
    # exit / empty output) and 5 (dsregcmd missing on Windows) are checked
    # by the call site before this function is even reached.
    # WorkplaceJoined is included because a work/school account on this PC
    # fails L1, whoever owns the hardware.
    # No override: no switch, parameter, environment variable or config
    # anywhere in this script bypasses or downgrades this function's
    # verdict; -AttestPersonalKit (Assert-PersonalKitAttested) is a
    # required attestation in addition to this check, never a substitute.
    $joinKeys = @('DomainJoined', 'AzureAdJoined', 'EnterpriseJoined', 'WorkplaceJoined')
    $yesKeys = @($joinKeys | Where-Object { $Flags[$_] -eq 'YES' })
    $unverifiedKeys = @($joinKeys | Where-Object { $Flags[$_] -ne 'YES' -and $Flags[$_] -ne 'NO' })
    $result = [PSCustomObject]@{
        Refuse  = ($yesKeys.Count -gt 0) -or ($unverifiedKeys.Count -gt 0)
        Message = $null
    }
    if ($yesKeys.Count -gt 0) {
        # Recording (Ruling 2): name only the flag(s), never DeviceId/
        # TenantName/TenantId -- $Flags only ever holds 'YES'/'NO'/
        # 'UNVERIFIED' for these 4 keys, so there is nothing else to leak.
        $result.Message = "This PC has a work/school account or is managed ($($yesKeys -join ', ') = YES). L1 requires personal kit. Stop and tell Risk."
    }
    elseif ($unverifiedKeys.Count -gt 0) {
        $result.Message = "MANAGED-DEVICE-CHECK: UNVERIFIED ($($unverifiedKeys -join ', ') could not be read as exactly YES or NO). L1 requires a verified personal-kit check. Stop and tell Risk."
    }
    return $result
}
