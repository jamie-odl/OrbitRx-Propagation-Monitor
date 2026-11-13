# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_submodules

sys.path.insert(0, '.')
from tools.make_version_info import write_version_info  # noqa: E402
from tools.ship_set import filter_binaries  # noqa: E402

# I3: VERSION is the single source of truth; regenerate the exe's Windows version
# resource from it on every build instead of hand-maintaining a second copy.
VERSION_INFO_FILE = write_version_info('VERSION', 'file_version_info.txt')

hiddenimports = ['PySide6', 'matplotlib.backends.backend_qtagg', 'serial', 'serial.tools.list_ports']
hiddenimports += collect_submodules('orbitrx')

# N1: conservative Qt module trim. Only excludes modules OrbitRx never imports
# (no 3D/multimedia/charts/bluetooth/sensors/sql/test/designer features anywhere
# in orbitrx/).
#
# Option B (2026-11-09): the Leaflet/WebEngine map view is gone (native
# PropagationMapWidget draws Live Spots directly), so the whole Chromium-backed
# stack it needed is excluded too: WebEngine itself, the Qml/Quick view it
# hosted the page in, WebChannel for the JS bridge, and Positioning/Location,
# which WebEngine pulled in for geolocation. Nothing in orbitrx/ imports any of
# these any more (orbitrx/ui/leaflet_map.py, the only importer, is deleted).
excludes = [
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
    'PySide6.QtQuick3D', 'PySide6.QtQuick3DRuntimeRender', 'PySide6.QtQuick3DUtils',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtDesigner', 'PySide6.QtUiTools',
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtSensors',
    'PySide6.QtSql', 'PySide6.QtTest',
    'PySide6.QtRemoteObjects', 'PySide6.QtSerialBus',
    'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech',
    'PySide6.QtHttpServer', 'PySide6.QtScxml', 'PySide6.QtStateMachine',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
    'PySide6.QtWebChannel', 'PySide6.QtWebView', 'PySide6.QtWebSockets',
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2', 'PySide6.QtQuickTest', 'PySide6.QtQmlFeatures',
    'PySide6.QtPositioning', 'PySide6.QtLocation',
    # F1 (2026-11-12): nothing in orbitrx/ imports these either. Qt6Pdf (PDF
    # viewing), Qt6VirtualKeyboard, Qt6Quick/Qml* and Qt6OpenGL (Qt6Quick's
    # only dependent) are dropped from both the Python modules here and the
    # Qt binaries below (tools/ship_set.BANNED_PATTERNS).
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtVirtualKeyboard',
    'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # Onedir: Qt libraries sit next to the exe so they can be replaced.
    # Basemap is only the Natural Earth render. Legacy JPEG and v2 images
    # are not datas. Licence texts are copied for reference; the
    # Corresponding Source offer itself is the NOTICE paragraph (see NOTICE),
    # not these copied licence texts.
    #
    # Option B (2026-11-09): Qt WebEngine is no longer bundled (see excludes
    # above), so its vendor notices (LICENSE.Chromium,
    # THIRD_PARTY_NOTICES_QtWebEngine-*.txt) are no longer shipped either --
    # packaging a notices file for a library that isn't in the build would
    # misstate what's actually distributed. Those files stay in third_party/qt
    # in git as the historical record for the WebEngine-era 5.1.0 release.
    datas=[
        ('basemap/ne_110m_dark.png', '.'),
        ('basemap/PROVENANCE.json', '.'),
        ('orbitrx/ui/assets', 'orbitrx/ui/assets'),
        ('assets/orbitrx.ico', 'assets'),
        ('LICENSE', '.'),
        ('NOTICE', '.'),
        ('PRIVACY.md', '.'),
        ('docs/REPLACING_QT_LIBRARIES.md', '.'),
        ('third_party/qt/LICENSES', 'third_party/qt/LICENSES'),
        ('third_party/qt/qtcoreglobal.h.SPDX.txt', 'third_party/qt'),
        ('third_party/natural_earth/TERMS_OF_USE.txt', 'third_party/natural_earth'),
        ('third_party/natural_earth/ne_110m_land.geojson', 'third_party/natural_earth'),
        ('third_party/win10toast/LICENSE', 'third_party/win10toast'),
        ('third_party/pillow/LICENSE', 'third_party/pillow'),
        ('third_party/matplotlib/LICENSE', 'third_party/matplotlib'),
        ('third_party/pyserial/LICENSE.txt', 'third_party/pyserial'),
        ('third_party/pywin32/License.txt', 'third_party/pywin32'),
        ('third_party/pyinstaller/COPYING.txt', 'third_party/pyinstaller'),
        ('third_party/openssl/LICENSE.txt', 'third_party/openssl'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
# F1: drop the Qt binaries/data nothing in orbitrx/ imports (see excludes
# above and tools/ship_set.py) from the actual ship set, not just the Python
# module graph -- PyInstaller's Qt hook still collects their DLLs by default.
a.binaries = filter_binaries(a.binaries)
a.datas = filter_binaries(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OrbitRxMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/orbitrx.ico',
    version=str(VERSION_INFO_FILE),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OrbitRxMonitor',
)
