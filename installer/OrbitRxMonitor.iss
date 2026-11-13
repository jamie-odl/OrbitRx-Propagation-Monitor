; Inno Setup 6 script for OrbitRx (unsigned).
; Build the exe first (build.bat or CI), then:
;   iscc /DAppVer=5.2.0 /DAppVerNumeric=5.2.0.0 installer\OrbitRxMonitor.iss
; AppVer can carry a pre-release suffix (e.g. "5.3.0-rc.1"); Inno's
; VersionInfoVersion cannot, so AppVerNumeric -- the strictly-numeric 4-part
; version from tools/make_version_info.version_tuple4 -- is passed separately.

[Setup]
AppName=OrbitRx Propagation Monitor
#ifndef AppVer
  #define AppVer "5.2.0"
#endif
#ifndef AppVerNumeric
  #define AppVerNumeric "5.2.0.0"
#endif
AppVersion={#AppVer}
AppVerName=OrbitRx Propagation Monitor {#AppVer}
AppPublisher=thevenom
AppCopyright=Copyright (C) 2026 thevenom
VersionInfoVersion={#AppVerNumeric}
VersionInfoCompany=thevenom
VersionInfoProductName=OrbitRx Propagation Monitor
LicenseFile=..\LICENSE
OutputDir=..\dist
SetupIconFile=..\assets\orbitrx.ico
UninstallDisplayIcon={app}\OrbitRxMonitor.exe
AppSupportURL=https://github.com/jamie-odl/OrbitRx-Propagation-Monitor
AppUpdatesURL=https://github.com/jamie-odl/OrbitRx-Propagation-Monitor/releases
DefaultDirName={autopf}\OrbitRxMonitor
DefaultGroupName=OrbitRx
OutputBaseFilename=OrbitRxMonitor-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest

; Unpublished onedir layout. This is not the 5 Nov 2026 one-file installer.
; The folder already contains ne_110m_dark.png, Qt DLLs, and third_party texts.
; world_map.jpg and the v2 images are not inputs.

[Files]
Source: "..\dist\OrbitRxMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"
Name: "{autodesktop}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\OrbitRxMonitor.exe"; Description: "Launch OrbitRx"; Flags: postinstall nowait skipifsilent
