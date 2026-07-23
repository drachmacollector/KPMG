# MAHABOCW GUI — Developer Guide

This document covers the `gui/` subfolder only.  
For the pipeline itself, see the root-level `README.md` on `main`.

---

## Branch context

This code lives on the `desktop-app` branch.  
Pipeline files (`verify_colleges.py`, `extractor.py`, etc.) are present at the **repo root** but must never be modified on this branch — see [ARCHITECTURE.md](../docs/ARCHITECTURE.md) for the full rationale.

---

## Quick start (dev)

```powershell
# 1. Activate (or create) a dedicated venv for the GUI
python -m venv gui_venv
.\gui_venv\Scripts\Activate.ps1

# 2. Install GUI dependencies (small, fast)
pip install -r gui/requirements.txt

# 3. Launch the app from the repo root (so imports resolve correctly)
python -m gui.app.main
# -- or from inside the gui/ folder:
cd gui
python -m app.main
```

The app opens at the Settings screen.  
Point **Pipeline Folder** at the repo root (where `verify_colleges.py` lives) for local development.

---

## Project structure

```
gui/
├── app/
│   ├── __init__.py
│   ├── main.py              # QApplication entry point
│   ├── settings.py          # Settings dataclass + JSON persistence
│   ├── runner.py            # PipelineRunner QThread (core subprocess logic)
│   └── ui/
│       ├── __init__.py
│       ├── styles.py        # Centralised Qt stylesheet + colour palette
│       ├── main_window.py   # QMainWindow + QStackedWidget (3 screens)
│       ├── settings_screen.py
│       ├── run_screen.py
│       └── done_screen.py
├── packaging/
│   ├── mahabocw_gui.spec    # PyInstaller build spec
│   ├── version_info.txt     # Windows version resource
│   ├── gui-installer.iss    # GUI Inno Setup installer script (MAHABOCW-GUI-Setup.exe)
│   └── pipeline_installer.iss  # Pipeline Inno Setup installer (MAHABOCW-Pipeline-Setup.exe)
├── requirements.txt         # PySide6, psutil, openpyxl only
└── README.md                # This file
```

---

## Settings persistence

Settings are stored in `%APPDATA%\MAHABOCW-GUI\settings.json`.  
The file is never written inside the pipeline repo directory.

`settings.py` also exports `default_pipeline_dir()` which returns
`C:\ProgramData\MAHABOCW\pipeline` if `verify_colleges.py` is present there,
or `""` otherwise. `Settings.load()` calls this automatically when `pipeline_dir`
is empty, so the Settings screen is pre-filled after `MAHABOCW-Pipeline-Setup.exe`
has been run — the user never needs to click Browse for that field on a fresh install.

---

## Building the installer

### 1. Install build tools (one-time)

```powershell
pip install pyinstaller
# Install Inno Setup from https://jrsoftware.org/isinfo.php
```

### 2. Build the PyInstaller onedir

```powershell
# From the gui/ folder:
cd gui
pyinstaller packaging/mahabocw_gui.spec
# Output: gui/dist/mahabocw_gui/
```

### 3. Generate the icon (if not already present)

Place a 256×256 `.ico` file at `gui/app/resources/icon.ico`.

### 4. Build the Inno Setup installers

There are two independent installer scripts:

**GUI installer** (`gui-installer.iss`) → `MAHABOCW-GUI-Setup.exe`
1. Open `gui/packaging/gui-installer.iss` in **Inno Setup Compiler** and click **Build**.
   (`gui-installer.iss` references `docs/SETUP_INSTRUCTIONS.md` at the repo root directly — no manual copy needed.)
2. Output: `gui/packaging/Output/MAHABOCW-GUI-Setup.exe`.

**Pipeline installer** (`pipeline_installer.iss`) → `MAHABOCW-Pipeline-Setup.exe`
1. Open `gui/packaging/pipeline_installer.iss` in **Inno Setup Compiler** and click **Build**.
   Source files are referenced two levels up from the script (the repo root), so the
   `.py` files and `requirements-lock-cpu.txt` must be present there.
2. Output: `gui/packaging/Output/MAHABOCW-Pipeline-Setup.exe`.
3. Running the resulting `.exe` on a client machine:
   - Verifies Python is on PATH (aborts with a clear message if not).
   - Copies the pipeline `.py` files to `C:\ProgramData\MAHABOCW\pipeline`.
   - Silently runs `pip install -r requirements-lock-cpu.txt` and
     `playwright install chromium` (no terminal window shown to the user).
   - All pip/playwright output is logged to
     `C:\ProgramData\MAHABOCW\pipeline\install.log`.

---

## Key design decisions

| Decision | Rationale |
|---|---|
| Subprocess boundary (no `import verify_colleges`) | Pipeline files stay completely untouched; GUI runs on a separate env |
| `PYTHONUNBUFFERED=1` injected into subprocess env | Ensures stdout arrives line-by-line when piped, not buffered |
| `psutil.suspend()` / `.resume()` for Pause | Suspends at OS level, zero cooperation needed from the pipeline |
| Login detection via `"Press ENTER here"` substring | Exact string from `verify_colleges.py` line 426 — update both if the pipeline prompt text ever changes |
| ACK lines for progress (not tqdm) | tqdm's `\r`-based rewrites behave unreliably once piped; `Acknowledgement:` lines are stable |
| `--onedir` PyInstaller mode | Faster startup, easier post-build patching vs `--onefile` |

---

## Merging pipeline updates

When `main` gets new pipeline commits:

```powershell
# On the desktop-app branch:
git merge main
# Resolve any conflicts only in pipeline files if they were accidentally touched here.
# The gui/ folder has no counterpart on main, so it's never in conflict.
```
