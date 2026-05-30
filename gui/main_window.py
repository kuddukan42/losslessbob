import threading

import requests
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget,
)

import gui.styles as styles
from gui.styles import apply_panel_shadow
from gui.widgets.state_store import GuiStateStore
from backend.paths import DATA_DIR

APP_NAME = "LosslessBobLookup"
from backend.version import VERSION


class MainWindow(QMainWindow):
    _status_message = pyqtSignal(str)
    _integrity_update = pyqtSignal(list)  # emits list of unacked event dicts

    def __init__(self, flask_port, ignore_saved_pos=False, parent=None):
        import backend.startup_log as _slog
        _slog.t("MainWindow.__init__: start")
        super().__init__(parent)
        self.flask_port = flask_port
        self.setWindowTitle(self.tr("LosslessBob Checksum Lookup"))
        self.setMinimumSize(800, 500)
        self.setStyleSheet(styles.MAIN_STYLESHEET)

        self.state_store = GuiStateStore(DATA_DIR / "gui_state.json", parent=self)

        _slog.t("MainWindow.__init__: _build_menu")
        self._build_menu()
        _slog.t("MainWindow.__init__: _build_tabs")
        self._build_tabs()
        _slog.t("MainWindow.__init__: _apply_shadows")
        self._apply_shadows()
        _slog.t("MainWindow.__init__: _build_status_bar")
        self._build_status_bar()
        _slog.t("MainWindow.__init__: geometry restore")

        if not ignore_saved_pos:
            self._restore_geometry()
        else:
            self.resize(1100, 750)
        _slog.t("MainWindow.__init__: done")

        self._status_message.connect(self.status_bar.showMessage)
        self._integrity_update.connect(self._on_integrity_update)

        self._status_stop = threading.Event()
        self._status_wake = threading.Event()
        self._status_thread = threading.Thread(
            target=self._status_poll_loop, daemon=True, name="status-poller"
        )
        self._status_thread.start()

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu(self.tr("File"))
        exit_act = QAction(self.tr("Exit"), self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        db_menu = menubar.addMenu(self.tr("Database"))

        check_update_act = QAction(self.tr("Check for Update"), self)
        check_update_act.triggered.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.indexOf(self.setup_tab))
        )
        db_menu.addAction(check_update_act)

        select_db_act = QAction(self.tr("Select Database"), self)
        select_db_act.triggered.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.indexOf(self.setup_tab))
        )
        db_menu.addAction(select_db_act)

        open_folder_act = QAction(self.tr("Open DB Folder"), self)
        open_folder_act.triggered.connect(lambda: self.setup_tab._on_open_folder())
        db_menu.addAction(open_folder_act)

        help_menu = menubar.addMenu(self.tr("Help"))
        help_act = QAction(self.tr("Help"), self)
        help_act.triggered.connect(self._on_help)
        help_menu.addAction(help_act)

        about_act = QAction(self.tr("About"), self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    def _build_tabs(self):
        import backend.startup_log as _slog
        _slog.t("_build_tabs: importing tab modules")
        from gui.lookup_tab import LookupTab
        from gui.rename_tab import RenameTab
        from gui.verify_tab import VerifyTab
        from gui.lbdir_tab import LbdirTab
        from gui.search_tab import SearchTab
        from gui.collection_tab import CollectionTab
        from gui.attachments_tab import AttachmentsTab
        from gui.setup_tab import SetupTab
        from gui.theme_tab import ThemeTab
        from gui.bootlegs_tab import BootlegsTab
        _slog.t("_build_tabs: tab modules imported")

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab order: Lookup(0) Rename(1) Verify(2) lbdir(3) Search(4)
        #            Bootlegs(5) Collection(6) Attachments(7)
        #            Spectrograms(8) DB Editor(9) Scraper(10) Setup(11) Themes(12)
        _slog.t("_build_tabs: init LookupTab")
        self.lookup_tab = LookupTab(self.flask_port)
        _slog.t("_build_tabs: init RenameTab")
        self.rename_tab = RenameTab(state_store=self.state_store, flask_port=self.flask_port)
        _slog.t("_build_tabs: init VerifyTab")
        self.verify_tab = VerifyTab(self.flask_port)
        _slog.t("_build_tabs: init LbdirTab")
        self.lbdir_tab = LbdirTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: init SearchTab")
        self.search_tab = SearchTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: init BootlegsTab")
        self.bootlegs_tab = BootlegsTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: init CollectionTab")
        self.collection_tab = CollectionTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: init AttachmentsTab")
        self.attachments_tab = AttachmentsTab(self.flask_port)
        _slog.t("_build_tabs: init SetupTab")
        self.setup_tab = SetupTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: init ThemeTab")
        self.theme_tab = ThemeTab()

        self.tabs.addTab(self.lookup_tab, self.tr("Lookup"))
        self.tabs.addTab(self.rename_tab, self.tr("Rename Folders"))
        self.tabs.addTab(self.verify_tab, self.tr("Verify"))
        self.tabs.addTab(self.lbdir_tab, self.tr("lbdir"))
        self.tabs.addTab(self.search_tab, self.tr("Search"))
        self.tabs.addTab(self.bootlegs_tab, self.tr("Bootlegs"))
        self.tabs.addTab(self.collection_tab, self.tr("My Collection"))
        _slog.t("_build_tabs: import SpectrogramTab")
        from gui.spectrogram_tab import SpectrogramTab
        _slog.t("_build_tabs: init SpectrogramTab")
        self.spectrogram_tab = SpectrogramTab(self.flask_port)
        _slog.t("_build_tabs: import DbEditTab")
        from gui.dbedit_tab import DbEditTab
        _slog.t("_build_tabs: init DbEditTab")
        self.dbedit_tab = DbEditTab(self.flask_port, state_store=self.state_store)
        _slog.t("_build_tabs: import ScraperTab")
        from gui.scraper_tab import ScraperTab
        _slog.t("_build_tabs: init ScraperTab")
        self.scraper_tab = ScraperTab(self.flask_port)

        self.tabs.addTab(self.attachments_tab, self.tr("Attachments"))
        self.tabs.addTab(self.spectrogram_tab, self.tr("Spectrograms"))
        self.tabs.addTab(self.dbedit_tab, self.tr("DB Editor"))
        self.tabs.addTab(self.scraper_tab, self.tr("Scraper"))
        self.tabs.addTab(self.setup_tab, self.tr("Setup"))
        self.tabs.addTab(self.theme_tab, self.tr("Themes"))

        _slog.t("_build_tabs: importing MapTab")
        try:
            from gui.map_tab import MapTab
            _slog.t("_build_tabs: init MapTab")
            self.map_tab = MapTab(self.flask_port, state_store=self.state_store)
            self.tabs.addTab(self.map_tab, self.tr("Map"))
            self.map_tab.open_in_search.connect(self._on_map_open_in_search)
            self.map_tab.list_in_search.connect(self._on_map_list_in_search)
            self.setup_tab.curator_mode_changed.connect(self.map_tab.set_curator_mode)
            # Apply initial curator state: signal fires during SetupTab.__init__
            # before MapTab exists, so the connection above misses it.
            self.map_tab.set_curator_mode(self.setup_tab.curator_cb.isChecked())
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("Map tab unavailable: %s", exc)

        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.search_tab.lookup_lb.connect(self._on_search_lookup_lb)
        self.collection_tab.lookup_lb.connect(self._on_search_lookup_lb)
        self.bootlegs_tab.open_lb_in_search.connect(self._on_bootleg_open_lb)
        self.bootlegs_tab.bootleg_lbs_loaded.connect(self.search_tab.set_bootleg_lbs)
        self.setup_tab.stats_changed.connect(self._refresh_status)
        self.setup_tab.stats_changed.connect(self.search_tab.load_years)
        self.setup_tab.stats_changed.connect(self.collection_tab.refresh_collection)
        self.setup_tab.search_page_size_changed.connect(self.search_tab.set_page_size)
        self.setup_tab.search_page_size_changed.connect(self.collection_tab.set_page_size)
        self.lookup_tab.lookup_completed.connect(self.rename_tab.populate_from_lookup)
        self.lookup_tab.lookup_completed.connect(
            lambda _d, folders: self.verify_tab.add_folders_from_lookup(folders)
        )
        self.lookup_tab.lookup_completed.connect(
            lambda _d, folders: self.lbdir_tab.add_folders_from_lookup(folders)
        )
        self.collection_tab.send_to_spectrograms.connect(self._on_send_to_spectrograms)
        self.theme_tab.theme_applied.connect(self._on_theme_applied)

        self.theme_tab.load_and_apply_saved()

    def _apply_shadows(self):
        apply_panel_shadow(self.lookup_tab.summary_container)
        apply_panel_shadow(self.lookup_tab.detail_container)
        apply_panel_shadow(self.rename_tab.view)
        apply_panel_shadow(self.search_tab.view)
        apply_panel_shadow(self.collection_tab.coll_view)
        apply_panel_shadow(self.collection_tab.miss_view)
        apply_panel_shadow(self.verify_tab.summary_container)
        apply_panel_shadow(self.verify_tab.detail_container)
        apply_panel_shadow(self.lbdir_tab.summary_container)
        apply_panel_shadow(self.lbdir_tab.detail_container)
        apply_panel_shadow(self.bootlegs_tab.view)

    def _build_status_bar(self):
        from PyQt6.QtCore import Qt
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._integrity_label = QLabel()
        self._integrity_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._integrity_label.setStyleSheet("color: #f0c040; padding: 0 8px;")
        self._integrity_label.hide()
        self._integrity_label.mousePressEvent = lambda _e: self._show_integrity_dialog()
        self.status_bar.addPermanentWidget(self._integrity_label)
        self.status_bar.showMessage(self.tr("Connecting to database…"))

    def _restore_geometry(self):
        restored = self.state_store.restore_window(self)
        if not restored:
            self.resize(1100, 750)

    def closeEvent(self, event):
        self._status_stop.set()
        self._status_wake.set()  # unblock any pending wait
        self.state_store.save_window(self)
        self.state_store.flush()
        super().closeEvent(event)

    def _status_poll_loop(self) -> None:
        """Persistent status-bar polling loop.

        A single long-lived daemon thread that wakes every 10 s (or on demand
        via _refresh_status()).  Avoids per-tick thread-creation overhead that
        is measurable on Windows (~0.5–2 ms per spawn vs ~100 µs on Linux).
        """
        self._do_status_fetch()
        while not self._status_stop.is_set():
            self._status_wake.wait(timeout=10)
            if self._status_stop.is_set():
                break
            self._status_wake.clear()
            self._do_status_fetch()

    def _do_status_fetch(self) -> None:
        """Fetch combined DB + bootleg stats and emit a status-bar message."""
        try:
            s = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/status", timeout=5
            ).json()
            lb = s.get("latest_lb", "?")
            checksums = s.get("total_checksums", 0)
            last_import = s.get("last_import", "Never")
            if last_import and len(str(last_import)) > 10:
                last_import = str(last_import)[:10]
            msg = self.tr("DB: LB-{}  |  Checksums: {}  |  Last import: {}").format(
                lb, f"{checksums:,}", last_import
            )
            bt = s.get("bootlegs", {}).get("total", 0)
            if bt:
                msg += self.tr("  |  Bootlegs: {}").format(f"{bt:,}")
        except Exception:
            msg = self.tr("Database not connected.")
        self._status_message.emit(msg)
        try:
            events = requests.get(
                f"http://127.0.0.1:{self.flask_port}/api/integrity/events?unacked=1",
                timeout=3,
            ).json()
        except Exception:
            events = []
        self._integrity_update.emit(events)

    def _refresh_status(self) -> None:
        """Wake the persistent status poller to fetch immediately."""
        self._status_wake.set()

    def _on_integrity_update(self, events: list) -> None:
        """Show or hide the integrity alert widget based on unacked event count."""
        self._integrity_events = events
        if events:
            self._integrity_label.setText(
                self.tr("⚠ {} integrity alert(s)").format(len(events))
            )
            self._integrity_label.show()
        else:
            self._integrity_label.hide()

    def _show_integrity_dialog(self) -> None:
        """Open a dialog listing unacknowledged integrity events."""
        events = getattr(self, "_integrity_events", [])
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Collection Integrity Alerts"))
        dlg.setMinimumWidth(500)
        layout = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        inner = QVBoxLayout(container)
        if events:
            for ev in events:
                text = "[{}]  LB-{}  {}  —  {}".format(
                    ev.get("occurred_at", "")[:19],
                    ev.get("lb_number", "?"),
                    ev.get("event_type", ""),
                    ev.get("detail", ""),
                )
                inner.addWidget(QLabel(text))
        else:
            inner.addWidget(QLabel(self.tr("No unacknowledged alerts.")))
        inner.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        ack_btn = QPushButton(self.tr("Acknowledge All"))
        ack_btn.clicked.connect(lambda: self._ack_all_integrity(dlg, events))
        layout.addWidget(ack_btn)
        dlg.exec()

    def _ack_all_integrity(self, dlg: QDialog, events: list) -> None:
        ids = [ev["id"] for ev in events if "id" in ev]
        if ids:
            try:
                requests.post(
                    f"http://127.0.0.1:{self.flask_port}/api/integrity/ack",
                    json={"ids": ids},
                    timeout=5,
                )
            except Exception:
                pass
        dlg.accept()
        self._integrity_label.hide()
        self._integrity_events = []

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if widget is self.spectrogram_tab and self.spectrogram_tab._folders:
            self.spectrogram_tab._refresh_inventory()
        if widget is self.setup_tab and not getattr(self.setup_tab, "_sox_checked", False):
            self.setup_tab._sox_checked = True
            self.setup_tab._check_sox()
        if widget is self.dbedit_tab and self.dbedit_tab.table_list.count() == 0:
            self.dbedit_tab.load_tables()
        if widget is self.verify_tab:
            # Carry lookup folders to verify when verify list is empty
            folders = self.lookup_tab.get_lookup_folders()
            if folders:
                self.verify_tab.add_folders_from_lookup(folders)
        if widget is self.lbdir_tab:
            folders = self.lookup_tab.get_lookup_folders()
            if folders:
                self.lbdir_tab.add_folders_from_lookup(folders)

    def _on_theme_applied(self):
        self.setStyleSheet(styles.MAIN_STYLESHEET)
        self.lookup_tab.refresh_colors()
        font_size = self.theme_tab._font_size_spin.value()
        self.search_tab.resize_columns_to_font()
        self.collection_tab.resize_columns_to_font(font_size)
        self.dbedit_tab.resize_columns_to_font()
        self.lookup_tab.resize_columns_to_font()
        self.rename_tab.resize_columns_to_font()
        self.verify_tab.resize_columns_to_font()
        self.lbdir_tab.resize_columns_to_font()
        self.bootlegs_tab.resize_columns_to_font()

    def _on_send_to_spectrograms(self, folders: list):
        self.spectrogram_tab._add_folders(folders)
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.spectrogram_tab))

    def _on_search_lookup_lb(self, lb_number):
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.lookup_tab))
        self.lookup_tab.lookup_lb_number(lb_number)

    def _on_bootleg_open_lb(self, lb_number: int) -> None:
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.search_tab))
        self.search_tab.search_field.setText(str(lb_number))
        self.search_tab._do_search()

    def _on_map_open_in_search(self, lb_number: int) -> None:
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.search_tab))
        self.search_tab.search_field.setText(str(lb_number))
        self.search_tab._do_search()

    def _on_map_list_in_search(self, lb_csv: str) -> None:
        try:
            lb_numbers = [int(x.strip()) for x in lb_csv.split(",") if x.strip()]
        except ValueError:
            return
        if not lb_numbers:
            return
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.search_tab))
        self.search_tab.load_lb_list(lb_numbers)

    def _on_help(self):
        QMessageBox.information(
            self, self.tr("Help"),
            self.tr(
                "LosslessBob Checksum Lookup\n\n"
                "1. Add files or folders to the listbox (drag-drop or Add buttons)\n"
                "2. Click 'Lookup From Listbox' to check checksums\n"
                "3. Or paste checksum text and click 'Lookup From Clipboard'\n"
                "4. Green rows = complete match, Orange = not found, Pink = incomplete set\n\n"
                "Use the Setup tab to import the LosslessBob flat-file database."
            ),
        )

    def _on_about(self):
        import sys, platform
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        info = (
            f"LosslessBob Checksum Lookup\n"
            f"Version: {VERSION}\n\n"
            f"Python: {sys.version.split()[0]}\n"
            f"PyQt6: {PYQT_VERSION_STR}  |  Qt: {QT_VERSION_STR}\n"
            f"Platform: {platform.system()} {platform.release()} "
            f"({'64-bit' if platform.machine().endswith('64') else '32-bit'})\n\n"
            "Cross-platform replacement for the original Windows Checksum_Lookup utility.\n"
            "Supports the LosslessBob Bob Dylan lossless recording archive.\n\n"
            "Built with Python, PyQt6, and Flask."
        )
        QMessageBox.about(self, "About LosslessBob", info)
