"""Map tab: world map of LB locations using Leaflet via QWebEngineView."""

import logging

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_OK = True
except ImportError:
    _WEBENGINE_OK = False

log = logging.getLogger(__name__)


class MapTab(QWidget):
    """World map of LosslessBob recording locations, rendered via Leaflet in a WebEngine view.

    Loads ``http://localhost:{flask_port}/map`` which in turn fetches marker data from
    ``/api/map/data``.  When PyQt6-WebEngine is unavailable the tab degrades gracefully to
    a plain-text notice and an "Open in Browser" button.

    Args:
        flask_port: Port number the local Flask server is listening on.
        state_store: Optional GuiStateStore instance (reserved for future use).
        parent: Optional Qt parent widget.
    """

    def __init__(self, flask_port: int, state_store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flask_port = flask_port
        self._state_store = state_store
        self._webview: "QWebEngineView | None" = None
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
