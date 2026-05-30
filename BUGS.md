
BUG-110: TOCTOU race in background-task start routes allows double workers
Status: Fixed
File(s): backend/app.py:2033,4000,4099,4156
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: The "already running" guard for spectrogram generate, fingerprint build, dup scan, and identify-folder all checked status inside the lock but released the lock before starting the thread. Two concurrent POST requests could both see "idle", both pass the guard, and both start worker threads simultaneously. Additionally, the guard checked only status=="running", missing the "scanning" state emitted by build_fingerprint_db during its folder-discovery phase.
Fix: Inside the lock, immediately after the guard, set status="running" to claim the slot atomically. Changed guard to `status not in ("idle", "done", "error")` to block all non-terminal states.

BUG-109: Crashed background workers leave status permanently stuck at "running"
Status: Fixed
File(s): backend/app.py:_do_fp_build,_do_fp_dup_scan,_do_fp_identify_folder,_do_spectro_batch
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: None of the four background worker functions had a top-level exception handler. A crash (e.g., import error, unexpected exception) would leave the state dict at status="running" forever, preventing any future invocation from passing the guard. This was a latent issue; BUG-110's fix (pre-marking status inside the lock) made it immediately observable.
Fix: Wrapped each worker body in try/except; on exception, sets status="error" with the exception message via the per-worker _set helper.

BUG-108: All attachment entries shown as stale regardless of download state
Status: Fixed
File(s): backend/app.py:626
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: attachments_cached response omitted the "downloaded" field from each file object. Frontend stale check (f.downloaded === 1) always saw undefined, so every entry with files evaluated to "stale".
Fix: Added "downloaded": r["downloaded"] to the file dict in attachments_cached.

BUG-107: Attachment viewer always shows 404 for text/html/image files
Status: Fixed
File(s): gui_next/src/renderer/src/screens/ScreenAttachments.tsx:134,198
Reported: 2026-05-29
Fixed: 2026-05-29
Root cause: Frontend passed activeFile.filename (raw LBF-prefixed name) to /api/attachment/<lb>/<name>, but the backend route queries entry_files WHERE clean_name=? — the LBF- prefix caused every lookup to miss.
Fix: Changed both the text-content fetch and fileUrl to use activeFile.clean_name || activeFile.filename.

BUG-106: Windows installer does not place app in Program Files
Status: Open
File(s): installer/losslessbob.iss (or equivalent Inno Setup script)
Reported: 2026-05-22
Description: The Windows installer does not install the application to the standard Program Files directory (e.g. C:\Program Files\LosslessBob). Install destination is incorrect or defaults to an unexpected location. May be a misconfigured DefaultDirName or missing {pf} / {autopf} constant in the Inno Setup script.
Root cause: Unknown
Fix: —


BUG-067: PyQt6 + lxml SIGABRT when Qt widget tests run before lxml-importing tests
Status: Open
File(s): tests/test_scraper_crawler.py, tests/test_lb_master.py
Reported: 2026-05-18
Description: Running all three test files in a single pytest process causes a Fatal Python error: Aborted when tests/test_lb_master.py Qt widget tests (TestSearchTabStatusColumn, TestDbEditorIntegrityPanel) run before tests/test_scraper_crawler.py which imports BeautifulSoup (bs4 loads lxml at import time). The SIGABRT is a known incompatibility between PyQt6 cleanup and lxml's memory allocator on Linux.
Root cause: bs4 unconditionally imports lxml at bs4 import time regardless of which parser is used. When lxml's .so is loaded into the same process as PyQt6 objects, Qt's atexit/destructor sequence may SIGABRT.
Fix: Run test files separately (`pytest tests/test_scraper_crawler.py`) or exclude Qt widget tests when running combined (`pytest tests/ -k "not SearchTab and not DbEditor and not CollectionTab"`). All three files pass independently (59 + 27 + 13 = 99 total tests, all green).
