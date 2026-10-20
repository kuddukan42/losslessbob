"""Single scrape / download-pages worker thread (moved out of backend/app.py, TODO-369).

One worker at a time: every caller (scrape routes, DB import auto-scrape, flat-file apply,
the refresh executor via ``backend.app._start_scrape_thread``) shares this module's guard,
because they all drive the module-level ``scraper._scrape_state``.
"""

import threading

from backend import scraper

_scrape_thread = None
_scrape_thread_lock = threading.Lock()  # one scrape/download-pages worker at a time


def _start_scrape_thread(
    lb_numbers: list[int],
    force: bool = False,
    delay_ms: int = 1500,
    download: bool = True,
    use_local_pages: bool = False,
) -> bool:
    """Start a background thread to scrape the given LB numbers, if none is running.

    Does nothing if a scrape thread is already alive. The thread calls
    scraper.scrape_range() with the supplied options.

    Args:
        lb_numbers: Ordered list of LB numbers to scrape.
        force: Re-scrape even if an entry already has data.
        delay_ms: Milliseconds to sleep between requests.
        download: Download attachment files when True.
        use_local_pages: Read from data/site/detail/ cache instead of the network.

    Returns:
        True if a thread was started; False if one was already running.
    """
    def run():
        scraper.scrape_range(
            lb_numbers,
            force=force,
            download_files=download,
            use_local_pages=use_local_pages,
            delay_ms=delay_ms,
        )

    return _start_scrape_worker(run)


def _start_download_pages_thread(lb_numbers, force=False, delay_ms=1500) -> bool:
    """Start a background page-download thread; False if a scrape is already running."""
    def run():
        scraper.download_pages_range(lb_numbers, force=force, delay_ms=delay_ms)

    return _start_scrape_worker(run)


def _start_scrape_worker(run) -> bool:
    """Start ``run`` as the single scrape worker thread unless one is alive.

    The check and the start share one lock so two requests cannot both start a
    scrape_range() — they share the module-level scraper._scrape_state.

    Args:
        run: Zero-arg thread body.

    Returns:
        True if the thread was started; False if a worker was already alive.
    """
    global _scrape_thread
    with _scrape_thread_lock:
        if _scrape_thread and _scrape_thread.is_alive():
            return False
        _scrape_thread = threading.Thread(target=run, daemon=True)
        _scrape_thread.start()
        return True
