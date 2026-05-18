"""Persistent GUI widget state stored in data/gui_state.json.

Single GuiStateStore instance lives for the lifetime of the app.  All tabs
receive it via their constructor and call attach_table / restore_window /
save_window rather than creating their own QSettings objects.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer

log = logging.getLogger(__name__)

_DEFAULT_PATH = Path("data/gui_state.json")


class GuiStateStore(QObject):
    """Single source of truth for persistent GUI widget state.

    Lives in data/gui_state.json. Atomic writes (tempfile + os.replace).
    Debounced saves (500 ms) to avoid disk thrash during user resize.
    """

    def __init__(self, path: Path = _DEFAULT_PATH, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._state: dict = {}
        self._dirty = False
        self._restoring: set[int] = set()   # id(table) values being restored
        self.corrupt_on_load = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._write_now)

        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            self._migrate_from_qsettings()
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError("root is not an object")
            self._state = data
        except Exception as exc:
            ts = int(time.time())
            broken = self._path.parent / f"{self._path.stem}.broken.{ts}{self._path.suffix}"
            log.warning(
                "gui_state.json unreadable (%s) — backed up to %s, starting fresh",
                exc, broken.name,
            )
            try:
                self._path.rename(broken)
            except OSError:
                pass
            self._state = {}
            self.corrupt_on_load = True

    def _migrate_from_qsettings(self) -> None:
        """One-time migration: translate existing QSettings geometry to JSON.

        Column-width migration is intentionally skipped: the old SearchTab
        QSettings stored auto-calculated values from Qt's initial layout (a
        bug that has since been fixed), so migrating them would perpetuate
        garbage.  Geometry is safe to migrate.
        """
        try:
            from PyQt6.QtCore import QSettings
            from backend.paths import DATA_DIR

            qs2 = QSettings(str(DATA_DIR / "settings.ini"), QSettings.Format.IniFormat)
            size = qs2.value("window/size")
            pos = qs2.value("window/pos")
            entry: dict = {}
            if size is not None:
                try:
                    entry["size"] = [size.width(), size.height()]
                except AttributeError:
                    pass
            if pos is not None:
                try:
                    entry["pos"] = [pos.x(), pos.y()]
                except AttributeError:
                    pass
            if entry:
                self._state["main_window"] = entry
                self._dirty = True
                self._write_now()
        except Exception as exc:
            log.debug("QSettings migration skipped: %s", exc)

    def _schedule_save(self) -> None:
        self._dirty = True
        self._save_timer.start(500)

    def _write_now(self) -> None:
        self._save_timer.stop()
        tmp = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2)
            os.replace(tmp, self._path)
            self._dirty = False
        except Exception as exc:
            log.error("Failed to save gui_state.json: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def flush(self) -> None:
        """Force-write any pending state immediately. Call from app closeEvent."""
        if self._dirty:
            self._write_now()

    # ── column widths ─────────────────────────────────────────────────────────

    def get_col_widths(self, key: str) -> list[int] | None:
        """Return stored column widths for key, or None if not stored / invalid."""
        entry = self._state.get(key)
        if isinstance(entry, dict):
            widths = entry.get("col_widths")
            if isinstance(widths, list) and widths:
                try:
                    parsed = [int(w) for w in widths]
                    # Reject if any width is outside the range a human could set.
                    # Values like 5340 come from Qt's offscreen/auto-layout and
                    # are never the result of a deliberate user resize.
                    if all(10 <= w <= 3000 for w in parsed):
                        return parsed
                except (ValueError, TypeError):
                    pass
        return None

    def set_col_widths(self, key: str, widths: list[int]) -> None:
        """Persist column widths for key (debounced 500 ms write)."""
        if key not in self._state:
            self._state[key] = {}
        self._state[key]["col_widths"] = list(widths)
        self._schedule_save()

    def attach_table(
        self,
        table,
        key: str,
        defaults: list[int] | None = None,
    ) -> None:
        """Bind a table widget to persistent column-width storage.

        Restores stored widths (or defaults) on first show; saves on user
        resize with a 500 ms debounce.  A _restoring guard prevents the
        programmatic restore itself from triggering spurious saves.
        """
        hdr = table.horizontalHeader()
        tid = id(table)

        # Guard must be set NOW, before any sectionResized can fire from Qt's
        # deferred initial layout.  The singleShot(0) _restore below fires on
        # the next event-loop tick — too late; Qt auto-resize fires first and
        # _on_resized would save garbage widths before we ever applied stored ones.
        self._restoring.add(tid)

        def _ncols() -> int:
            # model().columnCount() works for both QTableWidget and QTableView.
            m = table.model()
            return m.columnCount() if m is not None else 0

        def _restore() -> None:
            n = _ncols()
            stored = self.get_col_widths(key)
            if stored:
                for i in range(min(len(stored), n)):
                    table.setColumnWidth(i, stored[i])
                # Fill any new columns beyond stored length from defaults
                if len(stored) < n and defaults:
                    for i in range(len(stored), n):
                        if i < len(defaults):
                            table.setColumnWidth(i, defaults[i])
            elif defaults:
                for i in range(min(len(defaults), n)):
                    table.setColumnWidth(i, defaults[i])
            # Clear flag after a short delay to absorb synchronous resize signals
            QTimer.singleShot(150, lambda: self._restoring.discard(tid))

        def _on_resized(_col: int, _old: int, _new: int) -> None:
            if id(table) in self._restoring:
                return
            n = _ncols()
            self.set_col_widths(key, [table.columnWidth(i) for i in range(n)])

        hdr.sectionResized.connect(_on_resized)
        QTimer.singleShot(0, _restore)

    # ── window geometry ───────────────────────────────────────────────────────

    def restore_window(self, window, key: str = "main_window") -> bool:
        """Apply saved window size and position. Returns True if state was found."""
        entry = self._state.get(key)
        if not isinstance(entry, dict):
            return False
        size = entry.get("size")
        pos = entry.get("pos")
        found = False
        if isinstance(size, list) and len(size) == 2:
            try:
                window.resize(int(size[0]), int(size[1]))
                found = True
            except (TypeError, ValueError):
                pass
        if isinstance(pos, list) and len(pos) == 2:
            try:
                window.move(int(pos[0]), int(pos[1]))
            except (TypeError, ValueError):
                pass
        return found

    def save_window(self, window, key: str = "main_window") -> None:
        """Record current window size and position. Call from closeEvent."""
        s = window.size()
        p = window.pos()
        self._state[key] = {
            "size": [s.width(), s.height()],
            "pos": [p.x(), p.y()],
        }
        self._schedule_save()

    # ── sort state ────────────────────────────────────────────────────────────

    def get_sort(self, key: str) -> tuple[int, str] | None:
        """Return (col_index, 'asc'|'desc') for *key*, or None if not stored."""
        entry = self._state.get(key)
        if isinstance(entry, dict):
            sort = entry.get("sort")
            if isinstance(sort, dict):
                col = sort.get("col")
                direction = sort.get("dir", "asc")
                if isinstance(col, int) and direction in ("asc", "desc"):
                    return col, direction
        return None

    def set_sort(self, key: str, col: int, direction: str) -> None:
        """Persist sort state (col index + 'asc'|'desc') for *key* (debounced)."""
        if key not in self._state:
            self._state[key] = {}
        self._state[key]["sort"] = {"col": col, "dir": direction}
        self._schedule_save()
