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

; Map file shipped beside the exe is world_map.jpg. The v2 images are not
; included. Upstream licence texts under third_party are copied for the next
; build. They do not replace the 5 Nov 2026 installer and they are not a Qt
; source offer, a relink kit, or a Chromium credits file.

[Files]
Source: "..\dist\OrbitRxMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\world_map.jpg"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\orbitrx.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\third_party\qt\LICENSES\*"; DestDir: "{app}\third_party\qt\LICENSES"; Flags: ignoreversion
Source: "..\third_party\qt\qtcoreglobal.h.SPDX.txt"; DestDir: "{app}\third_party\qt"; Flags: ignoreversion
Source: "..\third_party\win10toast\LICENSE"; DestDir: "{app}\third_party\win10toast"; Flags: ignoreversion
Source: "..\third_party\pillow\LICENSE"; DestDir: "{app}\third_party\pillow"; Flags: ignoreversion
Source: "..\third_party\matplotlib\LICENSE"; DestDir: "{app}\third_party\matplotlib"; Flags: ignoreversion
Source: "..\third_party\pyserial\LICENSE.txt"; DestDir: "{app}\third_party\pyserial"; Flags: ignoreversion
Source: "..\third_party\pywin32\License.txt"; DestDir: "{app}\third_party\pywin32"; Flags: ignoreversion
Source: "..\third_party\pyinstaller\COPYING.txt"; DestDir: "{app}\third_party\pyinstaller"; Flags: ignoreversion

[Icons]
Name: "{group}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"
Name: "{autodesktop}\OrbitRx Monitor"; Filename: "{app}\OrbitRxMonitor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\OrbitRxMonitor.exe"; Description: "Launch OrbitRx"; Flags: postinstall nowait skipifsilent
