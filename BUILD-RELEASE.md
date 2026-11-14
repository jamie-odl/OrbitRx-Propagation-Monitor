# Building the OrbitRx 5.2.0 local candidate

This is Jamie's own checklist for running `tools/build_release_local.ps1` on
his personal PC. It does not upload, publish, tag or push anything -- it
only produces a zip and a provenance record on the local disk.

1. Use your own personal PC only. Not employer equipment, not over a VPN,
   not inside a remote session (L1).
2. Create a plain local folder, e.g. `C:\build\orbitrx-5.2.0\`. It must not
   be under OneDrive or under your Desktop -- the script refuses to run
   from either.
3. In that folder, make a fresh clone of the public repo, then detach HEAD
   at the exact commit you are building (L2):
   ```
   git clone https://github.com/jamie-odl/OrbitRx-Propagation-Monitor.git
   cd OrbitRx-Propagation-Monitor
   git checkout --detach <the 40-char commit SHA>
   ```
   The clone must stay fresh: no leftover files from a previous attempt, no
   extra untracked or ignored files. The script checks this and refuses to
   build from a dirty tree.
4. Download `python-3.12.10-amd64.exe` from the official python.org
   downloads page and install it "for the current user" (L3). Do not use
   any other source or version.
5. Install Inno Setup 6 (the free/personal edition, from jrsoftware.org).
   The script never installs this for you.
6. Optional but recommended: download `ship-set-inventory.txt` from the
   exact SHA's GitHub Actions run, from the `release-exe-captures`
   artifact (it is a text file, not a binary). This lets the script check
   your local build against what CI built from the same commit (L5).
7. Open PowerShell in the cloned repo and run the build script, for
   example:
   ```
   tools\build_release_local.ps1 `
     -ExpectedSha <the 40-char commit SHA> `
     -PythonInstaller C:\Downloads\python-3.12.10-amd64.exe `
     -CiInventory C:\Downloads\ship-set-inventory.txt `
     -AttestPersonalKit
   ```
   Add `-Iscc`, `-PythonExe` or `-BuildRoot` only if your installs are not
   at the script's default locations.
8. What PASS looks like: every gate prints its own `...: PASS` line
   (clean-clone, Python pins, tests, the build-meta check, the ship-set and
   OpenSSL/publisher/PE gates, the L6 pre-upload check and the determinism
   self-check), and the script finishes by printing both exe hashes, the
   zip's sha256 and size, and the reminders below. Any failure stops the
   script immediately with a clear message and a non-zero exit code --
   nothing is packed or left half-built.
9. L7, by hand: launch `dist\OrbitRxMonitor\OrbitRxMonitor.exe` yourself and
   confirm it completes a live SWPC fetch (the script does not do this for
   you).
10. Run your antivirus scan over `dist\OrbitRxMonitor\`, the installer exe
    and the zip in `<BuildRoot>\out\`.
11. Keep `OrbitRx-5.2.0-PROVENANCE.txt` (written beside the zip in
    `<BuildRoot>\out\`) together with the zip. If you want a copy tracked
    in the repo, add it under `docs/` later through a normal reviewed PR --
    do not commit it straight from this process.
12. L10: send the provenance record, the local `ship-set-inventory.txt` and
    the script's PASS output to QA/Risk for review.
13. Do not upload or publish anything yet. Wait for both: your own explicit
    publish go-ahead (P8), and the recorded N1 acceptance (P9).
14. Only once both of those are in hand: append the single line the script
    printed to **both** SUMS locations, additively. Do not edit, reorder or
    remove the existing 5.1.0 line (L9).

See `docs/SETUP_ZIP.md` for the exact zip layout and determinism rules the
script's packer enforces.
