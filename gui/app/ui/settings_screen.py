"""
app/ui/settings_screen.py

Settings screen — collects all configuration needed to launch the pipeline.
Fields are pre-populated from the persisted Settings JSON on load and saved
back when the user clicks "Save & Continue".
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional

import openpyxl
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.settings import Settings
from app.ui.styles import COLORS


class SettingsScreen(QWidget):
    """
    Settings configuration screen.

    Emits `proceed` when the user clicks Save & Continue with valid settings.
    The main window connects this signal to navigate to the run screen.
    """

    proceed = Signal(Settings)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = Settings.load()
        self._setup_ui()
        self._populate_fields()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = self._build_header()
        root.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_widget.setStyleSheet(f"background: {COLORS['bg_base']};")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(40, 32, 40, 32)
        content_layout.setSpacing(20)

        # --- Groups ---
        content_layout.addWidget(self._build_pipeline_group())
        content_layout.addWidget(self._build_files_group())
        content_layout.addWidget(self._build_api_group())
        content_layout.addWidget(self._build_row_range_group())
        content_layout.addSpacerItem(
            QSpacerItem(0, 16, QSizePolicy.Minimum, QSizePolicy.Fixed)
        )

        # Save button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._save_btn = QPushButton("Save & Continue →")
        self._save_btn.setObjectName("primary")
        self._save_btn.setMinimumWidth(200)
        self._save_btn.setFixedHeight(44)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        content_layout.addLayout(btn_row)

        scroll.setWidget(content_widget)
        root.addWidget(scroll)

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

        title_col = QVBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("heading")
        sub = QLabel("Configure your pipeline before starting a run")
        sub.setObjectName("subheading")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        layout.addLayout(title_col)
        layout.addStretch()

        badge = QLabel("Step 1 of 2")
        badge.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px; "
            f"background: {COLORS['bg_elevated']}; border-radius: 12px; "
            f"padding: 4px 12px; border: 1px solid {COLORS['border']};"
        )
        layout.addWidget(badge)
        return header

    def _build_pipeline_group(self) -> QGroupBox:
        group = QGroupBox("Pipeline")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # Pipeline folder
        layout.addWidget(self._section_label("Pipeline Folder"))
        row1 = QHBoxLayout()
        self._pipeline_dir_edit = self._line_edit("Path to the folder containing verify_colleges.py")
        self._pipeline_dir_edit.setReadOnly(True)
        self._pipeline_dir_browse = self._browse_btn()
        self._pipeline_dir_browse.clicked.connect(self._browse_pipeline_dir)
        row1.addWidget(self._pipeline_dir_edit)
        row1.addWidget(self._pipeline_dir_browse)
        layout.addLayout(row1)

        # Python interpreter
        layout.addWidget(self._section_label("Python Interpreter"))
        row2 = QHBoxLayout()
        self._python_exe_edit = self._line_edit('e.g. "python" or full path to python.exe')
        self._python_browse = self._browse_btn()
        self._python_browse.clicked.connect(self._browse_python)
        self._python_test_btn = QPushButton("Test")
        self._python_test_btn.setObjectName("ghost")
        self._python_test_btn.setFixedWidth(70)
        self._python_test_btn.setCursor(Qt.PointingHandCursor)
        self._python_test_btn.clicked.connect(self._test_python)
        row2.addWidget(self._python_exe_edit)
        row2.addWidget(self._python_browse)
        row2.addWidget(self._python_test_btn)
        layout.addLayout(row2)

        self._python_version_label = QLabel("")
        self._python_version_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; padding-left: 4px;")
        layout.addWidget(self._python_version_label)

        return group

    def _build_files_group(self) -> QGroupBox:
        group = QGroupBox("Files")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # Input Excel
        layout.addWidget(self._section_label("Input Excel File"))
        row1 = QHBoxLayout()
        self._input_file_edit = self._line_edit("Select .xlsx input file")
        self._input_file_edit.setReadOnly(True)
        btn = self._browse_btn()
        btn.clicked.connect(self._browse_input_file)
        row1.addWidget(self._input_file_edit)
        row1.addWidget(btn)
        layout.addLayout(row1)

        # Sheet name (dropdown, populated when a file is chosen)
        layout.addWidget(self._section_label("Sheet Name"))
        self._sheet_combo = QComboBox()
        self._sheet_combo.setEditable(True)
        self._sheet_combo.setPlaceholderText("Select or type sheet name")
        self._sheet_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._sheet_combo)

        # Output Excel
        layout.addWidget(self._section_label("Output Excel File"))
        row2 = QHBoxLayout()
        self._output_file_edit = self._line_edit("Select or create output .xlsx file")
        self._output_file_edit.setReadOnly(True)
        btn2 = self._browse_btn("Save As...")
        btn2.clicked.connect(self._browse_output_file)
        row2.addWidget(self._output_file_edit)
        row2.addWidget(btn2)
        layout.addLayout(row2)

        return group

    def _build_api_group(self) -> QGroupBox:
        group = QGroupBox("API Credentials")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("Gemini API Key"))
        key_row = QHBoxLayout()
        self._gemini_key_edit = QLineEdit()
        self._gemini_key_edit.setEchoMode(QLineEdit.Password)
        self._gemini_key_edit.setPlaceholderText("Paste your Gemini API key here")
        self._gemini_key_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._gemini_show_btn = QPushButton("Show")
        self._gemini_show_btn.setObjectName("ghost")
        self._gemini_show_btn.setFixedWidth(60)
        self._gemini_show_btn.setCursor(Qt.PointingHandCursor)
        self._gemini_show_btn.setCheckable(True)
        self._gemini_show_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._gemini_key_edit)
        key_row.addWidget(self._gemini_show_btn)
        layout.addLayout(key_row)

        note = QLabel(
            "ⓘ  The key is stored in plaintext in your AppData folder. "
            "Contact your IT team if a more secure option is required."
        )
        note.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        return group

    def _build_row_range_group(self) -> QGroupBox:
        """Build the 'Row Range' settings group."""
        group = QGroupBox("Row Range")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # Radio buttons
        self._radio_all = QRadioButton("Process all rows")
        self._radio_all.setChecked(True)
        self._radio_range = QRadioButton("Process a specific range")
        layout.addWidget(self._radio_all)
        layout.addWidget(self._radio_range)

        # Spin boxes (shown beneath the range radio)
        spin_row = QFormLayout()
        spin_row.setContentsMargins(24, 4, 0, 0)
        spin_row.setSpacing(8)

        self._start_row_spin = QSpinBox()
        self._start_row_spin.setMinimum(2)       # row 1 is always the header
        self._start_row_spin.setMaximum(1_000_000)
        self._start_row_spin.setValue(2)
        self._start_row_spin.setFixedWidth(120)
        self._start_row_spin.setEnabled(False)

        self._end_row_spin = QSpinBox()
        self._end_row_spin.setMinimum(2)
        self._end_row_spin.setMaximum(1_000_000)
        self._end_row_spin.setValue(100)
        self._end_row_spin.setFixedWidth(120)
        self._end_row_spin.setEnabled(False)

        spin_row.addRow("Start row (1-indexed, excl. header):", self._start_row_spin)
        spin_row.addRow("End row (inclusive):", self._end_row_spin)
        layout.addLayout(spin_row)

        note = QLabel(
            "ⓘ  Row numbers are 1-indexed and include the header row "
            "(so row 2 is the first data row). Leave on 'all' to process the "
            "entire sheet."
        )
        note.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Wire radio buttons to enable/disable spinboxes
        self._radio_all.toggled.connect(self._on_mode_changed)
        self._radio_range.toggled.connect(self._on_mode_changed)

        return group

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_label")
        return lbl

    @staticmethod
    def _line_edit(placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return edit

    @staticmethod
    def _browse_btn(label: str = "Browse...") -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedWidth(100)
        btn.setCursor(Qt.PointingHandCursor)
        return btn

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse_pipeline_dir(self) -> None:
        current = self._pipeline_dir_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(
            self, "Select Pipeline Folder", current
        )
        if path:
            self._pipeline_dir_edit.setText(path)

    def _browse_python(self) -> None:
        current = self._python_exe_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Python Interpreter", current, "Executables (*.exe);;All Files (*)"
        )
        if path:
            self._python_exe_edit.setText(path)

    def _test_python(self) -> None:
        exe = self._python_exe_edit.text().strip() or "python"
        try:
            result = subprocess.run(
                [exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = (result.stdout.strip() or result.stderr.strip())
            self._python_version_label.setText(f"✓  {version}")
            self._python_version_label.setStyleSheet(
                f"color: {COLORS['success']}; font-size: 11px; padding-left: 4px;"
            )
        except FileNotFoundError:
            self._python_version_label.setText(f"✗  Interpreter not found: {exe}")
            self._python_version_label.setStyleSheet(
                f"color: {COLORS['error']}; font-size: 11px; padding-left: 4px;"
            )
        except subprocess.TimeoutExpired:
            self._python_version_label.setText("✗  Timed out")
            self._python_version_label.setStyleSheet(
                f"color: {COLORS['error']}; font-size: 11px; padding-left: 4px;"
            )

    def _browse_input_file(self) -> None:
        current = self._input_file_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Input Excel File", current, "Excel Files (*.xlsx *.xls)"
        )
        if path:
            self._input_file_edit.setText(path)
            self._load_sheet_names(path)

    def _load_sheet_names(self, path: str) -> None:
        """Read sheet names from the workbook and populate the combo box."""
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            sheets = wb.sheetnames
            wb.close()
            self._sheet_combo.clear()
            self._sheet_combo.addItems(sheets)
            if sheets:
                # Pre-select the sheet that was previously saved, if present.
                saved = self._settings.sheet_name
                if saved in sheets:
                    self._sheet_combo.setCurrentText(saved)
                else:
                    self._sheet_combo.setCurrentIndex(0)
        except Exception:
            self._sheet_combo.clear()

    def _browse_output_file(self) -> None:
        current = self._output_file_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Output Excel File", current, "Excel Files (*.xlsx)"
        )
        if path:
            if not path.endswith(".xlsx"):
                path += ".xlsx"
            self._output_file_edit.setText(path)

    def _toggle_key_visibility(self, checked: bool) -> None:
        if checked:
            self._gemini_key_edit.setEchoMode(QLineEdit.Normal)
            self._gemini_show_btn.setText("Hide")
        else:
            self._gemini_key_edit.setEchoMode(QLineEdit.Password)
            self._gemini_show_btn.setText("Show")

    def _on_mode_changed(self) -> None:
        """Enable/disable spinboxes depending on the selected radio button."""
        is_range = self._radio_range.isChecked()
        self._start_row_spin.setEnabled(is_range)
        self._end_row_spin.setEnabled(is_range)

    def _on_save(self) -> None:
        """Validate, persist, and emit proceed."""
        s = self._collect_settings()
        errors = self._validate(s)
        if errors:
            QMessageBox.warning(
                self,
                "Missing Required Fields",
                "Please fix the following before continuing:\n\n" + "\n".join(f"• {e}" for e in errors),
            )
            return
        s.save()
        self._settings = s
        self.proceed.emit(s)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _collect_settings(self) -> Settings:
        if self._radio_range.isChecked():
            mode = "range"
            start = str(self._start_row_spin.value())
            end = str(self._end_row_spin.value())
        else:
            mode = "all"
            start = ""
            end = ""
        return Settings(
            pipeline_dir=self._pipeline_dir_edit.text().strip(),
            python_exe=self._python_exe_edit.text().strip() or "python",
            input_file=self._input_file_edit.text().strip(),
            sheet_name=self._sheet_combo.currentText().strip(),
            output_file=self._output_file_edit.text().strip(),
            gemini_api_key=self._gemini_key_edit.text().strip(),
            process_mode=mode,
            start_row=start,
            end_row=end,
        )

    @staticmethod
    def _validate(s: Settings) -> list[str]:
        errors: list[str] = []
        if not s.pipeline_dir:
            errors.append("Pipeline folder is required.")
        elif not os.path.isfile(os.path.join(s.pipeline_dir, "verify_colleges.py")):
            errors.append("Pipeline folder must contain verify_colleges.py.")
        if not s.python_exe:
            errors.append("Python interpreter path is required.")
        if not s.input_file:
            errors.append("Input Excel file is required.")
        elif not os.path.isfile(s.input_file):
            errors.append("Input Excel file does not exist.")
        if not s.sheet_name:
            errors.append("Sheet name is required.")
        if not s.output_file:
            errors.append("Output Excel file path is required.")
        if not s.gemini_api_key:
            errors.append("Gemini API key is required.")
        if s.process_mode == "range":
            try:
                start = int(s.start_row)
                end = int(s.end_row)
                if start < 2:
                    errors.append("Start row must be ≥ 2 (row 1 is the header).")
                if end < start:
                    errors.append("End row must be ≥ start row.")
            except (ValueError, TypeError):
                errors.append("Start and end row must be valid integers.")
        return errors

    def _populate_fields(self) -> None:
        s = self._settings
        self._pipeline_dir_edit.setText(s.pipeline_dir)
        self._python_exe_edit.setText(s.python_exe)
        self._gemini_key_edit.setText(s.gemini_api_key)
        self._output_file_edit.setText(s.output_file)

        if s.input_file:
            self._input_file_edit.setText(s.input_file)
            if os.path.isfile(s.input_file):
                self._load_sheet_names(s.input_file)
        if s.sheet_name:
            self._sheet_combo.setCurrentText(s.sheet_name)

        # Restore row-range state
        if s.process_mode == "range":
            self._radio_range.setChecked(True)
            if s.start_row:
                try:
                    self._start_row_spin.setValue(int(s.start_row))
                except ValueError:
                    pass
            if s.end_row:
                try:
                    self._end_row_spin.setValue(int(s.end_row))
                except ValueError:
                    pass
        else:
            self._radio_all.setChecked(True)

    def refresh(self) -> None:
        """Reload from disk and repopulate — called when navigating back."""
        self._settings = Settings.load()
        self._populate_fields()
