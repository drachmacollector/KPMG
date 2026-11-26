<#
.SYNOPSIS
  Builds MAHABOCW-Setup.exe (the single installer) end to end.

.DESCRIPTION
  1. Builds the React frontend into gui/frontend_dist (npm ci + npm run build).
  2. Fails if frontend_dist is older than any frontend source file.
  3. Bundles the GUI with PyInstaller (gui/dist/mahabocw_gui).
  4. Downloads + verifies the private Python 3.12 runtime
     (python-build-standalone) into gui/packaging/build/runtime.
  5. Compiles gui/packaging/mahabocw_setup.iss with Inno Setup.

  Output: gui/packaging/Output/MAHABOCW-Setup.exe

.PARAMETER Python
  Python used to run PyInstaller. It needs gui/requirements.txt + pyinstaller.

.PARAMETER RuntimeArchive
  Optional path to an already-downloaded python-build-standalone archive
  (cpython-<RuntimeVersion>+<RuntimeTag>-x86_64-pc-windows-msvc-install_only.tar.gz).
  It is still checked against the release's SHA256SUMS when that is reachable.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File gui\packaging\build.ps1 -Python .\gui_venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$RuntimeTag = "20261124",
    [string]$RuntimeVersion = "3.12.16",
    [string]$Iscc = "",
    [string]$RuntimeArchive = "",
    [switch]$SkipFrontend,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
# Windows PowerShell 5.1 defaults to TLS 1.0/1.1, which GitHub rejects.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Packaging = $PSScriptRoot
$Gui       = Split-Path $Packaging -Parent
$Frontend  = Join-Path $Gui "frontend"
$Dist      = Join-Path $Gui "frontend_dist"
$BuildDir  = Join-Path $Packaging "build"
$Cache     = Join-Path $BuildDir "cache"
$Runtime   = Join-Path $BuildDir "runtime"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Run($exe, [string[]]$argList, $cwd) {
    Push-Location $cwd
    try {
        & $exe @argList
        if ($LASTEXITCODE -ne 0) { throw "$exe $($argList -join ' ') failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

# --- 1. Frontend --------------------------------------------------------------
if (-not $SkipFrontend) {
    Step "Building the React frontend"
    Run "npm" @("ci") $Frontend
    Run "npm" @("run", "build") $Frontend
}

# --- 2. Stale-frontend guard -------------------------------------------------
Step "Checking the frontend build is up to date"
$index = Join-Path $Dist "index.html"
if (-not (Test-Path $index)) { throw "gui/frontend_dist/index.html is missing. Run without -SkipFrontend." }
$builtAt = (Get-Item $index).LastWriteTimeUtc
$newest = Get-ChildItem -Recurse -File (Join-Path $Frontend "src"), (Join-Path $Frontend "public"), (Join-Path $Frontend "index.html") |
    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($newest.LastWriteTimeUtc -gt $builtAt) {
    throw "frontend_dist is older than $($newest.FullName). Rebuild the frontend (run without -SkipFrontend)."
}
$version = (Get-Content (Join-Path $Frontend "package.json") -Raw | ConvertFrom-Json).version
Write-Host "Frontend OK (version $version)"

# --- 3. PyInstaller ------------------------------------------------------------
Step "Bundling the GUI with PyInstaller"
Run $Python @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/mahabocw_gui.spec") $Gui

# --- 4. Private Python runtime -------------------------------------------------
Step "Preparing the private Python $RuntimeVersion runtime"
New-Item -ItemType Directory -Force $Cache | Out-Null
$asset   = "cpython-$RuntimeVersion+$RuntimeTag-x86_64-pc-windows-msvc-install_only.tar.gz"
$baseUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$RuntimeTag"
$archive = Join-Path $Cache $asset
if ($RuntimeArchive) {
    if (-not (Test-Path $RuntimeArchive)) { throw "RuntimeArchive not found: $RuntimeArchive" }
    Copy-Item $RuntimeArchive $archive -Force
}
if (-not (Test-Path $archive)) {
    Write-Host "Downloading $asset"
    Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$([uri]::EscapeDataString($asset))" -OutFile $archive
}

# Verify the archive against the release's SHA256SUMS.
$sums = (Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/SHA256SUMS").Content
if ($sums -is [byte[]]) { $sums = [Text.Encoding]::UTF8.GetString($sums) }
$line = ($sums -split "`n") | Where-Object { $_ -match [regex]::Escape($asset) } | Select-Object -First 1
if (-not $line) { throw "No checksum for $asset in SHA256SUMS" }
$expected = ($line -split "\s+")[0].ToUpper()
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToUpper()
if ($expected -ne $actual) {
    Remove-Item $archive -Force
    throw "Checksum mismatch for $asset (expected $expected, got $actual). The download was deleted; run again."
}
Write-Host "Checksum OK"

if (Test-Path $Runtime) { Remove-Item -Recurse -Force $Runtime }
$extract = Join-Path $BuildDir "extract"
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
New-Item -ItemType Directory -Force $extract | Out-Null
Run "tar" @("-xzf", $archive, "-C", $extract) $BuildDir
Move-Item (Join-Path $extract "python") $Runtime
Remove-Item -Recurse -Force $extract
& (Join-Path $Runtime "python.exe") --version
if ($LASTEXITCODE -ne 0) { throw "The extracted runtime does not start." }

# --- 5. Inno Setup ------------------------------------------------------------
if ($SkipInstaller) { Write-Host "`nSkipping Inno Setup (-SkipInstaller)."; exit 0 }
Step "Compiling MAHABOCW-Setup.exe"
if (-not $Iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) { throw "ISCC.exe (Inno Setup 6 or 7) not found. Install it or pass -Iscc <path>." }
}
$env:MAHABOCW_VERSION = $version
Run $Iscc @("mahabocw_setup.iss") $Packaging

Write-Host "`nDone: $(Join-Path $Packaging 'Output\MAHABOCW-Setup.exe')" -ForegroundColor Green
