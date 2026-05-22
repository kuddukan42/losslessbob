#!/usr/bin/env python3
"""
LosslessBob interactive shell.

Interactive mode (default — run with no arguments):
  .venv/bin/python cli.py

One-shot mode (backward-compatible):
  .venv/bin/python cli.py <command> [args...]

Commands:
  lookup <file_or_glob> [--json]
  search <query> [--field all|location|date|description] [--json]
  stats [--json]
  import <path_to_flat_file>
  serve [--port 5174]
  daemon start|stop|status
  scrape start [--start-lb N] [--end-lb N] [--force] [--watch]
  scrape stop
  scrape status [--json]
  crawler start [--scope incremental|full] [--force] [--delay-ms N] [--daily-cap N] [--watch]
  crawler stop
  crawler status [--json]
  fingerprint build [--force] [--watch]
  fingerprint stop
  fingerprint status [--json]
  fingerprint identify <file> [--json]
  fingerprint stats [--json]
  fingerprint scan-dupes [--watch]
  fingerprint dupes [--json]
"""
import argparse
import json
import shlex
import shutil
import sys
import textwrap
import time
import threading
from pathlib import Path

# ── Version ───────────────────────────────────────────────────────────────────

_VERSION = "1.0.2"
_HISTORY_FILE = Path.home() / ".losslessbob_history"


def _term_width() -> int:
    """Return the current terminal column count, with an 80-column fallback."""
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def _parse_lb(raw: str) -> int:
    """Accept '123', '00123', or 'LB-00123' and return an int."""
    s = str(raw).strip().upper()
    if s.startswith("LB-"):
        s = s[3:]
    return int(s)


_LB_URL      = "http://www.losslessbob.wonderingwhattochoose.com/detail/LB-{:05d}.html"
_TYPE_LABELS = {"f": "ffp", "s": "st5", "m": "md5"}


# ── Flask helpers ─────────────────────────────────────────────────────────────


def _start_flask(port: int) -> None:
    from backend.app import create_app
    from backend.paths import ensure_data_dirs
    ensure_data_dirs()
    flask_app = create_app()
    if sys.platform == "win32":
        try:
            from waitress import serve as _serve
            _serve(flask_app, host="127.0.0.1", port=port, threads=4)
        except ImportError:
            flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    else:
        flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def _wait_for_flask(port: int, timeout: float = 15.0) -> None:
    """Block until Flask is accepting connections or timeout expires."""
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)


def _is_flask_running(port: int) -> bool:
    """Return True if a server is already accepting connections on *port*."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


# ── Daemon helpers ────────────────────────────────────────────────────────────


def _daemon_pid_file() -> Path:
    from backend.paths import DATA_DIR
    return DATA_DIR / "backend.pid"


def _daemon_log_file() -> Path:
    from backend.paths import DATA_DIR
    return DATA_DIR / "backend.log"


def _read_daemon_pid() -> int | None:
    """Return the PID from the PID file if the process is alive, else None."""
    import os
    pid_file = _daemon_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # signal 0 = existence check only
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def _daemon_start(port: int) -> None:
    """Fork run_backend.py as a detached background process with a PID file."""
    import subprocess

    pid = _read_daemon_pid()
    if pid is not None:
        print(f"Backend already running  PID={pid}  port={port}")
        return

    if _is_flask_running(port):
        print(f"Port {port} is already in use (GUI or another process — not daemon-managed)")
        return

    script   = Path(__file__).parent / "run_backend.py"
    log_file = _daemon_log_file()

    with open(log_file, "a") as log:
        proc = subprocess.Popen(
            [sys.executable, str(script), "--port", str(port)],
            stdout=log,
            stderr=log,
            start_new_session=True,  # detach from the terminal session
        )

    _daemon_pid_file().write_text(str(proc.pid))
    _wait_for_flask(port)
    print(f"Backend started  PID={proc.pid}  port={port}")
    print(f"Log: {log_file}")


def _daemon_stop() -> None:
    """Stop the daemon backend by sending SIGTERM to the stored PID."""
    import os
    import signal

    pid_file = _daemon_pid_file()
    pid      = _read_daemon_pid()

    if pid is None:
        if pid_file.exists():
            pid_file.unlink(missing_ok=True)
            print("Stale PID file removed. Backend was not running.")
        else:
            print("Backend is not running.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        print(f"Backend stopped  PID={pid}")
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        print(f"Process {pid} was already gone.")
    except PermissionError:
        print(f"Permission denied stopping PID {pid}.")


def _daemon_status(port: int) -> None:
    """Print the current daemon status."""
    pid     = _read_daemon_pid()
    running = _is_flask_running(port)

    if pid and running:
        print(f"running  PID={pid}  port={port}")
    elif pid and not running:
        print(f"PID {pid} alive but port {port} not responding (still starting?)")
    elif not pid and running:
        print(f"port {port} responding — no PID file (managed by GUI or run_backend.py)")
    else:
        print("not running")


# ── Status formatters ─────────────────────────────────────────────────────────


def _fmt_scrape_status(s: dict) -> str:
    running = "running" if s.get("running") else "idle"
    pct     = f"{s['done']}/{s['total']}" if s.get("total") else "0/0"
    if _term_width() < 50:
        lb = f" LB-{s['current_lb']:05d}" if s.get("current_lb") else ""
        return f"{running}  {pct}{lb}"
    lb      = f"  current=LB-{s['current_lb']:05d}" if s.get("current_lb") else ""
    errs    = f"  errors={s['errors']}" if s.get("errors") else ""
    skipped = f"  skipped={s['skipped']}" if s.get("skipped") else ""
    action  = f"  [{s['last_action']}]" if s.get("last_action") else ""
    return f"{running}  {pct}{lb}{errs}{skipped}{action}"


def _print_scrape_status(s: dict) -> None:
    """Print scrape status — tabular block on narrow, single line on wide."""
    w = _term_width()
    if w < 50:
        print(_hr("scraper"))
        running = "running" if s.get("running") else "idle"
        print(f"  {'Status':<10} {running}")
        if s.get("current_lb"):
            print(f"  {'LB':<10} LB-{s['current_lb']:05d}")
        if s.get("total"):
            print(f"  {'Progress':<10} {s['done']} / {s['total']}")
        if s.get("errors"):
            print(f"  {'Errors':<10} {s['errors']}")
        if s.get("skipped"):
            print(f"  {'Skipped':<10} {s['skipped']}")
        if s.get("last_action"):
            print(f"  {'Action':<10} {s['last_action'][:w - 13]}")
    else:
        print(_fmt_scrape_status(s))


# ── Crawler tail log ──────────────────────────────────────────────────────────


def _short_path(url: str, width: int) -> str:
    """Return just the URL path, truncated with a leading ellipsis if needed."""
    from urllib.parse import urlparse
    path = urlparse(url).path if url else ""
    if not path:
        return (url or "")[:width]
    if len(path) > width:
        path = "…" + path[-(width - 1):]
    return path


def _counts(s: dict) -> str:
    ok  = s.get("fetched", 0)
    nm  = s.get("not_modified", 0)
    nf  = s.get("not_found", 0)
    err = s.get("failed", 0)
    q   = s.get("queue_size", 0)
    if _term_width() < 50:
        parts = [f"↓{ok}", f"Q:{q}"]
        if err:
            parts.append(f"err:{err}")
        return "  ".join(parts)
    return f"ok:{ok} 304:{nm} 404:{nf} err:{err} Q:{q}"


def _hr(label: str = "") -> str:
    inner = f" {label} " if label else ""
    pad   = max(0, _term_width() - len(inner) - 2)
    return f"──{inner}{'─' * pad}"


def _watch_scrape(base_url: str) -> None:
    """Poll /api/scrape/status until the scrape finishes."""
    import requests
    try:
        while True:
            s     = requests.get(f"{base_url}/api/scrape/status", timeout=5).json()
            w     = _term_width()
            done  = s.get("done", 0)
            total = s.get("total", 0) or 1
            lb    = s.get("current_lb")
            if w < 50:
                lb_str   = f" LB-{lb:05d}" if lb else ""
                prog_str = f" {done}/{total}{lb_str}"
                bar_w    = max(3, w - len(prog_str) - 2)
                filled   = round(bar_w * done / total)
                bar      = "█" * filled + "░" * (bar_w - filled)
                line     = f"[{bar}]{prog_str}"
            else:
                line = _fmt_scrape_status(s)
            print(f"\r{line[:w]}", end="", flush=True)
            if not s.get("running"):
                print()
                break
            time.sleep(2)
    except KeyboardInterrupt:
        print()


def _watch_crawler(base_url: str) -> None:
    """Stream crawler progress as a tail log adapted to the current terminal width."""
    import requests

    last_url     = None
    last_stage   = None
    last_fetched = 0
    last_nm      = 0

    def _ts() -> str:
        return time.strftime("%H:%M:%S")

    try:
        while True:
            try:
                s = requests.get(f"{base_url}/api/crawler/status", timeout=5).json()
            except Exception:
                time.sleep(2)
                continue

            w       = _term_width()
            url_w   = max(15, w - 11)   # 11 = "HH:MM:SS ↓ "
            stage   = s.get("stage", "idle")
            url     = s.get("current_url") or ""
            running = s.get("running", False)
            msg     = s.get("message", "")
            fetched = s.get("fetched", 0)
            nm      = s.get("not_modified", 0)

            if stage != last_stage:
                print(_hr(stage.upper()))
                last_stage = stage

            if url and url != last_url:
                d_fetch = fetched - last_fetched
                d_nm    = nm - last_nm
                arrow   = "↺" if d_nm > d_fetch else "↓"
                if w < 50:
                    ts     = time.strftime("%H:%M")
                    q_str  = f"  Q:{s.get('queue_size', 0)}"
                    prefix = f"{ts} {arrow} "
                    u_w    = max(8, w - len(prefix) - len(q_str))
                    print(f"{prefix}{_short_path(url, u_w)}{q_str}")
                else:
                    print(f"{_ts()} {arrow} {_short_path(url, url_w)}")
                    print(f"  {_counts(s)}")
                last_url     = url
                last_fetched = fetched
                last_nm      = nm

            if not running and stage not in ("idle", ""):
                print(_hr("DONE"))
                print(f"  {_counts(s)}")
                if msg:
                    body_w = max(20, w - 2)
                    for chunk in (msg[i:i + body_w] for i in range(0, len(msg), body_w)):
                        print(f"  {chunk}")
                break

            time.sleep(2)
    except KeyboardInterrupt:
        print()


# ── Argument parser ───────────────────────────────────────────────────────────


class _SilentParser(argparse.ArgumentParser):
    """ArgumentParser that raises UsageError instead of calling sys.exit."""

    def error(self, message: str) -> None:
        raise _UsageError(message)


class _UsageError(Exception):
    pass


def _build_parser(klass=argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Build and return the full argument parser."""
    parser = klass(prog="losslessbob", add_help=True)
    parser.add_argument("--port", type=int, default=5174)
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    sub = parser.add_subparsers(dest="command")

    p_lookup = sub.add_parser("lookup", help="Lookup checksums from file(s)")
    p_lookup.add_argument("paths", nargs="+")

    p_search = sub.add_parser("search", help="Search the database")
    p_search.add_argument("query")
    p_search.add_argument("--field", default="all",
                          choices=["all", "location", "date", "description"])

    sub.add_parser("stats", help="Show database statistics")

    p_import = sub.add_parser("import", help="Import a flat checksum file")
    p_import.add_argument("path")

    sub.add_parser("serve", help="Start Flask server (foreground)")

    p_daemon = sub.add_parser("daemon", help="Manage the persistent background backend")
    daemon_sub = p_daemon.add_subparsers(dest="daemon_action", required=True)
    daemon_sub.add_parser("start", help="Start backend as a detached background process")
    daemon_sub.add_parser("stop",  help="Stop the background backend")
    daemon_sub.add_parser("status", help="Show whether the background backend is running")

    p_scrape = sub.add_parser("scrape", help="Entry-metadata scraper")
    scrape_sub = p_scrape.add_subparsers(dest="scrape_action", required=True)

    p_scrape_start = scrape_sub.add_parser("start")
    p_scrape_start.add_argument("--start-lb", type=int, default=None)
    p_scrape_start.add_argument("--end-lb", type=int, default=None)
    p_scrape_start.add_argument("--force", action="store_true")
    p_scrape_start.add_argument("--watch", action="store_true")
    scrape_sub.add_parser("stop")
    scrape_sub.add_parser("status")

    p_crawler = sub.add_parser("crawler", help="Full-domain site crawler")
    crawler_sub = p_crawler.add_subparsers(dest="crawler_action", required=True)

    p_crawler_start = crawler_sub.add_parser("start")
    p_crawler_start.add_argument("--scope", default="incremental",
                                 choices=["incremental", "full"])
    p_crawler_start.add_argument("--force", action="store_true")
    p_crawler_start.add_argument("--delay-ms", type=int, default=1500)
    p_crawler_start.add_argument("--daily-cap", type=int, default=99999)
    p_crawler_start.add_argument("--watch", action="store_true")
    crawler_sub.add_parser("stop")
    crawler_sub.add_parser("status")

    p_fp = sub.add_parser("fingerprint", help="Acoustic fingerprint database")
    fp_sub = p_fp.add_subparsers(dest="fp_action", required=True)

    p_fp_build = fp_sub.add_parser("build", help="Start building the fingerprint DB")
    p_fp_build.add_argument("--force", action="store_true",
                            help="Re-fingerprint files already in the DB")
    p_fp_build.add_argument("--watch", action="store_true",
                            help="Stream progress until the build finishes")

    fp_sub.add_parser("stop",   help="Stop a running fingerprint build")
    fp_sub.add_parser("status", help="Show fingerprint build progress")

    p_fp_identify = fp_sub.add_parser("identify",
                                       help="Identify an audio file against the fingerprint DB")
    p_fp_identify.add_argument("path", metavar="FILE")

    fp_sub.add_parser("stats", help="Show fingerprint DB statistics")

    p_fp_scan = fp_sub.add_parser("scan-dupes",
                                   help="Scan for duplicate recordings")
    p_fp_scan.add_argument("--watch", action="store_true",
                           help="Wait and show results when the scan finishes")

    fp_sub.add_parser("dupes", help="Show duplicate-scan results")

    p_show = sub.add_parser("show", help="Show full details for one entry")
    p_show.add_argument("lb", type=_parse_lb, metavar="LB")

    p_open = sub.add_parser("open", help="Open entry page in the default browser")
    p_open.add_argument("lb", type=_parse_lb, metavar="LB")

    p_diff = sub.add_parser("diff", help="Diff checksum file(s) against the database")
    p_diff.add_argument("paths", nargs="+")

    p_verify = sub.add_parser("verify",
                               help="Verify local audio files against on-disk checksum files")
    p_verify.add_argument("dirs", nargs="+")

    p_missing = sub.add_parser("missing", help="List entries missing checksums or metadata")
    p_missing.add_argument("--field", default="checksums",
                           choices=["checksums", "metadata"])

    p_export = sub.add_parser("export", help="Export entries to CSV, JSON, or plain text")
    p_export.add_argument("--format", dest="fmt", default="csv",
                          choices=["csv", "json", "txt"])
    p_export.add_argument("--out", default=None, metavar="FILE")

    p_backup = sub.add_parser("backup", help="Create a timestamped database backup")
    p_backup.add_argument("dest", nargs="?", default=None, metavar="DEST")

    p_recent = sub.add_parser("recent", help="Show recently scraped entries")
    p_recent.add_argument("n", nargs="?", type=int, default=10, metavar="N")

    return parser


# ── Fingerprint helpers ───────────────────────────────────────────────────────


def _watch_fp_build(base_url: str) -> None:
    """Poll fingerprint build status until the build finishes."""
    import requests
    try:
        while True:
            s      = requests.get(f"{base_url}/api/fingerprint/build/status", timeout=5).json()
            w      = _term_width()
            done   = s.get("done", 0)
            total  = s.get("total", 0) or 1
            status = s.get("status", "")
            cur    = s.get("current", "")
            errs   = len(s.get("errors", []))
            pct    = done / total
            if w < 50:
                bar_w  = max(3, w - len(str(done)) - len(str(total)) - 4)
                filled = round(bar_w * pct)
                bar    = "█" * filled + "░" * (bar_w - filled)
                line   = f"[{bar}] {done}/{total}"
            else:
                err_s  = f"  errors={errs}" if errs else ""
                cur_w  = max(10, w - 22 - len(err_s))
                line   = f"{done}/{total}{err_s}  {cur[:cur_w]}"
            print(f"\r{line[:w]}", end="", flush=True)
            if status != "running":
                print()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print()


def _watch_fp_dupes(base_url: str) -> None:
    """Poll until the duplicate scan finishes."""
    import requests
    try:
        while True:
            s = requests.get(f"{base_url}/api/fingerprint/duplicates", timeout=5).json()
            if s.get("status") != "running":
                break
            msg = s.get("message", "scanning…")
            w   = _term_width()
            print(f"\r{msg[:w]}", end="", flush=True)
            time.sleep(2)
        print()
    except KeyboardInterrupt:
        print()


def _print_fp_status(s: dict) -> None:
    """Print fingerprint build status."""
    w       = _term_width()
    status  = s.get("status", "idle")
    done    = s.get("done", 0)
    total   = s.get("total", 0)
    skipped = s.get("skipped", 0)
    errs    = s.get("errors", [])
    cur     = s.get("current", "")
    if w < 50:
        print(_hr("fingerprint"))
        print(f"  {'Status':<10} {status}")
        if total:
            print(f"  {'Progress':<10} {done} / {total}")
        if skipped:
            print(f"  {'Skipped':<10} {skipped}")
        if errs:
            print(f"  {'Errors':<10} {len(errs)}")
        if cur:
            print(f"  {'Current':<10} {cur[:w - 13]}")
    else:
        pct_str = f"  {done}/{total}" if total else "  0/0"
        skip_s  = f"  skipped={skipped}" if skipped else ""
        err_s   = f"  errors={len(errs)}" if errs else ""
        cur_s   = f"  [{cur}]" if cur else ""
        print(f"{status}{pct_str}{skip_s}{err_s}{cur_s}")


def _print_fp_identify(results: list) -> None:
    """Print identify results ranked by score."""
    w = _term_width()
    if not results:
        print("No match found in fingerprint database.")
        return
    for i, r in enumerate(results, 1):
        conf  = "  CONFIDENT" if r.get("confident") else ""
        lb    = r.get("lb_number", "?")
        score = r.get("score", 0)
        fp    = r.get("file_path", "")
        if w < 50:
            fp_w = max(8, w - 14)
            print(f"#{i} LB-{lb:05d}  s={score}{conf}")
            print(f"   {fp[:fp_w]}")
        else:
            fp_w = max(15, w - 30)
            print(f"#{i}  LB-{lb:05d}  score={score:4d}{conf}")
            print(f"     {fp[:fp_w]}")


def _print_fp_dupes(s: dict) -> None:
    """Print duplicate-scan results."""
    w       = _term_width()
    status  = s.get("status", "idle")
    message = s.get("message", "")
    results = s.get("results", [])
    if status == "idle":
        print("No duplicate scan has been run.  Use 'fingerprint scan-dupes' to start.")
        return
    if status == "running":
        print(f"Scan in progress…  {message}")
        return
    if message and w >= 50:
        print(message)
    if not results:
        print("No duplicate recordings found.")
        return
    fn_w = max(15, w - 4)
    for r in results:
        lb_a  = r.get("lb_a", "?")
        lb_b  = r.get("lb_b", "?")
        score = r.get("score", 0)
        conf  = "  CONFIDENT" if r.get("confident") else ""
        fa    = r.get("file_a", "")
        fb    = r.get("file_b", "")
        if w < 50:
            print(f"LB-{lb_a:05d} ~ LB-{lb_b:05d}  s={score}{conf}")
            print(f"  {fa[:fn_w]}")
            print(f"  {fb[:fn_w]}")
        else:
            print(f"LB-{lb_a:05d}  ↔  LB-{lb_b:05d}  score={score}{conf}")
            print(f"  a: {fa[:fn_w]}")
            print(f"  b: {fb[:fn_w]}")


# ── Command dispatch ──────────────────────────────────────────────────────────


def _execute(args: argparse.Namespace, base_url: str) -> None:
    """Dispatch a parsed args namespace to the appropriate handler."""
    import requests

    if args.command == "serve":
        port = int(base_url.rsplit(":", 1)[-1])
        _start_flask(port)
        return

    if args.command == "daemon":
        port = int(base_url.rsplit(":", 1)[-1])
        if args.daemon_action == "start":
            _daemon_start(port)
        elif args.daemon_action == "stop":
            _daemon_stop()
        elif args.daemon_action == "status":
            _daemon_status(port)
        return

    if args.command == "stats":
        r = requests.get(f"{base_url}/api/db/stats").json()
        w = _term_width()
        if args.json:
            print(json.dumps(r, indent=2))
        elif w < 50:
            print(_hr("stats"))
            print(f"  {'Entries':<11}{r['total_lb_numbers']:,}")
            print(f"  {'Checksums':<11}{r['total_checksums']:,}")
            print(f"  {'Latest LB':<11}{r['latest_lb']}")
            print(f"  {'Imported':<11}{r['last_import']}")
        elif w < 72:
            print(f"LB entries:  {r['total_lb_numbers']}\n"
                  f"Checksums:   {r['total_checksums']}\n"
                  f"Latest LB:   {r['latest_lb']}\n"
                  f"Last import: {r['last_import']}")
        else:
            print(f"LB entries: {r['total_lb_numbers']}  "
                  f"Checksums: {r['total_checksums']}  "
                  f"Latest LB: {r['latest_lb']}  "
                  f"Last import: {r['last_import']}")

    elif args.command == "lookup":
        text_parts = []
        for pattern in args.paths:
            for p in Path(".").glob(pattern) if "*" in pattern else [Path(pattern)]:
                if p.is_file():
                    text_parts.append(p.read_text(errors="replace"))
        text = "\n".join(text_parts)
        r = requests.post(f"{base_url}/api/lookup", json={"text": text}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            w = _term_width()
            for lb in r.get("summary", {}).get("lb_summary", []):
                m    = lb['matched']
                miss = lb['missing_from_set']
                if w >= 70:
                    print(f"LB-{lb['lb_number']:05d}  {lb['status']:25s}  "
                          f"matched={m}  missing={miss}")
                elif w < 50:
                    # single-line tabular: LB  m:N  ?:N  status
                    st_w = max(5, w - 18 - len(str(m)) - len(str(miss)))
                    print(f"LB-{lb['lb_number']:05d}  m:{m}  ?:{miss}  "
                          f"{lb['status'][:st_w]}")
                else:
                    print(f"LB-{lb['lb_number']:05d}  {lb['status']}")
                    print(f"  matched={m}  missing={miss}")

    elif args.command == "search":
        r = requests.get(f"{base_url}/api/search",
                         params={"q": args.query, "field": args.field}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            w     = _term_width()
            loc_w = max(1, w - 22)  # 22 = "LB-NNNNN  YYYY-MM-DD  "
            for e in r:
                date = (e.get('date_str', '') or '')[:10]
                loc  = (e.get('location', '') or '')[:loc_w]
                if w < 50:
                    print(f"LB-{e['lb_number']:05d}  {date:<10}  {loc}")
                else:
                    print(f"LB-{e['lb_number']:05d}  {date:<12}  {loc}")

    elif args.command == "import":
        r = requests.post(f"{base_url}/api/db/import",
                          json={"file_path": str(Path(args.path).resolve())}).json()
        print(json.dumps(r, indent=2) if args.json else str(r))

    elif args.command == "scrape":
        if args.scrape_action == "start":
            body: dict = {"force": args.force}
            if args.start_lb is not None:
                body["start_lb"] = args.start_lb
            if args.end_lb is not None:
                body["end_lb"] = args.end_lb
            r = requests.post(f"{base_url}/api/scrape/start", json=body).json()
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                if r.get("ok"):
                    total = r.get('total', '?')
                    if _term_width() < 50:
                        print(f"Scrape started\n  {total} entries")
                    else:
                        print(f"Scrape started  total={total} entries queued")
                else:
                    print(f"Error: {r.get('error', r)}", file=sys.stderr)
            if args.watch:
                _watch_scrape(base_url)

        elif args.scrape_action == "stop":
            r = requests.post(f"{base_url}/api/scrape/stop").json()
            print(json.dumps(r, indent=2) if args.json else "Stop signal sent.")

        elif args.scrape_action == "status":
            s = requests.get(f"{base_url}/api/scrape/status").json()
            if args.json:
                print(json.dumps(s, indent=2))
            else:
                _print_scrape_status(s)

    elif args.command == "crawler":
        if args.crawler_action == "start":
            body = {
                "scope":     args.scope,
                "force":     args.force,
                "delay_ms":  args.delay_ms,
                "daily_cap": args.daily_cap,
            }
            r = requests.post(f"{base_url}/api/crawler/start", json=body).json()
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                if r.get("ok"):
                    if _term_width() < 50:
                        print(f"Crawler started\n  scope: {args.scope}")
                    else:
                        print(f"Crawler started  scope={args.scope}")
                else:
                    print(f"Error: {r.get('error', r)}", file=sys.stderr)
            if args.watch:
                _watch_crawler(base_url)

        elif args.crawler_action == "stop":
            r = requests.post(f"{base_url}/api/crawler/stop").json()
            print(json.dumps(r, indent=2) if args.json else "Stop signal sent.")

        elif args.crawler_action == "status":
            s = requests.get(f"{base_url}/api/crawler/status").json()
            if args.json:
                print(json.dumps(s, indent=2))
            elif not s.get("running") and s.get("stage", "idle") == "idle":
                if _term_width() < 50:
                    print(_hr("crawler"))
                    print(f"  {'Status':<10} idle")
                    if s.get("fetched"):
                        print(f"  {'Fetched':<10} {s['fetched']}")
                else:
                    print("idle — no crawl running")
            else:
                _watch_crawler(base_url)

    elif args.command == "fingerprint":
        if args.fp_action == "build":
            r = requests.post(f"{base_url}/api/fingerprint/build",
                              json={"force": args.force}).json()
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                if r.get("ok"):
                    total = r.get("total", "?")
                    if _term_width() < 50:
                        print(f"Build started\n  {total} folders")
                    else:
                        print(f"Fingerprint build started  folders={total}")
                else:
                    print(f"Error: {r.get('error', r)}", file=sys.stderr)
            if getattr(args, "watch", False):
                _watch_fp_build(base_url)

        elif args.fp_action == "stop":
            r = requests.post(f"{base_url}/api/fingerprint/build/stop").json()
            print(json.dumps(r, indent=2) if args.json else "Stop signal sent.")

        elif args.fp_action == "status":
            s = requests.get(f"{base_url}/api/fingerprint/build/status").json()
            if args.json:
                print(json.dumps(s, indent=2))
            else:
                _print_fp_status(s)

        elif args.fp_action == "identify":
            p = Path(args.path).resolve()
            r = requests.post(f"{base_url}/api/fingerprint/identify",
                              json={"file_path": str(p)}).json()
            if args.json:
                print(json.dumps(r, indent=2))
            elif isinstance(r, dict) and "error" in r:
                print(f"Error: {r['error']}", file=sys.stderr)
            else:
                _print_fp_identify(r if isinstance(r, list) else [])

        elif args.fp_action == "stats":
            r = requests.get(f"{base_url}/api/fingerprint/stats").json()
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                w      = _term_width()
                tracks = r.get("track_count", 0)
                hashes = r.get("hash_count", 0)
                if w < 50:
                    print(_hr("fingerprint"))
                    print(f"  {'Tracks':<10} {tracks:,}")
                    print(f"  {'Hashes':<10} {hashes:,}")
                else:
                    print(f"tracks={tracks:,}  hashes={hashes:,}")

        elif args.fp_action == "scan-dupes":
            r = requests.post(f"{base_url}/api/fingerprint/duplicates/scan").json()
            if args.json:
                print(json.dumps(r, indent=2))
            else:
                if r.get("ok"):
                    print("Duplicate scan started.")
                else:
                    print(f"Error: {r.get('error', r)}", file=sys.stderr)
            if getattr(args, "watch", False):
                _watch_fp_dupes(base_url)

        elif args.fp_action == "dupes":
            s = requests.get(f"{base_url}/api/fingerprint/duplicates").json()
            if args.json:
                print(json.dumps(s, indent=2))
            else:
                _print_fp_dupes(s)

    elif args.command == "show":
        r = requests.get(f"{base_url}/api/entry/{args.lb}").json()
        if "error" in r:
            print(f"Error: {r['error']}", file=sys.stderr)
        elif args.json:
            print(json.dumps(r, indent=2))
        else:
            _print_show(r)

    elif args.command == "open":
        import webbrowser
        url = _LB_URL.format(args.lb)
        webbrowser.open(url)
        print(f"Opening  {url}")

    elif args.command == "diff":
        text_parts = []
        for pattern in args.paths:
            for p in Path(".").glob(pattern) if "*" in pattern else [Path(pattern)]:
                if p.is_file():
                    text_parts.append(p.read_text(errors="replace"))
        text = "\n".join(text_parts)
        r = requests.post(f"{base_url}/api/lookup", json={"text": text}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            _print_diff(r, base_url=base_url)

    elif args.command == "verify":
        dirs = [str(Path(d).resolve()) for d in args.dirs]
        r = requests.post(f"{base_url}/api/verify", json={"folders": dirs}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            _print_verify(r.get("results", []))

    elif args.command == "missing":
        if args.field == "checksums":
            nums = requests.get(f"{base_url}/api/db/missing_lb_numbers").json()
            if args.json:
                print(json.dumps(nums, indent=2))
            else:
                count = len(nums)
                if not count:
                    print("All LB entries have checksums.")
                else:
                    noun = "entry" if count == 1 else "entries"
                    print(f"{count} LB {noun} with no checksums:")
                    for n in nums:
                        print(f"  LB-{n:05d}")
        else:  # metadata
            rows: list = []
            offset = 0
            while True:
                page = requests.get(
                    f"{base_url}/api/lb_master",
                    params={"status": "missing", "limit": 500, "offset": offset},
                ).json()
                batch = page if isinstance(page, list) else []
                if not batch:
                    break
                rows.extend(batch)
                if len(batch) < 500:
                    break
                offset += len(batch)
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                count = len(rows)
                if not count:
                    print("No entries with missing metadata.")
                else:
                    noun = "entry" if count == 1 else "entries"
                    print(f"{count} LB {noun} with no metadata (404 on losslessbob.com):")
                    for row in rows:
                        lb = row.get("lb_number", "?")
                        print(f"  LB-{lb:05d}")

    elif args.command == "export":
        if args.fmt == "csv":
            out  = args.out or "entries.csv"
            resp = requests.get(f"{base_url}/api/dbedit/table/entries/export")
            Path(out).write_bytes(resp.content)
            print(f"Exported {len(resp.content):,} bytes → {out}")
        else:
            all_rows: list = []
            cols: list     = []
            pg = 0
            while True:
                resp = requests.get(
                    f"{base_url}/api/dbedit/table/entries/rows",
                    params={"page": pg, "limit": 500,
                            "sort_col": "lb_number", "sort_dir": "asc"},
                ).json()
                if not cols:
                    cols = resp.get("columns", [])
                batch = resp.get("rows", [])
                all_rows.extend(batch)
                if len(batch) < 500:
                    break
                pg += 1

            if args.fmt == "json":
                records = [dict(zip(cols, row)) for row in all_rows]
                out_str = json.dumps(records, indent=2)
                if args.out:
                    Path(args.out).write_text(out_str)
                    print(f"Exported {len(records)} entries → {args.out}")
                else:
                    print(out_str)
            else:  # txt
                out = args.out or "entries.txt"
                idx = {c: i for i, c in enumerate(cols)}
                lines = []
                for row in all_rows:
                    lb   = row[idx["lb_number"]] if "lb_number" in idx else "?"
                    date = (row[idx["date_str"]] or "") if "date_str" in idx else ""
                    loc  = (row[idx["location"]] or "") if "location" in idx else ""
                    lines.append(f"LB-{lb:05d}  {str(date):12s}  {str(loc)}")
                Path(out).write_text("\n".join(lines) + "\n")
                print(f"Exported {len(lines)} entries → {out}")

    elif args.command == "backup":
        r = requests.post(f"{base_url}/api/db/backup",
                          json={"reason": "cli manual backup"}).json()
        if args.json:
            print(json.dumps(r, indent=2))
        elif r.get("ok"):
            src  = r.get("path", "?")
            size = r.get("size_bytes", 0)
            if args.dest:
                shutil.copy2(src, args.dest)
                print(f"Backup saved ({size:,} bytes) → {args.dest}")
            else:
                print(f"Backup saved ({size:,} bytes) → {src}")
        else:
            print(f"Error: {r.get('error', r)}", file=sys.stderr)

    elif args.command == "recent":
        n    = min(args.n or 10, 500)
        resp = requests.get(
            f"{base_url}/api/dbedit/table/entries/rows",
            params={"page": 0, "limit": n,
                    "sort_col": "scraped_at", "sort_dir": "desc"},
        ).json()
        if args.json:
            print(json.dumps(resp, indent=2))
        else:
            cols = resp.get("columns", [])
            rows = resp.get("rows", [])
            idx  = {c: i for i, c in enumerate(cols)}
            w     = _term_width()
            loc_w = max(1, w - 22)  # 22 = "LB-NNNNN  YYYY-MM-DD  "
            for row in rows:
                lb   = row[idx["lb_number"]] if "lb_number" in idx else "?"
                date = (str(row[idx["date_str"]] or "") if "date_str" in idx else "")[:10]
                loc  = (str(row[idx["location"]] or "") if "location" in idx else "")[:loc_w]
                if w < 50:
                    print(f"LB-{lb:05d}  {date:<10}  {loc}")
                else:
                    print(f"LB-{lb:05d}  {date:<12}  {loc}")


# ── Interactive shell ─────────────────────────────────────────────────────────

_HELP_TEXT = """\
LosslessBob shell — available commands
───────────────────────────────────────
  stats                         Show database statistics
  search   <query>              Search entries by keyword
  lookup   <file> ...           Match checksums from file(s) against the database
  import   <path>               Import a flat checksum file into the database
  show     <LB>                 Show full concert details for one entry
  open     <LB>                 Open entry page in the default browser
  diff     <file> ...           Diff a checksum file against the database
  verify   <dir> ...            Verify local audio against on-disk checksum files
  missing  [--field ...]        List entries without checksums or metadata
  export   [--format ...] ...   Export entries to CSV, JSON, or plain text
  backup   [<dest>]             Create a timestamped database backup
  recent   [N]                  Show N most recently scraped entries (default: 10)
  scrape   start|stop|status    Manage the entry-metadata scraper
  crawler  start|stop|status    Manage the full-site crawler
  fingerprint build|stop|status|identify|stats|scan-dupes|dupes
                                Acoustic fingerprint database
  serve                         Start the Flask backend in the foreground
  daemon   start|stop|status    Run the backend as a persistent background service

Global flags (append to any command):
  --json                   Print raw JSON instead of formatted output
  --port N                 Override the backend port (default 5174)

Shell meta-commands:
  help [command]           Show help (optionally for a specific command)
  ?                        Same as 'help'
  clear                    Clear the screen
  exit  quit  q  Ctrl-D   Exit the shell

Examples:
  lb> stats
  lb> search Newport 1965
  lb> search "Bob Dylan" --field location --json
  lb> lookup /path/to/checksums.txt
  lb> lookup *.md5
  lb> scrape start --watch
  lb> crawler start --scope full --delay-ms 2000 --watch
  lb> crawler status
"""

_COMMAND_HELP: dict[str, str] = {
    "stats": """\
stats [--json]

  Print a one-line summary of the database.

  Output fields:
    LB entries    — total number of LB-numbered shows in the database
    Checksums     — total number of individual track checksums
    Latest LB     — highest LB number currently indexed
    Last import   — timestamp of the most-recent flat-file import

  Flags:
    --json        Return the raw JSON object instead of the formatted line

  Examples:
    lb> stats
    lb> stats --json
""",

    "search": """\
search <query> [--field all|location|date|description] [--json]

  Full-text search across the entry database.

  Arguments:
    query         The search term (quote multi-word terms)

  Flags:
    --field       Which field to search.  Choices:
                    all           Search all fields (default)
                    location      Concert venue / city
                    date          Recording date string (e.g. "1966-05-26")
                    description   Notes / set-list description
    --json        Return raw JSON array of matching entries

  Output columns (plain mode):
    LB-NNNNN  <date>  <location>

  Examples:
    lb> search Newport
    lb> search "Royal Albert Hall" --field location
    lb> search 1966 --field date --json
""",

    "lookup": """\
lookup <file> [<file> ...] [--json]

  Read one or more checksum files and report which LB entries they match.

  Arguments:
    file          Path to a checksum file, or a glob pattern (e.g. *.md5).
                  Multiple files / patterns are accepted and merged before lookup.

  Flags:
    --json        Return full JSON response including per-checksum details

  Output columns (plain mode):
    LB-NNNNN  <status>  matched=N  missing=N

  Examples:
    lb> lookup /downloads/show.ffp
    lb> lookup *.md5 *.ffp
    lb> lookup checksums.txt --json
""",

    "import": """\
import <path>

  Import a flat checksum file into the local database.

  Arguments:
    path          Absolute or relative path to the checksum file.
                  The path is resolved to an absolute path before sending to
                  the backend, so relative paths work fine.

  Examples:
    lb> import /data/lb_checksums.txt
    lb> import exports/new_batch.txt
""",

    "show": """\
show <LB> [--json]

  Display the full record for a single LB entry: date, location, rating, CDR,
  timing, description, setlist, stored checksums, and cached attachment files.

  Arguments:
    LB            LB number as an integer (123), zero-padded (00123), or
                  with prefix (LB-00123).

  Flags:
    --json        Return the raw JSON from /api/entry/<lb>

  Examples:
    lb> show 123
    lb> show LB-00042 --json
""",

    "open": """\
open <LB>

  Open the LosslessBob detail page for an entry in the system's default browser.

  Arguments:
    LB            LB number (same formats as 'show')

  Examples:
    lb> open 123
    lb> open LB-01234
""",

    "diff": """\
diff <file> [<file> ...] [--json]

  Read one or more checksum files and display a diff-style comparison against
  the database.

  Output symbols:
    ✓  File was found in the database for this LB
    ✗  File is in the database for this LB but was NOT in your input
    ?  File was in your input but is NOT in the database at all

  Arguments:
    file          Path to a checksum file or glob pattern (same as 'lookup').

  Flags:
    --json        Return the raw lookup JSON

  Examples:
    lb> diff /downloads/show.ffp
    lb> diff *.md5
""",

    "verify": """\
verify <dir> [<dir> ...] [--json]

  Verify audio files in one or more local directories against the checksum
  files (.ffp, .md5, .st5) that exist in the same directory.

  Each directory is checked for standalone checksum files; each audio file
  listed in those checksums is re-hashed and compared.

  Arguments:
    dir           Path to a local directory containing audio and checksum files.

  Flags:
    --json        Return the full JSON result from /api/verify

  Examples:
    lb> verify /music/LB-00123
    lb> verify /music/LB-00123 /music/LB-00456
""",

    "missing": """\
missing [--field checksums|metadata] [--json]

  List LB entries that have no checksums or no scraped metadata.

  Flags:
    --field checksums   (default) LB numbers in the range 1..max that have no
                        rows in the checksums table.
    --field metadata    LB numbers whose page returned 404 on losslessbob.com
                        (i.e. the scraper found no page to read).
    --json              Return raw JSON

  Examples:
    lb> missing
    lb> missing --field metadata
    lb> missing --field checksums --json
""",

    "export": """\
export [--format csv|json|txt] [--out FILE] [--json]

  Export the entries table (concert metadata) to a file.

  Flags:
    --format csv    (default) Download the full entries table as a CSV file.
    --format json   Paginate through entries and write a JSON array.
                    If --out is omitted, prints to stdout.
    --format txt    Write one line per entry: LB-NNNNN  date  location.
    --out FILE      Output file path.  Defaults: entries.csv / entries.txt.

  Examples:
    lb> export
    lb> export --format json --out all_entries.json
    lb> export --format txt --out concerts.txt
""",

    "backup": """\
backup [<dest>] [--json]

  Create a timestamped snapshot of the SQLite database via VACUUM INTO.
  The backup is always written to data/backups/ first; if <dest> is given
  the file is also copied there.

  Arguments:
    dest          Optional path to copy the backup to (file or directory).

  Flags:
    --json        Print the raw JSON response from /api/db/backup

  Examples:
    lb> backup
    lb> backup /external/drive/lb_backup.db
""",

    "recent": """\
recent [N] [--json]

  Show the N most recently scraped entries (sorted by scraped_at DESC).
  Entries that have never been scraped appear last.

  Arguments:
    N             Number of entries to show (default: 10, max: 500).

  Flags:
    --json        Return the raw dbedit JSON response

  Examples:
    lb> recent
    lb> recent 25
    lb> recent 50 --json
""",

    "serve": """\
serve [--port N]

  Start the Flask backend server in the foreground (blocking).

  This is mainly useful for running the backend as a standalone service.
  In interactive shell mode the backend is already running in the background,
  so you rarely need this command.

  Flags:
    --port N      Listen on port N instead of the default 5174

  Example:
    lb> serve --port 8080
""",

    "daemon": """\
daemon start|stop|status

  Manage the LosslessBob backend as a persistent background service.

  The backend is launched as a detached OS process so it survives closing
  your terminal or exiting the interactive shell.  Long-running operations
  (scrape, crawler) continue uninterrupted.  When you open a new terminal
  and run cli.py, it automatically attaches to the running backend instead
  of starting a new one.

  Sub-commands:

  start [--port N]
    Fork run_backend.py as a detached process, write data/backend.pid,
    and redirect output to data/backend.log.  Prints the PID when ready.

  stop
    Send SIGTERM to the stored PID and remove data/backend.pid.

  status [--port N]
    Show whether the backend is running, its PID, and whether the port
    is accepting connections.

  Examples:
    lb> daemon start
    lb> daemon status
    lb> daemon stop

  One-shot:
    python cli.py daemon start
    python cli.py daemon status
    python cli.py daemon stop
""",

    "scrape": """\
scrape start|stop|status

  Manage the entry-metadata scraper, which fetches concert details
  (date, location, description) from the LosslessBob website for each
  entry in the database.

  Sub-commands:

  start [--start-lb N] [--end-lb N] [--force] [--watch]
    Start the scraper.
      --start-lb N   First LB number to scrape (default: 1)
      --end-lb N     Last LB number to scrape  (default: all)
      --force        Re-scrape entries that already have metadata
      --watch        Stream progress until the scrape finishes

  stop
    Send a graceful stop signal.  The current entry finishes first.

  status [--json]
    Show a one-line status summary (or raw JSON with --json).
    Output: running|idle  done/total  current=LB-NNNNN  errors=N

  Examples:
    lb> scrape start --watch
    lb> scrape start --start-lb 100 --end-lb 200 --force
    lb> scrape status
    lb> scrape stop
""",

    "fingerprint": """\
fingerprint build|stop|status|identify|stats|scan-dupes|dupes

  Manage the acoustic fingerprint database (Wang/Shazam-style landmark algorithm).
  Fingerprinting identifies recordings by spectral content — robust to encoding
  changes, level differences, and partial files.

  Sub-commands:

  build [--force] [--watch]
    Index all audio files in the collection into fingerprints.db.
      --force     Re-fingerprint files whose content has not changed
      --watch     Stream progress until the build finishes

  stop
    Send a graceful stop signal to the running build.

  status [--json]
    Show current build progress.

  identify <FILE> [--json]
    Identify an unknown audio file against the fingerprint DB.
    Prints a ranked list of matching entries with scores.
    A result is marked CONFIDENT when its score >= 20.

  stats [--json]
    Show fingerprint DB statistics (track count, hash count).

  scan-dupes [--watch]
    Run a background scan for duplicate recordings in the collection.
    Two recordings are considered duplicates when they share enough
    temporally coherent fingerprint hashes.

  dupes [--json]
    Show the most recent duplicate-scan results.

  Examples:
    lb> fingerprint build --watch
    lb> fingerprint status
    lb> fingerprint identify /music/LB-00123/track01.flac
    lb> fingerprint stats
    lb> fingerprint scan-dupes --watch
    lb> fingerprint dupes
""",

    "crawler": """\
crawler start|stop|status

  Manage the full-domain site crawler, which archives web pages from
  the LosslessBob site for offline search and indexing.

  Sub-commands:

  start [--scope incremental|full] [--force] [--delay-ms N] [--daily-cap N] [--watch]
    Start the crawler.
      --scope incremental   Only fetch new or changed pages (default)
      --scope full          Re-crawl every page regardless of cache
      --force               Re-fetch already-cached pages
      --delay-ms N          Milliseconds between requests (default: 1500)
      --daily-cap N         Max requests this session (default: unlimited)
      --watch               Stream a live tail log until the crawl finishes

  stop
    Send a graceful stop signal.

  status [--json]
    Stream a live tail log of the running crawl (same as --watch).
    Prints "idle" if no crawl is in progress.
    With --json: print a one-shot status snapshot and exit.

  Live log format:
    HH:MM:SS ↓ /path/to/page    (↓ = fetched, ↺ = 304 not modified)
      ok:N 304:N 404:N err:N Q:N

  Examples:
    lb> crawler start --watch
    lb> crawler start --scope full --delay-ms 2000 --daily-cap 500
    lb> crawler status
    lb> crawler stop
""",
}


def _fmt_help(text: str) -> str:
    """Wrap help text to terminal width, preserving indentation."""
    w = _term_width()
    if w >= 70:
        return text
    lines = []
    for line in text.splitlines():
        if len(line) <= w:
            lines.append(line)
            continue
        stripped = line.lstrip()
        indent_n = len(line) - len(stripped)
        prefix = " " * indent_n
        wrapped = textwrap.fill(
            stripped, width=w,
            initial_indent=prefix,
            subsequent_indent=prefix + "  ",
        )
        lines.append(wrapped)
    return "\n".join(lines)


def _help_text() -> str:
    """Return the help overview sized for the current terminal width."""
    if _term_width() < 50:
        return (
            "Commands\n"
            "──────────────────────────────\n"
            "stats      DB summary\n"
            "search <q> Search entries\n"
            "lookup <f> Checksums lookup\n"
            "import <p> Import file\n"
            "show <LB>  Full details\n"
            "open <LB>  Open browser\n"
            "diff <f>   Diff vs database\n"
            "verify <d> Verify audio\n"
            "missing    Missing entries\n"
            "export     Export data\n"
            "backup     Backup DB\n"
            "recent [N] Recent (def: 10)\n"
            "daemon ... Background server\n"
            "scrape ... Metadata scraper\n"
            "crawler .. Site crawler\n"
            "finger .. Fingerprint DB\n"
            "serve      Start backend\n"
            "\n"
            "--json  --port N\n"
            "help [cmd]  clear  exit\n"
        )
    return _HELP_TEXT


_COMPLETIONS = [
    "stats", "search", "lookup", "import", "serve",
    "show", "open", "diff", "verify",
    "missing", "missing --field checksums", "missing --field metadata",
    "export", "export --format csv", "export --format json", "export --format txt",
    "backup", "recent",
    "daemon start", "daemon stop", "daemon status",
    "scrape start", "scrape stop", "scrape status",
    "crawler start", "crawler stop", "crawler status",
    "fingerprint build", "fingerprint build --force", "fingerprint build --watch",
    "fingerprint stop", "fingerprint status",
    "fingerprint identify", "fingerprint stats",
    "fingerprint scan-dupes", "fingerprint scan-dupes --watch",
    "fingerprint dupes",
    "help", "clear", "exit", "quit",
]

_TOP_LEVEL = sorted({c.split()[0] for c in _COMPLETIONS})


def _completer(text: str, state: int):
    """Readline completer for shell commands."""
    options = [c for c in _COMPLETIONS if c.startswith(text)] + \
              [None]  # type: ignore[list-item]
    return options[state] if state < len(options) else None


# ── Rich output formatters ─────────────────────────────────────────────────────


def _print_show(data: dict) -> None:
    """Pretty-print a full LB entry record."""
    entry     = data.get("entry", {})
    checksums = data.get("checksums", [])
    files     = data.get("files", [])
    w         = _term_width()
    body_w    = max(20, w - 4)
    fn_w      = max(10, w - 12)

    lb = entry.get("lb_number", "?")
    print(_hr(f"LB-{lb:05d}"))

    val_w = max(10, w - 14)  # 14 = 2 indent + 10 label + 2 spaces
    for label, key in [("Date",     "date_str"),
                       ("Location", "location"),
                       ("Rating",   "rating"),
                       ("CDR",      "cdr"),
                       ("Timing",   "timing"),
                       ("Status",   "status")]:
        val = (entry.get(key) or "—")[:val_w]
        print(f"  {label:10s} {val}")

    for section_key, section_label in [("description", "Description"),
                                        ("setlist",     "Setlist")]:
        text = (entry.get(section_key) or "").strip()
        if not text:
            continue
        print(f"\n  {section_label}:")
        for line in text.splitlines():
            if not line.strip():
                print()
                continue
            for chunk in [line[i:i + body_w] for i in range(0, max(1, len(line)), body_w)]:
                print(f"    {chunk}")

    if checksums:
        print(f"\n  Checksums ({len(checksums)}):")
        for c in checksums:
            t    = _TYPE_LABELS.get(c.get("chk_type", ""), "?")
            xref = " [xref]" if c.get("xref") else ""
            print(f"    {t:3s}  {c.get('filename', '')[:fn_w]}{xref}")

    if files:
        print(f"\n  Files ({len(files)}):")
        for f in files:
            dl   = "✓" if f.get("downloaded") else " "
            name = (f.get("clean_name") or f.get("filename") or "")[:fn_w]
            print(f"    [{dl}] {name}")

    print(_hr())


def _print_diff(data: dict, *, base_url: str) -> None:
    """Print diff-style lookup output; fetches entry detail to name missing files."""
    import requests as _req

    w       = _term_width()
    fn_w    = max(15, w - 6)
    db_sfx  = " [DB]" if w < 50 else "  (in DB, not in input)"
    db_fn_w = max(10, fn_w - len(db_sfx))

    summary = data.get("summary", {})
    detail  = data.get("detail", [])

    by_lb: dict[int, list]      = {}
    not_found: list             = []
    seen_per_lb: dict[int, set] = {}

    for item in detail:
        lb = item.get("lb_number")
        st = item.get("status", "")
        if lb is None or st == "NOT FOUND":
            not_found.append(item)
        elif st != "XREF":
            by_lb.setdefault(lb, []).append(item)
            seen_per_lb.setdefault(lb, set()).add(item.get("checksum"))

    lb_sum_map = {s["lb_number"]: s for s in summary.get("lb_summary", [])}

    for lb_num in sorted(by_lb):
        items    = by_lb[lb_num]
        lb_sum   = lb_sum_map.get(lb_num, {})
        st       = lb_sum.get("status", "")
        miss_cnt = lb_sum.get("missing_from_set", 0)

        print(_hr(f"LB-{lb_num:05d}  {st}"))

        seen_fns: set = set()
        for item in items:
            fn = item.get("filename") or item.get("checksum", "")
            if fn not in seen_fns:
                seen_fns.add(fn)
                print(f"  ✓  {fn[:fn_w]}")

        if miss_cnt:
            missing_fns: list[str] = []
            try:
                entry_data  = _req.get(f"{base_url}/api/entry/{lb_num}", timeout=5).json()
                db_chks     = entry_data.get("checksums", [])
                seen_chks   = seen_per_lb.get(lb_num, set())
                missing_fns = [c["filename"] for c in db_chks
                               if c.get("checksum") not in seen_chks
                               and not c.get("xref")]
            except Exception:
                pass
            if missing_fns:
                for fn in missing_fns:
                    print(f"  ✗  {fn[:db_fn_w]}{db_sfx}")
            else:
                print(f"  ✗  ({miss_cnt} DB file{'s' if miss_cnt != 1 else ''} not in input)")

    if not_found:
        print(_hr("NOT IN DATABASE"))
        seen_nf: set = set()
        for item in not_found:
            fn = item.get("filename") or item.get("checksum", "")
            if fn not in seen_nf:
                seen_nf.add(fn)
                print(f"  ?  {fn[:fn_w]}")

    if not by_lb and not not_found:
        print("No checksums found in input.")

    if by_lb or not_found:
        print(_hr())


def _print_verify(results: list) -> None:
    """Print verification results: summary line per folder then problem files."""
    w = _term_width()
    for r in results:
        folder  = str(r.get("folder", "?"))
        status  = r.get("status", "?").upper()
        total   = r.get("total", 0)
        ok      = r.get("pass", 0)
        miss_t  = r.get("missing_types", [])

        if w < 50:
            folder_w = max(8, w - 14)
            if len(folder) > folder_w:
                folder = "…" + folder[-(folder_w - 1):]
            print(f"{folder}  {status}  {ok}/{total}")
            if miss_t:
                print(f"  (no {'/'.join(miss_t)})")
        else:
            folder_w = max(10, w - 22)
            if len(folder) > folder_w:
                folder = "…" + folder[-(folder_w - 1):]
            miss_tag = f"  (no {'/'.join(miss_t)})" if miss_t else ""
            print(f"{folder}  {status}  {ok}/{total}{miss_tag}")

        fn_w = max(10, w - 16)
        for f in r.get("files", []):
            overall = f.get("overall", "")
            if overall in ("pass", "na"):
                continue
            sym = "✗" if "fail" in overall or "mismatch" in overall else "·"
            fn  = f.get("filename", "")[:fn_w]
            print(f"  {sym}  {fn}  ({overall})")


# ── Screen helpers ─────────────────────────────────────────────────────────────


def _clear_screen() -> None:
    """Clear the terminal and move the cursor to the top-left corner."""
    print("\033[2J\033[H", end="", flush=True)


def _setup_readline() -> None:
    """Enable readline history and tab-completion if available."""
    try:
        import readline
        readline.set_completer(_completer)
        readline.parse_and_bind("tab: complete")
        if _HISTORY_FILE.exists():
            readline.read_history_file(str(_HISTORY_FILE))
        import atexit
        atexit.register(readline.write_history_file, str(_HISTORY_FILE))
    except ImportError:
        pass


def _run_interactive(port: int) -> None:
    """Run the interactive REPL."""
    if _is_flask_running(port):
        if _term_width() < 50:
            print(f"LosslessBob {_VERSION}\nAttaching...", flush=True)
        else:
            print(f"LosslessBob {_VERSION} — attaching to existing backend on port {port}...",
                  end=" ", flush=True)
    else:
        if _term_width() < 50:
            print(f"LosslessBob {_VERSION}\nStarting...", flush=True)
        else:
            print(f"LosslessBob {_VERSION} — starting backend on port {port}...",
                  end=" ", flush=True)
        t = threading.Thread(target=_start_flask, args=(port,), daemon=True)
        t.start()
        _wait_for_flask(port)

    _clear_screen()
    if _term_width() < 50:
        print(f"LosslessBob {_VERSION}\ntype 'help' or 'exit'\n")
    else:
        print(f"LosslessBob {_VERSION} — interactive shell  (type 'help' or 'exit')\n")

    _setup_readline()

    parser   = _build_parser(klass=_SilentParser)
    base_url = f"http://127.0.0.1:{port}"

    while True:
        try:
            line = input("lb> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            if _term_width() < 50:
                print("  (Ctrl-D or 'exit')")
            else:
                print("  (press Ctrl-D or type 'exit' to quit)")
            continue

        if not line:
            continue

        if line in ("exit", "quit", "q"):
            break

        if line == "clear":
            _clear_screen()
            continue

        if line in ("help", "?"):
            print(_help_text())
            continue

        # help <command>
        if line.startswith(("help ", "? ")):
            topic = line.split(None, 1)[1].strip()
            if topic in _COMMAND_HELP:
                print(_fmt_help(_COMMAND_HELP[topic]))
            else:
                cmds = ", ".join(sorted(_COMMAND_HELP))
                if _term_width() < 50:
                    print(f"No help for '{topic}'.")
                    print(f"Try: {cmds[:_term_width() - 5]}")
                else:
                    print(f"No help for '{topic}'.  Try: {cmds}")
            continue

        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            continue

        try:
            args = parser.parse_args(tokens)
        except _UsageError as exc:
            print(f"Error: {exc}")
            print("Type 'help' for available commands.")
            continue
        except SystemExit:
            continue

        if args.command is None:
            print("Type 'help' for available commands.")
            continue

        try:
            _execute(args, base_url)
        except KeyboardInterrupt:
            print()
        except Exception as exc:
            print(f"Error: {exc}")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    # No arguments → interactive mode
    if len(sys.argv) == 1:
        _run_interactive(port=5174)
        return

    # Check for --port before deciding mode (e.g. `cli.py --port 5175`)
    if len(sys.argv) == 3 and sys.argv[1] == "--port" and sys.argv[2].isdigit():
        _run_interactive(port=int(sys.argv[2]))
        return

    # One-shot mode (backward-compatible)
    parser = _build_parser()
    # Make subcommand required for one-shot mode
    parser._subparsers._actions[-1].required = True  # type: ignore[attr-defined]
    args     = parser.parse_args()
    port     = args.port
    base_url = f"http://127.0.0.1:{port}"

    if args.command not in ("serve", "daemon"):
        if not _is_flask_running(port):
            t = threading.Thread(target=_start_flask, args=(port,), daemon=True)
            t.start()
            _wait_for_flask(port)

    _execute(args, base_url)


if __name__ == "__main__":
    main()
