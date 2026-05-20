from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class AudioReconcileDialog(QDialog):
    """Preview dialog for audio file renames driven by checksum DB canonical filenames.

    Shows a table of checkbox | Current Filename | DB Canonical Filename | Checksum.
    Proposals with status 'ok' are pre-checked; problematic ones are shown in yellow
    and left unchecked. Only checked 'ok' proposals are returned by get_selected_renames().
    """

    _C_WARN = QColor("#FFF9C4")

    def __init__(self, proposals: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Reconcile Audio Filenames"))
        self.setMinimumSize(920, 420)
        self._proposals = proposals

        ok_count = sum(1 for p in proposals if p["status"] == "ok")
        issue_count = len(proposals) - ok_count

        layout = QVBoxLayout(self)

        summary = self.tr(
            "{} proposed rename(s) — {} actionable, {} with issues (shown in yellow)."
        ).format(len(proposals), ok_count, issue_count)
        layout.addWidget(QLabel(summary))

        self._table = QTableWidget(len(proposals), 4)
        self._table.setHorizontalHeaderLabels([
            "", self.tr("Current Filename"), self.tr("DB Canonical Filename"), self.tr("Checksum"),
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 28)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        _STATUS_TIPS = {
            "from_missing": self.tr("Source file not found on disk"),
            "to_exists":    self.tr("Target filename already exists on disk"),
        }

        for row, p in enumerate(proposals):
            is_ok = p["status"] == "ok"

            chk_item = QTableWidgetItem()
            chk_item.setCheckState(
                Qt.CheckState.Checked if is_ok else Qt.CheckState.Unchecked
            )
            chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            from_name = Path(p.get("from", p.get("input_filename", ""))).name
            to_name   = Path(p.get("to",   p.get("db_filename",    ""))).name

            from_item = QTableWidgetItem(from_name)
            from_item.setToolTip(p.get("from", from_name))
            to_item   = QTableWidgetItem(to_name)
            to_item.setToolTip(p.get("to", to_name))

            chk_val = p.get("checksum", "")
            chk_short = (chk_val[:20] + "…") if len(chk_val) > 20 else chk_val
            chk_item2 = QTableWidgetItem(chk_short)
            chk_item2.setToolTip(chk_val)

            if not is_ok:
                tip = _STATUS_TIPS.get(p["status"], p["status"])
                from_item.setToolTip(f"{p.get('from', from_name)}\n⚠ {tip}")
                for item in (chk_item, from_item, to_item, chk_item2):
                    item.setBackground(self._C_WARN)

            self._table.setItem(row, 0, chk_item)
            self._table.setItem(row, 1, from_item)
            self._table.setItem(row, 2, to_item)
            self._table.setItem(row, 3, chk_item2)

        self._table.resizeColumnsToContents()
        self._table.setColumnWidth(0, 28)
        layout.addWidget(self._table)

        sel_row = QHBoxLayout()
        sel_all_btn = QPushButton(self.tr("Select All"))
        sel_all_btn.clicked.connect(self._select_all)
        desel_btn = QPushButton(self.tr("Deselect All"))
        desel_btn.clicked.connect(self._deselect_all)
        sel_row.addWidget(sel_all_btn)
        sel_row.addWidget(desel_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        btn_row = QHBoxLayout()
        apply_btn = QPushButton(self.tr("Apply Selected"))
        apply_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _select_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _deselect_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def get_selected_renames(self) -> list:
        """Return [{from, to}] for each checked, actionable proposal."""
        result = []
        for row in range(self._table.rowCount()):
            p = self._proposals[row]
            if (self._table.item(row, 0).checkState() == Qt.CheckState.Checked
                    and p["status"] == "ok"):
                result.append({"from": p["from"], "to": p["to"]})
        return result
