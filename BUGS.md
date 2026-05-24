BUG-113: Hard-coded table backgrounds break theming
Status: Open
File(s): gui/ (various table/widget files)
Reported: 2026-05-24
Description: Some table widgets still have hard-coded background colours in their
  stylesheets or palette settings. These colours do not respond to the application
  theme, making the tables look incorrect (e.g. white backgrounds in dark mode or
  vice versa).
Root cause: Unknown — likely inline stylesheet strings with fixed hex/RGB colour values
  instead of QPalette roles or theme variables.
Fix: —

---

BUG-112: Master update install incorrectly restricted to Curator and allows downgrade
Status: Open
File(s): gui/ or backend/ (master update install handler, unknown exact file)
Reported: 2026-05-24
Description: Two related issues with the "Install Master Update" flow:
  1. Permission gate: The install is gated behind Curator mode, but any user should be
     able to install a master update — it is not a privileged/editorial action.
  2. No downgrade protection: If a user selects an older master file than the one already
     installed, the import proceeds without warning or rejection. Installing an older file
     should be blocked (or at minimum require an explicit confirmation) to prevent data loss.
Root cause: Unknown — likely the permission check is a copy-paste from a curator-only action,
  and no version/date comparison is performed before importing.
Fix: —

---

BUG-111: Snapshot install fails on AppImage — "must be in data/exports/ or data/imports/"
Status: Open
File(s): backend/ or gui/ (snapshot install handler, unknown exact file)
Reported: 2026-05-24
Description: When attempting to install a snapshot in the AppImage build, an "Install Failed"
  dialog is shown with the message "Snapshot must be in data/exports/ or data/imports/".
  The install works correctly in non-AppImage (dev) runs.
Root cause: Unknown — the path check for data/exports/ and data/imports/ likely resolves
  relative to the AppImage mount point or CWD rather than the correct XDG data directory,
  causing a valid snapshot file to fail the location check.
Fix: —

---

BUG-110: Open data folder button does nothing on AppImage
Status: Open
File(s): gui/ (button handler, unknown exact file)
Reported: 2026-05-24
Description: Clicking the "Open data folder" button has no effect when running the AppImage
  build on Linux. The folder does not open in the file manager. Works as expected in
  non-AppImage (dev) runs.
Root cause: Unknown — likely xdg-open or QDesktopServices.openUrl() fails silently inside
  the AppImage sandbox, or the data path resolves incorrectly under the AppImage environment.
Fix: —

---

BUG-109: Map geocode layer not shown on load when Curator mode is already checked
Status: Open
File(s): gui/map_tab.py (suspected)
Reported: 2026-05-23
Description: When the app starts (or the Map tab is opened) with Curator mode already
  checked, the geocoded pins/layer do not appear on the map. Toggling the Curator mode
  checkbox off and back on forces the map to refresh and the geocode data appears correctly.
Root cause: Unknown — likely the map initialisation or data-load signal fires before the
  checkbox state is read, so the geocode layer is never injected into the initial render.
Fix: —

---

BUG-107: Soft-404 pages stored as entry descriptions
Status: Fixed
File(s): backend/scraper.py:177, backend/db.py:init_db
Reported: 2026-05-23
Fixed: 2026-05-23
Description: Archive server returns HTTP 200 with a 404 error HTML body for non-existent
  entries. Scraper parsed the error page text ("The requested URL was not found on this
  server.") as the entry description, resulting in 68 entries with garbage metadata.
Root cause: _fetch() only checked the HTTP status code; the server's soft-404 responses
  always returned 200 so the check was bypassed.
Fix: Added _is_soft_404() in scraper.py to detect the error text in HTML before parsing.
  Added one-time cleanup SQL in init_db() to fix existing affected rows.

BUG-106: Windows installer does not place app in Program Files
Status: Open
File(s): installer/losslessbob.iss (or equivalent Inno Setup script)
Reported: 2026-05-22
Description: The Windows installer does not install the application to the standard Program Files directory (e.g. C:\Program Files\LosslessBob). Install destination is incorrect or defaults to an unexpected location. May be a misconfigured DefaultDirName or missing {pf} / {autopf} constant in the Inno Setup script.
Root cause: Unknown
Fix: —

BUG-090: Black screen flickers in app at certain times
Status: Open
File(s): unknown
Reported: 2026-05-20
Description: Intermittent black screen flickers occur in the GUI at certain points during use. Trigger conditions not yet isolated — may be related to tab switching, background thread activity, or Qt repaint/viewport timing.
  Note (2026-05-24): User suspects the issue began after a specific code change, possibly
  related to XWayland support or a change made around the same time. Worth checking git
  history around any XWayland-related commits to narrow down the regression point.
Root cause: Unknown — possible regression introduced during XWayland-related changes
Fix: —

BUG-067: PyQt6 + lxml SIGABRT when Qt widget tests run before lxml-importing tests
Status: Open
File(s): tests/test_scraper_crawler.py, tests/test_lb_master.py
Reported: 2026-05-18
Description: Running all three test files in a single pytest process causes a Fatal Python error: Aborted when tests/test_lb_master.py Qt widget tests (TestSearchTabStatusColumn, TestDbEditorIntegrityPanel) run before tests/test_scraper_crawler.py which imports BeautifulSoup (bs4 loads lxml at import time). The SIGABRT is a known incompatibility between PyQt6 cleanup and lxml's memory allocator on Linux.
Root cause: bs4 unconditionally imports lxml at bs4 import time regardless of which parser is used. When lxml's .so is loaded into the same process as PyQt6 objects, Qt's atexit/destructor sequence may SIGABRT.
Fix: Run test files separately (`pytest tests/test_scraper_crawler.py`) or exclude Qt widget tests when running combined (`pytest tests/ -k "not SearchTab and not DbEditor and not CollectionTab"`). All three files pass independently (59 + 27 + 13 = 99 total tests, all green).
