"""Shared progress/stop primitive for background pipeline jobs (TODO-306).

Three new workers (olof fetch, bobserve fetch, concert_ranker scan) need the
same thread-safe progress dict, atomic start-claim, and cooperative stop that
``backend/geocoder.py`` implements inline with a module-level ``_progress``
dict and ``_lock``. ``JobState`` is that pattern lifted into a reusable class
so each new module gets one instance instead of copy-pasting the dict/lock
pair. ``geocoder.py`` itself is not refactored onto this — it is working
code and churning it buys nothing this phase.

``try_begin()`` is an atomic claim under the same lock used for every other
mutation, which closes a race the geocoder's inline pattern has today: two
rapid POSTs can both pass a bare ``if _progress["running"]`` check before
either sets it True. Callers claim first, then start the worker thread.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class JobStopped(Exception):
    """Raised inside a job's worker loop when a stop was requested mid-run."""


class JobState:
    """Thread-safe progress, atomic claim, and cooperative stop for one job.

    Field set matches ``activity._PROGRESS_FIELDS`` expectations: ``running,
    done, total, current, errors, skipped, stage, stop_requested,
    started_at``. Callers may pass additional job-specific fields to
    ``try_begin()``/``update()``/``finish()`` — they are merged into the
    dict as-is and included in ``snapshot()``.
    """

    def __init__(self, name: str) -> None:
        """Create an idle job state.

        Args:
            name: Job name, used only in log messages (e.g. "olof-fetch").
        """
        self._name = name
        self._lock = threading.Lock()
        self._progress: dict = {
            "running": False,
            "done": 0,
            "total": 0,
            "current": "",
            "errors": 0,
            "skipped": 0,
            "stage": "",
            "stop_requested": False,
            "started_at": None,
        }

    def try_begin(self, **fields) -> bool:
        """Atomically claim the job if it is not already running.

        Resets the progress dict to its defaults, applies ``fields`` on top,
        and sets ``running=True`` and ``started_at``. Returns False (no
        mutation) if the job was already running.

        Args:
            fields: Extra/overriding progress fields (e.g. ``stage="queued"``).

        Returns:
            True if the claim succeeded, False if already running.
        """
        with self._lock:
            if self._progress["running"]:
                return False
            self._progress = {
                "running": True,
                "done": 0,
                "total": 0,
                "current": "",
                "errors": 0,
                "skipped": 0,
                "stage": "",
                "stop_requested": False,
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._progress.update(fields)
        logger.info("%s: claimed", self._name)
        return True

    def update(self, **fields) -> None:
        """Merge ``fields`` into the progress dict under lock."""
        with self._lock:
            self._progress.update(fields)

    def bump(self, key: str, n: int = 1) -> None:
        """Increment an integer progress field (e.g. ``done``, ``errors``) by ``n``."""
        with self._lock:
            self._progress[key] = self._progress.get(key, 0) + n

    def check_stop(self) -> None:
        """Raise JobStopped if a stop has been requested.

        Raises:
            JobStopped: if ``stop()`` was called since the last check.
        """
        with self._lock:
            if self._progress["stop_requested"]:
                raise JobStopped()

    def sleep(self, seconds: float, slice_s: float = 0.5) -> None:
        """Sleep for ``seconds``, checking for a stop request every ``slice_s``.

        Args:
            seconds: Total time to sleep.
            slice_s: Granularity of the stop check.

        Raises:
            JobStopped: if a stop is requested at any point during the sleep.
        """
        remaining = seconds
        while remaining > 0:
            self.check_stop()
            chunk = min(slice_s, remaining)
            time.sleep(chunk)
            remaining -= chunk
        self.check_stop()

    def stop(self) -> None:
        """Request that the running job stop as soon as possible."""
        with self._lock:
            self._progress["stop_requested"] = True
        logger.info("%s: stop requested", self._name)

    def finish(self, **fields) -> None:
        """Mark the job no longer running and clear the stop flag.

        Args:
            fields: Extra/overriding progress fields to record on completion
                (e.g. ``stage="done"``).
        """
        with self._lock:
            self._progress["running"] = False
            self._progress["stop_requested"] = False
            self._progress.update(fields)
        logger.info("%s: finished", self._name)

    def snapshot(self) -> dict:
        """Return a shallow copy of the current progress dict."""
        with self._lock:
            return dict(self._progress)
