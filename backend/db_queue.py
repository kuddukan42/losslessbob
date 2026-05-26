"""
backend/db_queue.py — Serialised SQLite write queue (DB-09).

A single persistent writer thread holds one sqlite3.Connection and
executes all write callables submitted via execute() / execute_async().
This eliminates concurrent writer races entirely — there is only ever
one open write connection and one active transaction at a time.
"""
import logging
import queue
import sqlite3
import threading
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

_PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-32000;
PRAGMA foreign_keys=ON;
"""


class DatabaseWriteQueue:
    """Single-writer thread that serialises all SQLite write operations.

    All mutations submitted via :meth:`execute` or :meth:`execute_async` are
    funnelled through a single ``queue.Queue`` and executed by one persistent
    background thread.  This means SQLite never sees two concurrent writers,
    eliminating ``OperationalError: database is locked`` under WAL mode.

    Args:
        db_path: Absolute path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._queue: queue.Queue = queue.Queue()
        self._conn: Optional[sqlite3.Connection] = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="db-writer")
        self._thread.start()
        # Block until the writer has finished its PRAGMA setup.  This ensures
        # journal_mode=WAL is set before any other connection tries to do the
        # same — eliminating the race between the writer and init_db()'s
        # get_connection() call on a brand-new database file.
        if not self._ready.wait(timeout=10):
            raise RuntimeError("db-writer thread did not start within 10 s")

    def _run(self) -> None:
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit — we manage all transaction boundaries explicitly
        )
        self._conn.row_factory = sqlite3.Row
        for pragma in _PRAGMAS.strip().splitlines():
            pragma = pragma.strip()
            if pragma:
                self._conn.execute(pragma)
        _log.debug("db-writer: connection open → %s", self._db_path)
        self._ready.set()  # unblock __init__; WAL mode established before any reader opens

        while True:
            item = self._queue.get()
            if item is None:  # shutdown sentinel
                self._queue.task_done()
                break
            fn, result_event, result_box = item
            try:
                self._conn.execute("BEGIN")
                val = fn(self._conn)
                self._conn.execute("COMMIT")
                result_box[0] = val
            except Exception as exc:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                result_box[1] = exc
            finally:
                self._queue.task_done()
                if result_event is not None:
                    result_event.set()

    def execute(self, fn: Callable[[sqlite3.Connection], Any], timeout: float = 30.0) -> Any:
        """Submit fn(conn) to the writer thread; block until done; return result or raise.

        Args:
            fn: Callable that receives the writer connection and performs all
                SQL mutations.  Must NOT call other write-queue functions
                (re-entrancy would deadlock).  May return a value.
            timeout: Seconds to wait before raising :exc:`TimeoutError`.

        Returns:
            Whatever *fn* returns (may be ``None``).

        Raises:
            TimeoutError: If the write is not complete within *timeout* seconds.
            Exception: Any exception raised inside *fn* is re-raised here.
        """
        result_box: list = [None, None]  # [value, exception]
        event = threading.Event()
        self._queue.put((fn, event, result_box))
        if not event.wait(timeout):
            raise TimeoutError(f"DB write timed out after {timeout}s")
        if result_box[1] is not None:
            raise result_box[1]
        return result_box[0]

    def execute_async(self, fn: Callable[[sqlite3.Connection], None]) -> None:
        """Fire-and-forget: submit fn(conn) without waiting for completion.

        Args:
            fn: Callable that receives the writer connection.  Exceptions are
                silently discarded (logged at DEBUG level inside the thread).
        """
        self._queue.put((fn, None, [None, None]))

    def shutdown(self, timeout: float = 5.0) -> None:
        """Drain the queue and stop the writer thread cleanly.

        Args:
            timeout: Seconds to wait for the writer thread to finish.
        """
        self._queue.put(None)
        self._thread.join(timeout)
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass


_write_queue: Optional[DatabaseWriteQueue] = None
_wq_lock = threading.Lock()


def init_write_queue(db_path: str) -> None:
    """Initialise the module-level singleton.  Called once from ``init_db()``.

    Subsequent calls are no-ops (idempotent).

    Args:
        db_path: Absolute path to the SQLite database file.
    """
    global _write_queue
    with _wq_lock:
        if _write_queue is not None:
            return
        _write_queue = DatabaseWriteQueue(db_path)
    _log.info("DatabaseWriteQueue initialised → %s", db_path)


def get_write_queue() -> DatabaseWriteQueue:
    """Return the module-level :class:`DatabaseWriteQueue` singleton.

    Returns:
        The active write queue.

    Raises:
        RuntimeError: If :func:`init_write_queue` has not been called yet.
    """
    if _write_queue is None:
        raise RuntimeError("DatabaseWriteQueue not initialised; call init_write_queue() first.")
    return _write_queue
