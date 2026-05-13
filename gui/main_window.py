import threading

import requests
from PyQt6.QtCore import QSettings, QSize, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QMessageBox,
)

import gui.styles as styles
from gui.styles import apply_panel_shadow
from backend.paths import DATA_DIR

APP_NAME = "LosslessBobLookup"
VERSION = "1.0.0"


class MainWindow(QMainWindow):
    _status_message = pyqtSignal(str)

    def __init__(self, flask_port, ignore_saved_pos=False, parent=None):
        super().__init__(parent)
        self.flask_port = flask_port
        self.setWindowTitle("LosslessBob Checksum Lookup")
        self.setMinimumSize(800, 500)
        self.setStyleSheet(styles.MAIN_STYLESHEET)

        _settings_path = str(DATA_DIR / "settings.ini")
        self._settings = QSettings(_settings_path, QSettings.Format.IniFormat)

        self._build_menu()
        self._build_tabs()
        self._apply_shadows()
        self._build_status_bar()

        if not ignore_saved_pos:
            self._restore_geometry()
        else:
            self.resize(1100, 750)

        self._status_message.connect(self.status_bar.showMessage)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(10000)
        QTimer.singleShot(0, self._refresh_status)

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        db_menu = menubar.addMenu("Database")

        check_update_act = QAction("Check for Update", self)
        check_update_act.triggered.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.indexOf(self.setup_tab))
        )
        db_menu.addAction(check_update_act)

        select_db_act = QAction("Select Database", self)
        select_db_act.triggered.connect(
            lambda: self.tabs.setCurrentIndex(self.tabs.indexOf(self.setup_tab))
        )
        db_menu.addAction(select_db_act)

        open_folder_act = QAction("Open DB Folder", self)
        open_folder_act.triggered.connect(lambda: self.setup_tab._on_open_folder())
        db_menu.addAction(open_folder_act)

        help_menu = menubar.addMenu("Help")
        help_act = QAction("Help", self)
        help_act.triggered.connect(self._on_help)
        help_menu.addAction(help_act)

        about_act = QAction("About", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    def _build_tabs(self):
        from gui.lookup_tab import LookupTab
        from gui.rename_tab import RenameTab
        from gui.verify_tab import VerifyTab
        from gui.lbdir_tab import LbdirTab
        from gui.search_tab import SearchTab
        from gui.collection_tab import CollectionTab
        from gui.attachments_tab import AttachmentsTab
        from gui.setup_tab import SetupTab
        from gui.theme_tab import ThemeTab

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab order: Lookup(0) Rename(1) Verify(2) lbdir(3) Search(4)
        #            Collection(5) Attachments(6) Setup(7) Themes(8)
        self.lookup_tab = LookupTab(self.flask_port)
        self.rename_tab = RenameTab()
        self.verify_tab = VerifyTab(self.flask_port)
        self.lbdir_tab = LbdirTab(self.flask_port)
        self.search_tab = SearchTab(self.flask_port)
        self.collection_tab = CollectionTab(self.flask_port)
        self.attachments_tab = AttachmentsTab(self.flask_port)
        self.setup_tab = SetupTab(self.flask_port)
        self.theme_tab = ThemeTab()

        self.tabs.addTab(self.lookup_tab, "Lookup")
        self.tabs.addTab(self.rename_tab, "Rename Folders")
        self.tabs.addTab(self.verify_tab, "Verify")
        self.tabs.addTab(self.lbdir_tab, "lbdir")
        self.tabs.addTab(self.search_tab, "Search")
        self.tabs.addTab(self.collection_tab, "My Collection")
        self.tabs.addTab(self.attachments_tab, "Attachments")
        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.theme_tab, "Themes")

        self.search_tab.lookup_lb.connect(self._on_search_lookup_lb)
        self.collection_tab.lookup_lb.connect(self._on_search_lookup_lb)
        self.setup_tab.stats_changed.connect(self._refresh_status)
        self.setup_tab.stats_changed.connect(self.search_tab.load_years)
        self.setup_tab.stats_changed.connect(self.collection_tab.refresh_collection)
        self.setup_tab.search_page_size_changed.connect(self.search_tab.set_page_size)
        self.setup_tab.search_page_size_changed.connect(self.collection_tab.set_page_size)
        self.lookup_tab.lookup_completed.connect(self.rename_tab.populate_from_lookup)
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

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Connecting to database...")

    def _restore_geometry(self):
        size = self._settings.value("window/size", QSize(1100, 750))
        pos = self._settings.value("window/pos", QPoint(100, 100))
        if isinstance(size, QSize):
            self.resize(size)
        if isinstance(pos, QPoint):
            self.move(pos)

    def _save_geometry(self):
        self._settings.setValue("window/size", self.size())
        self._settings.setValue("window/pos", self.pos())

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _refresh_status(self):
        def _fetch():
            try:
                resp = requests.get(
                    f"http://127.0.0.1:{self.flask_port}/api/db/stats", timeout=5
                )
                s = resp.json()
                lb = s.get("latest_lb", "?")
                checksums = s.get("total_checksums", 0)
                last_import = s.get("last_import", "Never")
                if last_import and len(str(last_import)) > 10:
                    last_import = str(last_import)[:10]
                msg = f"DB: LB-{lb}  |  Checksums: {checksums:,}  |  Last import: {last_import}"
            except Exception:
                msg = "Database not connected."
            self._status_message.emit(msg)

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_theme_applied(self):
        self.setStyleSheet(styles.MAIN_STYLESHEET)
        self.lookup_tab.refresh_colors()

    def _on_search_lookup_lb(self, lb_number):
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.lookup_tab))
        self.lookup_tab.lookup_lb_number(lb_number)

    def _on_help(self):
        QMessageBox.information(
            self, "Help",
            "LosslessBob Checksum Lookup\n\n"
            "1. Add files or folders to the listbox (drag-drop or Add buttons)\n"
            "2. Click 'Lookup From Listbox' to check checksums\n"
            "3. Or paste checksum text and click 'Lookup From Clipboard'\n"
            "4. Green rows = complete match, Orange = not found, Pink = incomplete set\n\n"
            "Use the Setup tab to import the LosslessBob flat-file database."
        )

    def _on_about(self):
        QMessageBox.about(
            self, "About",
            f"LosslessBob Checksum Lookup v{VERSION}\n\n"
            "Cross-platform replacement for the original Windows Checksum_Lookup utility.\n"
            "Supports the LosslessBob Bob Dylan lossless recording archive.\n\n"
            "Built with Python, PyQt6, and Flask."
        )
