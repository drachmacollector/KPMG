"""
app/main.py

Application entry point.

Usage (from the gui/ directory):
    python -m app.main
    -- or --
    python app/main.py

PyInstaller uses this as the target script when building the executable.
"""
from __future__ import annotations

import os
import sys


def _add_gui_to_path() -> None:
    """
    Make sure the gui/ directory is on sys.path so that `app.*` imports work
    whether the script is launched as a module, a bare script, or from a
    PyInstaller bundle.
    """
    gui_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if gui_dir not in sys.path:
        sys.path.insert(0, gui_dir)


_add_gui_to_path()

from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET


def _resource_path(relative: str) -> str:
    """
    Resolve a path relative to this file, handling both normal and PyInstaller
    frozen environments (sys._MEIPASS).
    """
    if hasattr(sys, "_MEIPASS"):
        # Running inside a PyInstaller bundle.
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


def main() -> int:
    # High-DPI support (PySide6 enables it by default on Qt6, but be explicit).
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("MAHABOCW Verification Tool")
    app.setOrganizationName("KPMG")
    app.setApplicationVersion("1.0.0")

    # Apply the global dark stylesheet.
    app.setStyleSheet(APP_STYLESHEET)

    # Prefer Segoe UI on Windows; fall back gracefully.
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    icon_path = _resource_path(os.path.join("resources", "icon.ico"))
    window = MainWindow(icon_path=icon_path)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
