# Distribution materials

The unpublished recipe on this head is a PyInstaller onedir. It does not replace the 5 Nov 2026 one-file installer. Copying licence text is not clearance. The release gate stays closed. See the blockers in `packaging/distribution_manifest.json`.

## What the 5 Nov 2026 exe actually contained

Actions run `42004653668` produced `OrbitRxMonitor.exe` and `OrbitRxMonitor-Setup.exe`. That archive contains `world_map.jpg`, `LICENSE` (MIT, first-party), `NOTICE`, `PRIVACY.md`, and the bundled Leaflet BSD text. `Qt6Core.dll` and `Qt6WebEngineCore.dll` are in the exe, with the rest of the Qt6 DLLs that PyInstaller collected. `win10toast` is in the PYZ because `orbitrx/alerts.py` imports it. `pystray` was installed on that job and was not imported and was not in the PYZ.

That installer does not contain a GPL text, an LGPL text, a Qt source offer, relink objects, or a Chromium credits file. This commit does not replace those bytes.

## Unpublished onedir

`OrbitRxMonitor.spec` sets `exclude_binaries=True` and `COLLECT`, so Qt shared libraries are files beside the executable. `docs/REPLACING_QT_LIBRARIES.md` says how to replace them. That layout has not been built on Windows in this workspace. A Linux PyInstaller run was not treated as a Windows execution.

**Superseded 2026-11-09 (Option B):** the paragraph below described the decision
on the WebEngine-era 5.1.0 line. On `feat/native-map-no-webengine-2026-11-09`,
Live Spots were ported to the native `PropagationMapWidget` and the Leaflet/
WebEngine backend (`orbitrx/ui/leaflet_map.py`) was deleted, so WebEngine is
excluded from this build's spec. The rest of this section (the 5 Nov 2026 exe,
run `42362357356`, the hosted corresponding-source hashes) is unchanged
historical fact about builds that predate this branch.

~~WebEngine stays. The default map is static and does not need it. The interactive Leaflet backend does. Dropping WebEngine would remove that backend, so it was not removed.~~

Qt libraries are packaged for the LGPL-3.0-only alternative in the upstream SPDX line. That is not a commercial purchase and not a statement that the LGPL duties are finished. `docs/QT_SOURCE_OFFER_DRAFT.md` records the corresponding-source archives now hosted and hash-verified by a public HTTPS GET on 2026-11-08. Hosting is verified; that verification is not by itself legal clearance.

`third_party/qt/LICENSE.Chromium` is the file from qtwebengine branch `6.12` (Chromium 140.0.7339.264). The gn-generated about-credits list was not in the PySide6-WebEngine 6.12.0.140 wheel.

## Texts added for a later build

Exact upstream files, not paraphrases:

| Path | Source |
| --- | --- |
| `third_party/qt/LICENSES/LGPL-3.0-only.txt` | qtbase tag `v6.12.0` `LICENSES/` |
| `third_party/qt/LICENSES/GPL-2.0-only.txt` | same |
| `third_party/qt/LICENSES/GPL-3.0-only.txt` | same |
| `third_party/qt/LICENSES/LGPL-2.1-or-later.txt` | same. Qt's WebEngine licensing page says the most restrictive Chromium licence in that module is LGPL 2.1. |
| `third_party/qt/LICENSES/Qt-GPL-exception-1.0.txt` | same. This is The Qt Company's exception text. It is not an election and it does not licence OrbitRx. |
| `third_party/qt/qtcoreglobal.h.SPDX.txt` | The `SPDX-License-Identifier` line from `src/corelib/global/qtcoreglobal.h` at qtbase `v6.12.0`. |
| `third_party/win10toast/LICENSE` | `LICENSE` at commit `76d491638b5643dab7a3d6a483731df5de8deca9` |
| `third_party/pillow/LICENSE` | Pillow tag `13.0.0` |
| `third_party/matplotlib/LICENSE` | matplotlib tag `v3.11.2` `LICENSE/LICENSE` |
| `third_party/pyserial/LICENSE.txt` | pyserial tag `v3.5` |
| `third_party/pywin32/License.txt` | pywin32 tag `b312` `win32/License.txt` |
| `third_party/pyinstaller/COPYING.txt` | PyInstaller tag `v6.22.3` |

The onedir spec carries `basemap/ne_110m_dark.png` and the `third_party` texts. It does not carry `world_map.jpg`.

`tools/check_distribution_manifest.py --release` exits non-zero while the manifest blockers are open. The manual release workflow runs that command and uploads nothing.

## What is still not clearance

`qtcoreglobal.h` offers `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. This packaging uses the LGPL-3.0-only alternative for the Qt libraries. That is not a commercial licence and it does not finish the LGPL duties:

1. The corresponding source bytes are hosted and hash-verified by a public HTTPS GET on 2026-11-08 (~19:35 GMT, UTC+0) at `https://downloads.thevenom.dev/orbitrx/`: `pyside-setup-everywhere-src-6.12.0.tar.xz` (sha256 `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751`), `qt-everywhere-src-6.12.0.tar.xz` (sha256 `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165`), and `qtwebengine-everywhere-src-6.140.0-rc.tar.xz` (sha256 `61257967afd9803a1db6403e86ea25c4efff8fad479bda365a9d81bfd709f621`, qtwebengine commit `d505fc23640d2bd6345e6483eb73daf4e19f5829`, chromium submodule `39352427a3245a19fb395547b3aa38be9d091ec4`). The earlier private pins, `qtwebengine-6.12-d4735ce.tar.xz` and `qtwebengine-chromium-71a2fa55.tar`, are superseded -- they are not the shipped build's source and must not be presented as current. `docs/QT_SOURCE_OFFER_DRAFT.md` has the verified table, the publish-ready paragraph, and the hosting-verification note. `packaging/distribution_manifest.json` records the same URLs, sizes, and hashes under `corresponding_source`. The release gate still carries the open blocker `final-public-candidate-gate-pending` (the NOTICE path fix rebuild is not yet gated), so the public release gate stays closed.
2. Actions run 42362357356, commit `3736e29`, built the onedir on windows-latest. Qt6Core.dll and Qt6WebEngineCore.dll were separate files under `_internal/PySide6/`. Static and interactive captures both exited 0. An earlier run, 42359055614, had exited -1073741819 on the static capture before that shutdown change.
3. `third_party/qt/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt` (SHA-256 `acde5959267a8afbd29c04f776f228ef6d208fa8a632bf356204174de5c460ca`, 1,026,119 bytes) is the vendor-SBOM-derived notices file, generated offline by `gen_notices.py` from Qt vendor SPDX SBOMs for qtwebengine commit `d505fc23640d2bd6345e6483eb73daf4e19f5829` (tag `v6.140.0-rc`) and Chromium submodule `39352427a3245a19fb395547b3aa38be9d091ec4`. That is vendor-SBOM inference, not a GN-identity proof that the generated graph matches this build's own configure. It supersedes `third_party/qt/chromium_attributions.qdoc` (the former gn-walk credits file, SHA-256 `b2382a81239e6c100a3f96342909c6c7e7ecec12fb93e6fe91a5aa3bf756c0ec`, generated against the now-superseded qtwebengine `d4735ce` / Chromium `71a2fa55` pins) and that file's regeneration path, `docs/REGENERATE_CREDITS.ps1` (the regenerate-credits workflow); both are superseded and must not be run. `LICENSE.Chromium` is still only the BSD text. The applicable conveyance clause for this downloadable onedir is GPL-3.0 section 6(d), incorporated via LGPL-3.0 section 4, not the physical-product written-offer clause in section 6(b); see `docs/QT_SOURCE_OFFER_DRAFT.md` (hosting verified 2026-11-08).

## Other open decisions

- The copyright holder has not published the source offer as a release artifact; hosting the bytes and verifying the hashes is not that publication act.
- The Chromium third-party notices file is `third_party/qt/THIRD_PARTY_NOTICES_QtWebEngine-6.140.0.txt` (vendor-SBOM-derived; supersedes the former gn-generated `third_party/qt/chromium_attributions.qdoc`, and its regeneration path `docs/REGENERATE_CREDITS.ps1` is likewise superseded and must not be run). The source archives are now publicly hosted and hash-verified; see `docs/QT_SOURCE_OFFER_DRAFT.md` and `packaging/distribution_manifest.json`. The two earlier private pins, `qtwebengine-6.12-d4735ce.tar.xz` and `qtwebengine-chromium-71a2fa55.tar`, are superseded and are not current source.
- The Windows onedir build in run 42362357356 exited 0 for both captures. That run is not a release.
- `world_map.jpg` and the v2 images are no longer selected. Their old provenance questions remain for those historical files only.
