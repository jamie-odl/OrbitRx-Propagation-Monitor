# Distribution materials for the frozen app

This file describes the Windows exe built from this tree. It does not publish a build and it does not choose a Qt licence. Copying a licence text into `third_party/` is not compliance by itself.

## What the 5 Nov 2026 exe actually contained

Actions run `42004653668` produced `OrbitRxMonitor.exe` and `OrbitRxMonitor-Setup.exe`. That archive contains `world_map.jpg`, `LICENSE` (MIT, first-party), `NOTICE`, `PRIVACY.md`, and the bundled Leaflet BSD text. `Qt6Core.dll` and `Qt6WebEngineCore.dll` are in the exe, with the rest of the Qt6 DLLs that PyInstaller collected. `win10toast` is in the PYZ because `orbitrx/alerts.py` imports it. `pystray` was installed on that job and was not imported and was not in the PYZ.

That installer does not contain a GPL text, an LGPL text, a Qt source offer, relink objects, or a Chromium credits file. This commit does not replace those bytes.

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

`OrbitRxMonitor.spec` and `installer/OrbitRxMonitor.iss` now list those paths so a later build can carry them. The spec still packages `world_map.jpg` only.

`tools/check_distribution_manifest.py` checks those files against `packaging/distribution_manifest.json`. `--release` exits non-zero while the blockers below are open. The manual release workflow runs that command and uploads nothing.

## Owner decision: Qt

`qtcoreglobal.h` at Qt 6.12.0 offers the Qt libraries under `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. This repository does not hold a Qt commercial licence, and this change does not elect one of the open-source terms.

Safe open-source route, not adopted: ship Qt under **LGPL-3.0-only** for the Qt Project parts, and meet LGPL-2.1 for the Chromium code inside Qt WebEngine, using the texts already copied here. Remaining technical requirements if that route is chosen:

1. A written offer, or the corresponding source, for the Qt and PySide6 libraries that were linked, kept available on the terms those licences state. This tree does not make that offer.
2. Installation information so a recipient can replace those libraries in the user product. The onefile exe packs `Qt6Core.dll` and `Qt6WebEngineCore.dll` inside the archive. Replacing them is not something this build documents or supports. Shipping the Qt DLLs beside the exe, instead of only inside the onefile archive, is the usual technical shape. It was not done.
3. The Chromium third-party credits file that Qt WebEngine builds from the Chromium tree. It is not in the qtwebengine git tag as `src/3rdparty/chromium/LICENSE` (that URL 404s; Chromium is not in that git checkout). No substitute list was written.

Until those three exist, and until an owner records the election, `tools/check_distribution_manifest.py --release` fails.

## Other open decisions

- Licence of `world_map.jpg`. The Commons original is a different file. See `docs/MAP_IMAGE.md`.
- Licence of `static_basemap_v2.png` and `.webp`. The Natural Earth candidate is not the default.
