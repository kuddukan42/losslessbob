#!/usr/bin/env python3
"""Norton Commander-style two-pane terminal front end for the LosslessBob collection.

Each pane browses a collection mount (or any directory, or the virtual list of misfiled
folders). Every LB folder is marked against the year routing: canonical, misfiled, stray
(not in the collection), duplicate, or blocked. The keybar drives the running backend's
own filing API — the hash-verified move, the my_collection update and the qBittorrent
location sync all stay in backend/filer.py; this file never moves or deletes anything.

    tools/lb-nc                          # left/right = the first two mounts
    tools/lb-nc --left DIR --right DIR   # start the panes somewhere else
    tools/lb-nc --read-only              # every write gated off
    tools/lb-nc --preview --columns 100  # paint the screens once over a synthetic tree

Adapted from music_hopper/hopper_nc.py (same keys, schemes and rendering). Plain ANSI,
stdlib only, so any python3 runs it. The backend must be up on port 5174.
"""

from __future__ import annotations

import argparse
import json
import locale
import logging
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import threading
import time
import tty
import unicodedata
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
LOG_PATH = REPO / "data" / "logs" / "lb_nc.log"
SIZE_CACHE = Path.home() / ".cache" / "lb_nc" / "sizes.json"
CONFIG_PATH = Path.home() / ".config" / "systools" / "config"
API_URL = "http://127.0.0.1:5174"
MIN_COLUMNS = 30
MIN_ROWS = 10
TICK = 0.25
LOG_ROWS = 8
POLL = 0.5
SCHEME_NAMES = ("nc", "amber", "green", "mono")
PIPELINE_STEPS = ["verify", "lookup", "lbdir", "rename", "file"]
VIEW_SUFFIXES = (".txt", ".md5", ".ffp", ".st5", ".sha256", ".nfo", ".log", ".cue")
LB_RE = re.compile(r"LB-(\d{1,6})", re.IGNORECASE)
YEAR_RE = re.compile(r"^(\d{4})")
IN_PLACE = "at its routed location, not in collection"

log = logging.getLogger("lb_nc")

# -------------------------------------------------------------------- glyphs, palette

GLYPHS = {"canonical": "✓", "misfiled": "→", "stray": "?", "dup": "≠", "blocked": "⊘",
          "dest": "⇒", "cursor": "▶", "ellipsis": "…", "running": "■"}
ASCII_GLYPHS = {"canonical": "*", "misfiled": ">", "stray": "?", "dup": "=", "blocked": "x",
                "dest": "=>", "cursor": ">", "ellipsis": "~", "running": "*"}
STATUS_TEXT = {"canonical": "canonical", "misfiled": "MISFILED", "stray": "not in collection",
               "dup": "DUPLICATE", "blocked": "blocked"}
BOX = {"h": "─", "v": "│", "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
       "tt": "┬", "bt": "┴", "lt": "├", "rt": "┤"}
ASCII_BOX = {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+",
             "tt": "+", "bt": "+", "lt": "+", "rt": "+"}

# role -> SGR parameters. nc is 16-colour only, for authenticity.
SCHEMES: dict[str, dict[str, str]] = {
    "nc": {"pane": "44;37", "text": "44;97", "frame": "44;96", "header": "46;30;1",
           "cursor": "46;30", "tag": "44;93;1", "cursor_tag": "46;93;1", "dim": "44;36",
           "key_num": "40;97", "key_label": "46;30", "dialog": "47;30",
           "dialog_hi": "40;97", "danger": "41;97;1", "run": "40;93;1", "ghost": "44;96;4"},
    "amber": {"pane": "40;33", "text": "40;93", "frame": "40;33", "header": "40;93;1",
              "cursor": "43;30", "tag": "40;97;1", "cursor_tag": "43;97;1", "dim": "40;33",
              "key_num": "40;93", "key_label": "43;30", "dialog": "43;30",
              "dialog_hi": "40;93", "danger": "41;97;1", "run": "40;97;1", "ghost": "40;93;4"},
    "green": {"pane": "40;32", "text": "40;92", "frame": "40;32", "header": "40;92;1",
              "cursor": "42;30", "tag": "40;97;1", "cursor_tag": "42;97;1", "dim": "40;32",
              "key_num": "40;92", "key_label": "42;30", "dialog": "42;30",
              "dialog_hi": "40;92", "danger": "41;97;1", "run": "40;97;1", "ghost": "40;92;4"},
    "mono": {"pane": "0", "text": "0", "frame": "0", "header": "1", "cursor": "7",
             "tag": "1", "cursor_tag": "7;1", "dim": "0", "key_num": "1", "key_label": "7",
             "dialog": "7", "dialog_hi": "0", "danger": "7;1", "run": "1", "ghost": "4"},
}

Line = list[tuple[str, str]]          # (role, text) segments


def char_width(ch: str) -> int:
    """Terminal cells one character takes."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def text_width(text: str) -> int:
    """Terminal cells a string takes."""
    return sum(char_width(c) for c in text)


def printable(text: str) -> str:
    """A filename with control characters (and lone surrogates) made visible."""
    return "".join(c if c.isprintable() and not 0xD800 <= ord(c) <= 0xDFFF else "?"
                   for c in text)


def fit(text: str, width: int, ellipsis: str = "…", right: bool = False) -> str:
    """Truncate with an ellipsis and pad to exactly `width` cells."""
    if width <= 0:
        return ""
    text = printable(text)
    if text_width(text) > width:
        out, used = "", 0
        for ch in text:
            w = char_width(ch)
            if used + w > width - 1:
                break
            out, used = out + ch, used + w
        text = out + ellipsis + " " * (width - 1 - used)
    pad = " " * (width - text_width(text))
    return pad + text if right else text + pad


def fit_left(text: str, width: int, ellipsis: str = "…") -> str:
    """Keep the tail of a long path rather than its head."""
    text = printable(text)
    if text_width(text) <= width:
        return fit(text, width, ellipsis)
    tail = ""
    for ch in reversed(text):
        if text_width(tail) + char_width(ch) > width - 1:
            break
        tail = ch + tail
    return fit(ellipsis + tail, width, ellipsis)


def line_width(line: Line) -> int:
    """Cells a segment list takes."""
    return sum(text_width(t) for _, t in line)


def pad_line(line: Line, width: int, role: str) -> Line:
    """Truncate or pad a segment list to exactly `width` cells."""
    return cut(line, 0, width) + ([(role, " " * (width - min(width, line_width(line))))]
                                  if line_width(line) < width else [])


def cut(line: Line, start: int, end: int) -> Line:
    """The cells [start, end) of a line; a wide character split at an edge becomes spaces."""
    out: Line = []
    pos = 0
    for role, text in line:
        buf = ""
        for ch in text:
            w = char_width(ch)
            if pos >= start and pos + w <= end:
                buf += ch
            elif pos < end and pos + w > start:
                buf += " " * (min(end, pos + w) - max(start, pos))
            pos += w
        if buf:
            out.append((role, buf))
        if pos >= end:
            break
    return out


def overlay(line: Line, x: int, patch: Line) -> Line:
    """Paint `patch` over `line` starting at cell x."""
    width = line_width(line)
    return cut(line, 0, x) + patch + cut(line, x + line_width(patch), width)


def paint(line: Line, scheme: dict[str, str]) -> str:
    """Render segments as one ANSI string, merging runs of the same role."""
    out: list[str] = []
    last = None
    for role, text in line:
        if not text:
            continue
        if role != last:
            out.append(f"\x1b[0;{scheme.get(role, '0')}m")
            last = role
        out.append(text)
    return "".join(out) + "\x1b[0m"


def plain(line: Line) -> str:
    """A segment list as bare text."""
    return "".join(t for _, t in line)


def human(size: int | None) -> str:
    """1.4G-style size, five cells at most."""
    if size is None:
        return "…"
    value = float(size)
    for unit in "BKMGT":
        if value < 1000 or unit == "T":
            return f"{value:.0f}{unit}" if value >= 10 or unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return "?"


def tree_size(path: Path) -> int:
    """Bytes under a folder, unreadable entries skipped."""
    total = 0
    for dirpath, _dirs, names in os.walk(path, onerror=lambda e: None):
        for name in names:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


# -------------------------------------------------------------------------------- api

class ApiError(Exception):
    """The backend could not be reached or answered with an error."""


class Api:
    """JSON over HTTP to the LosslessBob backend."""

    def __init__(self, base: str = API_URL, timeout: float = 30.0) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read() or b"null")
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                return payload            # the routes answer errors as JSON bodies
            raise ApiError(f"{method} {path}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ApiError(f"backend unreachable at {self.base} ({exc})") from exc

    def get(self, path: str) -> Any:
        """GET a JSON endpoint."""
        return self._call("GET", path)

    def post(self, path: str, body: dict) -> Any:
        """POST a JSON body to an endpoint."""
        return self._call("POST", path, body)


# ------------------------------------------------------------------------------ model

def norm(path: str | Path) -> str:
    """A path as a comparable string: normalised, forward slashes, no trailing slash."""
    return os.path.normpath(str(path)).replace("\\", "/")


def lb_of(name: str) -> int | None:
    """The first LB number in a folder name, or None."""
    m = LB_RE.search(name)
    return int(m.group(1)) if m else None


@dataclass
class Collection:
    """my_collection rows, mounts and year routes, with the canonical-location rules."""

    mounts: list[dict]
    routes: dict[int, dict]
    rows: list[dict]
    by_path: dict[str, dict] = field(default_factory=dict)
    by_lb: dict[int, dict] = field(default_factory=dict)

    @classmethod
    def build(cls, mounts: list[dict], routes: list[dict], rows: list[dict]) -> Collection:
        """Index backend payloads by path and LB number."""
        coll = cls(mounts, {int(r["year"]): r for r in routes}, rows)
        for row in rows:
            if row.get("disk_path"):
                coll.by_path[norm(row["disk_path"])] = row
            coll.by_lb[int(row["lb_number"])] = row
        return coll

    @classmethod
    def load(cls, api: Api) -> Collection:
        """Fetch mounts, routes and the collection from the backend."""
        mounts = api.get("/api/collection/mounts")
        routes = api.get("/api/collection/routes")
        rows = api.get("/api/collection")
        for payload in (mounts, routes):
            if not isinstance(payload, dict) or "error" in payload:
                raise ApiError(str(payload.get("error") if isinstance(payload, dict)
                                   else payload))
        if not isinstance(rows, list):
            raise ApiError(str(rows.get("error") if isinstance(rows, dict) else rows))
        return cls.build(mounts["mounts"], routes["routes"], rows)

    def mount_for(self, path: str | Path) -> dict | None:
        """The mount whose root is the longest prefix of path."""
        target = norm(path)
        best, best_len = None, -1
        for m in self.mounts:
            root = norm(m["root_path"])
            if (target == root or target.startswith(root.rstrip("/") + "/")) \
                    and len(root) > best_len:
                best, best_len = m, len(root)
        return best

    def mount_by_id(self, mount_id: int) -> dict | None:
        """A mount row by id."""
        return next((m for m in self.mounts if m["id"] == mount_id), None)

    def expected_parent(self, year: int) -> str | None:
        """Where the year routes to: mount root joined with the route's sub_path."""
        route = self.routes.get(year)
        if not route:
            return None
        root = route["root_path"]
        return norm(Path(root) / route["sub_path"]) if route.get("sub_path") else norm(root)

    @staticmethod
    def year_of(row: dict) -> int | None:
        """The show year the backend derived, or the leading year of date_str."""
        if row.get("route_year"):
            return int(row["route_year"])
        m = YEAR_RE.match(row.get("date_str") or "")
        return int(m.group(1)) if m else None

    def row_status(self, row: dict) -> tuple[str, str]:
        """(status, note) for a collection row: canonical, misfiled or blocked."""
        year = self.year_of(row)
        if not year:
            return "blocked", "no show date — can't route"
        expected = self.expected_parent(year)
        if expected is None:
            return "blocked", f"no route for {year}"
        if norm(Path(row["disk_path"]).parent) == expected:
            return "canonical", expected
        return "misfiled", expected

    def classify(self, path: Path) -> tuple[str, str, dict | None]:
        """(status, note, row) for a folder on disk; status is "" for a non-LB folder."""
        row = self.by_path.get(norm(path))
        if row:
            status, note = self.row_status(row)
            return status, note, row
        lb = lb_of(path.name)
        if lb is None:
            return "", "", None
        other = self.by_lb.get(lb)
        if other:
            return "dup", other.get("disk_path") or "", other
        m = YEAR_RE.match(path.name)
        expected = self.expected_parent(int(m.group(1))) if m else None
        if expected is not None and norm(path.parent) == expected:
            return "stray", IN_PLACE, None
        return "stray", "not in collection", None

    def misfiled(self) -> list[dict]:
        """Collection rows whose folder is not under its year's routed location."""
        return [r for r in self.rows
                if r.get("disk_path") and self.row_status(r)[0] == "misfiled"]


@dataclass
class Entry:
    """One row in a pane."""

    name: str
    path: Path
    kind: str                      # parent | dir | file
    status: str = ""               # a GLYPHS status key, LB folders only
    note: str = ""                 # expected parent, the other copy, or a reason
    row: dict | None = None
    lb: int | None = None

    @property
    def key(self) -> str:
        """Tag key: the path, so the misfiled view can hold same-named folders."""
        return str(self.path)


def list_dir(root: Path, cwd: Path, coll: Collection | None) -> list[Entry]:
    """One directory, never outside root, LB folders classified. `..` leads the list."""
    if not str(cwd).startswith(str(root)) or not cwd.is_dir():
        cwd = root
    rows = [Entry("..", cwd.parent if cwd != root else root, "parent")]
    try:
        children = sorted(cwd.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        children = []
    for path in children:
        if path.name.startswith("."):
            continue
        try:
            is_dir = path.is_dir()
        except OSError:
            is_dir = False
        entry = Entry(path.name, path, "dir" if is_dir else "file")
        if is_dir:
            entry.lb = lb_of(path.name)
            if coll is not None:
                entry.status, entry.note, entry.row = coll.classify(path)
        rows.append(entry)
    return rows


def list_misfiled(coll: Collection | None) -> list[Entry]:
    """The virtual pane: every misfiled collection folder, wherever it is."""
    if coll is None:
        return []
    out = []
    for row in coll.misfiled():
        path = Path(row["disk_path"])
        status, note = coll.row_status(row)
        out.append(Entry(path.name, path, "dir", status, note, row, int(row["lb_number"])))
    out.sort(key=lambda e: e.name.lower())
    return out


class Pane:
    """Cursor, scroll, tags and filter over a directory or the misfiled view."""

    def __init__(self, root: Path | None, label: str = "") -> None:
        self.root = root                 # None: the misfiled view
        self.cwd = root
        self.label = label
        self.prev: tuple[Path | None, Path | None, str] | None = None
        self.entries: list[Entry] = []
        self.cursor = 0
        self.top = 0
        self.filter = ""
        self.editing = False
        self.tags: set[str] = set()

    @property
    def virtual(self) -> bool:
        """True for the misfiled view."""
        return self.root is None

    def visible(self) -> list[Entry]:
        """Entries after the filter; `..` always stays."""
        if not self.filter:
            return self.entries
        needle = self.filter.lower()
        return [e for e in self.entries if e.kind == "parent" or needle in e.name.lower()]

    def current(self) -> Entry | None:
        """The entry under the cursor."""
        rows = self.visible()
        return rows[self.cursor] if 0 <= self.cursor < len(rows) else None

    def move(self, delta: int) -> None:
        """Move the cursor, clamped."""
        count = len(self.visible())
        self.cursor = max(0, min(count - 1, self.cursor + delta)) if count else 0

    def scroll(self, height: int) -> None:
        """Keep the cursor inside the window of `height` rows."""
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + height:
            self.top = self.cursor - height + 1
        self.top = max(0, min(self.top, max(0, len(self.visible()) - height)))

    def selection(self) -> list[Entry]:
        """Tagged entries, else the cursor entry."""
        tagged = [e for e in self.entries if e.key in self.tags]
        if tagged:
            return tagged
        cur = self.current()
        return [cur] if cur and cur.kind != "parent" else []


class SizeCache:
    """Folder sizes computed lazily in a background thread, cached by path and mtime."""

    def __init__(self, path: Path | None, threaded: bool = True) -> None:
        self.path = path
        self.threaded = threaded
        self.data: dict[str, list[float]] = {}
        self.pending: deque[Path] = deque()
        self.lock = threading.Lock()
        self.changed = False
        if path and path.is_file():
            try:
                self.data = json.loads(path.read_text())
            except (OSError, ValueError):
                self.data = {}
        if threaded:
            threading.Thread(target=self._worker, daemon=True).start()

    def get(self, path: Path) -> int | None:
        """The cached size, or None while it is being computed."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        with self.lock:
            hit = self.data.get(str(path))
            if hit and hit[0] == mtime:
                return int(hit[1])
            if path not in self.pending:
                self.pending.append(path)
        if not self.threaded:
            self._compute(self.pending.popleft())
            return self.get(path)
        return None

    def _compute(self, path: Path) -> None:
        try:
            mtime = path.stat().st_mtime
            size = tree_size(path)
        except OSError as exc:
            log.debug("size failed %s: %s", path, exc)
            mtime, size = time.time(), 0
        with self.lock:
            self.data[str(path)] = [mtime, size]
            self.changed = True

    def _worker(self) -> None:
        while True:
            with self.lock:
                path = self.pending.popleft() if self.pending else None
            if path is None:
                time.sleep(TICK)
                continue
            self._compute(path)

    def save(self) -> None:
        """Persist the cache."""
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock:
                self.path.write_text(json.dumps(self.data))
        except OSError as exc:
            log.warning("size cache not saved: %s", exc)


# ------------------------------------------------------------------------------- jobs

class JobError(Exception):
    """A job failed; the message goes to the log pane and the failure dialog."""


Emit = Callable[[str, bool], None]    # (text, replace_last_progress_line)


@dataclass
class Job:
    """One unit of work against the backend: a label, what the gate shows, a callable."""

    label: str
    detail: str
    run: Callable[[Emit], None]
    gated: bool = True


def file_job(api: Api, entry: Entry, mount_id: int | None, file_mode: str | None,
             dest: str) -> Job:
    """File (or move) one folder via /api/pipeline/file/start, polling to completion."""
    body_item: dict[str, Any] = {"path": str(entry.path), "lb_number": entry.lb}
    if mount_id is not None:
        body_item["mount_id"] = mount_id
    body: dict[str, Any] = {"folders": [body_item]}
    if file_mode:
        body["file_mode"] = file_mode

    def run(emit: Emit) -> None:
        emit(f"LB-{entry.lb:05d} {entry.name}", False)
        started = api.post("/api/pipeline/file/start", body)
        if not started.get("ok"):
            raise JobError(f"{started.get('error_code') or 'error'}: {started.get('error')}")
        status: dict = {}
        while True:
            time.sleep(POLL)
            status = api.get("/api/pipeline/file/status")
            emit(f"  {status.get('stage', '?')} {status.get('files_done', 0)}/"
                 f"{status.get('files_total', 0)} files  "
                 f"{human(status.get('bytes_done'))}/{human(status.get('bytes_total'))}", True)
            if not status.get("running"):
                break
        result = status.get("result") or {}
        if not result.get("ok"):
            raise JobError(f"{result.get('error_code') or 'error'}: {result.get('error')}")
        emit(f"  {result.get('file_mode', 'move')}d ⇒ {result.get('dest')}", True)
        if result.get("qbt_error"):
            emit(f"  qBittorrent: {result['qbt_error']}", False)
        elif result.get("qbt_synced"):
            emit("  qBittorrent location synced", False)

    verb = "move" if file_mode == "move" else "file"
    return Job(f"{verb} LB-{entry.lb:05d}", f"{entry.name}  {GLYPHS['dest']} {dest}", run)


def register_job(api: Api, entry: Entry) -> Job:
    """Add a stray that already sits at its routed location to my_collection."""
    def run(emit: Emit) -> None:
        res = api.post("/api/collection", {"lb_number": entry.lb, "folder_name": entry.name,
                                           "disk_path": str(entry.path)})
        if not res.get("ok"):
            raise JobError(f"register LB-{entry.lb:05d}: {res.get('error')}")
        emit(f"registered LB-{entry.lb:05d} at {entry.path}"
             + ("" if res.get("added") else " (already present)"), False)
    return Job(f"register LB-{entry.lb:05d}", f"{entry.name}  (register in place)", run)


def route_job(api: Api, year: int, mount: dict, sub_path: str) -> Job:
    """Re-point one year's route at a mount, keeping its sub_path."""
    def run(emit: Emit) -> None:
        res = api.post("/api/collection/routes/bulk", {
            "year_from": year, "year_to": year, "mount_id": mount["id"], "sub_path": sub_path})
        if not res.get("ok"):
            raise JobError(f"route {year}: {res.get('error')}")
        emit(f"route {year} ⇒ {mount['label']}" + (f" /{sub_path}" if sub_path else ""), False)
    return Job(f"route {year}", f"route {year} ⇒ {mount['label']}", run)


def pipeline_job(api: Api, paths: list[Path], sink: dict[str, dict]) -> Job:
    """Run verify → lookup → lbdir → rename → file-check; results land in `sink`."""
    def run(emit: Emit) -> None:
        res = api.post("/api/pipeline/run/start", {
            "folders": [str(p) for p in paths], "steps": PIPELINE_STEPS})
        if not res.get("ok"):
            raise JobError(f"{res.get('error_code') or 'error'}: {res.get('error')}")
        status: dict = {}
        while True:
            time.sleep(POLL)
            status = api.get("/api/pipeline/run/status")
            emit(f"  pipeline {status.get('folders_done', 0)}/"
                 f"{status.get('folders_total', 0)} folders", True)
            if not status.get("running"):
                break
        sink.clear()
        sink.update(status.get("results") or {})
        for err in status.get("errors") or []:
            emit(f"  error {err.get('folder')}: {err.get('message')}", False)
        if status.get("cancelled"):
            emit("  cancelled", False)
    return Job("pipeline", f"pipeline {len(paths)} folder(s): {' → '.join(PIPELINE_STEPS)}",
               run)


class Runner:
    """Runs jobs one at a time in a thread; stops at the first failure.

    A filing job belongs to the backend once started, so quitting the UI never cuts a
    move in half — only the jobs still queued behind it are dropped.
    """

    def __init__(self, read_only: bool, threaded: bool = True) -> None:
        self.read_only = read_only
        self.threaded = threaded
        self.lines: deque[str] = deque(maxlen=400)
        self.thread: threading.Thread | None = None
        self.job: Job | None = None
        self.last: Job | None = None
        self.failure: tuple[str, list[str]] | None = None
        self.finished = False
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self._progress = False

    @property
    def running(self) -> bool:
        """True while a queue is being worked."""
        return self.thread is not None and self.thread.is_alive()

    def emit(self, text: str, progress: bool) -> None:
        """Append a log line; a progress line replaces the previous progress line."""
        with self.lock:
            if progress and self._progress and self.lines:
                self.lines[-1] = text
            else:
                self.lines.append(text)
            self._progress = progress
        if not progress:
            log.info("%s", text)

    def submit(self, jobs: list[Job]) -> bool:
        """Start a queue. False when busy or empty."""
        if self.running or not jobs:
            return False
        if self.read_only and any(j.gated for j in jobs):
            raise PermissionError("read-only mode")
        self.failure = None
        self.stop.clear()
        if self.threaded:
            self.thread = threading.Thread(target=self._work, args=(list(jobs),), daemon=True)
            self.thread.start()
        else:
            self._work(list(jobs))
        return True

    def _work(self, jobs: list[Job]) -> None:
        done = 0
        for job in jobs:
            if self.stop.is_set():
                self.emit(f"stopped — {len(jobs) - done} job(s) not run", False)
                break
            self.job = job
            log.info("run: %s", job.label)
            try:
                job.run(self.emit)
            except (JobError, ApiError) as exc:
                self.emit(f"FAILED {job.label}: {exc}", False)
                self.failure = (job.label, [f"{job.label}: {exc}",
                                            f"{len(jobs) - done - 1} queued job(s) not run"])
                break
            except Exception as exc:             # a bug must not kill the UI
                log.exception("job crashed: %s", job.label)
                self.failure = (job.label, [f"{job.label}: {exc!r}"])
                break
            done += 1
        self.last, self.job = self.job, None
        self.finished = True


# ------------------------------------------------------------------------------- keys

CSI_TILDE = {"1": "home", "2": "ins", "3": "del", "4": "end", "5": "pgup", "6": "pgdn",
             "7": "home", "8": "end", "11": "f1", "12": "f2", "13": "f3", "14": "f4",
             "15": "f5", "17": "f6", "18": "f7", "19": "f8", "20": "f9", "21": "f10"}
CSI_FINAL = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end",
             "P": "f1", "Q": "f2", "R": "f3", "S": "f4"}
CTRL = {b"\r": "enter", b"\n": "enter", b"\t": "tab", b"\x7f": "backspace",
        b"\x08": "backspace", b"\x0f": "ctrl-o", b"\x13": "ctrl-s", b"\x12": "ctrl-r",
        b"\x15": "ctrl-u", b"\x03": "ctrl-c"}
SEQ_RE = re.compile(rb"\x1b(?:\[\[([A-E])|\[<(\d+);(\d+);(\d+)([Mm])|\[([0-9;]*)([~A-Za-z])"
                    rb"|O([A-Za-z]))")


def decode(data: bytes) -> list[str]:
    """Bytes from the terminal -> key names. Unknown sequences are dropped, never echoed.

    Mouse reports come back as "mouse:BUTTON:X:Y:M" (press) or ":m" (release), 1-based.
    """
    keys: list[str] = []
    i = 0
    while i < len(data):
        byte = data[i:i + 1]
        if byte == b"\x1b":
            match = SEQ_RE.match(data, i)
            if match:
                i = match.end()
                if match.group(1):                        # linux console F1-F5
                    keys.append(f"f{ord(match.group(1)) - ord('A') + 1}")
                elif match.group(2):
                    keys.append("mouse:{}:{}:{}:{}".format(
                        *(g.decode() for g in match.group(2, 3, 4, 5))))
                elif match.group(7):
                    params, final = match.group(6).decode(), match.group(7).decode()
                    name = (CSI_TILDE.get(params.split(";")[0]) if final == "~"
                            else CSI_FINAL.get(final))
                    if name:
                        keys.append(name)
                else:
                    name = CSI_FINAL.get(match.group(8).decode())
                    if name:
                        keys.append(name)
                continue
            if i + 1 < len(data) and data[i + 1:i + 2] in (b"[", b"O"):
                break                                     # unknown or partial: drop the rest
            keys.append("esc")
            i += 1
            continue
        if byte in CTRL:
            keys.append(CTRL[byte])
            i += 1
            continue
        if byte[0] < 0x20:
            i += 1
            continue
        length = 1 if byte[0] < 0x80 else 2 if byte[0] >> 5 == 6 else \
            3 if byte[0] >> 4 == 14 else 4
        keys.append(data[i:i + length].decode("utf-8", "replace"))
        i += length
    return keys


PHONE_KEYS = {"k": "up", "j": "down", "K": "pgup", "J": "pgdn", "g": "home", "G": "end",
              "o": "ctrl-o", "s": "ctrl-s", "u": "ctrl-u", "q": "f10", "?": "f1",
              " ": "ins", "0": "f10", **{str(n): f"f{n}" for n in range(1, 10)}}


def normalize(key: str, modal: bool) -> str:
    """Map phone keys onto the F-key names. Digits count as F-keys only outside a dialog."""
    return key if modal else PHONE_KEYS.get(key, key)


# ----------------------------------------------------------------------------- dialogs

class Dialog:
    """A modal box. `render` returns its lines; `handle` consumes a key."""

    title = ""
    fullscreen = False

    def body(self, width: int) -> list[Line]:
        """The box contents, `width` cells wide."""
        return []

    def render(self, app: App, cols: int, rows: int) -> list[Line]:
        """The framed box."""
        width = min(cols - 2, max(40, min(96, cols - 4)))
        inner = width - 2
        b = app.box
        title = f"{b['h']} {self.title} "
        top = [("dialog", b["tl"] + title + b["h"] * max(0, inner - text_width(title))
                + b["tr"])]
        lines = [pad_line(top, width, "dialog")]
        for row in self.body(inner)[:max(1, rows - 4)]:
            lines.append([("dialog", b["v"])] + pad_line(row, inner, "dialog")
                         + [("dialog", b["v"])])
        lines.append([("dialog", b["bl"] + b["h"] * inner + b["br"])])
        return lines

    def handle(self, app: App, key: str) -> None:
        """Consume a key."""
        if key in ("esc", "enter", "q"):
            app.dialog = None


class Message(Dialog):
    """Text and any key closes."""

    def __init__(self, title: str, text: list[str]) -> None:
        self.title, self.text = title, text

    def body(self, width: int) -> list[Line]:
        return [[("dialog", fit(t, width))] for t in [*self.text, "", "  any key closes"]]

    def handle(self, app: App, key: str) -> None:
        app.dialog = None


class Confirm(Dialog):
    """The write gate. Shows what each job does; y runs, anything else cancels."""

    def __init__(self, title: str, jobs: list[Job], blurb: list[str],
                 toggle: tuple[str, str, Callable[[bool], list[Job]]] | None = None) -> None:
        self.title, self.jobs, self.blurb, self.toggle = title, jobs, blurb, toggle
        self.state = False

    def body(self, width: int) -> list[Line]:
        rows: list[Line] = []
        for job in self.jobs[:10]:
            rows.append([("dialog_hi", fit(job.detail, width))])
        if len(self.jobs) > 10:
            rows.append([("dialog", f"  … and {len(self.jobs) - 10} more")])
        rows.append([("dialog", "")])
        rows.extend([("dialog", fit(t, width))] for t in self.blurb)
        if self.toggle:
            mark = "x" if self.state else " "
            rows.append([("dialog", fit(f"  [{mark}] {self.toggle[1]}  "
                                        f"({self.toggle[0]} toggles)", width))])
        rows.append([("dialog", "")])
        rows.append([("dialog", "          "), ("danger", "[ y ] run"),
                     ("dialog", "      [ n ] cancel")])
        return rows

    def handle(self, app: App, key: str) -> None:
        if self.toggle and key == self.toggle[0]:
            self.state = not self.state
            self.jobs = self.toggle[2](self.state)
            return
        app.dialog = None
        if key in ("y", "Y"):
            app.run(self.jobs)
        else:
            log.info("cancelled: %s (key %s)", self.title, key)
            app.say(f"{self.title}: cancelled — only y runs it")


class Picker(Dialog):
    """A list to choose from with arrows/j/k and Enter, or by number."""

    def __init__(self, title: str, items: list[tuple[str, Callable[[], None]]]) -> None:
        self.title, self.items, self.cursor, self.top = title, items, 0, 0

    def body(self, width: int) -> list[Line]:
        height = 14
        self.top = max(0, min(self.cursor, max(self.top, self.cursor - height + 1)))
        rows: list[Line] = []
        for i, (label, _) in enumerate(self.items[self.top:self.top + height], self.top):
            role = "cursor" if i == self.cursor else "dialog"
            rows.append([(role, fit(f" {i + 1:>2} {label}", width))])
        if not self.items:
            rows.append([("dialog", "  (nothing here)")])
        return rows

    def handle(self, app: App, key: str) -> None:
        if key in ("up", "k"):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("down", "j"):
            self.cursor = min(len(self.items) - 1, self.cursor + 1)
        elif key in ("esc", "q"):
            app.dialog = None
        elif key == "enter" and self.items:
            app.dialog = None
            self.items[self.cursor][1]()
        elif key.isdigit() and 0 < int(key) <= min(9, len(self.items)):
            app.dialog = None
            self.items[int(key) - 1][1]()


class Prompt(Dialog):
    """One line of text input; Enter hands it to `done`."""

    def __init__(self, title: str, label: str, text: str,
                 done: Callable[[str], None]) -> None:
        self.title, self.label, self.text, self.done = title, label, text, done

    def body(self, width: int) -> list[Line]:
        return [[("dialog", fit(self.label, width))],
                [("dialog_hi", fit_left(self.text + "_", width))],
                [("dialog", "")], [("dialog", fit("  Enter ok · Esc cancel", width))]]

    def handle(self, app: App, key: str) -> None:
        if key == "esc":
            app.dialog = None
        elif key == "enter":
            app.dialog = None
            self.done(self.text)
        elif key == "backspace":
            self.text = self.text[:-1]
        elif len(key) == 1 and key.isprintable():
            self.text += key


class Pager(Dialog):
    """Full-screen text viewer; n cycles through several pages."""

    fullscreen = True

    def __init__(self, title: str, pages: list[tuple[str, list[str]]]) -> None:
        self.title, self.pages, self.page, self.top = title, pages, 0, 0

    def render(self, app: App, cols: int, rows: int) -> list[Line]:
        name, text = self.pages[self.page]
        height = rows - 2
        self.top = max(0, min(self.top, max(0, len(text) - height)))
        head = f" {self.title}: {name}  ({self.page + 1}/{len(self.pages)})"
        out = [[("key_label", fit(head, cols, app.g["ellipsis"]))]]
        for line in text[self.top:self.top + height]:
            out.append([("pane", fit(line.expandtabs(4), cols, app.g["ellipsis"]))])
        while len(out) < rows - 1:
            out.append([("pane", " " * cols)])
        out.append([("key_label", fit(" j/k scroll · n next page · q close", cols))])
        return out

    def handle(self, app: App, key: str) -> None:
        step = {"up": -1, "k": -1, "down": 1, "j": 1, "pgup": -20, "K": -20, "pgdn": 20,
                "J": 20, " ": 20}
        if key in step:
            self.top = max(0, self.top + step[key])
        elif key in ("home", "g"):
            self.top = 0
        elif key in ("end", "G"):
            self.top = 10 ** 6
        elif key == "n":
            self.page, self.top = (self.page + 1) % len(self.pages), 0
        elif key in ("esc", "q", "f10", "f3", "enter"):
            app.dialog = None


HELP = """lb_nc — two panes over the collection mounts

Move        ↑ ↓ PgUp PgDn Home End   (phone: k j K J g G)
Tab         switch pane              Enter   open folder
Backspace   up one level             Space/Ins tag · + all · - none · * invert
/           filter the active pane   Esc     close / clear filter / clear tags

1 Help      this screen
2 Info      the folder's collection row, show date, route and expected location
3 View      lbdir / checksum / text files inside the folder; n cycles files
4 Pipe      run the pipeline (verify, lookup, lbdir, rename, file-check) on the
            tagged folders; lbdir may copy a manifest in; results open in a pager
5 Scan      reload the collection from the backend and relist both panes
6 Move      move tagged LB folders to the OTHER pane's mount (hash-verified, the
            collection row and qBittorrent follow); r also re-routes their years
7 File      file tagged misfiled / stray folders to their year-routed location
8 Misfd     toggle this pane to the virtual list of every misfiled folder
9 Menu      drive picker, swap panes, stop queue, cancel pipeline, re-route years
0/q Quit

d           drive picker for this pane    u / Ctrl-U  swap panes
o / Ctrl-O  log pane                      s / Ctrl-S  size the cursor folder
t           cycle colour scheme

Glyphs: ✓ canonical  → misfiled (⇒ where it belongs)  ? stray, not in collection
        ≠ duplicate — the collection holds this LB at another path  ⊘ blocked

Every write goes through the backend (port 5174) after a y/n gate, one folder at a
time, stopping at the first failure. Duplicates are never filed — resolve them by hand."""


# -------------------------------------------------------------------------------- app

class App:
    """State, key handling and layout. No terminal I/O here, so tests can drive it."""

    def __init__(self, api: Api, left: Path | None = None, right: Path | None = None,
                 read_only: bool = False, scheme: str = "nc", ascii_only: bool = False,
                 threaded: bool = True, size_cache: Path | None = SIZE_CACHE,
                 persist: bool = True) -> None:
        self.api = api
        self.read_only = read_only
        self.scheme = scheme if scheme in SCHEMES else "nc"
        self.ascii = ascii_only
        self.g = ASCII_GLYPHS if ascii_only else GLYPHS
        self.box = ASCII_BOX if ascii_only else BOX
        self.threaded = threaded
        self.persist = persist
        self.dialog: Dialog | None = None
        self.show_log = False
        self.quit = False
        self.coll: Collection | None = None
        self.coll_error = ""
        self.loading = False
        self.sizes = SizeCache(size_cache, threaded)
        self.runner = Runner(read_only, threaded)
        self.pipeline_results: dict[str, dict] = {}
        self.hits: list[tuple[int, int, int, str]] = []     # (row, x0, x1, key)
        self.pane_rows: dict[str, tuple[int, int, int, int]] = {}
        self.lock = threading.Lock()
        self.dirty = True
        self._free_cache: dict[str, tuple[float, str]] = {}
        self.flash = ("", 0.0)
        self._load()
        mounts = [Path(m["root_path"]) for m in (self.coll.mounts if self.coll else [])]
        start_left = left or (mounts[0] if mounts else Path.cwd())
        start_right = right or (mounts[1] if len(mounts) > 1 else start_left)
        self.left = Pane(start_left, self.label_for(start_left))
        self.right = Pane(start_right, self.label_for(start_right))
        self.active = self.left
        self.relist()

    # ---- data

    def _load(self) -> None:
        try:
            coll = Collection.load(self.api)
            error = ""
        except ApiError as exc:
            coll, error = None, str(exc)
            log.warning("collection load failed: %s", exc)
        with self.lock:
            if coll is not None or self.coll is None:
                self.coll = coll
            self.coll_error = error
            self.loading = False
            self.dirty = True

    def reload(self) -> None:
        """Re-read the collection (in a thread when threaded), then relist both panes."""
        if self.threaded:
            if self.loading:
                return
            self.loading = True

            def work() -> None:
                self._load()
                with self.lock:
                    self.relist()
            threading.Thread(target=work, daemon=True).start()
        else:
            self._load()
            self.relist()

    def label_for(self, path: Path | None) -> str:
        """The mount label a path sits on, or its basename."""
        if path is None:
            return "misfiled"
        mount = self.coll.mount_for(path) if self.coll else None
        return mount["label"] if mount else (path.name or str(path))

    def relist(self) -> None:
        """Relist both panes, keeping the cursor on the same name where it survives."""
        for pane in (self.left, self.right):
            keep = pane.current().key if pane.current() else ""
            if pane.virtual:
                pane.entries = list_misfiled(self.coll)
            else:
                pane.entries = list_dir(pane.root, pane.cwd, self.coll)
            keys = [e.key for e in pane.visible()]
            pane.tags &= {e.key for e in pane.entries}
            pane.cursor = keys.index(keep) if keep in keys else min(pane.cursor, len(keys) - 1)
            pane.move(0)
        self.dirty = True

    # ---- navigation

    def other(self) -> Pane:
        """The inactive pane."""
        return self.right if self.active is self.left else self.left

    def set_dir(self, pane: Pane, path: Path) -> None:
        """Point a pane at a directory under its root."""
        if pane.virtual or not str(path).startswith(str(pane.root)) or not path.is_dir():
            return
        pane.cwd = path
        pane.entries = list_dir(pane.root, path, self.coll)
        pane.filter = ""
        pane.cursor = pane.top = 0

    def set_root(self, pane: Pane, root: Path | None) -> None:
        """Re-root a pane at a mount, a directory, or (None) the misfiled view."""
        if root is not None and not root.is_dir():
            self.dialog = Message("Drive", [f"Not reachable: {root}"])
            return
        if root is None and not pane.virtual:
            pane.prev = (pane.root, pane.cwd, pane.label)
        pane.root = pane.cwd = root
        pane.label = self.label_for(root)
        pane.tags.clear()
        pane.filter, pane.cursor, pane.top = "", 0, 0
        pane.entries = list_misfiled(self.coll) if root is None else \
            list_dir(root, root, self.coll)

    def handle(self, key: str) -> None:
        """Dispatch one decoded key."""
        self.dirty = True
        if key.startswith("mouse:"):
            self.mouse(key)
            return
        if self.dialog:
            self.dialog.handle(self, key)
            return
        pane = self.active
        if pane.editing:
            if key == "esc":
                pane.filter, pane.editing = "", False
            elif key == "enter":
                pane.editing = False
            elif key == "backspace":
                pane.filter = pane.filter[:-1]
            elif len(key) == 1 and key.isprintable():
                pane.filter += key
            pane.cursor = pane.top = 0
            return
        key = normalize(key, False)
        moves = {"up": -1, "down": 1, "pgup": -10, "pgdn": 10, "home": -10 ** 9,
                 "end": 10 ** 9}
        if key in moves:
            pane.move(moves[key])
            return
        simple: dict[str, Callable[[], None]] = {
            "tab": self.switch, "backspace": self.go_up, "enter": self.enter,
            "ins": self.tag_one, "+": lambda: self.tag_all("all"),
            "-": lambda: self.tag_all("none"), "*": lambda: self.tag_all("invert"),
            "/": self.start_filter, "esc": self.escape, "t": self.cycle_scheme,
            "d": self.drive_dialog, "ctrl-u": self.swap, "ctrl-o": self.toggle_log,
            "ctrl-s": self.size_current, "ctrl-r": self.reload, "f5": self.reload,
            "f1": self.help, "f2": self.info, "f3": self.view, "f4": self.pipeline_dialog,
            "f6": self.move_dialog, "f7": self.file_dialog, "f8": self.toggle_misfiled,
            "f9": self.menu_dialog, "f10": self.request_quit,
        }
        if key in simple:
            simple[key]()

    def mouse(self, key: str) -> None:
        """Wheel scrolls; a click hits a key or moves the cursor."""
        _, button, x, y, kind = key.split(":")
        b, col, row = int(button), int(x) - 1, int(y) - 1
        if b in (64, 65):
            if not self.dialog:
                self.active.move(-3 if b == 64 else 3)
            return
        if kind != "M" or b & 3 != 0:
            return
        for hit_row, x0, x1, hit_key in self.hits:
            if row == hit_row and x0 <= col < x1:
                self.handle(hit_key)
                return
        if self.dialog:
            return
        for name, (y0, height, x0, width) in self.pane_rows.items():
            if y0 <= row < y0 + height and x0 <= col < x0 + width:
                pane = self.left if name == "left" else self.right
                self.active = pane
                pane.cursor = pane.top + row - y0
                pane.move(0)

    def switch(self) -> None:
        """Tab: the other pane becomes active."""
        self.active = self.other()

    def swap(self) -> None:
        """Ctrl-U: exchange the two panes' locations."""
        self.left, self.right = self.right, self.left
        self.active = self.left if self.active is self.right else self.right

    def go_up(self) -> None:
        """Backspace: up one level, never above the pane root."""
        pane = self.active
        if pane.virtual or pane.cwd == pane.root:
            return
        here = pane.cwd.name
        self.set_dir(pane, pane.cwd.parent)
        names = [e.name for e in pane.visible()]
        pane.cursor = names.index(here) if here in names else 0

    def enter(self) -> None:
        """Enter: open a folder (or go up on `..`); in the misfiled view, show Info."""
        cur = self.active.current()
        if not cur:
            return
        if self.active.virtual:
            self.info()
        elif cur.kind == "parent":
            self.go_up()
        elif cur.kind == "dir":
            self.set_dir(self.active, cur.path)

    def tag_one(self) -> None:
        """Space/Ins: toggle the cursor entry and step down."""
        cur = self.active.current()
        if not cur or cur.kind == "parent":
            return
        self.active.tags ^= {cur.key}
        self.active.move(1)

    def tag_all(self, how: str) -> None:
        """+ all LB folders, - none, * invert."""
        keys = {e.key for e in self.active.visible() if e.lb is not None}
        tags = self.active.tags
        self.active.tags = keys if how == "all" else set() if how == "none" else keys - tags

    def start_filter(self) -> None:
        """/: type a filter."""
        self.active.editing = True

    def escape(self) -> None:
        """Esc: clear the filter, else the tags."""
        if self.active.filter:
            self.active.filter, self.active.cursor = "", 0
        else:
            self.active.tags.clear()

    def cycle_scheme(self) -> None:
        """t: next colour scheme."""
        self.scheme = SCHEME_NAMES[(SCHEME_NAMES.index(self.scheme) + 1) % len(SCHEME_NAMES)]
        if self.persist:
            save_scheme(self.scheme)

    def toggle_log(self) -> None:
        """o: show or hide the log pane."""
        self.show_log = not self.show_log

    def size_current(self) -> None:
        """s: size the cursor folder now (normally lazy for LB folders only)."""
        cur = self.active.current()
        if cur and cur.kind == "dir":
            self.sizes.get(cur.path)
            self.say(f"sizing {cur.name}…")

    def toggle_misfiled(self) -> None:
        """F8: flip the active pane to the misfiled view and back."""
        pane = self.active
        if pane.virtual:
            root, cwd, _label = pane.prev or (Path.cwd(), Path.cwd(), "")
            self.set_root(pane, root)
            if cwd:
                self.set_dir(pane, cwd)
        else:
            if self.coll is None:
                self.dialog = Message("Misfiled", [self.coll_error or "no collection loaded"])
                return
            self.set_root(pane, None)

    def request_quit(self) -> None:
        """F10: quit, warning when a queue is still running."""
        if not self.runner.running:
            self.quit = True
            return
        self.dialog = Picker("A job is still running", [
            ("Quit anyway — the backend finishes the current folder; the rest are dropped",
             lambda: setattr(self, "quit", True)),
            ("Stay", lambda: None)])

    def help(self) -> None:
        """F1: the key reference."""
        self.dialog = Pager("Help", [("keys", HELP.splitlines())])

    # ---- actions

    def say(self, text: str) -> None:
        """Show a short status in the info strip for a few seconds."""
        self.flash = (text, time.monotonic())
        self.dirty = True

    def run(self, jobs: list[Job]) -> None:
        """Start jobs. The single path to the runner; read-only refuses gated jobs here too."""
        if self.runner.running:
            self.dialog = Message("Busy", ["A job is already running — wait for it."])
            return
        if self.read_only and any(j.gated for j in jobs):
            self.dialog = Message("Read-only", ["read-only mode"])
            return
        self.show_log = True
        self.say(f"running {jobs[0].label}…")
        self.runner.submit(jobs)

    def gate(self, title: str, jobs: list[Job], blurb: list[str], **kw: Any) -> None:
        """Open the confirm dialog, or refuse in read-only mode or while busy."""
        if self.read_only:
            self.dialog = Message(title, ["read-only mode"])
        elif self.runner.running:
            self.dialog = Message("Busy", ["A job is already running — wait for it."])
        elif not jobs:
            self.dialog = Message(title, blurb or ["Nothing to do."])
        else:
            self.dialog = Confirm(title, jobs, blurb, **kw)

    def lb_selection(self) -> list[Entry]:
        """Selected LB folders in the active pane."""
        return [e for e in self.active.selection() if e.kind == "dir" and e.lb is not None]

    def preview(self, entries: list[Entry], mount_id: int | None,
                ) -> tuple[list[tuple[Entry, str]], list[str]]:
        """Ask the backend where each entry would land: ([(entry, dest)], [skip lines])."""
        items = []
        for e in entries:
            item: dict[str, Any] = {"path": str(e.path), "lb_number": e.lb}
            if mount_id is not None:
                item["mount_id"] = mount_id
            items.append(item)
        res = self.api.post("/api/pipeline/file/preview", {"folders": items})
        if "results" not in res:
            raise ApiError(str(res.get("error")))
        ok, skipped = [], []
        for e, r in zip(entries, res["results"], strict=True):
            if r.get("ok"):
                ok.append((e, r["dest"]))
            else:
                skipped.append(f"  skip {e.name}: {r.get('error_code')} — {r.get('error')}")
        return ok, skipped

    def file_dialog(self) -> None:
        """F7: file misfiled and stray folders to their year-routed location."""
        picked = self.lb_selection()
        if not picked:
            self.dialog = Message("File", ["Select LB folders first (Space tags, + all)."])
            return
        todo, skipped, register = [], [], []
        for e in picked:
            if e.status == "stray" and e.note == IN_PLACE:
                register.append(e)
            elif e.status in ("misfiled", "stray"):
                todo.append(e)
            elif e.status == "canonical":
                skipped.append(f"  skip {e.name}: already canonical")
            elif e.status == "dup":
                skipped.append(f"  skip {e.name}: collection has LB-{e.lb:05d} at {e.note}")
            else:
                skipped.append(f"  skip {e.name}: {e.note or 'not classified'}")
        try:
            chosen, refused = self.preview(todo, None) if todo else ([], [])
        except ApiError as exc:
            self.dialog = Message("File", [str(exc)])
            return
        jobs = [file_job(self.api, e, None, "move" if e.row else None, dest)
                for e, dest in chosen]
        jobs += [register_job(self.api, e) for e in register]
        blurb = [f"{len(chosen)} folder(s) to their year-routed location.",
                 "Registered folders are moved; strays use the pipeline file mode and",
                 "are added to the collection. Cross-drive moves are SHA-256 verified",
                 "before the source goes. One at a time, stops at the first failure."]
        if register:
            blurb += [f"{len(register)} stray(s) already in place are only registered — no",
                      "checksum pass; F4 Pipe them first if unsure."]
        blurb += [*skipped, *refused]
        self.gate("File to canonical", jobs, blurb)

    def move_dialog(self) -> None:
        """F6: move selected LB folders onto the other pane's mount."""
        target_pane = self.other()
        mount = self.coll.mount_for(target_pane.cwd) \
            if self.coll and not target_pane.virtual else None
        if mount is None:
            self.dialog = Message("Move", ["The other pane must show a collection mount",
                                           "(d picks a drive)."])
            return
        picked = self.lb_selection()
        if not picked:
            self.dialog = Message("Move", ["Select LB folders first (Space tags, + all)."])
            return
        todo, skipped = [], []
        for e in picked:
            here = self.coll.mount_for(e.path)
            if e.status == "dup":
                skipped.append(f"  skip {e.name}: collection has LB-{e.lb:05d} at {e.note}")
            elif e.status == "blocked":
                skipped.append(f"  skip {e.name}: {e.note}")
            elif here and here["id"] == mount["id"] and e.status == "canonical":
                skipped.append(f"  skip {e.name}: already on {mount['label']}")
            else:
                todo.append(e)
        try:
            chosen, refused = self.preview(todo, mount["id"]) if todo else ([], [])
        except ApiError as exc:
            self.dialog = Message("Move", [str(exc)])
            return
        moves = [file_job(self.api, e, mount["id"], "move", dest) for e, dest in chosen]
        years = sorted({y for e, _ in chosen if (y := self.year_of(e)) is not None})
        stay = [y for y in years if (self.coll.routes.get(y) or {}).get("mount_id")
                != mount["id"]]

        def jobs(reroute: bool) -> list[Job]:
            if not reroute:
                return moves
            return moves + [route_job(self.api, y, mount,
                                      (self.coll.routes.get(y) or {}).get("sub_path") or "")
                            for y in stay]
        blurb = [f"{len(moves)} folder(s) ⇒ {mount['label']} ({mount['root_path']}),",
                 "under each year's route sub-folder. Hash-verified across drives;",
                 "the collection row and qBittorrent follow. Stops at the first failure."]
        if stay:
            span = f"{stay[0]}–{stay[-1]}" if len(stay) > 1 else str(stay[0])
            blurb += [f"Years {span} route elsewhere: without r these folders show as",
                      "misfiled afterwards. With r, the routes move too — other folders",
                      "of those years left behind then show as misfiled (F8)."]
        blurb += skipped + refused
        toggle = ("r", f"re-route {len(stay)} year(s) to {mount['label']} after the moves",
                  jobs) if stay and moves else None
        self.gate("Move to other mount", moves, blurb, toggle=toggle)

    def year_of(self, entry: Entry) -> int | None:
        """The show year of an entry, from its collection row or its folder name."""
        if entry.row:
            return Collection.year_of(entry.row)
        m = YEAR_RE.match(entry.name)
        return int(m.group(1)) if m else None

    def pipeline_dialog(self) -> None:
        """F4: gate a pipeline run over the selected folders."""
        picked = [e for e in self.active.selection() if e.kind == "dir"]
        if not picked:
            self.dialog = Message("Pipeline", ["Select folders first (Space tags)."])
            return
        job = pipeline_job(self.api, [e.path for e in picked], self.pipeline_results)
        self.gate("Pipeline", [job], [
            "Checks each folder: verify checksums, look up the LB, fetch the lbdir",
            "(may copy a manifest INTO the folder), propose a rename, resolve the",
            "filing destination. Nothing is renamed or moved. Results open after."])

    def results_pages(self) -> list[tuple[str, list[str]]]:
        """The last pipeline run as pager text, one line block per folder."""
        lines: list[str] = []
        for folder, row in sorted(self.pipeline_results.items()):
            lookup = row.get("lookup") or {}
            lb = lookup.get("lb_number")
            lines.append(f"{Path(folder).name}")
            lines.append(f"  severity {row.get('severity', '?')}"
                         + (f" · LB-{lb:05d}" if lb else ""))
            for step in ("verify", "lookup", "lbdir", "rename", "file"):
                verdict = row.get(step) or {}
                text = f"    {step:<7}{verdict.get('status', '-'):<8}{verdict.get('label', '')}"
                if step == "file" and verdict.get("dest"):
                    text += f"  {self.g['dest']} {verdict['dest']}"
                elif verdict.get("error"):
                    text += f"  ({verdict['error']})"
                lines.append(text)
            lines.append("")
        return [("results", lines or ["(no results)"])]

    def info(self) -> None:
        """F2: everything known about the cursor folder."""
        cur = self.active.current()
        if not cur or cur.kind == "parent":
            return
        text = [str(cur.path), ""]
        if cur.lb is None:
            text.append("No LB number in the folder name.")
        else:
            text.append(f"LB-{cur.lb:05d}  ·  {STATUS_TEXT.get(cur.status, '?')}")
            row = cur.row
            if row:
                text.append(f"show  {row.get('date_str') or '?'}  {row.get('location') or ''}")
                text.append(f"collection path  {row.get('disk_path')}")
            if cur.status in ("canonical", "misfiled"):
                year = self.year_of(cur)
                mount = self.coll.mount_for(cur.note) if self.coll else None
                text.append(f"routes to  {cur.note}"
                            + (f"  ({mount['label']}, {year})" if mount else ""))
            elif cur.status == "dup":
                text.append(f"this path is NOT the collection copy; that is {cur.note}")
            elif cur.status == "stray":
                text.append("not in my_collection — F7 files it and registers it")
            elif cur.note:
                text.append(cur.note)
        result = self.pipeline_results.get(str(cur.path))
        if result:
            text.append(f"last pipeline: severity {result.get('severity', '?')}")
        self.dialog = Message("Info", text)

    def view(self) -> None:
        """F3: the folder's text files (lbdir, checksums, info) in the pager."""
        cur = self.active.current()
        if not cur or cur.kind == "parent":
            return
        if cur.kind == "file":
            files = [cur.path] if cur.path.suffix.lower() in VIEW_SUFFIXES else []
        else:
            try:
                files = sorted(p for p in cur.path.iterdir()
                               if p.is_file() and p.suffix.lower() in VIEW_SUFFIXES)[:12]
            except OSError:
                files = []
        if not files:
            self.dialog = Message("View", ["No lbdir, checksum or text file here."])
            return
        pages = []
        for p in files:
            try:
                text = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                text = [str(exc)]
            pages.append((p.name, text or ["(empty)"]))
        self.dialog = Pager("View", pages)

    def drive_dialog(self) -> None:
        """d: point the active pane at a mount, the misfiled view, or any directory."""
        pane = self.active
        items: list[tuple[str, Callable[[], None]]] = []
        for m in (self.coll.mounts if self.coll else []):
            state = "" if m.get("online", True) else "  OFFLINE"
            label = f"{m['label']:<10} {m['root_path']}  free {m.get('free', '?')}{state}"
            items.append((label, lambda r=Path(m["root_path"]): self.set_root(pane, r)))
        items.append(("Misfiled folders (all mounts)", lambda: self.set_root(pane, None)))
        items.append(("Directory…", lambda: setattr(self, "dialog", Prompt(
            "Directory", "Path to browse:", str(pane.cwd or Path.cwd()),
            lambda t: self.set_root(pane, Path(os.path.expanduser(t.strip())))))))
        self.dialog = Picker("Drive — " + ("left" if pane is self.left else "right"), items)

    def reroute_dialog(self) -> None:
        """Menu: re-point the routes of the selection's years at the other pane's mount."""
        mount = self.coll.mount_for(self.other().cwd) \
            if self.coll and not self.other().virtual else None
        if mount is None:
            self.dialog = Message("Re-route", ["The other pane must show a collection mount."])
            return
        years = sorted({y for e in self.lb_selection() if (y := self.year_of(e))})
        jobs = [route_job(self.api, y, mount,
                          (self.coll.routes.get(y) or {}).get("sub_path") or "")
                for y in years if (self.coll.routes.get(y) or {}).get("mount_id") != mount["id"]]
        self.gate("Re-route years", jobs, [
            f"Future filing of these years goes to {mount['label']}. Nothing moves now;",
            "folders of these years elsewhere will then show as misfiled (F8, F7)."])

    def menu_dialog(self) -> None:
        """F9: the less common actions."""
        def stop() -> None:
            self.runner.stop.set()
            self.say("queue stops after the current folder")

        def cancel_pipeline() -> None:
            try:
                self.api.post("/api/pipeline/run/cancel", {})
                self.say("pipeline cancel requested")
            except ApiError as exc:
                self.dialog = Message("Cancel", [str(exc)])

        self.dialog = Picker("Menu", [
            ("Drive picker for this pane (d)", self.drive_dialog),
            ("Swap panes (u)", self.swap),
            ("Re-route the selection's years to the other pane's mount", self.reroute_dialog),
            ("Last pipeline results", lambda: setattr(self, "dialog", Pager(
                "Pipeline", self.results_pages()))),
            ("Stop the queue after the current folder", stop),
            ("Cancel the running pipeline", cancel_pipeline),
        ])

    def tick(self) -> None:
        """Pick up job completion, sizes and flash expiry."""
        if self.runner.running:
            self.dirty = True
        if self.runner.finished:
            self.runner.finished = False
            last = self.runner.last
            if self.runner.failure:
                label, text = self.runner.failure
                self.runner.failure = None
                self.dialog = Message(f"{label}: failed", text)
            elif last and last.label == "pipeline":
                self.dialog = Pager("Pipeline", self.results_pages())
            else:
                tail = list(self.runner.lines)[-10:]
                self.dialog = Message("done", tail or ["ok"])
            self.reload()
        if self.sizes.changed:
            self.sizes.changed = False
            self.dirty = True
        if self.flash[0] and time.monotonic() - self.flash[1] >= 6:
            self.flash = ("", 0.0)
            self.dirty = True

    # ---- layout

    def frame(self, cols: int, rows: int) -> list[Line]:
        """The whole screen as segment lines, each exactly `cols` cells."""
        self.hits, self.pane_rows = [], {}
        if cols < MIN_COLUMNS or rows < MIN_ROWS:
            notice = [[("pane", fit("widen the terminal", cols, "~"))]]
            return notice + [[("pane", " " * cols)] for _ in range(rows - 1)]
        if self.dialog and self.dialog.fullscreen:
            return self.dialog.render(self, cols, rows)
        with self.lock:
            lines = self._layout(cols, rows)
        if self.dialog:
            box = self.dialog.render(self, cols, rows)
            y = max(0, (rows - len(box)) // 2)
            x = max(0, (cols - line_width(box[0])) // 2)
            for i, patch in enumerate(box[:rows]):
                if y + i < rows:
                    lines[y + i] = overlay(lines[y + i], x, patch)
        return lines

    def _layout(self, cols: int, rows: int) -> list[Line]:
        b = self.box
        two = cols >= 60
        info_rows = 3 if cols >= 80 else 2
        key_rows = 1 if two else 2
        log_rows = LOG_ROWS + 1 if self.show_log else 0
        body = rows - 1 - 1 - 1 - info_rows - 1 - key_rows - log_rows
        if body < 3 and log_rows:
            body, log_rows = body + log_rows, 0
        if body < 1:
            info_rows, body = 1, body + info_rows - 1
        out: list[Line] = []
        if two:
            lw = (cols - 3) // 2
            rw = cols - 3 - lw
            out.append([("frame", " ")] + self.pane_header(self.left, lw) + [("frame", " ")]
                       + self.pane_header(self.right, rw) + [("frame", " ")])
            out.append([("frame", b["tl"] + b["h"] * lw + b["tt"] + b["h"] * rw + b["tr"])])
            left = self.pane_body(self.left, lw, body)
            right = self.pane_body(self.right, rw, body)
            self.pane_rows = {"left": (2, body, 1, lw), "right": (2, body, lw + 2, rw)}
            for lrow, rrow in zip(left, right, strict=True):
                out.append([("frame", b["v"])] + lrow + [("frame", b["v"])] + rrow
                           + [("frame", b["v"])])
            out.append([("frame", b["lt"] + b["h"] * lw + b["bt"] + b["h"] * rw + b["rt"])])
        else:
            pane = self.active
            w = cols - 2
            out.append([("frame", " ")] + self.pane_header(pane, w, narrow=True)
                       + [("frame", " ")])
            out.append([("frame", b["tl"] + b["h"] * w + b["tr"])])
            self.pane_rows = {"left" if pane is self.left else "right": (2, body, 1, w)}
            for row in self.pane_body(pane, w, body):
                out.append([("frame", b["v"])] + row + [("frame", b["v"])])
            out.append([("frame", b["lt"] + b["h"] * w + b["rt"])])

        if log_rows:
            with self.runner.lock:
                tail = list(self.runner.lines)[-LOG_ROWS:]
            tail = [""] * (LOG_ROWS - len(tail)) + tail
            for text in tail:
                out.append([("frame", b["v"]), ("text", fit(text, cols - 2, self.g["ellipsis"])),
                            ("frame", b["v"])])
            title = f"{b['h']} log{' (running)' if self.runner.running else ''} "
            out.append([("frame", b["lt"] + title + b["h"] * max(0, cols - 2 - len(title))
                         + b["rt"])])
        for text in self.info_strip(info_rows):
            out.append([("frame", b["v"]), ("text", fit(text, cols - 2, self.g["ellipsis"])),
                        ("frame", b["v"])])
        out.append([("frame", b["bl"] + b["h"] * (cols - 2) + b["br"])])
        out.extend(self.keybar(cols, len(out)))
        return [pad_line(line, cols, "pane") for line in out[:rows]]

    def pane_header(self, pane: Pane, width: int, narrow: bool = False) -> Line:
        """The pane title (label: path) and its counts."""
        b = self.box
        if pane.virtual:
            title = "MISFILED — all mounts"
            count = f"{len(pane.entries)} misfiled"
        else:
            mount = self.coll.mount_for(pane.cwd) if self.coll else None
            if mount:
                rel = os.path.relpath(pane.cwd, mount["root_path"])
                title = f"{mount['label']}:/" + ("" if rel == "." else rel)
            else:
                title = str(pane.cwd)
            lbs = [e for e in pane.entries if e.lb is not None]
            off = sum(1 for e in lbs if e.status in ("misfiled", "stray", "dup", "blocked"))
            count = f"{len(lbs)} LB" + (f" · {off} off" if off else "")
            count += f" · {self.free(pane.cwd)} free"
        if pane.tags:
            count = f"{len(pane.tags)} tagged · {count}"
        if pane.filter or pane.editing:
            count = f"{len(pane.visible()) - (not pane.virtual)}/{count}"
        if narrow:
            title = ("[L] " if pane is self.left else "[R] ") + title
            if self.runner.running:
                count = self.g["running"] + " " + count
        if self.loading:
            count = "loading… " + count
        role = "header" if pane is self.active else "frame"
        count_w = min(text_width(count) + 2, width // 2)
        title_w = min(text_width(title) + 2, width - count_w)
        count_s = fit(f" {count} ", count_w, self.g["ellipsis"], right=True)
        title_s = fit_left(f" {title} ", title_w, self.g["ellipsis"])
        fill = b["h"] * max(0, width - title_w - count_w)
        return [(role, title_s), ("frame", fill), ("frame", count_s)]

    def pane_body(self, pane: Pane, width: int, height: int) -> list[Line]:
        """The visible rows of a pane, cursor and tags coloured."""
        rows: list[Line] = []
        visible = pane.visible()
        start = 0
        if pane.editing or pane.filter:
            cursor = "_" if pane.editing else ""
            rows.append([("tag", fit(f" /{pane.filter}{cursor}", width))])
            start = 1
        pane.scroll(height - start)
        for i in range(pane.top, pane.top + height - start):
            if i >= len(visible):
                rows.append([("pane", " " * width)])
                continue
            entry = visible[i]
            on = i == pane.cursor and pane is self.active
            tagged = entry.key in pane.tags
            ghost = i == pane.cursor and not on
            role = ("cursor_tag" if tagged else "cursor") if on else \
                "tag" if tagged else "ghost" if ghost else "text" if entry.kind == "dir" \
                else "pane"
            mark = self.g["cursor"] if on else " "
            rows.append([(role, mark + self.row_text(pane, entry, width - 1))])
        return rows

    def row_text(self, pane: Pane, entry: Entry, width: int) -> str:
        """Name, status glyph and size."""
        e = self.g["ellipsis"]
        if entry.kind == "parent":
            return fit("..", width, e)
        if entry.kind == "file":
            return fit(entry.name, width, e)
        if entry.lb is None:
            return fit(entry.name, width - 6, e) + fit("<DIR>", 6, e, right=True)
        glyph = self.g.get(entry.status, " ")
        size = self.sizes.get(entry.path)
        tail = f" {glyph} {fit(human(size), 5, e, right=True)}"
        if pane.virtual and self.coll:
            here = self.coll.mount_for(entry.path)
            there = self.coll.mount_for(entry.note)
            tail = (f" {(here or {}).get('label', '?')}{self.g['dest']}"
                    f"{(there or {}).get('label', '?')}") + tail
        if width < text_width(tail) + 6:
            tail = f" {glyph}"
        return fit(entry.name, width - text_width(tail), e) + tail

    def info_strip(self, count: int) -> list[str]:
        """Three lines about the cursor entry, or the backend state."""
        cur = self.active.current()
        rows: list[str]
        if self.coll is None:
            rows = [f"backend: {self.coll_error or 'not loaded'}",
                    "start it (/backend-restart or the app), then F5"]
        elif cur is None or cur.kind == "parent":
            rows = [str(self.active.cwd or "misfiled view"), ""]
        elif cur.lb is None:
            rows = [cur.name, "no LB number"]
        else:
            row = cur.row or {}
            first = f"{cur.name}  ·  {STATUS_TEXT.get(cur.status, '?')}"
            show = f"LB-{cur.lb:05d}  {row.get('date_str') or ''}  {row.get('location') or ''}"
            if cur.status == "misfiled":
                third = f"{self.g['dest']} {cur.note}  free: {self.free(cur.note)}  (F7 files)"
            elif cur.status == "dup":
                third = f"collection copy: {cur.note}"
            elif cur.status == "stray":
                third = ("in place, not registered — F7 registers it" if cur.note == IN_PLACE
                         else "not in collection — F7 files and registers it")
            elif cur.status == "blocked":
                third = cur.note
            else:
                third = f"{self.g['canonical']} at its routed location"
            rows = [first, show, third]
        if self.flash[0] and time.monotonic() - self.flash[1] < 6:
            rows.insert(0, f"{self.g['running']} {self.flash[0]}")
        return (rows + ["", "", ""])[:count]

    def free(self, path: str | Path | None) -> str:
        """Free space on the filesystem holding path, re-read at most every 10 s."""
        if path is None:
            return "?"
        hit = self._free_cache.get(str(path))
        if hit and time.monotonic() - hit[0] < 10:
            return hit[1]
        probe = Path(path)
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            text = human(shutil.disk_usage(probe).free)
        except OSError:
            text = "?"
        self._free_cache[str(path)] = (time.monotonic(), text)
        return text

    def keybar(self, cols: int, y: int) -> list[Line]:
        """The F-key bar; every slot is clickable."""
        full = ("Help", "Info", "View", "Pipe", "Scan", "Move", "File", "Misfd", "Menu",
                "Quit")
        short = ("Hlp", "Inf", "Viw", "Pip", "Scn", "Mov", "Fil", "Mis", "Mnu", "Qt")
        keys = [f"f{n}" for n in range(1, 11)]
        if cols >= 60:
            status = (f" {self.g['running']} running… " if self.runner.running
                      else f" LB · {time.strftime('%H:%M')} ")
            labels = full if cols >= 80 else short
            nums = [str(n) for n in range(1, 10)] + (["10"] if cols >= 80 else ["0"])
            slot = max(4, (cols - text_width(status)) // 10)
            line: Line = []
            x = 0
            for num, label, key in zip(nums, labels, keys, strict=True):
                self.hits.append((y, x, x + slot, key))
                line += [("key_num", num), ("key_label", fit(label, slot - len(num)))]
                x += slot
            gap = cols - x - text_width(status)
            line += [("key_num", " " * max(0, gap)), ("run" if self.runner.running
                                                     else "key_num", status)]
            return [pad_line(line, cols, "key_num")]
        slot = cols // 5
        out = []
        for r in range(2):
            line = []
            for i in range(5):
                n = r * 5 + i
                num = str((n + 1) % 10)
                self.hits.append((y + r, i * slot, (i + 1) * slot, keys[n]))
                line += [("key_num", num), ("key_label", fit(short[n], slot - 1))]
            out.append(pad_line(line, cols, "key_num"))
        return out


# --------------------------------------------------------------------------- terminal

def load_scheme() -> str:
    """The scheme shared with the other NC tools (nc_scheme in the systools config)."""
    try:
        for line in CONFIG_PATH.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "nc_scheme" and value.strip() in SCHEMES:
                return value.strip()
    except OSError:
        pass
    return "nc"


def save_scheme(name: str) -> None:
    """Persist the scheme in the shared config file, keeping its other keys."""
    conf: dict[str, str] = {}
    try:
        for line in CONFIG_PATH.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip():
                conf[key.strip()] = value.strip()
    except OSError:
        pass
    conf["nc_scheme"] = name
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text("".join(f"{k}={v}\n" for k, v in sorted(conf.items())))
    except OSError as exc:
        log.warning("scheme not saved: %s", exc)


class Term:
    """Terminal capabilities plus raw mode, alt screen and mouse, always restored."""

    def __init__(self, mouse: bool = True) -> None:
        self.fd = sys.stdin.fileno()
        self.mouse = mouse
        self.saved: list | None = None
        self.colors = self._colors()

    @staticmethod
    def _colors() -> int:
        try:
            out = subprocess.run(["tput", "colors"], capture_output=True, text=True, timeout=2)
            return int(out.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.SubprocessError):
            return 8

    def enter(self) -> None:
        """Raw-ish mode, alternate screen, hidden cursor, mouse reporting."""
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] &= ~termios.IXON                 # Ctrl-S must reach us
        attrs[3] &= ~termios.IEXTEN               # and Ctrl-O / Ctrl-V
        termios.tcsetattr(self.fd, termios.TCSADRAIN, attrs)
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J" + ("\x1b[?1000;1006h" if self.mouse else ""))

    def leave(self) -> None:
        """Undo enter()."""
        self.write(("\x1b[?1000;1006l" if self.mouse else "") + "\x1b[0m\x1b[?25h\x1b[?1049l")
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
            self.saved = None

    @staticmethod
    def write(text: str) -> None:
        """Write and flush."""
        sys.stdout.write(text)
        sys.stdout.flush()

    @staticmethod
    def size() -> tuple[int, int]:
        """(columns, rows)."""
        size = shutil.get_terminal_size((80, 24))
        return size.columns, size.lines


class Keys:
    """Reads stdin with select() and decodes it."""

    def __init__(self, fd: int) -> None:
        self.fd = fd

    def read(self, timeout: float) -> list[str]:
        """Keys that arrived within timeout."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return []
        data = os.read(self.fd, 4096)
        if data == b"\x1b":                         # a lone Esc, or the start of a sequence
            more, _, _ = select.select([self.fd], [], [], 0.03)
            if more:
                data += os.read(self.fd, 4096)
        return decode(data)


class Screen:
    """Keeps the last frame and redraws only the rows that changed."""

    def __init__(self) -> None:
        self.last: list[str] = []

    def draw(self, rows: list[str], force: bool = False) -> str:
        """The escape string that brings the terminal from the last frame to this one."""
        out = []
        for y, row in enumerate(rows):
            if force or y >= len(self.last) or self.last[y] != row:
                out.append(f"\x1b[{y + 1};1H{row}")
        self.last = list(rows)
        return "".join(out)


def main_loop(app: App, term: Term) -> None:
    """Read keys, tick, redraw. The caller restores the terminal."""
    keys = Keys(term.fd)
    screen = Screen()
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    while not app.quit:
        force = False
        if resized[0]:
            resized[0], force = False, True
            term.write("\x1b[0m\x1b[2J")
        cols, rows = term.size()
        if app.dirty or force or app.loading or app.runner.running:
            scheme = SCHEMES["mono" if term.colors < 16 else app.scheme]
            painted = [paint(line, scheme) for line in app.frame(cols, rows)]
            term.write(screen.draw(painted, force))
            app.dirty = False
        try:
            for key in keys.read(TICK):
                app.handle(key)
        except KeyboardInterrupt:
            app.quit = True
        app.tick()


# ---------------------------------------------------------------------------- preview

class FakeApi(Api):
    """An in-memory backend over a synthetic tree, for --preview and the tests.

    Implements the handful of routes lb_nc calls; file/start really renames inside the
    fixture tree so a test can watch a misfiled folder become canonical.
    """

    def __init__(self, mounts: list[dict], routes: list[dict], rows: list[dict]) -> None:
        super().__init__("fake://")
        self.mounts, self.routes_rows, self.rows = mounts, routes, rows
        self.status: dict = {"running": False}
        self.calls: list[tuple[str, dict | None]] = []

    def _route(self, year: int) -> dict | None:
        return next((r for r in self.routes_rows if r["year"] == year), None)

    def _resolve(self, item: dict) -> dict:
        row = next((r for r in self.rows if r["lb_number"] == item["lb_number"]), None)
        year = Collection.year_of(row) if row else None
        if year is None:
            m = YEAR_RE.match(Path(item["path"]).name)
            year = int(m.group(1)) if m else None
        route = self._route(year) if year else None
        if route is None:
            return {"ok": False, "error_code": "no_route", "error": f"no route for {year}"}
        mount = next(m for m in self.mounts
                     if m["id"] == item.get("mount_id", route["mount_id"]))
        dest = Path(mount["root_path"]) / route["sub_path"] / Path(item["path"]).name
        if dest.exists():
            return {"ok": False, "error_code": "dest_exists", "error": f"exists: {dest}"}
        return {"ok": True, "dest": str(dest), "mount_label": mount["label"]}

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        self.calls.append((path, body))
        if path == "/api/collection/mounts":
            return {"mounts": [dict(m, online=True, free="1.0T") for m in self.mounts]}
        if path == "/api/collection/routes":
            out = []
            for r in self.routes_rows:
                m = next(x for x in self.mounts if x["id"] == r["mount_id"])
                out.append(dict(r, mount_label=m["label"], root_path=m["root_path"]))
            return {"routes": out}
        if path == "/api/collection" and method == "GET":
            return [dict(r) for r in self.rows]
        if path == "/api/pipeline/file/preview":
            return {"results": [self._resolve(i) for i in body["folders"]]}
        if path == "/api/pipeline/file/start":
            item = body["folders"][0]
            res = self._resolve(item)
            if not res["ok"]:
                return res
            dest = Path(res["dest"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.rename(item["path"], dest)
            row = next((r for r in self.rows if r["lb_number"] == item["lb_number"]), None)
            if row:
                row["disk_path"] = str(dest)
            else:
                self.rows.append({"lb_number": item["lb_number"], "folder_name": dest.name,
                                  "disk_path": str(dest), "date_str": dest.name[:10]})
            self.status = {"running": False, "stage": "done", "result": {
                "ok": True, "dest": str(dest), "file_mode": body.get("file_mode") or "move"}}
            return {"ok": True}
        if path == "/api/pipeline/file/status":
            return self.status
        if path == "/api/collection" and method == "POST":
            self.rows.append({"lb_number": body["lb_number"], "folder_name": body["folder_name"],
                              "disk_path": body["disk_path"],
                              "date_str": body["folder_name"][:10]})
            return {"ok": True, "added": True}
        if path == "/api/collection/routes/bulk":
            for year in range(body["year_from"], body["year_to"] + 1):
                self.routes_rows = [r for r in self.routes_rows if r["year"] != year]
                self.routes_rows.append({"year": year, "mount_id": body["mount_id"],
                                         "sub_path": body["sub_path"]})
            return {"ok": True}
        return {"error": f"FakeApi: no route {path}"}


def build_fixture(base: Path) -> FakeApi:
    """Two mounts covering every glyph, and a FakeApi serving them."""
    one, two = base / "DYLAN1", base / "DYLAN2"
    mounts = [{"id": 1, "label": "DYLAN1", "root_path": str(one)},
              {"id": 2, "label": "DYLAN2", "root_path": str(two)}]
    routes = [{"year": y, "mount_id": 1, "sub_path": ""} for y in range(1961, 1980)]
    routes += [{"year": y, "mount_id": 2, "sub_path": str(y)} for y in range(1980, 2026)]
    rows: list[dict] = []

    def folder(parent: Path, name: str, lb: int | None, registered: bool = True) -> None:
        (parent / name).mkdir(parents=True, exist_ok=True)
        (parent / name / "d1t01.flac").write_bytes(b"\0" * 1024)
        if lb is not None and registered:
            rows.append({"lb_number": lb, "folder_name": name,
                         "disk_path": str(parent / name), "date_str": name[:10],
                         "location": name[11:].split(" (")[0]})

    folder(one, "1966-05-17 Manchester, England (LB-00123)", 123)
    folder(one, "1975-11-19 Toronto, Canada (LB-04410)", 4410)
    folder(one, "1987-10-17 London, England (LB-01860)", 1860)             # misfiled
    folder(one, "1995-03-01 Prague, Czech Republic (LB-05555)", 5555, False)  # stray
    folder(two / "1987", "1987-09-05 Tel Aviv, Israel (LB-02311)", 2311)
    folder(two / "1987", "1987-10-05 Verona, Italy (LB-07777)", 7777, False)   # stray
    folder(two / "1987", "1975-11-19 Toronto, Canada (LB-04410)-copy", None)
    (two / "1987" / "1975-11-19 Toronto (LB-04410) alt").mkdir()            # dup
    folder(two / "1998", "1998-06-24 Portsmouth, England (LB-09001)", 9001)
    (one / "notes.txt").write_text("mount notes\n")
    return FakeApi(mounts, routes, rows)


def preview(cols: int, rows: int, ascii_only: bool, scheme: str) -> int:
    """Paint each screen once against the synthetic tree, then exit."""
    with tempfile.TemporaryDirectory(prefix="lb_nc-") as tmp:
        api = build_fixture(Path(tmp))
        app = App(api, scheme=scheme, ascii_only=ascii_only, threaded=False,
                  size_cache=None, persist=False)

        def pick(pane: Pane, name: str) -> None:
            pane.cursor = [e.name for e in pane.visible()].index(name)
        app.set_dir(app.right, Path(tmp) / "DYLAN2" / "1987")
        pick(app.left, "1987-10-17 London, England (LB-01860)")
        screens: list[tuple[str, Callable[[], None]]] = [
            ("main", lambda: None),
            ("file", lambda: app.handle("f7")),
            ("move", lambda: (setattr(app, "dialog", None), app.handle("f6"))),
            ("misfiled", lambda: (setattr(app, "dialog", None), app.handle("f8"))),
            ("help", lambda: app.handle("f1")),
        ]
        sch = SCHEMES[scheme]
        out = sys.stdout
        for title, step in screens:
            step()
            out.write(f"\x1b[0m--- {title} ({cols}x{rows}) ---\n")
            for line in app.frame(cols, rows):
                out.write(paint(line, sch) + "\n")
    return 0


# ------------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    """Parse flags, then run the UI (or --preview)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", type=Path, help="left pane start (default: first mount)")
    parser.add_argument("--right", type=Path, help="right pane start (default: second mount)")
    parser.add_argument("--api", default=API_URL, help=f"backend URL (default {API_URL})")
    parser.add_argument("--read-only", action="store_true",
                        help="browse, info, view; every write gated off")
    parser.add_argument("--scheme", choices=SCHEME_NAMES)
    parser.add_argument("--ascii", action="store_true", help="ASCII glyphs and borders")
    parser.add_argument("--no-mouse", action="store_true")
    parser.add_argument("--preview", action="store_true",
                        help="paint each screen once over a synthetic tree, then exit")
    parser.add_argument("--columns", type=int, help="forced width for --preview")
    parser.add_argument("--rows", type=int, help="forced height for --preview")
    args = parser.parse_args(argv)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    utf8 = "utf" in (locale.getpreferredencoding(False) or "").lower()
    ascii_only = args.ascii or not utf8
    scheme = args.scheme or load_scheme()

    if args.preview:
        cols, rows = shutil.get_terminal_size((100, 30))
        return preview(args.columns or cols, args.rows or rows, ascii_only, scheme)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write("lb_nc needs a terminal (try --preview)\n")
        return 2
    for label, path in (("left", args.left), ("right", args.right)):
        if path is not None and not path.is_dir():
            sys.stderr.write(f"not a directory ({label}): {path}\n")
            return 2

    log.info("start api=%s left=%s right=%s read_only=%s",
             args.api, args.left, args.right, args.read_only)
    term = Term(mouse=not args.no_mouse)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    term.enter()
    app = None
    try:
        term.write("\x1b[1;1H\x1b[0mlb_nc: reading the collection and mounts…")
        app = App(Api(args.api), args.left, args.right, read_only=args.read_only,
                  scheme=scheme, ascii_only=ascii_only)
        main_loop(app, term)
    except KeyboardInterrupt:
        pass
    finally:
        term.leave()
        if app:
            app.sizes.save()
    if app is None:
        return 130
    if app.runner.running and app.runner.job:
        sys.stdout.write(f"{app.runner.job.label} is still running in the backend; "
                         f"queued jobs behind it were dropped. Log: {LOG_PATH}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
