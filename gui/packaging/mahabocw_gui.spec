# -*- mode: python ; coding: utf-8 -*-
"""
packaging/mahabocw_gui.spec

PyInstaller spec for the MAHABOCW GUI — pywebview + React edition.

Build order (run BOTH steps every time — a stale frontend_dist/ will
silently ship an outdated UI with no build-time error):
    1. npm run build   (inside gui/frontend/)
    2. pyinstaller packaging/mahabocw_gui.spec   (from gui/)

Output: gui/dist/mahabocw_gui/   (onedir, no console window)

NOTE: onedir is intentional.  onefile self-extracting binaries are flagged
by antivirus heuristics more often, which matters for a government-client
rollout.  Switch to onefile only after a clean onedir AV test.

Hidden imports:
    pywebview         — the main webview package
    clr               — pythonnet CLR bridge (required by pywebview's
                        edgechromium backend on Windows)
    webview.platforms.edgechromium
                      — pywebview's Windows WebView2 backend; this exact
                        module path was confirmed against pywebview 5.x.
                        Re-confirm if the pinned version changes.
    openpyxl.cell._writer
                      — openpyxl lazy import not caught by static analysis
    psutil            — process control (pause/resume/cancel)
    openpyxl          — row-count query in Api.start_pipeline()
"""

import os

# Root of the gui/ folder (one level up from this spec file).
GUI_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(GUI_ROOT, "app", "main.py")],
    pathex=[GUI_ROOT],
    binaries=[],
    datas=[
        # App icon
        (os.path.join(GUI_ROOT, "app", "resources", "icon.ico"), "resources"),
        # Built React/Vite SPA — must match _frontend_dist_path() in app/main.py.
        # Run `npm run build` in gui/frontend/ before this spec to keep it fresh.
        (os.path.join(GUI_ROOT, "frontend_dist"), "frontend_dist"),
    ],
    hiddenimports=[
        # pywebview + Windows backend
        "webview",
        "clr",
        "webview.platforms.edgechromium",
        # openpyxl lazy writer (row-count query)
        "openpyxl",
        "openpyxl.cell._writer",
        # process control
        "psutil",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Qt / PySide6 are no longer used — exclude everything.
        "PySide6",
        "PyQt5",
        "PyQt6",
        # Other heavy packages not needed by the GUI wrapper.
        "pandas",
        "playwright",
        "torch",
        "tensorflow",
        "matplotlib",
        "numpy",
        "PIL",
        "cv2",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries live next to the exe
    name="mahabocw_gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(GUI_ROOT, "app", "resources", "icon.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mahabocw_gui",
)
