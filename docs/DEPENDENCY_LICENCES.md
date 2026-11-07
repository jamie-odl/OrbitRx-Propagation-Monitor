# Dependency licences for the matching 5.1.0 build

Actions run `42004653668` (commit `304db03d99604af20da0b49ee2f3894ab17e2cc9`) installed the versions below. `requirements.txt` on that commit still uses ranges. The sentences here are from the upstream licence files for those versions, not from a PyPI classifier by itself. This file does not relicense OrbitRx. `LICENSE` is unchanged.

| Component | File that was read | What that file says |
| --- | --- | --- |
| Pillow 13.0.0 | `LICENSE` at Pillow tag `13.0.0` | "Pillow is licensed under the open source MIT-CMU License." Copyright lines for Secret Labs AB, Fredrik Lundh, and Jeffrey 'Alex' Clark. |
| matplotlib 3.11.2 | `LICENSE/LICENSE` at tag `v3.11.2` | Title: "License agreement for matplotlib versions 1.3.0 and later." Parties are the Matplotlib Development Team and the licensee. This is not the PSF licence text. PyPI's classifier "Python Software Foundation License" is a different string from this file. |
| pyserial 3.5 | `LICENSE.txt` at tag `v3.5` | Three-clause BSD. The file's own note says `SPDX-License-Identifier: BSD-3-Clause`. Copyright 2001-2020 Chris Liechti. |
| pywin32 release `b312` | `win32/License.txt` at that tag | Three-clause BSD. Copyright 1994-2008 Mark Hammond. The file does not say PSF. The previous NOTICE line "pywin32 (PSF)" was wrong. |
| PySide6 6.12.0 / Qt | `src/corelib/global/qtcoreglobal.h` at qtbase tag `v6.12.0` | First licence line: `SPDX-License-Identifier: LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. The old NOTICE line "LGPLv3" named only one of those. This note does not choose one. |
| pystray 0.19.5 | `pystray/__init__.py` inside the wheel, and the wheel's `COPYING` and `COPYING.LGPL` | The module header says GNU Lesser General Public License, version 3 or any later version. `COPYING.LGPL` is the LGPL-3 text. `COPYING` is GPL-3. Wheel metadata `License: LGPLv3` omits "or later". The header in the source is the more specific grant. |
| win10toast 0.9 | Repository file `LICENSE`, commit `76d491638b` (2017-07-21, "Added MIT License") | MIT, copyright 2017 Jithu R Jacob. That commit is earlier than the wheel timestamp 2018-01-26. There is no git tag `0.9`. The wheel has no `LICENSE` member. Its `METADATA` says `License: BSD` and its classifier says MIT. The conflict is resolved by the repository licence file, which is MIT. The wheel metadata was not treated as the grant. |
| PyInstaller 6.22.3 | `COPYING.txt` at tag `v6.22.3` | GPL version 2 or any later version, plus the Bootloader Exception for linking the bootloader into a combined executable. The same file licenses run-time hooks and fake-modules under Apache-2.0, and `PyInstaller.isolated` additionally under MIT. Build tool only. |
| Leaflet 1.9.4 | `orbitrx/ui/assets/leaflet/LICENSE-leaflet.txt` in this tree | BSD 2-Clause. Copyright 2010-2023 Volodymyr Agafonkin and 2010-2011 CloudMade. |

`customtkinter` is not imported and is not in `requirements.txt` here. The changelog on this commit records that it was removed. The PyPI CC0-versus-MIT disagreement for that project does not apply to this tree.

No map SDK and no paid map key are dependencies.
