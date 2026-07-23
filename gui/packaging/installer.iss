; packaging/installer.iss
; Inno Setup script for MAHABOCW Verification Tool GUI installer.
;
; Build instructions:
;   1. npm run build   (inside gui/frontend/)
;   2. pyinstaller packaging/mahabocw_gui.spec   (from gui/)
;   3. Open this .iss file in Inno Setup Compiler and click Build.
;      Output: gui/packaging/Output/MAHABOCW-GUI-Setup.exe

[Setup]
AppName=MAHABOCW Verification Tool
AppVersion=1.0.0
AppPublisher=KPMG
AppPublisherURL=https://kpmg.com/in/en/services/advisory/consulting/government-and-public-services.html
DefaultDirName={autopf}\MAHABOCW
DefaultGroupName=MAHABOCW
OutputDir=Output
OutputBaseFilename=MAHABOCW-GUI-Setup
SetupIconFile=..\app\resources\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Require Windows 10 or later (version 10.0)
MinVersion=10.0
; 64-bit only (the pipeline's Python and dependencies are 64-bit)
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; PrivilegesRequired=admin is necessary here because the [Run] section executes
; the Microsoft Edge WebView2 Evergreen Bootstrapper (MicrosoftEdgeWebview2Setup.exe)
; with the /silent /install flags.  The bootstrapper writes to HKLM and installs a
; system-wide runtime component, which requires an elevated process.  Without admin
; rights the bootstrapper silently fails and the app cannot open.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller onedir output — everything in the build folder.
Source: "..\dist\mahabocw_gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Setup instructions handout.
Source: "..\..\docs\SETUP_INSTRUCTIONS.md"; DestDir: "{app}"; DestName: "SETUP_INSTRUCTIONS.txt"; Flags: ignoreversion
; Microsoft Edge WebView2 Evergreen Bootstrapper (~2 MB).
; The bootstrapper is a no-op if the runtime is already present (which it is on
; most current Windows 10/11 machines), so it is always safe to include.
; Download the latest bootstrapper from:
;   https://developer.microsoft.com/en-us/microsoft-edge/webview2/
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Icons]
Name: "{group}\MAHABOCW Verification Tool"; Filename: "{app}\mahabocw_gui.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\MAHABOCW Verification Tool"; Filename: "{app}\mahabocw_gui.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
; Install the WebView2 runtime silently before the first launch.
; The /silent /install flags suppress all UI and are a no-op if already installed.
; waituntilterminated ensures the bootstrapper finishes before the app launches.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; Flags: waituntilterminated; StatusMsg: "Installing WebView2 Runtime (required)..."
; Open the setup instructions in Notepad after install completes (optional, skippable).
Filename: "{app}\SETUP_INSTRUCTIONS.txt"; Description: "View pipeline setup instructions"; Flags: postinstall shellexec skipifsilent
; Launch the application immediately after install (optional).
Filename: "{app}\mahabocw_gui.exe"; Description: "Launch MAHABOCW Verification Tool"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{userappdata}\MAHABOCW-GUI\settings.json"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Set progress bar to a continuous looping animation during the [Run] section }
    WizardForm.ProgressGauge.Style := npbstMarquee;
  end;
end;
