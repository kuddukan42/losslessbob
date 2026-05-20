import math
import webbrowser

import requests
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QThread
import gui.styles as styles
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QTableView, QAbstractItemView, QHeaderView, QLabel, QCheckBox,
    QMenu, QInputDialog,
)

_STATUS_COL = 1        # index of the lb_master Status column
_DESC_COL = 5          # index of the Description column
_XREF_COL = 6          # index of the Xref column
_OWNED_COL = 7         # index of the Owned column
_SEARCH_COL_DEFAULTS = [80, 80, 100, 200, 60, 600, 60, 60]

HEADERS = ["LB Number", "Status", "Date", "Location", "Rating", "Description", "Xref", "Owned"]

# Background colours for lb_master status — single source of truth for this tab
_BG_STATUS = {
    "public":  None,           # default background
    "private": "#B3E5FC",      # light blue
    "missing": "#E0E0E0",      # light gray
}


class SearchModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []
        self._owned = set()
        self._xref_map: dict = {}
        self._bootleg_lbs: set = set()

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        lb_status = row.get("lb_status") or ""
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                lb = row.get('lb_number', '')
                badge = " 🎵" if lb in self._bootleg_lbs else ""
                return f"LB-{lb}{badge}"
            if col == _STATUS_COL:
                return lb_status.capitalize() if lb_status else ""
            # cols 2-4: date, location, rating
            keys = [None, None, "date_str", "location", "rating"]
            if col in (2, 3, 4):
                val = row.get(keys[col], "") or ""
                return str(val)
            if col == _DESC_COL:
                return str(row.get("description", "") or "")
            if col == _XREF_COL:
                vals = self._xref_map.get(row.get("lb_number"), [])
                return ", ".join(str(x) for x in vals) if vals else ""
            if col == _OWNED_COL:
                return "✓" if row.get("lb_number") in self._owned else ""
            return ""
        if role == Qt.ItemDataRole.BackgroundRole:
            from PyQt6.QtGui import QColor
            hex_color = _BG_STATUS.get(lb_status)
            if hex_color:
                return QColor(hex_color)
            if row.get("lb_number") in self._owned:
                return styles.ROW_OWNED
        if role == Qt.ItemDataRole.TextAlignmentRole and col in (_STATUS_COL, _XREF_COL, _OWNED_COL):
            return Qt.AlignmentFlag.AlignCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == _STATUS_COL and lb_status:
                return self.tr("lb_master status: {}").format(lb_status)
            if col == 0 and row.get("lb_number") in self._bootleg_lbs:
                return self.tr("🎵 This LB has bootleg CD titles — open Bootlegs tab for details")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.tr(HEADERS[section])
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

    def set_xref_map(self, xref_map: dict) -> None:
        self._xref_map = xref_map
        if self._rows:
            self.dataChanged.emit(
                self.index(0, _XREF_COL),
                self.index(len(self._rows) - 1, _XREF_COL),
            )

    def set_bootleg_lbs(self, lb_set: set) -> None:
        self._bootleg_lbs = lb_set
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0),
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


class _LbListWorker(QThread):
    """Fetch a specific list of LB entries from /api/entries/by_lb_list."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, flask_port: int, lb_numbers: list[int]) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.lb_numbers = lb_numbers

    def run(self) -> None:
        try:
            lbs_csv = ",".join(str(n) for n in self.lb_numbers)
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/entries/by_lb_list",
                params={"lbs": lbs_csv},
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.error.emit(str(exc))


class _XrefWorker(QThread):
    finished = pyqtSignal(object)  # dict: {lb_number: [xref_values]}

    def __init__(self, flask_port):
        super().__init__()
        self.flask_port = flask_port

    def run(self):
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/checksums/xref_map",
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception:
            self.finished.emit({})


class SearchTab(QWidget):
    lookup_lb = pyqtSignal(int)

    def __init__(self, flask_port, parent=None, state_store=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self._state_store = state_store
        self._worker = None
        self._years_worker = None
        self._owned_worker = None
        self._xref_worker = None
        self._all_results: list = []
        self._xref_map: dict = {}
        self._xref_lb_numbers: set = set()
        self._lb_master_stats: dict = {}  # cached stats for status filter
        self._page: int = 0
        self._page_size: int = 50
        # Sort state for in-memory sort of results
        self._sort_col_idx: int = 0          # column index
        self._sort_dir: str = "asc"          # "asc" | "desc"
        self._load_page_size()
        self._build_ui()
        self.load_years()
        self._load_xref_lb_numbers()
        self._prefetch_owned()

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
        self.search_field.setPlaceholderText(self.tr("Search..."))
        self.search_field.returnPressed.connect(self._do_search)
        search_row.addWidget(self.search_field)

        self.field_combo = QComboBox()
        self.field_combo.addItem(self.tr("All Fields"), userData="all")
        self.field_combo.addItem(self.tr("Location"), userData="location")
        self.field_combo.addItem(self.tr("Date"), userData="date")
        self.field_combo.addItem(self.tr("Description"), userData="description")
        search_row.addWidget(self.field_combo)

        self.year_combo = QComboBox()
        self.year_combo.setMinimumWidth(90)
        self.year_combo.addItem(self.tr("All Years"), userData=None)
        self.year_combo.currentIndexChanged.connect(self._do_search)
        search_row.addWidget(self.year_combo)

        self.search_btn = QPushButton(self.tr("Search"))
        self.search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self.search_btn)

        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(110)
        self._status_combo.addItem(self.tr("All statuses"), userData=None)
        self._status_combo.addItem(self.tr("Public only"),  userData="public")
        self._status_combo.addItem(self.tr("Private only"), userData="private")
        self._status_combo.addItem(self.tr("Missing only"), userData="missing")
        self._status_combo.addItem(self.tr("Needs review"), userData="needs_review")
        self._status_combo.currentIndexChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._status_combo)

        self._owned_only_cb = QCheckBox(self.tr("Owned only"))
        self._owned_only_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._owned_only_cb)

        self._not_owned_cb = QCheckBox(self.tr("Not owned"))
        self._not_owned_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._not_owned_cb)

        self._xref_only_cb = QCheckBox(self.tr("Xref only"))
        self._xref_only_cb.setToolTip(
            self.tr("Show only entries that have cross-reference (xref) alternate versions in the DB.")
        )
        self._xref_only_cb.stateChanged.connect(self._on_filter_changed)
        search_row.addWidget(self._xref_only_cb)

        self._wrap_cb = QCheckBox(self.tr("Word wrap"))
        self._wrap_cb.stateChanged.connect(self._on_wrap_toggled)
        search_row.addWidget(self._wrap_cb)

        layout.addLayout(search_row)

        self.results_label = QLabel("")
        layout.addWidget(self.results_label)

        # Pagination controls — hidden until results span more than one page
        page_row = QHBoxLayout()
        self._prev_btn = QPushButton(self.tr("← Prev"))
        self._prev_btn.setMinimumWidth(80)
        self._prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self._prev_btn)
        self._page_label = QLabel(self.tr("Page 1 of 1"))
        page_row.addWidget(self._page_label)
        self._next_btn = QPushButton(self.tr("Next →"))
        self._next_btn.setMinimumWidth(80)
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
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_header_context)
        hdr.sectionClicked.connect(self._on_sort_col_clicked)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_row_context)
        self.view.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.view)

        if self._state_store:
            self._state_store.attach_table(
                self.view, "search.results", defaults=_SEARCH_COL_DEFAULTS
            )

    # ── Header sort ──────────────────────────────────────────────────────────

    # Maps column index → key extractor for in-memory sort of result dicts.
    # HEADERS = ["LB Number", "Status", "Date", "Location", "Rating",
    #            "Description", "Xref", "Owned"]
    _SORT_KEY_FNS = {
        0: lambda r: r.get("lb_number") or 0,
        1: lambda r: {"public": 0, "private": 1, "missing": 2}.get(
               (r.get("lb_status") or ""), 99),
        2: lambda r: (r.get("date_str") or "").lower(),
        3: lambda r: (r.get("location") or "").lower(),
        4: lambda r: (r.get("rating") or "").lower(),
        5: lambda r: (r.get("description") or "").lower(),
        6: lambda r: 0,   # Xref — not directly in the row dict; treat as unsortable
        7: lambda r: 0,   # Owned — depends on owned set; treat as unsortable
    }

    def _on_sort_col_clicked(self, logical_index: int) -> None:
        """Toggle sort direction or set new sort column, then re-render page 1."""
        if logical_index == self._sort_col_idx:
            self._sort_dir = "desc" if self._sort_dir == "asc" else "asc"
        else:
            self._sort_col_idx = logical_index
            self._sort_dir = "asc"
        order = (Qt.SortOrder.AscendingOrder if self._sort_dir == "asc"
                 else Qt.SortOrder.DescendingOrder)
        self.view.horizontalHeader().setSortIndicator(logical_index, order)
        self._page = 0
        self._render_page()

    # ── Column sizing ─────────────────────────────────────────────────────────

    def _on_header_context(self, pos) -> None:
        col = self.view.horizontalHeader().logicalIndexAt(pos)
        if col < 0:
            return
        col_name = self.tr(HEADERS[col])
        menu = QMenu(self)
        act = menu.addAction(self.tr("Set '{}' width…").format(col_name))
        if menu.exec(self.view.horizontalHeader().mapToGlobal(pos)) != act:
            return
        current = self.view.columnWidth(col)
        width, ok = QInputDialog.getInt(
            self, self.tr("Set Column Width"),
            self.tr("Width for '{}' (pixels):").format(col_name),
            value=current, min=20, max=9000, step=10,
        )
        if ok:
            self.view.setColumnWidth(col, width)

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
        # lb_master status filter
        status_filter = self._status_combo.currentData()
        if status_filter == "needs_review":
            # needs_review rows aren't in the search result data — fall back to all
            pass
        elif status_filter:
            results = [r for r in results if r.get("lb_status") == status_filter]
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

    def _prefetch_owned(self) -> None:
        """Warm the owned set at tab init so colours are ready for the first search render."""
        worker = _OwnedWorker(self.flask_port)
        worker.finished.connect(self._on_owned_loaded)
        worker.start()
        self._owned_worker = worker

    def _on_xref_loaded(self, raw_map: object) -> None:
        # JSON dict keys are strings; convert to int to match lb_number type.
        if isinstance(raw_map, dict):
            self._xref_map = {int(k): v for k, v in raw_map.items()}
        else:
            self._xref_map = {}
        self._xref_lb_numbers = set(self._xref_map.keys())
        # set_xref_map() emits dataChanged for the Xref column — that is
        # sufficient.  The previous _render_page() call here caused a full
        # beginResetModel/endResetModel cycle 5–6 seconds after the initial
        # display (because get_xref_map does a slow full-table scan), resetting
        # the user's page to 0 and delaying the visual appearance of row
        # colours until that late repaint.
        self.model.set_xref_map(self._xref_map)

    def _total_pages(self) -> int:
        results = self._filtered_results()
        if not results or self._page_size < 1:
            return 1
        return math.ceil(len(results) / self._page_size)

    def _render_page(self) -> None:
        results = self._filtered_results()
        key_fn = self._SORT_KEY_FNS.get(self._sort_col_idx)
        if key_fn is not None:
            try:
                results = sorted(results, key=key_fn,
                                 reverse=(self._sort_dir == "desc"))
            except Exception:
                pass
        start = self._page * self._page_size
        end = start + self._page_size

        self.model.set_rows(results[start:end])

        pages = self._total_pages()
        if pages > 1:
            self._page_widget.setVisible(True)
            self._page_label.setText(
                self.tr("Page {0} of {1}  ({2} results)").format(
                    self._page + 1, pages, len(results)
                )
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

    def load_lb_list(self, lb_numbers: list[int]) -> None:
        """Load a specific set of LB numbers directly (used by Map tab viewport filter).

        Args:
            lb_numbers: List of integer LB numbers to fetch and display.
        """
        if not lb_numbers:
            return
        self.search_btn.setEnabled(False)
        self.results_label.setText(self.tr("Loading {} entries…").format(len(lb_numbers)))
        self._lb_list_worker = _LbListWorker(self.flask_port, lb_numbers)
        self._lb_list_worker.finished.connect(self._on_results)
        self._lb_list_worker.error.connect(self._on_error)
        self._lb_list_worker.start()

    # ── Years ─────────────────────────────────────────────────────────────────

    def load_years(self):
        self._years_worker = _YearsWorker(self.flask_port)
        self._years_worker.finished.connect(self._on_years_loaded)
        self._years_worker.start()

    def _on_years_loaded(self, years):
        current_year = self.year_combo.currentData()
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItem(self.tr("All Years"), userData=None)
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
        field = self.field_combo.currentData() or "all"
        year = self.year_combo.currentData()
        self.search_btn.setEnabled(False)
        self.results_label.setText(self.tr("Searching..."))

        self._worker = _SearchWorker(self.flask_port, q, field, year=year)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_filter_changed(self) -> None:
        self._page = 0
        self._render_page()
        self._update_results_label()

    def _update_results_label(self) -> None:
        filtered = self._filtered_results()
        total = len(self._all_results)
        shown = len(filtered)
        status_filter = self._status_combo.currentData()
        if status_filter and shown != total:
            self.results_label.setText(
                self.tr("{0} result(s) matching '{1}' (of {2} total).").format(
                    shown, self._status_combo.currentText(), total
                )
            )
        else:
            self.results_label.setText(self.tr("{} result(s) found.").format(total))

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
        self.results_label.setText(self.tr("Error: {}").format(msg))

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
        wish_act = menu.addAction(self.tr("Add to Wishlist"))
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
                self.results_label.setText(self.tr("LB-{} added to wishlist.").format(f"{lb:05d}"))
            else:
                self.results_label.setText(self.tr("LB-{} already on wishlist.").format(f"{lb:05d}"))
        except Exception as e:
            self.results_label.setText(self.tr("Wishlist error: {}").format(e))

    def set_bootleg_lbs(self, lb_set: set) -> None:
        """Push the bootleg-LB set so the 🎵 badge can appear in the LB Number column."""
        self.model.set_bootleg_lbs(lb_set)

    def resize_columns_to_font(self) -> None:
        self.view.resizeColumnsToContents()
