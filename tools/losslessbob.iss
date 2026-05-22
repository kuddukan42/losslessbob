; LosslessBob Windows Installer — Inno Setup 6.x
;
; Build from the project root after running PyInstaller:
;   pyinstaller losslessbob.spec
;   iscc /DAppVersion=1.0.4 tools\losslessbob.iss
;
; Output: tools\Output\LosslessBob_Setup_<version>.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName      "LosslessBob"
#define AppPublisher "LosslessBob Project"
#define AppURL       "https://github.com/kuddukan42/losslessbob"
#define AppExeName   "LosslessBob.exe"

[Setup]
; Unique GUID — do NOT change after first public release
AppId={{F3A8D2C1-7E45-4B9F-A012-8C6E3D5F9012}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Install to %LocalAppData%\LosslessBob — no UAC required, and the
; data/ dir (created next to the exe) stays user-writable.
DefaultDirName={localappdata}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest

; Output
OutputDir=Output
OutputBaseFilename=LosslessBob_Setup_{#AppVersion}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

UninstallDisplayIcon={app}\{#AppExeName}
; Uncomment once tools\icon.ico exists:
; SetupIconFile=..\tools\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Both shortcuts are opt-in — checked by default, user can uncheck either.
Name: "startmenuicon";   Description: "Create a Start Menu shortcut";              GroupDescription: "Shortcuts:";          Flags: checked
Name: "desktopicon";     Description: "Create a Desktop shortcut";                 GroupDescription: "Shortcuts:";          Flags: checked
Name: "fileassoc";       Description: "Associate .ffp, .md5, .st5 files";          GroupDescription: "File associations:";  Flags: unchecked
Name: "startupregistry"; Description: "Launch LosslessBob when Windows starts";    GroupDescription: "System:";             Flags: unchecked

[Files]
; All PyInstaller output — recurse so Qt DLLs, _internal/, etc. are included
Source: "..\dist\LosslessBob\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Create an empty data\ dir next to the exe so the app can write its DB
; on first launch without needing to bootstrap the directory itself.
Name: "{app}\data"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; ── File associations (.ffp, .md5, .st5) ─────────────────────────────────────
; Register a ProgID then point each extension at it.
Root: HKCU; Subkey: "Software\Classes\LosslessBob.Checksum";                              ValueType: string; ValueName: "";          ValueData: "Checksum File";                           Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\LosslessBob.Checksum\DefaultIcon";                  ValueType: string; ValueName: "";          ValueData: "{app}\{#AppExeName},0";                   Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\LosslessBob.Checksum\shell\open\command";           ValueType: string; ValueName: "";          ValueData: """{app}\{#AppExeName}"" ""%1""";           Tasks: fileassoc

Root: HKCU; Subkey: "Software\Classes\.ffp"; ValueType: string; ValueName: ""; ValueData: "LosslessBob.Checksum"; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\.md5"; ValueType: string; ValueName: ""; ValueData: "LosslessBob.Checksum"; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\.st5"; ValueType: string; ValueName: ""; ValueData: "LosslessBob.Checksum"; Tasks: fileassoc

; ── Run at Windows startup ───────────────────────────────────────────────────
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Tasks: startupregistry

[Run]
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[Code]
// After the standard uninstaller removes tracked files, offer to wipe the
// data\ directory (database, cache, attachments, logs — all user-generated).
// The app dir itself is also removed if it is empty afterwards.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir:  String;
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;

  AppDir  := ExpandConstant('{app}');
  DataDir := AppDir + '\data';

  if not DirExists(DataDir) then Exit;

  if MsgBox(
    'Do you also want to delete all LosslessBob data?' + #13#10 + #13#10 +
    'This will permanently remove:' + #13#10 +
    '  • Your database (losslessbob.db)' + #13#10 +
    '  • Cached pages and attachments' + #13#10 +
    '  • Backups, logs, and settings' + #13#10 + #13#10 +
    'Location: ' + DataDir + #13#10 + #13#10 +
    'This cannot be undone. Choose No to keep your data.',
    mbConfirmation, MB_YESNO) = IDYES then
  begin
    DelTree(DataDir, True, True, True);
    // Remove the app dir too if nothing else remains
    RemoveDir(AppDir);
  end;
end;
