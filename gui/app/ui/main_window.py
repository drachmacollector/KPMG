"""
app/ui/main_window.py

QMainWindow — the top-level window that hosts the three-screen QStackedWidget.

Screen indices:
    0 — SettingsScreen
    1 — RunScreen
    2 — DoneScreen

Navigation flow:
    Settings ──[Save & Continue]──▶ Run
    Run ──────[⚙ Settings]────────▶ Settings
    Run ──────[finished_ok]────────▶ Done
    Done ─────[Run Again]──────────▶ Run
"""
from __future__ import annotations

import openpyxl
import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from app.settings import Settings
from app.ui.settings_screen import SettingsScreen
from app.ui.run_screen import RunScreen
from app.ui.done_screen import DoneScreen

# Screen index constants
IDX_SETTINGS = 0
IDX_RUN = 1
IDX_DONE = 2


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self, icon_path: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MAHABOCW Verification Tool")
        self.setMinimumSize(1000, 680)
        self.resize(1100, 750)

        if icon_path and os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._settings_screen = SettingsScreen()
        self._run_screen = RunScreen()
        self._done_screen = DoneScreen()

        self._stack.addWidget(self._settings_screen)   # index 0
        self._stack.addWidget(self._run_screen)         # index 1
        self._stack.addWidget(self._done_screen)        # index 2

        self._connect_signals()
        self._stack.setCurrentIndex(IDX_SETTINGS)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # Settings screen → Run screen
        self._settings_screen.proceed.connect(self._on_settings_proceed)

        # Run screen → Settings screen (back link)
        self._run_screen.request_settings.connect(self._go_settings)

        # Run screen → Done screen
        self._run_screen.finished.connect(self._on_run_finished)

        # Done screen → Run screen
        self._done_screen.run_again.connect(self._go_run)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_settings_proceed(self, settings: Settings) -> None:
        """Called when the user saves Settings and clicks Continue."""
        total_rows = self._count_input_rows(settings)
        self._run_screen.configure(settings, total_rows)
        self._stack.setCurrentIndex(IDX_RUN)

    def _go_settings(self) -> None:
        """Navigate to Settings (only when no run is active)."""
        if self._run_screen.has_active_runner():
            QMessageBox.information(
                self,
                "Run in Progress",
                "A run is currently active. Pause or cancel it before changing settings.",
            )
            return
        self._settings_screen.refresh()
        self._stack.setCurrentIndex(IDX_SETTINGS)

    def _on_run_finished(self) -> None:
        """Navigate to Done after a successful run."""
        if self._run_screen._settings:
            self._done_screen.configure(self._run_screen._settings)
        self._stack.setCurrentIndex(IDX_DONE)

    def _go_run(self) -> None:
        """Navigate back to Run screen for another run (from Done)."""
        self._stack.setCurrentIndex(IDX_RUN)

    # ------------------------------------------------------------------
    # Window close guard
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Prompt before closing while a run is active to avoid orphan subprocesses."""
        if self._run_screen.has_active_runner():
            reply = QMessageBox.question(
                self,
                "Run in Progress",
                "A pipeline run is in progress.\n\n"
                "Cancel the run and exit? Progress already saved will not be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._run_screen.cancel_runner()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_input_rows(settings: Settings) -> Optional[int]:
        """
        Count the number of data rows in the input workbook (read-only, fast).
        Returns None if anything goes wrong — the Run screen handles None gracefully
        by showing an indeterminate progress counter.
        """
        try:
            wb = openpyxl.load_workbook(settings.input_file, read_only=True)
            ws = wb[settings.sheet_name]
            # max_row includes the header row — subtract 1 for data rows.
            total = (ws.max_row or 1) - 1
            wb.close()
            return max(total, 0) or None
        except Exception:
            return None
