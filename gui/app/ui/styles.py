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
    "bg_deep":     "#0f1117",
    "bg_base":     "#161b27",
    "bg_surface":  "#1e2535",
    "bg_elevated": "#252d40",
    "bg_card":     "#1a2133",

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

    # Text
    "text_primary":   "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_disabled":  "#475569",
    "text_accent":    "#818cf8",

    # Borders
    "border":        "#2d3748",
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
    color: {COLORS["text_primary"]};
}}

QLabel#subheading {{
    font-size: 14px;
    color: {COLORS["text_secondary"]};
}}

QLabel#section_label {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS["text_secondary"]};
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QLabel#accent_label {{
    color: {COLORS["accent_hover"]};
    font-weight: 600;
}}

QLabel#error_label {{
    color: {COLORS["error"]};
}}

/* ===== QPushButton ===== */
QPushButton {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 500;
    min-height: 36px;
}}

QPushButton:hover {{
    background-color: {COLORS["bg_surface"]};
    border-color: {COLORS["accent"]};
    color: {COLORS["text_primary"]};
}}

QPushButton:pressed {{
    background-color: {COLORS["accent_muted"]};
    border-color: {COLORS["accent_press"]};
}}

QPushButton:disabled {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_disabled"]};
    border-color: {COLORS["border_subtle"]};
}}

QPushButton#primary {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    color: #ffffff;
    border: none;
    font-weight: 600;
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

QPushButton#danger {{
    background-color: transparent;
    color: {COLORS["error"]};
    border: 1px solid {COLORS["error"]};
}}

QPushButton#danger:hover {{
    background-color: rgba(239, 68, 68, 0.15);
}}

QPushButton#success_btn {{
    background-color: transparent;
    color: {COLORS["success"]};
    border: 1px solid {COLORS["success"]};
}}

QPushButton#success_btn:hover {{
    background-color: rgba(34, 197, 94, 0.15);
}}

QPushButton#ghost {{
    background: transparent;
    border: none;
    color: {COLORS["text_secondary"]};
    padding: 4px 8px;
    min-height: 28px;
}}

QPushButton#ghost:hover {{
    color: {COLORS["text_primary"]};
    background: rgba(255,255,255,0.05);
    border-radius: 6px;
}}

/* ===== QLineEdit ===== */
QLineEdit {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
    selection-background-color: {COLORS["accent_muted"]};
}}

QLineEdit:focus {{
    border-color: {COLORS["border_focus"]};
    background-color: {COLORS["bg_base"]};
}}

QLineEdit:disabled {{
    color: {COLORS["text_disabled"]};
    border-color: {COLORS["border_subtle"]};
}}

QLineEdit[echoMode="2"] {{
    lineedit-password-character: 9679;
}}

/* ===== QComboBox ===== */
QComboBox {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 20px;
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

/* ===== QProgressBar ===== */
QProgressBar {{
    background-color: {COLORS["bg_deep"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    height: 12px;
    text-align: center;
    color: {COLORS["text_primary"]};
    font-size: 11px;
}}

QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    border-radius: 8px;
}}

/* ===== QPlainTextEdit (log pane) ===== */
QPlainTextEdit {{
    background-color: {COLORS["bg_deep"]};
    color: #a8b9cc;
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px;
    font-family: "Consolas", "Cascadia Code", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: {COLORS["accent_muted"]};
}}

/* ===== QScrollBar ===== */
QScrollBar:vertical {{
    background: {COLORS["bg_deep"]};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 4px;
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
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS["border"]};
    border-radius: 4px;
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
    margin-top: 12px;
    padding: 12px 16px 12px 16px;
    font-weight: 600;
    color: {COLORS["text_secondary"]};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {COLORS["text_secondary"]};
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ===== QRadioButton / QCheckBox ===== */
QRadioButton, QCheckBox {{
    color: {COLORS["text_primary"]};
    spacing: 8px;
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

QMessageBox QPushButton {{
    min-width: 80px;
}}
"""
