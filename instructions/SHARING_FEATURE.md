# Plan: Share Audio Folder with a Friend over the Internet

## Context

Users want to send a folder of audio files (FLAC/SHN/APE/WAV) from their LosslessBob collection
to a friend over the internet. Concert recordings are typically 300 MB–2 GB per folder. The friend
needs only a browser — no CLI tools, no account. The existing Flask backend on port 5174 is
extended with file-sharing routes, and a Cloudflare Tunnel exposes it publicly. Optionally the user
can map the tunnel to their own domain for a permanent, stable URL.

---

## Overview

- New backend module `backend/sharing.py` — share state, streaming generators, tunnel lifecycle
- New Flask routes in `backend/app.py` — serve file listings and downloads under `/api/share/`
- `_ShareDialog(QDialog)` in `gui/collection_tab.py` — GUI to create, show, and stop shares
- "Share Folder…" added to the collection context menu and `torrent_row` button bar
- `cloudflared` binary (single Go binary, no Python package) provides the public tunnel
- No new DB tables — shares are ephemeral, stored in memory; tunnel state persisted to
  `data/active_share.json` so shares survive app restarts within their TTL

**Why Cloudflare Tunnel over ngrok:**
- No bandwidth cap on free tier (ngrok caps at ~1 GB/month — one concert can hit that)
- No browser interstitials on free tier
- Own-domain support: permanent `share.yourdomain.com` URL via a DNS CNAME
- Single static binary, no Python package dependency
- Your home IP is never exposed to the friend

---

## Cloudflare Tunnel: Two Modes

### Mode A — Quick share (no account, random URL)

```bash
cloudflared tunnel --url http://localhost:5174 --no-autoupdate
```

Cloudflare assigns a random `*.trycloudflare.com` URL. No account needed. The URL changes each
time the tunnel restarts. Run as a detached subprocess (see Step 1 below) so it outlives the app.

### Mode B — Named tunnel with own domain (permanent URL)

One-time setup (user does this manually once):

```bash
cloudflared tunnel create losslessbob
cloudflared tunnel route dns losslessbob share.yourdomain.com
cloudflared service install          # runs as systemd daemon, survives reboots
```

`~/.cloudflared/config.yml`:
```yaml
tunnel: <uuid>
credentials-file: /home/<user>/.cloudflared/<uuid>.json
ingress:
  - hostname: share.yourdomain.com
    service: http://localhost:5174
  - service: http_status:404
```

The friend's URL becomes `https://share.yourdomain.com/api/share/<token>/` — permanent, no
matter how many times the app or tunnel restarts. Requires the domain's nameservers pointed to
Cloudflare (free plan).

### Optional: Cloudflare Access (email OTP auth)

If configured in the Zero Trust dashboard, even a publicly posted URL is safe: Cloudflare
challenges visitors before they reach the Flask server. Add an Access policy allowing specific
email addresses. The app detects this by checking for the `CF-Access-Authenticated-User-Email`
request header.

---

## Security Model

| Layer | Default (token-only) | With Cloudflare Access |
|---|---|---|
| Transport | TLS (Cloudflare terminates) | Same |
| Auth | 128-bit URL token (obscurity) | Email OTP / OAuth required |
| Your home IP | Hidden | Hidden |
| Link leaked online | Anyone with URL can download | Safe — Cloudflare blocks them |
| Share expiry | Enforced at request time | Same |

Token is generated with `secrets.token_urlsafe(16)` — 128 bits of entropy, brute-force
impractical. Shares expire after configurable TTL (default 24 h); expired tokens return 404.

---

## New File: `backend/sharing.py`

All share state and streaming logic. Keeps `app.py` thin.

```python
# Module-level state
_active_shares: dict[str, dict] = {}   # token → {folder_path, files, expires_at, tunnel_url}
_shares_lock = threading.Lock()
SHARE_STATE_FILE = Path("data/active_share.json")
AUDIO_EXTENSIONS = {".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".m4a", ".wv"}
```

Key functions:

- `create_share(folder_path, ttl_hours) -> dict` — enumerate audio files by extension, generate
  token via `secrets.token_urlsafe(16)`, store entry, persist to `SHARE_STATE_FILE`
- `get_share(token) -> dict | None` — checks expiry, returns share dict or `None`
- `revoke_share(token) -> None` — removes from dict, updates `SHARE_STATE_FILE`
- `load_persisted_shares() -> None` — called at startup; re-loads `SHARE_STATE_FILE`, drops
  already-expired entries
- `stream_file(folder_path, filename) -> Generator` — validates no path traversal
  (`assert Path(filename).name == filename`), yields 1 MB chunks
- `stream_zip(folder_path, files) -> Generator` — producer thread writes
  `zipfile.ZipFile(allowZip64=True)` into a custom `io.RawIOBase` that enqueues chunks;
  generator yields from `queue.SimpleQueue`. Memory-bounded regardless of folder size:

```python
class _QueueWriter(io.RawIOBase):
    def write(self, b):
        buf_queue.put(bytes(b))
        return len(b)

def _zip_thread():
    with zipfile.ZipFile(_QueueWriter(), "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for fname in files:
            zf.write(Path(folder_path) / fname, arcname=fname)
    buf_queue.put(None)   # sentinel
```

- `start_cloudflare_tunnel(port) -> str | None` — checks `shutil.which("cloudflared")`;
  launches `cloudflared tunnel --url http://localhost:<port> --no-autoupdate` as
  `subprocess.Popen(start_new_session=True)` (detached); parses stdout for the public URL
  (cloudflared prints `+your tunnel is at https://...` within ~3 s); saves PID to
  `SHARE_STATE_FILE`; returns URL or `None` if cloudflared not found
- `stop_cloudflare_tunnel() -> None` — reads saved PID, sends SIGTERM
- `is_tunnel_alive() -> bool` — `os.kill(pid, 0)` with try/except
- `_expiry_reaper()` — daemon thread, wakes every 5 min, calls `revoke_share` for expired tokens;
  calls `stop_cloudflare_tunnel()` when no shares remain

---

## Flask Routes in `backend/app.py`

Add a new section inside `create_app()` after the collection routes:

```
# ── File Sharing ───────────────────────────────────────────────────────────
```

| Route | Method | Description |
|---|---|---|
| `/api/share/create` | POST | Body: `{lb_number, ttl_hours?, use_tunnel?}`. Resolve `disk_path` from `my_collection`. Call `sharing.create_share()`. If `use_tunnel` and tunnel not alive, call `start_cloudflare_tunnel(5174)`. Return `{token, share_url, tunnel_url?, files, expires_at}`. |
| `/api/share/<token>/` | GET | Return self-contained inline HTML file listing (module-level string constant, no CDN deps). 404 if token unknown/expired. |
| `/api/share/<token>/file/<path:filename>` | GET | Validate token + filename. `send_file(path, conditional=True, as_attachment=True)`. Werkzeug handles `Range:` / `206` / `ETag` automatically — zero extra code for resumable downloads. |
| `/api/share/<token>/zip` | GET | `Response(sharing.stream_zip(...), mimetype='application/zip', headers={'Content-Disposition': 'attachment; filename="LB-XXXXX.zip"'})`. No `Content-Length` — chunked transfer. |
| `/api/share/list` | GET | JSON list of active shares for GUI status display. |
| `/api/share/<token>` | DELETE | Revoke share; stop tunnel if no shares remain. |
| `/api/share/tunnel/status` | GET | `{cloudflared_available: bool, tunnel_alive: bool, tunnel_url: str?}` — used by Setup tab indicator. |

---

## GUI Changes in `gui/collection_tab.py`

### `_ShareDialog(QDialog)`

Shown via "Share Folder…" from context menu. Fields:

- Folder name + total audio size (computed once on open)
- "Expires after" `QComboBox`: 4 h / 12 h / 24 h / 48 h / 1 week
- "Share over internet" `QCheckBox` — disabled with tooltip if `cloudflared` not on PATH
- "Use own domain (named tunnel)" `QCheckBox` — enabled only when named tunnel is detected
  (i.e., `cloudflared service` is running); shows current `share_url` base
- "Create Share Link" `QPushButton` — calls `POST /api/share/create` via `_ApiWorker`
- On success: URL in read-only `QLineEdit` + "Copy" `QPushButton`
  (`QGuiApplication.clipboard().setText(url)`)
- "Stop Sharing" `QPushButton` → `DELETE /api/share/<token>` via `_ApiWorker`
- `QListWidget` showing audio filenames with human-readable sizes

### Context menu addition in `_on_coll_context` (line ~1651)

After the existing "Open Folder" action:

```python
if len(rows) == 1 and rows[0].get("disk_path") and Path(rows[0]["disk_path"]).is_dir():
    share_act = QAction(self.tr("Share Folder…"), self)
    share_act.triggered.connect(lambda: self._on_share_folder(rows[0]))
    menu.addAction(share_act)
```

### Button in `torrent_row` layout (line ~609)

Add alongside the torrent/qBittorrent/forum buttons (all are "distribution" actions):

```python
self.share_btn = QPushButton(self.tr("Share Folder"))
self.share_btn.clicked.connect(self._on_share_folder_from_btn)
torrent_row.addWidget(self.share_btn)
```

---

## Tunnel Persistence Across App Restarts

`data/active_share.json` format:

```json
{
  "tunnel_pid": 12345,
  "tunnel_url": "https://xyz.trycloudflare.com",
  "shares": {
    "<token>": {
      "folder_path": "/path/to/LB-00123",
      "files": ["disc1.flac", "disc2.flac"],
      "expires_at": "2026-05-28T14:00:00",
      "lb_number": 123
    }
  }
}
```

On app startup, `sharing.load_persisted_shares()` is called from `create_app()`. It:
1. Reads the file (ignore if missing)
2. Drops expired entries
3. Checks if saved PID is still alive (`is_tunnel_alive()`)
4. If alive: reuses tunnel URL for remaining valid shares
5. If dead: clears tunnel state but keeps any valid shares (they become LAN-only until
   user explicitly re-enables the tunnel from the Share dialog)

---

## Cloudflared Binary Detection

```python
import shutil

def cloudflared_available() -> bool:
    return shutil.which("cloudflared") is not None

def named_tunnel_running() -> bool:
    """True if cloudflared is installed as a systemd service and currently active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "cloudflared"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False
```

The Setup tab (or Share dialog) shows:
- "cloudflared not found — install from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" if unavailable
- "Quick tunnel (random URL)" if available but no named tunnel
- "Named tunnel active — share.yourdomain.com" if systemd service running

---

## HTML File Listing Page

Stored as a module-level string constant in `backend/sharing.py`. Self-contained — no CDN, no
external assets. Key elements:

- Table: filename, size (human-readable), individual download link
- "Download All as ZIP" button at top
- Expiry countdown (JS `setInterval` against `expires_at` ISO timestamp)
- Shows "This share has expired" if token is no longer valid (route returns 404)
- Basic dark-friendly CSS, readable on mobile

---

## `requirements.txt`

No new packages required. `cloudflared` is an external binary, not a Python package. All
streaming uses stdlib (`zipfile`, `io`, `queue`, `threading`, `subprocess`).

---

## Verification

1. `python -m py_compile backend/sharing.py backend/app.py gui/collection_tab.py`
2. Start app → My Collection tab → right-click a row with valid `disk_path` → "Share Folder…"
   appears and opens the dialog
3. Create share without tunnel (LAN mode) → copy URL → open in browser → file listing renders,
   individual file downloads work with partial-content resume (`curl -r 0-1023 <url>`)
4. Download ZIP → `python -m zipfile -t <file.zip>` passes
5. With `cloudflared` installed: create share with "Share over internet" checked → public URL
   appears → open in incognito browser → file listing and downloads work
6. Let share expire (reduce TTL to 1 min for testing) → URL returns 404
7. Restart app while share is active → share survives if TTL not yet elapsed
8. Click "Stop Sharing" → tunnel stops, share URL returns 404
