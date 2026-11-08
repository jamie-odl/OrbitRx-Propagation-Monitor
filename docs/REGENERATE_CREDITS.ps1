
# REGENERATE_CREDITS.ps1 -- canonical regeneration path for
# chromium_attributions.qdoc, matching the Windows/MSVC build that
# actually produced OrbitRx's shipped PySide6-WebEngine binaries.
#
# WHY WINDOWS/MSVC IS REQUIRED HERE (not just "allowed"):
#   The captured production GN-args log for :QtWebEngineCore
#   (third_party/qt/qtwebengine-core-gn-log.txt, from GitHub Actions run
#   42476475449) shows is_msvc=true. qtwebengine's src/core/CMakeLists.txt
#   also has several extend_gn_target(${buildGn} CONDITION WIN32 ...)
#   branches (e.g. the generic WIN32 block and the "WIN32 AND
#   QT_FEATURE_opengl" block) that add GN args/target closure ONLY when
#   CMake is actually configuring for Windows. That condition is driven by
#   CMake's own WIN32 platform variable, which is only true when CMake is
#   really running against a Windows target with a real toolchain -- it
#   is not something you can fake by passing target_os="win" to GN on a
#   Linux host. Reproducing the exact production target closure (and
#   therefore the exact credits content) requires actually running this
#   on Windows with MSVC installed. See docs/REGENERATE_CREDITS.sh for the
#   full mechanism writeup (cmake/QtGnCredits.cmake -> licenses.py credits
#   mode, requires a real `gn gen`'d out dir for :QtWebEngineCore).
#
# WHY THE QT HOST TOOLCHAIN IS A DIRECT, SHA1-VERIFIED DOWNLOAD (NOT aqt):
#   aqtinstall's module/arch arguments do not map onto a single fixed
#   Updates.xml path -- for Qt 6.12.0 desktop MSVC2022/64 the real listing
#   lives at
#     https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/qt6_6120_msvc2022_64/Updates.xml
#   not .../qt6_6120/qt6_6120/Updates.xml (the path aqtinstall 3.3.0 guessed
#   in run 42500822771, which 404s -- see evidence/desktop-sub.txt and
#   evidence/credits-regen-42500822771.json). Rather than pin another
#   guessed aqt invocation, this script downloads that same Updates.xml,
#   reads the real archive names and their per-archive .sha1 sidecars out
#   of it, and extracts only the archives qtwebengine's configure actually
#   needs with 7z (preinstalled on GitHub's windows-latest runners).
#
# EXPECTED RUNTIME / DISK (Windows runner with Visual Studio Build Tools
# + Windows SDK already installed -- if not, add 15-30 min and ~8-15GB
# for that install):
#   - Download tarball (580,351,144 bytes):                     2-10 min
#   - Extract (298,124 entries):                                 3-10 min
#   - Official Qt 6.12.0 host archives (win64_msvc2022_64,
#     qtbase+qtdeclarative+qttools+qtshadertools+qtwebchannel+
#     qtpositioning, sha1-verified, 7z-extracted):                2-6 min
#   - Bootstrap vendored `gn` tool under MSVC:                    3-8 min
#   - qt-configure-module + `gn gen` for :QtWebEngineCore
#     (graph evaluation only, no chromium compile):               8-25 min
#   - licenses.py credits scan:                                   1-4 min
#   Total: roughly 20-55 minutes (plus toolchain install if needed).
#   Disk: tarball + extracted tree (~6-8GB) + Qt host archives (~1GB) +
#   gn tool build (~1GB) + GN-generated files for GnDone only (~1-2GB).
#   Budget 15-20GB free.
#
# EXIT CRITERIA: script exits with non-zero only if chromium_attributions.qdoc
# was not produced or is empty. The args.gn fidelity check (Step 7) is
# informational -- a WARN does not abort the script but means the result
# must be reviewed before being treated as final.
#
# NO UPLOADS. NO APP REPO. Everything stays under $WorkDir.

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Fixed, verified inputs
# ---------------------------------------------------------------------------
$TarballUrl    = "https://download.qt.io/development_releases/qtwebengine/6.140.0-rc/qtwebengine-everywhere-src-6.140.0-rc.tar.xz"
$TarballName   = "qtwebengine-everywhere-src-6.140.0-rc.tar.xz"
$TarballSha256 = "61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621"
$TarballBytes  = 580351144
$OldCreditsSha256 = "b2382a81239e6c100a3f96342909c6c7e7ecec12fb93e6fe91a5aa3bf756c0ec"
$QtHostVersion = "6.12.0"
$SrcTopDir     = "qtwebengine-everywhere-src-6.140.0"

# Qt's official repository layout for this host toolchain (verified against
# https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/qt6_6120_msvc2022_64/Updates.xml,
# see evidence/Updates-qt6_6120_msvc2022_64.xml). This is NOT the layout
# aqtinstall 3.3.0 guessed (qt6_6120/qt6_6120/Updates.xml, which 404s).
$QtRepoVersionTag = "qt6_6120"
$QtRepoArchDir    = "msvc2022_64"
$QtPackagePrefix  = "qt.qt6.6120"
$QtPackageArch    = "win64_msvc2022_64"
$QtRepoBaseUrl    = "https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/$QtRepoVersionTag/${QtRepoVersionTag}_$QtRepoArchDir"

# Which packages/archives of that repository this script needs, and why.
# qtbase/qtdeclarative/qttools are bundled together as DownloadableArchives
# of the single "win64_msvc2022_64" PackageUpdate (Qt's top-level qtwebengine
# CMakeLists.txt add_subdirectory()s core, tools and declarative-facing
# pieces, so configuring the module at all needs all three, not just
# qtbase). qtshadertools is Qt's separate shader-compiler module, needed
# because QtWebEngine's Quick integration compiles .qsb shaders at
# configure/build time. qtwebchannel and qtpositioning are addons needed
# only because Step 6 below turns on FEATURE_webengine_webchannel and
# FEATURE_webengine_geolocation -- see the QT_FEATURE_webengine_webchannel
# and QT_FEATURE_webengine_geolocation extend_gn_target() conditions in
# qtwebengine's src/core/CMakeLists.txt, which only pull in
# renderer/web_channel_ipc_transport.* and location_provider_qt.* when
# those two features are enabled.
$NeededQtPackages = @(
    @{ Package = "$QtPackagePrefix.$QtPackageArch"; ArchivePrefixes = @("qtbase", "qtdeclarative", "qttools") },
    @{ Package = "$QtPackagePrefix.addons.qtshadertools.$QtPackageArch"; ArchivePrefixes = @("qtshadertools") },
    @{ Package = "$QtPackagePrefix.addons.qtwebchannel.$QtPackageArch"; ArchivePrefixes = @("qtwebchannel") },
    @{ Package = "$QtPackagePrefix.addons.qtpositioning.$QtPackageArch"; ArchivePrefixes = @("qtpositioning") }
)

# ---------------------------------------------------------------------------
# Operator-supplied, optional inputs
# ---------------------------------------------------------------------------
if (-not $env:WORKDIR) { $env:WORKDIR = Join-Path (Get-Location) "qtwebengine-credits-regen" }
$WorkDir = $env:WORKDIR
# Path to the captured production GN-args log for :QtWebEngineCore
# (qtwebengine-core-gn-log.txt from GH Actions run 42476475449). Strongly
# recommended on this canonical path -- without it you cannot confirm a
# byte-for-byte args.gn match to production.
$ProductionGnArgsFile = $env:PRODUCTION_GN_ARGS_FILE
# Path to the old chromium_attributions.qdoc (sha256 b2382a81...) for a
# line-level diff in Step 8.
$OldCreditsFile = $env:OLD_CREDITS_FILE

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
Set-Location $WorkDir

Write-Host "== Step 1/9: preflight tool check =="
foreach ($tool in @("curl.exe", "tar.exe", "7z.exe", "node.exe", "python", "cmake", "ninja")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "MISSING REQUIRED TOOL: $tool"
    }
}
# Confirm an MSVC compiler is actually on PATH (the whole point of this
# script). Run from a "Developer PowerShell for VS" / x64 Native Tools
# prompt, or call vcvarsall.bat before invoking this script.
if (-not (Get-Command "cl.exe" -ErrorAction SilentlyContinue)) {
    throw "cl.exe not found on PATH. Run this from a Visual Studio x64 Native Tools prompt (vcvarsall.bat x64) -- this canonical path requires a real MSVC toolchain, not just target_os=win."
}

Write-Host "== Step 2/9: download official tarball =="
if (-not (Test-Path $TarballName)) {
    curl.exe -fL --retry 3 -o $TarballName $TarballUrl
}

Write-Host "== Step 3/9: verify sha256 before touching the contents =="
$actualHash = (Get-FileHash -Algorithm SHA256 -Path $TarballName).Hash.ToLower()
if ($actualHash -ne $TarballSha256) {
    throw "SHA256 MISMATCH: expected $TarballSha256, got $actualHash"
}
$actualBytes = (Get-Item $TarballName).Length
if ($actualBytes -ne $TarballBytes) {
    throw "BYTE COUNT MISMATCH: expected $TarballBytes, got $actualBytes"
}
Write-Host "sha256 OK, bytes OK ($actualBytes)."

Write-Host "== Step 4/9: extract (this tarball only, nothing else) =="
if (-not (Test-Path $SrcTopDir)) {
    tar.exe -xJf $TarballName
}

Write-Host "== Step 5/9: get the official Qt $QtHostVersion host toolchain ($QtPackageArch, sha1-verified, no aqt) =="
$QtHostDir        = Join-Path $WorkDir "qt-host"
$QtHostInstallDir = Join-Path $QtHostDir "$QtHostVersion\$QtRepoArchDir"
if (-not (Test-Path $QtHostInstallDir)) {
    New-Item -ItemType Directory -Force -Path $QtHostDir | Out-Null
    New-Item -ItemType Directory -Force -Path $QtHostInstallDir | Out-Null

    $UpdatesUrl     = "$QtRepoBaseUrl/Updates.xml"
    $UpdatesXmlPath = Join-Path $QtHostDir "Updates.xml"
    Write-Host "-- downloading $UpdatesUrl --"
    curl.exe -fL --retry 3 -o $UpdatesXmlPath $UpdatesUrl
    [xml]$updates = Get-Content $UpdatesXmlPath

    foreach ($pkg in $NeededQtPackages) {
        $packageNode = $updates.Updates.PackageUpdate | Where-Object { $_.Name -eq $pkg.Package }
        if (-not $packageNode) {
            throw "Updates.xml ($UpdatesUrl) has no <PackageUpdate> named $($pkg.Package) -- Qt's repository layout may have changed since this script was written. Inspect $UpdatesXmlPath by hand before retrying."
        }
        $allArchives = @($packageNode.DownloadableArchives -split ",\s*" | Where-Object { $_ })

        foreach ($prefix in $pkg.ArchivePrefixes) {
            $archiveName = $allArchives | Where-Object { $_ -like "$prefix-*.7z" } | Select-Object -First 1
            if (-not $archiveName) {
                throw "Package $($pkg.Package) in Updates.xml has no archive matching '$prefix-*.7z'. Known archives: $($allArchives -join ', ')"
            }

            $archiveUrl  = "$QtRepoBaseUrl/$($pkg.Package)/$archiveName"
            $archivePath = Join-Path $QtHostDir $archiveName
            $sha1Path    = "$archivePath.sha1"

            if (-not (Test-Path $archivePath)) {
                Write-Host "-- downloading $archiveName --"
                curl.exe -fL --retry 3 -o $archivePath $archiveUrl
            }
            curl.exe -fL --retry 3 -o $sha1Path "$archiveUrl.sha1"
            if (-not (Test-Path $sha1Path) -or (Get-Item $sha1Path).Length -eq 0) {
                throw "Could not download the .sha1 sidecar for $archiveName from $archiveUrl.sha1 -- refusing to extract an unverified archive."
            }

            $expectedSha1 = ((Get-Content $sha1Path -Raw).Trim() -split "\s+")[0].ToLower()
            $actualSha1   = (Get-FileHash -Algorithm SHA1 -Path $archivePath).Hash.ToLower()
            if ($actualSha1 -ne $expectedSha1) {
                throw "SHA1 MISMATCH for $archiveName : expected $expectedSha1 (from $sha1Path), got $actualSha1. Refusing to extract."
            }
            Write-Host "   sha1 OK: $archiveName"

            7z.exe x -y "-o$QtHostInstallDir" $archivePath | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "7z extraction of $archiveName into $QtHostInstallDir failed with exit code $LASTEXITCODE."
            }
        }
    }
}
$QtHostBin = Join-Path $QtHostInstallDir "bin"
if (-not (Test-Path (Join-Path $QtHostBin "qt-configure-module.bat"))) {
    throw "Could not locate qt-host bin\qt-configure-module.bat under $QtHostBin after downloading and extracting the official $QtPackageArch archives. Qt's packaging layout may have changed -- inspect $QtHostInstallDir by hand."
}
$env:PATH = "$QtHostBin;$env:PATH"

Write-Host "== Step 6/9: configure the qtwebengine module only far enough for GN =="
$BuildDir = Join-Path $WorkDir "build"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
Set-Location $BuildDir
# NOTE: these flags are Qt's documented defaults. Confirm/override them
# against $ProductionGnArgsFile once Step 7 runs -- this script does not
# guess at WIN32-only feature combinations beyond Qt's own defaults.
& "$QtHostBin\qt-configure-module.bat" "$WorkDir\$SrcTopDir" `
    -- `
    -DFEATURE_webengine_printing_and_pdf=ON `
    -DFEATURE_webengine_geolocation=ON `
    -DFEATURE_webengine_webchannel=ON `
    -DFEATURE_webengine_extensions=ON `
    -DQT_BUILD_EXAMPLES=OFF `
    -DQT_BUILD_TESTS=OFF

Write-Host "== Step 7/9: run only up to GN generation (NOT a chromium compile) =="
cmake --build $BuildDir --target gn
cmake --build $BuildDir --target run_core_GnDone

$GeneratedArgsGn = Get-ChildItem -Path $BuildDir -Recurse -Filter "args.gn" | Where-Object { $_.FullName -match "src.core" } | Select-Object -First 1
if ($ProductionGnArgsFile -and (Test-Path $ProductionGnArgsFile) -and $GeneratedArgsGn) {
    Write-Host "-- args.gn fidelity check against $ProductionGnArgsFile --"
    $diff = Compare-Object (Get-Content $ProductionGnArgsFile) (Get-Content $GeneratedArgsGn.FullName)
    if (-not $diff) {
        Write-Host "FIDELITY: PASS -- generated args.gn matches the captured production GN args exactly."
    } else {
        Write-Host "FIDELITY: WARN -- generated args.gn DIFFERS from production:"
        $diff | Format-Table | Out-String | Write-Host
        Write-Host "Output below is provisional until this is reconciled."
    }
} else {
    Write-Host "FIDELITY: NOT CHECKED -- set PRODUCTION_GN_ARGS_FILE to the qtwebengine-core-gn-log.txt artifact from GH Actions run 42476475449 (or the real production log) to check this."
}

Write-Host "== Step 8/9: run Qt's own generator (licenses.py credits) =="
cmake --build $BuildDir --target generate_chromium_attributions

$OutputQdoc = Get-ChildItem -Path $BuildDir -Recurse -Filter "chromium_attributions.qdoc" | Select-Object -First 1
if (-not $OutputQdoc -or $OutputQdoc.Length -eq 0) {
    throw "FAILED: chromium_attributions.qdoc not produced or empty."
}
$NewSha256 = (Get-FileHash -Algorithm SHA256 -Path $OutputQdoc.FullName).Hash.ToLower()
$NewBytes = $OutputQdoc.Length
Copy-Item $OutputQdoc.FullName (Join-Path $WorkDir "chromium_attributions.qdoc")

Write-Host "== Step 9/9: results and diff summary =="
Write-Host "New chromium_attributions.qdoc:"
Write-Host "  path:   $WorkDir\chromium_attributions.qdoc"
Write-Host "  bytes:  $NewBytes"
Write-Host "  sha256: $NewSha256"
Write-Host "Old (stale, 71a2fa55-based) credits file sha256: $OldCreditsSha256"
if ($NewSha256 -eq $OldCreditsSha256) {
    Write-Host "UNEXPECTED: new hash equals the old (stale) hash. Known content changes exist"
    Write-Host "  between 71a2fa55 and 39352427 (libxml README.chromium, tools/licenses/sbom.py)."
    Write-Host "  An exact match here suggests this run did not actually scan the 39352427 tree."
} else {
    Write-Host "DIFFERENT from old hash, as expected given the known upstream changes."
    if ($OldCreditsFile -and (Test-Path $OldCreditsFile)) {
        Write-Host "Line-level diff summary vs $OldCreditsFile :"
        Compare-Object (Get-Content $OldCreditsFile) (Get-Content (Join-Path $WorkDir "chromium_attributions.qdoc")) |
            Group-Object SideIndicator | ForEach-Object { Write-Host "  $($_.Name): $($_.Count) lines" }
    } else {
        Write-Host "No OLD_CREDITS_FILE supplied -- set it to the retained b2382a81 file for a line diff."
    }
}
Write-Host ""
Write-Host "EXIT CRITERIA CHECK:"
Write-Host "  [x] output file exists and is non-empty"
Write-Host "  [x] sha256 and byte count computed"
Write-Host "  [x] run on Windows with a real MSVC toolchain (cl.exe confirmed in Step 1)"
Write-Host "  [$(if ($ProductionGnArgsFile) {'x'} else {' '})] args.gn fidelity checked against production log"
Write-Host ""
Write-Host "Record NewSha256 ($NewSha256) and NewBytes ($NewBytes) into docs/REMOTE_APPLY.md's <CREDITS_SHA256> / <CREDITS_BYTES> placeholders."
