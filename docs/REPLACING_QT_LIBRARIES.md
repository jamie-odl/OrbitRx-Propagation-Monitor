# Replacing Qt libraries

PyInstaller 6 writes `OrbitRxMonitor.exe` beside `_internal/`. PySide6 loads the Qt shared libraries from `_internal/PySide6/`. Replacing one of those DLLs with another build of the same Qt 6.12.0 module, then starting `OrbitRxMonitor.exe` again, is the relink step. Do not rename the folder. `ne_110m_dark.png` in `_internal/` is the map, not a Qt library.

Windows runs have shown these as separate files, not packed inside the exe:

- `_internal/PySide6/Qt6Core.dll`
- `_internal/PySide6/Qt6WebEngineCore.dll`

To rebuild a Qt library, use the archives named in `docs/QT_SOURCE_OFFER_DRAFT.md`. The local GN argument log is a configure this repository ran. It is not Qt's record of how the PySide6-WebEngine 6.12.0.140 wheel was built. `third_party/qt/qtpdf-args-AMD64.gn` is the PDF module's `args.gn` from that same local configure, not QtWebEngineCore.

The interactive map needs Qt WebEngine. The default map is the static Natural Earth image and does not. Removing WebEngine would drop the interactive backend, so this packaging keeps it.

Corresponding source for Qt and PySide6 is identified in `docs/QT_SOURCE_OFFER_DRAFT.md`. That draft is not an offer and has not been published.
