import os
import re
import shutil
import webbrowser
from pathlib import Path

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton,
    QAbstractItemView, QHeaderView, QMessageBox, QMenu, QLabel,
)

HEADERS = ["Rename", "Current Folder Name", "Proposed New Name", "LB Found", "Reason"]

# Row states → background colors
_STATE_COLORS = {
    "has_lb":       QColor("#C8E6C9"),  # green  — LB already in folder name
    "renamed":      QColor("#C8E6C9"),  # green  — just renamed
    "needs_rename": QColor("#FFE0B2"),  # orange — match found but not yet renamed
    "wrong_lb":     QColor("#E1BEE7"),  # purple — folder has a different LB number
    "no_match":     QColor("#FFCDD2"),  # red    — no match or multiple IDs
}


def _lb_in_name(folder_name, lb_str):
    if not lb_str or lb_str == "—" or "," in lb_str:
        return False
    m = re.search(r'LB-0*(\d+)', lb_str, re.IGNORECASE)
    if not m:
        return False
    lb_num = int(m.group(1))
    m2 = re.search(r'LB-0*(\d+)', folder_name, re.IGNORECASE)
    return bool(m2 and int(m2.group(1)) == lb_num)


def _has_wrong_lb(folder_name, lb_str):
    """True when folder_name contains an LB number that differs from lb_str."""
    if not lb_str or lb_str == "—" or "," in lb_str:
        return False
    m = re.search(r'LB-0*(\d+)', lb_str, re.IGNORECASE)
    if not m:
        return False
    lb_num = int(m.group(1))
    m2 = re.search(r'LB-0*(\d+)', folder_name, re.IGNORECASE)
    return bool(m2 and int(m2.group(1)) != lb_num)


def _strip_lb_from_name(name):
    """Remove LB-NNNN (and surrounding separators) from a folder name."""
    cleaned = re.sub(r'[\-_. ]+LB-\d+', '', name, flags=re.IGNORECASE)
    if cleaned == name:
        cleaned = re.sub(r'LB-\d+[\-_. ]*', '', name, flags=re.IGNORECASE)
    return cleaned.strip('-_. ')


def _row_state(folder_path, lb_str):
    if lb_str == "—" or "," in lb_str:
        return "no_match"
    folder_name = Path(folder_path).name
    if _lb_in_name(folder_name, lb_str):
        return "has_lb"
    if _has_wrong_lb(folder_name, lb_str):
        return "wrong_lb"
    return "needs_rename"


class RenameModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []
        self._states = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return ""
            return str(row[col])
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if row[0] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole:
            state = self._states[index.row()] if index.row() < len(self._states) else None
            return _STATE_COLORS.get(state)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self._rows[index.row()][0] = (value == Qt.CheckState.Checked)
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        base = super().flags(index)
        if index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def set_rows(self, rows, states=None):
        self.beginResetModel()
        self._rows = rows
        self._states = states or ["no_match"] * len(rows)
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None

    def update_row_after_rename(self, idx, new_path):
        if 0 <= idx < len(self._rows):
            self._rows[idx][0] = False
            self._rows[idx][1] = new_path
            self._rows[idx][2] = new_path
            self._rows[idx][4] = "Renamed"
            self._states[idx] = "renamed"
            self.dataChanged.emit(
                self.index(idx, 0),
                self.index(idx, len(HEADERS) - 1),
            )

    def check_all(self, checked):
        for row in self._rows:
            row[0] = checked
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0)
            )

    def check_actionable(self):
        """Check only rows that can actually be renamed."""
        _actionable = {"needs_rename", "wrong_lb"}
        for i, row in enumerate(self._rows):
            row[0] = (i < len(self._states) and self._states[i] in _actionable)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0))

    def check_by_state(self, state):
        """Check only rows whose state matches; uncheck all others."""
        for i, row in enumerate(self._rows):
            row[0] = (i < len(self._states) and self._states[i] == state)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0))

    def get_state(self, idx):
        return self._states[idx] if 0 <= idx < len(self._states) else None

    def update_proposed_name(self, idx, new_proposed, new_reason=None):
        if 0 <= idx < len(self._rows):
            self._rows[idx][2] = new_proposed
            if new_reason is not None:
                self._rows[idx][4] = new_reason
            self.dataChanged.emit(self.index(idx, 2), self.index(idx, 4))


class RenameTab(QWidget):
    jump_to_lookup = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel("Populate the Lookup listbox and run a lookup, then switch here to rename folders.")
        layout.addWidget(self.info_label)

        self.model = RenameModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.setColumnWidth(0, 50)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context)
        layout.addWidget(self.view)

        # Legend
        legend_row = QHBoxLayout()
        for color, text in [
            ("#C8E6C9", "LB found in name / renamed"),
            ("#FFE0B2", "Match found — rename suggested"),
            ("#E1BEE7", "Wrong LB in name — strip needed"),
            ("#FFCDD2", "No match or multiple IDs"),
        ]:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {color}; border: 1px solid #999;")
            legend_row.addWidget(swatch)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(12)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        btn_row = QHBoxLayout()
        self.rename_btn = QPushButton("Rename Selected")
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.rename_btn)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.model.check_actionable)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(lambda: self.model.check_all(False))
        btn_row.addWidget(self.deselect_all_btn)

        self.select_wrong_lb_btn = QPushButton("Select Wrong LB")
        self.select_wrong_lb_btn.clicked.connect(lambda: self.model.check_by_state("wrong_lb"))
        btn_row.addWidget(self.select_wrong_lb_btn)

        self.strip_wrong_lb_btn = QPushButton("Strip Wrong LB from Selected")
        self.strip_wrong_lb_btn.clicked.connect(self._on_strip_wrong_lb)
        btn_row.addWidget(self.strip_wrong_lb_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def populate_from_lookup(self, detail_list, listbox_folders):
        lb_by_folder = {}
        for d in detail_list:
            if d.get("lb_number") and d.get("source_file"):
                folder = str(Path(d["source_file"]).parent)
                lb_by_folder.setdefault(folder, set()).add(d["lb_number"])

        rows = []
        states = []
        for folder in listbox_folders:
            folder_path = Path(folder)
            if not folder_path.is_dir():
                continue
            lbs = lb_by_folder.get(folder, set())
            if not lbs:
                reason = "No match"
                proposed = folder_path.name
                lb_str = "—"
            elif len(lbs) > 1:
                reason = "Multiple IDs"
                proposed = folder_path.name
                lb_str = ", ".join(f"LB-{n}" for n in sorted(lbs))
            else:
                lb = next(iter(lbs))
                lb_str = f"LB-{lb}"
                if _lb_in_name(folder_path.name, lb_str):
                    proposed = folder_path.name
                    reason = "LB already in name"
                elif _has_wrong_lb(folder_path.name, lb_str):
                    proposed = f"{folder_path.name}-LB-{lb}"
                    reason = "Wrong LB in name"
                else:
                    proposed = f"{folder_path.name}-LB-{lb}"
                    reason = "Complete match"
            rows.append([True, folder, str(folder_path.parent / proposed), lb_str, reason])
            states.append(_row_state(folder, lb_str))

        self.model.set_rows(rows, states)
        self.view.resizeColumnsToContents()
        self.info_label.setText(f"{len(rows)} folders ready for rename review.")

    def _on_rename(self):
        to_rename = [
            (i, self.model.get_row(i))
            for i in range(self.model.rowCount())
            if self.model.get_row(i) and self.model.get_row(i)[0]
        ]
        if not to_rename:
            self.status_label.setText("No folders selected.")
            return

        confirm = QMessageBox.question(
            self, "Confirm Rename",
            f"Rename {len(to_rename)} folder(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        done = 0
        errors = []
        for idx, row in to_rename:
            src, proposed_dst = row[1], row[2]
            new_name = Path(proposed_dst).name
            processed_dir = os.path.join(str(Path(src).parent), "0. Processed")
            final_dst = os.path.join(processed_dir, new_name)
            if src == final_dst:
                self.model.update_row_after_rename(idx, final_dst)
                done += 1
                continue
            try:
                os.makedirs(processed_dir, exist_ok=True)
                shutil.move(src, final_dst)
                self.model.update_row_after_rename(idx, final_dst)
                done += 1
            except Exception as e:
                errors.append(f"{Path(src).name}: {e}")

        msg = f"Renamed {done} folder(s)."
        if errors:
            msg += f" {len(errors)} error(s): " + "; ".join(errors[:3])
        self.status_label.setText(msg)

    def _on_strip_wrong_lb(self):
        changed = 0
        for i in range(self.model.rowCount()):
            row = self.model.get_row(i)
            if not row or not row[0]:
                continue
            if self.model.get_state(i) != "wrong_lb":
                continue
            lb_str = row[3]
            m = re.search(r'LB-0*(\d+)', lb_str, re.IGNORECASE)
            if not m:
                continue
            lb_num = int(m.group(1))
            folder_path = Path(row[1])
            clean_name = _strip_lb_from_name(folder_path.name)
            new_proposed = str(folder_path.parent / f"{clean_name}-LB-{lb_num}")
            self.model.update_proposed_name(i, new_proposed, "Strip & rename")
            changed += 1
        if changed:
            self.status_label.setText(
                f"Updated proposed name for {changed} folder(s). Click Rename Selected to apply."
            )
        else:
            self.status_label.setText("No checked wrong-LB rows to strip.")

    def _on_context(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        row = self.model.get_row(index.row())
        if not row:
            return

        menu = QMenu(self)
        col = index.column()

        if col == 4:
            jump = QAction("Jump to Lookup Detail", self)
            jump.triggered.connect(lambda: self.jump_to_lookup.emit(row[1]))
            menu.addAction(jump)
        else:
            lb_str = row[3]
            if lb_str.startswith("LB-") and "," not in lb_str:
                try:
                    lb_num = int(lb_str.replace("LB-", ""))
                    open_web = QAction(f"Open {lb_str} in Browser", self)
                    url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
                    open_web.triggered.connect(lambda: webbrowser.open(url))
                    menu.addAction(open_web)
                except ValueError:
                    pass

        menu.exec(self.view.mapToGlobal(pos))
