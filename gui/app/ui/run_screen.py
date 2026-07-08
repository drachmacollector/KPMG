"""
app/ui/run_screen.py

Run screen — the live dashboard shown during a pipeline execution.

Layout:
  ┌─ Header bar ────────────────────────────────────────────────────────┐
  │  Title / Settings summary                         [Settings] button │
  ├─ Error banner (hidden unless finished_error) ───────────────────────┤
  │  🔴  Error message …                                                │
  ├─ Login banner (hidden until awaiting_login) ────────────────────────┤
  │  🔑  Browser is open — log in, then click Continue                  │
  ├─ Log pane (QPlainTextEdit, read-only, monospace) ───────────────────┤
  │  … live pipeline stdout …                                           │
  ├─ Progress bar + counter ────────────────────────────────────────────┤
  │  ━━━━━━━━━━━━━━━━━━  12 / 345 claims processed                      │
  └─ Button bar ────────────────────────────────────────────────────────┘
       [Start]   [Pause / Resume]   [Cancel]
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
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
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_error_banner())
        root.addWidget(self._build_login_banner())

        # Log pane
        self._log_pane = QPlainTextEdit()
        self._log_pane.setReadOnly(True)
        self._log_pane.setMaximumBlockCount(10_000)  # keep memory bounded
        self._log_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        log_wrapper = QWidget()
        log_wrapper.setStyleSheet(f"background: {COLORS['bg_base']};")
        lw_layout = QVBoxLayout(log_wrapper)
        lw_layout.setContentsMargins(24, 16, 24, 8)
        lw_layout.addWidget(self._log_pane)
        root.addWidget(log_wrapper, stretch=1)

        root.addWidget(self._build_progress_bar_row())
        root.addWidget(self._build_button_bar())

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

        col = QVBoxLayout()
        self._header_title = QLabel("Run")
        self._header_title.setObjectName("heading")
        self._header_sub = QLabel("Ready — click Start to begin processing")
        self._header_sub.setObjectName("subheading")
        col.addWidget(self._header_title)
        col.addWidget(self._header_sub)
        layout.addLayout(col)
        layout.addStretch()

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setObjectName("ghost")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self.request_settings)
        layout.addWidget(settings_btn)
        return header

    def _build_error_banner(self) -> QWidget:
        self._error_banner = QWidget()
        self._error_banner.setStyleSheet(
            f"background: rgba(239,68,68,0.12); border-bottom: 1px solid rgba(239,68,68,0.4);"
        )
        self._error_banner.hide()
        layout = QHBoxLayout(self._error_banner)
        layout.setContentsMargins(24, 10, 24, 10)
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"color: {COLORS['error']}; font-weight: 500;")
        self._error_label.setWordWrap(True)
        layout.addWidget(QLabel("❌"), 0)
        layout.addWidget(self._error_label, 1)
        return self._error_banner

    def _build_login_banner(self) -> QWidget:
        self._login_banner = QWidget()
        self._login_banner.setStyleSheet(
            f"background: rgba(99,102,241,0.12); border-bottom: 1px solid rgba(99,102,241,0.4);"
        )
        self._login_banner.hide()
        layout = QHBoxLayout(self._login_banner)
        layout.setContentsMargins(24, 12, 24, 12)

        icon = QLabel("🔑")
        icon.setStyleSheet("font-size: 18px;")
        msg = QLabel(
            "<b>Action required:</b> A browser window has opened. "
            "Log into the portal, navigate to Claims, set up the filter — "
            "then click <b>Continue</b> below."
        )
        msg.setStyleSheet(f"color: {COLORS['text_primary']};")
        msg.setWordWrap(True)

        self._login_confirm_btn = QPushButton("✓  I've logged in — Continue")
        self._login_confirm_btn.setObjectName("primary")
        self._login_confirm_btn.setFixedWidth(240)
        self._login_confirm_btn.setFixedHeight(40)
        self._login_confirm_btn.setCursor(Qt.PointingHandCursor)
        self._login_confirm_btn.clicked.connect(self._on_confirm_login)

        layout.addWidget(icon, 0)
        layout.addWidget(msg, 1)
        layout.addWidget(self._login_confirm_btn, 0)
        return self._login_banner

    def _build_progress_bar_row(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {COLORS['bg_base']};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 8, 24, 8)
        layout.setSpacing(6)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("")  # we'll use a label instead
        self._progress_bar.setFixedHeight(12)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("No run in progress")
        self._progress_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px;"
        )
        layout.addWidget(self._progress_label)
        return w

    def _build_button_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        bar.setStyleSheet(
            f"background: {COLORS['bg_surface']}; border-top: 1px solid {COLORS['border']};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        self._start_btn = QPushButton("▶  Start")
        self._start_btn.setObjectName("primary")
        self._start_btn.setFixedHeight(40)
        self._start_btn.setMinimumWidth(120)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start)

        self._pause_btn = QPushButton("⏸  Pause")
        self._pause_btn.setFixedHeight(40)
        self._pause_btn.setMinimumWidth(120)
        self._pause_btn.setCursor(Qt.PointingHandCursor)
        self._pause_btn.setEnabled(False)
        self._pause_btn.clicked.connect(self._on_pause_resume)

        self._cancel_btn = QPushButton("■  Cancel")
        self._cancel_btn.setObjectName("danger")
        self._cancel_btn.setFixedHeight(40)
        self._cancel_btn.setMinimumWidth(120)
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setEnabled(False)
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
            self._progress_bar.setMaximum(0)  # indeterminate until we know

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
        self._progress_label.setText("Ready")
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("⏸  Pause")
        self._cancel_btn.setEnabled(False)
        self._paused = False
        self._runner = None

    def _set_running(self) -> None:
        self._start_btn.setEnabled(False)
        self._pause_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._header_sub.setText("Running…")

    def _set_done(self) -> None:
        self._start_btn.setEnabled(True)
        self._pause_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._login_banner.hide()

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

        # Wire signals (Qt queued connections — safe across threads).
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
        else:
            self._runner.pause()
            self._paused = True
            self._pause_btn.setText("▶  Resume")
            self._header_sub.setText("Paused")

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
    # Runner signal handlers (run on GUI thread via queued connection)
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_log_line(self, line: str) -> None:
        """Append a log line, auto-scrolling only if the user hasn't scrolled up."""
        sb = self._log_pane.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # small tolerance
        self._log_pane.appendPlainText(line)
        if at_bottom:
            self._log_pane.moveCursor(QTextCursor.End)

    @Slot()
    def _on_awaiting_login(self) -> None:
        self._login_banner.show()
        self._login_confirm_btn.setEnabled(True)

    @Slot(int)
    def _on_progress(self, count: int) -> None:
        if self._total_rows:
            self._progress_bar.setMaximum(self._total_rows)
            self._progress_bar.setValue(count)
            self._progress_label.setText(
                f"{count} / {self._total_rows} claims processed"
            )
        else:
            # Indeterminate — just show a rising counter.
            self._progress_bar.setMaximum(0)
            self._progress_label.setText(f"{count} claims processed")

    @Slot()
    def _on_finished_ok(self) -> None:
        self._set_done()
        self._progress_label.setText("✓  All claims processed successfully")
        self._progress_bar.setValue(self._progress_bar.maximum())
        self.finished.emit()

    @Slot(str)
    def _on_finished_error(self, message: str) -> None:
        self._set_done()
        self._error_label.setText(message)
        self._error_banner.show()
        self._header_sub.setText("Run ended with an error — see above")
