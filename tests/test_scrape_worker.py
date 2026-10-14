"""The scrape worker starts at most once and reports when it is busy (BUG-367)."""

import threading

from backend import app as app_mod


def test_second_start_reports_busy_and_does_not_run(monkeypatch) -> None:
    monkeypatch.setattr(app_mod, "_scrape_thread", None)
    release = threading.Event()
    runs: list[int] = []

    def body(n: int):
        def run() -> None:
            runs.append(n)
            release.wait(5)
        return run

    barrier = threading.Barrier(4)
    results: list[bool] = []

    def caller(n: int) -> None:
        barrier.wait()
        results.append(app_mod._start_scrape_worker(body(n)))

    callers = [threading.Thread(target=caller, args=(n,)) for n in range(4)]
    for t in callers:
        t.start()
    for t in callers:
        t.join()
    try:
        assert sorted(results) == [False, False, False, True]
        app_mod._scrape_thread.join(0.2)
        assert len(runs) == 1
    finally:
        release.set()
        app_mod._scrape_thread.join(5)

    assert app_mod._start_scrape_worker(lambda: None) is True
    app_mod._scrape_thread.join(5)
