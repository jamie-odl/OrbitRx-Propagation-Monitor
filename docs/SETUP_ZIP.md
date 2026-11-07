# Installer and the 5.1.0 zip

Two different facts. The installer bytes have a recorded build. The zip around them was not produced by a command stored in git. A reconstruction from the installer file does reproduce the published zip bytes. A future pack does not aim at those bytes.

## Proven installer

`OrbitRxMonitor-Setup.exe` inside `OrbitRx-Setup-5.1.0.zip` is byte-identical to the file in Actions artifact `OrbitRx-windows-unsigned` from run `42004653668`.

- Commit: `304db03d99604af20da0b49ee2f3894ab17e2cc9`
- Installer SHA-256: `4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8`
- Job log: Python 3.12.10, PyInstaller 6.22.3, Inno Setup compiler engine 6.7.1, `iscc "/DAppVer=$ver" installer\OrbitRxMonitor.iss`
- `osslsigncode` on that exe: no signature. PE checksum field `00000000`, calculated `0F60B2DC`
- Version resource: CompanyName `thevenom`, FileVersion `5.1.0.0`, ProductVersion `5.1.0`

The release workflow on this commit does not publish. The changelog still says 5.1.0 is not yet released. Nothing in this branch uploads a release or replaces that exe.

## Published digest, and what was actually hashed

These are separate checks.

- `https://thevenom.dev/downloads/orbitrx/SHA256SUMS.txt` was fetched on 7 November 2026 (HTTP 200). Its checksum line is `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b  OrbitRx-Setup-5.1.0.zip` (two spaces before the filename). That is a text file on the website. It is not the zip bytes.
- `tools/pack_setup_zip.py --historical-observed`, given the Actions artifact `OrbitRxMonitor-Setup.exe`, writes a zip whose SHA-256 is that same digest. The deflate stream is `zlib.compressobj(9, zlib.DEFLATED, -15)` of those installer bytes. Observed headers: one member `OrbitRxMonitor-Setup.exe`, method 8, flag 0, no extra field, no comment, version needed 20, version made by `0x0314`, external attributes `0x81A40000`, DOS time `20601`, DOS date `23909` (2026-11-05 10:03:50), 257,486,082 bytes. This reconstruction does not download `downloads.thevenom.dev`.
- A later read of `https://downloads.thevenom.dev/orbitrx/OrbitRx-Setup-5.1.0.zip` received a Cloudflare challenge and did not hash the live object. Do not treat the reconstruction as a fresh hash of that URL.

The reconstruction is not a command found in git. No command in git or in the Actions workflow writes `OrbitRx-Setup-5.1.0.zip`. The CI `SHA256SUMS.txt` hashes the two exes and does not contain the zip digest.

## Future packs

The default of `tools/pack_setup_zip.py` also uses raw deflate level 9 and the same header shape, but it takes the DOS time from the input file's modification time. It does not force 2026-11-05 10:03:50. A new installer, or the same installer with a different timestamp, will not come out as `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`. Use the default for a pack you build later. Use `--historical-observed` only to check the 5 November 2026 archive against the known installer bytes.

This branch does not publish either zip. The onedir spec on this head is an unpublished recipe. It does not alter `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b` or the Actions installer `4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8`.
