"""
app/ui/splash_screen.py

Welcome / launch screen — the first thing shown when the app opens.

Layout (centred card on a dark gradient background):
  ┌──────────────────────────────────────┐
  │  [icon.ico  80 × 80]                 │
  │  MahaBOCW Verification Tool          │
  │  (tagline description, 2 lines)      │
  │  [v1.0.0 pill]                       │
  │  ─────────────────────────────       │
  │  [ Launch Application → ]            │
  └──────────────────────────────────────┘

Animations:
  • Card fades in from opacity 0 → 1 over 700 ms (QPropertyAnimation).
  • Launch button pulses via a QTimer that alternates between two object-name
    values ('primary_glow' / 'primary_glow_dim') every 900 ms — the global
    stylesheet maps each to a slightly different border colour, creating a
    breathing-glow effect without needing CSS transitions.
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    Signal,
)
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles import COLORS, SPLASH_CARD_STYLE


class SplashScreen(QWidget):
    """
    Welcome screen shown on first launch.

    Signals
    -------
    launch()
        Emitted when the user clicks "Launch Application →".
    """

    launch = Signal()

    def __init__(
        self,
        icon_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._icon_path = icon_path
        self._glow_state = True
        self._setup_ui()
        self._start_pulse()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        # Full-screen gradient background
        self.setObjectName("splash_root")
        self.setStyleSheet(
            f"QWidget#splash_root {{"
            f"background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:1,"
            f"stop:0 {COLORS['bg_deep']}, stop:0.6 {COLORS['bg_base']}, "
            f"stop:1 #0a1225);"
            f"}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.setAlignment(Qt.AlignCenter)

        # ── Card ──────────────────────────────────────────────────────
        self._card = QWidget()
        self._card.setObjectName("splash_card")
        self._card.setFixedWidth(500)
        self._card.setStyleSheet(SPLASH_CARD_STYLE)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(52, 52, 52, 48)
        card_layout.setSpacing(0)
        card_layout.setAlignment(Qt.AlignCenter)

        # App icon
        icon_lbl = self._build_icon_label()
        card_layout.addWidget(icon_lbl, 0, Qt.AlignCenter)
        card_layout.addSpacing(22)

        # Title
        title = QLabel("MahaBOCW Verification Tool")
        title.setObjectName("splash_title")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        card_layout.addWidget(title, 0, Qt.AlignCenter)
        card_layout.addSpacing(14)

        # Description
        desc = QLabel(
            "Automated OCR & web-based college verification pipeline.\n"
            "Processes beneficiary records against the MahaDBT portal in bulk."
        )
        desc.setObjectName("splash_sub")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        card_layout.addWidget(desc, 0, Qt.AlignCenter)
        card_layout.addSpacing(18)

        # Version pill
        version = QLabel("v 1.0.0")
        version.setObjectName("splash_version")
        version.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(version, 0, Qt.AlignCenter)
        card_layout.addSpacing(36)

        # Divider
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {COLORS['border']}; border-radius: 1px;")
        card_layout.addWidget(divider)
        card_layout.addSpacing(32)

        # Launch button
        self._launch_btn = QPushButton("Launch Application  →")
        self._launch_btn.setObjectName("primary_glow")
        self._launch_btn.setMinimumWidth(340)
        self._launch_btn.setCursor(Qt.PointingHandCursor)
        self._launch_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._launch_btn.clicked.connect(self.launch.emit)
        card_layout.addWidget(self._launch_btn, 0, Qt.AlignCenter)
        card_layout.addSpacing(8)

        # Subtle helper note
        note = QLabel("Maharashtra BOCW  ·  Beneficiary Verification")
        note.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px; background: transparent;"
        )
        note.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(note, 0, Qt.AlignCenter)

        outer.addWidget(self._card, 0, Qt.AlignCenter)

        # ── Opacity fade-in ───────────────────────────────────────────
        # NOTE: start at full opacity so the card is always rendered; the
        # animation resets to 0 and plays on showEvent for the entrance.
        self._opacity_effect = QGraphicsOpacityEffect(self._card)
        self._opacity_effect.setOpacity(1.0)   # fully visible by default
        self._card.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(700)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._first_show = True

    def _build_icon_label(self) -> QLabel:
        lbl = QLabel()
        lbl.setStyleSheet("background: transparent;")
        if self._icon_path and os.path.isfile(self._icon_path):
            from PySide6.QtGui import QIcon
            icon = QIcon(self._icon_path)
            pix = icon.pixmap(120, 120)
            if not pix.isNull():
                lbl.setPixmap(pix)
                lbl.setAlignment(Qt.AlignCenter)
                return lbl
        # Fallback — text monogram
        lbl.setText("◈")
        lbl.setStyleSheet(
            f"font-size: 72px; color: {COLORS['accent']}; background: transparent;"
        )
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    # ------------------------------------------------------------------
    # Animations
    # ------------------------------------------------------------------

    def _start_pulse(self) -> None:
        """Start the launch-button border-glow pulse."""
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(900)
        self._pulse_timer.timeout.connect(self._toggle_glow)
        self._pulse_timer.start()

    def _toggle_glow(self) -> None:
        self._glow_state = not self._glow_state
        name = "primary_glow" if self._glow_state else "primary_glow_dim"
        self._launch_btn.setObjectName(name)
        # Force stylesheet re-evaluation
        self._launch_btn.style().unpolish(self._launch_btn)
        self._launch_btn.style().polish(self._launch_btn)

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
        # Reset to transparent and play the fade-in entrance
        self._opacity_effect.setOpacity(0.0)
        self._fade_anim.stop()
        self._fade_anim.start()
