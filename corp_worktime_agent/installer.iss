; Inno Setup script for Corp Worktime Agent.
; Build with: iscc installer.iss   (requires dist\CorpWorktimeAgent\ to already exist,
; i.e. run build_windows_exe.bat first)
; Download Inno Setup (free): https://jrsoftware.org/isdl.php

#define MyAppName "Corp Worktime Agent"
#define MyAppVersion "1.0"
#define MyAppExeName "CorpWorktimeAgent.exe"

[Setup]
AppId={{525882F0-22A4-4EAB-9290-0F33FFB39ED7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Installs per-user under %LOCALAPPDATA%, no admin rights / UAC prompt required.
DefaultDirName={localappdata}\Programs\CorpWorktimeAgent
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=CorpWorktimeAgent-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; consent_notice.md is handled separately below -- it may have been customized by
; HR/legal in a prior install, so the bulk copy must not overwrite it on upgrade.
Source: "dist\CorpWorktimeAgent\*"; DestDir: "{app}"; Excludes: "consent_notice.md"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\CorpWorktimeAgent\consent_notice.md"; DestDir: "{app}"; Flags: onlyifdoesntexist
; Only seed config.json from the template on first install -- never clobber a config
; (employee_id, webhook URL, categories) the deployer has already filled in.
Source: "dist\CorpWorktimeAgent\config.example.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent unchecked
