import re
import shutil
import webbrowser
from pathlib import Path

from backend.rename import write_rename_log
from backend.folder_naming import (
    apply_nft_suffix, strip_nft_suffix, nft_discrepancy, build_standard_name,
)
from backend.db import get_entry, get_lb_status

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton,
    QAbstractItemView, QHeaderView, QMessageBox, QMenu, QLabel,
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
                return _NFT_DISC_TIPS.get(disc)
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
            return HEADERS[section]
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
        row[4] = "Multiple IDs → resolved"
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
            self._rows[idx][4] = "Renamed"
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.info_label = QLabel("Populate the Lookup listbox and run a lookup, then switch here to rename folders.")
        layout.addWidget(self.info_label)

        self.model = RenameModel()
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.view.setColumnWidth(0, 50)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context)
        self.view.clicked.connect(self._on_cell_clicked)
        layout.addWidget(self.view)

        # Legend
        legend_row = QHBoxLayout()
        for color, text in [
            ("#C8E6C9", "LB found in name / renamed"),
            ("#FFE0B2", "Match found — rename suggested"),
            ("#E1BEE7", "Wrong LB in name — strip needed"),
            ("#B2EBF2", "Multiple IDs — right-click to resolve"),
            ("#FFCDD2", "No match"),
            ("#FFCCCC", "Missing -NFT (Private LB)"),
            ("#FFF9C4", "Stale -NFT (LB now Public)"),
            ("#FFE8D0", "-NFT but LB is Missing"),
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
        self.rename_btn = QPushButton("Rename Selected")
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.rename_btn)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.model.check_actionable)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(lambda: self.model.check_all(False))
        btn_row.addWidget(self.deselect_all_btn)

        self.select_wrong_lb_btn = QPushButton("Select Wrong LB")
        self.select_wrong_lb_btn.clicked.connect(lambda: self.model.check_by_state("wrong_lb"))
        btn_row.addWidget(self.select_wrong_lb_btn)

        self.strip_wrong_lb_btn = QPushButton("Strip Wrong LB from Selected")
        self.strip_wrong_lb_btn.clicked.connect(self._on_strip_wrong_lb)
        btn_row.addWidget(self.strip_wrong_lb_btn)

        self.standardize_btn = QPushButton("Standardize Selected")
        self.standardize_btn.setToolTip(
            "Rewrite proposed names to canonical YYYY-MM-DD Location (LB-XXXXX)[-NFT] format"
        )
        self.standardize_btn.clicked.connect(self._on_standardize_selected)
        btn_row.addWidget(self.standardize_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

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
        for folder in listbox_folders:
            folder_path = Path(folder)
            if not folder_path.is_dir():
                continue
            lb_xref = lb_xref_by_folder.get(folder, {})
            cands = sorted(lb_xref.items())  # [(lb_num, xref_val), ...]

            if not cands:
                reason = "No match"
                proposed = folder_path.name
                lb_str = "—"
                cand_list = []
                row_lb_status = None
            elif len(cands) > 1:
                reason = "Multiple IDs"
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
                    reason = "LB already in name"
                elif _has_wrong_lb(folder_path.name, lb_str):
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = "Wrong LB in name"
                elif xref_val:
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = "xref match"
                else:
                    proposed = f"{folder_path.name}-{lb_str}"
                    reason = "Complete match"

                # Apply NFT logic: add -NFT for private, propose strip for stale public
                nft_applied = apply_nft_suffix(proposed, row_lb_status)
                if nft_applied != proposed:
                    proposed = nft_applied
                    if reason == "LB already in name":
                        reason = "Add NFT marker (Private LB)"
                elif row_lb_status == "public" and reason == "LB already in name":
                    stripped = strip_nft_suffix(proposed)
                    if stripped != proposed:
                        proposed = stripped
                        reason = "Strip NFT marker (now Public)"

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
        self.info_label.setText(f"{len(rows)} folders ready for rename review.")

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
                    f"{len(unresolved)} row(s) have multiple IDs — right-click each to resolve, "
                    "then select and rename."
                )
            else:
                self.status_label.setText(
                    "No folders selected." if not to_rename
                    else "None of the selected folders can be processed — "
                         "only 'Complete match', 'xref match', and 'LB already in name' rows are eligible."
                )
            return

        n_rename = sum(1 for i, _ in eligible if self.model.get_state(i) == "needs_rename")
        n_move   = sum(1 for i, _ in eligible if self.model.get_state(i) == "has_lb")
        parts = []
        if n_rename:
            parts.append(f"rename and move {n_rename} folder(s)")
        if n_move:
            parts.append(f"move {n_move} folder(s) without renaming")
        confirm = QMessageBox.question(
            self, "Confirm",
            f"This will {' and '.join(parts)} into '0. Processed'. This cannot be undone.",
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
                    errors.append(f"{Path(src).name}: proposed name contains illegal characters")
                    continue
            try:
                processed_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(f"Cannot create '0. Processed': {e}")
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
                    f"{Path(src).name}: Permission denied. Close any programs "
                    "that may have files in this folder open (Explorer, media "
                    "player, antivirus) and try again."
                )
            except FileExistsError:
                errors.append(
                    f"{Path(src).name}: A folder named '{new_name}' already "
                    "exists in '0. Processed'."
                )
            except OSError as e:
                errors.append(f"{Path(src).name}: {e}")

        parts = []
        if done_rename:
            parts.append(f"Renamed and moved {done_rename} folder(s)")
        if done_move:
            parts.append(f"moved {done_move} folder(s) without renaming")
        msg = ("; ".join(parts) + ".") if parts else "Nothing processed."
        if errors:
            msg += f" {len(errors)} error(s): " + "; ".join(errors[:3])
            if any("Permission denied" in e for e in errors):
                msg += (
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
                f"Updated proposed name for {changed} folder(s). Click Rename Selected to apply."
            )
        else:
            self.status_label.setText("No checked wrong-LB rows to strip.")

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
                f"Standardized {changed} row(s). {len(errors)} error(s): "
                + "; ".join(errors[:3])
            )
        elif changed:
            self.status_label.setText(
                f"Standardized {changed} row(s). Click 'Rename Selected' to apply."
            )
        else:
            self.status_label.setText("No checked single-LB rows to standardize.")

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
            self.status_label.setText(f"Error standardizing: {exc}")
            return
        folder_path = Path(row[1])
        new_proposed = str(folder_path.parent / standard)
        self.model.update_proposed_name(row_idx, new_proposed, "Standardize")
        if standard != folder_path.name:
            self.model.update_state(row_idx, "needs_rename")
        self.status_label.setText(
            f"Row {row_idx + 1}: proposed name set to '{standard}'."
        )

    def _compute_standard(self, lb_num: int, row: list) -> str:
        """Return the canonical standard folder name for an LB row."""
        entry_data = get_entry(lb_num)
        entry = (entry_data or {}).get("entry", {})
        date_str = entry.get("date_str") or ""
        location = (entry.get("location") or "").strip()
        lb_status = get_lb_status(lb_num) or (row[5] if len(row) > 5 else None)
        return build_standard_name(lb_num, date_str, location, lb_status)

    def _on_cell_clicked(self, index: QModelIndex) -> None:
        if index.column() != 0:
            return
        row = self.model.get_row(index.row())
        if row is None:
            return
        new_state = Qt.CheckState.Unchecked if row[0] else Qt.CheckState.Checked
        self.model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)

    def _on_context(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
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
                resolve_menu = menu.addMenu("Resolve — Apply…")
                for lb_num, xref_val in candidates:
                    label = _fmt_lb(lb_num, xref_val)
                    act = QAction(label, self)
                    # Capture lb_num and xref_val in closure
                    act.triggered.connect(
                        lambda checked=False, r=row_idx, lb=lb_num, xr=xref_val:
                        self._resolve_multi_id(r, lb, xr)
                    )
                    resolve_menu.addAction(act)

        elif col == 4:
            jump = QAction("Jump to Lookup Detail", self)
            jump.triggered.connect(lambda: self.jump_to_lookup.emit(row[1]))
            menu.addAction(jump)
        else:
            lb_str = row[3]
            if lb_str and lb_str != "—" and "," not in lb_str:
                m = re.search(r'LB-0*(\d+)', lb_str, re.IGNORECASE)
                if m:
                    try:
                        lb_num = int(m.group(1))
                        std_act = QAction("Standardize Name (YYYY-MM-DD Location…)", self)
                        std_act.triggered.connect(
                            lambda checked=False, r=row_idx: self._standardize_row(r)
                        )
                        menu.addAction(std_act)
                        open_web = QAction(f"Open LB-{lb_num} in Browser", self)
                        url = f"http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{lb_num}.html"
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
            f"Row {row_idx + 1}: resolved to {lb_str}. "
            "Click 'Select All' then 'Rename Selected' when ready."
        )

    def resize_columns_to_font(self) -> None:
        self.view.resizeColumnsToContents()
