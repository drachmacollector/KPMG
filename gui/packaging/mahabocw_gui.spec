# -*- mode: python ; coding: utf-8 -*-
"""
packaging/mahabocw_gui.spec

PyInstaller spec for the MAHABOCW GUI.

Build from the gui/ directory:
    pyinstaller packaging/mahabocw_gui.spec

Output: gui/dist/mahabocw_gui/   (onedir, no console window)

Notes:
  - console=False  — no terminal window appears behind the GUI.
  - icon.ico is bundled as the executable icon.
  - The entire app/ package is collected via pathex pointing at gui/.
  - PySide6 Qt plugins are collected automatically by PyInstaller's
    hook-PySide6 hooks; no manual hiddenimport is usually needed.
"""

import os

# Root of the gui/ folder (one level up from this spec file).
GUI_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(GUI_ROOT, "app", "main.py")],
    pathex=[GUI_ROOT],
    binaries=[],
    datas=[
        # Bundle the icon so _resource_path() can find it inside the bundle.
        (os.path.join(GUI_ROOT, "app", "resources", "icon.ico"), "resources"),
    ],
    hiddenimports=[
        "psutil",
        "openpyxl",
        "openpyxl.cell._writer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages that are NOT needed by the GUI.
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
