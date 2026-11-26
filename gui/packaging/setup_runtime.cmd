@echo off
rem ---------------------------------------------------------------------------
rem setup_runtime.cmd  [cpu|gpu]
rem
rem Installs the pipeline's Python packages and Playwright Chromium into the
rem PRIVATE runtime shipped by MAHABOCW-Setup.exe.  Installed to
rem   {app}\tools\setup_runtime.cmd
rem and run by the installer after files are copied.  Safe to re-run by hand
rem (as administrator) to repair an install.
rem
rem Exit codes: 0 ok, 10 runtime missing, 11 pip (shared), 12 pip (paddle),
rem             13 chromium, 14 import check failed.
rem Everything is logged to {app}\install.log.
rem ---------------------------------------------------------------------------
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PY=%ROOT%\runtime\python.exe"
set "PIPE=%ROOT%\pipeline"
set "LOG=%ROOT%\install.log"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=cpu"

set "PLAYWRIGHT_BROWSERS_PATH=%ROOT%\browsers"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PYTHONUTF8=1"

if exist "%ROOT%\.setup_complete" del /q "%ROOT%\.setup_complete"
echo ==== %DATE% %TIME%  setup_runtime (%MODE%) ==== >> "%LOG%"

if not exist "%PY%" (
  echo Private Python runtime not found: %PY% >> "%LOG%"
  exit /b 10
)

echo --- pip install shared dependencies >> "%LOG%"
"%PY%" -m pip install --no-warn-script-location -r "%PIPE%\requirements-lock.txt" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 11

echo --- pip install paddle (%MODE%, --no-deps) >> "%LOG%"
"%PY%" -m pip install --no-warn-script-location --no-deps -r "%PIPE%\requirements-paddle-%MODE%.txt" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 12

echo --- playwright install chromium >> "%LOG%"
"%PY%" -m playwright install chromium >> "%LOG%" 2>&1
if errorlevel 1 exit /b 13

echo --- import check >> "%LOG%"
set "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python"
"%PY%" -c "import pandas, openpyxl, playwright, bs4, fitz, cv2, PIL, ollama, paddle, paddleocr, google.genai, rapidfuzz, dotenv, tqdm; print('imports ok')" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 14

type nul > "%ROOT%\.setup_complete"
echo ==== setup_runtime finished OK ==== >> "%LOG%"
exit /b 0
