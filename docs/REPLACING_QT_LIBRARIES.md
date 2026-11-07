# Replacing Qt libraries

This describes the unpublished onedir layout. It is not a record of the 5 Nov 2026 one-file exe, and it has not been executed on Windows.

PyInstaller `COLLECT` writes `dist/OrbitRxMonitor/`. The executable is `OrbitRxMonitor.exe` on Windows or `OrbitRxMonitor` on Linux. Qt shared libraries are files in that same directory, not packed inside the executable:

- Windows: `Qt6Core.dll`, `Qt6WebEngineCore.dll`, and the other `Qt6*.dll` files the build collects.
- Linux: `libQt6Core.so.6`, `libQt6WebEngineCore.so.6`, and the other `libQt6*.so*` files.

To use a different build of a Qt library, replace that file with a build of the same Qt module version (6.12.0 for the libraries PySide6 6.12.0 / PySide6-WebEngine 6.12.0.140 were built against) and start the executable again. Do not rename the executable's folder. The basemap file `ne_110m_dark.png` in that folder is not a Qt library.

The interactive map needs Qt WebEngine. The default map is the static Natural Earth image and does not. Removing WebEngine would drop the interactive backend, so this packaging keeps it.

Corresponding source for Qt and PySide6 is identified in `docs/QT_SOURCE_OFFER_DRAFT.md`. That draft is not an offer and has not been published.
