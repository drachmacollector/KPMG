"""
app/ui/styles.py

Centralised Qt stylesheet and palette constants for the MAHABOCW GUI.

Design: deep dark glassmorphism with indigo accent, subtle gradients, smooth
hover transitions, and premium spacing. Every widget class references these
constants so colour changes only need to happen in one place.
"""

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
COLORS = {
    # Backgrounds
    "bg_deep":     "#080d18",
    "bg_base":     "#0e1624",
    "bg_surface":  "#151f32",
    "bg_elevated": "#1c2a42",
    "bg_card":     "#131d2e",

    # Accent (indigo / blue-violet)
    "accent":        "#6366f1",
    "accent_hover":  "#818cf8",
    "accent_press":  "#4f46e5",
    "accent_muted":  "#3730a3",
    "accent_glow":   "rgba(99,102,241,0.35)",
    "accent_subtle": "rgba(99,102,241,0.12)",

    # Success / warning / error
    "success":        "#22c55e",
    "success_subtle": "rgba(34,197,94,0.12)",
    "success_border": "rgba(34,197,94,0.35)",
    "warning":        "#f59e0b",
    "error":          "#ef4444",
    "error_subtle":   "rgba(239,68,68,0.12)",
    "error_border":   "rgba(239,68,68,0.35)",
    "info":           "#38bdf8",

    # Text
    "text_primary":   "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted":     "#475569",
    "text_disabled":  "#64748b",
    "text_accent":    "#a5b4fc",

    # Borders
    "border":        "#1e2d45",
    "border_focus":  "#6366f1",
    "border_subtle": "#131e30",
    "border_accent": "rgba(99,102,241,0.4)",
}

# ---------------------------------------------------------------------------
# Full application stylesheet
# ---------------------------------------------------------------------------
APP_STYLESHEET = f"""
/* ===== Global reset ===== */
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
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.5px;
}}

QLabel#subheading {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
    letter-spacing: 0.1px;
}}

QLabel#splash_title {{
    font-size: 30px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
    padding-top: 8px;
    padding-bottom: 8px;
    background: transparent;
}}

QLabel#splash_sub {{
    font-size: 14px;
    color: {COLORS["text_secondary"]};
    letter-spacing: 0.2px;
    line-height: 1.6;
    padding-top: 4px;
    padding-bottom: 4px;
    background: transparent;
}}

QLabel#splash_version {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS["text_accent"]};
    background: {COLORS["accent_subtle"]};
    border: 1px solid {COLORS["border_accent"]};
    border-radius: 10px;
    padding: 3px 10px;
    letter-spacing: 0.5px;
}}

QLabel#section_label {{
    font-size: 10px;
    font-weight: 700;
    color: {COLORS["text_secondary"]};
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}

QLabel#accent_label {{
    color: {COLORS["text_accent"]};
    font-weight: 600;
}}

QLabel#error_label {{
    color: {COLORS["error"]};
}}

QLabel#stat_number {{
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
    background: transparent;
}}

QLabel#stat_sub {{
    font-size: 12px;
    color: {COLORS["text_secondary"]};
    background: transparent;
}}

QLabel#pill {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS["text_secondary"]};
    background: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    padding: 3px 12px;
}}

QLabel#success_pill {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS["success"]};
    background: {COLORS["success_subtle"]};
    border: 1px solid {COLORS["success_border"]};
    border-radius: 10px;
    padding: 3px 12px;
}}

QLabel#check_badge {{
    font-size: 32px;
    font-weight: 700;
    color: {COLORS["success"]};
    background: {COLORS["success_subtle"]};
    border: 2px solid {COLORS["success_border"]};
    border-radius: 40px;
    padding: 16px 24px;
    qproperty-alignment: AlignCenter;
}}

QLabel#elapsed_label {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS["text_muted"]};
    font-family: "Cascadia Code", "Consolas", monospace;
    background: transparent;
}}

/* ===== QPushButton — base ===== */
QPushButton {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    padding: 0px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 36px;
    max-height: 36px;
}}

QPushButton:hover {{
    background-color: {COLORS["bg_surface"]};
    border-color: {COLORS["border_accent"]};
    color: #ffffff;
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

/* ===== Primary button ===== */
QPushButton#primary {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    color: #ffffff;
    border: none;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.3px;
    min-height: 40px;
    max-height: 40px;
    border-radius: 10px;
    padding: 0px 24px;
}}

QPushButton#primary:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent_hover"]}, stop:1 #c7d2fe
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

/* Primary button — glow state (toggled via QTimer for pulse effect) */
QPushButton#primary_glow {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    color: #ffffff;
    border: 2px solid {COLORS["accent_hover"]};
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.4px;
    min-height: 52px;
    max-height: 52px;
    border-radius: 12px;
    padding: 0px 32px;
}}

QPushButton#primary_glow_dim {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:1 {COLORS["accent_hover"]}
    );
    color: #ffffff;
    border: 2px solid {COLORS["accent_muted"]};
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.4px;
    min-height: 52px;
    max-height: 52px;
    border-radius: 12px;
    padding: 0px 32px;
}}

QPushButton#primary_glow:hover, QPushButton#primary_glow_dim:hover {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent_hover"]}, stop:1 #c7d2fe
    );
    border-color: #c7d2fe;
}}

QPushButton#primary_glow:pressed, QPushButton#primary_glow_dim:pressed {{
    background: {COLORS["accent_press"]};
}}

/* ===== Danger button ===== */
QPushButton#danger {{
    background-color: transparent;
    color: {COLORS["error"]};
    border: 1px solid {COLORS["error_border"]};
    font-weight: 500;
    border-radius: 10px;
}}

QPushButton#danger:hover {{
    background-color: {COLORS["error_subtle"]};
    color: #fca5a5;
    border-color: {COLORS["error"]};
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
    border: 1px solid {COLORS["success_border"]};
    font-weight: 600;
    border-radius: 10px;
}}

QPushButton#success_btn:hover {{
    background-color: {COLORS["success_subtle"]};
    color: #86efac;
    border-color: {COLORS["success"]};
}}

/* ===== Ghost button ===== */
QPushButton#ghost {{
    background: transparent;
    border: none;
    color: {COLORS["text_secondary"]};
    padding: 0px 12px;
    min-height: 32px;
    max-height: 32px;
    font-weight: 400;
    border-radius: 8px;
}}

QPushButton#ghost:hover {{
    color: {COLORS["text_primary"]};
    background: rgba(255,255,255,0.06);
}}

QPushButton#ghost:pressed {{
    background: rgba(255,255,255,0.10);
}}

/* ===== QLineEdit ===== */
QLineEdit {{
    background-color: {COLORS["bg_deep"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    padding: 0px 14px;
    min-height: 36px;
    max-height: 36px;
    selection-background-color: {COLORS["accent_muted"]};
    font-size: 13px;
}}

QLineEdit:focus {{
    border-color: {COLORS["border_focus"]};
    background-color: {COLORS["bg_base"]};
    color: #ffffff;
}}

QLineEdit:disabled {{
    color: {COLORS["text_disabled"]};
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
    border-radius: 10px;
    padding: 0px 14px;
    min-height: 36px;
    max-height: 36px;
    font-size: 13px;
}}

QComboBox:focus {{
    border-color: {COLORS["border_focus"]};
}}

QComboBox:hover {{
    border-color: {COLORS["border_accent"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {COLORS["text_secondary"]};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
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
    border-radius: 10px;
    padding: 0px 10px;
    min-height: 36px;
    max-height: 36px;
    font-size: 13px;
}}

QSpinBox:focus {{
    border-color: {COLORS["border_focus"]};
}}

QSpinBox:disabled {{
    color: {COLORS["text_disabled"]};
    border-color: {COLORS["border_subtle"]};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {COLORS["bg_elevated"]};
    border: none;
    width: 22px;
    border-radius: 4px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {COLORS["accent_muted"]};
}}

/* ===== QProgressBar ===== */
QProgressBar {{
    background-color: {COLORS["bg_deep"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 7px;
    height: 12px;
    text-align: center;
    color: transparent;
    font-size: 11px;
}}

QProgressBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS["accent"]}, stop:0.5 {COLORS["accent_hover"]}, stop:1 #c7d2fe
    );
    border-radius: 7px;
}}

/* ===== QPlainTextEdit (log pane) ===== */
QPlainTextEdit {{
    background-color: {COLORS["bg_deep"]};
    color: #c8d6e8;
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 14px;
    font-family: "Cascadia Code", "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: {COLORS["accent_muted"]};
    line-height: 1.6;
}}

/* ===== QFrame — accent stripe ===== */
QFrame#accent_stripe {{
    background: {COLORS["accent"]};
    border-radius: 2px;
    min-width: 3px;
    max-width: 3px;
}}

QFrame#divider {{
    background: {COLORS["border"]};
    min-height: 1px;
    max-height: 1px;
}}

/* ===== QScrollBar ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
    margin: 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS["border_accent"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    border-radius: 3px;
    margin: 0 4px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS["border"]};
    border-radius: 3px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS["border_accent"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    border: none;
    background: none;
}}

/* ===== QGroupBox ===== */
QGroupBox {{
    border: 1px solid {COLORS["border"]};
    border-radius: 14px;
    margin-top: 16px;
    padding: 20px 18px 16px 18px;
    font-weight: 700;
    font-size: 10px;
    color: {COLORS["text_secondary"]};
    background: {COLORS["bg_card"]};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 10px;
    color: {COLORS["text_accent"]};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    background: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border_accent"]};
    border-radius: 8px;
    left: 14px;
}}

/* ===== QRadioButton / QCheckBox ===== */
QRadioButton, QCheckBox {{
    color: {COLORS["text_primary"]};
    spacing: 10px;
    font-size: 13px;
}}

QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 2px solid {COLORS["border"]};
    border-radius: 9px;
    background: {COLORS["bg_deep"]};
}}

QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 2px solid {COLORS["border"]};
    border-radius: 5px;
    background: {COLORS["bg_deep"]};
}}

QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}

QRadioButton:hover, QCheckBox:hover {{
    color: #ffffff;
}}

/* ===== QSplitter ===== */
QSplitter::handle {{
    background-color: {COLORS["border"]};
}}

/* ===== QToolTip ===== */
QToolTip {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border_accent"]};
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
}}

/* ===== QMessageBox ===== */
QMessageBox {{
    background-color: {COLORS["bg_surface"]};
    color: {COLORS["text_primary"]};
    border-radius: 12px;
}}

QMessageBox QLabel {{
    color: {COLORS["text_primary"]};
    font-size: 13px;
}}

QMessageBox QPushButton {{
    min-width: 88px;
    max-height: 36px;
    min-height: 36px;
    border-radius: 9px;
}}

/* ===== QFormLayout labels ===== */
QFormLayout QLabel {{
    color: {COLORS["text_secondary"]};
    font-size: 12px;
}}

/* ===== QScrollArea ===== */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
"""

# ---------------------------------------------------------------------------
# Splash screen card style (applied directly, not via global sheet)
# ---------------------------------------------------------------------------
SPLASH_CARD_STYLE = f"""
    QWidget#splash_card {{
        background: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {COLORS["bg_surface"]}, stop:1 {COLORS["bg_card"]}
        );
        border-radius: 20px;
        border: 1px solid {COLORS["border"]};
    }}
"""
