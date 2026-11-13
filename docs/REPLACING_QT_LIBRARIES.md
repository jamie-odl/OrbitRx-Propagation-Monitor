# Replacing Qt libraries

PyInstaller 6 writes `OrbitRxMonitor.exe` beside `_internal/`. PySide6 loads the Qt shared libraries from `_internal/PySide6/`. Replacing one of those DLLs with another build of the same Qt 6.12.0 module, then starting `OrbitRxMonitor.exe` again, is the relink step. Do not rename the folder. `ne_110m_dark.png` in `_internal/` is the map, not a Qt library.

## Qt libraries shipped in this build (F1, 2026-11-12)

Windows runs have shown these as separate files, not packed inside the exe:

- `_internal/PySide6/Qt6Core.dll`
- `_internal/PySide6/Qt6Gui.dll`
- `_internal/PySide6/Qt6Widgets.dll`
- `_internal/PySide6/Qt6Network.dll`
- `_internal/PySide6/Qt6Svg.dll`

`opengl32sw.dll` (Qt's software OpenGL rasteriser fallback, built from Mesa llvmpipe) is in the PySide6 wheel but is not shipped: it is excluded by the ship-set filter (`tools/ship_set.py`), since nothing in `orbitrx/` creates a software-fallback `QOpenGLContext`. It is not a Qt module DLL and is not part of this relink list regardless.

`OrbitRxMonitor.spec` and its ship-set filter (`tools/ship_set.py`) drop Qt PDF, Qt Virtual Keyboard, Qt Quick/Qml, Qt OpenGL, and Qt WebEngine/WebChannel from the build (see "Removed Qt modules" below), so there is nothing to relink for any of those.

## Corresponding source offer

Corresponding source for the Qt and PySide6 libraries above is the offer in `NOTICE` (also packaged beside this file as `_internal/NOTICE`), repeated here because `docs/` itself is not packaged:

- `https://downloads.thevenom.dev/orbitrx/pyside-setup-everywhere-src-6.12.0.tar.xz`
  (sha256 `099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751`) -- PySide6 and Shiboken6.
- `https://downloads.thevenom.dev/orbitrx/qt-everywhere-src-6.12.0.tar.xz`
  (sha256 `98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165`) -- the single official Qt source archive, covering qtbase (Qt6Core, Qt6Gui, Qt6Widgets, Qt6Network) and qtsvg (Qt6Svg) among its modules.

This offer is made under GPL-3.0 section 6(d), as incorporated into LGPL-3.0 section 4 for this Combined Work (conveyance by download, not the physical-product written-offer clause in section 6(b)).

## Removed Qt modules

Option B (2026-11-09): the map is drawn natively with Qt Widgets; there is no
longer an embedded-browser map backend. Qt WebEngine, Qt WebChannel and the
Chromium code they depended on are excluded from this build (see
`OrbitRxMonitor.spec`), so `Qt6WebEngineCore.dll` and the other WebEngine
DLLs no longer ship and there is nothing to relink there. The local GN
argument log and `third_party/qt/qtpdf-args-AMD64.gn` describe a past
configure of the now-removed WebEngine module and are historical only.

F1 (2026-11-12): Qt PDF (`Qt6Pdf.dll`) and Qt Virtual Keyboard
(`Qt6VirtualKeyboard.dll`) are not installed by the pinned
`PySide6_Essentials` 6.12.0 wheel at all -- neither DLL is present in it.
Their orphan plugins (`plugins/imageformats/qpdf.dll`,
`plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll`), plus Qt
Quick/Qml (`Qt6Quick.dll`, `Qt6Qml*.dll`) and Qt OpenGL (`Qt6OpenGL.dll`,
the only importer of which was Qt6Quick), are present in the wheel but are
excluded the same way: nothing in `orbitrx/` imports any of them. Qt PDF
bundled PDFium, the only Chromium-derived code remaining after Option B;
with Qt PDF gone, no Chromium-derived code is shipped by this build.
