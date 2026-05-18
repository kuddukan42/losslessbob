"""Sort helpers for QTableWidget and QTableView across the LosslessBob GUI.

Provides:
  - SortableTableItem: a QTableWidgetItem that sorts by a typed key rather than
    display text, so numeric columns sort numerically, dates sort chronologically,
    etc.
  - sort_key_for(): maps a raw display value + kind tag to a comparable sort key.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtWidgets import QTableWidgetItem


class SortableTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a typed sort_key, not display text.

    Args:
        display: The string shown in the cell.
        sort_key: An optional comparable value used for ordering.  When omitted,
            ``display`` is used as-is.

    Example::

        item = SortableTableItem("LB-00042", sort_key=42)
        table.setItem(row, col, item)
    """

    def __init__(self, display: str, sort_key: Any = None) -> None:
        super().__init__(display)
        self._sort_key = sort_key if sort_key is not None else display

    def __lt__(self, other: "SortableTableItem") -> bool:  # noqa: D105
        if isinstance(other, SortableTableItem):
            try:
                return self._sort_key < other._sort_key
            except TypeError:
                return str(self._sort_key) < str(other._sort_key)
        return super().__lt__(other)


_STATUS_RANK = {"public": 0, "private": 1, "missing": 2}
_VERIFY_RANK = {"pass": 0, "mismatch": 1, "missing": 2}


def sort_key_for(value: Any, kind: str) -> Any:
    """Return a typed sort key for a display value.

    Args:
        value: The raw display value (may be ``None``).
        kind: One of ``'lb_number'``, ``'date_iso'``, ``'date_mdy'``,
            ``'file_size_h'``, ``'lb_status'``, ``'verify_status'``,
            ``'bool_check'``, ``'int'``, ``'text'``.

    Returns:
        A comparable key appropriate for the kind.  Lower values sort first
        (ascending default).
    """
    if value is None:
        value = ""
    if kind == "lb_number":
        # Strip "LB-" prefix and parse as int
        s = str(value).replace("LB-", "").replace("lb-", "").strip()
        try:
            return int(s)
        except ValueError:
            return 0
    if kind == "date_iso":
        return str(value)  # already lex-sortable
    if kind == "date_mdy":
        # Parse "M/D/YY H:MM:SS AM/PM" or "M/D/YY"
        s = str(value).strip()
        for fmt in ("%m/%d/%y %I:%M:%S %p", "%m/%d/%y %I:%M %p", "%m/%d/%y"):
            try:
                return datetime.strptime(s, fmt).isoformat()
            except ValueError:
                continue
        return s
    if kind == "file_size_h":
        # Parse "17.7 Meg" → bytes
        s = str(value).strip().lower()
        try:
            parts = s.split()
            num = float(parts[0])
            unit = parts[1] if len(parts) > 1 else "b"
            mult = {
                "b": 1, "kb": 1024, "mb": 1024**2, "meg": 1024**2, "gb": 1024**3,
            }.get(unit, 1)
            return int(num * mult)
        except (ValueError, IndexError):
            return 0
    if kind == "lb_status":
        return _STATUS_RANK.get(str(value).lower(), 99)
    if kind == "verify_status":
        return _VERIFY_RANK.get(str(value).lower(), 99)
    if kind == "bool_check":
        return 0 if str(value).strip() in ("✓", "1", "yes", "true") else 1
    if kind == "int":
        try:
            return int(str(value).replace(",", ""))
        except ValueError:
            return 0
    # default: text
    return str(value).lower()
