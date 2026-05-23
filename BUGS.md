BUG-107: sqlite3.OperationalError: database is locked during crawler upsert_inventory
Status: Open
File(s): backend/db.py:2788, backend/site_crawler.py:398
Reported: 2026-05-22
Description: During a crawl, Thread-N (crawl) raises sqlite3.OperationalError: database is locked when calling upsert_inventory() → conn.execute("INSERT OR IGNORE INTO site_inventory(url) VALUES(?)", ...). Indicates concurrent threads are each opening their own connection to the SQLite DB without WAL mode or a shared connection/lock strategy, causing write contention.
Root cause: Unknown
Fix: —

BUG-106: Windows installer does not place app in Program Files
Status: Open
File(s): installer/losslessbob.iss (or equivalent Inno Setup script)
Reported: 2026-05-22
Description: The Windows installer does not install the application to the standard Program Files directory (e.g. C:\Program Files\LosslessBob). Install destination is incorrect or defaults to an unexpected location. May be a misconfigured DefaultDirName or missing {pf} / {autopf} constant in the Inno Setup script.
Root cause: Unknown
Fix: —

BUG-105: Windows release — master DB install fails with "internal_error"
Status: Open
File(s): unknown (master update install path)
Reported: 2026-05-22
Description: On the Windows release build, clicking Yes on the "Install Master Update?" confirmation dialog (which shows the correct .db path, e.g. G:/losslessbob_master_2026-05-23_023135_publish.db) results in an "Install Failed — internal_error" dialog. The backup and install process does not complete. Root cause not yet isolated — could be a path handling issue (drive letter/Windows separator), a permission/file-lock problem, or an error in the install worker that surfaces a bare exception string rather than a descriptive message.
Root cause: Unknown
Fix: —

BUG-090: Black screen flickers in app at certain times
Status: Open
File(s): unknown
Reported: 2026-05-20
Description: Intermittent black screen flickers occur in the GUI at certain points during use. Trigger conditions not yet isolated — may be related to tab switching, background thread activity, or Qt repaint/viewport timing.
Root cause: Unknown
Fix: —

BUG-067: PyQt6 + lxml SIGABRT when Qt widget tests run before lxml-importing tests
Status: Open
File(s): tests/test_scraper_crawler.py, tests/test_lb_master.py
Reported: 2026-05-18
Description: Running all three test files in a single pytest process causes a Fatal Python error: Aborted when tests/test_lb_master.py Qt widget tests (TestSearchTabStatusColumn, TestDbEditorIntegrityPanel) run before tests/test_scraper_crawler.py which imports BeautifulSoup (bs4 loads lxml at import time). The SIGABRT is a known incompatibility between PyQt6 cleanup and lxml's memory allocator on Linux.
Root cause: bs4 unconditionally imports lxml at bs4 import time regardless of which parser is used. When lxml's .so is loaded into the same process as PyQt6 objects, Qt's atexit/destructor sequence may SIGABRT.
Fix: Run test files separately (`pytest tests/test_scraper_crawler.py`) or exclude Qt widget tests when running combined (`pytest tests/ -k "not SearchTab and not DbEditor and not CollectionTab"`). All three files pass independently (59 + 27 + 13 = 99 total tests, all green).
