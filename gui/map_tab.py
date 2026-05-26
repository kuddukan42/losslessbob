"""Map tab: browser-only map launcher with filters and curator geocoding panel."""

import logging

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QUrl

log = logging.getLogger(__name__)

_FLASK_PORT = 5174


# ── Worker threads ─────────────────────────────────────────────────────────────

class _GeocodeRunThread(QThread):
    """POST /api/geocode/run without blocking the GUI."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, retry_failed: bool) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.retry_failed = retry_failed

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/run",
                json={"retry_failed": self.retry_failed},
                timeout=15,
            )
            if resp.ok:
                self.finished.emit(resp.json())
            elif resp.status_code == 409:
                self.finished.emit({"error": "already running", "status_code": 409})
            else:
                self.finished.emit({"error": resp.text, "status_code": resp.status_code})
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


class _GeocodeStatusThread(QThread):
    """Poll GET /api/geocode/status every 2 s while geocoding is running."""

    status_update = pyqtSignal(dict)

    def __init__(self, flask_port: int) -> None:
        super().__init__()
        self.flask_port = flask_port
        self._running = True

    def run(self) -> None:
        while self._running:
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/geocode/status",
                    timeout=5,
                )
                self.status_update.emit(resp.json())
            except Exception:
                pass
            self.msleep(2000)

    def stop(self) -> None:
        """Signal the polling loop to exit on the next iteration."""
        self._running = False


class _GeoWorker(QThread):
    """Generic background worker for geocoding API calls."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self._fn())
        except Exception as exc:
            self.error.emit(str(exc))


class _PurgeGeoThread(QThread):
    """POST /api/geocode/purge in a background thread."""

    finished = pyqtSignal(dict)

    def __init__(self, flask_port: int, scope: str) -> None:
        super().__init__()
        self.flask_port = flask_port
        self.scope = scope

    def run(self) -> None:
        try:
            resp = requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/purge",
                json={"scope": self.scope},
                timeout=15,
            )
            self.finished.emit(resp.json())
        except Exception as exc:
            self.finished.emit({"error": str(exc)})


# ── Dialogs ────────────────────────────────────────────────────────────────────

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
        self.setWindowTitle(self.tr("Place Manually"))
        self.setMinimumWidth(360)

        form = QFormLayout(self)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)

        loc_lbl = QLabel(location_text)
        loc_lbl.setWordWrap(True)
        form.addRow(self.tr("Location:"), loc_lbl)

        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(6)
        self._lat_spin.setSingleStep(0.0001)
        self._lat_spin.setValue(lat if lat is not None else 0.0)
        form.addRow(self.tr("Lat:"), self._lat_spin)

        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(6)
        self._lon_spin.setSingleStep(0.0001)
        self._lon_spin.setValue(lon if lon is not None else 0.0)
        form.addRow(self.tr("Lon:"), self._lon_spin)

        self._note_edit = QLineEdit(note)
        self._note_edit.setPlaceholderText(self.tr("Optional curator note…"))
        form.addRow(self.tr("Note:"), self._note_edit)

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


# ── Main tab widget ────────────────────────────────────────────────────────────

class MapTab(QWidget):
    """Map tab: opens the Leaflet map in the system browser with optional URL filters.

    Includes curator-only Geocoding and Location Overrides panels, consolidated from
    the former Setup tab and DB Editor geocoding sections.

    Signals:
        open_in_search: Stub — retained for backward-compatible signal wiring in
            main_window.py. Not emitted (map now opens in browser).
        list_in_search: Stub — same reason.

    Args:
        flask_port: Port the local Flask server is listening on.
        state_store: Optional GuiStateStore (reserved for future use).
        parent: Optional Qt parent widget.
    """

    open_in_search = pyqtSignal(int)   # stub — kept for wiring compatibility
    list_in_search = pyqtSignal(str)   # stub — kept for wiring compatibility

    def __init__(self, flask_port: int, state_store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flask_port = flask_port
        self._state_store = state_store
        self._geocode_run_thread: _GeocodeRunThread | None = None
        self._geocode_status_thread: _GeocodeStatusThread | None = None
        self._geo_workers: list[_GeoWorker] = []
        self._purge_geo_thread: _PurgeGeoThread | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the full tab layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel(self.tr("Map — Concert Locations"))
        title.setStyleSheet("font-weight: 700; font-size: 11pt;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Primary open button
        open_btn = QPushButton(self.tr("Open Map in Browser"))
        open_btn.setToolTip(
            self.tr("Opens http://localhost:{}/map in your default web browser").format(self.flask_port)
        )
        open_btn.setMinimumHeight(32)
        open_btn.clicked.connect(self._open_map)
        layout.addWidget(open_btn)

        note = QLabel(self.tr(
            "The map opens in your default web browser. "
            "Use the filters below to pre-filter which concerts are shown."
        ))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(note)

        # Map Filters group
        filters_box = QGroupBox(self.tr("Map Filters"))
        fl = QVBoxLayout(filters_box)
        fl.setSpacing(4)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(self.tr("Year from:")))
        self._year_from = QSpinBox()
        self._year_from.setRange(1900, 2100)
        self._year_from.setValue(1961)
        self._year_from.setFixedWidth(70)
        row1.addWidget(self._year_from)
        row1.addWidget(QLabel(self.tr("to:")))
        self._year_to = QSpinBox()
        self._year_to.setRange(1900, 2100)
        self._year_to.setValue(2030)
        self._year_to.setFixedWidth(70)
        row1.addWidget(self._year_to)
        row1.addSpacing(16)
        row1.addWidget(QLabel(self.tr("LB Status:")))
        self._status_combo = QComboBox()
        self._status_combo.addItem(self.tr("All"), "")
        self._status_combo.addItem(self.tr("Public"), "public")
        self._status_combo.addItem(self.tr("Private"), "private")
        self._status_combo.addItem(self.tr("Missing"), "missing")
        row1.addWidget(self._status_combo)
        row1.addStretch()
        fl.addLayout(row1)

        row2 = QHBoxLayout()
        self._owned_cb = QCheckBox(self.tr("Owned only"))
        row2.addWidget(self._owned_cb)
        row2.addSpacing(16)
        row2.addWidget(QLabel(self.tr("Text filter:")))
        self._text_filter = QLineEdit()
        self._text_filter.setPlaceholderText(self.tr("location or LB# …"))
        self._text_filter.setFixedWidth(200)
        row2.addWidget(self._text_filter)
        row2.addStretch()
        fl.addLayout(row2)

        apply_btn = QPushButton(self.tr("Apply Filters and Open Map"))
        apply_btn.clicked.connect(self._open_filtered_map)
        fl.addWidget(apply_btn)

        layout.addWidget(filters_box)

        # Geocoding group (curator-only)
        self._geocode_box = QGroupBox(self.tr("Geocoding"))
        geo_layout = QVBoxLayout(self._geocode_box)
        geo_layout.addWidget(QLabel(
            self.tr("Geocode entries.location → lat/lon via Nominatim (curator only)")
        ))
        geo_opts = QHBoxLayout()
        self._geo_retry_cb = QCheckBox(self.tr("Retry Failed"))
        self._geo_retry_cb.setToolTip(
            self.tr("Re-attempt entries that previously failed geocoding")
        )
        geo_opts.addWidget(self._geo_retry_cb)
        self._geo_run_btn = QPushButton(self.tr("Run Geocoder"))
        self._geo_run_btn.clicked.connect(self._on_geocode_run)
        geo_opts.addWidget(self._geo_run_btn)
        geo_opts.addStretch()
        geo_layout.addLayout(geo_opts)
        self._geo_status_label = QLabel(self.tr("Status: idle"))
        geo_layout.addWidget(self._geo_status_label)

        purge_row = QHBoxLayout()
        self._geo_purge_failed_btn = QPushButton(self.tr("Purge Failed/Null"))
        self._geo_purge_failed_btn.setToolTip(
            self.tr("Remove cached geocoding entries where geocoding failed or returned no result")
        )
        self._geo_purge_failed_btn.clicked.connect(self._on_geocode_purge_failed)
        purge_row.addWidget(self._geo_purge_failed_btn)

        self._geo_purge_all_btn = QPushButton(self.tr("Purge All…"))
        self._geo_purge_all_btn.setToolTip(
            self.tr("Remove ALL cached geocoding data — manual overrides will also be lost")
        )
        self._geo_purge_all_btn.clicked.connect(self._on_geocode_purge_all)
        purge_row.addWidget(self._geo_purge_all_btn)
        purge_row.addStretch()
        geo_layout.addLayout(purge_row)

        self._geo_purge_status_label = QLabel("")
        geo_layout.addWidget(self._geo_purge_status_label)

        self._geocode_box.setVisible(False)
        layout.addWidget(self._geocode_box)

        # Location Overrides group (curator-only)
        self._overrides_box = QGroupBox(self.tr("Location Overrides"))
        ov_layout = QVBoxLayout(self._overrides_box)

        ov_filter_row = QHBoxLayout()
        ov_filter_row.addWidget(QLabel(self.tr("Filter:")))
        self._geo_filter_combo = QComboBox()
        self._geo_filter_combo.addItem(self.tr("All"), "all")
        self._geo_filter_combo.addItem(self.tr("Failed"), "failed")
        self._geo_filter_combo.addItem(self.tr("Low Confidence"), "low_confidence")
        self._geo_filter_combo.addItem(self.tr("Manual Only"), "manual")
        ov_filter_row.addWidget(self._geo_filter_combo)
        self._geo_load_btn = QPushButton(self.tr("Load"))
        self._geo_load_btn.setToolTip(self.tr("Fetch locations from /api/geocode/locations"))
        self._geo_load_btn.clicked.connect(self._on_geo_load)
        ov_filter_row.addWidget(self._geo_load_btn)
        ov_filter_row.addStretch()
        ov_layout.addLayout(ov_filter_row)

        self._geo_table = QTableWidget(0, 8)
        self._geo_table.setHorizontalHeaderLabels([
            self.tr("Location Text"), self.tr("LB#"), self.tr("Source"), self.tr("Confidence"),
            self.tr("Lat"), self.tr("Lon"), self.tr("Manual?"), self.tr("Note"),
        ])
        self._geo_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._geo_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self._geo_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for col in range(2, 8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._geo_table.setMinimumHeight(140)
        self._geo_table.doubleClicked.connect(self._on_geo_row_dblclick)
        ov_layout.addWidget(self._geo_table)

        self._geo_info_label = QLabel("")
        self._geo_info_label.setWordWrap(True)
        ov_layout.addWidget(self._geo_info_label)

        self._overrides_box.setVisible(False)
        layout.addWidget(self._overrides_box)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_curator_mode(self, enabled: bool) -> None:
        """Show or hide curator-only panels.

        Args:
            enabled: True to show geocoding and overrides groups.
        """
        self._geocode_box.setVisible(enabled)
        self._overrides_box.setVisible(enabled)

    # ------------------------------------------------------------------
    # Map open helpers
    # ------------------------------------------------------------------

    def _open_map(self) -> None:
        """Open the map URL in the system default browser."""
        QDesktopServices.openUrl(QUrl(f"http://localhost:{self.flask_port}/map"))

    def _open_filtered_map(self) -> None:
        """Build a filtered map URL from the filter controls and open it."""
        params: list[str] = []
        year_from = self._year_from.value()
        year_to = self._year_to.value()
        if year_from != 1961:
            params.append(f"year_min={year_from}")
        if year_to != 2030:
            params.append(f"year_max={year_to}")
        lb_status = self._status_combo.currentData() or ""
        if lb_status:
            params.append(f"lb_status={lb_status}")
        if self._owned_cb.isChecked():
            params.append("owned=1")
        q = self._text_filter.text().strip()
        if q:
            from urllib.parse import quote
            params.append(f"q={quote(q)}")
        base = f"http://localhost:{self.flask_port}/map"
        url = f"{base}?{'&'.join(params)}" if params else base
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------------
    # Geocoder (curator-only)
    # ------------------------------------------------------------------

    def _on_geocode_run(self) -> None:
        """Start the Nominatim geocoder in a background thread.

        POSTs to /api/geocode/run; polls status on success.
        """
        retry = self._geo_retry_cb.isChecked()
        self._geo_run_btn.setEnabled(False)
        self._geo_status_label.setText(self.tr("Status: starting…"))
        self._geocode_run_thread = _GeocodeRunThread(self.flask_port, retry)
        self._geocode_run_thread.finished.connect(self._on_geocode_started)
        self._geocode_run_thread.start()

    def _on_geocode_started(self, result: dict) -> None:
        """Handle immediate response from POST /api/geocode/run.

        Args:
            result: JSON response dict including optional error/status_code keys.
        """
        if result.get("status_code") == 409 or result.get("already_running"):
            self._geo_status_label.setText(self.tr("Status: already running"))
            self._geo_run_btn.setEnabled(True)
            return
        if "error" in result and "status_code" not in result:
            self._geo_status_label.setText(
                self.tr("Status: error — {}").format(result["error"])
            )
            self._geo_run_btn.setEnabled(True)
            return
        self._geo_status_label.setText(self.tr("Status: running…"))
        self._geocode_status_thread = _GeocodeStatusThread(self.flask_port)
        self._geocode_status_thread.status_update.connect(self._on_geocode_status)
        self._geocode_status_thread.start()

    def _on_geocode_status(self, status: dict) -> None:
        """Update the geocode progress label from a polling update.

        Args:
            status: JSON payload from GET /api/geocode/status.
        """
        running = status.get("running", False)
        done = status.get("done", 0)
        total = status.get("total", 0)
        current = status.get("current", "")
        errors = status.get("errors", 0)
        succeeded = status.get("succeeded", 0)
        stage = status.get("stage", "")

        if running:
            pct = int(done / total * 100) if total else 0
            parts = [f"{done} / {total}  ({pct}%)"]
            stage_map = {
                "querying": self.tr("querying Nominatim…"),
                "sleeping": self.tr("waiting (rate limit)…"),
                "saving": self.tr("saving…"),
                "starting": self.tr("starting…"),
            }
            if stage in stage_map:
                parts.append(stage_map[stage])
            if current:
                parts.append(current)
            remaining = total - done
            if remaining > 0 and done > 0:
                eta_s = int(remaining * 1.1)
                if eta_s >= 3600:
                    parts.append(self.tr("~{0}h {1}m left").format(
                        eta_s // 3600, (eta_s % 3600) // 60))
                elif eta_s >= 60:
                    parts.append(self.tr("~{0}m {1}s left").format(eta_s // 60, eta_s % 60))
                else:
                    parts.append(self.tr("~{}s left").format(eta_s))
            if succeeded + errors > 0:
                parts.append(self.tr("{0} ok  |  {1} failed").format(succeeded, errors))
            self._geo_status_label.setText("  ·  ".join(parts))
        else:
            if self._geocode_status_thread is not None:
                self._geocode_status_thread.stop()
                self._geocode_status_thread = None
            self._geo_run_btn.setEnabled(True)
            self._geo_status_label.setText(
                self.tr("Done: {0} geocoded, {1} failed").format(succeeded, errors)
            )

    def _on_geocode_purge_failed(self) -> None:
        """Purge geocoding rows where geocoding failed or returned no coordinates."""
        from PyQt6.QtWidgets import QMessageBox
        ans = QMessageBox.question(
            self,
            self.tr("Purge Failed Geocoding"),
            self.tr(
                "Remove all cached geocoding entries that failed or returned no result?\n\n"
                "This frees up those locations to be re-geocoded on the next run."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._start_purge("failed")

    def _on_geocode_purge_all(self) -> None:
        """Purge the entire geocoding cache, including manual overrides."""
        from PyQt6.QtWidgets import QMessageBox
        ans = QMessageBox.warning(
            self,
            self.tr("Purge All Geocoding Data"),
            self.tr(
                "Remove ALL cached geocoding data from the database?\n\n"
                "This includes manual pin placements. All coordinates will be lost\n"
                "and must be re-geocoded from scratch.\n\n"
                "This cannot be undone."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._start_purge("all")

    def _start_purge(self, scope: str) -> None:
        self._geo_purge_failed_btn.setEnabled(False)
        self._geo_purge_all_btn.setEnabled(False)
        self._geo_purge_status_label.setText(self.tr("Purging…"))
        self._purge_geo_thread = _PurgeGeoThread(self.flask_port, scope)
        self._purge_geo_thread.finished.connect(self._on_purge_done)
        self._purge_geo_thread.start()

    def _on_purge_done(self, result: dict) -> None:
        self._geo_purge_failed_btn.setEnabled(True)
        self._geo_purge_all_btn.setEnabled(True)
        if "error" in result:
            self._geo_purge_status_label.setText(
                self.tr("Purge failed: {}").format(result["error"])
            )
            return
        deleted = result.get("deleted", 0)
        self._geo_purge_status_label.setText(
            self.tr("Purged {0} row(s). Run geocoder to rebuild.").format(deleted)
        )

    # ------------------------------------------------------------------
    # Location Overrides (curator-only)
    # ------------------------------------------------------------------

    def _on_geo_load(self) -> None:
        """Load geocoded locations from the backend into the overrides table."""
        filter_val = self._geo_filter_combo.currentData() or "all"
        self._geo_load_btn.setEnabled(False)
        self._geo_info_label.setText(self.tr("Loading…"))

        def _fetch():
            return requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/locations",
                params={"filter": filter_val},
                timeout=15,
            ).json()

        w = _GeoWorker(_fetch)
        w.finished.connect(self._on_geo_loaded)
        w.error.connect(self._on_geo_load_error)
        self._geo_workers.append(w)
        w.start()

    def _on_geo_loaded(self, data: object) -> None:
        """Populate the overrides table from the API response.

        Args:
            data: List of location dicts, or dict with error key.
        """
        self._geo_load_btn.setEnabled(True)
        if isinstance(data, dict) and "error" in data:
            self._geo_info_label.setText(self.tr("Error: {}").format(data["error"]))
            return
        if isinstance(data, dict):
            data = data.get("locations", [])
        if not isinstance(data, list):
            self._geo_info_label.setText(self.tr("Unexpected response from server."))
            return

        self._geo_table.setRowCount(0)
        for row in data:
            r = self._geo_table.rowCount()
            self._geo_table.insertRow(r)
            lat = row.get("lat")
            lon = row.get("lon")
            lb_numbers = row.get("lb_numbers") or row.get("lb_number") or ""
            for col, val in enumerate([
                row.get("location_text") or "",
                str(lb_numbers),
                row.get("source") or "",
                str(row.get("confidence") or ""),
                f"{lat:.6f}" if lat is not None else "",
                f"{lon:.6f}" if lon is not None else "",
                self.tr("Yes") if row.get("is_manual") else "",
                row.get("note") or "",
            ]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self._geo_table.setItem(r, col, item)

        self._geo_info_label.setText(self.tr("{} location(s) loaded.").format(len(data)))

    def _on_geo_load_error(self, msg: str) -> None:
        """Handle a worker error during location load.

        Args:
            msg: Error message string from the worker thread.
        """
        self._geo_load_btn.setEnabled(True)
        self._geo_info_label.setText(self.tr("Error: {}").format(msg))
        log.error("Geo load error: %s", msg)

    def _on_geo_row_dblclick(self) -> None:
        """Open PlaceManualDialog for the double-clicked row and POST the result."""
        row = self._geo_table.currentRow()
        if row < 0:
            return
        first_item = self._geo_table.item(row, 0)
        if first_item is None:
            return
        row_data: dict = first_item.data(Qt.ItemDataRole.UserRole) or {}
        loc_text = row_data.get("location_text") or first_item.text()
        lat_val: float | None = row_data.get("lat")
        lon_val: float | None = row_data.get("lon")
        note_val: str = row_data.get("note") or ""
        lb_number_val: str | None = row_data.get("lb_number") or None

        dlg = PlaceManualDialog(loc_text, lat_val, lon_val, note_val, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payload: dict = {
            "location": dlg.location,
            "lat": dlg.lat,
            "lon": dlg.lon,
            "note": dlg.note,
        }
        if lb_number_val:
            payload["lb_number"] = lb_number_val

        def _post():
            return requests.post(
                f"http://127.0.0.1:{self.flask_port}/api/geocode/location",
                json=payload,
                timeout=10,
            ).json()

        def _done(result: dict) -> None:
            if "error" in result:
                self._geo_info_label.setText(
                    self.tr("Save error: {}").format(result["error"])
                )
            else:
                self._geo_info_label.setText(
                    self.tr("Saved manual placement for: {}").format(loc_text)
                )
                self._on_geo_load()

        w = _GeoWorker(_post)
        w.finished.connect(_done)
        w.error.connect(
            lambda e: self._geo_info_label.setText(self.tr("Save error: {}").format(e))
        )
        self._geo_workers.append(w)
        w.start()
