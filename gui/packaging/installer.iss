; packaging/installer.iss
; Inno Setup script for MAHABOCW Verification Tool GUI installer.
;
; Build instructions:
;   1. Build the PyInstaller onedir first (from gui/ directory):
;        pyinstaller packaging/mahabocw_gui.spec
;   2. Open this .iss file in Inno Setup Compiler and click Build.
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller onedir output — everything in the build folder.
Source: "..\dist\mahabocw_gui\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Setup instructions handout — shipped as a plain .txt file so Windows can
; open it directly in Notepad via shellexec (no PDF viewer required).
Source: "..\..\docs\SETUP_INSTRUCTIONS.md"; DestDir: "{app}"; DestName: "SETUP_INSTRUCTIONS.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\MAHABOCW Verification Tool"; Filename: "{app}\mahabocw_gui.exe"; WorkingDir: "{app}"
Name: "{commondesktop}\MAHABOCW Verification Tool"; Filename: "{app}\mahabocw_gui.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
; Open the setup instructions in Notepad after install completes (optional, skippable).
Filename: "{app}\SETUP_INSTRUCTIONS.txt"; Description: "View pipeline setup instructions"; Flags: postinstall shellexec skipifsilent
; Launch the application immediately after install (optional).
Filename: "{app}\mahabocw_gui.exe"; Description: "Launch MAHABOCW Verification Tool"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{userappdata}\MAHABOCW-GUI\settings.json"
