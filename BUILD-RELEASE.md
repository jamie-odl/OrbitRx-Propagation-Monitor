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
   inside a remote session (L1). The script also runs a best-effort check
   with `dsregcmd /status` (if present) and refuses to continue if the
   machine reports as domain-joined, Azure AD-joined or Intune/MDM
   ("Enterprise") joined; it only warns if the machine is "workplace
   joined". This heuristic is not a substitute for actually knowing whose
   PC this is.
2. **PowerShell 7 (`pwsh`).** This script requires it and refuses to run on
   Windows PowerShell 5.1 with a clear message rather than failing partway
   through. Install PowerShell 7 from Microsoft if `pwsh -v` does not
   already work in your terminal.
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
13. Open PowerShell 7 (`pwsh`) in the cloned repo and run the build script,
    for example:
    ```
    pwsh -ExecutionPolicy Bypass -File tools\build_release_local.ps1 `
      -ExpectedSha <the 40-char commit SHA> `
      -PythonInstaller C:\Downloads\python-3.12.10-amd64.exe `
      -CiInventory C:\Downloads\ship-set-inventory.txt `
      -AttestPersonalKit `
      *>&1 | Tee-Object -FilePath C:\build\orbitrx-5.2.0\build-console.txt
    ```
    Add `-Iscc`, `-PythonExe` or `-BuildRoot` only if your installs are not
    at the script's default locations. `*>&1 | Tee-Object -FilePath ...`
    (not `Start-Transcript`) saves a copy of everything the script printed,
    for QA/Risk, without also stamping your username and computer name
    into the saved file's own header the way `Start-Transcript` would.

    If you have to re-run after a failure, use
    `Tee-Object -FilePath ... -Append`, or give each attempt its own file
    name (e.g. `build-console-attempt2.txt`) -- a plain `Tee-Object
    -FilePath` with no `-Append` overwrites the file on every run, so a
    retry would silently wipe out the previous attempt's build-console.txt
    before QA/Risk ever see it.

    `build-console.txt`, and some files under `out\`, can end up containing
    your Windows username -- by way of the default
    `-PythonExe`/`-PythonInstaller` paths (which sit under your profile),
    pip's and PyInstaller's own build-path output, and whatever path you
    pass as `-CiInventory`. That is one more reason these files go only to
    QA and Risk and are never published (see the send-back list in step 17
    below). Passing `-CiInventory` and `-PythonInstaller` from a plain
    folder such as `C:\build\...` instead of `C:\Users\<you>\Downloads\...`
    keeps your username out of these files in the first place -- prefer
    that over Downloads.

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
    hashes, the zip's sha256 and size, and the reminders below.

    Any failure stops the script immediately with a clear message and a
    non-zero exit code. **This does not mean nothing was left on disk.** If
    the failure happens after the commit-stamping step (f), the tracked
    file `orbitrx/_build_meta.py` can be left locally modified, and
    `dist\`, `build\`, the venv under `-BuildRoot`, and a partial `out\` can
    all remain on disk. Re-running the script against the same clone will
    then refuse immediately with the "working tree is not clean" error,
    because that modified tracked file is exactly what the clean-clone
    check (step b) is there to catch.

    To recover:
    - **Preferred:** delete the whole clone folder and the `-BuildRoot`
      folder, and start again from a fresh `git clone` (step 8).
    - **Or**, inside the existing clone: `git checkout -- .` followed by
      `git clean -xdf` to restore the tracked file and remove untracked/
      build output, then delete the `-BuildRoot` folder separately (it is
      outside the clone, so `git clean` inside the clone does not touch
      it).
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

    `build-console.txt` can contain local paths (your username, folder
    layout) and is for QA/Risk only -- never publish it. The provenance
    record is the file written to be publish-safe (it self-checks for your
    username, computer name, `$env:USERPROFILE`/`$env:HOME` and anything
    that looks like a UK postcode, and refuses to write itself if it finds
    any); send both, but only the provenance record is meant to ever leave
    that reviewing circle.
18. Do not upload or publish anything yet. Wait for both: your own explicit
    publish go-ahead (P8), and the recorded N1 acceptance (P9).
19. Only once both of those are in hand: append the single line the script
    printed to **both** SUMS locations, additively. Do not edit, reorder or
    remove the existing 5.1.0 line (L9).

See `docs/SETUP_ZIP.md` for the exact zip layout and determinism rules the
script's packer enforces.
