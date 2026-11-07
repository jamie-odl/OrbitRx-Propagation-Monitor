# Published builds and this tree

This file records what was checked on 7 November 2026. It does not publish a new build. The verified downloads were not modified.

`origin/main` at that check was `43a35a8` (`chore: run Linux CI on self-hosted obsidian runner`). Tag `v5.0.0` is `6a3e1c60794b22e460222fb4673c556b000e9cad`. Those two commits differ only in `.github/workflows/ci.yml` and `START_HERE.txt`. Neither file is an input to `OrbitRxMonitor.spec`. That does not make `main` a byte-for-byte rebuild of either published file. Application version in this tree is `5.0.0` (`orbitrx/__init__.py`, `pyproject.toml`).

## Channel summary

| Channel | File | Source that was actually built | Digest |
| --- | --- | --- | --- |
| GitHub Release `v5.0.0` | `OrbitRxMonitor.exe` (253,660,999 bytes) | Tag `v5.0.0`, commit `6a3e1c60794b22e460222fb4673c556b000e9cad` | GitHub asset digest `sha256:5bd2485d0821bb2c61fda8de15d6dda5ac25eb19e6ff6de65cd33e6961afc57b` |
| thevenom.dev, 5 November 2026 | `OrbitRx-Setup-5.1.0.zip` (257,486,082 bytes) wrapping `OrbitRxMonitor-Setup.exe` (257,990,884 bytes) | `304db03d99604af20da0b49ee2f3894ab17e2cc9` on `feat/merge-matrix-2026-11-04`, which is not `main` | Zip `sha256:bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`. Installer exe `sha256:4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8` |

`main` is an ancestor of `304db03`, and so is tag `v5.0.0`. The 5.1.0 installer is the later branch tip, not the tree this file is committed on.

## GitHub Release v5.0.0

- Release: https://github.com/jamie-odl/OrbitRx-Propagation-Monitor/releases/tag/v5.0.0
- The `thevenomv/OrbitRx-Propagation-Monitor` path resolves to that same repository. This tree's update checker still calls `thevenomv/OrbitRx-Propagation-Monitor`.
- Actions run `27161875203` (`build-windows`, success) has `headSha` `6a3e1c60794b22e460222fb4673c556b000e9cad` and `headBranch` `v5.0.0`.
- Recipe in `.github/workflows/release.yml` at that tag: `windows-latest`, `actions/setup-python` with `python-version: "3.12"`, `pip install -r requirements.txt`, `python -m pytest tests/ -q`, `pyinstaller OrbitRxMonitor.spec --noconfirm`, upload `dist/OrbitRxMonitor.exe` with `softprops/action-gh-release@v2`. The workflow does not run Inno Setup and has no Authenticode or `signtool` step.
- `OrbitRxMonitor.spec` sets PyInstaller's `codesign_identity=None`. That field is not a Windows Authenticode signature.
- The asset digest above is the `digest` field on the GitHub Release asset. This investigation did not download the 253,660,999-byte exe again, so that digest was not recomputed locally and the exe's certificate table was not inspected.
- Job-log download for job `80179124363` returned HTTP 410. The resolved pip set, PyInstaller version, runner image digest, and whether UPX ran are not recoverable from that log. `requirements.txt` on the tag uses version ranges, not pins. `OrbitRxMonitor.spec` sets `upx=True`.

`installer/OrbitRxMonitor.iss` in this tree is version `5.0.0`, `AppPublisher=OrbitRx`, and `OutputBaseFilename=OrbitRxMonitor-Setup`. The v5.0.0 workflow never compiled it. It is not the script that produced the 5.1.0 installer (that script is on commit `304db03` and sets `AppPublisher=thevenom`).

## thevenom.dev 5.1.0

Product page: https://thevenom.dev/tools/orbitrx/

Checked wording on that page:

- Platform: Windows desktop. macOS, Linux, phones, and tablets are listed as not supported.
- Licence: MIT. Publisher: thevenom. Version: 5.1.0. Released and last updated: 2026-11-05.
- Signed: "No. Verify with SHA-256 instead."
- Download: `https://downloads.thevenom.dev/orbitrx/OrbitRx-Setup-5.1.0.zip`, size 246 MB, SHA-256 `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`.
- Map: "offline, self-hosted tiles", no map API key, pin starts in London until the user sets a location.
- The page says the zip hash is also in `SHA256SUMS.txt`. That filename is not a member of the zip.

The zip was downloaded and hashed locally. SHA-256 matches the page. It is a deflate zip (method 8), creator system Unix, no archive comment, one member:

- `OrbitRxMonitor-Setup.exe`, 257,990,884 bytes, stored timestamp 2026-11-05 10:03:50

That exe is byte-identical to `OrbitRxMonitor-Setup.exe` in Actions artifact `OrbitRx-windows-unsigned` from run `42004653668` (https://github.com/jamie-odl/OrbitRx-Propagation-Monitor/actions/runs/42004653668). The artifact's `SHA256SUMS.txt` is:

```
4cb3c4d0774218b0b39e05d9f4ca3dc2609c367349f1383f60d378a0d89642d8  OrbitRxMonitor-Setup.exe
71cfc3574c018e472d7ae26f034706bde7742b302eb0d04c71705448d41f043a  OrbitRxMonitor.exe
```

Run `42004653668` is the push of `304db03d99604af20da0b49ee2f3894ab17e2cc9` on `feat/merge-matrix-2026-11-04`. The Windows build job log shows Python 3.12.10, Inno Setup compiler engine 6.7.1, and `iscc "/DAppVer=$ver" installer\OrbitRxMonitor.iss`. The same log's resolved install line was:

`PySide6-6.12.0 PySide6_Addons-6.12.0 PySide6_Essentials-6.12.0 PySide6_Pdf-6.12.0.140 PySide6_WebEngine-6.12.0.140 altgraph-0.17.5 contourpy-1.4.0 cycler-0.12.1 fonttools-4.68.0 iniconfig-2.3.1 kiwisolver-1.5.1 matplotlib-3.11.2 numpy-2.5.4 pefile-2024.8.26 pillow-13.0.0 pluggy-1.7.0 pygments-2.21.0 pyinstaller-6.22.3 pyinstaller-hooks-contrib-2026.9 pyparsing-3.3.3 pypiwin32-223 pyserial-3.5 pystray-0.19.5 pytest-9.2.0 python-dateutil-4.0.0 pywin32-312 pywin32-ctypes-0.2.3 setuptools-84.2.1 shiboken6-6.12.0 six-1.17.0 tzdata-2026.6 win10toast-0.9`

That list is what the matching run installed. It is not a lockfile in the commit. `requirements.txt` at `304db03` still uses ranges. `customtkinter` is not in that list. Re-running the workflow later can resolve different versions.

`osslsigncode verify` on the shipped installer (the same bytes as the artifact) reported no signature, PE checksum field `00000000`, and calculated checksum `0F60B2DC`. The version resource reads CompanyName `thevenom`, ProductName `OrbitRx Propagation Monitor`, FileVersion `5.1.0.0`, ProductVersion `5.1.0`, LegalCopyright `Copyright 2026 thevenom`. A plaintext string in the stub says `Inno Setup Setup Data (6.7.0)`. The compiler log says engine `6.7.1`. Those are two different observations (setup-data label versus compiler engine). `innoextract` 1.9 cannot list the payload ("Could not determine setup data version"), so files inside the installer were not extracted. The job log does show ISCC compressing `OrbitRxMonitor.exe`, `world_map.jpg`, `assets/orbitrx.ico`, `LICENSE`, `NOTICE`, and `PRIVACY.md` from that commit.

No workflow in either commit writes `OrbitRx-Setup-5.1.0.zip` or uploads it to `downloads.thevenom.dev`. The release workflow at `304db03` is a manual placeholder that does not publish. The commit's `CHANGELOG.md` still says `## [5.1.0] - not yet released`. The website published a zip of that commit's CI installer anyway.

### Behaviour of commit 304db03, which the installer matches

These facts are from that commit, not from this tree:

- `orbitrx/__init__.py` is `5.1.0`.
- Default `home_lat` / `home_lon` are `51.5081` / `-0.1281`, commented in `orbitrx/config.py` as London centre. `ip_geolocation_enabled` defaults to false.
- `map_backend` defaults to `static`. Leaflet uses bundled Leaflet and a local image overlay (`static_basemap_v2.png`, then `.webp`, then `world_map.jpg`). The page is built with `file://` URLs. That commit's `leaflet_map.py` says it does not use Carto or a CDN tile server. There is no paid map API key in config.
- The product page's phrase "self-hosted tiles" is the page's description. The matching source uses one local equirectangular image overlay, not a remote slippy-tile server.

### Behaviour of this tree

- No `home_lat`. Location refresh calls `https://ipinfo.io/json` and clears the coordinates on failure. There is no London default.
- `map_backend` defaults to `static`, using vendored `world_map.jpg` (offline raster, no map API key).
- Optional `map_backend` `leaflet` loads Leaflet 1.9.4 from `https://unpkg.com/leaflet@1.9.4/` and tiles from `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png` with attribution `OSM` and `CARTO`. That path is not self-hosted and is not the 5.1.0 page's map.
- Other network used by this tree when those features run: NOAA SWPC `https://services.swpc.noaa.gov/products/`, HamQSL `https://www.hamqsl.com/solarxml.php`, DX cluster `dxc.ve7cc.net:23` and `nc7j.com:7373`, optional QRZ `https://xmldata.qrz.com/` if the user supplies `qrz_api_key`, Wikimedia `https://upload.wikimedia.org/wikipedia/commons/f/f2/Large_World_Map_bright.jpg` only when `world_map.jpg` is missing, and GitHub `api.github.com` for the update check. QRZ is not a map key. The example key is empty.

## Missing inputs

Still not recoverable:

- A lockfile, runner image digest, and UPX-on/off record for the v5.0.0 exe. The job log is HTTP 410. The published exe was not re-hashed or checked for a certificate table here.
- The command, tool, and timestamp policy that wrapped the 5.1.0 installer in `OrbitRx-Setup-5.1.0.zip`, and the step that put that zip on `downloads.thevenom.dev`.
- A website `SHA256SUMS.txt` whose contents match the zip. The CI `SHA256SUMS.txt` hashes the two exes and does not contain `bb8f087e041c13f868e6bb2ceb77c197760901aa478b3ee4ac9f9509efb2498b`.
- Payload listing from the installer. `innoextract` 1.9 does not understand this setup-data version, so the MIT text and `NOTICE` were not read back out of the exe. They are inputs in the matching job log and in commit `304db03`.
