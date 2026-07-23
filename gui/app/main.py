"""
app/main.py

Application entry point — pywebview edition.

Usage (from the gui/ directory):
    python -m app.main
    -- or --
    python app/main.py

PyInstaller uses this as the target script when building the executable.

DEV_MODE:
    Set MAHABOCW_GUI_DEV=1 to load the React app from the Vite dev server
    (http://localhost:5173) instead of the bundled static files.  This
    enables Vite hot-reload during UI development.

    Dev workflow:
        Terminal 1:  cd gui/frontend && npm run dev
        Terminal 2:  MAHABOCW_GUI_DEV=1 python -m app.main

Production:
    The entry HTML is at <bundle_root>/frontend_dist/index.html, which
    matches the datas tuple in packaging/mahabocw_gui.spec.
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

import webview  # noqa: E402 — must come after path fix
from app.api import Api  # noqa: E402


DEV_MODE: bool = os.environ.get("MAHABOCW_GUI_DEV") == "1"


def _frontend_dist_path() -> str:
    """
    Resolve the path to the bundled frontend index.html.

    In a PyInstaller onefile/onedir bundle, _MEIPASS is the temporary
    extraction directory that contains the datas entries.
    In development (non-frozen), the path is relative to this file.
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        # Non-frozen: gui/app/main.py → gui/ (one level up from app/)
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "frontend_dist", "index.html")


def main() -> None:
    api = Api()

    # In DEV_MODE load from the Vite dev server; in production load the
    # built static file.  Both paths resolve to the same React app.
    entry = "http://localhost:5173" if DEV_MODE else _frontend_dist_path()

    window = webview.create_window(
        "MAHABOCW Verification Tool",
        entry,
        js_api=api,
        width=1100,
        height=750,
        resizable=True,
        min_size=(800, 600),
        # Match the React app's deep background so there's no white flash
        # during the brief window before React hydrates.
        background_color="#080d18",
    )
    api.set_window(window)

    # ------------------------------------------------------------------
    # Window close guard
    # Prevent orphan subprocesses if the user closes the window mid-run.
    # pywebview's on_top confirmation dialog is used instead of QMessageBox.
    # ------------------------------------------------------------------
    def on_closing() -> bool:
        """
        Return True to allow the close, False to prevent it.
        Called on the main thread by pywebview before the window is destroyed.
        """
        if api._runner and api._runner._thread and api._runner._thread.is_alive():
            confirmed = window.create_confirmation_dialog(
                "Run in Progress",
                "A pipeline run is in progress.\n\n"
                "Cancel the run and exit? Progress already saved will not be lost.",
            )
            if confirmed:
                api._runner.cancel()
                return True   # allow close
            return False      # prevent close
        return True           # no active run — allow close

    window.events.closing += on_closing

    webview.start(debug=DEV_MODE)


if __name__ == "__main__":
    main()
