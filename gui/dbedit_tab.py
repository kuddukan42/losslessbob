import logging
import requests
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QMenu, QComboBox, QApplication, QInputDialog,
    QDialog, QFormLayout, QDoubleSpinBox, QDialogButtonBox, QGroupBox,
)

_log = logging.getLogger(__name__)

_C_DIRTY  = QColor("#fffbe6")
_C_WARN   = QColor("#fff0f0")
_C_AUDIT  = QColor("#f0f0ff")
_C_RDONLY = QColor("#f4f4f4")


# ── Geocoding helpers ─────────────────────────────────────────────────────────

class PlaceManualDialog(QDialog):
    """Dialog for manually entering lat/lon coordinates for a location.

    Args:
        location_text: The raw location string being geocoded (read-only).
        lat: Pre-filled latitude, or None if not yet geocoded.
        lon: Pre-filled longitude, or None if not yet geocoded.
        note: Pre-filled curator note, or empty string.
        parent: Parent widget.
    """

    def __init__(
        self,
        location_text: str,
        lat: float | None,
        lon: float | None,
        note: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Place Manually")
        self.setMinimumWidth(360)

        form = QFormLayout(self)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)

        loc_lbl = QLabel(location_text)
        loc_lbl.setWordWrap(True)
        form.addRow("Location:", loc_lbl)

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(6)
        self._lat_spin.setSingleStep(0.0001)
        self._lat_spin.setValue(lat if lat is not None else 0.0)
        form.addRow("Lat:", self._lat_spin)

        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(6)
        self._lon_spin.setSingleStep(0.0001)
        self._lon_spin.setValue(lon if lon is not None else 0.0)
        form.addRow("Lon:", self._lon_spin)

        self._note_edit = QLineEdit(note)
        self._note_edit.setPlaceholderText("Optional curator note…")
        form.addRow("Note:", self._note_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._location_text = location_text

    @property
    def location(self) -> str:
        """The location text that was passed in (read-only)."""
        return self._location_text

    @property
    def lat(self) -> float:
        """Currently selected latitude value."""
        return self._lat_spin.value()

    @property
    def lon(self) -> float:
        """Currently selected longitude value."""
        return self._lon_spin.value()

    @property
    def note(self) -> str:
        """Currently entered note text."""
        return self._note_edit.text().strip()


class _Worker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.finished.emit(self._fn())
        except Exception as e:
            self.error.emit(str(e))


class DbEditTab(QWidget):

    def __init__(self, flask_port, parent=None, state_store=None):
        super().__init__(parent)
        self.flask_port            = flask_port
        self._state_store          = state_store
        self._table_meta: dict     = {}
        self._current_table        = ""
        self._schema: list         = []
        self._columns: list        = []
        self._page                 = 0
        self._limit                = 100
        self._total                = 0
        self._dirty: dict          = {}   # (row, col) -> new_value
        self._rowids: list         = []   # rowid per displayed row
        self._workers: list        = []
        # Per-table column widths in-session cache: {table_name: [w0, w1, ...]}
        self._col_widths: dict     = {}
        self._resizing_prog: bool  = False
        # Sort state: column name string and direction for the current table
        self._sort_col: str  = ""
        self._sort_dir: str  = "asc"
        self._is_curator: bool | None = None   # fetched lazily on first alias panel use
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: table list
        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.addWidget(QLabel("Tables"))
        self.table_list = QListWidget()
        self.table_list.setFixedWidth(190)
        self.table_list.currentItemChanged.connect(self._on_table_selected)
        ll.addWidget(self.table_list)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_tables)
        ll.addWidget(refresh_btn)

        # ── DB Integrity sub-panel ────────────────────────────────────────────
        integrity_box = QGroupBox("DB Integrity")
        ib_layout = QVBoxLayout(integrity_box)
        ib_layout.setContentsMargins(6, 8, 6, 6)
        ib_layout.setSpacing(3)

        self._integrity_label = QLabel("—")
        self._integrity_label.setWordWrap(True)
        ib_layout.addWidget(self._integrity_label)

        reconcile_btn = QPushButton("Reconcile All")
        reconcile_btn.setToolTip(
            "Recompute lb_master status for every LB number. Backs up DB first."
        )
        reconcile_btn.clicked.connect(self._on_reconcile_all)
        ib_layout.addWidget(reconcile_btn)

        needs_review_btn = QPushButton("Show Needs Review")
        needs_review_btn.setToolTip(
            "Load lb_master rows flagged as needing curator review."
        )
        needs_review_btn.clicked.connect(self._on_show_needs_review)
        ib_layout.addWidget(needs_review_btn)

        export_overrides_btn = QPushButton("Export Overrides")
        export_overrides_btn.setToolTip("Save all manual LB status overrides to a JSON file.")
        export_overrides_btn.clicked.connect(self._on_export_overrides)
        ib_layout.addWidget(export_overrides_btn)

        import_overrides_btn = QPushButton("Import Overrides")
        import_overrides_btn.setToolTip("Load manual LB status overrides from a JSON file.")
        import_overrides_btn.clicked.connect(self._on_import_overrides)
        ib_layout.addWidget(import_overrides_btn)

        backup_btn = QPushButton("Backup DB Now")
        backup_btn.setToolTip("Create a manual snapshot of the database.")
        backup_btn.clicked.connect(self._on_backup_db)
        ib_layout.addWidget(backup_btn)

        ll.addWidget(integrity_box)

        # ── Aliases sub-panel ─────────────────────────────────────────────────
        aliases_box = QGroupBox("LB Aliases")
        ab_layout = QVBoxLayout(aliases_box)
        ab_layout.setContentsMargins(6, 8, 6, 6)
        ab_layout.setSpacing(3)

        self._alias_table = QTableWidget()
        self._alias_table.setColumnCount(5)
        self._alias_table.setHorizontalHeaderLabels(
            ["Alias LB", "→", "Canonical LB", "Relationship", "Note"]
        )
        self._alias_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._alias_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._alias_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._alias_table.setFixedHeight(130)
        ab_layout.addWidget(self._alias_table)

        alias_btn_row = QHBoxLayout()
        self._alias_add_btn = QPushButton("Add")
        self._alias_add_btn.setToolTip("Add a new alias mapping (curator only)")
        self._alias_add_btn.clicked.connect(self._on_add_alias)
        alias_btn_row.addWidget(self._alias_add_btn)

        self._alias_del_btn = QPushButton("Delete")
        self._alias_del_btn.setToolTip("Remove selected alias (curator only)")
        self._alias_del_btn.clicked.connect(self._on_delete_alias)
        alias_btn_row.addWidget(self._alias_del_btn)

        reload_alias_btn = QPushButton("Reload")
        reload_alias_btn.clicked.connect(self._load_aliases)
        alias_btn_row.addWidget(reload_alias_btn)
        ab_layout.addLayout(alias_btn_row)

        self._alias_status = QLabel("")
        self._alias_status.setWordWrap(True)
        ab_layout.addWidget(self._alias_status)

        ll.addWidget(aliases_box)

        # ── Location Geocoding sub-panel (curator only) ───────────────────────
        self._geo_box = QGroupBox("Location Geocoding")
        geo_layout = QVBoxLayout(self._geo_box)
        geo_layout.setContentsMargins(6, 8, 6, 6)
        geo_layout.setSpacing(3)

        geo_filter_row = QHBoxLayout()
        geo_filter_row.addWidget(QLabel("Filter:"))
        self._geo_filter_combo = QComboBox()
        self._geo_filter_combo.addItems(["All", "Failed", "Low Confidence", "Manual Only"])
        self._geo_filter_combo.setToolTip(
            "All → all locations\n"
            "Failed → geocoding failed\n"
            "Low Confidence → confidence score below threshold\n"
            "Manual Only → entries with a manual coordinate override"
        )
        geo_filter_row.addWidget(self._geo_filter_combo)

        self._geo_load_btn = QPushButton("Load")
        self._geo_load_btn.setToolTip("Fetch locations from /api/geocode/locations")
        self._geo_load_btn.clicked.connect(self._on_geo_load)
        geo_filter_row.addWidget(self._geo_load_btn)
        geo_layout.addLayout(geo_filter_row)

        self._geo_table = QTableWidget(0, 7)
        self._geo_table.setHorizontalHeaderLabels(
            ["Location Text", "Source", "Confidence", "Lat", "Lon", "Manual?", "Note"]
        )
        self._geo_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._geo_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        hdr = self._geo_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._geo_table.setMinimumHeight(120)
        self._geo_table.setMaximumHeight(200)
        self._geo_table.doubleClicked.connect(self._on_geo_row_dblclick)
        geo_layout.addWidget(self._geo_table)

        self._geo_status = QLabel("")
        self._geo_status.setWordWrap(True)
        geo_layout.addWidget(self._geo_status)

        self._geo_box.setVisible(False)  # shown only in curator mode
        ll.addWidget(self._geo_box)

        ll.addStretch()
        splitter.addWidget(left)

        # Right panel: data view
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)

        # Toolbar row
        toolbar = QHBoxLayout()
        self.table_label = QLabel("Select a table")
        f = self.table_label.font()
        f.setBold(True)
        self.table_label.setFont(f)
        toolbar.addWidget(self.table_label)
        toolbar.addStretch()
        load_btn = QPushButton("Load Records")
        load_btn.setToolTip("Retrieve all records for the selected table (clears search)")
        load_btn.clicked.connect(self._on_load_all)
        toolbar.addWidget(load_btn)
        toolbar.addWidget(QLabel("LB#:"))
        self.lb_input = QLineEdit()
        self.lb_input.setPlaceholderText("e.g. 1797")
        self.lb_input.setFixedWidth(80)
        self.lb_input.returnPressed.connect(self._do_search)
        toolbar.addWidget(self.lb_input)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search text columns…")
        self.search_input.setFixedWidth(220)
        self.search_input.returnPressed.connect(self._do_search)
        toolbar.addWidget(self.search_input)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        toolbar.addWidget(search_btn)
        rl.addLayout(toolbar)

        # Schema strip
        self.schema_label = QLabel("")
        self.schema_label.setWordWrap(True)
        self.schema_label.setStyleSheet("font-size:10px; color:#888;")
        rl.addWidget(self.schema_label)

        # Data table
        self.data_table = QTableWidget()
        self.data_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        hdr = self.data_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_header_context)
        hdr.sectionResized.connect(self._on_col_resized)
        hdr.sectionClicked.connect(self._on_sort_col_clicked)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_context)
        self.data_table.itemChanged.connect(self._on_cell_changed)
        rl.addWidget(self.data_table)

        # Pagination row
        page_row = QHBoxLayout()
        self.prev_btn = QPushButton("< Prev")
        self.prev_btn.setMinimumWidth(70)
        self.prev_btn.clicked.connect(self._prev_page)
        page_row.addWidget(self.prev_btn)
        self.page_label = QLabel("")
        page_row.addWidget(self.page_label)
        self.next_btn = QPushButton("Next >")
        self.next_btn.setMinimumWidth(70)
        self.next_btn.clicked.connect(self._next_page)
        page_row.addWidget(self.next_btn)
        page_row.addStretch()
        page_row.addWidget(QLabel("Rows per page:"))
        self.limit_combo = QComboBox()
        for v in [50, 100, 200, 500]:
            self.limit_combo.addItem(str(v), v)
        self.limit_combo.setCurrentIndex(1)
        self.limit_combo.currentIndexChanged.connect(self._on_limit_changed)
        page_row.addWidget(self.limit_combo)
        rl.addLayout(page_row)

        # Action row
        act_row = QHBoxLayout()
        self.save_btn = QPushButton("Commit Changes")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_commit)
        act_row.addWidget(self.save_btn)
        self.discard_btn = QPushButton("Discard Changes")
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self._on_discard)
        act_row.addWidget(self.discard_btn)
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete)
        act_row.addWidget(self.delete_btn)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._on_export)
        act_row.addWidget(self.export_btn)
        act_row.addStretch()
        self.status_label = QLabel("")
        act_row.addWidget(self.status_label)
        rl.addLayout(act_row)

        splitter.addWidget(right)
        splitter.setSizes([190, 800])
        layout.addWidget(splitter)

    # ── Table list ────────────────────────────────────────────────────────────

    def load_tables(self):
        w = _Worker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}/api/dbedit/tables",
            timeout=10).json())
        w.finished.connect(self._on_tables_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()
        self.load_integrity_stats()
        self._load_aliases()

    def _on_tables_loaded(self, data):
        self.table_list.clear()
        self._table_meta = {}
        if not isinstance(data, list):
            return
        for t in data:
            name = t["name"]
            self._table_meta[name] = t
            label = (f"{name}  ({t['row_count']:,})" if t["row_count"] >= 0
                     else name)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if t.get("readonly"):
                item.setForeground(QColor("#888"))
                item.setToolTip("Read-only virtual table")
            elif t.get("warn"):
                item.setForeground(QColor("#c0392b"))
                item.setToolTip("Core archive — deletions affect lookup results")
            elif t.get("audit"):
                item.setForeground(QColor("#2980b9"))
                item.setToolTip("Audit log — delete only, no editing")
            self.table_list.addItem(item)

    def _on_table_selected(self, current, _previous):
        if not current:
            return
        self._current_table = current.data(Qt.ItemDataRole.UserRole)
        self._page = 0
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.search_input.clear()
        self.lb_input.clear()
        self._sort_col = ""
        self._sort_dir = "asc"
        self.data_table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        # Prime the in-session cache so the first load can restore widths
        if self._current_table not in self._col_widths:
            saved = self._load_saved_widths(self._current_table)
            if saved:
                self._col_widths[self._current_table] = saved
        self._load_schema()
        self._load_rows()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _load_schema(self):
        if not self._current_table:
            return
        name = self._current_table
        w = _Worker(lambda: requests.get(
            f"http://127.0.0.1:{self.flask_port}"
            f"/api/dbedit/table/{name}/schema",
            timeout=5).json())
        w.finished.connect(self._on_schema_loaded)
        self._workers.append(w)
        w.start()

    def _on_schema_loaded(self, data):
        if not isinstance(data, list):
            return
        self._schema = data
        parts = []
        for c in data:
            pk = " [PK]" if c.get("pk") else ""
            nn = " NOT NULL" if c.get("notnull") else ""
            parts.append(f"{c['name']} {c.get('type', '')}{pk}{nn}")
        self.schema_label.setText("  |  ".join(parts))

    # ── Row data ──────────────────────────────────────────────────────────────

    def _on_sort_col_clicked(self, logical_index: int) -> None:
        """Toggle sort direction when the same column header is clicked; reset to ASC otherwise."""
        if not self._columns or logical_index >= len(self._columns):
            return
        col_name = self._columns[logical_index]
        # Skip the hidden rowid column (index 0)
        if logical_index == 0:
            return
        if self._sort_col == col_name:
            self._sort_dir = "desc" if self._sort_dir == "asc" else "asc"
        else:
            self._sort_col = col_name
            self._sort_dir = "asc"
        order = (Qt.SortOrder.AscendingOrder if self._sort_dir == "asc"
                 else Qt.SortOrder.DescendingOrder)
        self.data_table.horizontalHeader().setSortIndicator(logical_index, order)
        self._page = 0
        self._load_rows()

    def _on_load_all(self):
        if not self._current_table:
            self.status_label.setText("Select a table first.")
            return
        self.search_input.clear()
        self.lb_input.clear()
        self._page = 0
        self._sort_col = ""
        self._sort_dir = "asc"
        self.data_table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self._load_rows()

    def _do_search(self):
        self._page = 0
        self._load_rows()

    def _load_rows(self):
        if not self._current_table:
            return
        name      = self._current_table
        search    = self.search_input.text().strip()
        lb_number = self.lb_input.text().strip()
        url    = (f"http://127.0.0.1:{self.flask_port}"
                  f"/api/dbedit/table/{name}/rows"
                  f"?page={self._page}&limit={self._limit}"
                  + (f"&search={search}" if search else "")
                  + (f"&lb_number={lb_number}" if lb_number else "")
                  + (f"&sort_col={self._sort_col}&sort_dir={self._sort_dir}"
                     if self._sort_col else ""))
        self.status_label.setText("Loading…")
        w = _Worker(lambda: requests.get(url, timeout=20).json())
        w.finished.connect(self._on_rows_loaded)
        w.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_rows_loaded(self, data):
        if "error" in data:
            self.status_label.setText(f"Error: {data['error']}")
            return

        self._total   = data["total"]
        self._columns = data["columns"]
        rows          = data["rows"]
        meta          = self._table_meta.get(self._current_table, {})
        editable      = not meta.get("readonly") and not meta.get("audit")

        self.data_table.blockSignals(True)
        self.data_table.clearContents()
        self.data_table.setRowCount(len(rows))
        self.data_table.setColumnCount(len(self._columns))
        self.data_table.setHorizontalHeaderLabels(self._columns)

        self._rowids = []
        for r_idx, row in enumerate(rows):
            self._rowids.append(row[0])
            for c_idx, val in enumerate(row):
                text = "" if val is None else str(val)
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, val)
                not_editable = (c_idx == 0 or not editable)
                if not_editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c_idx == 0:
                    item.setForeground(QColor("#aaa"))
                if meta.get("warn"):
                    item.setBackground(_C_WARN)
                elif meta.get("audit"):
                    item.setBackground(_C_AUDIT)
                elif meta.get("readonly"):
                    item.setBackground(_C_RDONLY)
                self.data_table.setItem(r_idx, c_idx, item)

        self.data_table.blockSignals(False)
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)

        pages = max(1, -(-self._total // self._limit))
        self.page_label.setText(
            f"Page {self._page + 1}/{pages}  ({self._total:,} rows total)"
        )
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)

        lbl = self._current_table
        if meta.get("readonly"): lbl += " [read-only]"
        if meta.get("audit"):    lbl += " [audit: delete only]"
        if meta.get("warn"):     lbl += "  WARNING: core archive table"
        self.table_label.setText(lbl)
        self.status_label.setText(f"{self._total:,} rows")

        # Column widths: restore saved, or size-to-content on first load
        saved = self._col_widths.get(self._current_table)
        if saved and len(saved) == len(self._columns):
            self._apply_col_widths(saved)
        else:
            self._resizing_prog = True
            self.data_table.resizeColumnsToContents()
            self._resizing_prog = False
            self._snapshot_and_save()

    # ── Column width management ───────────────────────────────────────────────

    def _snapshot_and_save(self) -> None:
        """Capture current column widths and persist via state_store."""
        n = self.data_table.columnCount()
        if n == 0:
            return
        widths = [self.data_table.columnWidth(i) for i in range(n)]
        self._col_widths[self._current_table] = widths
        if self._state_store:
            self._state_store.set_col_widths(
                f"dbedit.{self._current_table}", widths
            )

    def _load_saved_widths(self, table: str) -> list | None:
        """Return persisted widths for *table*, or None if not saved yet."""
        if self._state_store:
            return self._state_store.get_col_widths(f"dbedit.{table}")
        return None

    def _apply_col_widths(self, widths: list) -> None:
        self._resizing_prog = True
        for i, w in enumerate(widths):
            if i < self.data_table.columnCount():
                self.data_table.setColumnWidth(i, w)
        self._resizing_prog = False

    def _on_col_resized(self, col: int, _old: int, new_w: int) -> None:
        if self._resizing_prog:
            return
        table = self._current_table
        if not table:
            return
        n = self.data_table.columnCount()
        widths = self._col_widths.get(table) or [self.data_table.columnWidth(i) for i in range(n)]
        if col < len(widths):
            widths[col] = new_w
        self._col_widths[table] = widths
        if self._state_store:
            self._state_store.set_col_widths(f"dbedit.{table}", widths)

    def _on_header_context(self, pos) -> None:
        hdr = self.data_table.horizontalHeader()
        col = hdr.logicalIndexAt(pos)
        if col < 0:
            return
        col_name = self._columns[col] if col < len(self._columns) else str(col)
        menu = QMenu(self)
        set_act    = menu.addAction(f"Set '{col_name}' width…")
        fit_act    = menu.addAction(f"Fit '{col_name}' to contents")
        fit_all    = menu.addAction("Fit all columns to contents")
        chosen = menu.exec(hdr.mapToGlobal(pos))
        if chosen == set_act:
            current = self.data_table.columnWidth(col)
            width, ok = QInputDialog.getInt(
                self, "Set Column Width",
                f"Width for '{col_name}' (pixels):",
                value=current, min=20, max=9000, step=10,
            )
            if ok:
                self._resizing_prog = True
                self.data_table.setColumnWidth(col, width)
                self._resizing_prog = False
                self._snapshot_and_save()
        elif chosen == fit_act:
            self.data_table.resizeColumnToContents(col)
            self._snapshot_and_save()
        elif chosen == fit_all:
            self._resizing_prog = True
            self.data_table.resizeColumnsToContents()
            self._resizing_prog = False
            self._snapshot_and_save()

    # ── Pagination ────────────────────────────────────────────────────────────

    def _on_limit_changed(self):
        self._limit = self.limit_combo.currentData()
        self._page  = 0
        self._load_rows()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._load_rows()

    def _next_page(self):
        pages = max(1, -(-self._total // self._limit))
        if self._page < pages - 1:
            self._page += 1
            self._load_rows()

    # ── Inline editing ────────────────────────────────────────────────────────

    def _on_cell_changed(self, item):
        row, col = item.row(), item.column()
        if col == 0:
            return
        original = item.data(Qt.ItemDataRole.UserRole)
        new_val  = item.text()
        if str("" if original is None else original) != new_val:
            self._dirty[(row, col)] = new_val
            item.setBackground(_C_DIRTY)
        else:
            self._dirty.pop((row, col), None)
            item.setBackground(QColor("white"))
        has = bool(self._dirty)
        self.save_btn.setEnabled(has)
        self.discard_btn.setEnabled(has)

    def _on_commit(self):
        if not self._dirty:
            return
        by_row: dict = {}
        for (r, c), val in self._dirty.items():
            by_row.setdefault(r, {})[self._columns[c]] = val

        errors = []
        for r_idx, updates in by_row.items():
            rowid = self._rowids[r_idx]
            name  = self._current_table
            try:
                resp = requests.patch(
                    f"http://127.0.0.1:{self.flask_port}"
                    f"/api/dbedit/table/{name}/row",
                    json={"rowid": rowid, "updates": updates},
                    timeout=10,
                ).json()
                if resp.get("error"):
                    errors.append(f"rowid {rowid}: {resp['error']}")
            except Exception as e:
                errors.append(str(e))

        if errors:
            self.status_label.setText(f"Errors: {errors[0]}")
        else:
            self.status_label.setText(f"Committed {len(by_row)} row(s).")
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self._load_rows()

    def _on_discard(self):
        self._dirty.clear()
        self.save_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self._load_rows()

    # ── Delete ────────────────────────────────────────────────────────────────

    def _on_delete(self):
        selected = list({idx.row() for idx in
                         self.data_table.selectedIndexes()})
        if not selected:
            self.status_label.setText("Select rows to delete.")
            return
        meta = self._table_meta.get(self._current_table, {})
        if meta.get("readonly"):
            self.status_label.setText("Cannot delete from a read-only table.")
            return

        extra = ""
        if meta.get("warn"):
            extra = ("\n\nWARNING: This is a core archive table. "
                     "Deleting checksums or entries affects lookup results.")

        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(selected)} row(s) from '{self._current_table}'?{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        rowids = [self._rowids[r] for r in selected]
        name   = self._current_table
        try:
            resp = requests.delete(
                f"http://127.0.0.1:{self.flask_port}"
                f"/api/dbedit/table/{name}/rows",
                json={"rowids": rowids}, timeout=15,
            ).json()
            if resp.get("error"):
                self.status_label.setText(f"Error: {resp['error']}")
            else:
                self.status_label.setText(f"Deleted {resp.get('deleted', 0)} row(s).")
                self._load_rows()
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_context(self, pos):
        menu = QMenu(self)
        copy_act = QAction("Copy Cell Value", self)
        copy_act.triggered.connect(self._copy_cell)
        menu.addAction(copy_act)
        del_act = QAction("Delete Selected Row(s)", self)
        del_act.triggered.connect(self._on_delete)
        menu.addAction(del_act)
        menu.exec(self.data_table.mapToGlobal(pos))

    def _copy_cell(self):
        item = self.data_table.currentItem()
        if item:
            QApplication.clipboard().setText(item.text())

    # ── CSV export ────────────────────────────────────────────────────────────

    def _on_export(self):
        if not self._current_table:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV",
            f"{self._current_table}.csv",
            "CSV Files (*.csv)"
        )
        if not path:
            return
        name = self._current_table
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}"
                f"/api/dbedit/table/{name}/export",
                timeout=60,
            )
            with open(path, "wb") as fh:
                fh.write(resp.content)
            self.status_label.setText(f"Exported to {Path(path).name}")
        except Exception as e:
            self.status_label.setText(f"Export error: {e}")

    def resize_columns_to_font(self) -> None:
        self.data_table.resizeColumnsToContents()

    # ── DB Integrity panel ────────────────────────────────────────────────────

    def load_integrity_stats(self) -> None:
        """Fetch lb_master stats and update the integrity label."""
        def _fetch():
            return requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/lb_master/stats",
                timeout=10,
            ).json()

        w = _Worker(_fetch)
        w.finished.connect(self._on_integrity_stats)
        w.error.connect(lambda e: self._integrity_label.setText(f"Stats error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_integrity_stats(self, data: dict) -> None:
        if not isinstance(data, dict) or "error" in data:
            self._integrity_label.setText("Stats unavailable")
            return
        self._integrity_label.setText(
            f"Public: {data.get('public', 0):,}\n"
            f"Private: {data.get('private', 0):,}\n"
            f"Missing: {data.get('missing', 0):,}\n"
            f"Max LB: {data.get('max_lb', 0):,}\n"
            f"Overrides: {data.get('overrides', 0):,}\n"
            f"Needs review: {data.get('needs_review', 0):,}"
        )

    def _on_reconcile_all(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Reconcile All",
            "Recompute lb_master status for every LB number?\n"
            "A database backup will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._integrity_label.setText("Reconciling…")

        def _run():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lb_master/reconcile",
                timeout=120,
            ).json()

        w = _Worker(_run)
        w.finished.connect(self._on_reconcile_done)
        w.error.connect(lambda e: self._integrity_label.setText(f"Reconcile error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_reconcile_done(self, data: dict) -> None:
        if data.get("ok"):
            stats = data.get("stats", {})
            self._on_integrity_stats(stats)
            self.status_label.setText("Reconcile complete.")
        else:
            self._integrity_label.setText(f"Error: {data.get('error', 'unknown')}")

    def _on_show_needs_review(self) -> None:
        """Select lb_master in the table list and filter to needs_review rows."""
        for i in range(self.table_list.count()):
            item = self.table_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == "lb_master":
                self.table_list.setCurrentItem(item)
                break
        # Apply filter via search box
        self.search_input.setText("needs_review:1")
        self._do_search()

    def _on_backup_db(self) -> None:
        from PyQt6.QtWidgets import QMessageBox

        def _run():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/db/backup",
                json={"reason": "manual"},
                timeout=60,
            ).json()

        w = _Worker(_run)
        w.finished.connect(self._on_backup_done)
        w.error.connect(lambda e: self.status_label.setText(f"Backup error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_backup_done(self, data: dict) -> None:
        from PyQt6.QtWidgets import QMessageBox
        if data.get("ok"):
            size_mb = data.get("size_bytes", 0) / 1_048_576
            QMessageBox.information(
                self, "Backup Complete",
                f"Backup saved to:\n{data.get('path', '?')}\n\nSize: {size_mb:.1f} MB",
            )
        else:
            self.status_label.setText(f"Backup error: {data.get('error', 'unknown')}")

    def _on_export_overrides(self) -> None:
        """Export all manual lb_master overrides to a user-chosen JSON file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Overrides", "lb_overrides.json", "JSON files (*.json)"
        )
        if not path:
            return

        def _run():
            r = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/lb_master/overrides/export",
                timeout=10,
            )
            r.raise_for_status()
            return r.json()

        w = _Worker(_run)

        def _done(data: list) -> None:
            import json
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {len(data)} override(s) to:\n{path}",
            )

        w.finished.connect(_done)
        w.error.connect(lambda e: QMessageBox.warning(self, "Export Error", str(e)))
        self._workers.append(w)
        w.start()

    def _on_import_overrides(self) -> None:
        """Import manual lb_master overrides from a user-chosen JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Overrides", "", "JSON files (*.json)"
        )
        if not path:
            return

        import json
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:
            QMessageBox.warning(self, "Import Error", f"Could not read file:\n{exc}")
            return

        if not isinstance(payload, list):
            QMessageBox.warning(self, "Import Error", "File must contain a JSON array.")
            return

        reply = QMessageBox.question(
            self, "Confirm Import",
            f"Import {len(payload)} override(s) from:\n{path}\n\n"
            "This will overwrite existing overrides for those LBs.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def _run():
            r = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lb_master/overrides/import",
                json=payload,
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

        w = _Worker(_run)

        def _done(data: dict) -> None:
            QMessageBox.information(
                self, "Import Complete",
                f"Imported {data.get('imported', 0)} override(s).\n"
                f"Skipped {data.get('skipped', 0)} out-of-range entries.",
            )
            self.load_integrity_stats()

        w.finished.connect(_done)
        w.error.connect(lambda e: QMessageBox.warning(self, "Import Error", str(e)))
        self._workers.append(w)
        w.start()

    # ── Aliases panel ─────────────────────────────────────────────────────────

    def _check_curator(self) -> bool:
        """Return curator status, fetching from backend once per session."""
        if self._is_curator is None:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/curator",
                    timeout=5,
                )
                self._is_curator = bool(resp.json().get("is_curator", False))
            except Exception:
                self._is_curator = False
        return self._is_curator

    def _load_aliases(self) -> None:
        """Fetch lb_alias rows from the backend and populate the alias table."""
        def _fetch():
            return requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/lb_alias",
                timeout=10,
            ).json()

        w = _Worker(_fetch)
        w.finished.connect(self._on_aliases_loaded)
        w.error.connect(lambda e: self._alias_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_aliases_loaded(self, data) -> None:
        if not isinstance(data, list):
            self._alias_status.setText("Failed to load aliases.")
            return
        curator = self._check_curator()
        self._alias_add_btn.setEnabled(curator)
        self._alias_del_btn.setEnabled(curator)
        self._geo_box.setVisible(curator)

        self._alias_table.setRowCount(0)
        for row in data:
            r = self._alias_table.rowCount()
            self._alias_table.insertRow(r)
            alias_lb = row.get("alias_lb", "")
            canonical_lb = row.get("canonical_lb", "")
            relationship = row.get("relationship", "")
            note = row.get("note") or ""
            for c, val in enumerate([str(alias_lb), "→", str(canonical_lb), relationship, note]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._alias_table.setItem(r, c, item)
        n = len(data)
        self._alias_status.setText(
            f"{n} alias{'es' if n != 1 else ''}" + ("" if curator else " (read-only)")
        )

    def _on_add_alias(self) -> None:
        """Open a dialog to add a new lb_alias entry (curator only)."""
        if not self._check_curator():
            self._alias_status.setText("Curator mode required to add aliases.")
            return

        from PyQt6.QtWidgets import (
            QDialog, QFormLayout, QSpinBox, QComboBox, QTextEdit, QDialogButtonBox,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Add LB Alias")
        dlg.setMinimumWidth(360)
        form = QFormLayout(dlg)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)

        alias_spin = QSpinBox()
        alias_spin.setRange(1, 999999)
        form.addRow("Alias LB (secondary):", alias_spin)

        canon_spin = QSpinBox()
        canon_spin.setRange(1, 999999)
        form.addRow("Canonical LB (primary):", canon_spin)

        rel_combo = QComboBox()
        for rel in ("duplicate", "supersedes", "see_also"):
            rel_combo.addItem(rel)
        form.addRow("Relationship:", rel_combo)

        note_edit = QTextEdit()
        note_edit.setFixedHeight(56)
        note_edit.setPlaceholderText("Optional note…")
        form.addRow("Note:", note_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        alias_lb = alias_spin.value()
        canonical_lb = canon_spin.value()
        relationship = rel_combo.currentText()
        note = note_edit.toPlainText().strip()

        def _post():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/lb_alias",
                json={
                    "alias_lb": alias_lb,
                    "canonical_lb": canonical_lb,
                    "relationship": relationship,
                    "note": note,
                },
                timeout=10,
            ).json()

        def _done(result):
            if "error" in result:
                self._alias_status.setText(f"Error: {result['error']}")
            else:
                rewrote = " (chain rewritten)" if result.get("rewrote_chain") else ""
                self._alias_status.setText(
                    f"Alias LB-{alias_lb:05d} → LB-{result.get('canonical_lb', canonical_lb):05d} "
                    f"saved{rewrote}."
                )
                self._load_aliases()

        w = _Worker(_post)
        w.finished.connect(_done)
        w.error.connect(lambda e: self._alias_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    def _on_delete_alias(self) -> None:
        """Delete the selected alias row (curator only)."""
        if not self._check_curator():
            self._alias_status.setText("Curator mode required to delete aliases.")
            return
        selected = self._alias_table.selectedItems()
        if not selected:
            self._alias_status.setText("Select an alias row to delete.")
            return
        row_idx = self._alias_table.currentRow()
        alias_item = self._alias_table.item(row_idx, 0)
        if alias_item is None:
            return
        try:
            alias_lb = int(alias_item.text())
        except ValueError:
            self._alias_status.setText("Could not parse alias LB number.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Remove alias LB-{alias_lb:05d}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def _delete():
            return requests.delete(
                f"http://127.0.0.1:{self.flask_port}/api/lb_alias/{alias_lb}",
                timeout=10,
            ).json()

        def _done(result):
            if result.get("ok"):
                self._alias_status.setText(f"Alias LB-{alias_lb:05d} removed.")
                self._load_aliases()
            else:
                self._alias_status.setText(f"Error: {result.get('error', 'unknown')}")

        w = _Worker(_delete)
        w.finished.connect(_done)
        w.error.connect(lambda e: self._alias_status.setText(f"Error: {e}"))
        self._workers.append(w)
        w.start()

    # ── Location Geocoding panel (curator only) ───────────────────────────────

    # Filter combo labels → API parameter values
    _GEO_FILTER_MAP: dict[str, str] = {
        "All": "all",
        "Failed": "failed",
        "Low Confidence": "low_confidence",
        "Manual Only": "manual",
    }

    def _on_geo_load(self) -> None:
        """Load geocoded locations from the backend into the geo table.

        Calls GET /api/geocode/locations?filter=<value> in a background worker.
        """
        if not self._check_curator():
            self._geo_status.setText("Curator mode required.")
            return
        label = self._geo_filter_combo.currentText()
        filter_val = self._GEO_FILTER_MAP.get(label, "all")
        self._geo_load_btn.setEnabled(False)
        self._geo_status.setText("Loading…")

        def _fetch():
            return requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/locations",
                params={"filter": filter_val},
                timeout=15,
            ).json()

        w = _Worker(_fetch)
        w.finished.connect(self._on_geo_loaded)
        w.error.connect(self._on_geo_load_error)
        self._workers.append(w)
        w.start()

    def _on_geo_loaded(self, data: object) -> None:
        """Populate the geocoding table from the API response.

        Args:
            data: List of location dicts from the backend, or an error dict.
        """
        self._geo_load_btn.setEnabled(True)
        if isinstance(data, dict) and "error" in data:
            self._geo_status.setText(f"Error: {data['error']}")
            return
        # API wraps the list in {"locations": [...]}
        if isinstance(data, dict):
            data = data.get("locations", [])
        if not isinstance(data, list):
            self._geo_status.setText("Unexpected response from server.")
            return

        self._geo_table.setRowCount(0)
        for row in data:
            r = self._geo_table.rowCount()
            self._geo_table.insertRow(r)
            loc_text = row.get("location_text") or ""
            source = row.get("source") or ""
            confidence = str(row.get("confidence") or "")
            lat = row.get("lat")
            lon = row.get("lon")
            lat_str = f"{lat:.6f}" if lat is not None else ""
            lon_str = f"{lon:.6f}" if lon is not None else ""
            manual = "Yes" if row.get("is_manual") else ""
            note = row.get("note") or ""
            for col, val in enumerate(
                [loc_text, source, confidence, lat_str, lon_str, manual, note]
            ):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Store the full row dict on the first column for later retrieval
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self._geo_table.setItem(r, col, item)

        self._geo_status.setText(f"{len(data)} location(s) loaded.")

    def _on_geo_load_error(self, msg: str) -> None:
        """Handle a worker error during geocode location load.

        Args:
            msg: Error message string from the worker thread.
        """
        self._geo_load_btn.setEnabled(True)
        self._geo_status.setText(f"Error: {msg}")
        _log.error("Geocode load error: %s", msg)

    def _on_geo_row_dblclick(self) -> None:
        """Open PlaceManualDialog for the double-clicked geocoding row.

        POSTs the updated coordinates to /api/geocode/location on Save.
        """
        row = self._geo_table.currentRow()
        if row < 0:
            return
        first_item = self._geo_table.item(row, 0)
        if first_item is None:
            return
        row_data: dict = first_item.data(Qt.ItemDataRole.UserRole) or {}
        loc_text = row_data.get("location_text") or (first_item.text())
        lat_val: float | None = row_data.get("lat")
        lon_val: float | None = row_data.get("lon")
        note_val: str = row_data.get("note") or ""

        dlg = PlaceManualDialog(loc_text, lat_val, lon_val, note_val, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payload = {
            "location": dlg.location,
            "lat": dlg.lat,
            "lon": dlg.lon,
            "note": dlg.note,
        }

        def _post():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/location",
                json=payload,
                timeout=10,
            ).json()

        def _done(result: dict) -> None:
            if "error" in result:
                self._geo_status.setText(f"Save error: {result['error']}")
            else:
                self._geo_status.setText(
                    f"Saved manual placement for: {loc_text}"
                )
                # Reload the table to reflect the change
                self._on_geo_load()

        w = _Worker(_post)
        w.finished.connect(_done)
        w.error.connect(lambda e: self._geo_status.setText(f"Save error: {e}"))
        self._workers.append(w)
        w.start()
