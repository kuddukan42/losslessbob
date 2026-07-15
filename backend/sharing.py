"""File-sharing module: ephemeral token-based share state, streaming, and Cloudflare Tunnel."""

import io
import json
import logging
import os
import queue
import secrets
import shutil
import subprocess
import threading
import time
import zipfile
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

SHARE_STATE_FILE = Path("data/active_share.json")
AUDIO_EXTENSIONS = {".flac", ".shn", ".ape", ".wav", ".mp3", ".ogg", ".m4a", ".wv"}
DEFAULT_TTL_HOURS = 24
_REAPER_INTERVAL = 300  # seconds

_active_shares: dict[str, dict] = {}
_shares_lock = threading.Lock()
_tunnel_pid: int | None = None
_tunnel_url: str | None = None


# ── Persistence ───────────────────────────────────────────────────────────────

def _persist() -> None:
    """Write current share + tunnel state to disk (must be called under _shares_lock)."""
    payload: dict = {
        "tunnel_pid": _tunnel_pid,
        "tunnel_url": _tunnel_url,
        "shares": {},
    }
    for token, share in _active_shares.items():
        payload["shares"][token] = {
            "folder_path": share["folder_path"],
            "files": share["files"],
            "expires_at": share["expires_at"],
            "lb_number": share.get("lb_number"),
        }
    try:
        SHARE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHARE_STATE_FILE.write_text(json.dumps(payload, indent=2))
    except OSError as exc:
        logger.warning("sharing: failed to persist state: %s", exc)


def load_persisted_shares() -> None:
    """Re-load share state from disk on app startup; drop expired entries."""
    global _tunnel_pid, _tunnel_url
    if not SHARE_STATE_FILE.exists():
        return
    try:
        payload = json.loads(SHARE_STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("sharing: could not read state file: %s", exc)
        return

    now = datetime.now(UTC)
    with _shares_lock:
        _tunnel_pid = payload.get("tunnel_pid")
        _tunnel_url = payload.get("tunnel_url")

        if _tunnel_pid and not is_tunnel_alive():
            logger.info("sharing: saved tunnel PID %s is dead; clearing tunnel state", _tunnel_pid)
            _tunnel_pid = None
            _tunnel_url = None

        for token, share in payload.get("shares", {}).items():
            try:
                exp = datetime.fromisoformat(share["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=UTC)
                if exp <= now:
                    continue
                _active_shares[token] = {
                    "folder_path": share["folder_path"],
                    "files": share["files"],
                    "expires_at": share["expires_at"],
                    "lb_number": share.get("lb_number"),
                    "tunnel_url": _tunnel_url,
                }
            except (KeyError, ValueError):
                continue

        logger.info("sharing: loaded %d active share(s) from disk", len(_active_shares))


# ── Share CRUD ────────────────────────────────────────────────────────────────

def create_share(folder_path: str, ttl_hours: int = DEFAULT_TTL_HOURS,
                 lb_number: int | None = None) -> dict:
    """Create a new share for the given folder path.

    Args:
        folder_path: Absolute path to the folder to share.
        ttl_hours: How long the share should remain valid.
        lb_number: LB number for display purposes.

    Returns:
        Share dict with token, files, expires_at, tunnel_url.
    """
    path = Path(folder_path)
    files = sorted(
        f.name for f in path.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )
    token = secrets.token_urlsafe(16)
    expires_at = (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat()
    share = {
        "folder_path": folder_path,
        "files": files,
        "expires_at": expires_at,
        "lb_number": lb_number,
        "tunnel_url": _tunnel_url,
    }
    with _shares_lock:
        _active_shares[token] = share
        _persist()
    logger.info("sharing: created share %s (%d files, TTL %dh)", token[:8], len(files), ttl_hours)
    return {"token": token, **share}


def get_share(token: str) -> dict | None:
    """Return the share dict if the token is valid and not expired, else None."""
    with _shares_lock:
        share = _active_shares.get(token)
    if share is None:
        return None
    exp = datetime.fromisoformat(share["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp <= datetime.now(UTC):
        revoke_share(token)
        return None
    return share


def revoke_share(token: str) -> None:
    """Remove a share and persist state. Stops tunnel if no shares remain."""
    with _shares_lock:
        _active_shares.pop(token, None)
        _persist()
        remaining = len(_active_shares)
    logger.info("sharing: revoked share %s; %d remaining", token[:8], remaining)
    if remaining == 0:
        stop_cloudflare_tunnel()


def list_shares() -> list[dict]:
    """Return all active (non-expired) shares for GUI status display."""
    now = datetime.now(UTC)
    result = []
    expired = []
    with _shares_lock:
        for token, share in list(_active_shares.items()):
            exp = datetime.fromisoformat(share["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp > now:
                result.append({"token": token, **share})
            else:
                expired.append(token)
    # Revoke outside the lock — revoke_share persists state and stops the
    # tunnel when the last share is gone, which a bare pop() would skip.
    for token in expired:
        revoke_share(token)
    return result


# ── Streaming ─────────────────────────────────────────────────────────────────

def stream_file(folder_path: str, filename: str) -> Generator[bytes, None, None]:
    """Yield 1 MB chunks of a single audio file. Rejects path-traversal attempts.

    Args:
        folder_path: Base directory of the share.
        filename: Bare filename (no path components).

    Yields:
        1 MB byte chunks.
    """
    if Path(filename).name != filename:
        raise ValueError("path traversal rejected")
    full = Path(folder_path) / filename
    with full.open("rb") as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            yield chunk


def stream_zip(folder_path: str, files: list[str]) -> Generator[bytes, None, None]:
    """Stream a ZIP archive of the share files without buffering the whole archive in memory.

    Uses a producer thread writing into a queue-backed writer; the generator
    dequeues and yields chunks so memory usage stays bounded.

    Args:
        folder_path: Base directory of the share.
        files: List of bare filenames to include.

    Yields:
        Raw ZIP byte chunks.
    """
    buf_queue: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()

    class _QueueWriter(io.RawIOBase):
        def write(self, b: bytes | bytearray) -> int:
            buf_queue.put(bytes(b))
            return len(b)

    def _zip_thread() -> None:
        try:
            writer = _QueueWriter()
            with zipfile.ZipFile(writer, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                for fname in files:
                    zf.write(Path(folder_path) / fname, arcname=fname)
        finally:
            buf_queue.put(None)

    threading.Thread(target=_zip_thread, daemon=True).start()
    while True:
        chunk = buf_queue.get()
        if chunk is None:
            break
        yield chunk


# ── Cloudflare Tunnel ─────────────────────────────────────────────────────────

def cloudflared_available() -> bool:
    """Return True if the cloudflared binary is on PATH."""
    return shutil.which("cloudflared") is not None


def named_tunnel_running() -> bool:
    """Return True if cloudflared is installed as a systemd service and active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "cloudflared"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def is_tunnel_alive() -> bool:
    """Return True if the saved tunnel PID is still running."""
    if _tunnel_pid is None:
        return False
    try:
        os.kill(_tunnel_pid, 0)
        return True
    except OSError:
        return False


def start_cloudflare_tunnel(port: int = 5174) -> str | None:
    """Launch a quick Cloudflare Tunnel and return the public URL.

    Parses cloudflared stdout for the assigned trycloudflare.com URL. Saves
    the PID to state so the tunnel survives across GUI restarts within a session.

    Args:
        port: Local Flask port to expose.

    Returns:
        Public HTTPS URL string, or None if cloudflared is not available.
    """
    global _tunnel_pid, _tunnel_url
    if not cloudflared_available():
        logger.warning("sharing: cloudflared not found on PATH")
        return None
    if is_tunnel_alive():
        logger.info("sharing: tunnel already alive (PID %s)", _tunnel_pid)
        return _tunnel_url

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    url: str | None = None
    deadline = time.monotonic() + 15
    for line in proc.stdout:  # type: ignore[union-attr]
        if time.monotonic() > deadline:
            break
        line = line.strip()
        if "trycloudflare.com" in line or "https://" in line:
            for part in line.split():
                if part.startswith("https://"):
                    url = part
                    break
        if url:
            break

    if url:
        with _shares_lock:
            _tunnel_pid = proc.pid
            _tunnel_url = url
            for share in _active_shares.values():
                share["tunnel_url"] = url
            _persist()
        logger.info("sharing: tunnel started PID=%s url=%s", proc.pid, url)
    else:
        logger.warning("sharing: could not parse tunnel URL from cloudflared output")

    return url


def stop_cloudflare_tunnel() -> None:
    """Send SIGTERM to the saved tunnel process."""
    global _tunnel_pid, _tunnel_url
    if _tunnel_pid is None:
        return
    try:
        os.kill(_tunnel_pid, 15)
        logger.info("sharing: sent SIGTERM to tunnel PID %s", _tunnel_pid)
    except OSError:
        pass
    with _shares_lock:
        _tunnel_pid = None
        _tunnel_url = None
        _persist()


# ── Expiry reaper ─────────────────────────────────────────────────────────────

def _reaper_loop() -> None:
    while True:
        time.sleep(_REAPER_INTERVAL)
        # The loop body must never raise: this thread is started once at import
        # and has no restart path, so an uncaught exception (e.g. a corrupt
        # expires_at) would silently disable share expiry for the whole session.
        try:
            now = datetime.now(UTC)
            expired = []
            with _shares_lock:
                for token, share in list(_active_shares.items()):
                    try:
                        exp = datetime.fromisoformat(share["expires_at"])
                    except (KeyError, TypeError, ValueError):
                        logger.warning("sharing: share %s has invalid expires_at; reaping it",
                                    token[:8])
                        expired.append(token)
                        continue
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    if exp <= now:
                        expired.append(token)
            for token in expired:
                revoke_share(token)
            if expired:
                logger.info("sharing: reaped %d expired share(s)", len(expired))
        except Exception:
            logger.exception("sharing: reaper iteration failed; retrying next interval")


threading.Thread(target=_reaper_loop, name="share-reaper", daemon=True).start()


# ── HTML file listing page ────────────────────────────────────────────────────

_LISTING_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LosslessBob Share</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#111;color:#ddd;padding:24px}
h1{font-size:1.2rem;margin-bottom:4px;color:#fff}
.meta{font-size:.82rem;color:#888;margin-bottom:20px}
.expired{color:#f87171;font-weight:600}
.dl-all{display:inline-block;margin-bottom:18px;padding:8px 18px;background:#3b82f6;
  color:#fff;border-radius:6px;text-decoration:none;font-weight:600;font-size:.9rem}
.dl-all:hover{background:#2563eb}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:8px 12px;color:#888;border-bottom:1px solid #333;
  font-size:.75rem;text-transform:uppercase;letter-spacing:.06em}
td{padding:8px 12px;border-bottom:1px solid #222;vertical-align:middle}
td.sz{color:#888;text-align:right;font-variant-numeric:tabular-nums}
a.dl{color:#60a5fa;text-decoration:none}
a.dl:hover{text-decoration:underline}
</style>
</head>
<body>
<h1>LosslessBob Share — LB-{lb_number}</h1>
<div class="meta">
  Expires: <span id="exp"></span>
  &nbsp;·&nbsp; {file_count} files
</div>
<a class="dl-all" href="zip">⬇ Download All as ZIP</a>
<table>
<thead><tr><th>File</th><th style="text-align:right">Size</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
<script>
const exp=new Date("{expires_at}");
function fmt(){{
  const s=Math.floor((exp-Date.now())/1000);
  if(s<=0){{document.getElementById('exp').textContent='Expired';
    document.getElementById('exp').className='expired';return;}}
  const h=Math.floor(s/3600),m=Math.floor((s%3600)/60);
  document.getElementById('exp').textContent=h+'h '+m+'m';
}}
fmt();setInterval(fmt,60000);
</script>
</body>
</html>"""


def render_listing(token: str, share: dict, base_url: str) -> str:
    """Render the self-contained HTML file listing for a share.

    Args:
        token: Share token.
        share: Share dict from _active_shares.
        base_url: Absolute URL prefix for this share (no trailing slash).

    Returns:
        HTML string.
    """
    folder = Path(share["folder_path"])
    lb = share.get("lb_number") or "?????"

    def _human(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
            n //= 1024
        return f"{n:.1f} TB"

    rows = []
    for fname in share["files"]:
        fpath = folder / fname
        try:
            sz = _human(fpath.stat().st_size)
        except OSError:
            sz = "?"
        row = (
            f'<tr><td><a class="dl" href="file/{fname}">{fname}</a></td>'
            f'<td class="sz">{sz}</td></tr>'
        )
        rows.append(row)

    return _LISTING_HTML.format(
        lb_number=lb,
        file_count=len(share["files"]),
        expires_at=share["expires_at"],
        rows="\n".join(rows),
    )
