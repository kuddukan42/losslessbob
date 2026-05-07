import csv
import re
import subprocess
import webbrowser
from pathlib import Path

import requests
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QThread, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableView, QPushButton,
    QLabel, QLineEdit, QAbstractItemView, QHeaderView, QMenu, QDialog,
    QFormLayout, QDialogButtonBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QSizePolicy,
)

from gui.styles import ROW_OWNED

_LB_RE = re.compile(r'LB-0*(\d+)', re.IGNORECASE)

COLL_HEADERS = ["LB Number", "Date", "Location", "Folder Name", "Disk Path", "Confirmed", "Notes"]
MISS_HEADERS = ["LB Number", "Date", "Location", "Rating", "Description"]


def _extract_lb(name):
    m = _LB_RE.search(name)
    return int(m.group(1)) if m else None


class _CollectionModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._all_rows = []
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLL_HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{row['lb_number']}"
            if col == 1:
                return row.get("date_str") or ""
            if col == 2:
                return row.get("location") or ""
            if col == 3:
                return row.get("folder_name", "")
            if col == 4:
                return row.get("disk_path", "")
            if col == 5:
                v = row.get("confirmed_at", "") or ""
                return str(v)[:10]
            if col == 6:
                return row.get("notes", "") or ""
        if role == Qt.ItemDataRole.FontRole and col in (1, 2):
            val = row.get("date_str") if col == 1 else row.get("location")
            if not val:
                f = QFont()
                f.setItalic(True)
                return f
        if role == Qt.ItemDataRole.ForegroundRole and col in (1, 2):
            val = row.get("date_str") if col == 1 else row.get("location")
            if not val:
                return QColor("#888888")
        if role == Qt.ItemDataRole.BackgroundRole:
            return ROW_OWNED
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLL_HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._all_rows = rows
        self._rows = rows
        self.endResetModel()

    def filter(self, text):
        self.beginResetModel()
        if not text:
            self._rows = self._all_rows
        else:
            t = text.lower()
            self._rows = [
                r for r in self._all_rows
                if t in str(r.get("lb_number", "")).lower()
                or t in (r.get("folder_name", "") or "").lower()
                or t in (r.get("disk_path", "") or "").lower()
            ]
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None


class _MissingModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(MISS_HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"LB-{row.get('lb_number', '')}"
            keys = ["lb_number", "date_str", "location", "rating", "description"]
            val = row.get(keys[col], "") or ""
            if col == 4:
                return str(val)[:120] + ("..." if len(str(val)) > 120 else "")
            return str(val)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return MISS_HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None

    def all_rows(self):
        return list(self._rows)


class _ApiWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


class _AddDialog(QDialog):
    def __init__(self, lb_number=None, folder_name="", disk_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add to My Collection")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.lb_edit = QLineEdit(str(lb_number) if lb_number is not None else "")
        self.folder_edit = QLineEdit(folder_name)
        self.path_edit = QLineEdit(disk_path)
        self.notes_edit = QLineEdit()
        layout.addRow("LB Number:", self.lb_edit)
        layout.addRow("Folder Name:", self.folder_edit)
        layout.addRow("Disk Path:", self.path_edit)
        layout.addRow("Notes:", self.notes_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_values(self):
        try:
            lb = int(self.lb_edit.text().strip())
        except ValueError:
            lb = None
        return {
            "lb_number": lb,
            "folder_name": self.folder_edit.text().strip(),
            "disk_path": self.path_edit.text().strip(),
            "notes": self.notes_edit.text().strip() or None,
        }


class _ScanPreviewDialog(QDialog):
    def __init__(self, entries, owned_set, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Results — Confirm Add")
        self.setMinimumSize(700, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Found {len(entries)} folder(s) with LB numbers:"))

        self.table = QTableWidget(len(entries), 4)
        self.table.setHorizontalHeaderLabels(["LB Number", "Folder Name", "Path", "Already Owned"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, (lb, name, path) in enumerate(entries):
            owned = lb in owned_set
            self.table.setItem(i, 0, QTableWidgetItem(f"LB-{lb}"))
            self.table.setItem(i, 1, QTableWidgetItem(name))
            self.table.setItem(i, 2, QTableWidgetItem(path))
            item = QTableWidgetItem("Yes" if owned else "No")
            if owned:
                item.setForeground(QColor("#388E3C"))
            self.table.setItem(i, 3, item)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)

        skipped = getattr(self, '_skipped', 0)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Add All")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


class CollectionTab(QWidget):
    lookup_lb = pyqtSignal(int)

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._workers = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inner_tabs = QTabWidget()
        layout.addWidget(self.inner_tabs)
        self.inner_tabs.addTab(self._build_collection_panel(), "My Collection")
        self.inner_tabs.addTab(self._build_missing_panel(), "Missing")

    # ── My Collection panel ───────────────────────────────────────────────────

    def _build_collection_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        # Search bar
        search_row = QHBoxLayout()
        self.coll_search = QLineEdit()
        self.coll_search.setPlaceholderText("Filter by LB number, folder name, or path…")
        self.coll_search.textChanged.connect(self._on_coll_filter)
        search_row.addWidget(self.coll_search)
        layout.addLayout(search_row)

        # Button row
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Single Folder")
        add_btn.clicked.connect(self._on_add_single)
        btn_row.addWidget(add_btn)

        scan_btn = QPushButton("Scan Directory")
        scan_btn.clicked.connect(self._on_scan_directory)
        btn_row.addWidget(scan_btn)

        self.update_loc_btn = QPushButton("Update Location")
        self.update_loc_btn.clicked.connect(self._on_update_location)
        btn_row.addWidget(self.update_loc_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(self.remove_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_collection)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.coll_model = _CollectionModel()
        self.coll_view = QTableView()
        self.coll_view.setModel(self.coll_model)
        self.coll_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.coll_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.coll_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.coll_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.coll_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.coll_view.customContextMenuRequested.connect(self._on_coll_context)
        layout.addWidget(self.coll_view)

        self.coll_status = QLabel("")
        layout.addWidget(self.coll_status)
        return w

    # ── Missing panel ─────────────────────────────────────────────────────────

    def _build_missing_panel(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_missing)
        btn_row.addWidget(refresh_btn)

        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._on_export_csv)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.miss_model = _MissingModel()
        self.miss_view = QTableView()
        self.miss_view.setModel(self.miss_model)
        self.miss_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.miss_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.miss_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.miss_view.doubleClicked.connect(self._on_missing_double_click)
        layout.addWidget(self.miss_view)

        self.miss_status = QLabel("")
        layout.addWidget(self.miss_status)
        return w

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh_collection(self):
        self.coll_status.setText("Loading…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/collection", timeout=15
        ).json())
        w.finished.connect(self._on_collection_loaded)
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_collection_loaded(self, data):
        if isinstance(data, list):
            self.coll_model.set_rows(data)
            self.coll_view.resizeColumnsToContents()
            self.coll_status.setText(f"{len(data)} item(s) in collection.")
        else:
            self.coll_status.setText(f"Error: {data.get('error', 'unknown')}")

    def refresh_missing(self):
        self.miss_status.setText("Loading…")
        w = _ApiWorker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/collection/missing", timeout=15
        ).json())
        w.finished.connect(self._on_missing_loaded)
        w.error.connect(lambda e: self.miss_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_missing_loaded(self, data):
        if isinstance(data, list):
            self.miss_model.set_rows(data)
            self.miss_view.resizeColumnsToContents()
            self.miss_status.setText(f"{len(data)} missing from collection.")
        else:
            self.miss_status.setText(f"Error: {data.get('error', 'unknown')}")

    # ── Collection filter ─────────────────────────────────────────────────────

    def _on_coll_filter(self, text):
        self.coll_model.filter(text)

    # ── Add Single Folder ─────────────────────────────────────────────────────

    def _on_add_single(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not path:
            return
        folder = Path(path)
        lb_number = _extract_lb(folder.name)
        dlg = _AddDialog(lb_number, folder.name, str(folder), parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if not vals["lb_number"]:
            QMessageBox.warning(self, "Invalid", "LB Number is required and must be an integer.")
            return
        self._post_collection(vals)

    def _post_collection(self, vals):
        def call():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/collection",
                json=vals, timeout=10,
            ).json()
        w = _ApiWorker(call)
        w.finished.connect(lambda r: self._on_post_done(r, 1, 0))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_post_done(self, result, added, skipped):
        if isinstance(result, dict) and result.get("error"):
            self.coll_status.setText(f"Error: {result['error']}")
        else:
            self.coll_status.setText(f"Added: {added}, already existed: {skipped}.")
            self.refresh_collection()

    # ── Scan Directory ────────────────────────────────────────────────────────

    def _on_scan_directory(self):
        root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Scan")
        if not root:
            return
        root_path = Path(root)
        entries = []
        skipped = 0
        for child in sorted(root_path.iterdir()):
            if not child.is_dir():
                continue
            lb = _extract_lb(child.name)
            if lb is not None:
                entries.append((lb, child.name, str(child)))
            else:
                skipped += 1

        if not entries:
            QMessageBox.information(self, "Scan", f"No folders with LB numbers found.\n{skipped} folder(s) skipped.")
            return

        try:
            owned_resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/collection/lb_numbers", timeout=10
            )
            owned_set = set(owned_resp.json())
        except Exception:
            owned_set = set()

        dlg = _ScanPreviewDialog(entries, owned_set, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._bulk_add(entries, skipped)

    def _bulk_add(self, entries, skipped_count):
        flask_port = self.flask_port

        def call():
            added = 0
            already = 0
            for lb, name, path in entries:
                resp = requests.post(
                    f"http://127.0.0.1:{flask_port}/api/collection",
                    json={"lb_number": lb, "folder_name": name, "disk_path": path},
                    timeout=10,
                ).json()
                if resp.get("added"):
                    added += 1
                else:
                    already += 1
            return {"added": added, "already": already, "skipped": skipped_count}

        w = _ApiWorker(call)
        w.finished.connect(lambda r: self._on_bulk_done(r))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()
        self.coll_status.setText("Adding…")

    def _on_bulk_done(self, result):
        self.coll_status.setText(
            f"Added: {result['added']}, already existed: {result['already']}, "
            f"skipped (no LB): {result['skipped']}."
        )
        self.refresh_collection()

    # ── Update Location ───────────────────────────────────────────────────────

    def _on_update_location(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more rows to update.")
            return

        if len(rows) == 1:
            row = rows[0]
            path = QFileDialog.getExistingDirectory(self, "Select New Folder Location")
            if not path:
                return
            folder = Path(path)
            self._patch_collection(row["lb_number"], {
                "disk_path": str(folder),
                "folder_name": folder.name,
            })
        else:
            root = QFileDialog.getExistingDirectory(self, "Select Root Directory to Search")
            if not root:
                return
            root_path = Path(root)
            updated = 0
            not_found = []
            for row in rows:
                folder_name = row.get("folder_name", "")
                candidate = root_path / folder_name
                if not candidate.is_dir():
                    # Case-insensitive fallback
                    candidate = next(
                        (c for c in root_path.iterdir()
                         if c.is_dir() and c.name.lower() == folder_name.lower()),
                        None,
                    )
                if candidate:
                    self._patch_collection(row["lb_number"], {
                        "disk_path": str(candidate),
                        "folder_name": candidate.name,
                    })
                    updated += 1
                else:
                    not_found.append(f"LB-{row['lb_number']}")
            msg = f"Updated: {updated}."
            if not_found:
                msg += f" Not found: {', '.join(not_found)}."
            self.coll_status.setText(msg)
            self.refresh_collection()

    def _patch_collection(self, lb_number, fields):
        def call():
            return requests.patch(
                f"http://127.0.0.1:{self.flask_port}/api/collection/{lb_number}",
                json=fields, timeout=10,
            ).json()
        w = _ApiWorker(call)
        w.finished.connect(lambda _: self.refresh_collection())
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Remove ────────────────────────────────────────────────────────────────

    def _on_remove(self):
        rows = self._selected_rows()
        if not rows:
            self.coll_status.setText("Select one or more rows to remove.")
            return
        confirm = QMessageBox.question(
            self, "Confirm Remove",
            f"Remove {len(rows)} item(s) from My Collection?\n(Files are not deleted.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for row in rows:
            lb = row["lb_number"]
            w = _ApiWorker(lambda lb=lb: requests.delete(
                f"http://127.0.0.1:{self.flask_port}/api/collection/{lb}", timeout=10
            ).json())
            self._workers.append(w)
            w.start()
        self.coll_status.setText(f"Removed {len(rows)} item(s).")
        self.refresh_collection()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_coll_context(self, pos):
        index = self.coll_view.indexAt(pos)
        menu = QMenu(self)

        rows = self._selected_rows()
        if rows:
            open_act = QAction("Open Folder", self)
            open_act.triggered.connect(lambda: self._open_folders(rows))
            menu.addAction(open_act)

        if index.isValid():
            row = self.coll_model.get_row(index.row())
            if row:
                lb = row["lb_number"]
                view_act = QAction("View LB Entry", self)
                url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
                view_act.triggered.connect(lambda: webbrowser.open(url))
                menu.addAction(view_act)

                scrape_act = QAction("Scrape Entry", self)
                scrape_act.triggered.connect(lambda: self._scrape_entry(lb))
                menu.addAction(scrape_act)

                upd_act = QAction("Update Location", self)
                upd_act.triggered.connect(self._on_update_location)
                menu.addAction(upd_act)

        if not menu.isEmpty():
            menu.exec(self.coll_view.mapToGlobal(pos))

    def _open_folders(self, rows):
        for row in rows:
            path = row.get("disk_path", "")
            if path and Path(path).is_dir():
                try:
                    subprocess.Popen(["xdg-open", path])
                except Exception:
                    pass

    def _scrape_entry(self, lb_number):
        self.coll_status.setText(f"Scraping LB-{lb_number}…")
        w = _ApiWorker(lambda: requests.post(
            f"http://127.0.0.1:{self.flask_port}/api/entry/{lb_number}/scrape",
            timeout=60,
        ).json())
        w.finished.connect(lambda _: (
            self.coll_status.setText(f"Scraped LB-{lb_number}."),
            self.refresh_collection(),
        ))
        w.error.connect(lambda e: self.coll_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Missing: double-click & export ────────────────────────────────────────

    def _on_missing_double_click(self, index):
        row = self.miss_model.get_row(index.row())
        if row:
            self.lookup_lb.emit(row["lb_number"])

    def _on_export_csv(self):
        rows = self.miss_model.all_rows()
        if not rows:
            self.miss_status.setText("Nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Missing as CSV", "missing_from_collection.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=MISS_HEADERS)
                writer.writeheader()
                for r in rows:
                    writer.writerow({
                        "LB Number": f"LB-{r.get('lb_number', '')}",
                        "Date": r.get("date_str", ""),
                        "Location": r.get("location", ""),
                        "Rating": r.get("rating", ""),
                        "Description": r.get("description", ""),
                    })
            self.miss_status.setText(f"Exported {len(rows)} rows to {Path(path).name}.")
        except Exception as e:
            self.miss_status.setText(f"Export error: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _selected_rows(self):
        seen = set()
        rows = []
        for idx in self.coll_view.selectedIndexes():
            r = idx.row()
            if r not in seen:
                seen.add(r)
                row = self.coll_model.get_row(r)
                if row:
                    rows.append(row)
        return rows
