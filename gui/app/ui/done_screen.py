"""
app/ui/done_screen.py

Done screen — shown after the pipeline finishes successfully.

Provides four actions:
  1. Open the output Excel file directly (os.startfile).
  2. Open the most recent log file from the pipeline's logs/ folder.
  3. Run again — navigate back to the Run screen with the same settings.
  4. Run on custom range — navigate to Settings to adjust the row range.

The central card fades in on show via QPropertyAnimation.
"""
from __future__ import annotations

import os
import glob
from typing import Optional

from PySide6.QtCore import (
    Qt,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
    QScrollArea,
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
    run_custom_range()
        User wants to go back to Settings to change the row range before running.
    """

    run_again = Signal()
    run_custom_range = Signal()

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

        # Accent top bar — green for done
        top_bar = QFrame()
        top_bar.setFixedHeight(3)
        top_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLORS['success']}, stop:1 #86efac);"
        )
        root.addWidget(top_bar)

        root.addWidget(self._build_header())

        # Scrollable centre area (so card never gets clipped on small windows)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {COLORS['bg_base']};")

        center_widget = QWidget()
        center_widget.setStyleSheet(f"background: {COLORS['bg_base']};")
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        center_layout.setContentsMargins(40, 48, 40, 48)

        self._card = self._build_card()
        center_layout.addWidget(self._card, 0, Qt.AlignCenter)

        scroll.setWidget(center_widget)
        root.addWidget(scroll, stretch=1)

        # Prepare fade-in: apply effect to the scroll area itself (a direct child
        # of the root layout) so QScrollArea viewport clipping doesn't interfere.
        self._opacity_effect = QGraphicsOpacityEffect(scroll)
        self._opacity_effect.setOpacity(1.0)   # always visible
        scroll.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(88)
        header.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLORS['bg_deep']}, stop:1 {COLORS['bg_surface']});"
            f"border-bottom: 1px solid {COLORS['border']};"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(44, 18, 44, 18)

        # Accent stripe — green for done
        stripe = QFrame()
        stripe.setFixedWidth(3)
        stripe.setFixedHeight(44)
        stripe.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {COLORS['success']}, stop:1 #86efac); border-radius: 2px;"
        )
        layout.addWidget(stripe)
        layout.addSpacing(14)

        title = QLabel("Run Complete")
        title.setObjectName("heading")
        layout.addWidget(title)
        layout.addStretch()

        badge = QLabel("Done  ✓")
        badge.setObjectName("success_pill")
        layout.addWidget(badge)
        return header

    def _build_card(self) -> QWidget:
        # Outer rounded frame (paints background + border)
        card = QFrame()
        card.setFixedWidth(560)
        card.setObjectName("done_card_outer")
        card.setStyleSheet(
            f"QFrame#done_card_outer {{"
            f"background: {COLORS['bg_card']}; "
            f"border-radius: 18px; "
            f"border: 1px solid {COLORS['border']};"
            f"}}"
        )

        outer_layout = QVBoxLayout(card)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Inner content widget (transparent, no border-radius so content isn't clipped)
        inner = QWidget()
        inner.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 56, 48, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)
        outer_layout.addWidget(inner)

        # ── Success icon ────────────────────────────────────
        check = QLabel("✓")
        check.setStyleSheet(
            f"font-size: 36px; font-weight: 900; color: {COLORS['success']};"
            f"background: transparent; border: none; padding-bottom: 4px;"
        )
        check.setFixedSize(100, 80)
        check.setAlignment(Qt.AlignCenter)
        layout.addWidget(check, 0, Qt.AlignCenter)
        layout.addSpacing(4)

        # ── Title ───────────────────────────────────────────────────
        title = QLabel("Pipeline Finished Successfully")
        title.setStyleSheet(
            f"font-size: 19px; font-weight: 700; color: {COLORS['text_primary']}; "
            f"background: transparent; letter-spacing: -0.3px; padding-top: 6px;"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setMinimumHeight(60)
        layout.addWidget(title, 0, Qt.AlignCenter)
        layout.addSpacing(10)

        # ── Subtitle ─────────────────────────────────────────────────
        subtitle = QLabel(
            "All records have been verified and saved to the output file."
        )
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; "
            f"background: transparent; line-height: 1.5;"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setMinimumWidth(400)
        subtitle.setMinimumHeight(30)
        layout.addWidget(subtitle, 0, Qt.AlignCenter)
        layout.addSpacing(26)

        # ── Output path + copy ───────────────────────────────────────
        path_label_title = QLabel("Output File")
        path_label_title.setObjectName("section_label")
        layout.addWidget(path_label_title)
        layout.addSpacing(6)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._output_path_label = QLabel("")
        self._output_path_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px; "
            f"font-family: 'Cascadia Code', 'Consolas', monospace; "
            f"background: {COLORS['bg_elevated']}; border-radius: 8px; "
            f"padding: 8px 14px; border: 1px solid {COLORS['border']};"
        )
        self._output_path_label.setWordWrap(True)
        self._output_path_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._output_path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._output_path_label.setMinimumWidth(380)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("ghost")
        copy_btn.setFixedWidth(60)
        copy_btn.setFixedHeight(36)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setToolTip("Copy path to clipboard")
        copy_btn.clicked.connect(self._copy_path)

        path_row.addWidget(self._output_path_label)
        path_row.addWidget(copy_btn)
        layout.addLayout(path_row)
        layout.addSpacing(26)

        # ── Divider ─────────────────────────────────────────────────
        div = QFrame()
        div.setObjectName("divider")
        layout.addWidget(div)
        layout.addSpacing(22)

        # ── Action buttons ───────────────────────────────────────────
        self._open_output_btn = QPushButton("📂  Open Output File")
        self._open_output_btn.setObjectName("success_btn")
        self._open_output_btn.setFixedHeight(42)
        self._open_output_btn.setCursor(Qt.PointingHandCursor)
        self._open_output_btn.setToolTip("Open the output Excel file")
        self._open_output_btn.clicked.connect(self._open_output)
        layout.addWidget(self._open_output_btn)
        layout.addSpacing(10)

        self._open_log_btn = QPushButton("📋  Open Latest Log File")
        self._open_log_btn.setFixedHeight(42)
        self._open_log_btn.setCursor(Qt.PointingHandCursor)
        self._open_log_btn.setToolTip("Open the most recent pipeline log file")
        self._open_log_btn.clicked.connect(self._open_log)
        layout.addWidget(self._open_log_btn)
        layout.addSpacing(16)

        # ── Secondary divider ────────────────────────────────────────
        div2 = QFrame()
        div2.setObjectName("divider")
        layout.addWidget(div2)
        layout.addSpacing(16)

        # ── Run again (same settings) ────────────────────────────────
        again_btn = QPushButton("↩  Run Again  (same settings)")
        again_btn.setObjectName("ghost")
        again_btn.setFixedHeight(38)
        again_btn.setCursor(Qt.PointingHandCursor)
        again_btn.setToolTip("Go back to the Run screen with the same settings")
        again_btn.clicked.connect(self.run_again)
        layout.addWidget(again_btn)
        layout.addSpacing(8)

        # ── Run on custom range ──────────────────────────────────────
        range_btn = QPushButton("⚙  Run on Custom Row Range…")
        range_btn.setObjectName("ghost")
        range_btn.setFixedHeight(38)
        range_btn.setCursor(Qt.PointingHandCursor)
        range_btn.setToolTip(
            "Go back to Settings to change the row range before running again"
        )
        range_btn.clicked.connect(self.run_custom_range)
        layout.addWidget(range_btn)

        return card

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Play fade-in entrance each time the screen is shown
        self._opacity_effect.setOpacity(0.0)
        self._fade_anim.stop()
        self._fade_anim.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure(self, settings: Settings) -> None:
        """Update the screen with the finished run's settings."""
        self._settings = settings
        self._output_path_label.setText(settings.output_file)
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

    def _copy_path(self) -> None:
        if self._settings:
            QApplication.clipboard().setText(self._settings.output_file)

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
