import copy

from PyQt6.QtCore import pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QScrollArea, QColorDialog, QGridLayout,
    QFrame, QApplication,
)

import gui.styles as styles

THEMES = {
    "Light": {
        "app_bg": "#F8F8F0", "app_fg": "#1A1A1A",
        "accent": "#1F4E79", "accent_hover": "#2E6FA3", "accent_pressed": "#14375A",
        "header_bg": "#1F4E79", "header_fg": "#FFFFFF",
        "table_bg": "#FFFFFF", "table_alt": "#F0F0E8",
        "border": "#CCCCCC", "status_bg": "#E8E8E0",
        "tab_bg": "#E0E0E0", "tab_selected": "#F8F8F0",
        "selection": "#CCE5FF", "input_bg": "#FFFFFF",
        "row_matched": "#90EE90", "row_not_found": "#FFA07A",
        "row_missing": "#FFB6C1", "row_duplicate": "#FFFF99", "row_xref": "#E0E0FF",
    },
    "Dark": {
        "app_bg": "#2D2D2D", "app_fg": "#D4D4D4",
        "accent": "#2E6FA3", "accent_hover": "#3A8AC4", "accent_pressed": "#1A5276",
        "header_bg": "#1A5276", "header_fg": "#FFFFFF",
        "table_bg": "#3A3A3A", "table_alt": "#404040",
        "border": "#555555", "status_bg": "#222222",
        "tab_bg": "#3A3A3A", "tab_selected": "#2D2D2D",
        "selection": "#1A4A7A", "input_bg": "#444444",
        "row_matched": "#1E5C1E", "row_not_found": "#7A2E1E",
        "row_missing": "#6B1F2E", "row_duplicate": "#6B6B1A", "row_xref": "#1A1A5C",
    },
    "Black": {
        "app_bg": "#0D0D0D", "app_fg": "#E0E0E0",
        "accent": "#2A2A2A", "accent_hover": "#404040", "accent_pressed": "#111111",
        "header_bg": "#111111", "header_fg": "#CCCCCC",
        "table_bg": "#141414", "table_alt": "#1C1C1C",
        "border": "#333333", "status_bg": "#0A0A0A",
        "tab_bg": "#1A1A1A", "tab_selected": "#0D0D0D",
        "selection": "#2A2A4A", "input_bg": "#1A1A1A",
        "row_matched": "#0F3B0F", "row_not_found": "#4A1A0F",
        "row_missing": "#3B0F1A", "row_duplicate": "#3B3B0F", "row_xref": "#0F0F3B",
    },
    "Dracula": {
        "app_bg": "#282A36", "app_fg": "#F8F8F2",
        "accent": "#6272A4", "accent_hover": "#BD93F9", "accent_pressed": "#44475A",
        "header_bg": "#44475A", "header_fg": "#F8F8F2",
        "table_bg": "#282A36", "table_alt": "#30323E",
        "border": "#6272A4", "status_bg": "#21222C",
        "tab_bg": "#44475A", "tab_selected": "#282A36",
        "selection": "#44475A", "input_bg": "#21222C",
        "row_matched": "#1A5C30", "row_not_found": "#7A2020",
        "row_missing": "#5C1A3A", "row_duplicate": "#4A4A10", "row_xref": "#2A2050",
    },
    "Blue": {
        "app_bg": "#EBF5FB", "app_fg": "#1A2A4A",
        "accent": "#1565C0", "accent_hover": "#1976D2", "accent_pressed": "#0D47A1",
        "header_bg": "#0D47A1", "header_fg": "#FFFFFF",
        "table_bg": "#FFFFFF", "table_alt": "#E3F2FD",
        "border": "#90CAF9", "status_bg": "#BBDEFB",
        "tab_bg": "#BBDEFB", "tab_selected": "#EBF5FB",
        "selection": "#90CAF9", "input_bg": "#FFFFFF",
        "row_matched": "#A5D6A7", "row_not_found": "#EF9A9A",
        "row_missing": "#F48FB1", "row_duplicate": "#FFF176", "row_xref": "#B3E5FC",
    },
    "Purple": {
        "app_bg": "#F3E5F5", "app_fg": "#1A0A2A",
        "accent": "#7B1FA2", "accent_hover": "#9C27B0", "accent_pressed": "#4A148C",
        "header_bg": "#4A148C", "header_fg": "#FFFFFF",
        "table_bg": "#FFFFFF", "table_alt": "#EDE7F6",
        "border": "#CE93D8", "status_bg": "#E1BEE7",
        "tab_bg": "#E1BEE7", "tab_selected": "#F3E5F5",
        "selection": "#CE93D8", "input_bg": "#FFFFFF",
        "row_matched": "#A5D6A7", "row_not_found": "#EF9A9A",
        "row_missing": "#F48FB1", "row_duplicate": "#FFF176", "row_xref": "#E1BEE7",
    },
}

COLOR_LABELS = [
    ("App Background",       "app_bg"),
    ("App Text",             "app_fg"),
    ("Accent / Buttons",     "accent"),
    ("Accent Hover",         "accent_hover"),
    ("Accent Pressed",       "accent_pressed"),
    ("Table Header Bg",      "header_bg"),
    ("Table Header Text",    "header_fg"),
    ("Table Background",     "table_bg"),
    ("Table Alt Row",        "table_alt"),
    ("Border",               "border"),
    ("Status Bar",           "status_bg"),
    ("Tab Background",       "tab_bg"),
    ("Tab Selected",         "tab_selected"),
    ("Selection Highlight",  "selection"),
    ("Input Background",     "input_bg"),
    ("Row: Matched",         "row_matched"),
    ("Row: Not Found",       "row_not_found"),
    ("Row: Missing",         "row_missing"),
    ("Row: Duplicate",       "row_duplicate"),
    ("Row: Cross-ref",       "row_xref"),
]

_SETTINGS_GROUP = "LosslessBobLookup"


class ThemeTab(QWidget):
    theme_applied = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = copy.deepcopy(THEMES["Light"])
        self._custom = copy.deepcopy(THEMES["Light"])
        self._swatches = {}
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # ── Left: theme selector ──────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(130)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(QLabel("Presets"))

        self.theme_list = QListWidget()
        for name in list(THEMES.keys()) + ["Custom"]:
            self.theme_list.addItem(QListWidgetItem(name))
        self.theme_list.currentTextChanged.connect(self._on_preset_selected)
        left_layout.addWidget(self.theme_list)
        layout.addWidget(left)

        # ── Right: swatches + apply ───────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("Click any color swatch to customize. Changes become Custom.")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        swatch_container = QWidget()
        grid = QGridLayout(swatch_container)
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnMinimumWidth(1, 110)

        for row_idx, (label_text, key) in enumerate(COLOR_LABELS):
            grid.addWidget(QLabel(label_text), row_idx, 0, Qt.AlignmentFlag.AlignRight)
            btn = QPushButton()
            btn.setFixedHeight(22)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda checked, k=key: self._on_swatch_clicked(k))
            self._swatches[key] = btn
            grid.addWidget(btn, row_idx, 1)

        scroll.setWidget(swatch_container)
        right_layout.addWidget(scroll)

        self.apply_btn = QPushButton("Apply Theme")
        self.apply_btn.clicked.connect(self._on_apply)
        right_layout.addWidget(self.apply_btn)

        self.status_label = QLabel("")
        right_layout.addWidget(self.status_label)

        layout.addWidget(right, 1)

        self._refresh_swatches()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _refresh_swatches(self):
        for key, btn in self._swatches.items():
            color = self._current.get(key, "#FFFFFF")
            qc = QColor(color)
            luma = 0.299 * qc.red() + 0.587 * qc.green() + 0.114 * qc.blue()
            fg = "#000000" if luma > 128 else "#FFFFFF"
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color}; color: {fg}; "
                f"border: 1px solid #888; border-radius: 2px; padding: 0 6px; }}"
                f"QPushButton:hover {{ background-color: {color}; border: 1px solid #444; }}"
            )
            btn.setText(color.upper())

    def _switch_to_custom(self):
        for i in range(self.theme_list.count()):
            if self.theme_list.item(i).text() == "Custom":
                self.theme_list.blockSignals(True)
                self.theme_list.setCurrentRow(i)
                self.theme_list.blockSignals(False)
                break

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_preset_selected(self, name):
        if name == "Custom":
            self._current = copy.deepcopy(self._custom)
        elif name in THEMES:
            self._current = copy.deepcopy(THEMES[name])
        self._refresh_swatches()

    def _on_swatch_clicked(self, key):
        initial = QColor(self._current.get(key, "#FFFFFF"))
        color = QColorDialog.getColor(initial, self, f"Choose color")
        if not color.isValid():
            return
        current_name = self.theme_list.currentItem().text() if self.theme_list.currentItem() else ""
        if current_name != "Custom":
            self._custom = copy.deepcopy(self._current)
            self._switch_to_custom()
        self._current[key] = color.name()
        self._custom[key] = color.name()
        self._refresh_swatches()

    def _on_apply(self):
        styles.apply_theme(self._current)
        self._save_settings()
        self.theme_applied.emit()
        self.status_label.setText("Theme applied.")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_settings(self):
        s = QSettings(_SETTINGS_GROUP, _SETTINGS_GROUP)
        name = self.theme_list.currentItem().text() if self.theme_list.currentItem() else "Light"
        s.setValue("theme/name", name)
        for _, key in COLOR_LABELS:
            s.setValue(f"theme/color/{key}", self._current.get(key, ""))

    def load_and_apply_saved(self):
        s = QSettings(_SETTINGS_GROUP, _SETTINGS_GROUP)
        name = s.value("theme/name", "Light")

        saved_colors = {}
        for _, key in COLOR_LABELS:
            val = s.value(f"theme/color/{key}", "")
            if val:
                saved_colors[key] = val

        if name in THEMES:
            self._current = copy.deepcopy(THEMES[name])
        else:
            name = "Custom"
            self._current = copy.deepcopy(THEMES["Light"])

        if saved_colors:
            self._current.update(saved_colors)

        if name == "Custom":
            self._custom = copy.deepcopy(self._current)

        for i in range(self.theme_list.count()):
            if self.theme_list.item(i).text() == name:
                self.theme_list.blockSignals(True)
                self.theme_list.setCurrentRow(i)
                self.theme_list.blockSignals(False)
                break

        self._refresh_swatches()
        self._on_apply()
