; Lightworks Pro — Inno Setup installer script
; Requires: Inno Setup 6.x  (https://jrsoftware.org/isdl.php)
;
; To compile:
;   iscc installer\setup.iss
;
; Output: dist\installer\LightworksPro_Setup_1.2.0.exe

#define AppName       "Lightworks Pro"
#define AppVersion    "1.2.0"
#define AppPublisher  "Abu Hoque & Lighthouse Guild, New York"
#define AppCopyright  "Copyright (c) 2026 Abu Hoque & Lighthouse Guild, New York. MIT License."
#define AppExeName    "LightworksPro.exe"
#define AppId         "{{A3F2B8C1-D4E5-4F67-8901-234567890ABC}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
AppContact=ai.apuhoque@gmail.com
AppPublisherURL=https://lightworkspro.app
AppSupportURL=https://lightworkspro.app/support
AppUpdatesURL=https://lightworkspro.app/updates

; Install to Program Files without requiring admin:
; PrivilegesRequired=lowest allows per-user install with no UAC prompt.
; This is correct for a user-space tray app.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Output
OutputDir=..\dist\installer
OutputBaseFilename=LightworksPro_Setup_{#AppVersion}
SetupIconFile=..\assets\lightworks_pro.ico
UninstallDisplayIcon={app}\{#AppExeName}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Accessibility: modern wizard style with large fonts is most readable
; and compatible with JAWS/NVDA screen readers on the installer UI.
WizardStyle=modern
WizardSizePercent=120

; Architecture
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Restart not required (no kernel drivers installed)
RestartIfNeededByRun=no
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startup";     Description: "Start {#AppName} automatically when &Windows starts (recommended)"; GroupDescription: "Additional options:"
Name: "desktopicon"; Description: "Create a &desktop shortcut";                                        GroupDescription: "Additional options:"; Flags: unchecked

[Dirs]
; Create the AppData config directory so the app can write its config on first run
Name: "{userappdata}\LightworksPro"

[Files]
; PyInstaller onedir output — the entire LightworksPro folder
Source: "..\dist\LightworksPro\*"; DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Pre-populate a default config so the voice setup wizard is skipped and the
; tray service starts immediately on first launch.
; onlyifdoesntexist — preserves the user's config on upgrades.
; uninsneveruninstall — uninstaller leaves the user's config intact.
Source: "..\dist\LightworksPro\_internal\config.example.json"; \
  DestDir: "{userappdata}\LightworksPro"; \
  DestName: "config.json"; \
  Flags: onlyifdoesntexist uninsneveruninstall

; Helper scripts — placed in {app}\scripts\ for users and IT admins.
; setup_user.ps1           : run once per machine to configure Microsoft 365 (no admin rights needed).
; register_azure_app.ps1   : IT admin only — one-time Azure App Registration per organisation.
; grant_admin_consent.py   : run once if contact/People.Read search is not working.
; set_microsoft_client_id.py: set or change the Azure App Client ID manually.
Source: "..\scripts\setup_user.ps1";             DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\register_azure_app.ps1";     DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\grant_admin_consent.py";     DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\set_microsoft_client_id.py"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Icons]
; Start Menu — main app
Name: "{group}\{#AppName}";            Filename: "{app}\{#AppExeName}"; \
  Comment: "Voice-controlled productivity assistant"

; Start Menu — user Microsoft 365 setup (no admin rights needed)
Name: "{group}\Connect Microsoft 365"; \
  Filename: "pwsh.exe"; \
  Parameters: "-NoExit -File ""{app}\scripts\setup_user.ps1"""; \
  Comment: "Connect your Microsoft 365 account — run once after installation"

; Start Menu — IT admin Azure App Registration
Name: "{group}\IT Admin — Register Azure App"; \
  Filename: "pwsh.exe"; \
  Parameters: "-NoExit -File ""{app}\scripts\register_azure_app.ps1"""; \
  Comment: "IT administrators only — one-time Azure App Registration for your organisation"

Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}"

; Desktop (optional task)
Name: "{commondesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon; Comment: "Voice-controlled productivity assistant"

[Registry]
; HKCU Run key — no admin rights needed, automatically removed on uninstall
Root: HKCU; \
  Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; \
  ValueName: "LightworksPro"; \
  ValueData: """{app}\{#AppExeName}"""; \
  Flags: uninsdeletevalue; \
  Tasks: startup

[Run]
; Launch unconditionally after install — no checkbox, always runs.
; nowait so the installer finishes immediately; the app goes to the system tray.
Filename: "{app}\{#AppExeName}"; \
  Flags: nowait

; Post-install: run the user setup script to configure Microsoft 365.
; Presented as a checkbox on the final installer page.
; No admin rights or Azure permissions needed — safe for all users.
Filename: "pwsh.exe"; \
  Parameters: "-NoExit -File ""{app}\scripts\setup_user.ps1"""; \
  Description: "Connect Microsoft 365 (recommended — connects calendar, email and calling)"; \
  Flags: postinstall shellexec skipifsilent

[UninstallRun]
; Signal the running instance to shut down gracefully before files are removed
Filename: "{app}\{#AppExeName}"; \
  Parameters: "--quit"; \
  Flags: runhidden waituntilterminated; \
  RunOnceId: "QuitBeforeUninstall"

[UninstallDelete]
; Clean up AppData on uninstall (optional — comment out to preserve user config)
; Type: filesandordirs; Name: "{userappdata}\LightworksPro"

[Code]
// ---------------------------------------------------------------------------
// Custom installer code
// ---------------------------------------------------------------------------

// Prevent installing a 32-bit build on 64-bit Windows (shouldn't happen with
// ArchitecturesAllowed but belt-and-braces check).
function InitializeSetup(): Boolean;
begin
  if not Is64BitInstallMode then begin
    MsgBox('This version of Lightworks Pro requires a 64-bit version of Windows.', mbError, MB_OK);
    Result := False;
  end else
    Result := True;
end;

// After uninstall, remove the HKCU Run key entry even if the task was not
// selected (covers manual registry edits by the user or the startup module).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  RegKey: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    RegKey := 'SOFTWARE\Microsoft\Windows\CurrentVersion\Run';
    if RegValueExists(HKEY_CURRENT_USER, RegKey, 'LightworksPro') then
      RegDeleteValue(HKEY_CURRENT_USER, RegKey, 'LightworksPro');
  end;
end;
