import requests
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QAction
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QMenu, QComboBox, QApplication, QInputDialog,
)

_C_DIRTY  = QColor("#fffbe6")
_C_WARN   = QColor("#fff0f0")
_C_AUDIT  = QColor("#f0f0ff")
_C_RDONLY = QColor("#f4f4f4")


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
        from PyQt6.QtWidgets import QGroupBox
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
