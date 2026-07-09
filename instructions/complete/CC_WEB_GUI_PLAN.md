# Plan: Web GUI — Full Implementation Guide

**Created:** 2026-05-19  
**Status:** Not started  
**Tracks:** TODO-050 through TODO-066

---

## Context and Goal

LosslessBob is a PyQt6 desktop app. Its Flask backend (port 5174) already exposes 80+
REST endpoints covering every tab in the desktop UI. The goal is to add a browser-based
UI served by the same Flask process so the app is accessible from a browser on the same
machine or the LAN — without replacing or breaking the desktop UI.

**What is already done that this feature builds on:**

| Already exists | Notes |
|---|---|
| Flask on `0.0.0.0:5174` | Phase 3 LAN binding from original spec is already shipped |
| `/admin` — admin control panel | Single-file HTML, dark theme — the reference pattern |
| `/map` — Leaflet concert map | Single-file HTML using fetch + vanilla JS — also reference pattern |
| `GET /api/status` | Combined DB + bootleg stats in one call |
| All data endpoints | 80+ routes covering every feature |

---

## Architecture Decision

**Vanilla JS multi-page, no build step.** Each web tab is a self-contained HTML file
served via Flask, matching the admin.html / map.html pattern exactly. A shared
`frontend/nav.html` snippet is inlined by a Jinja2 template base, or duplicated as a
simple `<nav>` block in each file.

Rationale:
- Zero build toolchain — no npm, webpack, Vite needed
- Consistent with admin.html / map.html already in the codebase
- Each page is independently deployable and reviewable
- Framework upgrade (React/Vue) possible later without discarding this work

**Not chosen:** React/Vue SPA — adds build step complexity for a local tool used by one person.

---

## File Layout

```
frontend/
├── index.html            # Landing page / redirect to /web/search
├── base.css              # Shared dark-theme CSS (variables, nav, table, button, form styles)
├── utils.js              # Shared JS: apiFetch(), escapeHtml(), statusBadge(), pagination()
├── search.html           # Search tab
├── lookup.html           # Lookup tab (checksum paste)
├── collection.html       # My Collection tab (owned + missing + wishlist)
├── entry.html            # Entry detail page (linked from search/collection rows)
├── lb_master.html        # LB Master status viewer
└── bootlegs.html         # Bootleg catalog browser
```

Flask routes added to `backend/app.py`:
- `GET /` → redirect to `/web/search`
- `GET /web/<page>` → `send_from_directory("frontend/", page + ".html")`
- `GET /frontend/<path:filename>` → serve CSS/JS from `frontend/`

Admin panel (`/admin`) and Map (`/map`) already served; just need nav links added.

---

## Shared Infrastructure

### base.css
Dark theme matching `admin.html` CSS variables:
```
--bg, --surface, --surface2, --border, --text, --muted
--accent, --success, --warning, --danger, --radius
```
Components: nav bar, data table (sortable header, hover rows, status-color rows),
pagination controls, filter bar, loading spinner, error banner, status badge.

### utils.js
```js
apiFetch(url, options)   // fetch wrapper: throws on non-2xx, parses JSON
escapeHtml(str)          // XSS-safe string escape
statusBadge(status)      // returns <span> with colour for public/private/missing
formatDate(dateStr)      // "DD/MM/YY" → readable
paginate(items, page, size)  // client-side pagination helper
debounce(fn, ms)         // for live search inputs
```

### Nav bar
Fixed top bar with links: Search · Lookup · Collection · Map · Bootlegs · LB Master · Admin  
Active tab highlighted. Shows DB stats from `GET /api/status` in the corner (LB count,
entry count). Responsive — collapses to hamburger on narrow screens.

---

## Phase 1 — Infrastructure (TODO-050 to TODO-052)

### TODO-050: Flask routes for frontend static files
**File:** `backend/app.py`  
Add three routes at the bottom of `register_routes()`:

```python
@app.route("/")
def web_root():
    return redirect("/web/search")

@app.route("/web/<page>")
def web_page(page: str):
    allowed = {"search","lookup","collection","entry","lb_master","bootlegs","index"}
    if page not in allowed:
        abort(404)
    frontend_dir = (Path(__file__).parent.parent / "frontend").resolve()
    return send_from_directory(str(frontend_dir), page + ".html")

@app.route("/frontend/<path:filename>")
def web_static(filename: str):
    frontend_dir = (Path(__file__).parent.parent / "frontend").resolve()
    return send_from_directory(str(frontend_dir), filename)
```

Note: `/` redirect must not conflict with any existing route. Verify no existing `/`
route exists first.

### TODO-051: frontend/base.css — shared dark theme stylesheet
**File:** `frontend/base.css` (new)  
Port the CSS variables and component styles from `backend/admin.html` into a standalone
stylesheet. Components required at this stage: `:root` variables, `body`, `header/nav`,
`.btn`, `.badge` (status colours), `.spinner`, `.error-banner`.

### TODO-052: frontend/utils.js — shared JS utilities
**File:** `frontend/utils.js` (new)  
Implement: `apiFetch`, `escapeHtml`, `statusBadge`, `formatDate`, `paginate`, `debounce`.
Test manually by opening browser console on the `/web/search` page.

---

## Phase 2 — Search Tab (TODO-053 to TODO-054)

**API used:** `GET /api/search?q=&field=&year=`, `GET /api/search/years`,  
`GET /api/checksums/xref_lb_numbers`

### TODO-053: frontend/search.html — Search tab
**File:** `frontend/search.html` (new)

Layout:
```
[Nav bar]
[Filter bar: text input | field combo | year combo | Status filter | Xref-only | Search btn]
[Results table: LB# | Status | Date | Location | Rating | Description | Xref | Owned]
[Pagination bar: Prev | Page N of M | Next | per-page select]
[Status: "N results"]
```

Features:
- On load: fetch years from `/api/search/years`, populate year combo
- On Search: `GET /api/search?q=&field=all&year=` → render table
- Status badge: colour-code rows by `lb_status` (public=default, private=light-blue,
  missing=light-gray) — match desktop tab exactly
- Owned column: fetch `GET /api/collection/lb_numbers` on page load; mark matching rows ★
- Xref-only toggle: fetch `/api/checksums/xref_lb_numbers`; filter client-side
- Row click → open `/web/entry?lb=<lb_number>` in same tab
- Client-side sort on all columns (same sort key logic as desktop)
- Pagination: 50 rows/page default

### TODO-054: Owned column async load for search results
After results render, fire a background `GET /api/collection/lb_numbers` and update
the Owned column cells in-place. Matches the pattern in `search_tab.py:_OwnedWorker`.

---

## Phase 3 — Lookup Tab (TODO-055)

**API used:** `POST /api/lookup` body: `{checksums: [...]}`

### TODO-055: frontend/lookup.html — Lookup tab
**File:** `frontend/lookup.html` (new)

Layout:
```
[Nav bar]
[Textarea: paste FFP/MD5/ST5 checksum text here]
[Lookup btn]    [Clear btn]
[Summary table: Source | Given | Matched | Not Found | Missing | Dups | Xrefs | Status]
[Detail table: Checksum | Filename | Type | LB# | Xref | Status | Source]
```

Features:
- Parse textarea content client-side: split lines, detect type (ffp/md5/st5), POST
  `{checksums: [...]}` to `/api/lookup`
- Summary row click → filter detail table to that source
- LB# in detail table → link to `/web/entry?lb=<lb_number>`
- Status colour coding matching desktop (green=matched, red=not found, orange=missing,
  yellow=xref, gray=duplicate)
- "Copy results" button: copy detail table as TSV to clipboard

---

## Phase 4 — Collection Tab (TODO-056 to TODO-057)

**API used:**  
- `GET /api/collection` — owned LBs  
- `GET /api/collection/missing` — LBs in master without owned folder  
- `GET /api/wishlist` — wishlist  
- `POST /api/collection` — add to collection  
- `DELETE /api/collection/<lb>` — remove from collection  
- `GET /api/collection/search?q=` — search within collection

### TODO-056: frontend/collection.html — My Collection tab (read)
**File:** `frontend/collection.html` (new)

Layout — three sub-panels via tab pills:
```
[Nav bar]
[Pills: Owned (N) | Missing (N) | Wishlist (N)]

Owned panel:
  [Filter bar: text | status | xref-only | owned-only | search btn]
  [Table: LB# | Status | Date | Location | Folder | Disk Path | Confirmed | Notes]
  [Pagination]

Missing panel:
  [Table: LB# | Status | Date | Location | Rating | Description]
  [Pagination]

Wishlist panel:
  [Table: LB# | Date | Location | Rating | Priority | Notes | Added]
```

### TODO-057: frontend/collection.html — write operations
Add to the Owned panel:
- "Remove from Collection" button per row (DELETE `/api/collection/<lb>` then reload)
- Confirm dialog before removal
- "Add to Wishlist" button for Missing rows (POST `/api/wishlist`)
- Counts in tab pills update after mutation

---

## Phase 5 — Entry Detail Page (TODO-058)

**API used:**  
- `GET /api/entry/<lb>` — entry + checksums + files  
- `GET /api/entry/<lb>/changes` — field change history  
- `GET /api/lb_master/<lb>` — master status  
- `GET /api/collection/<lb>/meta` — personal notes  
- `POST /api/collection` — add to collection from this page  
- `GET /api/entry/<lb>/preview_forum` — forum post preview

### TODO-058: frontend/entry.html — Entry detail page
**File:** `frontend/entry.html` (new)  
Opened as `/web/entry?lb=<lb_number>` from Search/Collection/Lookup links.

Layout:
```
[Nav bar]
[Breadcrumb: Search > LB-XXXXX]

[Header: LB-XXXXX | date | location | status badge | owned/not-owned badge]
[Description panel]

[Checksum table: Filename | Checksum | Type | Xref]
[Files table: Filename | Size | Path (if entry_files has paths)]

[Collapsible: Change History (GET /api/entry/<lb>/changes)]
[Collapsible: LB Master record (lb_status, manual_override, needs_review)]
[Collapsible: Personal Notes (GET /api/collection/<lb>/meta)]

[Actions: Add to Collection | Add to Wishlist | Forum Preview (opens modal)]
```

---

## Phase 6 — LB Master Viewer (TODO-059)

**API used:**  
- `GET /api/lb_master?status=&limit=&offset=` — paginated list  
- `GET /api/lb_master/stats` — counts by status  
- `GET /api/lb_master/history/<lb>` — override history

### TODO-059: frontend/lb_master.html — LB Master status browser
**File:** `frontend/lb_master.html` (new)

Layout:
```
[Nav bar]
[Stats bar: N public | N private | N missing | N with overrides | N needs review]
[Filter bar: status | needs_review | manual_override | text search]
[Table: LB# | Status | Manual Override | Needs Review | Last Updated]
[Pagination]
[Row click → expand history inline (GET /api/lb_master/history/<lb>)]
```

---

## Phase 7 — Bootlegs Tab (TODO-060)

**API used:**  
- `GET /api/bootlegs?q=&year=&format=` — paginated list  
- `GET /api/bootlegs/stats` — counts  
- `GET /api/bootlegs/by_lb/<lb>` — bootleg detail for a specific LB

### TODO-060: frontend/bootlegs.html — Bootleg catalog browser
**File:** `frontend/bootlegs.html` (new)

Layout:
```
[Nav bar]
[Stats bar: N total bootlegs | N LBs with bootleg releases]
[Filter bar: text | year | format]
[Table: LB# | Title | Year | Format | Source | Label]
[Row click → expand bootleg detail panel]
```

---

## Phase 8 — Nav Integration and Polish (TODO-061 to TODO-063)

### TODO-061: Add web nav links to admin.html and map.html
**Files:** `backend/admin.html`, `gui/resources/map.html`  
Add the shared nav bar (or a minimal "← App" back-link) to the existing admin and map
pages so they feel part of the same UI.

### TODO-062: frontend/index.html — landing redirect
**File:** `frontend/index.html`  
Simple redirect page: `<meta http-equiv="refresh" content="0; url=/web/search">` with
a JS fallback. Shown when someone hits `http://localhost:5174/` directly.

### TODO-063: Status bar data in nav
Add a lightweight `GET /api/status` call on every page load (already returns DB counts
+ bootleg stats in one hit). Display entry count and DB status in the nav bar corner.

---

## Phase 9 — LAN Auth (TODO-064 to TODO-065)

Since Flask is already bound to `0.0.0.0`, anyone on the LAN can reach the app.
Before the web UI ships, optional basic auth should be available for users who care
about LAN security.

### TODO-064: Optional basic-auth middleware for web routes
**File:** `backend/app.py`

Add a `before_request` hook that checks for a `web_password` meta key:
```python
@app.before_request
def _check_web_auth():
    if not _is_web_route(request.path):  # skip /api/* and /admin
        return
    pw = database.get_meta("web_password")
    if not pw:
        return  # auth disabled
    auth = request.authorization
    if not auth or auth.password != pw:
        return Response("Unauthorized", 401,
                        {"WWW-Authenticate": 'Basic realm="LosslessBob"'})
```

Scope: protect `/web/*` and `/frontend/*` only. API routes (`/api/*`) remain
unauthenticated since the desktop app calls them directly.

### TODO-065: Web password setting in Setup tab
**File:** `gui/setup_tab.py`, `backend/app.py:db_settings`  
Add "Web GUI Password" QLineEdit (password mode) in Setup → Network section.
POST to `/api/db/settings` with `{web_password: "..."}`. Empty string = disabled.
Add `web_password` to the `keys` list in `db_settings()` GET handler (masked: return
`"set"` or `""`, never the actual value).

---

## Phase 10 — Docs and Cleanup (TODO-066)

### TODO-066: Docs update after web GUI ships
**Files:** `PROJECT.md`, `README.md`, `CHANGELOG.md`

PROJECT.md:
- Add `frontend/` to File Structure with one-liner per file
- Add web routes to Backend section (`GET /`, `GET /web/<page>`, `GET /frontend/<path>`)
- Note LAN auth mechanism

README.md:
- Add "Web UI" section: how to open, LAN access, setting a password
- Privacy note: web UI exposes the same data as the desktop app to anyone on the LAN
  unless a password is set

---

## TODO List Summary

| # | Priority | Phase | Title |
|---|---|---|---|
| TODO-050 | High | 1 | Flask routes for frontend static files |
| TODO-051 | High | 1 | frontend/base.css — shared dark theme |
| TODO-052 | High | 1 | frontend/utils.js — shared JS utilities |
| TODO-053 | High | 2 | frontend/search.html — Search tab |
| TODO-054 | Medium | 2 | Search tab: owned column async load |
| TODO-055 | High | 3 | frontend/lookup.html — Lookup tab |
| TODO-056 | High | 4 | frontend/collection.html — Collection tab (read) |
| TODO-057 | Medium | 4 | Collection tab: add/remove write operations |
| TODO-058 | High | 5 | frontend/entry.html — Entry detail page |
| TODO-059 | Medium | 6 | frontend/lb_master.html — LB Master viewer |
| TODO-060 | Low | 7 | frontend/bootlegs.html — Bootlegs tab |
| TODO-061 | Low | 8 | Add web nav links to admin.html and map.html |
| TODO-062 | Low | 8 | frontend/index.html — landing redirect |
| TODO-063 | Low | 8 | Status bar data in nav |
| TODO-064 | High | 9 | Optional basic-auth middleware for web routes |
| TODO-065 | High | 9 | Web password setting in Setup tab |
| TODO-066 | Low | 10 | Docs update after web GUI ships |

**Recommended build order:** 050 → 051 → 052 → 064 → 065 → 053 → 054 → 055 → 056 →
057 → 058 → 059 → 060 → 061 → 062 → 063 → 066

Do auth (064/065) before any UI page, since the Flask server is already LAN-accessible.

---

## API Routes Consumed Per Page

| Page | GET | POST/PATCH/DELETE |
|---|---|---|
| search.html | /api/search, /api/search/years, /api/collection/lb_numbers, /api/checksums/xref_lb_numbers | — |
| lookup.html | — | POST /api/lookup |
| collection.html | /api/collection, /api/collection/missing, /api/wishlist, /api/collection/search | DELETE /api/collection/<lb>, POST /api/wishlist |
| entry.html | /api/entry/<lb>, /api/entry/<lb>/changes, /api/lb_master/<lb>, /api/collection/<lb>/meta | POST /api/collection, DELETE /api/collection/<lb> |
| lb_master.html | /api/lb_master, /api/lb_master/stats, /api/lb_master/history/<lb> | — |
| bootlegs.html | /api/bootlegs, /api/bootlegs/stats, /api/bootlegs/by_lb/<lb> | — |
| nav (all pages) | /api/status | — |

---

## Out of Scope for This Plan

These desktop tabs require local filesystem access that a browser cannot provide:
- **Rename tab** — needs to read/write local folder names
- **Verify tab** — needs to hash local files
- **LBDir tab** — needs to traverse local directory trees
- **Spectrogram tab** — needs to run sox against local audio files

These could theoretically be wired through the Flask backend (which has full filesystem
access), but the UX for file-path input from a browser is awkward and not worth the
effort for a local tool.

---

## Deferred

- Torrent creation from browser (POST /api/torrent/create requires torrent-maker path
  input — awkward from browser)
- Forum posting from browser (functional via API, but WYSIWYG BBCode preview in browser
  is extra work)
- qBittorrent management from browser (POST /api/qbt/add — requires torrent file upload
  which is more complex)
- Docker / headless deployment (useful if someone wants to run this as a NAS service;
  requires removing PyQt6 dependency from startup or running Flask independently)
