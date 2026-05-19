"""Bootleg-CD Catalog tab — browse the LosslessBob LBBCD index."""
from __future__ import annotations

import webbrowser

import requests
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLineEdit, QComboBox, QSpinBox, QLabel, QPushButton,
    QTableView, QAbstractItemView, QHeaderView,
    QGroupBox, QFormLayout, QTextEdit, QSizePolicy,
)

import gui.styles as styles

# ── Constants ─────────────────────────────────────────────────────────────────

HEADERS = [
    "LB Number", "Title", "Date", "Year", "Location",
    "CDs", "LBBCD", "Status", "Owned",
]
_LB_COL     = 0
_TITLE_COL  = 1
_DATE_COL   = 2
_YEAR_COL   = 3
_LOC_COL    = 4
_CD_COL     = 5
_LBBCD_COL  = 6
_STATUS_COL = 7
_OWNED_COL  = 8

_COL_DEFAULTS = [80, 300, 80, 50, 200, 40, 60, 65, 50]

_BG_STATUS = {
    "public":  None,
    "private": "#B3E5FC",
    "missing": "#E0E0E0",
}

_LBBCD_BASE = "http://www.losslessbob.wonderingwhattochoose.com/"


# ── Model ─────────────────────────────────────────────────────────────────────

class _BootlegsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == _LB_COL:
                return f"LB-{row['lb_number']:05d}"
            if col == _TITLE_COL:
                return row.get("title") or "(no title)"
            if col == _DATE_COL:
                return row.get("date_str") or ""
            if col == _YEAR_COL:
                y = row.get("year")
                return str(y) if y else ""
            if col == _LOC_COL:
                return row.get("location") or ""
            if col == _CD_COL:
                return str(row.get("cd_count", 0))
            if col == _LBBCD_COL:
                return f"LBBCD-{row['lbbcd_id']}" if row.get("lbbcd_id") else ""
            if col == _STATUS_COL:
                s = row.get("lb_status") or ""
                return s.capitalize() if s else ""
            if col == _OWNED_COL:
                return "✓" if row.get("owned") else ""
            return ""

        if role == Qt.ItemDataRole.BackgroundRole:
            lb_status = row.get("lb_status") or ""
            hex_c = _BG_STATUS.get(lb_status)
            if hex_c:
                return QColor(hex_c)
            if row.get("owned"):
                return styles.ROW_OWNED
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (_LB_COL, _YEAR_COL, _CD_COL, _LBBCD_COL, _STATUS_COL, _OWNED_COL):
                return Qt.AlignmentFlag.AlignCenter
            return None

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == _STATUS_COL:
                s = row.get("lb_status") or ""
                return f"lb_master status: {s}" if s else None
            if col == _LBBCD_COL and row.get("lbbcd_id"):
                return f"Open LBBCD-{row['lbbcd_id']} detail page"
            return None

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def get_row(self, idx: int) -> dict | None:
        if 0 <= idx < len(self._rows):
            return self._rows[idx]
        return None


# ── Worker threads ─────────────────────────────────────────────────────────────

class _FetchWorker(QThread):
    finished = pyqtSignal(dict)   # {rows, total}
    error    = pyqtSignal(str)

    def __init__(self, port: int, params: dict) -> None:
        super().__init__()
        self.port   = port
        self.params = params

    def run(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.port}/api/bootlegs",
                params=self.params,
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _ScrapeWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, port: int, force: bool) -> None:
        super().__init__()
        self.port  = port
        self.force = force

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.port}/api/bootlegs/scrape",
                json={"force": self.force},
                timeout=10,
            )
            self.finished.emit(resp.json())
        except Exception as e:
            self.error.emit(str(e))


class _StatusPollWorker(QThread):
    """Polls /api/bootlegs/scrape/status until running=False."""
    update  = pyqtSignal(dict)
    stopped = pyqtSignal()

    def __init__(self, port: int) -> None:
        super().__init__()
        self.port      = port
        self._stopping = False

    def stop(self) -> None:
        self._stopping = True

    def run(self) -> None:
        import time
        while not self._stopping:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.port}/api/bootlegs/scrape/status",
                    timeout=5,
                )
                data = resp.json()
                self.update.emit(data)
                if not data.get("running"):
                    break
            except Exception:
                break
            time.sleep(1)
        self.stopped.emit()


class _LbNumbersWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, port: int) -> None:
        super().__init__()
        self.port = port

    def run(self) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.port}/api/bootlegs/lb_numbers",
                timeout=10,
            )
            self.finished.emit(resp.json())
        except Exception:
            self.finished.emit([])


# ── Main tab widget ───────────────────────────────────────────────────────────

class BootlegsTab(QWidget):
    """Browse the LosslessBob Bootleg-CD catalog (LBBCD index)."""

    # Emitted when the user navigates to an LB via the detail pane.
    open_lb_in_search = pyqtSignal(int)
    # Emitted after the bootleg LB-number set is (re)loaded; carries the set.
    bootleg_lbs_loaded = pyqtSignal(object)

    def __init__(self, flask_port: int, parent=None, state_store=None) -> None:
        super().__init__(parent)
        self.flask_port   = flask_port
        self._state_store = state_store
        self._worker:        _FetchWorker | None       = None
        self._scrape_worker: _ScrapeWorker | None      = None
        self._poll_worker:   _StatusPollWorker | None  = None
        self._lb_worker:     _LbNumbersWorker | None   = None
        self._total: int = 0
        self._offset: int = 0
        self._page_size: int = 200
        self._filter_lb: int | None = None   # set externally to pre-filter to one LB
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._do_fetch)
        self._build_ui()
        self._prefetch_lb_numbers()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_bootleg_lb_numbers(self) -> set[int]:
        """Return the cached set of lb_numbers that have bootleg titles."""
        return getattr(self, "_bootleg_lb_set", set())

    def filter_to_lb(self, lb: int) -> None:
        """Pre-filter the tab to show only rows for *lb* and switch page to 0."""
        self._filter_lb = lb
        self._q_edit.setText(f"lb:{lb}")
        self._offset = 0
        self._do_fetch()

    def refresh_lb_numbers(self) -> None:
        """Reload the bootleg LB-number set (call after a scrape completes)."""
        self._prefetch_lb_numbers()

    # ── UI build ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Filter bar ──────────────────────────────────────────────────────
        filter_bar = QHBoxLayout()

        self._q_edit = QLineEdit()
        self._q_edit.setPlaceholderText("Search title / location…")
        self._q_edit.textChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._q_edit, stretch=2)

        filter_bar.addWidget(QLabel("Year:"))
        self._year_min = QSpinBox()
        self._year_min.setRange(0, 2099)
        self._year_min.setSpecialValueText("Any")
        self._year_min.setValue(0)
        self._year_min.setFixedWidth(65)
        self._year_min.valueChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._year_min)
        filter_bar.addWidget(QLabel("–"))
        self._year_max = QSpinBox()
        self._year_max.setRange(0, 2099)
        self._year_max.setSpecialValueText("Any")
        self._year_max.setValue(0)
        self._year_max.setFixedWidth(65)
        self._year_max.valueChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._year_max)

        filter_bar.addWidget(QLabel("CDs:"))
        self._cd_combo = QComboBox()
        self._cd_combo.addItems(["All", "0", "1", "2", "3+"])
        self._cd_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._cd_combo)

        self._status_combo = QComboBox()
        self._status_combo.addItem("All statuses", userData=None)
        self._status_combo.addItem("Public",        userData="public")
        self._status_combo.addItem("Private",       userData="private")
        self._status_combo.addItem("Missing",       userData="missing")
        self._status_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._status_combo)

        self._owned_combo = QComboBox()
        self._owned_combo.addItem("All",       userData=None)
        self._owned_combo.addItem("Owned",     userData=True)
        self._owned_combo.addItem("Not owned", userData=False)
        self._owned_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._owned_combo)

        self._lbbcd_combo = QComboBox()
        self._lbbcd_combo.addItem("All",          userData=None)
        self._lbbcd_combo.addItem("Has LBBCD",    userData=True)
        self._lbbcd_combo.addItem("No LBBCD",     userData=False)
        self._lbbcd_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_bar.addWidget(self._lbbcd_combo)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear_filters)
        filter_bar.addWidget(self._clear_btn)

        root.addLayout(filter_bar)

        # ── Status / pagination bar ─────────────────────────────────────────
        status_bar = QHBoxLayout()
        self._status_lbl = QLabel("No results.")
        status_bar.addWidget(self._status_lbl)
        status_bar.addStretch()
        self._prev_btn = QPushButton("← Prev")
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._prev_page)
        status_bar.addWidget(self._prev_btn)
        self._page_lbl = QLabel("")
        status_bar.addWidget(self._page_lbl)
        self._next_btn = QPushButton("Next →")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._next_page)
        status_bar.addWidget(self._next_btn)
        root.addLayout(status_bar)

        # ── Splitter: table | detail ────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.model = _BootlegsModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.view.doubleClicked.connect(self._on_double_click)
        splitter.addWidget(self.view)

        if self._state_store:
            self._state_store.attach_table(
                self.view, "bootlegs.main", defaults=_COL_DEFAULTS
            )

        # Detail pane
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(8, 4, 4, 4)

        detail_group = QGroupBox("Bootleg Detail")
        form = QFormLayout(detail_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._d_lb       = QLabel("—")
        self._d_title    = QLabel("—")
        self._d_title.setWordWrap(True)
        self._d_date     = QLabel("—")
        self._d_location = QLabel("—")
        self._d_location.setWordWrap(True)
        self._d_cds      = QLabel("—")
        self._d_status   = QLabel("—")
        self._d_lbbcd    = QLabel("—")

        form.addRow("LB Number:",  self._d_lb)
        form.addRow("Title:",      self._d_title)
        form.addRow("Date:",       self._d_date)
        form.addRow("Location:",   self._d_location)
        form.addRow("CDs:",        self._d_cds)
        form.addRow("LB Status:",  self._d_status)
        form.addRow("LBBCD:",      self._d_lbbcd)

        self._open_lb_btn = QPushButton("Open in Search Tab")
        self._open_lb_btn.clicked.connect(self._on_open_lb)
        self._open_lb_btn.setEnabled(False)

        self._open_lbbcd_btn = QPushButton("Open LBBCD Page")
        self._open_lbbcd_btn.clicked.connect(self._on_open_lbbcd)
        self._open_lbbcd_btn.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._open_lb_btn)
        btn_row.addWidget(self._open_lbbcd_btn)
        btn_row.addStretch()

        detail_layout.addWidget(detail_group)
        detail_layout.addLayout(btn_row)

        also_group = QGroupBox("Other bootleg titles for this LB")
        also_layout = QVBoxLayout(also_group)
        self._also_text = QTextEdit()
        self._also_text.setReadOnly(True)
        self._also_text.setMaximumHeight(110)
        also_layout.addWidget(self._also_text)
        detail_layout.addWidget(also_group)
        detail_layout.addStretch()

        splitter.addWidget(detail_widget)
        splitter.setSizes([700, 300])
        root.addWidget(splitter)

    # ── Filter helpers ──────────────────────────────────────────────────────

    def _on_filter_changed(self) -> None:
        self._filter_lb = None
        self._offset = 0
        self._debounce.start(300)

    def _on_clear_filters(self) -> None:
        self._filter_lb = None
        self._q_edit.blockSignals(True)
        self._q_edit.clear()
        self._q_edit.blockSignals(False)
        self._year_min.blockSignals(True)
        self._year_min.setValue(0)
        self._year_min.blockSignals(False)
        self._year_max.blockSignals(True)
        self._year_max.setValue(0)
        self._year_max.blockSignals(False)
        self._cd_combo.blockSignals(True)
        self._cd_combo.setCurrentIndex(0)
        self._cd_combo.blockSignals(False)
        self._status_combo.blockSignals(True)
        self._status_combo.setCurrentIndex(0)
        self._status_combo.blockSignals(False)
        self._owned_combo.blockSignals(True)
        self._owned_combo.setCurrentIndex(0)
        self._owned_combo.blockSignals(False)
        self._lbbcd_combo.blockSignals(True)
        self._lbbcd_combo.setCurrentIndex(0)
        self._lbbcd_combo.blockSignals(False)
        self._offset = 0
        self._do_fetch()

    # ── Fetch ───────────────────────────────────────────────────────────────

    def _build_params(self) -> dict:
        params: dict = {
            "limit":  self._page_size,
            "offset": self._offset,
        }

        # If pre-filtered to one LB, bypass text filter
        if self._filter_lb is not None:
            # We use a special "lb:N" prefix understood only by the GUI layer;
            # translate it to a direct lb_number filter via the by_lb endpoint
            # (handled in _do_fetch).
            return params

        q = self._q_edit.text().strip()
        if q:
            params["q"] = q

        y_min = self._year_min.value()
        y_max = self._year_max.value()
        if y_min:
            params["year_min"] = y_min
        if y_max:
            params["year_max"] = y_max

        cd_text = self._cd_combo.currentText()
        if cd_text == "0":
            params["cd_min"] = 0;  params["cd_max"] = 0
        elif cd_text == "1":
            params["cd_min"] = 1;  params["cd_max"] = 1
        elif cd_text == "2":
            params["cd_min"] = 2;  params["cd_max"] = 2
        elif cd_text == "3+":
            params["cd_min"] = 3

        lb_status = self._status_combo.currentData()
        if lb_status:
            params["lb_status"] = lb_status

        owned = self._owned_combo.currentData()
        if owned is True:
            params["owned"] = "true"
        elif owned is False:
            params["owned"] = "false"

        has_lbbcd = self._lbbcd_combo.currentData()
        if has_lbbcd is True:
            params["has_lbbcd"] = "true"
        elif has_lbbcd is False:
            params["has_lbbcd"] = "false"

        return params

    def _do_fetch(self) -> None:
        self._status_lbl.setText("Loading…")
        params = self._build_params()
        if self._worker and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.error.disconnect()
        self._worker = _FetchWorker(self.flask_port, params)
        self._worker.finished.connect(self._on_fetched)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.start()

    def _on_fetched(self, data: dict) -> None:
        rows  = data.get("rows", [])
        total = data.get("total", len(rows))
        self._total = total
        self.model.set_rows(rows)
        self._update_status(total)
        self._update_pagination()

    def _on_fetch_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")

    def _update_status(self, total: int) -> None:
        page = self._offset // self._page_size + 1
        pages = max(1, -(-total // self._page_size))
        self._status_lbl.setText(
            f"{total:,} bootleg title(s)  —  page {page} of {pages}"
        )

    def _update_pagination(self) -> None:
        page  = self._offset // self._page_size + 1
        pages = max(1, -(-self._total // self._page_size))
        self._prev_btn.setEnabled(self._offset > 0)
        self._next_btn.setEnabled(page < pages)
        self._page_lbl.setText(f"Page {page} of {pages}")

    def _prev_page(self) -> None:
        self._offset = max(0, self._offset - self._page_size)
        self._do_fetch()

    def _next_page(self) -> None:
        self._offset += self._page_size
        self._do_fetch()

    # ── Detail pane ──────────────────────────────────────────────────────────

    def _on_row_changed(self, current, _previous) -> None:
        row = self.model.get_row(current.row())
        if row is None:
            self._clear_detail()
            return
        lb = row["lb_number"]
        self._d_lb.setText(f"LB-{lb:05d}")
        self._d_title.setText(row.get("title") or "(no title)")
        self._d_date.setText(row.get("date_str") or "—")
        self._d_location.setText(row.get("location") or "—")
        self._d_cds.setText(str(row.get("cd_count", 0)))
        self._d_status.setText((row.get("lb_status") or "").capitalize() or "—")
        lbbcd_id = row.get("lbbcd_id")
        if lbbcd_id:
            self._d_lbbcd.setText(f"LBBCD-{lbbcd_id}")
            self._open_lbbcd_btn.setEnabled(True)
        else:
            self._d_lbbcd.setText("—")
            self._open_lbbcd_btn.setEnabled(False)
        self._open_lb_btn.setEnabled(True)
        self._open_lb_btn.setProperty("lb", lb)
        self._open_lbbcd_btn.setProperty("lbbcd_url", row.get("lbbcd_url") or "")
        self._load_also_titles(lb, exclude_row_id=row.get("id"))

    def _clear_detail(self) -> None:
        for lbl in (self._d_lb, self._d_title, self._d_date,
                    self._d_location, self._d_cds, self._d_status, self._d_lbbcd):
            lbl.setText("—")
        self._open_lb_btn.setEnabled(False)
        self._open_lbbcd_btn.setEnabled(False)
        self._also_text.clear()

    def _load_also_titles(self, lb: int, exclude_row_id: int | None) -> None:
        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/bootlegs/by_lb/{lb}",
                timeout=5,
            )
            all_rows = resp.json()
        except Exception:
            all_rows = []
        others = [r for r in all_rows if r.get("id") != exclude_row_id]
        if others:
            lines = [f"• {r.get('title') or '(no title)'} ({r.get('date_str', '')})"
                     for r in others]
            self._also_text.setPlainText("\n".join(lines))
        else:
            self._also_text.setPlainText("(only bootleg title for this LB)")

    def _on_open_lb(self) -> None:
        lb = self._open_lb_btn.property("lb")
        if lb:
            self.open_lb_in_search.emit(int(lb))

    def _on_open_lbbcd(self) -> None:
        url = self._open_lbbcd_btn.property("lbbcd_url") or ""
        if url:
            if not url.startswith("http"):
                url = _LBBCD_BASE + url.lstrip("/")
            webbrowser.open(url)

    def _on_double_click(self, index) -> None:
        row = self.model.get_row(index.row())
        if row:
            lb = row["lb_number"]
            url = (f"http://www.losslessbob.wonderingwhattochoose.com"
                   f"/detail/LB-{lb:05d}.html")
            webbrowser.open(url)

    # ── Bootleg LB number set ─────────────────────────────────────────────────

    def _prefetch_lb_numbers(self) -> None:
        self._lb_worker = _LbNumbersWorker(self.flask_port)
        self._lb_worker.finished.connect(self._on_lb_numbers_loaded)
        self._lb_worker.start()

    def _on_lb_numbers_loaded(self, lb_list: list) -> None:
        self._bootleg_lb_set: set[int] = set(lb_list)
        self.bootleg_lbs_loaded.emit(self._bootleg_lb_set)

    # ── Scrape control (called from Setup tab signal) ─────────────────────────

    def start_scrape(self, force: bool = False) -> None:
        """Kick off a catalog scrape and start polling for status updates."""
        self._scrape_worker = _ScrapeWorker(self.flask_port, force)
        self._scrape_worker.finished.connect(self._on_scrape_started)
        self._scrape_worker.error.connect(lambda e: None)  # Setup tab handles errors
        self._scrape_worker.start()

    def _on_scrape_started(self, data: dict) -> None:
        if data.get("ok"):
            self._poll_worker = _StatusPollWorker(self.flask_port)
            self._poll_worker.stopped.connect(self._on_scrape_done)
            self._poll_worker.start()

    def _on_scrape_done(self) -> None:
        self.refresh_lb_numbers()
        self._do_fetch()

    # ── Font resize ───────────────────────────────────────────────────────────

    def resize_columns_to_font(self) -> None:
        self.view.resizeColumnsToContents()
