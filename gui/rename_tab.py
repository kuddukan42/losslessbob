import re
import shutil
import webbrowser
from pathlib import Path
from urllib.parse import quote as _url_quote

import requests

from backend.rename import write_rename_log
from backend.folder_naming import (
    apply_nft_suffix, strip_nft_suffix, nft_discrepancy, build_standard_name,
)
from backend.db import get_entry, get_lb_status

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton,
    QAbstractItemView, QHeaderView, QMessageBox, QMenu, QLabel,
    QInputDialog, QDialog, QFormLayout, QComboBox, QTextEdit,
    QDialogButtonBox, QSpinBox,
)

HEADERS = ["Rename", "Current Folder Name", "Proposed New Name", "LB Found", "Reason"]

# Row states → background colors
_STATE_COLORS = {
    "has_lb":       QColor("#C8E6C9"),  # green  — LB already in folder name
    "renamed":      QColor("#C8E6C9"),  # green  — just renamed
    "needs_rename": QColor("#FFE0B2"),  # orange — match found but not yet renamed
    "wrong_lb":     QColor("#E1BEE7"),  # purple — folder has a different LB number
    "no_match":     QColor("#FFCDD2"),  # red    — no match
    "multiple_ids": QColor("#B2EBF2"),  # cyan   — multiple LBs found, unresolved
}

# NFT discrepancy state → background color (overrides state color when set)
_NFT_DISC_COLORS = {
    "missing": QColor("#FFCCCC"),  # pale red    — Private LB, folder lacks -NFT
    "stale":   QColor("#FFF9C4"),  # pale yellow — Public LB, folder has -NFT
    "unknown": QColor("#FFE8D0"),  # pale orange — Missing/None LB, folder has -NFT
}

# NFT discrepancy → tooltip text
_NFT_DISC_TIPS = {
    "missing": "LB is Private — folder should be marked -NFT",
    "stale":   "LB is now Public — -NFT marker may no longer be needed",
    "unknown": "LB does not exist — investigate this folder",
}

# Only include these detail statuses when building the folder→LB map
_MATCH_STATUSES = {"MATCHED", "MATCHED (INCOMPLETE)"}

# Sort rank for the State/Reason column (lower = earlier in ASC sort)
_STATE_SORT_RANK = {
    "needs_rename": 0,
    "has_lb":       1,
    "wrong_lb":     2,
    "multiple_ids": 3,
    "renamed":      4,
    "no_match":     5,
}


class RenameSortProxy(QSortFilterProxyModel):
    """QSortFilterProxyModel wrapper for RenameModel with per-column sort logic."""

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        col = left.column()
        src = self.sourceModel()

        if col == 1:
            l_row = src.get_row(left.row())
            r_row = src.get_row(right.row())
            l_val = Path(l_row[1] if l_row else "").name.lower()
            r_val = Path(r_row[1] if r_row else "").name.lower()
            return l_val < r_val

        if col == 2:
            l_row = src.get_row(left.row())
            r_row = src.get_row(right.row())
            l_val = Path(l_row[2] if l_row else "").name.lower()
            r_val = Path(r_row[2] if r_row else "").name.lower()
            return l_val < r_val

        if col == 3:
            def _lb_key(lb_str: str) -> int:
                if not lb_str or lb_str == "—":
                    return 999_999
                nums = re.findall(r'LB-0*(\d+)', lb_str, re.IGNORECASE)
                return min(int(n) for n in nums) if nums else 999_999

            l_row = src.get_row(left.row())
            r_row = src.get_row(right.row())
            return _lb_key(l_row[3] if l_row else "") < _lb_key(r_row[3] if r_row else "")

        if col == 4:
            l_state = src.get_state(left.row()) or "no_match"
            r_state = src.get_state(right.row()) or "no_match"
            return _STATE_SORT_RANK.get(l_state, 99) < _STATE_SORT_RANK.get(r_state, 99)

        return super().lessThan(left, right)


def _fmt_lb(lb_num: int, xref_val: int = 0) -> str:
    """Format an LB label, including xref suffix when xref_val > 0."""
    if xref_val:
        return f"LB-{lb_num}-xref{xref_val:04d}"
    return f"LB-{lb_num}"


def _lb_in_name(folder_name: str, lb_str: str) -> bool:
    """True when folder_name already contains the LB (and xref) from lb_str."""
    if not lb_str or lb_str == "—" or "," in lb_str:
        return False
    m = re.search(r'LB-0*(\d+)(?:-xref0*(\d+))?', lb_str, re.IGNORECASE)
    if not m:
        return False
    lb_num = int(m.group(1))
    xref_num = int(m.group(2)) if m.group(2) else 0

    m2 = re.search(r'LB-0*(\d+)(?:-xref0*(\d+))?', folder_name, re.IGNORECASE)
    if not m2:
        return False
    folder_lb = int(m2.group(1))
    folder_xref = int(m2.group(2)) if m2.group(2) else 0
    return folder_lb == lb_num and folder_xref == xref_num


def _has_wrong_lb(folder_name: str, lb_str: str) -> bool:
    """True when folder_name contains an LB number that differs from lb_str."""
    if not lb_str or lb_str == "—" or "," in lb_str:
        return False
    m = re.search(r'LB-0*(\d+)(?:-xref0*(\d+))?', lb_str, re.IGNORECASE)
    if not m:
        return False
    lb_num = int(m.group(1))
    xref_num = int(m.group(2)) if m.group(2) else 0

    m2 = re.search(r'LB-0*(\d+)(?:-xref0*(\d+))?', folder_name, re.IGNORECASE)
    if not m2:
        return False
    folder_lb = int(m2.group(1))
    folder_xref = int(m2.group(2)) if m2.group(2) else 0
    # Wrong if LB number differs, OR if xref number differs
    return not (folder_lb == lb_num and folder_xref == xref_num)


def _strip_lb_from_name(name: str) -> str:
    """Remove LB-NNNN[-xrefNNNN] (and surrounding separators) from a folder name."""
    # Strip full xref pattern first, then plain LB
    cleaned = re.sub(r'[\-_. ]+LB-\d+(?:-xref\d+)?', '', name, flags=re.IGNORECASE)
    if cleaned == name:
        cleaned = re.sub(r'LB-\d+(?:-xref\d+)?[\-_. ]*', '', name, flags=re.IGNORECASE)
    return cleaned.strip('-_. ')


def _row_state(folder_path: str, lb_str: str) -> str:
    if lb_str == "—":
        return "no_match"
    if "," in lb_str:
        return "multiple_ids"
    folder_name = Path(folder_path).name
    if _lb_in_name(folder_name, lb_str):
        return "has_lb"
    if _has_wrong_lb(folder_name, lb_str):
        return "wrong_lb"
    return "needs_rename"


class RenameModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []
        self._states = []
        # Per-row list of (lb_number, xref_value) candidate tuples (for multiple_ids rows)
        self._candidates: list[list[tuple[int, int]]] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return ""
            return str(row[col])
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if row[0] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole:
            lb_status = row[5] if len(row) > 5 else None
            # NFT discrepancy overrides the whole row
            disc = nft_discrepancy(Path(row[1]).name, lb_status)
            if disc:
                return _NFT_DISC_COLORS.get(disc)
            # LB Found column (col 3) shows lb_status tint when private or missing
            if col == 3 and lb_status in ("private", "missing"):
                return QColor("#B3E5FC") if lb_status == "private" else QColor("#E0E0E0")
            state = self._states[index.row()] if index.row() < len(self._states) else None
            return _STATE_COLORS.get(state)
        if role == Qt.ItemDataRole.ToolTipRole:
            lb_status = row[5] if len(row) > 5 else None
            disc = nft_discrepancy(Path(row[1]).name, lb_status)
            if disc:
                _tips = {
                    "missing": self.tr("LB is Private — folder should be marked -NFT"),
                    "stale":   self.tr("LB is now Public — -NFT marker may no longer be needed"),
                    "unknown": self.tr("LB does not exist — investigate this folder"),
                }
                return _tips.get(disc)
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            self._rows[index.row()][0] = (value == Qt.CheckState.Checked)
            self.dataChanged.emit(index, index)
            return True
        return False

    def flags(self, index):
        base = super().flags(index)
        if index.column() == 0:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.tr(HEADERS[section])
        return None

    def set_rows(self, rows, states=None, candidates=None):
        self.beginResetModel()
        self._rows = rows
        self._states = states or ["no_match"] * len(rows)
        self._candidates = candidates or [[] for _ in rows]
        self.endResetModel()

    def get_row(self, idx):
        return self._rows[idx] if 0 <= idx < len(self._rows) else None

    def get_state(self, idx):
        return self._states[idx] if 0 <= idx < len(self._states) else None

    def get_candidates(self, idx) -> list[tuple[int, int]]:
        if 0 <= idx < len(self._candidates):
            return self._candidates[idx]
        return []

    def resolve_multi_id(self, idx: int, lb_num: int, xref_val: int) -> None:
        """Resolve a multiple_ids row to a specific LB (and optional xref)."""
        if not (0 <= idx < len(self._rows)):
            return
        row = self._rows[idx]
        folder_path = Path(row[1])
        lb_str = _fmt_lb(lb_num, xref_val)
        proposed_name = f"{folder_path.name}-{lb_str}"
        proposed = str(folder_path.parent / proposed_name)
        row[2] = proposed
        row[3] = lb_str
        row[4] = self.tr("Multiple IDs → resolved")
        new_state = _row_state(str(folder_path), lb_str)
        self._states[idx] = new_state
        self._candidates[idx] = []
        self.dataChanged.emit(
            self.index(idx, 0),
            self.index(idx, len(HEADERS) - 1),
        )

    def update_row_after_rename(self, idx, new_path):
        if 0 <= idx < len(self._rows):
            self._rows[idx][0] = False
            self._rows[idx][1] = new_path
            self._rows[idx][2] = new_path
            self._rows[idx][4] = self.tr("Renamed")
            self._states[idx] = "renamed"
            self.dataChanged.emit(
                self.index(idx, 0),
                self.index(idx, len(HEADERS) - 1),
            )

    def check_all(self, checked):
        for row in self._rows:
            row[0] = checked
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0)
            )

    def check_actionable(self):
        """Check only rows that can actually be renamed."""
        _actionable = {"needs_rename", "wrong_lb"}
        for i, row in enumerate(self._rows):
            row[0] = (i < len(self._states) and self._states[i] in _actionable)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0))

    def check_by_state(self, state):
        """Check only rows whose state matches; uncheck all others."""
        for i, row in enumerate(self._rows):
            row[0] = (i < len(self._states) and self._states[i] == state)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0))

    def update_proposed_name(self, idx, new_proposed, new_reason=None):
        if 0 <= idx < len(self._rows):
            self._rows[idx][2] = new_proposed
            if new_reason is not None:
                self._rows[idx][4] = new_reason
            self.dataChanged.emit(self.index(idx, 2), self.index(idx, 4))

    def update_state(self, idx: int, state: str) -> None:
        if 0 <= idx < len(self._states):
            self._states[idx] = state
            self.dataChanged.emit(
                self.index(idx, 0),
                self.index(idx, len(HEADERS) - 1),
            )


class RenameTab(QWidget):
    jump_to_lookup = pyqtSignal(str)

    def __init__(self, parent=None, state_store=None, flask_port: int = 5174):
        super().__init__(parent)
        self._state_store = state_store
        self._flask_port = flask_port
        # Rows (by model index) that were resolved via folder_lb_link (show 🔗 indicator)
        self._linked_rows: set[int] = set()
        # Curator flag — fetched lazily; None means not yet checked
        self._is_curator: bool | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel(self.tr("Populate the Lookup listbox and run a lookup, then switch here to rename folders."))
        layout.addWidget(self.info_label)

        self.model = RenameModel()
        self.proxy = RenameSortProxy()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context)
        self.view.clicked.connect(self._on_cell_clicked)
        layout.addWidget(self.view)

        if self._state_store:
            self._state_store.attach_table(
                self.view, "rename.folders", defaults=[50, 220, 220, 90, 200]
            )

        # Legend
        legend_row = QHBoxLayout()
        for color, text in [
            ("#C8E6C9", self.tr("LB found in name / renamed")),
            ("#FFE0B2", self.tr("Match found — rename suggested")),
            ("#E1BEE7", self.tr("Wrong LB in name — strip needed")),
            ("#B2EBF2", self.tr("Multiple IDs — right-click to resolve")),
            ("#FFCDD2", self.tr("No match")),
            ("#FFCCCC", self.tr("Missing -NFT (Private LB)")),
            ("#FFF9C4", self.tr("Stale -NFT (LB now Public)")),
            ("#FFE8D0", self.tr("-NFT but LB is Missing")),
        ]:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {color}; border: 1px solid #999;")
            legend_row.addWidget(swatch)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(12)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        btn_row = QHBoxLayout()
        self.rename_btn = QPushButton(self.tr("Rename Selected"))
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.rename_btn)

        self.select_all_btn = QPushButton(self.tr("Select All"))
        self.select_all_btn.clicked.connect(self.model.check_actionable)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton(self.tr("Deselect All"))
        self.deselect_all_btn.clicked.connect(lambda: self.model.check_all(False))
        btn_row.addWidget(self.deselect_all_btn)

        self.select_wrong_lb_btn = QPushButton(self.tr("Select Wrong LB"))
        self.select_wrong_lb_btn.clicked.connect(lambda: self.model.check_by_state("wrong_lb"))
        btn_row.addWidget(self.select_wrong_lb_btn)

        self.strip_wrong_lb_btn = QPushButton(self.tr("Strip Wrong LB from Selected"))
        self.strip_wrong_lb_btn.clicked.connect(self._on_strip_wrong_lb)
        btn_row.addWidget(self.strip_wrong_lb_btn)

        self.standardize_btn = QPushButton(self.tr("Standardize Selected"))
        self.standardize_btn.setToolTip(
            self.tr("Rewrite proposed names to canonical YYYY-MM-DD Location (LB-XXXXX)[-NFT] format")
        )
        self.standardize_btn.clicked.connect(self._on_standardize_selected)
        btn_row.addWidget(self.standardize_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _api(self, path: str, **kwargs):
        """GET the local Flask API. Returns parsed JSON or None on error."""
        try:
            r = requests.get(
                f"http://127.0.0.1:{self._flask_port}{path}",
                timeout=5, **kwargs
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def _api_put(self, path: str, json_body: dict) -> bool:
        """PUT to the local Flask API. Returns True on success."""
        try:
            r = requests.put(
                f"http://127.0.0.1:{self._flask_port}{path}",
                json=json_body, timeout=5,
            )
            return r.ok
        except Exception:
            return False

    def _api_delete(self, path: str, **kwargs) -> bool:
        """DELETE the local Flask API resource. Returns True on success."""
        try:
            r = requests.delete(
                f"http://127.0.0.1:{self._flask_port}{path}",
                timeout=5, **kwargs
            )
            return r.ok
        except Exception:
            return False

    def _api_post(self, path: str, json_body: dict):
        """POST to the local Flask API. Returns parsed JSON or None on error."""
        try:
            r = requests.post(
                f"http://127.0.0.1:{self._flask_port}{path}",
                json=json_body, timeout=5,
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def _check_curator(self) -> bool:
        """Return curator status, fetching from backend once per session."""
        if self._is_curator is None:
            data = self._api("/api/curator")
            self._is_curator = bool((data or {}).get("is_curator", False))
        return self._is_curator

    def _resolve_single_lb(
        self,
        cands: list[tuple[int, int]],
        folder: str,
    ) -> tuple[int, int, bool] | None:
        """Try to resolve a multiple-candidate folder to a single (lb, xref, linked) triple.

        Resolution order:
          1. folder_lb_link — sticky user choice for this exact path.
          2. lb_alias collapse — if all candidates collapse to one canonical.

        Args:
            cands: Sorted list of (lb_number, xref_value) candidate pairs.
            folder: Absolute folder path string.

        Returns:
            Tuple (lb_num, xref_val, linked_flag) if resolved to a single LB,
            or None if still ambiguous.
        """
        # Step 1: folder_lb_link
        link = self._api(f"/api/folder_link?path={_url_quote(folder, safe='')}")
        if link and link.get("lb_number"):
            linked_lb = int(link["lb_number"])
            # Find xref for this lb in the candidate list (default 0)
            xref_for_linked = next((xr for lb, xr in cands if lb == linked_lb), 0)
            return (linked_lb, xref_for_linked, True)

        # Step 2: lb_alias collapse
        lb_nums = [lb for lb, _xr in cands]
        resolve_data = self._api(
            f"/api/lb_alias/resolve?lbs={','.join(str(x) for x in lb_nums)}"
        )
        if resolve_data and len(resolve_data.get("canonical", [])) == 1:
            canonical_lb = resolve_data["canonical"][0]
            xref_for_canon = next((xr for lb, xr in cands if lb == canonical_lb), 0)
            return (canonical_lb, xref_for_canon, False)

        return None

    # ── Populate ──────────────────────────────────────────────────────────────

    def populate_from_lookup(self, detail_list, listbox_folders):
        # Build folder → {lb_number: xref_value} from MATCHED items only.
        # Excluding DUPLICATE (resolved losers) prevents spurious "Multiple IDs" when
        # duplicate resolution already picked a winner.
        lb_xref_by_folder: dict[str, dict[int, int]] = {}
        # lb_status_map: lb_number → lb_status (populated from detail lb_status annotations)
        lb_status_map: dict[int, str] = {}
        for d in detail_list:
            lb = d.get("lb_number")
            if lb and d.get("source_file") and d.get("status") in _MATCH_STATUSES:
                folder = str(Path(d["source_file"]).parent)
                xref_val = d.get("xref") or 0
                existing = lb_xref_by_folder.setdefault(folder, {}).get(lb, xref_val)
                lb_xref_by_folder[folder][lb] = min(existing, xref_val)  # 0 wins over non-zero
            if lb and d.get("lb_status"):
                lb_status_map[lb] = d["lb_status"]

        rows = []
        states = []
        candidates = []
        self._linked_rows = set()

        for row_idx, folder in enumerate(listbox_folders):
            folder_path = Path(folder)
            if not folder_path.is_dir():
                continue
            lb_xref = lb_xref_by_folder.get(folder, {})
            cands = sorted(lb_xref.items())  # [(lb_num, xref_val), ...]

            if not cands:
                reason = self.tr("No match")
                proposed = folder_path.name
                lb_str = "—"
                cand_list = []
                row_lb_status = None
            elif len(cands) > 1:
                # --- Disambiguation resolution ---
                resolved = self._resolve_single_lb(cands, folder)
                if resolved is not None:
                    lb, xref_val, is_linked = resolved
                    lb_str = ("🔗 " if is_linked else "") + _fmt_lb(lb, xref_val)
                    cand_list = []
                    row_lb_status = lb_status_map.get(lb)
                    if is_linked:
                        self._linked_rows.add(len(rows))  # index in the rows list
                    if _lb_in_name(folder_path.name, _fmt_lb(lb, xref_val)):
                        proposed = folder_path.name
                        reason = self.tr("LB already in name (resolved)")
                    elif _has_wrong_lb(folder_path.name, _fmt_lb(lb, xref_val)):
                        proposed = f"{folder_path.name}-{_fmt_lb(lb, xref_val)}"
                        reason = self.tr("Wrong LB in name (resolved)")
                    else:
                        proposed = f"{folder_path.name}-{_fmt_lb(lb, xref_val)}"
                        reason = self.tr("Multiple IDs → resolved")
                    nft_applied = apply_nft_suffix(proposed, row_lb_status)
                    if nft_applied != proposed:
                        proposed = nft_applied
                        if reason.endswith(self.tr("(resolved)")) and "already" in reason:
                            reason = self.tr("Add NFT marker (Private LB)")
                elif resolved is None:
                    reason = self.tr("Multiple IDs")
                    proposed = folder_path.name
                    lb_str = ", ".join(_fmt_lb(lb, xr) for lb, xr in cands)
                    cand_list = cands
                    # Conservative: any private candidate → mark the whole folder
                    cand_statuses = [lb_status_map.get(lb) for lb, _xr in cands]
                    row_lb_status = "private" if any(s == "private" for s in cand_statuses) else None
            else:
                lb, xref_val = cands[0]
                lb_str = _fmt_lb(lb, xref_val)
                cand_list = []
                row_lb_status = lb_status_map.get(lb)
                if _lb_in_name(folder_path.name, lb_str):
                    proposed = folder_path.name
                    reason = self.tr("LB already in name")
                elif _has_wrong_lb(folder_path.name, lb_str):
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = self.tr("Wrong LB in name")
                elif xref_val:
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = self.tr("xref match")
                else:
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = self.tr("Complete match")

                # Apply NFT logic: add -NFT for private, propose strip for stale public
                nft_applied = apply_nft_suffix(proposed, row_lb_status)
                if nft_applied != proposed:
                    proposed = nft_applied
                    if reason == self.tr("LB already in name"):
                        reason = self.tr("Add NFT marker (Private LB)")
                elif row_lb_status == "public" and reason == self.tr("LB already in name"):
                    stripped = strip_nft_suffix(proposed)
                    if stripped != proposed:
                        proposed = stripped
                        reason = self.tr("Strip NFT marker (now Public)")

            state = _row_state(folder, lb_str)
            # If NFT logic changed the proposed name for an already-named folder,
            # escalate to needs_rename so the rename path uses the proposed name.
            if state == "has_lb" and proposed != folder_path.name:
                state = "needs_rename"

            rows.append([True, folder, str(folder_path.parent / proposed) if proposed != folder_path.name
                         else folder, lb_str, reason, row_lb_status])
            states.append(state)
            candidates.append(cand_list)

        self.model.set_rows(rows, states, candidates)
        self.view.resizeColumnsToContents()
        self.info_label.setText(self.tr("{} folders ready for rename review.").format(len(rows)))

    def _on_rename(self):
        to_rename = [
            (i, self.model.get_row(i))
            for i in range(self.model.rowCount())
            if self.model.get_row(i) and self.model.get_row(i)[0]
        ]
        _eligible_states = {"needs_rename", "has_lb"}
        eligible = [(i, r) for i, r in to_rename if self.model.get_state(i) in _eligible_states]

        # Report unresolved multiple_ids that user tried to include
        unresolved = [(i, r) for i, r in to_rename if self.model.get_state(i) == "multiple_ids"]
        if not eligible:
            if unresolved:
                self.status_label.setText(
                    self.tr(
                        "{} row(s) have multiple IDs — right-click each to resolve, "
                        "then select and rename."
                    ).format(len(unresolved))
                )
            else:
                self.status_label.setText(
                    self.tr("No folders selected.") if not to_rename
                    else self.tr(
                        "None of the selected folders can be processed — "
                        "only 'Complete match', 'xref match', and 'LB already in name' rows are eligible."
                    )
                )
            return

        n_rename = sum(1 for i, _ in eligible if self.model.get_state(i) == "needs_rename")
        n_move   = sum(1 for i, _ in eligible if self.model.get_state(i) == "has_lb")
        parts = []
        if n_rename:
            parts.append(self.tr("rename and move {} folder(s)").format(n_rename))
        if n_move:
            parts.append(self.tr("move {} folder(s) without renaming").format(n_move))
        confirm = QMessageBox.question(
            self, self.tr("Confirm"),
            self.tr("This will {} into '0. Processed'. This cannot be undone.").format(
                self.tr(" and ").join(parts)
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        done_rename = 0
        done_move = 0
        errors = []
        for idx, row in eligible:
            src = row[1]
            state = self.model.get_state(idx)
            new_name = Path(src).name if state == "has_lb" else Path(row[2]).name
            processed_dir = Path(src).parent / "0. Processed"
            final_dst = processed_dir / new_name
            if str(src) == str(final_dst):
                self.model.update_row_after_rename(idx, str(final_dst))
                done_rename += (state == "needs_rename")
                done_move += (state == "has_lb")
                continue
            if state == "needs_rename":
                illegal = set('<>:"/\\|?*')
                if any(c in illegal for c in new_name):
                    errors.append(
                        self.tr("{}: proposed name contains illegal characters").format(Path(src).name)
                    )
                    continue
            try:
                processed_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(self.tr("Cannot create '0. Processed': {}").format(e))
                continue
            try:
                # Extract LB number for rename_history (best-effort; None if not found)
                _lb_m = re.search(r'LB-0*(\d+)', row[3] or "", re.IGNORECASE)
                _lb_num = int(_lb_m.group(1)) if _lb_m else None
                # Write log entry BEFORE the move so it ends up in the renamed folder
                write_rename_log(
                    folder_path=src,
                    old_name=Path(src).name,
                    new_name=new_name,
                    source="rename_tab",
                    lb_number=_lb_num,
                )
                shutil.move(str(src), str(final_dst))
                self.model.update_row_after_rename(idx, str(final_dst))
                if state == "needs_rename":
                    done_rename += 1
                else:
                    done_move += 1
            except PermissionError:
                errors.append(
                    self.tr(
                        "{}: Permission denied. Close any programs that may have "
                        "files in this folder open (Explorer, media player, antivirus) "
                        "and try again."
                    ).format(Path(src).name)
                )
            except FileExistsError:
                errors.append(
                    self.tr("{0}: A folder named '{1}' already exists in '0. Processed'.").format(
                        Path(src).name, new_name
                    )
                )
            except OSError as e:
                errors.append(self.tr("{}: {}").format(Path(src).name, e))

        parts = []
        if done_rename:
            parts.append(self.tr("Renamed and moved {} folder(s)").format(done_rename))
        if done_move:
            parts.append(self.tr("moved {} folder(s) without renaming").format(done_move))
        msg = ("; ".join(parts) + ".") if parts else self.tr("Nothing processed.")
        if errors:
            msg += self.tr(" {} error(s): ").format(len(errors)) + "; ".join(errors[:3])
            if any("Permission denied" in e for e in errors):
                msg += self.tr(
                    "\n\nTip (Windows): click somewhere else in Explorer to "
                    "deselect the folder, then retry."
                )
        self.status_label.setText(msg)

    def _on_strip_wrong_lb(self):
        changed = 0
        for i in range(self.model.rowCount()):
            row = self.model.get_row(i)
            if not row or not row[0]:
                continue
            if self.model.get_state(i) != "wrong_lb":
                continue
            lb_str = row[3]
            # Extract LB and optional xref from lb_str
            m = re.search(r'LB-0*(\d+)(?:-xref0*(\d+))?', lb_str, re.IGNORECASE)
            if not m:
                continue
            lb_num = int(m.group(1))
            xref_val = int(m.group(2)) if m.group(2) else 0
            folder_path = Path(row[1])
            clean_name = _strip_lb_from_name(folder_path.name)
            lb_status = row[5] if len(row) > 5 else None
            new_base = f"{clean_name}-{_fmt_lb(lb_num, xref_val)}"
            new_proposed = str(folder_path.parent / apply_nft_suffix(new_base, lb_status))
            self.model.update_proposed_name(i, new_proposed, "Strip & rename")
            self.model.update_state(i, "needs_rename")
            changed += 1
        if changed:
            self.status_label.setText(
                self.tr("Updated proposed name for {} folder(s). Click Rename Selected to apply.").format(changed)
            )
        else:
            self.status_label.setText(self.tr("No checked wrong-LB rows to strip."))

    def _on_standardize_selected(self) -> None:
        """Rewrite proposed names for checked single-LB rows to canonical format."""
        changed = 0
        errors: list[str] = []
        for i in range(self.model.rowCount()):
            row = self.model.get_row(i)
            if not row or not row[0]:
                continue
            lb_str = row[3]
            if not lb_str or lb_str == "—" or "," in lb_str:
                continue
            m = re.search(r"LB-0*(\d+)(?:-xref0*(\d+))?", lb_str, re.IGNORECASE)
            if not m:
                continue
            lb_num = int(m.group(1))
            try:
                standard = self._compute_standard(lb_num, row)
            except Exception as exc:
                errors.append(f"LB-{lb_num:05d}: {exc}")
                continue
            folder_path = Path(row[1])
            new_proposed = str(folder_path.parent / standard)
            self.model.update_proposed_name(i, new_proposed, "Standardize")
            if standard != folder_path.name:
                self.model.update_state(i, "needs_rename")
            changed += 1

        if errors:
            self.status_label.setText(
                self.tr("Standardized {0} row(s). {1} error(s): ").format(changed, len(errors))
                + "; ".join(errors[:3])
            )
        elif changed:
            self.status_label.setText(
                self.tr("Standardized {} row(s). Click 'Rename Selected' to apply.").format(changed)
            )
        else:
            self.status_label.setText(self.tr("No checked single-LB rows to standardize."))

    def _standardize_row(self, row_idx: int) -> None:
        """Standardize the proposed name for a single row (right-click action)."""
        row = self.model.get_row(row_idx)
        if not row:
            return
        lb_str = row[3]
        if not lb_str or lb_str == "—" or "," in lb_str:
            return
        m = re.search(r"LB-0*(\d+)", lb_str, re.IGNORECASE)
        if not m:
            return
        lb_num = int(m.group(1))
        try:
            standard = self._compute_standard(lb_num, row)
        except Exception as exc:
            self.status_label.setText(self.tr("Error standardizing: {}").format(exc))
            return
        folder_path = Path(row[1])
        new_proposed = str(folder_path.parent / standard)
        self.model.update_proposed_name(row_idx, new_proposed, "Standardize")
        if standard != folder_path.name:
            self.model.update_state(row_idx, "needs_rename")
        self.status_label.setText(
            self.tr("Row {0}: proposed name set to '{1}'.").format(row_idx + 1, standard)
        )

    def _compute_standard(self, lb_num: int, row: list) -> str:
        """Return the canonical standard folder name for an LB row."""
        entry_data = get_entry(lb_num)
        entry = (entry_data or {}).get("entry", {})
        date_str = entry.get("date_str") or ""
        location = (entry.get("location") or "").strip()
        lb_status = get_lb_status(lb_num) or (row[5] if len(row) > 5 else None)
        return build_standard_name(lb_num, date_str, location, lb_status)

    def _on_cell_clicked(self, proxy_index: QModelIndex) -> None:
        if proxy_index.column() != 0:
            return
        source_index = self.proxy.mapToSource(proxy_index)
        row = self.model.get_row(source_index.row())
        if row is None:
            return
        new_state = Qt.CheckState.Unchecked if row[0] else Qt.CheckState.Checked
        self.model.setData(source_index, new_state, Qt.ItemDataRole.CheckStateRole)

    def _on_context(self, pos):
        proxy_index = self.view.indexAt(pos)
        if not proxy_index.isValid():
            return
        index = self.proxy.mapToSource(proxy_index)
        row_idx = index.row()
        row = self.model.get_row(row_idx)
        if not row:
            return

        menu = QMenu(self)
        state = self.model.get_state(row_idx)
        col = index.column()

        # Multiple IDs resolution submenu
        if state == "multiple_ids":
            candidates = self.model.get_candidates(row_idx)
            if candidates:
                resolve_menu = menu.addMenu(self.tr("Resolve — Apply…"))
                for lb_num, xref_val in candidates:
                    label = _fmt_lb(lb_num, xref_val)
                    act = QAction(label, self)
                    # Capture lb_num and xref_val in closure
                    act.triggered.connect(
                        lambda checked=False, r=row_idx, lb=lb_num, xr=xref_val:
                        self._resolve_multi_id(r, lb, xr)
                    )
                    resolve_menu.addAction(act)

            # "Link this folder to specific LB..." — persist user choice
            link_act = QAction(self.tr("Link this folder to specific LB…"), self)
            link_act.triggered.connect(
                lambda checked=False, r=row_idx: self._on_link_folder(r)
            )
            menu.addAction(link_act)

            # Curator-only: "Save as master alias…"
            if self._check_curator() and candidates:
                alias_act = QAction(self.tr("Save as master alias…"), self)
                alias_act.triggered.connect(
                    lambda checked=False, r=row_idx: self._on_save_alias(r)
                )
                menu.addAction(alias_act)

        elif col == 4:
            jump = QAction(self.tr("Jump to Lookup Detail"), self)
            jump.triggered.connect(lambda: self.jump_to_lookup.emit(row[1]))
            menu.addAction(jump)
        else:
            lb_str = row[3]
            # Unlink action — shown for linked rows (have 🔗 prefix)
            if row_idx in self._linked_rows or lb_str.startswith("🔗"):
                unlink_act = QAction(self.tr("Unlink this folder"), self)
                unlink_act.triggered.connect(
                    lambda checked=False, r=row_idx: self._on_unlink_folder(r)
                )
                menu.addAction(unlink_act)
                menu.addSeparator()

            # Strip the 🔗 prefix for LB parsing
            lb_str_clean = lb_str.lstrip("🔗 ")
            if lb_str_clean and lb_str_clean != "—" and "," not in lb_str_clean:
                m = re.search(r'LB-0*(\d+)', lb_str_clean, re.IGNORECASE)
                if m:
                    try:
                        lb_num = int(m.group(1))
                        std_act = QAction(self.tr("Standardize Name (YYYY-MM-DD Location…)"), self)
                        std_act.triggered.connect(
                            lambda checked=False, r=row_idx: self._standardize_row(r)
                        )
                        menu.addAction(std_act)
                        open_web = QAction(self.tr("Open LB-{} in Browser").format(lb_num), self)
                        url = (
                            f"http://www.losslessbob.wonderingwhattochoose.com"
                            f"/detail/LB-{lb_num}.html"
                        )
                        open_web.triggered.connect(lambda: webbrowser.open(url))
                        menu.addAction(open_web)
                    except ValueError:
                        pass

        if not menu.isEmpty():
            menu.exec(self.view.mapToGlobal(pos))

    def _resolve_multi_id(self, row_idx: int, lb_num: int, xref_val: int) -> None:
        """Apply a specific LB (and optional xref) to a multiple_ids row."""
        self.model.resolve_multi_id(row_idx, lb_num, xref_val)
        lb_str = _fmt_lb(lb_num, xref_val)
        self.status_label.setText(
            self.tr("Row {0}: resolved to {1}. Click 'Select All' then 'Rename Selected' when ready.").format(
                row_idx + 1, lb_str
            )
        )

    def _on_link_folder(self, row_idx: int) -> None:
        """Prompt the user to link a multiple_ids folder to a specific LB."""
        row = self.model.get_row(row_idx)
        if not row:
            return
        folder = row[1]
        candidates = self.model.get_candidates(row_idx)
        candidate_labels = [_fmt_lb(lb, xr) for lb, xr in candidates]

        if candidate_labels:
            hint = self.tr("Candidates: {}\n\nEnter the LB number to link:").format(
                ', '.join(candidate_labels)
            )
        else:
            hint = self.tr("Enter the LB number to link:")

        lb_text, ok = QInputDialog.getText(
            self, self.tr("Link Folder to LB"), hint,
        )
        if not ok or not lb_text.strip():
            return
        # Accept plain integers or "LB-NNNNN" format
        m = re.search(r'\d+', lb_text)
        if not m:
            self.status_label.setText(self.tr("Invalid LB number entered."))
            return
        lb_num = int(m.group())

        ok_put = self._api_put("/api/folder_link", {
            "folder_path": folder,
            "lb_number": lb_num,
            "note": "",
        })
        if not ok_put:
            self.status_label.setText(self.tr("Row {}: failed to save link.").format(row_idx + 1))
            return

        # Re-resolve the row using the new link
        xref_val = next((xr for lb, xr in candidates if lb == lb_num), 0)
        lb_str = "🔗 " + _fmt_lb(lb_num, xref_val)
        folder_path = Path(folder)
        plain_lb_str = _fmt_lb(lb_num, xref_val)
        if _lb_in_name(folder_path.name, plain_lb_str):
            proposed = folder
            reason = self.tr("LB already in name (linked)")
        else:
            proposed = str(folder_path.parent / f"{folder_path.name}-{plain_lb_str}")
            reason = self.tr("Multiple IDs → linked")

        row[2] = proposed
        row[3] = lb_str
        row[4] = reason
        new_state = _row_state(folder, plain_lb_str)
        self.model._states[row_idx] = new_state
        self.model._candidates[row_idx] = []
        self._linked_rows.add(row_idx)
        self.model.dataChanged.emit(
            self.model.index(row_idx, 0),
            self.model.index(row_idx, len(HEADERS) - 1),
        )
        self.status_label.setText(
            self.tr("Row {0}: linked to LB-{1}. Select and rename when ready.").format(
                row_idx + 1, f"{lb_num:05d}"
            )
        )

    def _on_unlink_folder(self, row_idx: int) -> None:
        """Remove a folder→LB link and re-run resolution for that row."""
        row = self.model.get_row(row_idx)
        if not row:
            return
        folder = row[1]
        ok = self._api_delete(f"/api/folder_link?path={_url_quote(folder, safe='')}")
        if not ok:
            self.status_label.setText(self.tr("Row {}: failed to remove link.").format(row_idx + 1))
            return
        self._linked_rows.discard(row_idx)
        # Reset lb_str to stripped value (remove 🔗 prefix) and re-evaluate state
        lb_str = row[3].lstrip("🔗 ")
        row[3] = lb_str
        row[4] = self.tr("Unlinked — check manually")
        # If only one LB remains after stripping, keep needs_rename / has_lb logic
        new_state = _row_state(folder, lb_str)
        self.model._states[row_idx] = new_state
        self.model.dataChanged.emit(
            self.model.index(row_idx, 0),
            self.model.index(row_idx, len(HEADERS) - 1),
        )
        self.status_label.setText(
            self.tr("Row {}: link removed. Re-run lookup to refresh candidates.").format(row_idx + 1)
        )

    def _on_save_alias(self, row_idx: int) -> None:
        """Open a dialog to save a master alias for a multiple_ids row (curator only)."""
        row = self.model.get_row(row_idx)
        if not row:
            return
        candidates = self.model.get_candidates(row_idx)
        if len(candidates) < 2:
            self.status_label.setText(self.tr("Need at least 2 candidates to create an alias."))
            return

        dlg = _AliasDialog(candidates, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        alias_lb, canonical_lb, relationship, note = dlg.get_values()

        result = self._api_post("/api/lb_alias", {
            "alias_lb": alias_lb,
            "canonical_lb": canonical_lb,
            "relationship": relationship,
            "note": note,
        })
        if result is None:
            self.status_label.setText(self.tr("Failed to save alias (check curator mode)."))
            return

        rewrote = result.get("rewrote_chain", False)
        effective_canon = result.get("canonical_lb", canonical_lb)
        msg = self.tr("Alias LB-{0} → LB-{1} saved.").format(
            f"{alias_lb:05d}", f"{effective_canon:05d}"
        )
        if rewrote:
            msg += self.tr(" (chain rewritten)")
        self.status_label.setText(msg)

        # Re-run alias resolution for this row in-place
        resolved = self._resolve_single_lb(candidates, row[1])
        if resolved is not None:
            lb, xref_val, is_linked = resolved
            plain_lb_str = _fmt_lb(lb, xref_val)
            lb_str = ("🔗 " if is_linked else "") + plain_lb_str
            folder_path = Path(row[1])
            row[3] = lb_str
            row[4] = self.tr("Multiple IDs → resolved (alias)")
            if not _lb_in_name(folder_path.name, plain_lb_str):
                row[2] = str(folder_path.parent / f"{folder_path.name}-{plain_lb_str}")
            new_state = _row_state(row[1], plain_lb_str)
            self.model._states[row_idx] = new_state
            self.model._candidates[row_idx] = []
            if is_linked:
                self._linked_rows.add(row_idx)
            self.model.dataChanged.emit(
                self.model.index(row_idx, 0),
                self.model.index(row_idx, len(HEADERS) - 1),
            )

    def resize_columns_to_font(self) -> None:
        self.view.resizeColumnsToContents()


class _AliasDialog(QDialog):
    """Dialog for curator to create an lb_alias mapping from a multiple_ids row."""

    def __init__(self, candidates: list[tuple[int, int]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Save as Master Alias"))
        self.setMinimumWidth(380)
        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lb_nums = [lb for lb, _xr in candidates]

        self._alias_spin = QSpinBox()
        self._alias_spin.setRange(1, 999999)
        self._alias_spin.setValue(lb_nums[0] if lb_nums else 1)
        layout.addRow(self.tr("Alias LB (the secondary/wrong one):"), self._alias_spin)

        self._canon_spin = QSpinBox()
        self._canon_spin.setRange(1, 999999)
        self._canon_spin.setValue(lb_nums[1] if len(lb_nums) > 1 else 1)
        layout.addRow(self.tr("Canonical LB (the correct one):"), self._canon_spin)

        self._rel_combo = QComboBox()
        for rel in ("duplicate", "supersedes", "see_also"):
            self._rel_combo.addItem(rel)
        layout.addRow(self.tr("Relationship:"), self._rel_combo)

        self._note_edit = QTextEdit()
        self._note_edit.setFixedHeight(60)
        self._note_edit.setPlaceholderText(self.tr("Optional note for this alias…"))
        layout.addRow(self.tr("Note:"), self._note_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> tuple[int, int, str, str]:
        """Return (alias_lb, canonical_lb, relationship, note)."""
        return (
            self._alias_spin.value(),
            self._canon_spin.value(),
            self._rel_combo.currentText(),
            self._note_edit.toPlainText().strip(),
        )
