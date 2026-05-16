import math
import webbrowser

import requests
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QThread, QSettings
import gui.styles as styles
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QTableView, QAbstractItemView, QHeaderView, QLabel, QCheckBox,
    QMenu, QInputDialog,
)

_DESC_COL = 4          # index of the Description column
_DESC_DEFAULT_W = 600  # default width for Description in pixels
_QSETTINGS_ORG = "LosslessBob"
_QSETTINGS_APP = "SearchTab"
_QSETTINGS_COL_KEY = "col_widths"

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
                return str(val)
            if col == 5:
                return "✓" if row.get("lb_number") in self._owned else ""
            val = row.get(keys[col], "")
            return str(val) if val else ""
        if role == Qt.ItemDataRole.BackgroundRole:
            if row.get("status") == "missing":
                return styles.ROW_MISSING
            if row.get("lb_number") in self._owned:
                return styles.ROW_OWNED
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


class _XrefWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/checksums/xref_lb_numbers",
                timeout=15,
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
        self._xref_worker = None
        self._all_results: list = []
        self._xref_lb_numbers: set = set()
        self._show_missing_only: bool = False
        self._page: int = 0
        self._page_size: int = 50
        self._resizing_programmatically: bool = False
        self._qsettings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        self._col_widths: list | None = self._load_col_widths()
        self._load_page_size()
        self._build_ui()
        self.load_years()
        self._load_xref_lb_numbers()

    def _load_page_size(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/db/settings", timeout=5
            )
            data = resp.json()
            self._page_size = int(data.get("search_page_size") or 50)
        except Exception:
            pass

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

        self._missing_only_cb = QCheckBox("Missing only")
        self._missing_only_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._missing_only_cb)

        self._owned_only_cb = QCheckBox("Owned only")
        self._owned_only_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._owned_only_cb)

        self._not_owned_cb = QCheckBox("Not owned")
        self._not_owned_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._not_owned_cb)

        self._xref_only_cb = QCheckBox("Xref only")
        self._xref_only_cb.setToolTip(
            "Show only entries that have cross-reference (xref) alternate versions in the DB."
        )
        self._xref_only_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._xref_only_cb)

        self._wrap_cb = QCheckBox("Word wrap")
        self._wrap_cb.stateChanged.connect(self._on_wrap_toggled)
        search_row.addWidget(self._wrap_cb)

        layout.addLayout(search_row)

        self.results_label = QLabel("")
        layout.addWidget(self.results_label)

        # Pagination controls — hidden until results span more than one page
        page_row = QHBoxLayout()
        self._prev_btn = QPushButton("← Prev")
        self._prev_btn.setFixedWidth(80)
        self._prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self._prev_btn)
        self._page_label = QLabel("Page 1 of 1")
        page_row.addWidget(self._page_label)
        self._next_btn = QPushButton("Next →")
        self._next_btn.setFixedWidth(80)
        self._next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self._next_btn)
        page_row.addStretch()
        self._page_widget = QWidget()
        self._page_widget.setLayout(page_row)
        self._page_widget.setVisible(False)
        layout.addWidget(self._page_widget)

        self.model = SearchModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_header_context)
        hdr.sectionResized.connect(self._on_col_resized)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_row_context)
        self.view.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.view)

    # ── Column sizing ─────────────────────────────────────────────────────────

    def _load_col_widths(self) -> list | None:
        data = self._qsettings.value(_QSETTINGS_COL_KEY)
        if isinstance(data, list) and len(data) == len(HEADERS):
            try:
                return [int(w) for w in data]
            except (ValueError, TypeError):
                pass
        return None

    def _save_col_widths(self) -> None:
        if self._col_widths and len(self._col_widths) == len(HEADERS):
            self._qsettings.setValue(_QSETTINGS_COL_KEY, self._col_widths)

    def _on_col_resized(self, col: int, _old_w: int, new_w: int) -> None:
        if self._resizing_programmatically:
            return
        if self._col_widths is None:
            self._col_widths = [self.view.columnWidth(i) for i in range(len(HEADERS))]
        if col < len(self._col_widths):
            self._col_widths[col] = new_w
        self._save_col_widths()

    def _set_default_col_widths(self) -> None:
        """Size all columns by content except Description, which gets a fixed default."""
        self._resizing_programmatically = True
        self.view.resizeColumnsToContents()
        self.view.setColumnWidth(_DESC_COL, _DESC_DEFAULT_W)
        self._resizing_programmatically = False
        self._col_widths = [self.view.columnWidth(i) for i in range(len(HEADERS))]
        self._save_col_widths()

    def _apply_col_widths(self) -> None:
        if not self._col_widths:
            return
        self._resizing_programmatically = True
        for i, w in enumerate(self._col_widths):
            self.view.setColumnWidth(i, w)
        self._resizing_programmatically = False

    def _on_header_context(self, pos) -> None:
        col = self.view.horizontalHeader().logicalIndexAt(pos)
        if col < 0:
            return
        menu = QMenu(self)
        act = menu.addAction(f"Set '{HEADERS[col]}' width…")
        if menu.exec(self.view.horizontalHeader().mapToGlobal(pos)) != act:
            return
        current = self.view.columnWidth(col)
        width, ok = QInputDialog.getInt(
            self, "Set Column Width",
            f"Width for '{HEADERS[col]}' (pixels):",
            value=current, min=20, max=9000, step=10,
        )
        if ok:
            self.view.setColumnWidth(col, width)
            if self._col_widths and col < len(self._col_widths):
                self._col_widths[col] = width
            self._save_col_widths()

    def _on_wrap_toggled(self, state: int) -> None:
        enabled = bool(state)
        self.view.setWordWrap(enabled)
        vh = self.view.verticalHeader()
        if enabled:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        else:
            vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            default_h = vh.defaultSectionSize()
            for i in range(self.model.rowCount()):
                vh.resizeSection(i, default_h)

    # ── Pagination ────────────────────────────────────────────────────────────

    def _filtered_results(self) -> list:
        results = self._all_results
        if self._show_missing_only:
            results = [r for r in results if r.get("status") == "missing"]
        owned = self.model._owned
        owned_only = self._owned_only_cb.isChecked()
        not_owned = self._not_owned_cb.isChecked()
        if owned_only and not_owned:
            results = []
        elif owned_only:
            results = [r for r in results if r.get("lb_number") in owned]
        elif not_owned:
            results = [r for r in results if r.get("lb_number") not in owned]
        if self._xref_only_cb.isChecked():
            results = [r for r in results if r.get("lb_number") in self._xref_lb_numbers]
        return results

    def _load_xref_lb_numbers(self) -> None:
        self._xref_worker = _XrefWorker(self.flask_port)
        self._xref_worker.finished.connect(self._on_xref_loaded)
        self._xref_worker.start()

    def _on_xref_loaded(self, lb_numbers: list) -> None:
        self._xref_lb_numbers = set(lb_numbers)
        if self._xref_only_cb.isChecked() and self._all_results:
            self._page = 0
            self._render_page()

    def _total_pages(self) -> int:
        results = self._filtered_results()
        if not results or self._page_size < 1:
            return 1
        return math.ceil(len(results) / self._page_size)

    def _render_page(self) -> None:
        results = self._filtered_results()
        start = self._page * self._page_size
        end = start + self._page_size

        # Snapshot current (possibly user-dragged) widths before model reset
        # clears the QHeaderView sections.
        if self._col_widths is not None:
            self._col_widths = [self.view.columnWidth(i) for i in range(len(HEADERS))]

        self.model.set_rows(results[start:end])

        if self._col_widths is None:
            if self.model.rowCount() > 0:
                self._set_default_col_widths()
        else:
            self._apply_col_widths()

        pages = self._total_pages()
        if pages > 1:
            self._page_widget.setVisible(True)
            self._page_label.setText(
                f"Page {self._page + 1} of {pages}  ({len(results)} results)"
            )
            self._prev_btn.setEnabled(self._page > 0)
            self._next_btn.setEnabled(self._page < pages - 1)
        else:
            self._page_widget.setVisible(False)

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self) -> None:
        if self._page < self._total_pages() - 1:
            self._page += 1
            self._render_page()

    def set_page_size(self, size: int) -> None:
        """Update the number of results shown per page; resets to page 1."""
        self._page_size = max(1, size)
        self._page = 0
        if self._all_results:
            self._render_page()

    # ── Years ─────────────────────────────────────────────────────────────────

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
        if current_year is not None:
            idx = self.year_combo.findData(current_year)
            if idx >= 0:
                self.year_combo.setCurrentIndex(idx)
        self.year_combo.blockSignals(False)

    # ── Search ────────────────────────────────────────────────────────────────

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

    def _on_filter_changed(self) -> None:
        self._show_missing_only = self._missing_only_cb.isChecked()
        self._page = 0
        self._render_page()
        self._update_results_label()

    def _update_results_label(self) -> None:
        filtered = self._filtered_results()
        total = len(self._all_results)
        shown = len(filtered)
        if self._show_missing_only and shown != total:
            self.results_label.setText(f"{shown} missing result(s) (of {total} total).")
        else:
            self.results_label.setText(f"{total} result(s) found.")

    def _on_results(self, results):
        self.search_btn.setEnabled(True)
        self._all_results = results
        self._page = 0
        self._render_page()
        self._update_results_label()
        self._owned_worker = _OwnedWorker(self.flask_port)
        self._owned_worker.finished.connect(self._on_owned_loaded)
        self._owned_worker.start()

    def _on_owned_loaded(self, lbs: list) -> None:
        self.model.set_owned(set(lbs))
        if self._owned_only_cb.isChecked() or self._not_owned_cb.isChecked():
            self._page = 0
            self._render_page()
            self._update_results_label()

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
            url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb:05d}.html"
            webbrowser.open(url)

    def _on_row_context(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        lb = self.model.get_lb(index.row())
        if lb is None:
            return
        menu = QMenu(self)
        wish_act = menu.addAction("Add to Wishlist")
        wish_act.triggered.connect(lambda: self._add_to_wishlist(lb))
        menu.exec(self.view.mapToGlobal(pos))

    def _add_to_wishlist(self, lb: int):
        import requests as _req
        try:
            resp = _req.post(
                f"http://127.0.0.1:{self.flask_port}/api/wishlist",
                json={"lb_number": lb}, timeout=5,
            ).json()
            if resp.get("added"):
                self.results_label.setText(f"LB-{lb:05d} added to wishlist.")
            else:
                self.results_label.setText(f"LB-{lb:05d} already on wishlist.")
        except Exception as e:
            self.results_label.setText(f"Wishlist error: {e}")
