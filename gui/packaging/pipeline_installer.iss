; gui/packaging/pipeline_installer.iss
; Inno Setup script for MAHABOCW Pipeline Installer.
;
; What this installer does:
;   1. Verifies Python is on PATH (aborts with a clear message if not).
;   2. Copies pipeline .py source files to C:\ProgramData\MAHABOCW\pipeline
;      (a system folder not normally browsed by end-users).
;   3. Silently runs (all output redirected to install.log):
;        a. python -m pip install --upgrade pip
;        b. python -m pip install -r requirements-lock-cpu.txt
;        c. python -m playwright install chromium
;   4. Writes .setup_complete marker so the GUI can confirm setup succeeded.
;
; KNOWN LIMITATION:
;   Pip-installed packages (site-packages) and the Playwright Chromium download
;   (~300 MB in %LOCALAPPDATA%\ms-playwright) are NOT removed by the uninstaller.
;   Inno Setup only tracks files it copied directly. A full removal would require
;   a custom uninstall script that calls `pip uninstall` and
;   `playwright uninstall chromium` — intentionally left out-of-scope here.
;   Document this to clients in the uninstall notes if needed.
;
; Build instructions:
;   Open this .iss file in Inno Setup Compiler and click Build.
;   Output: gui/packaging/Output/MAHABOCW-Pipeline-Setup.exe
;   Source .py files are referenced from the repo root (two levels up from here).

[Setup]
AppName=MAHABOCW Pipeline
AppVersion=1.0.0
AppPublisher=KPMG
AppPublisherURL=https://kpmg.com/in/en/services/advisory/consulting/government-and-public-services.html
; Fixed install dir — non-negotiable. The GUI hard-codes this path for auto-detection.
DefaultDirName={commonappdata}\MAHABOCW\pipeline
; Suppress the "Select Destination" page: the location is fixed and must not
; be changed by the user (the GUI always looks at C:\ProgramData\MAHABOCW\pipeline).
DisableDirPage=yes
DefaultGroupName=MAHABOCW
OutputDir=Output
OutputBaseFilename=MAHABOCW-Pipeline-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Require Windows 10 or later (matches GUI installer)
MinVersion=10.0
; 64-bit only (Python ecosystem packages are 64-bit)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; This is a background component, not a launchable app — no Desktop/Start Menu icon.
; The uninstaller entry in Add/Remove Programs is sufficient.
CreateUninstallRegKey=yes
; The target (C:\ProgramData) requires elevation.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; ------------------------------------------------------------------
; Pipeline source files — copied to {commonappdata}\MAHABOCW\pipeline
; ------------------------------------------------------------------
; Orchestrator
Source: "..\..\verify_colleges.py";        DestDir: "{app}"; Flags: ignoreversion
; Supporting pipeline modules
Source: "..\..\document_processor.py";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\extractor.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\ocr_engine.py";             DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\web_resolver.py";           DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\logger_config.py";          DestDir: "{app}"; Flags: ignoreversion
; CPU-safe requirements file (paddlepaddle, not paddlepaddle-gpu)
Source: "..\..\requirements-lock-cpu.txt"; DestDir: "{app}"; Flags: ignoreversion
;
; NOT shipped:
;   institution_cache.json — client must start with a clean cache, not the dev cache.
;   .env                   — never tracked; secrets are entered in the GUI at runtime.
;   test_*.py              — dev/test files, not needed at runtime.

[Run]
; ------------------------------------------------------------------
; Post-install steps — all runhidden so no terminal window appears.
; All output (stdout + stderr) is appended to install.log for diagnostics.
; Steps run sequentially after files are copied.
; ------------------------------------------------------------------

; Step A: upgrade pip itself first (avoids "pip is outdated" noise in the log)
Filename: "cmd.exe"; \
  Parameters: "/c python -m pip install --upgrade pip >> ""{app}\install.log"" 2>&1"; \
  WorkingDir: "{app}"; \
  Flags: runhidden; \
  StatusMsg: "Upgrading pip...";

; Step B: install all pipeline dependencies (~several minutes for PaddleOCR/pandas/etc.)
Filename: "cmd.exe"; \
  Parameters: "/c python -m pip install -r ""{app}\requirements-lock-cpu.txt"" >> ""{app}\install.log"" 2>&1"; \
  WorkingDir: "{app}"; \
  Flags: runhidden; \
  StatusMsg: "Installing Python packages (this may take several minutes)...";

; Step C: download Playwright's self-contained Chromium browser (~300 MB)
Filename: "cmd.exe"; \
  Parameters: "/c python -m playwright install chromium >> ""{app}\install.log"" 2>&1"; \
  WorkingDir: "{app}"; \
  Flags: runhidden; \
  StatusMsg: "Installing Chromium browser component...";

; Step D: write the .setup_complete marker after all three steps above finish.
; The GUI's default_pipeline_dir() checks for verify_colleges.py to locate the
; pipeline, but this separate marker lets a future health-check distinguish
; "files were copied but pip/playwright failed" from "fully installed".
; An empty file is sufficient — its mere existence is the signal.
Filename: "cmd.exe"; \
  Parameters: "/c type nul > ""{app}\.setup_complete"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden; \
  StatusMsg: "Finalising installation...";

[UninstallDelete]
; ------------------------------------------------------------------
; Remove files written at runtime (not auto-tracked by Inno Setup).
; ------------------------------------------------------------------
; The completion marker
Type: files; Name: "{app}\.setup_complete"
; The pip/playwright install log
Type: files; Name: "{app}\install.log"
;
; The .py files and requirements-lock-cpu.txt copied by [Files] are removed
; automatically because Inno Setup tracks every file it copies.
;
; NOTE: pip-installed packages in Python's site-packages and the Playwright
; Chromium download (~%LOCALAPPDATA%\ms-playwright) are NOT removed here.
; This is a known limitation — Inno Setup only manages what it directly copied,
; not pip's side-effects. A full cleanup would require running
; `pip uninstall -r requirements-lock-cpu.txt -y` and `playwright uninstall chromium`
; as part of a custom [UninstallRun] section. Left out of scope for now.

[Code]
// ------------------------------------------------------------------
// Pre-install check: verify Python is reachable on PATH.
// If not found, show a clear message and abort before any files are written.
// ------------------------------------------------------------------

function IsPythonAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  // Exec() returns True if the process launched; we also require exit code 0
  // (i.e. `python --version` succeeded, not just that the shell started).
  Result := Exec('python', '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsPythonAvailable() then
  begin
    MsgBox(
      'Python was not found on this machine.' + #13#10 + #13#10 +
      'Before running this installer, please:' + #13#10 +
      '  1. Download Python 3.12 or 3.13 from https://www.python.org/downloads/' + #13#10 +
      '  2. During installation, tick "Add Python to PATH"' + #13#10 +
      '  3. Re-run this installer once Python is installed.' + #13#10 + #13#10 +
      'Installation will now be cancelled.',
      mbCriticalError,
      MB_OK
    );
    Result := False;
  end;
end;
