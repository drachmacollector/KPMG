# MAHABOCW Desktop App Architecture

This document details the architecture of the MAHABOCW desktop application (GUI) built on top of the underlying verification pipeline.

*(Note: The architecture for the core verification pipeline is maintained on the `main` branch. This document is focused strictly on the new PySide6 GUI wrapper and its packaging.)*

## 1. System Overview

The desktop app is a PySide6-based graphical wrapper around the existing `verify_colleges.py` script. It provides a user-friendly way to configure, run, and monitor the pipeline without touching the terminal or modifying the core pipeline code.

- **Framework**: PySide6 (Qt for Python)
- **Design Language**: Dark mode, glassmorphism-inspired UI with Indigo accents.
- **Process Model**: The GUI runs in a lightweight, independent Python environment. It launches the heavy verification pipeline as a separate subprocess, communicating via `stdout`/`stderr` and environment variables.
- **Packaging**: PyInstaller for binary bundling, Inno Setup for the Windows installer.

## 2. Directory Structure

The GUI code is entirely contained within the `gui/` directory to maintain strict separation from the pipeline codebase:

```text
gui/
├── app/
│   ├── __init__.py
│   ├── main.py                  # QApplication entry point
│   ├── settings.py              # Configuration dataclass & JSON persistence
│   ├── runner.py                # PipelineRunner QThread (subprocess manager)
│   └── ui/
│       ├── styles.py            # Centralized stylesheet (CSS/QSS)
│       ├── main_window.py       # QMainWindow & QStackedWidget navigation
│       ├── settings_screen.py   # Settings configuration screen
│       ├── run_screen.py        # Live execution & logs screen
│       └── done_screen.py       # Completion & actions screen
├── packaging/
│   ├── mahabocw_gui.spec        # PyInstaller spec file
│   ├── version_info.txt         # Windows executable metadata
│   └── installer.iss            # Inno Setup compilation script
├── requirements.txt             # Lightweight GUI dependencies (PySide6, psutil, openpyxl)
└── README.md                    # Developer guide for the GUI
```

## 3. Component Details

### `PipelineRunner` (Subprocess Management)
Located in `app/runner.py`. The GUI does not import pipeline modules directly. Instead, it spawns `verify_colleges.py` as a subprocess using Python's `subprocess.Popen`.
- Environment variables (`MAHABOCW_INPUT_FILE`, `MAHABOCW_SHEET_NAME`, `MAHABOCW_OUTPUT_FILE`, `GEMINI_API_KEY`) are used to pass configuration to the pipeline.
- `PYTHONUNBUFFERED=1` is injected into the subprocess environment to ensure log lines stream in real-time.
- The pipeline's `stdout` and `stderr` are piped and read line-by-line by the `PipelineRunner` thread, emitting PyQt Signals (`log_line`, `progress`, `awaiting_login`, `finished_ok`, `finished_error`) back to the main UI thread.
- **Process Control**: Uses `psutil.Process(pid).suspend()` and `.resume()` to pause the entire pipeline process tree at the OS level. This means zero changes were required to the pipeline's codebase to support pausing.

### UI Screens (`app/ui/`)
Controlled by a `QStackedWidget` hosted in `MainWindow` for seamless transitions.
1. **SettingsScreen**: Allows users to select the pipeline folder, python interpreter, input file, and output file. Validates configurations and uses `openpyxl` to populate a dropdown of available Excel sheets directly from the chosen file.
2. **RunScreen**: Displays a live streaming log with smart auto-scroll, a progress bar (driven by matching "Acknowledgement: ACK-..." regex in the log stream), and controls to Pause, Resume, or Cancel the pipeline.
3. **DoneScreen**: Shown when the pipeline finishes. Provides buttons to easily open the generated output Excel file, the latest log file, or start a new run.

### Settings Persistence
Located in `app/settings.py`. User settings are persisted as a JSON file in the user's `%APPDATA%\MAHABOCW-GUI` directory (hyphen, matching the `CONFIG_DIR` constant in `settings.py`). Unknown keys are ignored during load to ensure forward compatibility with future configuration updates.

## 4. Packaging and Distribution

The app is packaged for Windows deployment to allow non-technical users to install and run it easily.

1. **PyInstaller**: Configured via `packaging/mahabocw_gui.spec` to use `--onedir` mode (for faster startup and easy patchability) and `--noconsole` (to hide the background terminal window).
2. **Inno Setup**: The `packaging/installer.iss` script bundles the PyInstaller output into a standard Windows Setup (`.exe`) file. It handles creating Start Menu and Desktop shortcuts and provides a seamless installation wizard.

## 5. Security & Isolation

The strict architectural separation between the GUI and the Pipeline ensures:
- **Dependency Isolation**: The GUI only requires `PySide6`, `psutil`, and `openpyxl` (~100MB). The heavy AI/OCR dependencies (PaddlePaddle, Playwright, Ollama, etc.) remain solely in the pipeline's environment, preventing dependency conflicts and keeping the GUI bundle small.
- **Fault Tolerance**: If the GUI crashes or is closed abruptly, the `closeEvent` hook ensures the pipeline subprocess is safely terminated. If the pipeline crashes, the GUI catches the exit code and displays the error gracefully without going down itself.
