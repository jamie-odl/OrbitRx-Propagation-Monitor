# Replacing Qt libraries

PyInstaller 6 writes `OrbitRxMonitor.exe` beside `_internal/`. PySide6 loads the Qt shared libraries from `_internal/PySide6/`. Replacing one of those DLLs with another build of the same Qt 6.12.0 module, then starting `OrbitRxMonitor.exe` again, is the relink step. Do not rename the folder. `ne_110m_dark.png` in `_internal/` is the map, not a Qt library.

Windows runs have shown this as a separate file, not packed inside the exe:

- `_internal/PySide6/Qt6Core.dll`

To rebuild a Qt library, use the plain Qt/PySide6 archives named in `docs/QT_SOURCE_OFFER_DRAFT.md`.

Option B (2026-11-09): the map is drawn natively with Qt Widgets; there is no
longer an embedded-browser map backend. Qt WebEngine, Qt WebChannel and the
Chromium code they depended on are excluded from this build (see
`OrbitRxMonitor.spec`), so `Qt6WebEngineCore.dll` and the other WebEngine
DLLs no longer ship and there is nothing to relink there. The local GN
argument log and `third_party/qt/qtpdf-args-AMD64.gn` describe a past
configure of the now-removed WebEngine module and are historical only.

Corresponding source for Qt and PySide6 is identified in `docs/QT_SOURCE_OFFER_DRAFT.md`. That draft is not an offer and has not been published.
