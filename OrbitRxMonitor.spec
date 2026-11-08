# -*- mode: python ; coding: utf-8 -*-
import sys

from PyInstaller.utils.hooks import collect_submodules

sys.path.insert(0, '.')
from tools.make_version_info import write_version_info  # noqa: E402

# I3: VERSION is the single source of truth; regenerate the exe's Windows version
# resource from it on every build instead of hand-maintaining a second copy.
VERSION_INFO_FILE = write_version_info('VERSION', 'file_version_info.txt')

hiddenimports = ['PySide6', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel', 'matplotlib.backends.backend_qtagg', 'serial', 'serial.tools.list_ports']
hiddenimports += collect_submodules('orbitrx')

# N1: conservative Qt module trim. Only excludes modules OrbitRx never imports
# (no 3D/multimedia/charts/bluetooth/sensors/sql/test/designer features anywhere
# in orbitrx/). QtWebEngineCore/Widgets/WebChannel/Network/Positioning/Quick/Qml
# are kept: QtWebEngine depends on them for the Leaflet map view.
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
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    # Onedir: Qt libraries sit next to the exe so they can be replaced.
    # Basemap is only the Natural Earth render. Legacy JPEG and v2 images
    # are not datas. Licence texts are copied; they are not a published
    # source offer and not the gn-generated Chromium about_credits file.
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
        ('third_party/qt/LICENSE.Chromium', 'third_party/qt'),
        ('third_party/qt/chromium_attributions.qdoc', 'third_party/qt'),
        ('third_party/natural_earth/TERMS_OF_USE.txt', 'third_party/natural_earth'),
        ('third_party/natural_earth/ne_110m_land.geojson', 'third_party/natural_earth'),
        ('third_party/win10toast/LICENSE', 'third_party/win10toast'),
        ('third_party/pillow/LICENSE', 'third_party/pillow'),
        ('third_party/matplotlib/LICENSE', 'third_party/matplotlib'),
        ('third_party/pyserial/LICENSE.txt', 'third_party/pyserial'),
        ('third_party/pywin32/License.txt', 'third_party/pywin32'),
        ('third_party/pyinstaller/COPYING.txt', 'third_party/pyinstaller'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
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
