; Inno Setup script for Personal Focus Guard.
; Build with: iscc installer.iss   (requires dist\PersonalFocusGuard\ to already exist,
; i.e. run build_windows_exe.bat first)
; Download Inno Setup (free): https://jrsoftware.org/isdl.php

#define MyAppName "Personal Focus Guard"
#define MyAppVersion "1.0"
#define MyAppExeName "PersonalFocusGuard.exe"

[Setup]
AppId={{B352E7E8-A7DA-46DB-A351-4B091ACFE47D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Installs per-user under %LOCALAPPDATA%, no admin rights / UAC prompt required.
DefaultDirName={localappdata}\Programs\PersonalFocusGuard
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=PersonalFocusGuard-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\PersonalFocusGuard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Only seed config.json from the template on first install -- never clobber a config
; the user has already customized (blacklist keywords, time windows, etc.) on upgrade.
Source: "dist\PersonalFocusGuard\config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent unchecked
