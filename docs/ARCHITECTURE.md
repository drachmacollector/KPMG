# MAHABOCW Desktop App Architecture

This document details the architecture of the MAHABOCW desktop application (GUI) built on top of the underlying verification pipeline.

*(Architecture for the core verification pipeline is maintained on the `main` branch. This document covers the GUI wrapper and its packaging.)*

> **Architectural change — pywebview migration (2026-07):**
> The GUI was originally built with PySide6/QWidgets. It has been fully migrated to
> **pywebview + React/Tailwind**, replacing the QWidget layer while keeping the Python
> subprocess management layer (`PipelineRunner`, `settings.py`) intact.
> `ARCHITECTURE.md` has been updated in the same change per the documentation rule in `AGENTS.md`.

---

## 1. System Overview

The desktop app is a thin Python backend wrapped around the existing `verify_colleges.py`
subprocess, with a React/Tailwind SPA rendered via the OS-native Edge WebView2 runtime
through `pywebview`.

- **Frontend**: React 18 + Vite + Tailwind CSS 3 — a single-page app with four sequential screens (Splash → Settings → Run → Done).
- **Backend**: Plain Python (`app/main.py`, `app/api.py`, `app/runner.py`, `app/settings.py`). No Qt, no event loop.
- **Bridge**: `window.pywebview.api` (pull) + `CustomEvent` dispatched via `window.evaluate_js()` (push).
- **Process Model**: Same as before — the GUI spawns `verify_colleges.py` as a subprocess and communicates via `stdout`/`stderr` and environment variables.
- **Packaging**: PyInstaller (onedir) → Inno Setup. Now a two-step build: `npm run build` must precede PyInstaller.

---

## 2. Directory Structure

```text
gui/
├── app/
│   ├── __init__.py
│   ├── main.py          # pywebview entry point (create_window, on_closing guard)
│   ├── api.py           # Api class — sole JS bridge surface (window.pywebview.api)
│   ├── settings.py      # Settings dataclass + JSON persistence + module-level wrappers
│   ├── runner.py        # PipelineRunner (threading.Thread, subprocess, psutil)
│   └── ui/              # KEPT FOR REFERENCE — old PySide6 screens (not imported)
├── frontend/            # React/Vite source
│   ├── src/
│   │   ├── lib/bridge.js          # call() + on() bridge helpers
│   │   ├── components/
│   │   │   ├── Splash.jsx
│   │   │   ├── Settings.jsx
│   │   │   ├── Run.jsx
│   │   │   └── Done.jsx
│   │   ├── App.jsx                # 4-screen state machine
│   │   ├── index.css              # Tailwind + CSS variables (COLORS palette)
│   │   └── main.jsx
│   ├── vite.config.js             # base: './' — critical for pywebview local serving
│   └── tailwind.config.js
├── frontend_dist/       # Built SPA — output of `npm run build` (gitignored)
├── packaging/
│   ├── mahabocw_gui.spec          # PyInstaller spec (pywebview hiddenimports, frontend datas)
│   ├── version_info.txt
│   ├── installer.iss              # GUI installer (includes WebView2 bootstrapper)
│   └── pipeline_installer.iss
└── README.md
```

---

## 3. Component Details

### 3.1 `Api` class (`app/api.py`) — the sole bridge surface

`Api` is exposed as `window.pywebview.api` in React. Every public method is callable
from JS. Methods are grouped:

| Method | Direction | Description |
|---|---|---|
| `get_initial_state()` | Pull | Returns `{settings: {...}, default_pipeline_dir: str}` on React mount |
| `pick_pipeline_folder()` | Pull | OS-native folder picker dialog |
| `pick_input_file()` | Pull | OS-native open-file dialog (Excel filter) |
| `pick_output_file()` | Pull | OS-native save-file dialog (Excel filter) |
| `pick_python_exe()` | Pull | OS-native open-file dialog (exe filter) |
| `get_sheet_names(path)` | Pull | Read sheet names from an Excel workbook via openpyxl |
| `test_python(exe)` | Pull | Run `exe --version`, return `{ok, version, error}` |
| `save_settings(dict)` | Command | Persist settings to `%APPDATA%\MAHABOCW-GUI\settings.json` |
| `start_pipeline(dict)` | Command | Count rows, create `PipelineRunner`, start thread. Returns `{ok, total_rows}` |
| `pause_pipeline()` | Command | Suspend subprocess (psutil) |
| `resume_pipeline()` | Command | Resume subprocess (psutil) |
| `cancel_pipeline()` | Command | Terminate process tree (psutil) |
| `confirm_login()` | Command | Send `\n` to subprocess stdin to unblock `input()` |
| `open_file(path)` | Command | `os.startfile(path)` |
| `open_log(pipeline_dir)` | Command | `os.startfile(latest .log in pipeline_dir/logs/)` |

**Push events** — dispatched from the background thread via `window.evaluate_js()`:

| Event name | Payload | Trigger |
|---|---|---|
| `pipeline-log` | `{line: str}` | Every stdout/stderr line from the subprocess |
| `pipeline-awaiting-login` | `{}` | Once when the pipeline's `input()` prompt appears |
| `pipeline-progress` | `{count: int, total: int\|null}` | Each `Acknowledgement:` line in stdout |
| `pipeline-done` | `{claims_seen: int, output_file: str}` | Subprocess exited with code 0 |
| `pipeline-error` | `{message: str}` | Non-zero exit, cancellation, or launch failure |

**UTF-8 safety**: payloads are `json.dumps → utf-8 encode → base64` on the Python side.
The injected JS decodes with `Uint8Array + TextDecoder('utf-8')` (not bare `atob()`) so
multi-byte characters in Marathi college names survive the round-trip correctly.

### 3.2 `PipelineRunner` (`app/runner.py`)

Unchanged internal logic. The only architectural changes:

| Before (PySide6) | After (pywebview) |
|---|---|
| `class PipelineRunner(QThread)` | `class PipelineRunner:` (plain class) |
| `QThread.start()` | `threading.Thread(target=self._run, daemon=True).start()` |
| `self.log_line.emit(line)` | `self.api.push_log({"line": line})` |
| `self.awaiting_login.emit()` | `self.api.push_awaiting_login()` |
| `self.progress.emit(n)` | `self.api.push_progress({"count": n, "total": ...})` |
| `self.finished_ok.emit()` | `self.api.push_done({"claims_seen": n, "output_file": ...})` |
| `self.finished_error.emit(msg)` | `self.api.push_error({"message": msg})` |

**Reason for change**: `QThread`/`Signal` requires a live Qt event loop (`QApplication.exec()`)
to deliver queued signal connections across threads. Once the QWidgets main window is deleted,
nothing runs a Qt event loop — so even if `PipelineRunner` still imported Qt, its signals
would not fire reliably. `threading.Thread` + `evaluate_js()` works entirely without Qt.

All subprocess piping, the character-by-character stdout reader (needed to catch the login
prompt that lacks a trailing newline), psutil pause/resume/cancel, and the full process-tree
kill are preserved exactly.

### 3.3 React Frontend (`gui/frontend/src/`)

| File | Responsibility |
|---|---|
| `lib/bridge.js` | `call(method, ...args)` → async pywebview call; `on(event, handler)` → CustomEvent listener with cleanup |
| `App.jsx` | `useState<'splash'\|'settings'\|'run'\|'done'>` linear state machine |
| `components/Splash.jsx` | Welcome screen with animated launch button |
| `components/Settings.jsx` | All form fields; calls `get_initial_state()` on mount (fixes pipeline-folder auto-populate bug) |
| `components/Run.jsx` | Log pane, progress bar, elapsed timer, login confirmation banner, pause/resume/cancel |
| `components/Done.jsx` | Shows `claims_seen` + `output_file` from `push_done` payload; open file/log buttons |

The login confirmation banner on the Run screen is the React equivalent of the old
`QWidget` login banner: it appears when `pipeline-awaiting-login` fires and exposes
a "Continue" button wired to `api.confirm_login()`.

### 3.4 Settings Persistence (`app/settings.py`)

Unchanged. `Settings.load()` / `Settings.save()` continue to use
`%APPDATA%\MAHABOCW-GUI\settings.json`. Two new module-level functions —
`load_settings() → dict` and `save_settings(dict)` — are thin wrappers that let
`api.py` work with plain JS-compatible dicts instead of the dataclass directly.

---

## 4. Build Pipeline

The build is now two steps and **must be run in this order every time**:

```powershell
# Step 1 — build the React SPA
cd gui/frontend
npm run build
# Output: gui/frontend/dist/  (copied to gui/frontend_dist/ for PyInstaller)

# Step 2 — bundle with PyInstaller
cd gui
pyinstaller packaging/mahabocw_gui.spec
```

A PyInstaller build run without step 1 first will ship a stale or missing frontend
with no build-time error.

Node.js 20 LTS or later is required for the frontend build.

---

## 5. Packaging and Distribution

### 5.1 GUI Installer (`MAHABOCW-GUI-Setup.exe`)

1. **PyInstaller** (`mahabocw_gui.spec`): `onedir` mode, no console window.
   Key hidden imports: `pywebview`, `clr` (pythonnet), `webview.platforms.edgechromium`.
   Key datas: `frontend_dist/` → `frontend_dist` inside the bundle.
2. **Inno Setup** (`installer.iss`): Bundles PyInstaller output. Creates Start Menu and
   Desktop shortcuts. Runs the Microsoft Edge **WebView2 Evergreen Bootstrapper** silently
   before first launch — this is a no-op if the runtime is already present (true of most
   current Windows 10/11 machines), but ensures it installs on machines where it's missing.
   Requires `PrivilegesRequired=admin` because the bootstrapper writes to HKLM.

### 5.2 Pipeline Installer (`MAHABOCW-Pipeline-Setup.exe`)

Unchanged — see previous version of this section.

### 5.3 Auto-detection in `settings.py`

Unchanged — `default_pipeline_dir()` pre-fills the Settings screen after the pipeline
installer has run. The `get_initial_state()` pull call on React mount is the mechanism
that delivers this value to the frontend, fixing the previously-open pipeline-folder bug.

---

## 6. Security & Isolation

- **Dependency Isolation**: The GUI Python environment only needs `pywebview`, `pythonnet`,
  `psutil`, and `openpyxl` (the heavy AI/OCR stack stays in the pipeline's environment).
- **Fault Tolerance**: The `on_closing` event handler in `main.py` ensures the pipeline
  subprocess is cancelled before the window closes mid-run.
- **No network from GUI**: The pywebview window loads a local `file://` URL in production;
  all network access is through the pipeline subprocess.
