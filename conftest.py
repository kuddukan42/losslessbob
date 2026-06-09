"""
conftest.py — pytest fixtures shared across all test modules.

Resets the DatabaseWriteQueue singleton between every test so each test gets
its own fresh queue pointing at its own temp database.  Without this, the
module-level _write_queue singleton initialised by the first test would
persist and route all subsequent writes to the wrong database file.
"""
import pytest


@pytest.fixture(autouse=True)
def reset_write_queue():
    """Reset the write-queue singleton before every test.

    Shuts down the previous queue (if any) so its writer thread and connection
    are released, then clears the module-level reference so the next
    init_write_queue() call creates a fresh queue for the new temp DB.
    """
    import backend.db as _db
    import backend.db_queue as _dq

    # Tear down any leftover queue from a previous test
    if _dq._write_queue is not None:
        try:
            _dq._write_queue.shutdown(timeout=2)
        except Exception:
            pass
        _dq._write_queue = None

    # Also clear thread-local read connections so each test starts clean
    _db._local.connections = {}

    yield

    # Tear down the queue created by this test
    if _dq._write_queue is not None:
        try:
            _dq._write_queue.shutdown(timeout=2)
        except Exception:
            pass
        _dq._write_queue = None

    _db._local.connections = {}
