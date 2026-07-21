"""
app/ui/run_screen.py

Run screen — the live dashboard shown during a pipeline execution.

Layout:
  ┌─ Top accent bar (3 px gradient) ───────────────────────────────────┐
  ├─ Header bar ────────────────────────────────────────────────────────┤
  │  Title / file summary                     [elapsed]  [Settings] btn │
  ├─ Error banner (hidden unless finished_error) ───────────────────────┤
  │  🔴  Error message …                                                │
  ├─ Login banner (hidden until awaiting_login) ────────────────────────┤
  │  🔑  Browser is open — log in, then click Continue                  │
  ├─ Log pane (QPlainTextEdit, read-only, monospace) ───────────────────┤
  │  … live pipeline stdout …                                           │
  ├─ Progress bar + stat counter ───────────────────────────────────────┤
  │  ━━━━━━━━━━━━━━━━━━  12 / 345  claims processed                     │
  └─ Button bar ────────────────────────────────────────────────────────┘
       [▶ Start]   [⏸ Pause]   [■ Cancel]
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from app.runner import PipelineRunner
from app.settings import Settings
from app.ui.styles import COLORS


class RunScreen(QWidget):
    """
    Live pipeline execution dashboard.

    Signals
    -------
    request_settings()
        User clicked the Settings shortcut — navigate back to Settings.
    finished()
        Emitted on successful completion so the main window can go to Done.
    """

    request_settings = Signal()
    finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings: Optional[Settings] = None
        self._runner: Optional[PipelineRunner] = None
        self._paused: bool = False
        self._total_rows: Optional[int] = None

        # Elapsed-time tracking
        self._elapsed_seconds: int = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        # Indeterminate shuttle animation
        self._shuttle_value: int = 0
        self._shuttle_dir: int = 1
        self._shuttle_timer = QTimer(self)
        self._shuttle_timer.setInterval(30)
        self._shuttle_timer.timeout.connect(self._shuttle_step)

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Accent top bar
        top_bar = QFrame()
        top_bar.setFixedHeight(3)
        top_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLORS['accent']}, stop:0.5 {COLORS['accent_hover']}, stop:1 #c7d2fe);"
        )
        root.addWidget(top_bar)

        root.addWidget(self._build_header())
        root.addWidget(self._build_error_banner())
        root.addWidget(self._build_login_banner())

        # Log pane wrapper
        log_wrapper = QWidget()
        log_wrapper.setStyleSheet(f"background: {COLORS['bg_base']};")
        lw_layout = QVBoxLayout(log_wrapper)
        lw_layout.setContentsMargins(24, 14, 24, 6)
        lw_layout.setSpacing(6)

        log_label = QLabel("Live Output")
        log_label.setObjectName("section_label")
        lw_layout.addWidget(log_label)

        self._log_pane = QPlainTextEdit()
        self._log_pane.setReadOnly(True)
        self._log_pane.setMaximumBlockCount(10_000)
        self._log_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lw_layout.addWidget(self._log_pane)

        root.addWidget(log_wrapper, stretch=1)

        root.addWidget(self._build_progress_bar_row())
        root.addWidget(self._build_button_bar())

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

        # Accent stripe
        stripe = QFrame()
        stripe.setObjectName("accent_stripe")
        stripe.setFixedWidth(3)
        stripe.setFixedHeight(44)
        layout.addWidget(stripe)
        layout.addSpacing(14)

        col = QVBoxLayout()
        col.setSpacing(3)
        self._header_title = QLabel("Run")
        self._header_title.setObjectName("heading")
        self._header_sub = QLabel("Ready — click Start to begin processing")
        self._header_sub.setObjectName("subheading")
        col.addWidget(self._header_title)
        col.addWidget(self._header_sub)
        layout.addLayout(col)
        layout.addStretch()

        # Elapsed time
        self._elapsed_label = QLabel("00:00:00")
        self._elapsed_label.setObjectName("elapsed_label")
        self._elapsed_label.setToolTip("Elapsed run time")
        layout.addWidget(self._elapsed_label)
        layout.addSpacing(16)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setObjectName("ghost")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setToolTip("Return to configuration (only when no run is active)")
        settings_btn.clicked.connect(self.request_settings)
        layout.addWidget(settings_btn)
        return header

    def _build_error_banner(self) -> QWidget:
        self._error_banner = QWidget()
        self._error_banner.setStyleSheet(
            f"background: {COLORS['error_subtle']};"
            f"border-bottom: 1px solid {COLORS['error_border']};"
        )
        self._error_banner.hide()
        layout = QHBoxLayout(self._error_banner)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(12)

        icon = QLabel("❌")
        icon.setStyleSheet("font-size: 16px; background: transparent;")
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(
            f"color: {COLORS['error']}; font-weight: 500; background: transparent;"
        )
        self._error_label.setWordWrap(True)
        layout.addWidget(icon, 0)
        layout.addWidget(self._error_label, 1)
        return self._error_banner

    def _build_login_banner(self) -> QWidget:
        self._login_banner = QWidget()
        self._login_banner.setStyleSheet(
            f"background: {COLORS['accent_subtle']};"
            f"border-bottom: 1px solid {COLORS['border_accent']};"
        )
        self._login_banner.hide()
        layout = QHBoxLayout(self._login_banner)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(14)

        icon = QLabel("🔑")
        icon.setStyleSheet("font-size: 20px; background: transparent;")
        msg = QLabel(
            "<b>Action required:</b> A browser window has opened. "
            "Log into the portal, navigate to Claims, set up the filter — "
            "then click <b>Continue</b> below."
        )
        msg.setStyleSheet(f"color: {COLORS['text_primary']}; background: transparent;")
        msg.setWordWrap(True)

        self._login_confirm_btn = QPushButton("✓  I've logged in — Continue")
        self._login_confirm_btn.setObjectName("primary")
        self._login_confirm_btn.setFixedWidth(250)
        self._login_confirm_btn.setFixedHeight(40)
        self._login_confirm_btn.setCursor(Qt.PointingHandCursor)
        self._login_confirm_btn.clicked.connect(self._on_confirm_login)

        layout.addWidget(icon, 0)
        layout.addWidget(msg, 1)
        layout.addWidget(self._login_confirm_btn, 0)
        return self._login_banner

    def _build_progress_bar_row(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            f"background: {COLORS['bg_surface']};"
            f"border-top: 1px solid {COLORS['border']};"
        )
        outer = QHBoxLayout(w)
        outer.setContentsMargins(24, 14, 24, 14)
        outer.setSpacing(24)

        # Left: large counter
        left = QVBoxLayout()
        left.setSpacing(0)
        self._stat_count_label = QLabel("—")
        self._stat_count_label.setObjectName("stat_number")
        self._stat_sub_label = QLabel("No run in progress")
        self._stat_sub_label.setObjectName("stat_sub")
        left.addWidget(self._stat_count_label)
        left.addWidget(self._stat_sub_label)
        outer.addLayout(left)

        # Right: progress bar (expands)
        right = QVBoxLayout()
        right.setSpacing(4)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("")
        self._progress_bar.setFixedHeight(12)
        self._progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right.addWidget(self._progress_bar)
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet(
            f"color: {COLORS['text_muted']}; font-size: 11px;"
        )
        right.addWidget(self._progress_label)
        outer.addLayout(right, stretch=1)

        return w

    def _build_button_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        bar.setStyleSheet(
            f"background: {COLORS['bg_deep']}; border-top: 1px solid {COLORS['border']};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.setObjectName("primary")
        self._start_btn.setFixedHeight(40)
        self._start_btn.setMinimumWidth(130)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setToolTip("Start the pipeline run")
        self._start_btn.clicked.connect(self._on_start)

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setFixedHeight(36)
        self._pause_btn.setMinimumWidth(110)
        self._pause_btn.setCursor(Qt.PointingHandCursor)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setToolTip("Pause the current run (can be resumed)")
        self._pause_btn.clicked.connect(self._on_pause_resume)

        self._cancel_btn = QPushButton("■  Cancel")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.setFixedHeight(36)
        self._cancel_btn.setMinimumWidth(110)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setToolTip("Cancel the run (progress already saved is kept)")
        self._cancel_btn.clicked.connect(self._on_cancel)

        layout.addWidget(self._start_btn)
        layout.addWidget(self._pause_btn)
        layout.addWidget(self._cancel_btn)
        layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Public API called by MainWindow
    # ------------------------------------------------------------------

    def configure(self, settings: Settings, total_rows: Optional[int] = None) -> None:
        """Set the settings to use for the next run."""
        self._settings = settings
        self._total_rows = total_rows

        if total_rows:
            self._progress_bar.setMaximum(total_rows)
        else:
            self._progress_bar.setMaximum(100)  # shuttle uses 0-100

        self._reset_ui()
        self._header_sub.setText(
            f"Input: {os.path.basename(settings.input_file)}  →  "
            f"Output: {os.path.basename(settings.output_file)}"
        )

    def has_active_runner(self) -> bool:
        return self._runner is not None and self._runner.is_running_proc

    def cancel_runner(self) -> None:
        if self._runner:
            self._runner.cancel()

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------

    def _reset_ui(self) -> None:
        self._error_banner.hide()
        self._login_banner.hide()
        self._log_pane.clear()
        self._progress_bar.setValue(0)
        self._stat_count_label.setText("—")
        self._stat_sub_label.setText("Ready")
        self._progress_label.setText("")
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")
        self._cancel_btn.setEnabled(False)
        self._paused = False
        self._runner = None
        self._stop_elapsed()
        self._elapsed_seconds = 0
        self._elapsed_label.setText("00:00:00")
        self._shuttle_timer.stop()

    def _set_running(self) -> None:
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._header_sub.setText("Running…")
        self._start_elapsed()
        # Start shuttle animation if we don't know the total rows yet
        if not self._total_rows:
            self._shuttle_value = 0
            self._shuttle_dir = 1
            self._shuttle_timer.start()

    def _set_done(self) -> None:
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._login_banner.hide()
        self._stop_elapsed()
        self._shuttle_timer.stop()

    # ------------------------------------------------------------------
    # Elapsed timer
    # ------------------------------------------------------------------

    def _start_elapsed(self) -> None:
        self._elapsed_seconds = 0
        self._elapsed_timer.start()

    def _stop_elapsed(self) -> None:
        self._elapsed_timer.stop()

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        h = self._elapsed_seconds // 3600
        m = (self._elapsed_seconds % 3600) // 60
        s = self._elapsed_seconds % 60
        self._elapsed_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    # ------------------------------------------------------------------
    # Indeterminate shuttle animation
    # ------------------------------------------------------------------

    def _shuttle_step(self) -> None:
        self._shuttle_value += self._shuttle_dir * 2
        if self._shuttle_value >= 100:
            self._shuttle_value = 100
            self._shuttle_dir = -1
        elif self._shuttle_value <= 0:
            self._shuttle_value = 0
            self._shuttle_dir = 1
        self._progress_bar.setValue(self._shuttle_value)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        if not self._settings or not self._settings.is_runnable():
            QMessageBox.warning(self, "Not Configured", "Please save valid Settings first.")
            self.request_settings.emit()
            return

        self._reset_ui()
        self._set_running()

        env_overrides = self._settings.build_env_overrides()
        self._runner = PipelineRunner(
            python_exe=self._settings.python_exe,
            pipeline_dir=self._settings.pipeline_dir,
            env_overrides=env_overrides,
            total_rows_hint=self._total_rows,
        )

        self._runner.log_line.connect(self._on_log_line)
        self._runner.awaiting_login.connect(self._on_awaiting_login)
        self._runner.progress.connect(self._on_progress)
        self._runner.finished_ok.connect(self._on_finished_ok)
        self._runner.finished_error.connect(self._on_finished_error)

        self._runner.start()

    def _on_pause_resume(self) -> None:
        if not self._runner:
            return
        if self._paused:
            self._runner.resume()
            self._paused = False
            self._pause_btn.setText("⏸  Pause")
            self._header_sub.setText("Running…")
            self._elapsed_timer.start()
            if not self._total_rows:
                self._shuttle_timer.start()
        else:
            self._runner.pause()
            self._paused = True
            self._pause_btn.setText("▶  Resume")
            self._header_sub.setText("Paused")
            self._elapsed_timer.stop()
            self._shuttle_timer.stop()

    def _on_cancel(self) -> None:
        reply = QMessageBox.question(
            self,
            "Cancel Run?",
            "This will stop the pipeline.\n\nProgress already saved will not be lost — "
            "the next run will resume from where this one stopped.\n\nCancel the run?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes and self._runner:
            self._runner.cancel()

    def _on_confirm_login(self) -> None:
        if self._runner:
            self._runner.confirm_login()
            self._login_banner.hide()
            self._log_pane.appendPlainText("[GUI] Login confirmed — continuing…")

    # ------------------------------------------------------------------
    # Runner signal handlers
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_log_line(self, line: str) -> None:
        """Append a log line, auto-scrolling only if the user hasn't scrolled up."""
        sb = self._log_pane.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self._log_pane.appendPlainText(line)
        if at_bottom:
            self._log_pane.moveCursor(QTextCursor.End)

    @Slot()
    def _on_awaiting_login(self) -> None:
        self._login_banner.show()
        self._login_confirm_btn.setEnabled(True)

    @Slot(int)
    def _on_progress(self, count: int) -> None:
        self._shuttle_timer.stop()   # stop shuttle once we have real progress
        if self._total_rows:
            self._progress_bar.setMaximum(self._total_rows)
            self._progress_bar.setValue(count)
            pct = int(count / self._total_rows * 100)
            self._stat_count_label.setText(f"{count:,}")
            self._stat_sub_label.setText(f"of {self._total_rows:,} claims processed")
            self._progress_label.setText(f"{pct}% complete")
        else:
            self._progress_bar.setMaximum(0)
            self._stat_count_label.setText(f"{count:,}")
            self._stat_sub_label.setText("claims processed")
            self._progress_label.setText("")

    @Slot()
    def _on_finished_ok(self) -> None:
        self._set_done()
        self._stat_sub_label.setText("claims processed  ✓")
        if self._total_rows:
            self._progress_bar.setMaximum(self._total_rows)
            self._progress_bar.setValue(self._total_rows)
        self._progress_label.setText("Completed successfully")
        self.finished.emit()

    @Slot(str)
    def _on_finished_error(self, message: str) -> None:
        self._set_done()
        self._error_label.setText(message)
        self._error_banner.show()
        self._header_sub.setText("Run ended with an error — see above")
