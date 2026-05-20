"""Map tab: world map of LB locations using Leaflet via QWebEngineView."""

import logging

from PyQt6.QtCore import QFile, QIODeviceBase, QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebChannel import QWebChannel
    from PyQt6.QtWebEngineCore import QWebEngineScript
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_OK = True
except ImportError:
    _WEBENGINE_OK = False

log = logging.getLogger(__name__)


def _read_qwebchannel_js() -> str:
    """Read qwebchannel.js from Qt's built-in resources."""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QIODeviceBase.OpenModeFlag.ReadOnly):
        data = bytes(f.readAll()).decode("utf-8")
        f.close()
        return data
    log.warning("MapTab: could not open :/qtwebchannel/qwebchannel.js")
    return ""


class _MapBridge(QObject):
    """Qt object registered with QWebChannel; called from JS in the map page.

    Signals are forwarded by :class:`MapTab` to the rest of the GUI.
    """

    open_in_search = pyqtSignal(int)   # single LB number
    list_in_search = pyqtSignal(str)   # comma-separated LB numbers

    @pyqtSlot(str)
    def openInSearch(self, lb_number: str) -> None:
        """Switch the GUI to Search tab and search for lb_number.

        Args:
            lb_number: String representation of the LB integer (e.g. "1234").
        """
        try:
            self.open_in_search.emit(int(lb_number))
        except (ValueError, TypeError):
            log.warning("MapBridge.openInSearch: invalid lb_number %r", lb_number)

    @pyqtSlot(str)
    def listInSearch(self, lb_csv: str) -> None:
        """Load a set of LB numbers into the Search tab.

        Args:
            lb_csv: Comma-separated LB numbers from the viewport filter.
        """
        self.list_in_search.emit(lb_csv)


class MapTab(QWidget):
    """World map of LosslessBob recording locations, rendered via Leaflet in a WebEngine view.

    Loads ``http://localhost:{flask_port}/map`` which in turn fetches marker data from
    ``/api/map/data``.  When PyQt6-WebEngine is unavailable the tab degrades gracefully to
    a plain-text notice and an "Open in Browser" button.

    Signals:
        open_in_search: Emitted when the user clicks "Open in Search" in a marker popup.
            Carries the integer LB number.
        list_in_search: Emitted when the user clicks "List in Search" from the viewport
            filter panel. Carries a comma-separated string of LB numbers.

    Args:
        flask_port: Port number the local Flask server is listening on.
        state_store: Optional GuiStateStore instance (reserved for future use).
        parent: Optional Qt parent widget.
    """

    open_in_search = pyqtSignal(int)   # forwarded from _MapBridge
    list_in_search = pyqtSignal(str)   # forwarded from _MapBridge

    def __init__(self, flask_port: int, state_store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flask_port = flask_port
        self._state_store = state_store
        self._webview: "QWebEngineView | None" = None
        self._bridge: "_MapBridge | None" = None
        self._channel: "QWebChannel | None" = None
        self._map_url = QUrl(f"http://localhost:{flask_port}/map")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct the layout based on WebEngine availability."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Top bar — always present
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        title_label = QLabel("Map")
        title_label.setStyleSheet("font-weight: 700; font-size: 11pt;")
        top_bar.addWidget(title_label)
        top_bar.addStretch()

        self._open_browser_btn = QPushButton("Open in Browser")
        self._open_browser_btn.setToolTip(f"Open {self._map_url.toString()} in the system browser")
        self._open_browser_btn.clicked.connect(self._open_in_browser)
        top_bar.addWidget(self._open_browser_btn)

        layout.addLayout(top_bar)

        if _WEBENGINE_OK:
            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.setToolTip("Reload the map page")
            self._refresh_btn.clicked.connect(self._on_refresh)
            top_bar.insertWidget(top_bar.count() - 1, self._refresh_btn)

            self._webview = QWebEngineView(self)
            self._setup_webchannel()
            layout.addWidget(self._webview, stretch=1)
        else:
            log.warning("PyQt6-WebEngine not available — Map tab running in fallback mode")
            from PyQt6.QtCore import Qt

            fallback_container = QWidget()
            fallback_layout = QVBoxLayout(fallback_container)
            fallback_layout.setContentsMargins(0, 0, 0, 0)

            notice = QLabel("Map tab requires PyQt6-WebEngine — see README to enable")
            notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
            notice.setStyleSheet("color: gray; font-style: italic;")
            fallback_layout.addStretch()
            fallback_layout.addWidget(notice)
            fallback_layout.addStretch()

            layout.addWidget(fallback_container, stretch=1)

    def _setup_webchannel(self) -> None:
        """Configure QWebChannel and inject qwebchannel.js into every loaded page."""
        self._bridge = _MapBridge()
        self._bridge.open_in_search.connect(self.open_in_search)
        self._bridge.list_in_search.connect(self.list_in_search)

        self._channel = QWebChannel(self._webview.page())
        self._channel.registerObject("bridge", self._bridge)
        self._webview.page().setWebChannel(self._channel)

        js_src = _read_qwebchannel_js()
        if js_src:
            script = QWebEngineScript()
            script.setName("qwebchannel_init")
            script.setSourceCode(js_src)
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            self._webview.page().scripts().insert(script)
        else:
            log.warning("MapTab: QWebChannel JS not injected — 'Open in Search' unavailable")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Load the map URL on first show if WebEngine is available.

        Args:
            event: The QShowEvent passed by Qt.
        """
        if _WEBENGINE_OK and self._webview is not None:
            current = self._webview.url()
            if not current.isValid() or current.isEmpty() or current == QUrl("about:blank"):
                log.debug("MapTab.showEvent: loading %s", self._map_url.toString())
                self._webview.load(self._map_url)
        super().showEvent(event)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_refresh(self) -> None:
        """Reload the WebEngine view."""
        if self._webview is not None:
            self._webview.reload()

    def _open_in_browser(self) -> None:
        """Open the map URL in the system default browser."""
        QDesktopServices.openUrl(self._map_url)
