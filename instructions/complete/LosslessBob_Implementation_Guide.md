

**LosslessBob**

Feature Implementation Guide

Torrent Generation  •  Forum Posting  •  qBittorrent Integration  •  Credentials  •  Rename Log



Version 1.1  —  May 2026


# **Overview**

**This document describes how to add four new backend modules and supporting infrastructure to the LosslessBob application. All features are triggered from the My Collection tab.**


| **\#** | **Module** | **New File** | **Depends On** |
| - | - | - | - |
| 1 | Credentials | backend/credentials.py | keyring (pip) |
| 2 | Torrent Generation | backend/torrent\_maker.py | torf (pip), credentials |
| 3 | qBittorrent Integration | backend/qbittorrent.py | requests, credentials |
| 4 | Forum Posting | backend/forum\_poster.py | requests, bs4, credentials |


| **Scope note: **File sharing backends (Internet Archive, Gofile, oshi.at) are out of scope for this phase and will be added later. |
| - |


## **New Dependencies**

**Add to requirements.txt:**

torf\>=4.0.0

keyring\>=25.0.0


**All other dependencies (requests, beautifulsoup4, lxml) are already present.**


## **New Database Tables**

**Run these against data/losslessbob.db before wiring the UI.**


### **torrents**

| **Column** | **Type** | **Notes** |
| - | - | - |
| id | INTEGER PK | Auto-increment |
| lb\_number | INTEGER | FK to entries |
| torrent\_path | TEXT | Absolute path to .torrent in data/torrents/ |
| source\_folder | TEXT | Absolute path to LB folder on disk |
| created\_at | TIMESTAMP |  |
| infohash | TEXT | Read from .torrent via torf at creation time |
| added\_to\_qbt | INTEGER | 0 / 1 |
| added\_to\_qbt\_at | TIMESTAMP | NULL if never added |
| qbt\_infohash\_confirmed | INTEGER | 0 / 1 |
| last\_seen\_at | TIMESTAMP | Last time source\_folder verified on disk |
| excluded\_files | TEXT | JSON list of files excluded from torrent |


### **rename\_history**

| **Column** | **Type** | **Notes** |
| - | - | - |
| id | INTEGER PK |  |
| lb\_number | INTEGER | FK to entries |
| old\_path | TEXT |  |
| new\_path | TEXT |  |
| renamed\_at | TIMESTAMP |  |
| source | TEXT | 'rename\_tab', 'collection\_tab', 'auto' |
| notes | TEXT | Warnings, mismatch details, relocation notes |


| **Rename tab: **Update gui/rename\_tab.py to write to rename\_history on every executed rename. Also update it to append to rename\_log.txt inside each folder (see Rename Log section). |
| - |


# **Module 1 — Credentials**

**File: backend/credentials.py**


## **Purpose**

**Secure credential storage using the OS keyring as primary backend and a Qt dialog prompt as fallback. Credentials are never written to the SQLite meta table or any file on disk.**


## **Keyring Backends by Platform**

| **Platform** | **Backend** |
| - | - |
| Linux (GNOME) | Secret Service via libsecret |
| Linux (KDE) | KWallet |
| Windows | Windows Credential Manager |
| macOS | Keychain |


## **Service Name Constants**

| **Constant** | **Value** | **Used For** |
| - | - | - |
| SERVICE\_QBT | losslessbob\_qbittorrent | qBittorrent WebUI |
| SERVICE\_WTRF | losslessbob\_wtrf | Watching the River Flow forum |


## **Public API**

| **Function** | **Returns** | **Notes** |
| - | - | - |
| keyring\_available() | bool | Cached after first call |
| save\_credentials(service, user, pass) | StorageResult | result.label for UI status |
| get\_credentials(service) | tuple\[str,str\] | Returns ('','') if not stored |
| delete\_credentials(service) | bool | Silent if nothing stored |
| credentials\_stored(service) | bool | Quick presence check for UI |
| prompt\_if\_missing(service, label, parent) | tuple | None | None = user cancelled |


## **Implementation Steps**

1. Create backend/credentials.py from the module prepared in the design session.

2. Add keyring to requirements.txt.

3. Add Credentials sections to Setup tab for SERVICE\_QBT and SERVICE\_WTRF (see Setup Tab Additions).

4. Use prompt\_if\_missing() as the single call pattern everywhere credentials are needed throughout the app.


| **Fallback: **When no keyring is available the dialog informs the user credentials will only be used for the current session and are not saved. The app proceeds normally. |
| - |


# **Module 2 — Torrent Generation**

**File: backend/torrent\_maker.py**


## **Purpose**

**Generates .torrent files from LB recording folders on disk. Triggered from the My Collection tab for single or multiple selected entries. Each entry produces one .torrent file written to data/torrents/.**


## **Torrent Name Format**

YYYY-MM-DD Location Name (LB-XXXXX)


**Examples:**

1966-05-17 Manchester Free Trade Hall (LB-00042)

1975-10-16 New York City (LB-01025)


## **Tracker Source**

- Fetched live from ngosang/trackerslist via jsDelivr CDN

- Default list: trackers\_best  (~20 trackers, updated daily by the repo)

- Cached in-process after first fetch — one network call per session per list

- Available list names: best, all, all\_udp, all\_http, all\_https

- Configurable in Setup tab — user can select list and force refresh


## **Private Flag**

**All torrents are created with private=True. This sets the info.private flag in the torrent dict, which disables DHT, PEX, and LSD in all compliant clients on both Windows and Linux.**


## **Exclusion List  (TORRENT\_EXCLUDE)**

| **Pattern** | **Reason** |
| - | - |
| rename\_log.txt | Local housekeeping — not part of the recording |
| \*\_mychecksums.ffp | Locally generated — not original release files |
| \*\_mychecksums.md5 | Locally generated — not original release files |
| \*\_mychecksums.st5 | Locally generated — not original release files |
| \*.torrent | Stray torrent files inside the folder |
| Thumbs.db | Windows thumbnail cache |
| .DS\_Store | macOS metadata |


| **Checksums: **Original .ffp, .md5 and .st5 files that shipped with the LosslessBob release are included. Only locally generated \_mychecksums variants are excluded. The exact \_mychecksums filename convention is to be confirmed before finalising this list. |
| - |


## **Batch Behaviour**

- Each selected entry generates one independent .torrent file

- Errors skip and continue — one failure does not abort the batch

- Error summary shown on completion: LB number and reason for each failure

- Each successful torrent is written to the torrents table immediately on creation


## **Implementation Steps**

1. Create backend/torrent\_maker.py from the module prepared in the design session.

2. Add torf to requirements.txt.

3. Create the data/torrents/ directory and add it to .gitignore.

4. Run the DB migration to create the torrents table.

5. Add Flask route POST /api/torrent/create accepting lb\_number and source\_folder. Call make\_torrent\_with\_progress(), write record to torrents table, return torrent\_path and infohash.

6. Add Create Torrent button to My Collection tab — enabled for single and multi-select. Run in a QThread. Emit per-torrent hashing progress and overall batch count to QProgressBar.

7. On batch completion display error summary for any failed entries.

8. Confirm \_mychecksums filename convention and finalise TORRENT\_EXCLUDE before first use.


# **Module 3 — qBittorrent Integration**

**File: backend/qbittorrent.py**


## **Purpose**

**Adds generated .torrent files to a qBittorrent instance via the WebUI API v2. Sets save\_path to the parent of each source folder so qBittorrent finds the existing files and begins seeding immediately without re-downloading.**


## **save\_path Logic**

source\_folder  =  /music/Dylan/1966-05-17 Manchester Free Trade Hall (LB-00042)

save\_path      =  /music/Dylan    ←  parent directory


**qBittorrent resolves the folder by name from save\_path and starts seeding. If entries have source folders on different drives or parent directories, each torrent add call derives its own save\_path automatically.**


## **Single vs Batch Add**

| **Action** | **Source** | **Behaviour** |
| - | - | - |
| Add to qBittorrent | Single selected entry | Adds one torrent, updates torrents table |
| Add All to qBittorrent | All entries in current session batch | Loops per torrent, skip and continue on error |
| Add from history panel | Previously generated torrent record | Uses stored torrent\_path and source\_folder |


## **Torrent History Panel  (My Collection Tab)**

**Lists all records from the torrents table for the selected entry:**

- Green indicator — source\_folder exists on disk

- Red indicator — source\_folder path no longer valid

- Regenerate button — if torrent\_path file is missing from data/torrents/

- Add to qBittorrent — available regardless of added\_to\_qbt status (allows re-add)

- added\_to\_qbt\_at timestamp shown per record


## **Path Relocation Flow**

**When a user clicks Add to qBittorrent on a red-indicator record:**

1. File browser dialog opens — user selects new folder location.

2. App cross-checks new folder contents against checksums table by filename. Shows warning on mismatch but allows proceeding.

3. source\_folder updated in torrents table.

4. Folder name checked against standard format YYYY-MM-DD Location Name (LB-XXXXX).

5. If name does not match — rename suggestion offered inline without switching to Rename tab.

6. User accepts, skips, or defers rename — qBittorrent add proceeds regardless.

7. If renamed — source\_folder updated again, rename\_history row inserted, rename\_log.txt in folder appended.


## **Implementation Steps**

1. Create backend/qbittorrent.py from the module prepared in the design session.

2. Add qBittorrent credentials section to Setup tab (see Setup Tab Additions).

3. Add Flask route POST /api/qbt/add accepting lb\_number (single) or lb\_numbers list (batch). Look up torrent\_path and source\_folder from torrents table. Call add\_torrent\_for\_seeding() per entry.

4. On success update added\_to\_qbt=1 and added\_to\_qbt\_at in torrents table.

5. Wire Add to qBittorrent and Add All buttons in My Collection tab. Batch runs in a QThread, skip and continue, error summary on completion.

6. Implement torrent history panel with path validation, red/green indicators, and Regenerate button.

7. Implement path relocation flow including inline rename suggestion.


# **Module 4 — Forum Posting**

**File: backend/forum\_poster.py**


## **Purpose**

**Posts a new topic to the Watching the River Flow forum (SMF 2.x) for a selected LB entry. Single entry only — not a batch operation. A .torrent file for the entry must exist before posting is enabled.**


## **Post Format**

| **Field** | **Content** |
| - | - |
| Subject | YYYY-MM-DD Location Name (LB-XXXXX) |
| Body line 1 | Info .txt file content wrapped in \[code\] BBcode block |
| Body line 2 | FFP .ffp file content wrapped in \[code\] BBcode block |
| Attachment | The generated .torrent file for this entry |
| Board | Board 16  (index.php?board=16.0) |


| **Body fallback: **If no cached .txt or .ffp file exists in data/attachments/LB-XXXXX/, the body is assembled from the entries table fields: date\_str, location, cdr, rating, timing, description, setlist. |
| - |


## **Login Method**

**HTTP session via requests + BeautifulSoup. Hidden form fields (sc, seqnum) are scraped from the SMF compose page before each post. Session cookie used for auth throughout.**


| **Attachments: **SMF accepts file attachments via multipart POST to ?action=post;sa=post2. The .torrent file is sent as attachment\[\] with MIME type application/x-bittorrent. Forum attachment restrictions (size, type whitelist) apply — .torrent files are universally permitted on SMF. |
| - |


## **Implementation Steps**

1. Create backend/forum\_poster.py from the module prepared in the design session.

2. Add WTRF credentials section to Setup tab (see Setup Tab Additions).

3. Add Flask route POST /api/entry/\<lb\>/post\_forum. Accept optional attachments list. Retrieve credentials via keyring. Call post\_lb\_topic().

4. Wire Post to Forum button in My Collection tab — single entry only. Disable button if no torrent record exists for this entry.

5. Call prompt\_if\_missing(SERVICE\_WTRF, 'Watching the River Flow', parent=self) before posting.

6. On success display the returned topic URL in the status bar and offer to open in the system browser.

7. On failure display the error message. Common failures: login rejected, CAPTCHA (manual login required), attachment rejected.


# **Rename Log**


## **Purpose**

**Every folder rename is recorded in two places simultaneously. The rename\_history database table enables app-wide querying and history views. The rename\_log.txt file inside each folder lets the folder carry its own history independently of the database.**


## **rename\_log.txt Format**

2026-05-12 14:32:01  \[rename\_tab\]      "1966-05-17 Manchester" → "1966-05-17 Manchester Free Trade Hall (LB-00042)"

2026-05-14 09:15:44  \[collection\_tab\]  path relocated: /mnt/archive/Dylan/

2026-05-15 11:02:33  \[collection\_tab\]  "1966-05-17 Manchester Free Trade Hall (LB-00042)" → "1966-05-17 Manchester Free Trade Hall (LB-00042)"  \[file mismatch warning: 3 unexpected files\]


- Append-only — never overwritten or recreated

- Written before os.rename() executes so the log entry survives inside the newly named folder

- Relocation events (folder moved, not renamed) logged as path relocated notes

- File mismatch warnings included inline when they occur

- Excluded from generated torrents via TORRENT\_EXCLUDE


## **Shared Helper**

**A single write\_rename\_log() function handles all origins to ensure consistent formatting:**

write\_rename\_log(folder\_path, old\_name, new\_name, source, notes='')


**This function appends one line to rename\_log.txt inside folder\_path and inserts one row into rename\_history. It is called by both the Rename tab and the My Collection tab path relocation flow.**


## **Implementation Steps**

1. Create the write\_rename\_log() helper — place in backend/db.py or a new backend/rename.py.

2. Update gui/rename\_tab.py to call write\_rename\_log() on every executed rename.

3. My Collection tab path relocation calls write\_rename\_log() with source='collection\_tab'.

4. Verify rename\_log.txt is present in TORRENT\_EXCLUDE in torrent\_maker.py.

5. Run DB migration to create rename\_history table.


# **Setup Tab Additions**

**Add the following sections to gui/setup\_tab.py. Non-sensitive settings save to the meta table. Credentials save to the keyring via credentials.py. On load, call credentials\_stored() to show the correct status label without retrieving the actual password.**


## **qBittorrent Section**

| **Widget** | **meta key** | **Notes** |
| - | - | - |
| QLineEdit — Host | qbt\_host | Default: localhost |
| QSpinBox — Port | qbt\_port | Default: 8080 |
| QLineEdit — Username | — | Keyring via SERVICE\_QBT |
| QLineEdit — Password (masked) | — | Keyring via SERVICE\_QBT |
| QLineEdit — Category | qbt\_category | Optional e.g. losslessbob |
| QLineEdit — Tags | qbt\_tags | Optional comma-separated |
| QPushButton — Save Credentials | — | Calls save\_credentials(SERVICE\_QBT, ...) |
| QPushButton — Test Connection | — | Calls test\_connection(), shows version string |
| QPushButton — Clear Credentials | — | Calls delete\_credentials(SERVICE\_QBT) |
| QLabel — Status | — | Shows StorageResult.label |


## **WTRF Forum Section**

| **Widget** | **meta key** | **Notes** |
| - | - | - |
| QLineEdit — Username | — | Keyring via SERVICE\_WTRF |
| QLineEdit — Password (masked) | — | Keyring via SERVICE\_WTRF |
| QPushButton — Save Credentials | — | Calls save\_credentials(SERVICE\_WTRF, ...) |
| QPushButton — Clear Credentials | — | Calls delete\_credentials(SERVICE\_WTRF) |
| QLabel — Status | — | Shows StorageResult.label |


## **Torrent Section**

| **Widget** | **meta key** | **Notes** |
| - | - | - |
| QComboBox — Tracker list | tracker\_list | best / all / all\_udp / all\_http / all\_https |
| QPushButton — Refresh Trackers | — | Calls fetch\_trackers(force\_refresh=True) |
| QLabel — Tracker count / status | — | e.g. '20 trackers loaded' |



**End of LosslessBob Feature Implementation Guide  —  Phase 1**

**File sharing backends (Internet Archive, Gofile, oshi.at) will be documented in a separate Phase 2 guide.**
