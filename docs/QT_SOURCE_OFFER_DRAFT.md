# DRAFT — not an offer

This text is prepared for review. It is not a written offer by the copyright holder. It has not been published, posted, or attached to a release. `tools/check_distribution_manifest.py --release` stays closed until the copyright holder publishes an offer or ships the corresponding source.

If published later, a sufficient offer for the Qt libraries used by an OrbitRx onedir build would name:

- PySide6 6.12.0 and PySide6-WebEngine 6.12.0.140, the versions installed by Actions run `42004653668`.
- Qt tag `v6.12.0` for qtbase, which is the tag whose `LICENSES/` files are copied in `third_party/qt/LICENSES/`.
- Qt WebEngine branch `6.12`. `CHROMIUM_VERSION` on that branch, read 7 November 2026, says the base is Chromium `140.0.7339.264` and security patches go up to Chromium `151.0.7922.108`. Chromium submodule `qtwebengine-chromium` commit `71a2fa55e2e2f5a5d6567aac93bda8775fc7b084`.
- The packaging route prepared here: LGPL-3.0-only for the Qt Project libraries, which is one alternative in `qtcoreglobal.h` (`LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`). Chromium code inside WebEngine stays under its own licences. `third_party/qt/LICENSE.Chromium` is the BSD text from that WebEngine branch. It is not the gn-generated third-party credits file.

Accessible source locations, checked as existing tags or branches, not as a promise to host them:

- https://github.com/pyside/pyside-setup/tree/v6.12.0
- https://github.com/qt/qtbase/tree/v6.12.0
- https://github.com/qt/qtwebengine/tree/6.12
- https://github.com/qt/qtwebengine-chromium/tree/71a2fa55e2e2f5a5d6567aac93bda8775fc7b084
- https://download.qt.io/official_releases/qt/6.12/6.12.0/

The gn credits step is `cmake/QtGnCredits.cmake` on qtwebengine `6.12`. Its output was not a file in the PySide6-WebEngine 6.12.0.140 Windows wheel (file list and `qtwebengine_resources.pak` were inspected). That generated credits file is still a release blocker.
