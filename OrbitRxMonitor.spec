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
    datas=[('world_map.jpg', '.'), ('orbitrx/ui/assets', 'orbitrx/ui/assets'), ('assets/orbitrx.ico', 'assets'), ('LICENSE', '.'), ('NOTICE', '.'), ('PRIVACY.md', '.')],
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
    a.binaries,
    a.datas,
    [],
    name='OrbitRxMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # I4: UPX-compressing the onefile exe was the likely source of the malformed PE
    # security directory the installer review flagged (UPX doesn't relocate/clear that
    # directory correctly in some bootloader builds). Disabled until that's confirmed fixed
    # upstream. Releases ship unsigned; users verify downloads with SHA256SUMS.txt.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/orbitrx.ico',
    version=str(VERSION_INFO_FILE),
)
