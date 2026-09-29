; Inno Setup script for HeadFocus. Compiled by installer\build.bat.
; Installs per-user (no admin prompt) into %LOCALAPPDATA%\Programs\HeadFocus,
; adds Start Menu shortcuts and a Settings > Apps entry with an uninstaller.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
; Never change AppId: Windows uses it to recognise upgrades and uninstalls.
AppId={{6B0F3C1E-8E4A-4D2B-9F53-2A7C5E9D1B40}
AppName=HeadFocus
AppVersion={#AppVersion}
AppVerName=HeadFocus {#AppVersion}
AppPublisher=Maximous Atef
AppComments=Look at a monitor and the mouse follows.
DefaultDirName={autopf}\HeadFocus
DefaultGroupName=HeadFocus
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
OutputDir=..\release
OutputBaseFilename=HeadFocus-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\HeadFocus.exe
UninstallDisplayName=HeadFocus
; Close a running HeadFocus before upgrading or uninstalling.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start HeadFocus automatically when I sign in"; Flags: unchecked

[Files]
Source: "..\release\app\HeadFocus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\HeadFocus"; Filename: "{app}\HeadFocus.exe"
Name: "{group}\HeadFocus - Calibrate"; Filename: "{app}\HeadFocus.exe"; Parameters: "--calibrate"
Name: "{group}\HeadFocus - Preview (camera window)"; Filename: "{app}\HeadFocus.exe"; Parameters: "--preview"
Name: "{group}\Uninstall HeadFocus"; Filename: "{uninstallexe}"
Name: "{autodesktop}\HeadFocus"; Filename: "{app}\HeadFocus.exe"; Tasks: desktopicon
Name: "{userstartup}\HeadFocus"; Filename: "{app}\HeadFocus.exe"; Tasks: startup

[Run]
Filename: "{app}\HeadFocus.exe"; Description: "Start HeadFocus now (the first run calibrates)"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The calibration file written by the app.
Type: filesandordirs; Name: "{userappdata}\HeadFocus"
