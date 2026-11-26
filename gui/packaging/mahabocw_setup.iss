; gui/packaging/mahabocw_setup.iss
; Single installer for the MAHABOCW Verification Tool -> MAHABOCW-Setup.exe
;
; Replaces the old pair MAHABOCW-Pipeline-Setup.exe + MAHABOCW-GUI-Setup.exe.
; No system Python is needed: a private Python 3.12 runtime is shipped.
;
; Install layout ({app} = C:\Program Files\MAHABOCW):
;   app\        GUI (PyInstaller onedir: mahabocw_gui.exe)
;   pipeline\   verify_colleges.py + modules + requirement files
;   runtime\    private Python 3.12 (python-build-standalone)
;   browsers\   Playwright Chromium (PLAYWRIGHT_BROWSERS_PATH)
;   tools\      setup_runtime.cmd (re-runnable repair script)
;   install.log
; Per-user run data (logs, downloads, cache) lives in %LOCALAPPDATA%\MAHABOCW.
;
; Do not compile this by hand; run gui\packaging\build.ps1, which builds the
; frontend, the GUI exe and the runtime folder first.

#define AppVersion GetEnv("MAHABOCW_VERSION")
#if AppVersion == ""
  #define AppVersion "2.1.0"
#endif

[Setup]
AppId={{6C2F4E7A-3B1D-4C9E-9A57-2D8E0B4F1A63}
AppName=MAHABOCW Verification Tool
AppVersion={#AppVersion}
AppPublisher=KPMG
AppPublisherURL=https://kpmg.com/in/en/services/advisory/consulting/government-and-public-services.html
DefaultDirName={autopf}\MAHABOCW
DefaultGroupName=MAHABOCW
UninstallDisplayIcon={app}\app\mahabocw_gui.exe
OutputDir=Output
OutputBaseFilename=MAHABOCW-Setup
SetupIconFile=..\app\resources\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Admin: Program Files target + WebView2 bootstrapper (writes HKLM).
PrivilegesRequired=admin
UsedUserAreasWarning=no
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; GUI
Source: "..\dist\mahabocw_gui\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; Pipeline
Source: "..\..\verify_colleges.py";         DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\scoring.py";                 DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\document_processor.py";      DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\extractor.py";               DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\ocr_engine.py";              DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\web_resolver.py";            DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\logger_config.py";           DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\requirements-lock.txt";      DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\requirements-paddle-cpu.txt"; DestDir: "{app}\pipeline"; Flags: ignoreversion
Source: "..\..\requirements-paddle-gpu.txt"; DestDir: "{app}\pipeline"; Flags: ignoreversion
; Private Python runtime (extracted by build.ps1)
Source: "build\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
; Repair / post-install script
Source: "setup_runtime.cmd"; DestDir: "{app}\tools"; Flags: ignoreversion
; Handout
Source: "..\..\docs\SETUP_INSTRUCTIONS.md"; DestDir: "{app}"; DestName: "SETUP_INSTRUCTIONS.txt"; Flags: ignoreversion
; WebView2 Evergreen Bootstrapper (no-op when the runtime is already present)
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{group}\MAHABOCW Verification Tool"; Filename: "{app}\app\mahabocw_gui.exe"; WorkingDir: "{app}\app"
Name: "{group}\Repair MAHABOCW components"; Filename: "{app}\tools\setup_runtime.cmd"; Parameters: "{code:HardwareMode}"; WorkingDir: "{app}\tools"
Name: "{commondesktop}\MAHABOCW Verification Tool"; Filename: "{app}\app\mahabocw_gui.exe"; WorkingDir: "{app}\app"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\SETUP_INSTRUCTIONS.txt"; Description: "View setup instructions"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\app\mahabocw_gui.exe"; Description: "Launch MAHABOCW Verification Tool"; Flags: postinstall nowait skipifsilent; Check: SetupSucceeded

[UninstallDelete]
; Everything below is private to this install, so uninstall removes it fully
; (pip packages and Chromium included).
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\browsers"
Type: filesandordirs; Name: "{app}\pipeline\__pycache__"
Type: files; Name: "{app}\install.log"
Type: files; Name: "{app}\.setup_complete"

[Code]
var
  HardwarePage: TInputOptionWizardPage;
  RuntimeOk: Boolean;

function HardwareMode(Param: String): String;
begin
  if HardwarePage.Values[1] then Result := 'gpu' else Result := 'cpu';
end;

function SetupSucceeded(): Boolean;
begin
  Result := RuntimeOk;
end;

procedure InitializeWizard;
begin
  HardwarePage := CreateInputOptionPage(
    wpSelectDir,
    'Hardware Acceleration',
    'Choose how documents are read (OCR).',
    'Standard works on every computer. The NVIDIA option is faster but needs a dedicated NVIDIA graphics card (AMD and Intel graphics are not supported).',
    True, False);
  HardwarePage.Add('Standard (CPU) - recommended for most computers');
  HardwarePage.Add('High performance (NVIDIA GPU)');
  HardwarePage.Values[0] := True;
end;

{ ---------------------------------------------------------------------------
  Remove the old two-installer setup (MAHABOCW Pipeline + old GUI) first.
  --------------------------------------------------------------------------- }
function OldUninstaller(Key: String): String;
var
  S: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + Key, 'UninstallString', S) then
    Result := RemoveQuotes(S);
end;

procedure RunOldUninstaller(Key, Title: String);
var
  Path: String;
  Code: Integer;
begin
  Path := OldUninstaller(Key);
  if Path <> '' then
  begin
    Log('Removing old component: ' + Title);
    Exec(Path, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if (OldUninstaller('MAHABOCW Pipeline_is1') <> '') or (OldUninstaller('MAHABOCW Verification Tool_is1') <> '') then
  begin
    if MsgBox('An older version of MAHABOCW (separate Pipeline and GUI installers) was found.' + #13#10 +
              'It will be removed and replaced by this version.' + #13#10 +
              'You may need to enter your API key and file choices again.' + #13#10#13#10 +
              'Continue?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := 'Installation cancelled. The older version was left unchanged.';
      Exit;
    end;
    RunOldUninstaller('MAHABOCW Pipeline_is1', 'MAHABOCW Pipeline');
    RunOldUninstaller('MAHABOCW Verification Tool_is1', 'MAHABOCW GUI');
  end;
end;

{ ---------------------------------------------------------------------------
  Post-install: WebView2, then pip + Chromium via tools\setup_runtime.cmd.
  Exit codes are checked; failures are reported instead of being ignored.
  --------------------------------------------------------------------------- }
function StepName(Code: Integer): String;
begin
  case Code of
    10: Result := 'the Python runtime is missing';
    11: Result := 'installing Python packages failed';
    12: Result := 'installing the OCR engine (PaddlePaddle) failed';
    13: Result := 'downloading the Chromium browser failed';
    14: Result := 'the installed packages could not be loaded';
  else
    Result := 'an unexpected error occurred (code ' + IntToStr(Code) + ')';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep <> ssPostInstall then Exit;

  WizardForm.ProgressGauge.Style := npbstMarquee;

  WizardForm.StatusLabel.Caption := 'Installing the WebView2 runtime (if needed)...';
  Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code);

  WizardForm.StatusLabel.Caption := 'Installing Python packages and the Chromium browser. This takes several minutes...';
  RuntimeOk := Exec(ExpandConstant('{cmd}'),
                    '/C ""' + ExpandConstant('{app}\tools\setup_runtime.cmd') + '" ' + HardwareMode('') + '"',
                    ExpandConstant('{app}\tools'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);

  WizardForm.ProgressGauge.Style := npbstNormal;

  if not RuntimeOk then
    MsgBox('Setup could not finish: ' + StepName(Code) + '.' + #13#10#13#10 +
           'Check your internet connection, then run "Repair MAHABOCW components" from the Start menu ' +
           '(right-click > Run as administrator).' + #13#10#13#10 +
           'Details: ' + ExpandConstant('{app}\install.log'),
           mbError, MB_OK);
end;
