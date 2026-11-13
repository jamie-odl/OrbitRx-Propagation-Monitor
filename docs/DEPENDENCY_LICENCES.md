# Dependency licences for the matching 5.1.0 build

Actions run `42004653668` (commit `304db03d99604af20da0b49ee2f3894ab17e2cc9`) installed the versions below. `requirements.txt` on that commit still uses ranges. The sentences here are from the upstream licence files for those versions, not from a PyPI classifier by itself. This file does not relicense OrbitRx. `LICENSE` is unchanged.

| Component | File that was read | What that file says |
| --- | --- | --- |
| Pillow 13.0.0 | `LICENSE` at Pillow tag `13.0.0` | "Pillow is licensed under the open source MIT-CMU License." Copyright lines for Secret Labs AB, Fredrik Lundh, and Jeffrey 'Alex' Clark. |
| matplotlib 3.11.2 | `LICENSE/LICENSE` at tag `v3.11.2` | Title: "License agreement for matplotlib versions 1.3.0 and later." Parties are the Matplotlib Development Team and the licensee. This is not the PSF licence text. PyPI's classifier "Python Software Foundation License" is a different string from this file. |
| pyserial 3.5 | `LICENSE.txt` at tag `v3.5` | Three-clause BSD. The file's own note says `SPDX-License-Identifier: BSD-3-Clause`. Copyright 2001-2020 Chris Liechti. |
| pywin32 release `b312` | `win32/License.txt` at that tag | Three-clause BSD. Copyright 1994-2008 Mark Hammond. The file does not say PSF. In this tree, `orbitrx/spots/omnirig.py` imports `win32com.client`. `orbitrx/alerts.py` imports `win10toast` and does not import pywin32. |
| PySide6 6.12.0 / Qt | `src/corelib/global/qtcoreglobal.h` at qtbase tag `v6.12.0` | First licence line: `SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. The private prospective packaging route in `docs/DISTRIBUTION.md` is LGPL-3.0-only for the Qt libraries. That is not clearance, not a published offer, and not use of the commercial alternative. |
| win10toast 0.9 | `third_party/win10toast/LICENSE`, byte copy of repository `LICENSE` at commit `76d491638b` | MIT, copyright 2017 Jithu R Jacob. The 0.9 wheel contains no licence file and its METADATA says BSD. `orbitrx/alerts.py` imports it. |
| pystray 0.19.5 | Not bundled | The 5 Nov job installed it because `requirements.txt` asked for it. Nothing under `orbitrx/` imports it. The tray is `QSystemTrayIcon`. It was not in the exe PYZ. It is removed from `requirements.txt` here so a later build does not install it. Its LGPL terms are not an obligation of the frozen exe. |
| PyInstaller 6.22.3 | `COPYING.txt` at tag `v6.22.3` | GPL version 2 or any later version, plus the Bootloader Exception for linking the bootloader into a combined executable. The same file licenses run-time hooks and fake-modules under Apache-2.0, and `PyInstaller.isolated` additionally under MIT. Build tool only. |
| Leaflet 1.9.4 | `orbitrx/ui/assets/leaflet/LICENSE-leaflet.txt` in this tree | BSD 2-Clause. Copyright 2010-2023 Volodymyr Agafonkin and 2010-2011 CloudMade. |
| OpenSSL 3 | `third_party/openssl/LICENSE.txt`, byte copy of `openssl/openssl` tag `openssl-3.0.0` `LICENSE.txt` | Apache License 2.0. Two copies ship: `_internal/libcrypto-3.dll` and `_internal/libssl-3.dll` are the CPython 3.12 runtime's own OpenSSL, loaded by `_ssl.pyd` for every `urllib` HTTPS request OrbitRx makes; `_internal/libcrypto-3-x64.dll` and `_internal/libssl-3-x64.dll` are a second copy, collected by PyInstaller's Qt hook for the Qt `tls` plugin `qopensslbackend.dll`. |

`customtkinter` is not imported and is not in `requirements.txt` here. The changelog on this commit records that it was removed. The PyPI CC0-versus-MIT disagreement for that project does not apply to this tree.

No map SDK and no paid map key are dependencies.
