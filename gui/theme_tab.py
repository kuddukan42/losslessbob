import copy

from PyQt6.QtCore import pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QScrollArea, QColorDialog, QGridLayout,
    QFrame, QComboBox, QSpinBox,
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
        "row_owned": "#C8E6C9", "row_wishlist": "#E8D5FF",
        "row_fail": "#FFCDD2", "row_missing_file": "#FFE0B2", "row_grey": "#E0E0E0",
        "row_private": "#B3E5FC", "row_wrong_lb": "#E1BEE7", "row_multiple_ids": "#B2EBF2",
        "row_dirty": "#FFFBE6", "row_audit": "#F0F0FF", "row_readonly": "#F4F4F4",
        "row_nft_missing": "#FFCCCC", "row_nft_stale": "#FFF9C4", "row_nft_unknown": "#FFE8D0",
        "status_ok": "#D4EDDA", "status_warn": "#FFF3CD", "status_error": "#F8D7DA",
        "status_neutral": "#E2E3E5",
        "fg_muted": "#888888", "fg_link": "#1565C0", "fg_danger": "#C0392B",
        "fg_success": "#2E7D32", "fg_warning": "#E65100",
    },
    "Dark": {
        "app_bg": "#2D2D2D", "app_fg": "#D4D4D4",
        "accent": "#2E6FA3", "accent_hover": "#3A8AC4", "accent_pressed": "#1A5276",
        "header_bg": "#1A5276", "header_fg": "#FFFFFF",
        "table_bg": "#3A3A3A", "table_alt": "#404040",
        "border": "#555555", "status_bg": "#222222",
        "tab_bg": "#3A3A3A", "tab_selected": "#2D2D2D",
        "selection": "#1A4A7A", "input_bg": "#444444",
        "row_matched": "#206820", "row_not_found": "#922C1C",
        "row_missing": "#922848", "row_duplicate": "#6B6B1A", "row_xref": "#4040A8",
        "row_owned": "#267040", "row_wishlist": "#603098",
        "row_fail": "#6A2020", "row_missing_file": "#5A3010", "row_grey": "#3A3A3A",
        "row_private": "#0A3A5A", "row_wrong_lb": "#3A2A4A", "row_multiple_ids": "#0A3A4A",
        "row_dirty": "#4A4410", "row_audit": "#1A1A4A", "row_readonly": "#2A2A2A",
        "row_nft_missing": "#5A1818", "row_nft_stale": "#4A4010", "row_nft_unknown": "#502A10",
        "status_ok": "#1A4A2A", "status_warn": "#4A3C10", "status_error": "#4A1A1A",
        "status_neutral": "#3A3A3A",
        "fg_muted": "#888888", "fg_link": "#5BA4F5", "fg_danger": "#E74C3C",
        "fg_success": "#52BE80", "fg_warning": "#F39C12",
    },
    "Black": {
        "app_bg": "#0D0D0D", "app_fg": "#E0E0E0",
        "accent": "#2A2A2A", "accent_hover": "#404040", "accent_pressed": "#111111",
        "header_bg": "#111111", "header_fg": "#CCCCCC",
        "table_bg": "#141414", "table_alt": "#1C1C1C",
        "border": "#333333", "status_bg": "#0A0A0A",
        "tab_bg": "#1A1A1A", "tab_selected": "#0D0D0D",
        "selection": "#2A2A4A", "input_bg": "#1A1A1A",
        "row_matched": "#0F3B0F", "row_not_found": "#6B280F",
        "row_missing": "#5C1428", "row_duplicate": "#3B3B0F", "row_xref": "#20207E",
        "row_owned": "#163D20", "row_wishlist": "#321480",
        "row_fail": "#481010", "row_missing_file": "#3C2008", "row_grey": "#252525",
        "row_private": "#082840", "row_wrong_lb": "#28183A", "row_multiple_ids": "#082830",
        "row_dirty": "#2E2C08", "row_audit": "#101030", "row_readonly": "#1A1A1A",
        "row_nft_missing": "#3A0E0E", "row_nft_stale": "#2C2808", "row_nft_unknown": "#3A1C08",
        "status_ok": "#0F3020", "status_warn": "#302A08", "status_error": "#301010",
        "status_neutral": "#252525",
        "fg_muted": "#666666", "fg_link": "#4488CC", "fg_danger": "#FF5555",
        "fg_success": "#27AE60", "fg_warning": "#E67E22",
    },
    "Dracula": {
        "app_bg": "#282A36", "app_fg": "#F8F8F2",
        "accent": "#6272A4", "accent_hover": "#BD93F9", "accent_pressed": "#44475A",
        "header_bg": "#44475A", "header_fg": "#F8F8F2",
        "table_bg": "#282A36", "table_alt": "#30323E",
        "border": "#6272A4", "status_bg": "#21222C",
        "tab_bg": "#44475A", "tab_selected": "#282A36",
        "selection": "#44475A", "input_bg": "#21222C",
        "row_matched": "#1A5C30", "row_not_found": "#8C2424",
        "row_missing": "#7A2048", "row_duplicate": "#4A4A10", "row_xref": "#383098",
        "row_owned": "#1C6030", "row_wishlist": "#5028A0",
        "row_fail": "#682020", "row_missing_file": "#503010", "row_grey": "#44475A",
        "row_private": "#1A2A50", "row_wrong_lb": "#3A2850", "row_multiple_ids": "#1A3850",
        "row_dirty": "#4A4218", "row_audit": "#1E2250", "row_readonly": "#30323E",
        "row_nft_missing": "#521818", "row_nft_stale": "#484018", "row_nft_unknown": "#503010",
        "status_ok": "#1A4A28", "status_warn": "#4A3C18", "status_error": "#4A1A24",
        "status_neutral": "#44475A",
        "fg_muted": "#6272A4", "fg_link": "#BD93F9", "fg_danger": "#FF5555",
        "fg_success": "#50FA7B", "fg_warning": "#FFB86C",
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
        "row_owned": "#A5D6A7", "row_wishlist": "#CE93D8",
        "row_fail": "#FFCDD2", "row_missing_file": "#FFE0B2", "row_grey": "#CFD8DC",
        "row_private": "#81D4FA", "row_wrong_lb": "#CE93D8", "row_multiple_ids": "#80DEEA",
        "row_dirty": "#FFF9C4", "row_audit": "#BBDEFB", "row_readonly": "#ECEFF1",
        "row_nft_missing": "#FFCDD2", "row_nft_stale": "#FFF9C4", "row_nft_unknown": "#FFE0B2",
        "status_ok": "#C8E6C9", "status_warn": "#FFF9C4", "status_error": "#FFCDD2",
        "status_neutral": "#CFD8DC",
        "fg_muted": "#5B7FA6", "fg_link": "#0D47A1", "fg_danger": "#C62828",
        "fg_success": "#1B5E20", "fg_warning": "#E65100",
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
        "row_owned": "#A5D6A7", "row_wishlist": "#CE93D8",
        "row_fail": "#FFCDD2", "row_missing_file": "#FFE0B2", "row_grey": "#E0E0E0",
        "row_private": "#B3E5FC", "row_wrong_lb": "#E1BEE7", "row_multiple_ids": "#B2EBF2",
        "row_dirty": "#FFF9C4", "row_audit": "#EDE7F6", "row_readonly": "#F3E5F5",
        "row_nft_missing": "#FFCDD2", "row_nft_stale": "#FFF9C4", "row_nft_unknown": "#FFE0B2",
        "status_ok": "#C8E6C9", "status_warn": "#FFF9C4", "status_error": "#FFCDD2",
        "status_neutral": "#E0E0E0",
        "fg_muted": "#7B5FA6", "fg_link": "#6A1B9A", "fg_danger": "#B71C1C",
        "fg_success": "#1B5E20", "fg_warning": "#E65100",
    },
    "Red": {
        "app_bg": "#1A0A0A", "app_fg": "#F0D0D0",
        "accent": "#C0392B", "accent_hover": "#E74C3C", "accent_pressed": "#922B21",
        "header_bg": "#922B21", "header_fg": "#FFFFFF",
        "table_bg": "#2A1010", "table_alt": "#331515",
        "border": "#7B241C", "status_bg": "#110808",
        "tab_bg": "#331515", "tab_selected": "#1A0A0A",
        "selection": "#5C1A1A", "input_bg": "#331515",
        "row_matched": "#1E5C1E", "row_not_found": "#7A2E10",
        "row_missing": "#6B1F2E", "row_duplicate": "#6B6B1A", "row_xref": "#22226B",
        "row_owned": "#1E4A2A", "row_wishlist": "#3B2060",
        "row_fail": "#7A1A1A", "row_missing_file": "#5A2A10", "row_grey": "#3A2020",
        "row_private": "#0A2A4A", "row_wrong_lb": "#3A1A4A", "row_multiple_ids": "#0A2A3A",
        "row_dirty": "#4A3A10", "row_audit": "#1A1A4A", "row_readonly": "#2A1818",
        "row_nft_missing": "#6A1818", "row_nft_stale": "#4A3A10", "row_nft_unknown": "#5A2810",
        "status_ok": "#0F3B20", "status_warn": "#3B2E08", "status_error": "#5A1A1A",
        "status_neutral": "#3A2020",
        "fg_muted": "#8B5A5A", "fg_link": "#E57373", "fg_danger": "#FF6B6B",
        "fg_success": "#4CAF50", "fg_warning": "#FFB74D",
    },
    "Nord": {
        # Arctic blue-gray — https://www.nordtheme.com/
        "app_bg": "#2E3440", "app_fg": "#D8DEE9",
        "accent": "#5E81AC", "accent_hover": "#81A1C1", "accent_pressed": "#4C6E95",
        "header_bg": "#3B4252", "header_fg": "#ECEFF4",
        "table_bg": "#2E3440", "table_alt": "#3B4252",
        "border": "#4C566A", "status_bg": "#252A34",
        "tab_bg": "#3B4252", "tab_selected": "#2E3440",
        "selection": "#4C566A", "input_bg": "#3B4252",
        "row_matched": "#3B6B3B", "row_not_found": "#863C3C",
        "row_missing": "#6B4A3B", "row_duplicate": "#6B6030", "row_xref": "#445B80",
        "row_owned": "#426542", "row_wishlist": "#554A6B",
        "row_fail": "#5A2020", "row_missing_file": "#4A3010", "row_grey": "#3B4252",
        "row_private": "#1A2850", "row_wrong_lb": "#2E2A4A", "row_multiple_ids": "#1A3040",
        "row_dirty": "#3A3818", "row_audit": "#1A1A3A", "row_readonly": "#2A2E38",
        "row_nft_missing": "#4A1A1A", "row_nft_stale": "#3A3618", "row_nft_unknown": "#3A2810",
        "status_ok": "#1E3A1E", "status_warn": "#3A3018", "status_error": "#3A1A1E",
        "status_neutral": "#3B4252",
        "fg_muted": "#7B8699", "fg_link": "#81A1C1", "fg_danger": "#BF616A",
        "fg_success": "#A3BE8C", "fg_warning": "#EBCB8B",
    },
    "Gruvbox": {
        # Earthy retro dark — https://github.com/morhetz/gruvbox
        "app_bg": "#282828", "app_fg": "#EBDBB2",
        "accent": "#458588", "accent_hover": "#83A598", "accent_pressed": "#2D6B6E",
        "header_bg": "#3C3836", "header_fg": "#FBF1C7",
        "table_bg": "#282828", "table_alt": "#32302F",
        "border": "#504945", "status_bg": "#1D2021",
        "tab_bg": "#3C3836", "tab_selected": "#282828",
        "selection": "#504945", "input_bg": "#3C3836",
        "row_matched": "#3A5A1A", "row_not_found": "#8C3210",
        "row_missing": "#8C2840", "row_duplicate": "#6B5A10", "row_xref": "#2A5060",
        "row_owned": "#2E5C20", "row_wishlist": "#6E2860",
        "row_fail": "#581A10", "row_missing_file": "#3A2808", "row_grey": "#3C3836",
        "row_private": "#0A2A3A", "row_wrong_lb": "#2A1A3A", "row_multiple_ids": "#0A2830",
        "row_dirty": "#38320A", "row_audit": "#101A2A", "row_readonly": "#282828",
        "row_nft_missing": "#4A1808", "row_nft_stale": "#382E08", "row_nft_unknown": "#3A2008",
        "status_ok": "#1C3A10", "status_warn": "#3A3210", "status_error": "#3A1A10",
        "status_neutral": "#3C3836",
        "fg_muted": "#928374", "fg_link": "#83A598", "fg_danger": "#FB4934",
        "fg_success": "#B8BB26", "fg_warning": "#FABD2F",
    },
    "Monokai": {
        # Vivid dark — TextMate/Sublime classic
        "app_bg": "#272822", "app_fg": "#F8F8F2",
        "accent": "#66D9E8", "accent_hover": "#A6E22E", "accent_pressed": "#4BACB8",
        "header_bg": "#3E3D32", "header_fg": "#F8F8F2",
        "table_bg": "#272822", "table_alt": "#2E2E28",
        "border": "#75715E", "status_bg": "#1E1F1A",
        "tab_bg": "#3E3D32", "tab_selected": "#272822",
        "selection": "#49483E", "input_bg": "#3E3D32",
        "row_matched": "#3A6010", "row_not_found": "#8A2840",
        "row_missing": "#841A50", "row_duplicate": "#606010", "row_xref": "#285060",
        "row_owned": "#305A10", "row_wishlist": "#604A90",
        "row_fail": "#501828", "row_missing_file": "#2A1808", "row_grey": "#3E3D32",
        "row_private": "#082830", "row_wrong_lb": "#20183A", "row_multiple_ids": "#082828",
        "row_dirty": "#2E2808", "row_audit": "#101028", "row_readonly": "#2E2E28",
        "row_nft_missing": "#400A1A", "row_nft_stale": "#2A2408", "row_nft_unknown": "#301808",
        "status_ok": "#182A0A", "status_warn": "#302808", "status_error": "#3A0A20",
        "status_neutral": "#3E3D32",
        "fg_muted": "#75715E", "fg_link": "#66D9E8", "fg_danger": "#F92672",
        "fg_success": "#A6E22E", "fg_warning": "#FD971F",
    },
    "Tokyo Night": {
        # Neon city dark — https://github.com/folke/tokyonight.nvim
        "app_bg": "#1A1B26", "app_fg": "#C0CAF5",
        "accent": "#7AA2F7", "accent_hover": "#89B4FA", "accent_pressed": "#5D7FD8",
        "header_bg": "#24283B", "header_fg": "#C0CAF5",
        "table_bg": "#1A1B26", "table_alt": "#1F2335",
        "border": "#414868", "status_bg": "#13141F",
        "tab_bg": "#24283B", "tab_selected": "#1A1B26",
        "selection": "#2D3149", "input_bg": "#24283B",
        "row_matched": "#204A20", "row_not_found": "#701830",
        "row_missing": "#6E1450", "row_duplicate": "#585010", "row_xref": "#263278",
        "row_owned": "#1A4A20", "row_wishlist": "#4A2868",
        "row_fail": "#40101A", "row_missing_file": "#281C08", "row_grey": "#24283B",
        "row_private": "#0A1A30", "row_wrong_lb": "#1A1040", "row_multiple_ids": "#081A30",
        "row_dirty": "#282408", "row_audit": "#0A0A28", "row_readonly": "#1F2335",
        "row_nft_missing": "#380A12", "row_nft_stale": "#282208", "row_nft_unknown": "#281408",
        "status_ok": "#163020", "status_warn": "#2E2808", "status_error": "#2E0A18",
        "status_neutral": "#24283B",
        "fg_muted": "#565F89", "fg_link": "#7AA2F7", "fg_danger": "#F7768E",
        "fg_success": "#9ECE6A", "fg_warning": "#E0AF68",
    },
    "Solarized": {
        # Precision warm light — https://ethanschoonover.com/solarized/
        "app_bg": "#FDF6E3", "app_fg": "#586E75",
        "accent": "#268BD2", "accent_hover": "#2AA198", "accent_pressed": "#1A6DA8",
        "header_bg": "#073642", "header_fg": "#93A1A1",
        "table_bg": "#FDF6E3", "table_alt": "#EEE8D5",
        "border": "#D0CBB8", "status_bg": "#EEE8D5",
        "tab_bg": "#EEE8D5", "tab_selected": "#FDF6E3",
        "selection": "#C8DDEF", "input_bg": "#FDF6E3",
        "row_matched": "#B8E6B8", "row_not_found": "#F8C8A8",
        "row_missing": "#F8B0C0", "row_duplicate": "#F8F0A0", "row_xref": "#C8E0F8",
        "row_owned": "#C8E6C8", "row_wishlist": "#E8D8F8",
        "row_fail": "#F0C8C0", "row_missing_file": "#F0D8B0", "row_grey": "#DDD8C5",
        "row_private": "#B8DCF0", "row_wrong_lb": "#E8D0F0", "row_multiple_ids": "#B0E0F0",
        "row_dirty": "#F0ECC0", "row_audit": "#D8D8F0", "row_readonly": "#F0EBD8",
        "row_nft_missing": "#F0C0C0", "row_nft_stale": "#F0EAB8", "row_nft_unknown": "#F0D8B8",
        "status_ok": "#D0E8C8", "status_warn": "#F0E8B0", "status_error": "#F0C8C0",
        "status_neutral": "#EEE8D5",
        "fg_muted": "#93A1A1", "fg_link": "#268BD2", "fg_danger": "#DC322F",
        "fg_success": "#859900", "fg_warning": "#CB4B16",
    },
    "Everforest": {
        # Forest dark green — https://github.com/sainnhe/everforest
        "app_bg": "#2D3B2D", "app_fg": "#D5C9A0",
        "accent": "#8DA101", "accent_hover": "#A3B820", "accent_pressed": "#6A7A01",
        "header_bg": "#374535", "header_fg": "#E9DDB0",
        "table_bg": "#2D3B2D", "table_alt": "#374535",
        "border": "#4A5E48", "status_bg": "#232F22",
        "tab_bg": "#374535", "tab_selected": "#2D3B2D",
        "selection": "#3D5040", "input_bg": "#374535",
        "row_matched": "#3C6A20", "row_not_found": "#A04020",
        "row_missing": "#A03050", "row_duplicate": "#706520", "row_xref": "#2E6262",
        "row_owned": "#3A6628", "row_wishlist": "#783F65",
        "row_fail": "#542010", "row_missing_file": "#3C2808", "row_grey": "#374535",
        "row_private": "#102838", "row_wrong_lb": "#2A1A3A", "row_multiple_ids": "#0A2830",
        "row_dirty": "#363010", "row_audit": "#101C2A", "row_readonly": "#2D3B2D",
        "row_nft_missing": "#481808", "row_nft_stale": "#382C10", "row_nft_unknown": "#381E0A",
        "status_ok": "#1A3C18", "status_warn": "#3A3010", "status_error": "#3C2010",
        "status_neutral": "#374535",
        "fg_muted": "#7B8A78", "fg_link": "#8DA101", "fg_danger": "#E06C75",
        "fg_success": "#A3BE8C", "fg_warning": "#D79921",
    },
    "Catppuccin": {
        # Soft pastel dark (Mocha) — https://github.com/catppuccin/catppuccin
        "app_bg": "#1E1E2E", "app_fg": "#CDD6F4",
        "accent": "#89B4FA", "accent_hover": "#74C7EC", "accent_pressed": "#6A9CE8",
        "header_bg": "#313244", "header_fg": "#CDD6F4",
        "table_bg": "#1E1E2E", "table_alt": "#272738",
        "border": "#45475A", "status_bg": "#181825",
        "tab_bg": "#313244", "tab_selected": "#1E1E2E",
        "selection": "#313244", "input_bg": "#313244",
        "row_matched": "#1C5A28", "row_not_found": "#6A2038",
        "row_missing": "#7A1850", "row_duplicate": "#585010", "row_xref": "#283A90",
        "row_owned": "#1C4E28", "row_wishlist": "#4A2870",
        "row_fail": "#3A1020", "row_missing_file": "#281C08", "row_grey": "#313244",
        "row_private": "#0A1A30", "row_wrong_lb": "#1A0A30", "row_multiple_ids": "#081828",
        "row_dirty": "#26220A", "row_audit": "#0A0A28", "row_readonly": "#272738",
        "row_nft_missing": "#300A14", "row_nft_stale": "#28200A", "row_nft_unknown": "#261408",
        "status_ok": "#1A3A28", "status_warn": "#2E2A08", "status_error": "#2E0A18",
        "status_neutral": "#313244",
        "fg_muted": "#6C7086", "fg_link": "#89B4FA", "fg_danger": "#F38BA8",
        "fg_success": "#A6E3A1", "fg_warning": "#FAB387",
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
    ("Row: Owned",           "row_owned"),
    ("Row: Wishlist",        "row_wishlist"),
    ("Row: Fail/Bad",        "row_fail"),
    ("Row: Missing File",    "row_missing_file"),
    ("Row: Neutral/N/A",     "row_grey"),
    ("Row: Private LB",      "row_private"),
    ("Row: Wrong LB",        "row_wrong_lb"),
    ("Row: Multiple IDs",    "row_multiple_ids"),
    ("Row: Dirty/Unsaved",   "row_dirty"),
    ("Row: Audit/System",    "row_audit"),
    ("Row: Read-only",       "row_readonly"),
    ("Row: NFT Missing",     "row_nft_missing"),
    ("Row: NFT Stale",       "row_nft_stale"),
    ("Row: NFT Unknown",     "row_nft_unknown"),
    ("Status: OK",           "status_ok"),
    ("Status: Warning",      "status_warn"),
    ("Status: Error",        "status_error"),
    ("Status: Neutral",      "status_neutral"),
    ("Text: Muted",          "fg_muted"),
    ("Text: Link",           "fg_link"),
    ("Text: Danger",         "fg_danger"),
    ("Text: Success",        "fg_success"),
    ("Text: Warning",        "fg_warning"),
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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ── Preset list ───────────────────────────────────────────────────────
        preset_panel = QWidget()
        preset_panel.setFixedWidth(130)
        preset_layout = QVBoxLayout(preset_panel)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.addWidget(QLabel(self.tr("Presets")))

        self.theme_list = QListWidget()
        for name in list(THEMES.keys()) + ["Custom"]:
            self.theme_list.addItem(QListWidgetItem(name))
        self.theme_list.currentTextChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.theme_list)
        layout.addWidget(preset_panel)

        # ── Swatches panel (2-column grid) ────────────────────────────────────
        swatch_panel = QWidget()
        swatch_panel_layout = QVBoxLayout(swatch_panel)
        swatch_panel_layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(self.tr("Click any color swatch to customize. Changes become Custom."))
        hint.setWordWrap(True)
        swatch_panel_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        swatch_container = QWidget()
        grid = QGridLayout(swatch_container)
        grid.setVerticalSpacing(5)
        grid.setHorizontalSpacing(14)
        # 4 grid columns: label-A | swatch-A | label-B | swatch-B
        grid.setColumnStretch(0, 1)
        grid.setColumnMinimumWidth(1, 110)
        grid.setColumnStretch(2, 1)
        grid.setColumnMinimumWidth(3, 110)

        num_rows = (len(COLOR_LABELS) + 1) // 2
        for i, (label_text, key) in enumerate(COLOR_LABELS):
            row = i % num_rows
            col_base = (i // num_rows) * 2  # 0 for left column, 2 for right column
            grid.addWidget(QLabel(self.tr(label_text)), row, col_base, Qt.AlignmentFlag.AlignRight)
            btn = QPushButton()
            btn.setFixedHeight(22)
            btn.setMinimumWidth(110)
            btn.clicked.connect(lambda checked, k=key: self._on_swatch_clicked(k))
            self._swatches[key] = btn
            grid.addWidget(btn, row, col_base + 1)

        scroll.setWidget(swatch_container)
        swatch_panel_layout.addWidget(scroll)

        # ── Font settings ──────────────────────────────────────────────────────
        _FONT_OPTIONS = [
            ("System default",  ""),
            ("Cantarell",       "Cantarell"),
            ("DejaVu Sans",     "DejaVu Sans"),
            ("Liberation Sans", "Liberation Sans"),
            ("Noto Sans",       "Noto Sans"),
            ("Ubuntu",          "Ubuntu"),
            ("Arial",           "Arial"),
        ]
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel(self.tr("Font:")))
        self._font_family_combo = QComboBox()
        for display, family in _FONT_OPTIONS:
            self._font_family_combo.addItem(self.tr(display), userData=family)
        font_row.addWidget(self._font_family_combo)
        font_row.addWidget(QLabel(self.tr("Size:")))
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 14)
        self._font_size_spin.setValue(9)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setFixedWidth(70)
        font_row.addWidget(self._font_size_spin)
        font_row.addStretch()
        swatch_panel_layout.addLayout(font_row)

        self.apply_btn = QPushButton(self.tr("Apply Theme"))
        self.apply_btn.clicked.connect(self._on_apply)
        swatch_panel_layout.addWidget(self.apply_btn)

        self.status_label = QLabel("")
        swatch_panel_layout.addWidget(self.status_label)

        layout.addWidget(swatch_panel)
        layout.addStretch()

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
        color = QColorDialog.getColor(initial, self, self.tr("Choose color"))
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
        font_family = self._font_family_combo.currentData()
        font_size = self._font_size_spin.value()
        styles.apply_theme(self._current, font_family=font_family, font_size=font_size)
        self._save_settings()
        self.theme_applied.emit()
        self.status_label.setText(self.tr("Theme applied."))

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_settings(self):
        s = QSettings(_SETTINGS_GROUP, _SETTINGS_GROUP)
        name = self.theme_list.currentItem().text() if self.theme_list.currentItem() else "Light"
        s.setValue("theme/name", name)
        for _, key in COLOR_LABELS:
            s.setValue(f"theme/color/{key}", self._current.get(key, ""))
        s.setValue("theme/font_family", self._font_family_combo.currentData() or "")
        s.setValue("theme/font_size",   self._font_size_spin.value())

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

        saved_family = s.value("theme/font_family", "")
        saved_size   = max(8, min(14, int(s.value("theme/font_size", 9))))
        matched_idx = 0
        for i in range(self._font_family_combo.count()):
            if self._font_family_combo.itemData(i) == saved_family:
                matched_idx = i
                break
        self._font_family_combo.setCurrentIndex(matched_idx)
        self._font_size_spin.setValue(saved_size)

        self._refresh_swatches()
        self._on_apply()
