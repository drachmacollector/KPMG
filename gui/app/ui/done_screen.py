"""
app/ui/done_screen.py

Done screen — shown after the pipeline finishes successfully.

Provides three actions:
  1. Open the output Excel file directly (os.startfile).
  2. Open the most recent log file from the pipeline's logs/ folder.
  3. Run again — navigate back to the Run screen with the same settings.
"""
from __future__ import annotations

import os
import glob
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from app.settings import Settings
from app.ui.styles import COLORS


class DoneScreen(QWidget):
    """
    Success / completion screen.

    Signals
    -------
    run_again()
        User wants to go back to the Run screen for another run.
    """

    run_again = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings: Optional[Settings] = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # Central card
        center = QWidget()
        center.setStyleSheet(f"background: {COLORS['bg_base']};")
        center_layout = QVBoxLayout(center)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(0)

        card = self._build_card()
        center_layout.addWidget(card)
        root.addWidget(center, stretch=1)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(90)
        header.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLORS['bg_deep']}, stop:1 {COLORS['bg_surface']});"
            f"border-bottom: 1px solid {COLORS['border']};"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(40, 20, 40, 20)
        title = QLabel("Run Complete")
        title.setObjectName("heading")
        layout.addWidget(title)
        layout.addStretch()
        badge = QLabel("Step 3 of 2 — Done ✓")
        badge.setStyleSheet(
            f"color: {COLORS['success']}; font-size: 12px; "
            f"background: rgba(34,197,94,0.1); border-radius: 12px; "
            f"padding: 4px 12px; border: 1px solid rgba(34,197,94,0.3);"
        )
        layout.addWidget(badge)
        return header

    def _build_card(self) -> QWidget:
        card = QWidget()
        card.setFixedWidth(520)
        card.setStyleSheet(
            f"background: {COLORS['bg_card']}; "
            f"border-radius: 16px; "
            f"border: 1px solid {COLORS['border']};"
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Checkmark icon
        icon = QLabel("✅")
        icon.setStyleSheet("font-size: 48px; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        # Title
        title = QLabel("Pipeline Finished Successfully")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {COLORS['text_primary']}; "
            f"background: transparent;"
        )
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Output file path label
        self._output_path_label = QLabel("")
        self._output_path_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px; "
            f"background: {COLORS['bg_elevated']}; border-radius: 8px; "
            f"padding: 8px 12px; border: 1px solid {COLORS['border']};"
        )
        self._output_path_label.setWordWrap(True)
        self._output_path_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._output_path_label)

        layout.addSpacerItem(
            QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )

        # Action buttons
        self._open_output_btn = QPushButton("📂  Open Output File")
        self._open_output_btn.setObjectName("success_btn")
        self._open_output_btn.setFixedHeight(44)
        self._open_output_btn.setCursor(Qt.PointingHandCursor)
        self._open_output_btn.clicked.connect(self._open_output)
        layout.addWidget(self._open_output_btn)

        self._open_log_btn = QPushButton("📋  Open Latest Log File")
        self._open_log_btn.setFixedHeight(44)
        self._open_log_btn.setCursor(Qt.PointingHandCursor)
        self._open_log_btn.clicked.connect(self._open_log)
        layout.addWidget(self._open_log_btn)

        again_btn = QPushButton("↩  Run Again")
        again_btn.setObjectName("ghost")
        again_btn.setFixedHeight(44)
        again_btn.setCursor(Qt.PointingHandCursor)
        again_btn.clicked.connect(self.run_again)
        layout.addWidget(again_btn)

        return card

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure(self, settings: Settings) -> None:
        """Update the screen with the finished run's settings."""
        self._settings = settings
        self._output_path_label.setText(
            f"Output saved to:\n{settings.output_file}"
        )
        self._open_output_btn.setEnabled(os.path.isfile(settings.output_file))
        self._open_log_btn.setEnabled(bool(self._latest_log_path()))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _open_output(self) -> None:
        if self._settings and os.path.isfile(self._settings.output_file):
            os.startfile(self._settings.output_file)

    def _open_log(self) -> None:
        log_path = self._latest_log_path()
        if log_path:
            os.startfile(log_path)

    def _latest_log_path(self) -> Optional[str]:
        """Return the most recently modified .log file in the pipeline's logs/ folder."""
        if not self._settings or not self._settings.pipeline_dir:
            return None
        log_dir = os.path.join(self._settings.pipeline_dir, "logs")
        pattern = os.path.join(log_dir, "*.log")
        log_files = glob.glob(pattern)
        if not log_files:
            return None
        return max(log_files, key=os.path.getmtime)
