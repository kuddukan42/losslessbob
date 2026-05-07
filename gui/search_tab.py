import webbrowser

import requests
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QThread
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QTableView, QAbstractItemView, QHeaderView, QLabel,
)

HEADERS = ["LB Number", "Date", "Location", "Rating", "Description", "Owned"]


class SearchModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []
        self._owned = set()

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
            keys = ["lb_number", "date_str", "location", "rating", "description"]
            if col == 0:
                return f"LB-{row.get('lb_number', '')}"
            if col == 4:
                val = row.get("description", "") or ""
                return str(val)[:120] + ("..." if len(str(val)) > 120 else "")
            if col == 5:
                return "✓" if row.get("lb_number") in self._owned else ""
            val = row.get(keys[col], "")
            return str(val) if val else ""
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.get("lb_number") in self._owned:
                from gui.styles import ROW_OWNED
                return ROW_OWNED
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 5:
            return Qt.AlignmentFlag.AlignCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def set_owned(self, owned_set):
        self._owned = owned_set
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, len(HEADERS) - 1),
            )

    def get_lb(self, row_idx):
        if 0 <= row_idx < len(self._rows):
            return self._rows[row_idx].get("lb_number")
        return None


class _SearchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, flask_port, query, field, year=None):
        super().__init__()
        self.flask_port = flask_port
        self.query = query
        self.field = field
        self.year = year

    def run(self):
        try:
            params = {"q": self.query, "field": self.field}
            if self.year is not None:
                params["year"] = self.year
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/search",
                params=params,
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _YearsWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/search/years",
                timeout=10,
            )
            self.finished.emit(resp.json())
        except Exception:
            self.finished.emit([])


class _OwnedWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/collection/lb_numbers",
                timeout=10,
            )
            self.finished.emit(resp.json())
        except Exception:
            self.finished.emit([])


class SearchTab(QWidget):
    lookup_lb = pyqtSignal(int)

    def __init__(self, flask_port, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._worker = None
        self._years_worker = None
        self._owned_worker = None
        self._build_ui()
        self.load_years()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search...")
        self.search_field.returnPressed.connect(self._do_search)
        search_row.addWidget(self.search_field)

        self.field_combo = QComboBox()
        self.field_combo.addItems(["All Fields", "Location", "Date", "Description"])
        search_row.addWidget(self.field_combo)

        self.year_combo = QComboBox()
        self.year_combo.setMinimumWidth(90)
        self.year_combo.addItem("All Years", userData=None)
        self.year_combo.currentIndexChanged.connect(self._do_search)
        search_row.addWidget(self.year_combo)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)
        layout.addLayout(search_row)

        self.results_label = QLabel("")
        layout.addWidget(self.results_label)

        self.model = SearchModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.view)

    def load_years(self):
        self._years_worker = _YearsWorker(self.flask_port)
        self._years_worker.finished.connect(self._on_years_loaded)
        self._years_worker.start()

    def _on_years_loaded(self, years):
        current_year = self.year_combo.currentData()
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItem("All Years", userData=None)
        for y in years:
            self.year_combo.addItem(str(y), userData=y)
        # Restore selection if possible
        if current_year is not None:
            idx = self.year_combo.findData(current_year)
            if idx >= 0:
                self.year_combo.setCurrentIndex(idx)
        self.year_combo.blockSignals(False)

    def _do_search(self):
        q = self.search_field.text().strip()
        field_map = {
            "All Fields": "all",
            "Location": "location",
            "Date": "date",
            "Description": "description",
        }
        field = field_map.get(self.field_combo.currentText(), "all")
        year = self.year_combo.currentData()
        self.search_btn.setEnabled(False)
        self.results_label.setText("Searching...")

        self._worker = _SearchWorker(self.flask_port, q, field, year=year)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, results):
        self.search_btn.setEnabled(True)
        self.model.set_rows(results)
        self.view.resizeColumnsToContents()
        self.results_label.setText(f"{len(results)} result(s) found.")
        # Fetch owned set and mark rows
        self._owned_worker = _OwnedWorker(self.flask_port)
        self._owned_worker.finished.connect(lambda lbs: self.model.set_owned(set(lbs)))
        self._owned_worker.start()

    def _on_error(self, msg):
        self.search_btn.setEnabled(True)
        self.results_label.setText(f"Error: {msg}")

    def _on_double_click(self, index):
        lb = self.model.get_lb(index.row())
        if lb is None:
            return
        if index.column() == 0:
            self.lookup_lb.emit(lb)
        else:
            url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb}.html"
            webbrowser.open(url)
