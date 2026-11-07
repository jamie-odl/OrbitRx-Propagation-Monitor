# Distribution materials

The unpublished recipe on this head is a PyInstaller onedir. It does not replace the 5 Nov 2026 one-file installer. Copying licence text is not clearance. The release gate stays closed. See the blockers in `packaging/distribution_manifest.json`.

## What the 5 Nov 2026 exe actually contained

Actions run `42004653668` produced `OrbitRxMonitor.exe` and `OrbitRxMonitor-Setup.exe`. That archive contains `world_map.jpg`, `LICENSE` (MIT, first-party), `NOTICE`, `PRIVACY.md`, and the bundled Leaflet BSD text. `Qt6Core.dll` and `Qt6WebEngineCore.dll` are in the exe, with the rest of the Qt6 DLLs that PyInstaller collected. `win10toast` is in the PYZ because `orbitrx/alerts.py` imports it. `pystray` was installed on that job and was not imported and was not in the PYZ.

That installer does not contain a GPL text, an LGPL text, a Qt source offer, relink objects, or a Chromium credits file. This commit does not replace those bytes.

## Unpublished onedir

`OrbitRxMonitor.spec` sets `exclude_binaries=True` and `COLLECT`, so Qt shared libraries are files beside the executable. `docs/REPLACING_QT_LIBRARIES.md` says how to replace them. That layout has not been built on Windows in this workspace. A Linux PyInstaller run was not treated as a Windows execution.

WebEngine stays. The default map is static and does not need it. The interactive Leaflet backend does. Dropping WebEngine would remove that backend, so it was not removed.

Qt libraries are packaged for the LGPL-3.0-only alternative in the upstream SPDX line. That is not a commercial purchase and not a statement that the LGPL duties are finished. `docs/QT_SOURCE_OFFER_DRAFT.md` is a draft. It is not an offer.

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

1. The copyright holder has not published a source offer. `docs/QT_SOURCE_OFFER_DRAFT.md` is only a draft. `third_party/corresponding-source/` holds the official PySide6 6.12.0 source archive, the official qtbase 6.12.0 source archive, and a git archive of qtwebengine branch `6.12` at `d4735ce` without the Chromium submodule. That is not the WebEngine/Chromium corresponding source and it is not an offer.
2. Actions run 42362357356, commit `3736e29`, built the onedir on windows-latest. Qt6Core.dll and Qt6WebEngineCore.dll were separate files under `_internal/PySide6/`. Static and interactive captures both exited 0. An earlier run, 42359055614, had exited -1073741819 on the static capture before that shutdown change.
3. `LICENSE.Chromium` from qtwebengine branch `6.12` is included. The gn-generated third-party credits file is not. The PySide6-WebEngine 6.12.0.140 Windows wheel has no such file; `qtwebengine_resources.pak` did not contain an about:credits document; submodule `71a2fa55e2e2f5a5d6567aac93bda8775fc7b084` is the chromium tree the branch points at, and the credits are produced by `cmake/QtGnCredits.cmake` at build time.

## Other open decisions

- The copyright holder has not published the source offer. The draft is not that publication.
- The gn-generated Chromium third-party credits file is still absent.
- The Windows onedir build in run 42362357356 exited 0 for both captures. That run is not a release.
- `world_map.jpg` and the v2 images are no longer selected. Their old provenance questions remain for those historical files only.
