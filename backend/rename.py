"""Rename log helper — writes rename_log.txt inside the folder and a rename_history DB row.

All rename origins (Rename tab, Collection tab path relocation) call
write_rename_log() to ensure consistent formatting and a unified audit trail.
"""
import logging
from datetime import datetime
from pathlib import Path

from backend import db

logger = logging.getLogger(__name__)


def write_rename_log(
    folder_path: str | Path,
    old_name: str,
    new_name: str,
    source: str,
    notes: str = "",
    lb_number: int | None = None,
    db_path=None,
) -> None:
    """Append one line to rename_log.txt inside folder_path and insert a rename_history row.

    The log entry is written BEFORE os.rename() executes so it survives inside
    the newly named folder. Callers are responsible for the rename itself.

    Args:
        folder_path: Absolute path to the folder (current path before rename).
        old_name: Old folder name or path string shown in the log line.
        new_name: New folder name or path string shown in the log line.
        source: Origin tag — 'rename_tab', 'collection_tab', or 'auto'.
        notes: Optional inline warning text (e.g. file mismatch details).
        lb_number: LB number to record in rename_history; None if unknown.
        db_path: Override DB path (for testing); None uses the default DB.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    folder = Path(folder_path)

    # Build the log line
    if old_name == new_name:
        line = f"{ts}  [{source:<16}]  path relocated: {folder}"
    else:
        line = f'{ts}  [{source:<16}]  "{old_name}" → "{new_name}"'
    if notes:
        line += f"  [{notes}]"

    # Write to rename_log.txt (append-only)
    log_path = folder / "rename_log.txt"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        logger.warning("Could not write rename_log.txt in %s: %s", folder, exc)

    # Insert into rename_history table
    old_path = str(folder / old_name) if old_name != str(folder) else str(folder)
    new_path = str(folder.parent / new_name) if old_name != new_name else str(folder)
    try:
        db.add_rename_history(
            lb_number=lb_number,
            old_path=old_path,
            new_path=new_path,
            source=source,
            notes=notes,
            db_path=db_path,
        )
    except Exception as exc:
        logger.warning("Could not write rename_history row: %s", exc)
