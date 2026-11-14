# Installer and the 5.1.0 zip

## 5.2.0 local build (Option B)

This is prepared but not published; see `BUILD-RELEASE.md` for the full
checklist. `tools/pack_setup_zip.py`'s Option-B mode (`--onedir --installer
--out --epoch`) builds a deterministic `OrbitRx-Setup-5.2.0.zip`:

- Zip root is exactly two entries: the `OrbitRxMonitor/` onedir tree
  (unmodified) and a top-level `OrbitRxMonitor-Setup.exe`. Nothing else.
- Example command (run by `tools/build_release_local.ps1`, step i):
  ```
  python tools/pack_setup_zip.py --onedir dist\OrbitRxMonitor --installer dist\OrbitRxMonitor-Setup.exe --out OrbitRx-Setup-5.2.0.zip --epoch <commit time>
  ```
  `--epoch` also accepts `--source-date-epoch` or a `SOURCE_DATE_EPOCH`
  environment variable; the local build script passes the commit's own
  `git show -s --format=%ct` time, so the zip's timestamp is tied to the
  commit, not to when or where it was packed.

Determinism rules (see the module docstring in `tools/pack_setup_zip.py`
for the full rationale):

- **No directory entries** -- every member is a file. This was decided
  explicitly rather than left implicit, settling QA's point about it.
- Members are sorted by archive path, compared bytewise on the UTF-8,
  forward-slash-separated name.
- Every member is `ZIP_DEFLATED` at compresslevel 9.
- Every member shares one fixed DOS date/time, derived from the epoch via
  `time.gmtime` (UTC/GMT, not the host's local time zone), with the
  2-second DOS granularity rounded down and dates before 1980-01-01
  clamped forward to it.
- `create_system` is fixed at 0 (MS-DOS/FAT). `external_attr` is fixed at
  `0x20` (the FAT "archive" bit alone, and nonzero so the zipfile library
  cannot silently replace a falsy 0 with a Unix permission default).
  `create_version`/`extract_version` are fixed at 20.
- No extra fields, no archive or per-member comments, no data descriptors.
- The result is byte-identical regardless of file mtimes, directory
  listing order, permissions/umask, host time zone, current working
  directory or the absolute location of the inputs -- see
  `tests/test_pack_setup_zip_deterministic.py`.

`--expect-inventory PATH` compares the zip's `OrbitRxMonitor/` member sizes
against a CI-produced `ship-set-inventory.txt`, excluding both shipped
exes (L5). `--verify ZIP` re-opens an existing zip and checks that shape
(L6). `--compare-tree DIR --inventory FILE` runs that same size comparison
against an already-extracted `OrbitRxMonitor/` directory tree instead of a
zip -- used to re-check the zip's contents once more after unpacking it
(also L6).

The sha256 of the zip produced by a real local build is to be recorded
here after that build runs; this section does not itself claim one.

## Current live 5.1.0 zip (since 9 November 2026)

The public `OrbitRx-Setup-5.1.0.zip` was replaced on 9 November 2026. The digest below is the live one. `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`, described in the sections after this one, is the superseded 5 November installer-only archive. Do not publish it as the 5.1.0 checksum.

- URL: `https://downloads.thevenom.dev/orbitrx/OrbitRx-Setup-5.1.0.zip`, 434,814,502 bytes
- SHA-256: `d6a3aebf3c79389949ce3ca4abe2b865fe6d1ce4346aa409ba610b053c609c6f`
- Live `SHA256SUMS.txt` (both `https://thevenom.dev/downloads/orbitrx/SHA256SUMS.txt` and `https://downloads.thevenom.dev/orbitrx/SHA256SUMS.txt`, re-fetched 12 November 2026) has exactly one entry: `d6a3aebf3c79389949ce3ca4abe2b865fe6d1ce4346aa409ba610b053c609c6f  OrbitRx-Setup-5.1.0.zip`. The zip was downloaded and re-hashed on 12 November 2026 and matches.
- Built by Actions run `42520759834` from commit `9ca6178799a698231491eebcc101ad3bba914754` (branch `cursor/shipped-5-1-0-notices-2d8d`, private artifact `windows-private-candidate`). Layout: onedir `OrbitRxMonitor/` plus `OrbitRxMonitor-Setup.exe`. `OrbitRxMonitor.exe` SHA-256 `a103f27d4abff5450acfcce52e4eb116cf99d65d175bc582a126005d24257830`; `OrbitRxMonitor-Setup.exe` SHA-256 `1fedae7e50b69576762a3670a07ffd1c63ffa5032749f2fb30d6408c32d723c8`.
- `tools/pack_setup_zip.py` does not produce this zip and does not claim to.

This branch (the 5.2.0 native-map candidate, prepared but not yet published) does not publish, replace or re-pack the live zip.

## Superseded 5 November 2026 archive

Two different facts. The installer bytes have a recorded build. The zip around them was not produced by a command stored in git. A reconstruction from the installer file does reproduce the published zip bytes. A future pack does not aim at those bytes.

### Proven installer

`OrbitRxMonitor-Setup.exe` inside `OrbitRx-Setup-5.1.0.zip` is byte-identical to the file in Actions artifact `OrbitRx-windows-unsigned` from run `42004653668`.

- Commit: `304db03d99604af20da0b49ee2f3894ab17e2cc9`
- Installer SHA-256: `4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8`
- Job log: Python 3.12.10, PyInstaller 6.22.3, Inno Setup compiler engine 6.7.1, `iscc "/DAppVer=$ver" installer\OrbitRxMonitor.iss`
- `osslsigncode` on that exe: no signature. PE checksum field `00000000`, calculated `0F60B2DC`
- Version resource: CompanyName `thevenom`, FileVersion `5.1.0.0`, ProductVersion `5.1.0`

The release workflow on this commit does not publish. The changelog records 5.1.0 as released on 9 November 2026. Nothing in this branch uploads a release or replaces that exe.

### Published digest at the time, and what was actually hashed

These are separate checks.

- `https://thevenom.dev/downloads/orbitrx/SHA256SUMS.txt` was fetched on 7 November 2026 (HTTP 200). At that time (before the 9 November replacement) its checksum line was `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b  OrbitRx-Setup-5.1.0.zip` (two spaces before the filename). That is a text file on the website. It is not the zip bytes.
- `tools/pack_setup_zip.py --historical-observed`, given the Actions artifact `OrbitRxMonitor-Setup.exe`, writes a zip whose SHA-256 is that same digest. The deflate stream is `zlib.compressobj(9, zlib.DEFLATED, -15)` of those installer bytes. Observed headers: one member `OrbitRxMonitor-Setup.exe`, method 8, flag 0, no extra field, no comment, version needed 20, version made by `0x0314`, external attributes `0x81A40000`, DOS time `20601`, DOS date `23909` (2026-11-05 10:03:50), 257,486,082 bytes. This reconstruction does not download `downloads.thevenom.dev`.
- A later read of `https://downloads.thevenom.dev/orbitrx/OrbitRx-Setup-5.1.0.zip` received a Cloudflare challenge and did not hash the live object. Do not treat the reconstruction as a fresh hash of that URL.

The reconstruction is not a command found in git. No command in git or in the Actions workflow writes `OrbitRx-Setup-5.1.0.zip`. The CI `SHA256SUMS.txt` hashes the two exes and does not contain the zip digest.

### Future packs

The default of `tools/pack_setup_zip.py` also uses raw deflate level 9 and the same header shape, but it takes the DOS time from the input file's modification time. It does not force 2026-11-05 10:03:50. A new installer, or the same installer with a different timestamp, will not come out as `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`. Use the default for a pack you build later. Use `--historical-observed` only to check the 5 November 2026 archive against the known installer bytes.

This branch does not publish either zip. The onedir spec on this head is an unpublished recipe. It does not alter `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b` or the Actions installer `4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8`.
