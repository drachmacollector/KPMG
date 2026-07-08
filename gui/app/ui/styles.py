"""
app/ui/styles.py

Centralised Qt stylesheet and palette constants for the MAHABOCW GUI.

Design: dark glassmorphism with indigo accent, subtle gradients, and smooth
hover/active transitions.  Every widget class references these constants so
colour changes only need to happen in one place.
"""

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
COLORS = {
    # Backgrounds
    "bg_deep":     "#0b0f1a",
    "bg_base":     "#111827",
    "bg_surface":  "#1a2236",
    "bg_elevated": "#1f2d45",
    "bg_card":     "#16213a",

    # Accent (indigo / blue-violet)
    "accent":        "#6366f1",
    "accent_hover":  "#818cf8",
    "accent_press":  "#4f46e5",
    "accent_muted":  "#3730a3",

    # Success / warning / error
    "success":  "#22c55e",
    "warning":  "#f59e0b",
    "error":    "#ef4444",
    "info":     "#38bdf8",

    # Text  — kept bright & readable
    "text_primary":   "#f8fafc",   # near-white, very readable
    "text_secondary": "#cbd5e1",   # light slate — clearly visible
    "text_muted":     "#64748b",   # only for truly unimportant hints
    "text_disabled":  "#94a3b8",   # disabled — still legible
    "text_accent":    "#a5b4fc",

    # Borders
    "border":        "#2d3f5a",
    "border_focus":  "#6366f1",
    "border_subtle": "#1e2a3a",
}

# ---------------------------------------------------------------------------
# Full application stylesheet
# ---------------------------------------------------------------------------
APP_STYLESHEET = f"""
/* ===== Global ===== */
QWidget {{
    background-color: {COLORS["bg_base"]};
    color: {COLORS["text_primary"]};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}}

QMainWindow, QDialog {{
    background-color: {COLORS["bg_deep"]};
}}

/* ===== Labels ===== */
QLabel {{
    color: {COLORS["text_primary"]};
    background: transparent;
}}

QLabel#heading {{
    font-size: 22px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.3px;
}}

QLabel#subheading {{
    font-size: 13px;
    color: {COLORS["text_secondary"]};
}}

QLabel#section_label {{
    font-size: 11px;
    font-weight: 700;
    color: {COLORS["text_secondary"]};
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

QLabel#accent_label {{
    color: {COLORS["text_accent"]};
    font-weight: 600;
}}

QLabel#error_label {{
    color: {COLORS["error"]};
}}

/* ===== QPushButton — base ===== */
QPushButton {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    padding: 0px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 34px;
    max-height: 34px;
}}

QPushButton:hover {{
    background-color: {COLORS["bg_surface"]};
    border-color: {COLORS["accent"]};
    color: #ffffff;
}}

QPushButton:pressed {{
    background-color: {COLORS["accent_muted"]};
    border-color: {COLORS["accent_press"]};
}}

QPushButton:disabled {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_subtle"]};
}}

/* ===== Primary button ===== */
QPushButton#primary {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    color: #ffffff;
    border: none;
    font-weight: 600;
    font-size: 13px;
    letter-spacing: 0.2px;
    min-height: 38px;
    max-height: 38px;
    border-radius: 8px;
    padding: 0px 20px;
}}

QPushButton#primary:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent_hover"]}, stop:1 #a5b4fc
    );
    border: none;
}}

QPushButton#primary:pressed {{
    background: {COLORS["accent_press"]};
}}

QPushButton#primary:disabled {{
    background: {COLORS["accent_muted"]};
    color: #6b7280;
}}

/* ===== Danger button ===== */
QPushButton#danger {{
    background-color: transparent;
    color: {COLORS["error"]};
    border: 1px solid {COLORS["error"]};
    font-weight: 500;
}}

QPushButton#danger:hover {{
    background-color: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    border-color: #fca5a5;
}}

QPushButton#danger:disabled {{
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_subtle"]};
    background: transparent;
}}

/* ===== Success button ===== */
QPushButton#success_btn {{
    background-color: transparent;
    color: {COLORS["success"]};
    border: 1px solid {COLORS["success"]};
    font-weight: 500;
}}

QPushButton#success_btn:hover {{
    background-color: rgba(34, 197, 94, 0.15);
    color: #86efac;
    border-color: #86efac;
}}

/* ===== Ghost button ===== */
QPushButton#ghost {{
    background: transparent;
    border: none;
    color: {COLORS["text_secondary"]};
    padding: 0px 10px;
    min-height: 30px;
    max-height: 30px;
    font-weight: 400;
}}

QPushButton#ghost:hover {{
    color: {COLORS["text_primary"]};
    background: rgba(255,255,255,0.07);
    border-radius: 6px;
}}

/* ===== QLineEdit ===== */
QLineEdit {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    padding: 0px 12px;
    min-height: 34px;
    max-height: 34px;
    selection-background-color: {COLORS["accent_muted"]};
    font-size: 13px;
}}

QLineEdit:focus {{
    border-color: {COLORS["border_focus"]};
    background-color: {COLORS["bg_base"]};
    color: #ffffff;
}}

QLineEdit:disabled {{
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_subtle"]};
    background-color: {COLORS["bg_deep"]};
}}

QLineEdit[echoMode="2"] {{
    lineedit-password-character: 9679;
}}

/* ===== QComboBox ===== */
QComboBox {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    padding: 0px 12px;
    min-height: 34px;
    max-height: 34px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {COLORS["border_focus"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLORS["text_secondary"]};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    color: {COLORS["text_primary"]};
    selection-background-color: {COLORS["accent_muted"]};
    outline: none;
    padding: 4px;
}}

/* ===== QSpinBox ===== */
QSpinBox {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    padding: 0px 8px;
    min-height: 34px;
    max-height: 34px;
    font-size: 13px;
}}

QSpinBox:focus {{
    border-color: {COLORS["border_focus"]};
}}

QSpinBox:disabled {{
    color: {COLORS["text_muted"]};
    border-color: {COLORS["border_subtle"]};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {COLORS["bg_elevated"]};
    border: none;
    width: 20px;
    border-radius: 3px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {COLORS["accent_muted"]};
}}

/* ===== QProgressBar ===== */
QProgressBar {{
    background-color: {COLORS["bg_deep"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
    font-size: 11px;
}}

QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    border-radius: 6px;
}}

/* ===== QPlainTextEdit (log pane) ===== */
QPlainTextEdit {{
    background-color: {COLORS["bg_deep"]};
    color: #d1dce8;
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: {COLORS["accent_muted"]};
    line-height: 1.5;
}}

/* ===== QScrollBar ===== */
QScrollBar:vertical {{
    background: {COLORS["bg_deep"]};
    width: 7px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["accent_muted"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
    background: none;
}}

QScrollBar:horizontal {{
    background: {COLORS["bg_deep"]};
    height: 7px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS["accent_muted"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
    background: none;
}}

/* ===== QGroupBox ===== */
QGroupBox {{
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 16px 14px 16px;
    font-weight: 700;
    font-size: 11px;
    color: {COLORS["text_secondary"]};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {COLORS["text_secondary"]};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}

/* ===== QRadioButton / QCheckBox ===== */
QRadioButton, QCheckBox {{
    color: {COLORS["text_primary"]};
    spacing: 8px;
    font-size: 13px;
}}

QRadioButton::indicator, QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {COLORS["border"]};
    border-radius: 8px;
    background: {COLORS["bg_deep"]};
}}

QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}

/* ===== QSplitter ===== */
QSplitter::handle {{
    background-color: {COLORS["border"]};
}}

/* ===== QToolTip ===== */
QToolTip {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ===== QMessageBox ===== */
QMessageBox {{
    background-color: {COLORS["bg_surface"]};
    color: {COLORS["text_primary"]};
}}

QMessageBox QLabel {{
    color: {COLORS["text_primary"]};
    font-size: 13px;
}}

QMessageBox QPushButton {{
    min-width: 80px;
    max-height: 32px;
    min-height: 32px;
}}

/* ===== QFormLayout labels ===== */
QFormLayout QLabel {{
    color: {COLORS["text_secondary"]};
    font-size: 12px;
}}
"""
