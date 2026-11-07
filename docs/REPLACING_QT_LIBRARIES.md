# Replacing Qt libraries

This describes the unpublished onedir layout. It is not a record of the 5 Nov 2026 one-file exe, and it has not been executed on Windows.

PyInstaller 6 writes `dist/OrbitRxMonitor/OrbitRxMonitor.exe` and puts collected files in `dist/OrbitRxMonitor/_internal/`. A Windows run of commit `ef8ebd6` (Actions run 42357631996) compressed these separate files, which are not inside the exe:

- `_internal/PySide6/Qt6Core.dll`
- `_internal/PySide6/Qt6WebEngineCore.dll`
- `_internal/ne_110m_dark.png`

Replace a Qt DLL in `_internal/PySide6/` with a build of the same module from Qt 6.12.0 / PySide6 6.12.0 and PySide6-WebEngine 6.12.0.140, then start `OrbitRxMonitor.exe` again. Do not rename the folder. `ne_110m_dark.png` is the map, not a Qt library. Linux library names were not produced by that Windows run.

The interactive map needs Qt WebEngine. The default map is the static Natural Earth image and does not. Removing WebEngine would drop the interactive backend, so this packaging keeps it.

Corresponding source for Qt and PySide6 is identified in `docs/QT_SOURCE_OFFER_DRAFT.md`. That draft is not an offer and has not been published.
