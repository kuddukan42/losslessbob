import sys as _sys

from PyQt6.QtGui import QColor


def _platform_font_stack() -> str:
    if _sys.platform == "win32":
        return "Segoe UI, Arial, sans-serif"
    elif _sys.platform == "darwin":
        return "-apple-system, Helvetica Neue, Arial, sans-serif"
    else:
        return "Ubuntu, Cantarell, DejaVu Sans, Arial, sans-serif"

ROW_MATCHED = QColor("#90EE90")
ROW_NOT_FOUND = QColor("#FFA07A")
ROW_MISSING = QColor("#FFB6C1")
ROW_DUPLICATE = QColor("#FFFF99")
ROW_XREF = QColor("#E0E0FF")
ROW_OWNED = QColor("#C8E6C9")
ROW_WISHLIST = QColor("#E8D5FF")
HEADER_BG = QColor("#1F4E79")
HEADER_FG = QColor("#FFFFFF")
APP_BG = QColor("#F8F8F0")
SELECTION_COLOR = QColor("#CCE5FF")

MAIN_STYLESHEET = ""  # set by apply_theme() at startup


def build_stylesheet(t):
    return f"""
QMainWindow, QWidget {{
    background-color: {t['app_bg']};
    color: {t['app_fg']};
    font-family: {_platform_font_stack()};
    font-size: 9pt;
}}
QTabWidget::pane {{
    border: 1px solid {t['border']};
}}
QTabBar::tab {{
    background: {t['tab_bg']};
    color: {t['app_fg']};
    padding: 5px 12px;
    border: none;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {t['tab_selected']};
    color: {t['app_fg']};
    font-weight: 700;
    border-bottom: 2px solid {t['accent']};
}}
QTableView {{
    color: {t['app_fg']};
    background-color: {t['table_bg']};
    gridline-color: {t['border']};
    selection-background-color: {t['selection']};
    selection-color: {t['app_fg']};
    alternate-background-color: {t['table_alt']};
}}
QHeaderView::section {{
    background-color: {t['header_bg']};
    color: {t['header_fg']};
    font-weight: 700;
    padding: 4px;
    border: 1px solid {t['accent_pressed']};
}}
QPushButton {{
    background-color: {t['accent']};
    color: {t['header_fg']};
    border: none;
    padding: 5px 14px;
    border-radius: 6px;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: {t['accent_hover']};
    color: {t['header_fg']};
}}
QPushButton:pressed {{
    background-color: {t['accent_pressed']};
    color: {t['header_fg']};
}}
QPushButton:disabled {{
    background-color: #A0A0A0;
    color: #E0E0E0;
}}
QListWidget {{
    border: 1px solid {t['border']};
    background-color: {t['table_bg']};
    color: {t['app_fg']};
}}
QListWidget::item:selected {{
    background-color: {t['selection']};
    color: {t['app_fg']};
}}
QLineEdit, QSpinBox {{
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px 6px;
    background-color: {t['input_bg']};
    color: {t['app_fg']};
}}
QComboBox {{
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 2px 6px;
    background-color: {t['input_bg']};
    color: {t['app_fg']};
}}
QComboBox QAbstractItemView {{
    background-color: {t['input_bg']};
    color: {t['app_fg']};
    selection-background-color: {t['selection']};
    border: 1px solid {t['border']};
}}
QLabel {{
    color: {t['app_fg']};
}}
QCheckBox, QRadioButton {{
    color: {t['app_fg']};
}}
QMenuBar {{
    background-color: {t['app_bg']};
    color: {t['app_fg']};
}}
QMenuBar::item:selected {{
    background-color: {t['selection']};
    color: {t['app_fg']};
}}
QMenu {{
    background-color: {t['input_bg']};
    color: {t['app_fg']};
    border: 1px solid {t['border']};
}}
QMenu::item:selected {{
    background-color: {t['selection']};
    color: {t['app_fg']};
}}
QStatusBar {{
    background-color: {t['status_bg']};
    color: {t['app_fg']};
    border-top: 1px solid {t['border']};
}}
QProgressBar {{
    border: none;
    border-radius: 3px;
    background-color: {t['table_bg']};
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 3px;
}}
QProgressBar#scrapeProgress,
QProgressBar#importProgress {{
    min-height: 20px;
    max-height: 20px;
    border-radius: 4px;
    color: {t['app_fg']};
    text-align: center;
}}
QProgressBar#scrapeProgress::chunk,
QProgressBar#importProgress::chunk {{
    border-radius: 4px;
}}
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 1.5em;
    padding-top: 6px;
    font-weight: 700;
    color: {t['app_fg']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {t['table_alt']};
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {t['border']};
    min-width: 8px;
    min-height: 8px;
    border-radius: 3px;
}}
QSplitter::handle {{
    background-color: {t['border']};
}}
"""


def apply_theme(theme_dict):
    global ROW_MATCHED, ROW_NOT_FOUND, ROW_MISSING, ROW_DUPLICATE, ROW_XREF, ROW_OWNED, ROW_WISHLIST
    global HEADER_BG, HEADER_FG, APP_BG, SELECTION_COLOR, MAIN_STYLESHEET
    ROW_MATCHED = QColor(theme_dict["row_matched"])
    ROW_NOT_FOUND = QColor(theme_dict["row_not_found"])
    ROW_MISSING = QColor(theme_dict["row_missing"])
    ROW_DUPLICATE = QColor(theme_dict["row_duplicate"])
    ROW_XREF = QColor(theme_dict["row_xref"])
    ROW_OWNED = QColor(theme_dict.get("row_owned", "#C8E6C9"))
    ROW_WISHLIST = QColor(theme_dict.get("row_wishlist", "#E8D5FF"))
    HEADER_BG = QColor(theme_dict["header_bg"])
    HEADER_FG = QColor(theme_dict["header_fg"])
    APP_BG = QColor(theme_dict["app_bg"])
    SELECTION_COLOR = QColor(theme_dict["selection"])
    MAIN_STYLESHEET = build_stylesheet(theme_dict)


def apply_panel_shadow(widget):
    """Attach a subtle drop-shadow effect to a results panel widget."""
    from PyQt6.QtWidgets import QGraphicsDropShadowEffect
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(12)
    effect.setOffset(0, 2)
    effect.setColor(QColor(0, 0, 0, 60))
    widget.setGraphicsEffect(effect)


# Apply the default (Light) theme at import time
apply_theme({
    "app_bg": "#F8F8F0", "app_fg": "#1A1A1A",
    "accent": "#1F4E79", "accent_hover": "#2E6FA3", "accent_pressed": "#14375A",
    "header_bg": "#1F4E79", "header_fg": "#FFFFFF",
    "table_bg": "#FFFFFF", "table_alt": "#F0F0E8",
    "border": "#CCCCCC", "status_bg": "#E8E8E0",
    "tab_bg": "#E0E0E0", "tab_selected": "#F8F8F0",
    "selection": "#CCE5FF", "input_bg": "#FFFFFF",
    "row_matched": "#90EE90", "row_not_found": "#FFA07A",
    "row_missing": "#FFB6C1", "row_duplicate": "#FFFF99", "row_xref": "#E0E0FF",
    "row_owned": "#C8E6C9", "row_wishlist": "#E8D5FF",
})
