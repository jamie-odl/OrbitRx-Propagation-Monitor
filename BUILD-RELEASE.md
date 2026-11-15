# Building the OrbitRx 5.2.0 local candidate

This is Jamie's own checklist for running `tools/build_release_local.ps1` on
his personal PC. It does not upload, publish, tag or push anything -- it
only produces a zip and a provenance record on the local disk.

**This is a dry run until stated otherwise.** The first time Jamie runs this
script -- at whatever commit he runs it at first -- it is a rehearsal, not a
publish candidate. Its zip is not to be published or treated as release
evidence. The console output and provenance record from that run go to
QA/Risk for review (L10) alongside everything else in step 17's send-back
list. Expect this first run to surface friction: a missing prerequisite, a
path guard tripping on something unexpected, a stale pin. Fixing those is
the point of the dry run. Only a later run -- at the final `<CLEARED_SHA>`
QA and Risk have cleared, after L10 review of the dry run is done -- produces
something that can become a publish candidate, and even that still needs
Jamie's explicit publish go-ahead (P8) and the recorded N1 acceptance (P9)
before anything is uploaded.

## Prerequisites

1. Your own personal PC only. Not employer equipment, not over a VPN, not
   inside a remote session (L1). Confirm **Settings > Accounts > Access work
   or school is empty** before you start.

   The script also runs a mandatory check with `dsregcmd /status` and
   refuses (`BUILD FAILED`, exit 1, ending "Stop and tell Risk.") if:
   - **any** of DomainJoined, AzureAdJoined, Intune/MDM ("Enterprise")
     joined, or "workplace joined" reads YES anywhere in the output -- a
     duplicate YES counts; there is no "last value wins";
   - `dsregcmd` exits non-zero, or its output is empty;
   - fewer than all 4 of those values can be read, or any of them is
     anything other than exactly YES or NO (for example `YES (Contoso)` or a
     localised word) -- that reads as UNVERIFIED, and UNVERIFIED means
     refuse;
   - `dsregcmd` itself is missing. It ships in `System32` on Windows 10 and
     11, so that is itself abnormal.

   This check cannot be bypassed, downgraded or skipped by any switch,
   parameter, environment variable or config file -- `-AttestPersonalKit` is
   an attestation required **in addition** to this check, never a substitute
   for it. The provenance record keeps only the 4 YES/NO values (never the
   device ID, tenant name or tenant ID), and a refusal names only the
   flag(s) or the reason, never any tenant/device detail.

   **If it refuses on a PC you believe is personal** -- for example because
   a work account was added just for Teams or Outlook -- **stop and tell
   Risk**. Do not disconnect accounts, remove a work profile, or edit
   anything just to get past the check. Risk decides whether that PC can be
   used; this heuristic is not a substitute for actually knowing whose PC
   this is.
2. **PowerShell 7.4 or later (`pwsh`).** This script requires it (`#Requires
   -Version 7.4`, plus its own inline check -- both compare the full
   version, so 7.0-7.3 refuse with the same clear message as Windows
   PowerShell 5.1, not just a pre-7 major version) rather than failing
   partway through. Check what you have with `pwsh -v`; if that does not already work, or
   reports an older 7.x, install the current release with
   `winget install --id Microsoft.PowerShell`, then re-check with `pwsh -v`.
3. **Git for Windows** (for `git clone`, `git rev-parse`, etc.).
4. **Python 3.12.10 for Windows (64-bit)**, downloaded yourself from
   python.org and installed "for the current user". The script never
   fetches or installs this.
5. **Inno Setup 6** (the free/personal edition, from jrsoftware.org),
   installed yourself. The script never installs this either. A "for me
   only" (per-user) install lands under
   `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`, not
   `%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe` (the script's default) -- if
   you installed it that way, pass `-Iscc "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"`.
6. **Disk space and time**: roughly 3 GB free (the venv, PyInstaller's
   `build\`/`dist\` output and the packed zip together), and roughly
   20-40 minutes end to end, most of it the PyInstaller build and the full
   pytest suite.
7. **PowerShell's execution policy.** If running the script directly gives
   a "cannot be loaded because running scripts is disabled" error, either:
   - in that PowerShell window only, run
     `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before
     calling the script (this affects only the current process, not your
     machine- or user-wide policy and does not persist), or
   - run `pwsh -ExecutionPolicy Bypass -File tools\build_release_local.ps1 ...`
     instead -- use `pwsh`, not `powershell` (Windows PowerShell 5.1, which
     the script refuses -- see prerequisite 2).
   Do not change the machine or user execution policy to get this script to
   run.

## Steps

8. Create a plain local folder, e.g. `C:\build\orbitrx-5.2.0\`. It must not
   be under OneDrive or your Desktop, on a subst/mapped or UNC network
   drive, behind a reparse point (junction/symlink) anywhere in its path,
   or under `$env:USERPROFILE`. The script resolves the real full path
   (expanding environment variables, 8.3 short names and relative paths)
   and refuses all of the above itself -- this is just so you know what it
   is checking and why, rather than guessing from the error message.
9. In that folder, make a fresh clone of the public repo, then detach HEAD
   at the exact commit you are building (L2):
   ```
   git clone https://github.com/jamie-odl/OrbitRx-Propagation-Monitor.git
   cd OrbitRx-Propagation-Monitor
   git checkout --detach <the 40-char commit SHA>
   ```
   The clone must stay fresh: no leftover files from a previous attempt, no
   extra untracked or ignored files. The script checks this and refuses to
   build from a dirty tree.
10. Download `python-3.12.10-amd64.exe` from the official python.org
    downloads page and install it "for the current user" (L3). Do not use
    any other source or version.
11. Install Inno Setup 6 as described in the prerequisites above.
12. **Get `ship-set-inventory.txt` -- this is mandatory (L5), not optional.**
    The script refuses to run without it. To get it:
    1. Open the GitHub Actions run for the **exact commit SHA** you are
       building, on github.com (you need to be signed in to a GitHub
       account to download run artifacts).
    2. Download the `release-exe-captures` artifact from that run and unzip
       it.
    3. Take `ship-set-inventory.txt` from inside it -- that is the file to
       pass as `-CiInventory`.
    Artifacts expire 30 days after the run finished. If the artifact has
    already expired, re-running CI at that SHA just to regenerate it is a
    decision for QA/Risk to make, not something to do unilaterally --
    ask first; do not build without it.
13. Put the Python installer you downloaded in step 10 and the
    `ship-set-inventory.txt` you got in step 12 into a plain local folder,
    e.g. `C:\build\inputs\` (not `Downloads` -- see why below). Open
    PowerShell 7 (`pwsh`) in the cloned repo and run the build script, for
    example:
    ```
    pwsh -ExecutionPolicy Bypass -File tools\build_release_local.ps1 `
      -ExpectedSha <the 40-char commit SHA> `
      -PythonInstaller C:\build\inputs\python-3.12.10-amd64.exe `
      -CiInventory C:\build\inputs\ship-set-inventory.txt `
      -AttestPersonalKit `
      *>&1 | Tee-Object -FilePath C:\build\orbitrx-5.2.0\build-console.txt
    ```
    `-PythonInstaller` has no default -- unlike `-Iscc`, `-PythonExe` and
    `-BuildRoot`, which fall back to the locations described above if
    omitted, `-PythonInstaller` must always be passed explicitly; the
    script refuses to run without it. Add `-Iscc`, `-PythonExe` or
    `-BuildRoot` only if your installs are not at the script's default
    locations. `*>&1 | Tee-Object -FilePath ...` (not `Start-Transcript`)
    saves a copy of everything the script printed, for QA/Risk, without
    also stamping your username and computer name into the saved file's
    own header the way `Start-Transcript` would.

    **Use a new, empty `-BuildRoot` for every run (M-1).** Delete the whole
    `-BuildRoot` folder (the default is `C:\build\orbitrx-5.2.0-work\`;
    whatever you passed if you overrode it) before every attempt -- not
    only after a failure. The script itself refuses immediately, before any
    build work starts, if `<BuildRoot>\out\` already exists and is not
    empty: most often that means an earlier *successful* run's zip and
    provenance record are still there, and reusing that BuildRoot would
    either leave the old zip under the public name next to a provenance
    record for a different zip, or fail at the very last step once the new
    run gets that far. This applies to the real build that follows a
    cleared dry run too -- do not reuse the dry run's BuildRoot.

    **Tool caches (C6):** the script points pip's and PyInstaller's own
    caches (`PIP_CACHE_DIR`, `PYINSTALLER_CONFIG_DIR`) at folders under
    `-BuildRoot` for the duration of the run, so you do not need to set
    either of those yourself -- there is no manual env var step here.
    `$env:TEMP`/`$env:TMP` are deliberately left alone (redirecting them
    would change what the auto-redaction in step 13's note below treats as
    "this PC's temp folder" partway through the run).

    If you have to re-run after a failure, use
    `Tee-Object -FilePath ... -Append`, or give each attempt its own file
    name (e.g. `build-console-attempt2.txt`) -- a plain `Tee-Object
    -FilePath` with no `-Append` overwrites the file on every run, so a
    retry would silently wipe out the previous attempt's build-console.txt
    before QA/Risk ever see it.

    `build-console.txt`, and some files under `out\`, used to be able to end
    up containing your Windows username -- by way of the default
    `-PythonExe` path (which sits under your profile), pip's and
    PyInstaller's own build-path output, and whatever path you pass
    yourself as `-PythonInstaller`/`-CiInventory`. The script now
    auto-redacts: anything it prints, anything it relays from pip,
    pytest, PyInstaller, ISCC or its own python tools, any direct `git`/
    `python` call this script itself makes, and the ship-set/pe-check/
    pyz-scan files it writes under `out\`, have `$env:USERNAME`,
    `$env:USERPROFILE` (and `$env:LOCALAPPDATA`/`$env:APPDATA`/`$env:TEMP`),
    `$env:COMPUTERNAME`, `$env:USERDOMAIN`, `$env:USERDNSDOMAIN`,
    `$env:LOGONSERVER` and `$env:OneDrive`/`$env:OneDriveCommercial`/
    `$env:OneDriveConsumer` replaced with `<user>`/`<profile>`/`<host>`/
    `<domain>`/`<dnsdomain>`/`<logonserver>` before you ever see them --
    including the `/` form of a path value, its Windows 8.3 short form,
    and a URL-encoded form, matched case-insensitively (L-C). That
    auto-redaction only matches those exact environment values, though --
    it is not a human review, so a manual redaction scan (B4) over
    `build-console.txt` and `out\` is still required before sending
    anything on, in case a different real name you typed into a custom
    path slipped through untouched. These files still go only to QA and
    Risk and are never published (see the send-back list in step 17
    below). Passing `-CiInventory` and `-PythonInstaller` from a plain
    folder such as `C:\build\inputs\` instead of
    `C:\Users\<you>\Downloads\...` reduces what the B4 scan has to catch in
    the first place -- prefer that over Downloads.

    **Which SHA?** Use `<CLEARED_SHA>` as a placeholder here, never a
    commit you picked yourself. The actual value must be the final head
    that QA and Risk have cleared and Jamie has approved for release --
    after the fast-forward merge to `main`, that is `main`'s head commit.
    Get the real value from the Chief of Staff or the Risk clearance note,
    not by reading recent commits in this repo, and confirm it against the
    clone itself with `git rev-parse HEAD` before you build.

    This applies just as much to the dry run: the Chief of Staff supplies
    the dry-run SHA too, together with that SHA's CI run -- do not pick a
    dry-run commit yourself either. `-CiInventory`'s ship-set-inventory.txt
    must come from that exact SHA's CI run (L5), so the SHA and the
    inventory always travel together as a pair, dry run or not.
14. What PASS looks like: every gate prints its own `...: PASS` line (the
    managed-device check, clean-clone, the CI-inventory header check,
    Python pins, tests, the build-meta check, the ship-set and
    OpenSSL/publisher/PE/PYZ-scan gates, the L5 and L6 checks and the
    determinism self-check), and the script finishes by printing both exe
    hashes, the zip's sha256 and size, and the reminders below. The TESTS
    gate (step e) runs with the one network-marked live NOAA test excluded
    -- that test is skipped here, not failing; CI already ran it at this
    exact SHA, in both OSes' full suites. Adding that network-marker skip
    to the local gate (rather than running the full suite unmodified) is a
    deliberate change Risk asked to review -- it is called out here, not
    hidden in a side comment, precisely so that review happens.

    **Network use during this run (L-D):** besides pip's PyPI hash-pinned
    downloads (step 13) and Windows' own Authenticode CRL/OCSP lookups
    during a signature check, several UI/capture tests in that same TESTS
    gate start the app, which then attempts its normal background fetches
    (NOAA SWPC, hamqsl, PSKReporter, the contest calendar, and an
    api.github.com update check). Those tests tolerate being offline and
    do not assert on any fetch succeeding -- only the one test that makes
    a live, *asserted* network call is marked `@pytest.mark.network` and
    is the test this local gate deselects.

    Any failure stops the script immediately with a clear message and a
    non-zero exit code, and that message is always `BUILD FAILED: ...`
    (see the top of this script's output or `build-console.txt`). If an
    invocation instead errors out with no `BUILD FAILED` line at all --
    e.g. a PowerShell parameter-binding error -- the command line itself
    was wrong before the script's own logic ever ran (a mistyped
    parameter name, a missing required value); check what you typed
    against step 13's example rather than treating it as one of the
    gates above failing. **This does not mean nothing was left on disk.** If
    the failure happens after the commit-stamping step (f), the tracked
    file `orbitrx/_build_meta.py` can be left locally modified, and
    `dist\`, `build\`, the venv under `-BuildRoot`, and a partial `out\` can
    all remain on disk. Re-running the script against the same clone will
    then refuse immediately with the "working tree is not clean" error,
    because that modified tracked file is exactly what the clean-clone
    check (step b) is there to catch.

    To recover, **deleting the `-BuildRoot` folder is not optional** (M-1):
    whatever else is wrong, a leftover `out\` under the old `-BuildRoot`
    makes the script refuse before any build work even starts on the next
    attempt, regardless of whether this failure's own symptom is fixed.
    - **Preferred:** delete the whole clone folder and the `-BuildRoot`
      folder, and start again from a fresh `git clone` (step 8).
    - **Or**, inside the existing clone: `git checkout -- .` followed by
      `git clean -xdf` to restore the tracked file and remove untracked/
      build output -- but still delete the `-BuildRoot` folder separately
      (it is outside the clone, so `git clean` inside the clone does not
      touch it, and the script will not proceed while its `out\` is
      non-empty).
15. L7, by hand: launch `dist\OrbitRxMonitor\OrbitRxMonitor.exe` yourself
    and confirm it completes a live SWPC fetch (the script does not do this
    for you, and does not launch the GUI for you). The script prints
    exactly what to capture as evidence when it finishes -- a screenshot or
    a short written note of what you saw and when.

    Note on what this run does *not* re-check: the local gates mirror CI's
    *build-time* checks (pins, ship-set contents, the static PYZ scan for
    the simulated-rig gate, publisher/PE checks). They do **not** repeat
    CI's *runtime* gates -- the screenshot capture at 100%/150% scale, the
    on-screen-fit check, the units check, or the DX cluster field-edge
    measurement. Those rely on the CI run at this exact SHA having already
    passed; this script does not re-run them locally.
16. Run your antivirus scan over `dist\OrbitRxMonitor\`, the installer exe
    and the zip in `<BuildRoot>\out\`.
17. Keep everything the script wrote together: `OrbitRx-<VERSION>-PROVENANCE.txt`
    and the rest of `<BuildRoot>\out\` (the zip, `ship-set-inventory.txt`,
    `installer-publisher.txt`, `ship-set-qt.txt`, `ship-set-tls.txt`, the
    pyz-scan output, and the L5/L6 compare-result files), plus
    `build-console.txt` from step 13. If you want a copy of the provenance
    record tracked in the repo, add it under `docs/` later through a normal
    reviewed PR -- do not commit it straight from this process.

    **Send to QA/Risk (L10):**
    - the provenance record (`OrbitRx-<VERSION>-PROVENANCE.txt`)
    - `build-console.txt`
    - `out\ship-set-inventory.txt` (the locally-built one)
    - `out\installer-publisher.txt` (the PE check output)
    - `out\ship-set-qt.txt` and `out\ship-set-tls.txt`
    - the pyz-scan output (`out\pyz-scan.txt`)
    - the L7 evidence (screenshot or note of the SWPC fetch)
    - the antivirus scan result from step 16

    `build-console.txt` and the `out\` files above have `$env:USERNAME`,
    `$env:USERPROFILE`, `$env:COMPUTERNAME` and the other values listed in
    step 13 auto-redacted to `<user>`/`<profile>`/`<host>`/etc., but that
    is not a substitute for the manual B4 redaction scan over both before
    sending -- they are for QA/Risk only and must never be published.

    **Run this wider B4 scan (C5)** in `pwsh`, from `C:\build\orbitrx-5.2.0`
    (the clone), before sending anything on:
    ```powershell
    $vals = @($env:USERNAME, $env:COMPUTERNAME, $env:USERDOMAIN, $env:USERDNSDOMAIN, ($env:LOGONSERVER -replace '^\\\\','')) | Where-Object { $_ -and $_.Length -ge 3 }
    $pat = (($vals | ForEach-Object { [regex]::Escape($_) }) + @('C:\\Users\\', 'OneDrive', 'Desktop', '~1', '%20')) -join '|'
    Select-String -Path .\build-console*.txt, C:\build\orbitrx-5.2.0-work\out\*.txt -Pattern $pat
    ```
    - Hits that are already `<user>`, `<profile>` or `<host>` are fine.
    - For any other hit, redact a **copy** and write "redacted N lines" in
      the cover note you send with step 17's set. Otherwise write
      "redaction scan: no hits".
    - On a personal PC, `USERDOMAIN` usually equals `COMPUTERNAME`. A real
      domain name showing up here would itself be an L1 red flag -- **stop
      and tell Risk**, do not just redact it and carry on.

    The provenance record is the file written to be publish-safe (it
    self-checks for your username, computer name, `$env:USERPROFILE`/
    `$env:HOME` and anything that looks like a UK postcode, and refuses to
    write itself if it finds any); send both, but only the provenance
    record is meant to ever leave that reviewing circle.
18. Do not upload or publish anything yet. Wait for both: your own explicit
    publish go-ahead (P8), and the recorded N1 acceptance (P9).
19. Only once both of those are in hand: append the single `<sha256>  <zip
    filename>` line the script printed to **both** SUMS locations,
    additively. Do not edit, reorder or remove the existing 5.1.0 line (L9).
    The script labels that line "SUMS line for a QA/Risk-cleared build
    only (see marker):" rather than phrasing it as something to do now --
    it has no way to know whether a given run is the cleared build, so it
    always prints that line directly beneath a
    `DRY-RUN ONLY -- NOT FOR PUBLICATION` marker it cannot suppress either
    (I-3). Both lines are reminders for you, not part of the SUMS line
    itself; copy only the `<sha256>  <zip filename>` line into the SUMS
    files, and only once this is genuinely the `<CLEARED_SHA>` build QA/Risk
    cleared and you have both P8 and P9 in hand.

See `docs/SETUP_ZIP.md` for the exact zip layout and determinism rules the
script's packer enforces.
