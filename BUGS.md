BUG-098: Curator checkbox shows an error dialog when toggled
Status: Open
File(s): gui/setup_tab.py:1299
Reported: 2026-05-21
Description: Toggling the "Curator mode" checkbox in the Setup tab triggers an error
  dialog ("Could not update flag: …"). The exact error message has not been captured;
  likely a ConnectionRefusedError if the Flask backend hasn't fully started, or an
  unexpected 500 from /api/curator if set_curator() raises inside the route handler.
  Additionally, the docstring for _on_curator_toggled mentions gating a "geocoder group"
  but that code is absent — the method only gates publish_master_btn.
Root cause: Unknown — exact error message required to confirm.
Fix:

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
