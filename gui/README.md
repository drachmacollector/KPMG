# MAHABOCW desktop app — developer guide

This guide covers `gui/` only: the pywebview + React/Tailwind desktop app and the installer build. For the design (bridge API, event protocol, install layout), see [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) Part B.

## Layout

```
gui/
├── app/                    Python backend (no UI toolkit)
│   ├── main.py             pywebview entry point + close guard
│   ├── api.py              Api — the only JS bridge surface
│   ├── runner.py           PipelineRunner — subprocess, events, stop/pause
│   ├── settings.py         Settings, DPAPI keys, install-layout detection
│   └── resources/          icons
├── frontend/               React + Vite + Tailwind source
│   └── src/{App.jsx, components/, lib/, index.css}
├── frontend_dist/          build output (gitignored) — bundled by PyInstaller
├── packaging/
│   ├── build.ps1           one-shot release build → Output/MAHABOCW-Setup.exe
│   ├── mahabocw_gui.spec   PyInstaller (onedir, windowed)
│   ├── mahabocw_setup.iss  Inno Setup — the single installer
│   ├── setup_runtime.cmd   pip + Chromium into the private runtime (also "Repair")
│   └── version_info.txt
└── requirements.txt        pywebview, pythonnet, psutil, openpyxl, pyinstaller
```

## Run in development

```powershell
python -m venv gui_venv
.\gui_venv\Scripts\Activate.ps1
pip install -r gui\requirements.txt

cd gui\frontend; npm ci; npm run build; cd ..
python -m app.main
```

When not frozen, the app uses the repo root as the pipeline folder and `python` on PATH as the interpreter. Override either under **Settings → Advanced**, for example pointing the interpreter at the pipeline venv (`..\venv\Scripts\python.exe`). The System check shows an **Ignore (dev)** link in this mode.

For hot reload, run `npm run dev` in `gui\frontend` and start the app with `$env:MAHABOCW_GUI_DEV = "1"; python -m app.main`.

Settings are stored in `%APPDATA%\MAHABOCW-GUI\settings.json`, with API keys DPAPI-encrypted. Run data (logs, downloads, cache) goes to `%LOCALAPPDATA%\MAHABOCW`.

## Build the installer

Prerequisites: Node.js 20+ and Inno Setup 6 or 7. The `-Python` interpreter must have `gui\requirements.txt` installed.

```powershell
powershell -ExecutionPolicy Bypass -File gui\packaging\build.ps1 -Python .\gui_venv\Scripts\python.exe
```

Output: `gui\packaging\Output\MAHABOCW-Setup.exe`. Use `-SkipInstaller` to stop after PyInstaller and the runtime download. The script fails if `frontend_dist` is older than the frontend sources, so a stale UI cannot be shipped.

To test the installer, use a clean machine or **Windows Sandbox**:
1. Install with CPU mode.
2. Check `C:\Program Files\MAHABOCW\install.log` ends with "finished OK".
3. Launch the app as a standard user and follow the System check.

## Tests

```powershell
python -m pytest tests          # from the repo root; needs pytest + psutil
cd gui\frontend; npm run lint
```

`tests/test_gui_backend.py` drives `PipelineRunner` against a dummy pipeline script. It covers events, progress with skipped rows, graceful stop and force stop.
