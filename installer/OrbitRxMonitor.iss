; Inno Setup 6 script for OrbitRx (unsigned).
; Build the exe first (build.bat or CI), then: iscc /DAppVer=5.1.0 installer\OrbitRxMonitor.iss

[Setup]
AppName=OrbitRx Propagation Monitor
#ifndef AppVer
  #define AppVer "5.1.0"
#endif
AppVersion={#AppVer}
AppVerName=OrbitRx Propagation Monitor {#AppVer}
AppPublisher=thevenom
AppCopyright=Copyright (C) 2026 thevenom
VersionInfoVersion={#AppVer}.0
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

[Files]
Source: "..\dist\OrbitRxMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\world_map.jpg"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\orbitrx.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"
Name: "{autodesktop}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\OrbitRxMonitor.exe"; Description: "Launch OrbitRx"; Flags: postinstall nowait skipifsilent
