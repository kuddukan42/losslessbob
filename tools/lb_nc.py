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
import itertools
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from backend.folder_naming import (  # noqa: E402 — the repo's own NFT rules, one source
    apply_nft_suffix,
    build_standard_name,
    has_nft_suffix,
    nft_discrepancy,
    strip_nft_suffix,
)

LOG_PATH = REPO / "data" / "logs" / "lb_nc.log"
JOURNAL_PATH = REPO / "data" / "lb_nc_undo.jsonl"
QUEUE_PATH = REPO / "data" / "lb_nc_queue.json"     # the live queue, resumed after a restart
SIZE_CACHE = Path.home() / ".cache" / "lb_nc" / "sizes.json"
CONFIG_PATH = Path.home() / ".config" / "systools" / "config"
API_URL = "http://127.0.0.1:5174"
MIN_COLUMNS = 30
MIN_ROWS = 10
TICK = 0.25
LOG_ROWS = 8
POLL = 0.5
SPACE_RESERVE = 2 * 1024 ** 3        # bytes a cross-drive move must leave free on the target
PROBE_INTERVAL = 1.0                 # seconds between live LB-page checks (be polite to the site)
PLAN_HEADROOM = (0.02, 0.01, 0.005, 0.0)   # route planner: free share per drive, first that fits
SCHEME_NAMES = ("nc", "amber", "green", "mono")
PIPELINE_STEPS = ["verify", "lookup", "lbdir", "rename", "file"]
CHECKSUM_SUFFIXES = (".ffp", ".md5", ".st5")
VIEW_SUFFIXES = (".txt", ".md5", ".ffp", ".st5", ".sha256", ".nfo", ".log", ".cue")
LB_RE = re.compile(r"LB-(\d{1,6})", re.IGNORECASE)
YEAR_RE = re.compile(r"^(\d{4})")
IN_PLACE = "at its routed location, not in collection"
PRIVATE_DIR = "PRIVATE LB"          # a folder named this holds private LBs, outside the routes
PRIVATE_AREA = "in the private area"
OFF = ("misfiled", "public", "stray", "dup", "blocked", "gone", "relink")   # not in the right spot
SHOW_MODES = ("all", "off", "public", "nft", "name", "bad")
SHOW_LABELS = {"off": "not right", "public": "public in private", "nft": "NFT mismatch",
               "name": "non-canonical names", "bad": "integrity issues"}
RELOAD_EVERY = 5.0                  # seconds between pane refreshes while a queue runs
# jobs whose result opens a dialog when the queue ends — never queued behind a running one
FOLLOW_UP = ("pipeline", "compare", "measure", "measure-routes")
DUP_DIR = "_duplicates"             # where the resolver sets a losing copy aside (same drive)

log = logging.getLogger("lb_nc")

# -------------------------------------------------------------------- glyphs, palette

GLYPHS = {"canonical": "✓", "misfiled": "→", "public": "↑", "gone": "✗", "relink": "⇄",
          "stray": "?", "dup": "≠", "blocked": "⊘",
          "dest": "⇒", "cursor": "▶", "ellipsis": "…", "running": "■",
          "bar_on": "█", "bar_off": "░"}
ASCII_GLYPHS = {"canonical": "*", "misfiled": ">", "public": "^", "gone": "X", "relink": "~",
                "stray": "?", "dup": "=", "blocked": "x",
                "dest": "=>", "cursor": ">", "ellipsis": "~", "running": "*",
                "bar_on": "#", "bar_off": "."}
STATUS_TEXT = {"canonical": "canonical", "misfiled": "MISFILED",
               "public": "PUBLIC LB in the private folder",
               "gone": "GONE — the collection path is not on disk",
               "relink": "collection copy is gone — l relinks the record here",
               "stray": "not in collection", "dup": "DUPLICATE", "blocked": "blocked"}
BOX = {"h": "─", "v": "│", "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
       "tt": "┬", "bt": "┴", "lt": "├", "rt": "┤"}
ASCII_BOX = {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+",
             "tt": "+", "bt": "+", "lt": "+", "rt": "+"}

# role -> SGR parameters. nc is 16-colour only, for authenticity.
SCHEMES: dict[str, dict[str, str]] = {
    "nc": {"pane": "44;37", "text": "44;97", "frame": "44;96", "header": "46;30;1",
           "cursor": "46;30", "tag": "44;93;1", "cursor_tag": "46;93;1", "dim": "44;36",
           "key_num": "40;97", "key_label": "46;30", "dialog": "47;30",
           "dialog_hi": "40;97", "danger": "41;97;1", "run": "40;93;1", "ghost": "44;96;4",
           "odd": "44;95;1"},
    "amber": {"pane": "40;33", "text": "40;93", "frame": "40;33", "header": "40;93;1",
              "cursor": "43;30", "tag": "40;97;1", "cursor_tag": "43;97;1", "dim": "40;33",
              "key_num": "40;93", "key_label": "43;30", "dialog": "43;30",
              "dialog_hi": "40;93", "danger": "41;97;1", "run": "40;97;1", "ghost": "40;93;4",
              "odd": "40;91;1"},
    "green": {"pane": "40;32", "text": "40;92", "frame": "40;32", "header": "40;92;1",
              "cursor": "42;30", "tag": "40;97;1", "cursor_tag": "42;97;1", "dim": "40;32",
              "key_num": "40;92", "key_label": "42;30", "dialog": "42;30",
              "dialog_hi": "40;92", "danger": "41;97;1", "run": "40;97;1", "ghost": "40;92;4",
              "odd": "40;93;1"},
    "mono": {"pane": "0", "text": "0", "frame": "0", "header": "1", "cursor": "7",
             "tag": "1", "cursor_tag": "7;1", "dim": "0", "key_num": "1", "key_label": "7",
             "dialog": "7", "dialog_hi": "0", "danger": "7;1", "run": "1", "ghost": "4",
             "odd": "3"},
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


def wrap(text: str, width: int) -> list[str]:
    """Word-wrap to rows of exactly `width` cells; continuation rows keep the indent."""
    text = printable(text)
    if width <= 0 or text_width(text) <= width:
        return [fit(text, width)]
    indent = text[:len(text) - len(text.lstrip(" "))]
    if len(indent) > width // 2:
        indent = ""
    rows, cur = [], indent
    for word in text.split():
        sep = " " if cur.strip() else ""
        if text_width(cur + sep + word) <= width:
            cur += sep + word
            continue
        if cur.strip():
            rows.append(cur)
            cur = indent
        while text_width(cur + word) > width:      # longer than a row: break it
            head = ""
            for ch in word:
                if text_width(cur + head + ch) > width:
                    break
                head += ch
            head = head or word[0]
            rows.append(cur + head)
            word, cur = word[len(head):], indent
        cur += word
    if cur.strip():
        rows.append(cur)
    return [fit(r, width) for r in rows]


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


def existing(path: str | Path) -> Path:
    """The path, or its nearest ancestor that exists (a destination not made yet)."""
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def same_device(a: Path, b: Path) -> bool:
    """True when both paths are on one filesystem (a move is then a rename)."""
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


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

    def patch(self, path: str, body: dict) -> Any:
        """PATCH a JSON body to an endpoint."""
        return self._call("PATCH", path, body)

    def delete(self, path: str) -> Any:
        """DELETE an endpoint."""
        return self._call("DELETE", path)


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
    gone: set[str] = field(default_factory=set)            # normed disk_paths not on disk
    integrity: dict[int, dict] = field(default_factory=dict)   # lb -> integrity status row

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
        # M/D/YY → YYYY-MM-DD, the backend's own parser
        from backend.torrent_maker import _parse_date

        m = YEAR_RE.match(_parse_date(row.get("date_str") or ""))
        return int(m.group(1)) if m else None

    @staticmethod
    def in_private(path: str | Path) -> bool:
        """True when the folder sits anywhere under a PRIVATE_DIR folder."""
        return PRIVATE_DIR in Path(path).parent.parts

    def row_status(self, row: dict) -> tuple[str, str]:
        """(status, note) for a collection row: canonical, misfiled, public or blocked.

        A private LB anywhere under PRIVATE_DIR is where it belongs. A public LB there
        has gone public since it was filed: status "public", destination its year route.
        Everything else must sit directly in its year route's folder.
        """
        if norm(row["disk_path"]) in self.gone:
            return "gone", ""
        year = self.year_of(row)
        if self.in_private(row["disk_path"]) and row.get("lb_status") != "public":
            return "canonical", PRIVATE_AREA
        if not year:
            return "blocked", "no show date — can't route"
        expected = self.expected_parent(year)
        if expected is None:
            return "blocked", f"no route for {year}"
        if self.in_private(row["disk_path"]):
            return "public", expected
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
            if norm(other.get("disk_path") or "") in self.gone:
                return "relink", other.get("disk_path") or "", other
            return "dup", other.get("disk_path") or "", other
        m = YEAR_RE.match(path.name)
        expected = self.expected_parent(int(m.group(1))) if m else None
        if expected is not None and norm(path.parent) == expected:
            return "stray", IN_PLACE, None
        return "stray", "not in collection", None

    def stale(self) -> list[dict]:
        """Rows whose disk_path is no longer on disk (after the gone check ran)."""
        return [r for r in self.rows if r.get("disk_path") and norm(r["disk_path"]) in self.gone]

    def misfiled(self) -> list[dict]:
        """Rows to refile: misfiled, or public LBs sitting in the private area."""
        return [r for r in self.rows
                if r.get("disk_path") and self.row_status(r)[0] in ("misfiled", "public")]


@dataclass
class Entry:
    """One row in a pane."""

    name: str
    path: Path
    kind: str                      # parent | dir | file | ghost (a previewed destination)
    status: str = ""               # a GLYPHS status key, LB folders only
    note: str = ""                 # expected parent, the other copy, or a reason
    row: dict | None = None
    lb: int | None = None
    nft: str = ""                  # "missing" (private, no -NFT) | "stale" (public, has -NFT)
    health: str = ""               # integrity status when it isn't "pass"
    canon: str = ""                # the canonical folder name, when this one differs

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
                annotate(entry, coll)
        rows.append(entry)
    return rows


def annotate(entry: Entry, coll: Collection) -> None:
    """NFT and integrity flags for a folder that is the collection's copy of its LB."""
    row = entry.row
    if not row or norm(row.get("disk_path") or "") != norm(entry.path):
        return
    nft = nft_discrepancy(entry.name, row.get("lb_status"))
    entry.nft = nft if nft in ("missing", "stale") else ""
    entry.canon = canonical_name(entry.name, row)
    health = coll.integrity.get(int(row["lb_number"]))
    if health and health.get("status") not in (None, "pass") \
            and norm(health.get("disk_path") or "") == norm(entry.path):
        entry.health = str(health["status"])


def canonical_name(name: str, row: dict) -> str:
    """The pipeline's canonical name for a collection folder, or "" when name already is it.

    Built by backend.folder_naming.build_standard_name — the rename step's own rule.
    Multi-LB folders and entries without both a date and a location aren't judged
    (the pipeline needs extra sources for those).
    """
    location = (row.get("location") or "").strip()
    if "+LB-" in name.upper() or not row.get("date_str") or not location:
        return ""
    want = build_standard_name(int(row["lb_number"]), row["date_str"], location,
                               row.get("lb_status"), int(row.get("xref") or 0))
    return "" if want == name or "/" in want else want


VIEWS = {"misfiled": "MISFILED — all mounts", "gone": "GONE — collection paths not on disk"}


def list_view(coll: Collection | None, view: str) -> list[Entry]:
    """A virtual pane: every misfiled (or gone) collection folder, wherever it is."""
    if coll is None:
        return []
    out = []
    for row in (coll.stale() if view == "gone" else coll.misfiled()):
        path = Path(row["disk_path"])
        status, note = coll.row_status(row)
        entry = Entry(path.name, path, "dir", status, note, row, int(row["lb_number"]))
        annotate(entry, coll)
        out.append(entry)
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
        self.show = "all"                # a SHOW_MODES value
        self.view = "misfiled"           # which virtual list, when root is None

    @property
    def virtual(self) -> bool:
        """True for the misfiled view."""
        return self.root is None

    def visible(self) -> list[Entry]:
        """Entries after the show mode and the text filter; `..` always stays."""
        rows = self.entries
        fixed = ("parent", "ghost")
        if self.show == "off":
            rows = [e for e in rows if e.kind in fixed or e.status in OFF]
        elif self.show == "public":
            rows = [e for e in rows if e.kind in fixed or e.status == "public"]
        elif self.show == "nft":
            rows = [e for e in rows if e.kind in fixed or e.nft]
        elif self.show == "name":
            rows = [e for e in rows if e.kind in fixed or e.canon]
        elif self.show == "bad":
            rows = [e for e in rows if e.kind in fixed or e.health]
        if not self.filter:
            return rows
        needle = self.filter.lower()
        return [e for e in rows if e.kind in fixed or needle in e.name.lower()]

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

    def get_now(self, path: Path) -> int:
        """The size, computed in this thread when not cached (for the space check)."""
        size = self.get(path) if not self.threaded else None
        if size is not None:
            return size
        with self.lock:
            hit = self.data.get(str(path))
        try:
            if hit and hit[0] == path.stat().st_mtime:
                return int(hit[1])
        except OSError:
            return 0
        self._compute(path)
        with self.lock:
            return int(self.data.get(str(path), [0, 0])[1])

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


class JobRefused(JobError):
    """A job declined to run (a safety gate said no); the queue carries on without it."""


def private_marked(name: str, path: Path, row: dict | None) -> bool:
    """True for a folder whose LB is private, whose name has -NFT, or that sits in PRIVATE_DIR."""
    return (row or {}).get("lb_status") == "private" or has_nft_suffix(name) \
        or Collection.in_private(path)


class PageGate:
    """Refuses a move unless the LB has a live page on the LB site right now.

    Applied to every folder move of a private-marked folder (see private_marked): the
    site is asked through the backend at move time, one LB at a time, at most one
    request per PROBE_INTERVAL. No page, or no answer, means no move.
    """

    def __init__(self, api: Api) -> None:
        self.api = api
        self.last = 0.0
        self.lock = threading.Lock()

    def check(self, lb: int | None, emit: Emit, want: bool = True) -> None:
        """Return when LB-lb's page exists (want=True) or is absent (want=False).

        Raise JobRefused otherwise, and always when the site doesn't answer.
        """
        if lb is None:
            raise JobRefused("no LB number — can't check the LB site, refused")
        with self.lock:
            wait = PROBE_INTERVAL - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            try:
                res = self.api.get(f"/api/lb_master/{lb}/live")
            finally:
                self.last = time.monotonic()
        exists = res.get("exists") if isinstance(res, dict) else None
        if exists is want:
            emit(f"  LB-{lb:05d}: " + ("page live on the LB site" if want
                                       else "no page on the LB site (private)"), False)
            return
        if exists is False:
            raise JobRefused(f"LB-{lb:05d} has no page on the LB site — refused")
        if exists is True:
            raise JobRefused(f"LB-{lb:05d} has a public page on the LB site, so it isn't "
                             "private — refused")
        why = (res or {}).get("error") or f"status {(res or {}).get('status')}"
        raise JobRefused(f"LB-{lb:05d}: LB site didn't answer ({why}) — refused")


class Journal:
    """Append-only undo log, one JSON record per line; an "undone" record retires one.

    With path None it lives in memory (tests, --preview).
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.mem: list[dict] = []

    def add(self, record: dict) -> None:
        """Append a record, stamped with an id and the local time."""
        record = {"id": str(time.time_ns()), "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                  **record}
        with self.lock:
            if self.path is None:
                self.mem.append(record)
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record) + "\n")
            except OSError as exc:
                log.warning("undo journal not written: %s", exc)

    def undoable(self, limit: int = 40) -> list[dict]:
        """Records not yet undone, newest first."""
        with self.lock:
            if self.path is None:
                records = list(self.mem)
            else:
                try:
                    records = [json.loads(line) for line in
                               self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
                except (OSError, ValueError):
                    records = []
        done = {r.get("undoes") for r in records if r.get("kind") == "undone"}
        return [r for r in reversed(records)
                if r.get("kind") != "undone" and r["id"] not in done][:limit]


def describe(rec: dict) -> str:
    """One line for an undo record."""
    kind = rec.get("kind", "?")
    if kind in ("move", "rename", "aside"):
        to = Path(rec["to"])
        return f"{kind} {Path(rec['from']).name} {GLYPHS['dest']} " + \
            (str(to.parent) if kind == "move" else to.name if kind == "rename" else str(to))
    if kind == "relink":
        return f"relink LB-{rec['lb']:05d} {GLYPHS['dest']} {rec['new_path']}"
    if kind == "drop":
        return f"drop record LB-{rec['row']['lb_number']:05d}"
    if kind == "register":
        return f"register LB-{rec['lb']:05d}"
    if kind == "route":
        return f"route {rec['year']} (was mount {rec.get('old_mount_id')})"
    if kind == "extras":
        return f"extras {len(rec['files'])} file(s) in {Path(rec['folder']).name}"
    return kind

Emit = Callable[[str, bool], None]    # (text, replace_last_progress_line)


@dataclass
class Job:
    """One unit of work against the backend: a label, what the gate shows, a callable."""

    label: str
    detail: str
    run: Callable[[Emit], None]
    gated: bool = True
    path: str | None = None        # the folder it acts on; a queued job claims it
    dest: str | None = None        # where a move lands, for the space check of later batches
    cross: bool = False            # the move copies across drives
    meter: list[int] = field(default_factory=lambda: [0, 0])   # [bytes done, bytes total]
    spec: dict | None = None       # how to rebuild it after a restart; None: never saved


def file_job(api: Api, entry: Entry, mount_id: int | None, file_mode: str | None,
             dest: str, journal: Journal | None = None,
             from_mount_id: int | None = None, gate: PageGate | None = None,
             adopt: bool = False) -> Job:
    """File (or move) one folder via /api/pipeline/file/start, polling to completion.

    A private-marked folder is only moved after gate confirms its LB page is live.
    With adopt the backend is already moving this folder (a queue resumed after a
    restart): nothing is started, the job only follows it to the end and journals it.
    """
    guarded = gate is not None and private_marked(entry.name, entry.path, entry.row)
    cross = not same_device(entry.path, existing(dest))
    registered = bool(entry.row) and norm(entry.row.get("disk_path") or "") == norm(entry.path)
    body_item: dict[str, Any] = {"path": str(entry.path), "lb_number": entry.lb}
    if mount_id is not None:
        body_item["mount_id"] = mount_id
    body: dict[str, Any] = {"folders": [body_item]}
    if file_mode:
        body["file_mode"] = file_mode

    meter = [0, 0]

    def run(emit: Emit) -> None:
        emit(f"LB-{entry.lb:05d} {entry.name}" + (" (already running)" if adopt else ""), False)
        if not adopt:
            if guarded:
                gate.check(entry.lb, emit)
            started = api.post("/api/pipeline/file/start", body)
            if not started.get("ok"):
                raise JobError(
                    f"{started.get('error_code') or 'error'}: {started.get('error')}")
        status: dict = {}
        while True:
            time.sleep(POLL)
            status = api.get("/api/pipeline/file/status")
            emit(f"  {status.get('stage', '?')} {status.get('files_done', 0)}/"
                 f"{status.get('files_total', 0)} files  "
                 f"{human(status.get('bytes_done'))}/{human(status.get('bytes_total'))}", True)
            meter[:] = [status.get("bytes_done") or 0, status.get("bytes_total") or 0]
            if not status.get("running"):
                break
        result = status.get("result") or {}
        if not result.get("ok"):
            raise JobError(f"{result.get('error_code') or 'error'}: {result.get('error')}")
        emit(f"  {result.get('file_mode', 'move')}d ⇒ {result.get('dest')}", True)
        if journal and result.get("file_mode", "move") == "move":
            journal.add({"kind": "move", "lb": entry.lb, "from": str(entry.path),
                         "to": result.get("dest"), "cross": cross,
                         "from_mount_id": from_mount_id, "registered": registered})
        if result.get("qbt_error"):
            emit(f"  qBittorrent: {result['qbt_error']}", False)
        elif result.get("qbt_synced"):
            emit("  qBittorrent location synced", False)

    verb = "move" if file_mode == "move" else "file"
    mark = "  [LB page checked first]" if guarded else ""
    return Job(f"{verb} LB-{entry.lb:05d}", f"{entry.name}  {GLYPHS['dest']} {dest}{mark}", run,
               path=norm(entry.path), dest=dest, cross=cross, meter=meter,
               spec={"kind": "file", "path": str(entry.path), "lb": entry.lb,
                     "mount_id": mount_id, "file_mode": file_mode, "dest": dest,
                     "from_mount_id": from_mount_id, "cross": cross,
                     "registered": registered})


def register_job(api: Api, entry: Entry, journal: Journal | None = None) -> Job:
    """Add a stray that already sits at its routed location to my_collection."""
    def run(emit: Emit) -> None:
        res = api.post("/api/collection", {"lb_number": entry.lb, "folder_name": entry.name,
                                           "disk_path": str(entry.path)})
        if not res.get("ok"):
            raise JobError(f"register LB-{entry.lb:05d}: {res.get('error')}")
        emit(f"registered LB-{entry.lb:05d} at {entry.path}"
             + ("" if res.get("added") else " (already present)"), False)
        if journal and res.get("added"):
            journal.add({"kind": "register", "lb": entry.lb})
    return Job(f"register LB-{entry.lb:05d}", f"{entry.name}  (register in place)", run,
               spec={"kind": "register", "path": str(entry.path), "lb": entry.lb})


def has_checksums(folder: Path) -> bool:
    """True when any .ffp/.md5/.st5 sits anywhere under the folder."""
    try:
        return any(p.suffix.lower() in CHECKSUM_SUFFIXES and p.is_file()
                   for p in folder.rglob("*"))
    except OSError:
        return False


def generate_job(api: Api, entry: Entry) -> Job:
    """Write _mychecksums.ffp/.md5 into one folder via /api/verify/generate."""
    def run(emit: Emit) -> None:
        emit(f"checksums {entry.name}", False)
        res = api.post("/api/verify/generate", {"folders": [str(entry.path)]})
        if "results" not in res:
            raise JobError(f"generate: {res.get('error')}")
        result = res["results"][0]
        for err in result.get("errors") or []:
            emit(f"  error: {err}", False)
        if not result.get("generated"):
            raise JobError(f"nothing generated for {entry.name}")
        emit("  wrote " + ", ".join(Path(g).name for g in result["generated"]), False)
    return Job("checksums", f"{entry.name}  (generate checksums)", run,
               path=norm(entry.path), spec={"kind": "checksums", "path": str(entry.path)})


def rename_job(api: Api, entry: Entry, new_name: str, journal: Journal | None = None,
               gate: PageGate | None = None) -> Job:
    """Rename one folder in place via /api/folder/rename (collection row + qBittorrent follow).

    A private-marked rename (old or new name) first checks the LB site: the new name
    must match reality — -NFT only when there's no page, no -NFT only when there is.
    """
    registered = bool(entry.row) and norm(entry.row.get("disk_path") or "") == norm(entry.path)
    guarded = gate is not None and (
        private_marked(entry.name, entry.path, entry.row)
        or private_marked(new_name, entry.path.parent / new_name, entry.row))

    def run(emit: Emit) -> None:
        if guarded:
            gate.check(entry.lb, emit, want=not has_nft_suffix(new_name))
        body: dict[str, Any] = {"folder": str(entry.path), "new_name": new_name}
        if entry.lb is not None:
            body["lb_number"] = entry.lb
        res = api.post("/api/folder/rename", body)
        if not res.get("ok"):
            raise JobError(f"rename {entry.name}: {res.get('error')}")
        emit(f"renamed {entry.name} {GLYPHS['dest']} {new_name}", False)
        if journal:
            journal.add({"kind": "rename", "lb": entry.lb, "from": str(entry.path),
                         "to": str(entry.path.parent / new_name), "registered": registered})
        if res.get("qbt_error"):
            emit(f"  qBittorrent: {res['qbt_error']}", False)
    mark = "  [LB page checked first]" if guarded else ""
    return Job("rename", f"{entry.name}  {GLYPHS['dest']} {new_name}{mark}", run,
               path=norm(entry.path),
               spec={"kind": "rename", "path": str(entry.path), "lb": entry.lb,
                     "new_name": new_name})


def route_job(api: Api, year: int, mount: dict, sub_path: str,
              journal: Journal | None = None, old: dict | None = None) -> Job:
    """Re-point one year's route at a mount, keeping its sub_path."""
    def run(emit: Emit) -> None:
        res = api.post("/api/collection/routes/bulk", {
            "year_from": year, "year_to": year, "mount_id": mount["id"], "sub_path": sub_path})
        if not res.get("ok"):
            raise JobError(f"route {year}: {res.get('error')}")
        emit(f"route {year} ⇒ {mount['label']}" + (f" /{sub_path}" if sub_path else ""), False)
        if journal:
            journal.add({"kind": "route", "year": year,
                         "old_mount_id": (old or {}).get("mount_id"),
                         "old_sub_path": (old or {}).get("sub_path") or "",
                         "new_mount_id": mount["id"]})
    return Job(f"route {year}", f"route {year} ⇒ {mount['label']}", run,
               spec={"kind": "route", "year": year, "mount_id": mount["id"],
                     "sub_path": sub_path})


def _ok(res: Any, what: str) -> None:
    """Raise JobError unless a route answered {ok: true}."""
    if not isinstance(res, dict) or not res.get("ok"):
        err = res.get("error") if isinstance(res, dict) else res
        raise JobError(f"{what}: {err}")


def _move_path(api: Api, src: str, dst: str, lb: int | None = None) -> None:
    """Move a path on one drive via /api/rename/apply (logged to rename_history)."""
    item: dict[str, Any] = {"old_path": src, "new_path": dst}
    if lb is not None:
        item["lb_number"] = lb
    res = api.post("/api/rename/apply", {"renames": [item]})
    if not isinstance(res, dict) or res.get("applied") != 1:
        errors = (res or {}).get("errors") or [str((res or {}).get("error"))]
        raise JobError(f"{Path(src).name}: {'; '.join(map(str, errors))}")


def _repoint(api: Api, lb: int, path: str) -> None:
    """Point a collection record at a folder path."""
    _ok(api.patch(f"/api/collection/{lb}", {"disk_path": path,
                                             "folder_name": Path(path).name}),
        f"repoint LB-{lb:05d}")


def relink_job(api: Api, lb: int, old_path: str, new_path: str,
               journal: Journal | None = None) -> Job:
    """Point a record whose folder is gone at a surviving copy."""
    def run(emit: Emit) -> None:
        _repoint(api, lb, new_path)
        emit(f"relinked LB-{lb:05d} {GLYPHS['dest']} {new_path}", False)
        if journal:
            journal.add({"kind": "relink", "lb": lb, "old_path": old_path,
                         "new_path": new_path})
    return Job("relink", f"LB-{lb:05d}  {GLYPHS['dest']} {new_path}", run)


def drop_job(api: Api, row: dict, journal: Journal | None = None) -> Job:
    """Delete a collection record whose folder is gone (nothing on disk is touched)."""
    lb = int(row["lb_number"])

    def run(emit: Emit) -> None:
        _ok(api.delete(f"/api/collection/{lb}"), f"drop LB-{lb:05d}")
        emit(f"dropped record LB-{lb:05d} ({row.get('disk_path')})", False)
        if journal:
            journal.add({"kind": "drop", "row": {k: row.get(k) for k in (
                "lb_number", "folder_name", "disk_path", "notes", "xref")}})
    return Job("drop", f"LB-{lb:05d}  {row.get('disk_path')}", run)


def aside_target(path: Path, root: Path) -> Path:
    """A free name for path under root/_duplicates/."""
    base = root / DUP_DIR / path.name
    dest, n = base, 2
    while dest.exists():
        dest = base.with_name(f"{path.name} ({n})")
        n += 1
    return dest


def aside_job(api: Api, path: Path, dest: Path, journal: Journal | None = None,
              gate: PageGate | None = None, row: dict | None = None) -> Job:
    """Set a losing duplicate aside on its own drive (a rename, never a delete)."""
    guarded = gate is not None and private_marked(path.name, path, row)

    def run(emit: Emit) -> None:
        if guarded:
            gate.check(lb_of(path.name), emit)
        _move_path(api, str(path), str(dest))
        emit(f"set aside {path.name} {GLYPHS['dest']} {dest.parent}", False)
        if journal:
            journal.add({"kind": "aside", "from": str(path), "to": str(dest)})
    return Job("aside", f"{path}  {GLYPHS['dest']} {dest.parent}/", run)


def extras_job(api: Api, folder: Path, files: list[str], journal: Journal | None = None) -> Job:
    """Move files the lbdir doesn't list into <folder>/extras/."""
    def run(emit: Emit) -> None:
        res = api.post("/api/lbdir/move_extras", {"folder": str(folder), "files": files})
        if "moved" not in res:
            raise JobError(f"extras {folder.name}: {res.get('error')}")
        emit(f"{folder.name}: {res['moved']} file(s) {GLYPHS['dest']} extras/", False)
        for err in res.get("errors") or []:
            emit(f"  {err.get('file')}: {err.get('error')}", False)
        moved = [f for f in files if (folder / "extras" / f).exists()]
        if journal and moved:
            journal.add({"kind": "extras", "folder": str(folder), "files": moved})
        if res.get("errors"):
            raise JobError(f"{len(res['errors'])} file(s) not moved in {folder.name}")
    return Job("extras", f"{folder.name}: {len(files)} extra file(s) {GLYPHS['dest']} extras/",
               run)


def integrity_job(api: Api, mount: dict | None) -> Job:
    """Run the backend integrity scan over one mount (or everything) and wait for it."""
    body = {"mount_id": mount["id"]} if mount else {}
    label = mount["label"] if mount else "whole collection"

    def run(emit: Emit) -> None:
        res = api.post("/api/collection/integrity/scan", body)
        _ok(res, "integrity scan")
        status: dict = {}
        while True:
            time.sleep(POLL)
            status = api.get("/api/collection/integrity/scan/status")
            emit(f"  integrity {label}: {status.get('folders_done', 0)}/"
                 f"{status.get('folders_total', 0)}", True)
            if not status.get("running"):
                break
        emit(f"integrity scan of {label} finished", False)
    return Job("integrity", f"integrity scan: {label}", run, gated=False)


def compare_job(api: Api, paths: list[Path], sink: list[dict]) -> Job:
    """Check each copy against its lbdir and measure it, for the duplicate resolver."""
    def run(emit: Emit) -> None:
        emit("comparing " + " vs ".join(p.name for p in paths), False)
        res = api.post("/api/lbdir/check", {"folders": [str(p) for p in paths]})
        if "results" not in res:
            raise JobError(f"lbdir check: {res.get('error')}")
        sink.clear()
        for path, result in zip(paths, res["results"], strict=True):
            files = sum(1 for f in path.rglob("*") if f.is_file()) if path.is_dir() else 0
            sink.append({**result, "path": str(path), "size": tree_size(path), "files": files})
    return Job("compare", "compare " + " vs ".join(str(p) for p in paths), run, gated=False)


def measure_job(sizes: SizeCache, paths: list[Path], label: str = "measure") -> Job:
    """Size every folder (cached by mtime) — the rebalance planner's input."""
    def run(emit: Emit) -> None:
        for i, path in enumerate(paths, 1):
            sizes.get_now(path)
            if i % 10 == 0 or i == len(paths):
                emit(f"  measured {i}/{len(paths)} folders", True)
        sizes.save()
    return Job(label, f"measure {len(paths)} folders", run, gated=False)


def undo_job(api: Api, rec: dict, journal: Journal, gate: PageGate | None = None) -> Job:
    """Reverse one journal record; moving a private-marked folder back is page-gated too."""
    kind = rec["kind"]

    def run(emit: Emit) -> None:
        if gate is not None and kind == "rename":
            back, here = Path(rec["from"]), Path(rec["to"])
            if private_marked(back.name, back, None) or private_marked(here.name, here, None):
                gate.check(rec.get("lb") or lb_of(back.name), emit,
                           want=not has_nft_suffix(back.name))
        if gate is not None and kind in ("move", "aside"):
            here = Path(rec["to"])
            if private_marked(here.name, here, None) or \
                    private_marked(Path(rec["from"]).name, Path(rec["from"]), None):
                gate.check(rec.get("lb") or lb_of(here.name), emit)
        if kind in ("rename", "aside"):
            _move_path(api, rec["to"], rec["from"], rec.get("lb") if kind == "rename" else None)
            if kind == "rename" and rec.get("registered") and rec.get("lb") is not None:
                _repoint(api, rec["lb"], rec["from"])
        elif kind == "move" and not rec.get("cross"):
            _move_path(api, rec["to"], rec["from"], rec["lb"])
            _repoint(api, rec["lb"], rec["from"])
        elif kind == "move":
            mount_id = rec.get("from_mount_id")
            res = api.post("/api/pipeline/file/preview", {"folders": [
                {"path": rec["to"], "lb_number": rec["lb"], "mount_id": mount_id}]}) \
                if mount_id is not None else {}
            dest = ((res.get("results") or [{}])[0]).get("dest")
            if not dest or norm(dest) != norm(rec["from"]):
                raise JobError(f"a cross-drive move only undoes back to a route folder; "
                               f"{rec['from']} isn't one — move it back by hand")
            entry = Entry(Path(rec["to"]).name, Path(rec["to"]), "dir", lb=rec["lb"])
            file_job(api, entry, mount_id, "move", dest).run(emit)
        elif kind == "register":
            _ok(api.delete(f"/api/collection/{rec['lb']}"), "unregister")
        elif kind == "relink":
            _repoint(api, rec["lb"], rec["old_path"])
        elif kind == "drop":
            _ok(api.post("/api/collection", rec["row"]), "re-add record")
        elif kind == "route":
            if rec.get("old_mount_id") is None:
                _ok(api.delete(f"/api/collection/routes/{rec['year']}"), "remove route")
            else:
                _ok(api.post("/api/collection/routes/bulk", {
                    "year_from": rec["year"], "year_to": rec["year"],
                    "mount_id": rec["old_mount_id"], "sub_path": rec.get("old_sub_path", "")}),
                    "restore route")
        elif kind == "extras":
            folder = Path(rec["folder"])
            for rel in rec["files"]:
                _move_path(api, str(folder / "extras" / rel), str(folder / rel))
        else:
            raise JobError(f"don't know how to undo {kind}")
        journal.add({"kind": "undone", "undoes": rec["id"]})
        emit(f"undone: {describe(rec)}", False)
    return Job("undo", f"undo {describe(rec)}", run)


@dataclass
class RoutePlan:
    """A suggested year → mount layout (see suggest_routes)."""

    order: tuple[str, ...]                 # mount labels, earliest years first
    ranges: dict[str, list[int]]           # label -> its years, contiguous
    moved: int                             # bytes that would change drive
    fill: dict[str, float]                 # label -> used fraction afterwards


def suggest_routes(where: dict[int, dict[str, int]], capacity: dict[str, int],
                   totals: dict[str, int], fixed: dict[str, int]) -> RoutePlan | None:
    """The contiguous year → mount layout that fits and moves the fewest bytes.

    Every mount order is tried; for each, a DP picks the cut points. Ties on bytes moved
    go to the layout whose fullest drive is least full.

    Args:
        where: year -> {mount label: bytes of that year's folders on that drive now}
            (label "" for folders on no mount's drive — they always move).
        capacity: label -> bytes that mount can take for routed years (total minus the
            unrouted data on it, minus SPACE_RESERVE).
        totals: label -> filesystem size, for the fill figures.
        fixed: label -> bytes on the drive that no route governs.

    Returns:
        The best RoutePlan, or None when no contiguous layout fits.
    """
    years = sorted(where)
    n = len(years)
    size = [sum(where[y].values()) for y in years]
    best: RoutePlan | None = None
    best_key: tuple[int, float] | None = None
    for order in itertools.permutations(capacity):
        # dp[i][j] = (moved, peak fill, cuts) for years[:j] on order[:i]
        inf = (float("inf"), float("inf"), ())
        dp = [[inf] * (n + 1) for _ in range(len(order) + 1)]
        dp[0][0] = (0, 0.0, ())
        for i, label in enumerate(order, 1):
            for j in range(n + 1):
                seg = 0
                stay = 0
                for t in range(j, -1, -1):          # segment years[t:j] on this mount
                    if t < j:
                        seg += size[t]
                        stay += where[years[t]].get(label, 0)
                    if seg > capacity[label]:
                        break
                    prev = dp[i - 1][t]
                    if prev[0] == float("inf"):
                        continue
                    fill = (fixed[label] + seg) / totals[label] if totals[label] else 1.0
                    cand = (prev[0] + seg - stay, max(prev[1], fill), (*prev[2], t))
                    if cand[:2] < dp[i][j][:2]:
                        dp[i][j] = cand
        moved, peak, cuts = dp[len(order)][n]
        if moved == float("inf"):
            continue
        key = (int(moved) // (1024 ** 3), peak)       # GB-level ties go to the balance
        if best_key is None or key < best_key:
            bounds = [*cuts[1:], n]
            ranges, fill, start = {}, {}, 0
            for label, end in zip(order, bounds, strict=True):
                ranges[label] = years[start:end]
                fill[label] = (fixed[label] + sum(size[start:end])) / totals[label] \
                    if totals[label] else 1.0
                start = end
            best, best_key = RoutePlan(order, ranges, int(moved), fill), key
    return best


def move_order(batches: dict[tuple[str, str], int], free: dict[str, int],
               ) -> tuple[list[tuple[str, str, int]], dict[tuple[str, str], int]]:
    """Order cross-drive batches so each step fits the target's free space at that point.

    Moving off a drive frees space there, so a full drive empties first. Batches are
    split when only part fits.

    Returns:
        (steps as (src, dst, bytes), whatever could not be scheduled).
    """
    left = {k: v for k, v in batches.items() if v > 0}
    free = dict(free)
    steps: list[tuple[str, str, int]] = []
    while left:
        progress = False
        # biggest room first, so the fullest drives get relief early
        for (src, dst), want in sorted(left.items(), key=lambda kv: -free.get(kv[0][1], 0)):
            room = free.get(dst, 0) - SPACE_RESERVE
            if room <= 0:
                continue
            chunk = min(want, room)
            steps.append((src, dst, chunk))
            free[dst] = free.get(dst, 0) - chunk
            free[src] = free.get(src, 0) + chunk
            left[(src, dst)] = want - chunk
            if not left[(src, dst)]:
                del left[(src, dst)]
            progress = True
            break
        if not progress:
            break
    merged: list[tuple[str, str, int]] = []
    for src, dst, chunk in steps:
        if merged and merged[-1][:2] == (src, dst):
            merged[-1] = (src, dst, merged[-1][2] + chunk)
        else:
            merged.append((src, dst, chunk))
    return merged, left


def plan_rebalance(year_bytes: dict[int, int], src: tuple[int, int], dst: tuple[int, int],
                   from_high: bool) -> tuple[list[tuple[int, int, float, float]], int]:
    """Whole-year moves from src to dst, cumulative, and the step that balances best.

    Args:
        year_bytes: bytes per routed year on the source mount.
        src: (free, total) of the source filesystem.
        dst: (free, total) of the target filesystem.
        from_high: take the latest years first (else the earliest).

    Returns:
        ([(year, cumulative bytes, src used % after, dst used % after), ...], chosen) where
        chosen is how many leading steps to take (0 = move nothing). Steps stop before the
        target would drop under SPACE_RESERVE free.
    """
    (sf, st), (df, dt) = src, dst

    def gap(moved: int) -> float:
        return abs((st - sf - moved) / st - (dt - df + moved) / dt)
    steps: list[tuple[int, int, float, float]] = []
    cum = 0
    for year in sorted(year_bytes, reverse=from_high):
        cum += year_bytes[year]
        if df - cum < SPACE_RESERVE:
            break
        steps.append((year, cum, (st - sf - cum) / st * 100, (dt - df + cum) / dt * 100))
    best, chosen = gap(0), 0
    for i, (_y, moved, _a, _b) in enumerate(steps, 1):
        if gap(moved) < best:
            best, chosen = gap(moved), i
    return steps, chosen


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


class QueueStore:
    """The live queue on disk, so a restart picks it up. With path None nothing is saved.

    The file holds the batches as job specs (Job.spec) plus the pid that wrote it; it is
    rewritten on every queue change and removed when the queue empties.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = threading.Lock()

    def save(self, batches: list[list[dict]]) -> None:
        """Replace the file with these batches; no batches removes it."""
        if self.path is None:
            return
        with self.lock:
            try:
                if not batches:
                    self.path.unlink(missing_ok=True)
                    return
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_name(self.path.name + ".tmp")
                tmp.write_text(json.dumps({
                    "pid": os.getpid(), "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "batches": batches}, indent=1), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError as exc:
                log.warning("queue not saved: %s", exc)

    def load(self) -> dict | None:
        """The saved queue, or None when there is none (or it can't be read)."""
        if self.path is None:
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        batches = data.get("batches") if isinstance(data, dict) else None
        if not isinstance(batches, list) or not any(batches):
            return None
        return data

    @staticmethod
    def owner_alive(data: dict) -> bool:
        """True when another running lb-nc wrote the file — its queue, not ours to resume."""
        pid = data.get("pid")
        if not isinstance(pid, int) or pid == os.getpid():
            return False
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return False
        return b"lb_nc" in cmdline or b"lb-nc" in cmdline


class Runner:
    """Runs jobs one at a time in a thread, batch after batch.

    A batch is what one confirm dialog submitted. A failure drops the rest of its own
    batch; batches submitted behind it while it ran still run. A filing job belongs to the
    backend once started, so quitting the UI never cuts a move in half — only the jobs
    still queued behind it are dropped.
    """

    def __init__(self, read_only: bool, threaded: bool = True) -> None:
        self.read_only = read_only
        self.threaded = threaded
        self.lines: deque[str] = deque(maxlen=400)
        self.thread: threading.Thread | None = None
        self.job: Job | None = None
        self.last: Job | None = None
        self.current: deque[Job] = deque()         # the rest of the batch being worked
        self.pending: deque[list[Job]] = deque()   # batches submitted behind it
        self.done = 0                              # jobs finished since the queue started
        self.total = 0                             # jobs submitted since the queue started
        self.ran: set[str] = set()                 # labels run since tick last looked
        self.failure: tuple[str, list[str]] | None = None
        self.refused: list[str] = []
        self.finished = False
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.on_change: Callable[[], None] | None = None   # the queue changed: save it
        self._active = False
        self._progress = False

    @property
    def running(self) -> bool:
        """True while a queue is being worked."""
        return self._active

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
        """Start a queue, or add a batch behind the one being worked. False when empty."""
        if not jobs:
            return False
        if self.read_only and any(j.gated for j in jobs):
            raise PermissionError("read-only mode")
        with self.lock:
            appended = self._active
            if appended:
                self.pending.append(list(jobs))
                self.total += len(jobs)
            else:
                self._active = True
                self.current = deque(jobs)
                self.done, self.total = 0, len(jobs)
                self.stop.clear()
        self._changed()
        if appended:
            return True
        if self.threaded:
            self.thread = threading.Thread(target=self._work, daemon=True)
            self.thread.start()
        else:
            self._work()
        return True

    def outstanding(self) -> list[Job]:
        """The running job and every job still queued behind it."""
        with self.lock:
            return ([self.job] if self.job else []) + list(self.current) \
                + [j for batch in self.pending for j in batch]

    def snapshot(self) -> list[list[dict]]:
        """The queue as saveable batches of job specs; the running job is marked."""
        with self.lock:
            first = ([self.job] if self.job else []) + list(self.current)
            out = []
            for batch in (first, *self.pending):
                specs = [dict(j.spec, running=True) if j is self.job else dict(j.spec)
                         for j in batch if j.spec]
                if specs:
                    out.append(specs)
            return out

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:                    # saving must never stop the queue
                log.exception("queue save failed")

    def progress(self) -> tuple[Job | None, int, int]:
        """(running job, jobs finished, jobs submitted) for the progress bar."""
        with self.lock:
            return self.job, self.done, self.total

    def _next(self) -> Job | None:
        """Take the next job, or close the queue when nothing is left."""
        with self.lock:
            dropped = 0
            if self.stop.is_set():
                dropped = len(self.current) + sum(len(b) for b in self.pending)
                self.current.clear()
                self.pending.clear()
                self.total -= dropped
            elif not self.current and self.pending:
                self.current = deque(self.pending.popleft())
            job = self.current.popleft() if self.current else None
            self.job = job
            if job is None:
                self.finished = True
                self._active = False
        if dropped:
            self.emit(f"stopped — {dropped} job(s) not run", False)
        self._changed()
        return job

    def _fail(self, job: Job, text: str) -> None:
        """Record a failure and drop the rest of that job's batch; later batches still run."""
        with self.lock:
            skipped = len(self.current)
            self.current.clear()
            self.total -= skipped
            waiting = sum(len(b) for b in self.pending)
        lines = [text]
        if skipped:
            lines.append(f"{skipped} queued job(s) of that batch not run")
        if waiting:
            lines.append(f"{waiting} job(s) queued behind it still run")
        with self.lock:
            if self.failure:
                self.failure[1].extend(lines)
            else:
                self.failure = (job.label, lines)
        self._changed()

    def _work(self) -> None:
        while (job := self._next()) is not None:
            log.info("run: %s", job.label)
            try:
                job.run(self.emit)
            except JobRefused as exc:
                self.emit(f"REFUSED {job.label}: {exc}", False)
                self.refused.append(f"{job.label}: {exc}")
            except (JobError, ApiError) as exc:
                self.emit(f"FAILED {job.label}: {exc}", False)
                self._fail(job, f"{job.label}: {exc}")
            except Exception as exc:             # a bug must not kill the UI
                log.exception("job crashed: %s", job.label)
                self._fail(job, f"{job.label}: {exc!r}")
            with self.lock:
                self.last = job
                self.done += 1
                self.ran.add(job.label)


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
    foot = 0                # trailing body rows that survive when the box overflows

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
        body, room = self.body(inner), max(1, rows - 4)
        if len(body) > room and 0 < self.foot < room:
            body = body[:room - self.foot] + body[-self.foot:]
        for row in body[:room]:
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
        return [[("dialog", row)] for t in [*self.text, "", "  any key closes"]
                for row in wrap(t, width)]

    def handle(self, app: App, key: str) -> None:
        app.dialog = None


class Confirm(Dialog):
    """The write gate. Shows what each job does; y runs, anything else cancels."""

    def __init__(self, title: str, jobs: list[Job], blurb: list[str],
                 toggle: tuple[str, str, Callable[[bool], list[Job]]] | None = None) -> None:
        self.title, self.jobs, self.blurb, self.toggle = title, jobs, blurb, toggle
        self.state = False

    foot = 2                # the y/n row must stay on screen

    def body(self, width: int) -> list[Line]:
        rows: list[Line] = []
        for job in self.jobs[:10]:
            rows.extend([("dialog_hi", row)] for row in wrap(job.detail, width))
        if len(self.jobs) > 10:
            rows.append([("dialog", f"  … and {len(self.jobs) - 10} more")])
        rows.append([("dialog", "")])
        rows.extend([("dialog", row)] for t in self.blurb for row in wrap(t, width))
        if self.toggle:
            mark = "x" if self.state else " "
            rows.extend([("dialog", row)] for row in wrap(
                f"  [{mark}] {self.toggle[1]}  ({self.toggle[0]} toggles)", width))
        rows.append([("dialog", "")])
        lead, gap = ("          ", "      ") if width >= 37 else ("  ", "  ")
        rows.append([("dialog", lead), ("danger", "[ y ] run"),
                     ("dialog", gap + "[ n ] cancel")])
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

    def __init__(self, title: str, items: list[tuple[str, Callable[[], None]]],
                 lines: list[str] | None = None) -> None:
        self.title, self.items, self.cursor, self.top = title, items, 0, 0
        self.lines = lines or []

    def body(self, width: int) -> list[Line]:
        height = 14
        self.top = max(0, min(self.cursor, max(self.top, self.cursor - height + 1)))
        rows: list[Line] = [[("dialog", row)] for t in self.lines for row in wrap(t, width)]
        if self.lines:
            rows.append([("dialog", "")])
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


class PlanView(Message):
    """A text report; a applies it (through the usual gate), Esc closes."""

    def __init__(self, title: str, text: list[str], apply: Callable[[], None] | None) -> None:
        super().__init__(title, text)
        self.apply = apply

    def body(self, width: int) -> list[Line]:
        tail = ["", "  [ a ] apply      [ Esc ] close" if self.apply else "  [ Esc ] close"]
        return [[("dialog", fit(t, width))] for t in [*self.text, *tail]]

    def handle(self, app: App, key: str) -> None:
        if key in ("a", "A") and self.apply:
            app.dialog = None
            self.apply()
        elif key in ("esc", "enter", "q", "n"):
            app.dialog = None


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
f           show: all → not in the right spot → public LBs in the private folder
            → -NFT mismatches → non-canonical names → integrity issues

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
9 Menu      drive picker, swap panes, checksums, renames, stop queue, cancel
            pipeline, re-route years
0/q Quit

c           generate checksums (folders with no .ffp/.md5/.st5)
r           rename to the canonical name (the last F4 proposal, else the collection
            row's date + location + LB tag); non-canonical names are highlighted
h           highlighting of non-canonical names on / off
p           destination preview on / off: while the left pane is active the right
            pane opens where the cursor folder would land and shows it there,
            mid-pane, as an underlined ⇒ row. An out-of-place folder goes where
            7 File puts it (its year's route, on whatever drive); one already in
            place goes where 6 Move puts it on the right pane's drive. A right
            pane holding tags stays put
            usual order for a new folder: c → 4 Pipe → r → 7 File
n           fix the -NFT suffix (private LBs have it, public ones don't)
e           move files the lbdir doesn't list into <folder>/extras/
=           duplicate resolver: compare a ≠ copy with the collection's, keep one,
            set the other aside in _duplicates/ on its own drive
x / l       gone records (d → Gone): x drops the record, l relinks it to the
            folder under the other pane's cursor (a ⇄ folder relinks in place)
i           integrity scan of this pane's drive; ! marks folders with issues
b           rebalance: size this pane's drive, plan whole-year moves to the
            other pane's drive, a applies (moves + re-routes, space-checked)
w           route suggestion: size every routed year, find the year → drive layout
            that fits and moves the least, list the refile order; a applies routes
z           undo: reverse any logged move, rename, relink, drop, route, extras

d           drive picker for this pane    u / Ctrl-U  swap panes
o / Ctrl-O  log pane                      s / Ctrl-S  size the cursor folder
t           cycle colour scheme

Glyphs: ✓ canonical  → misfiled (⇒ where it belongs)  ? stray, not in collection
        ↑ public LB still under the private folder (F7 files it to its year)
        ≠ duplicate — the collection holds this LB at another path  ⊘ blocked
        ✗ gone — the record's folder isn't on disk  ⇄ a copy of a gone record
Flags:  n -NFT suffix wrong  ! integrity issue   highlighted name: not canonical
A private LB anywhere under "PRIVATE LB" counts as canonical (--private-dir renames it).

Private LBs, -NFT folders and anything in the private folder are only moved after a
live check that the LB's page exists on the LB site — no page (or no answer): refused,
the rest of the queue carries on. Renames of such folders check that the new name
matches the site: -NFT only with no page, no -NFT only with a page.
Every write goes through the backend (port 5174) after a y/n gate, one folder at a
time, stopping at the first failure. Duplicates are never filed — resolve them by hand.
While a queue runs, more moves, files and renames can be confirmed: each batch is added
behind the running one (a folder already queued is skipped), and a failure only drops
the rest of its own batch. The bar above the keys shows the current folder's bytes and
the queue. F4, the duplicate resolver and the planners wait for the queue to end.
The queue is saved in data/lb_nc_queue.json: after a quit or a crash the next start
offers to resume it (moves, files, registers, renames, checksums and routes).
Pane headers show free space; the line under the panes shows every drive. F6/F7 add up
cross-drive bytes per target, moves already queued included, and refuse a batch that
would leave < 2G free."""


# -------------------------------------------------------------------------------- app

class App:
    """State, key handling and layout. No terminal I/O here, so tests can drive it."""

    def __init__(self, api: Api, left: Path | None = None, right: Path | None = None,
                 read_only: bool = False, scheme: str = "nc", ascii_only: bool = False,
                 threaded: bool = True, size_cache: Path | None = SIZE_CACHE,
                 persist: bool = True, journal_path: Path | None = JOURNAL_PATH,
                 queue_path: Path | None = None) -> None:
        self.api = api
        self.page_gate = PageGate(api)
        self.journal = Journal(journal_path)
        self.checking_gone = False
        self.compare_result: list[dict] = []
        self.compare_ctx: tuple[Entry, dict] | None = None
        self.plan_ctx: tuple[dict, dict, list[dict]] | None = None
        self.read_only = read_only
        self.scheme = scheme if scheme in SCHEMES else "nc"
        self.ascii = ascii_only
        self.g = ASCII_GLYPHS if ascii_only else GLYPHS
        self.box = ASCII_BOX if ascii_only else BOX
        self.threaded = threaded
        self.persist = persist
        self.dialog: Dialog | None = None
        self.show_log = False
        self.highlight = True            # h: colour non-canonical folder names
        self.follow = True               # p: the right pane previews the left cursor's destination
        self.quit = False
        self.coll: Collection | None = None
        self.coll_error = ""
        self.loading = False
        self.sizes = SizeCache(size_cache, threaded)
        self.runner = Runner(read_only, threaded)
        self.queue = QueueStore(None if read_only else queue_path)
        self.saved: dict | None = None       # a queue left by the last session, undecided
        self.runner.on_change = self.save_queue
        self.pipeline_results: dict[str, dict] = {}
        self.hits: list[tuple[int, int, int, str]] = []     # (row, x0, x1, key)
        self.pane_rows: dict[str, tuple[int, int, int, int]] = {}
        self.pane_height = 0             # rows in a pane body at the last layout
        self.lock = threading.Lock()
        self.dirty = True
        self._free_cache: dict[str, tuple[float, str]] = {}
        self._reloaded: tuple[int, float] = (0, 0.0)   # (runner.done, when) of the last refresh
        self.flash = ("", 0.0)
        self._load()
        mounts = [Path(m["root_path"]) for m in (self.coll.mounts if self.coll else [])]
        start_left = left or (mounts[0] if mounts else Path.cwd())
        start_right = right or (mounts[1] if len(mounts) > 1 else start_left)
        self.left = Pane(start_left, self.label_for(start_left))
        self.right = Pane(start_right, self.label_for(start_right))
        self.active = self.left
        self.relist()
        self.check_gone()
        self.saved = self.queue.load()
        if self.saved and QueueStore.owner_alive(self.saved):
            self.saved, self.queue = None, QueueStore(None)
            self.say("another lb-nc is running a queue — this session's queue is not saved")
        elif self.saved:
            self.resume_dialog()

    # ---- data

    def _load(self) -> None:
        try:
            coll = Collection.load(self.api)
            error = ""
        except ApiError as exc:
            coll, error = None, str(exc)
            log.warning("collection load failed: %s", exc)
        if coll is not None:
            try:
                res = self.api.get("/api/collection/integrity/status")
                coll.integrity = {int(r["lb_number"]): r for r in res.get("status") or []}
            except (ApiError, AttributeError, KeyError, TypeError, ValueError) as exc:
                log.warning("integrity status not loaded: %s", exc)
        with self.lock:
            if coll is not None and self.coll is not None:
                coll.gone = self.coll.gone          # until check_gone re-runs
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
                self.check_gone()
            threading.Thread(target=work, daemon=True).start()
        else:
            self._load()
            self.relist()
            self.check_gone()

    def check_gone(self) -> None:
        """Stat every collection path (in a thread when threaded); gone ones get ✗."""
        coll = self.coll
        if coll is None or self.checking_gone:
            return
        self.checking_gone = True

        def work() -> None:
            gone = {norm(r["disk_path"]) for r in coll.rows
                    if r.get("disk_path") and not os.path.isdir(r["disk_path"])}
            with self.lock:
                coll.gone = gone
                self.checking_gone = False
                self.relist()
        if self.threaded:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()

    def label_for(self, path: Path | None) -> str:
        """The mount label a path sits on, or its basename."""
        if path is None:
            return "virtual"
        mount = self.coll.mount_for(path) if self.coll else None
        return mount["label"] if mount else (path.name or str(path))

    def relist(self) -> None:
        """Relist both panes, keeping the cursor on the same name where it survives."""
        for pane in (self.left, self.right):
            keep = pane.current().key if pane.current() else ""
            if pane.virtual:
                pane.entries = list_view(self.coll, pane.view)
            else:
                pane.entries = list_dir(pane.root, pane.cwd, self.coll)
            keys = [e.key for e in pane.visible()]
            pane.tags &= {e.key for e in pane.entries}
            pane.cursor = keys.index(keep) if keep in keys else min(pane.cursor, len(keys) - 1)
            pane.move(0)
        self.sync_preview()
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

    def set_root(self, pane: Pane, root: Path | None, view: str = "misfiled") -> None:
        """Re-root a pane at a mount, a directory, or (None) a virtual view."""
        if root is not None and not root.is_dir():
            self.dialog = Message("Drive", [f"Not reachable: {root}"])
            return
        if root is None and not pane.virtual:
            pane.prev = (pane.root, pane.cwd, pane.label)
        pane.root = pane.cwd = root
        pane.label = self.label_for(root)
        pane.tags.clear()
        pane.filter, pane.cursor, pane.top = "", 0, 0
        pane.view = view
        pane.entries = list_view(self.coll, view) if root is None else \
            list_dir(root, root, self.coll)

    def handle(self, key: str) -> None:
        """Dispatch one decoded key, then let the right pane follow the left cursor."""
        self._handle(key)
        self.sync_preview()

    def _handle(self, key: str) -> None:
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
            "/": self.start_filter, "f": self.cycle_show, "esc": self.escape,
            "t": self.cycle_scheme,
            "d": self.drive_dialog, "c": self.checksum_dialog, "r": self.rename_dialog,
            "h": self.toggle_highlight, "p": self.toggle_follow,
            "x": self.drop_dialog, "l": self.relink_dialog, "n": self.nft_dialog,
            "i": self.integrity_dialog, "=": self.compare_dialog, "e": self.extras_dialog,
            "z": self.undo_dialog, "b": self.rebalance_dialog, "w": self.routes_dialog,
            "ctrl-u": self.swap, "ctrl-o": self.toggle_log,
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
                rows = pane.visible()
                hit = rows[pane.top + row - y0] if pane.top + row - y0 < len(rows) else None
                self.clear_ghost(pane)             # a previewed row is not there to click
                rows = pane.visible()
                self.active = pane
                pane.cursor = rows.index(hit) if hit in rows else pane.top + row - y0
                pane.move(0)

    # ---- destination preview

    def toggle_follow(self) -> None:
        """p: the right pane follows the left cursor's destination, on / off."""
        self.follow = not self.follow
        self.say("destination preview " + ("on" if self.follow else "off"))

    @staticmethod
    def clear_ghost(pane: Pane) -> bool:
        """Drop a previewed row from a pane. True when there was one."""
        if not any(e.kind == "ghost" for e in pane.entries):
            return False
        pane.entries = [e for e in pane.entries if e.kind != "ghost"]
        pane.move(0)
        return True

    def preview_target(self, entry: Entry, mount: dict | None) -> Path | None:
        """The directory the cursor folder would land in, or None when it has nowhere to go.

        A folder that is out of place (misfiled, a public LB in the private folder, a
        stray) goes where F7 files it: its show year's route, whatever drive that is.
        A folder already in place goes where F6 would move it: the right pane's mount
        joined with the route's sub_path — the backend's mount-override rule.
        """
        if entry.kind != "dir" or entry.lb is None or entry.status in ("dup", "blocked", "gone"):
            return None
        year = self.year_of(entry)
        route = self.coll.routes.get(year) if year is not None else None
        if not route:
            return None
        if entry.status in ("misfiled", "public", "stray"):
            expected = self.coll.expected_parent(year)
            if expected and norm(entry.path.parent) != expected:
                return Path(expected)
        here = self.coll.mount_for(entry.path)
        if mount is None or (here and here["id"] == mount["id"]):
            return None
        sub = route.get("sub_path") or ""
        return Path(mount["root_path"]) / sub if sub else Path(mount["root_path"])

    def sync_preview(self) -> None:
        """Show, in the right pane, where the folder under the left cursor would land.

        The right pane opens the destination directory (changing drive when the route
        says so), scrolls the spot to mid-pane and shows the folder there as an
        underlined ⇒ row, or puts its cursor on the folder already there. A year folder
        not made yet is shown as "⇒ 1991/name" in the nearest folder that exists. Only
        the left pane drives it, only while it is the active pane, and a right pane
        holding tags is never moved. Nothing is written.
        """
        pane = self.right
        if self.dialog:                               # keep the preview behind a dialog
            return
        self.clear_ghost(pane)
        if not self.follow or self.active is not self.left or self.coll is None \
                or pane.virtual or pane.tags or pane.editing:
            return
        cur = self.left.current()
        parent = self.preview_target(cur, self.coll.mount_for(pane.cwd)) if cur else None
        if parent is None:
            return
        target = existing(parent)
        if norm(pane.cwd) != norm(target):
            if not str(target).startswith(str(pane.root)):       # the route is on another drive
                mount = self.coll.mount_for(target)
                if mount is None or not Path(mount["root_path"]).is_dir():
                    return
                self.set_root(pane, Path(mount["root_path"]))
            self.set_dir(pane, target)
            if norm(pane.cwd) != norm(target):
                return
        # a destination folder not made yet shows as its missing path under what exists
        name = cur.name if target == parent else str(parent.relative_to(target) / cur.name)
        names = [e.name for e in pane.visible()]
        if name in names:
            pane.cursor = names.index(name)           # already there: a clash F6/F7 refuse
        else:
            ghost = Entry(name, parent / cur.name, "ghost")
            at = next((i for i, e in enumerate(pane.entries)
                       if e.kind != "parent" and e.name.lower() > name.lower()),
                      len(pane.entries))
            pane.entries.insert(at, ghost)
            pane.cursor = pane.visible().index(ghost)
        # scroll so the row sits mid-pane, between the folders it will land among
        pane.top = max(0, pane.cursor - self.pane_height // 2)

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

    def cycle_show(self) -> None:
        """f: show all → only folders not in the right spot → only public LBs in private."""
        pane = self.active
        pane.show = SHOW_MODES[(SHOW_MODES.index(pane.show) + 1) % len(SHOW_MODES)]
        pane.cursor = pane.top = 0
        shown = sum(1 for e in pane.visible() if e.kind != "parent")
        self.say({"all": "showing everything",
                  "off": f"{shown} folder(s) not in the right spot",
                  "public": f"{shown} public LB(s) in {PRIVATE_DIR}",
                  "nft": f"{shown} folder(s) whose -NFT suffix is wrong",
                  "name": f"{shown} folder(s) with a non-canonical name",
                  "bad": f"{shown} folder(s) with integrity issues"}[pane.show])

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

    def toggle_highlight(self) -> None:
        """h: colour non-canonical folder names, or stop."""
        self.highlight = not self.highlight
        self.say("non-canonical names " + ("highlighted" if self.highlight else "not highlighted"))

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
            self.set_root(pane, None, "misfiled")

    def request_quit(self) -> None:
        """F10: quit, warning when a queue is still running."""
        if not self.runner.running:
            self.quit = True
            return
        self.dialog = Picker("A job is still running", [
            ("Quit anyway — the backend finishes the current folder; the rest "
             + ("resume next start" if self.queue.path else "are dropped"),
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

    # ---- the saved queue

    def save_queue(self) -> None:
        """Write the live queue to disk (the runner calls this on every change)."""
        if self.saved is None:                 # an undecided saved queue is never overwritten
            self.queue.save(self.runner.snapshot())

    def entry_at(self, path: Path) -> Entry:
        """A pane entry for one folder, classified as the listing would."""
        entry = Entry(path.name, path, "dir")
        entry.lb = lb_of(path.name)
        if self.coll is not None:
            entry.status, entry.note, entry.row = self.coll.classify(path)
            annotate(entry, self.coll)
        return entry

    def job_from(self, spec: dict, status: dict) -> Job | str:
        """Rebuild one saved job against today's disk, or say why it can't resume."""
        kind = spec.get("kind")
        if kind == "route":
            year = spec["year"]
            mount = self.coll.mount_by_id(spec["mount_id"])
            old = self.coll.routes.get(year)
            if mount is None:
                return f"route {year}: its mount is gone"
            if old and old.get("mount_id") == mount["id"]:
                return f"route {year}: already on {mount['label']}"
            return route_job(self.api, year, mount, spec.get("sub_path") or "",
                             self.journal, old)
        path = Path(spec["path"])
        here = norm(status.get("path") or "") == norm(path)
        if kind == "file" and spec.get("running") and here and status.get("running"):
            entry = self.entry_at(path)
            entry.lb = entry.lb if entry.lb is not None else spec.get("lb")
            return file_job(self.api, entry, spec.get("mount_id"), spec.get("file_mode"),
                            spec["dest"], self.journal, spec.get("from_mount_id"),
                            self.page_gate, adopt=True)
        if not path.is_dir():
            result = status.get("result") or {}
            if kind == "file" and spec.get("running") and here and result.get("ok"):
                if result.get("file_mode", "move") == "move":
                    self.journal.add({
                        "kind": "move", "lb": spec.get("lb"), "from": str(path),
                        "to": result.get("dest"), "cross": bool(spec.get("cross")),
                        "from_mount_id": spec.get("from_mount_id"),
                        "registered": bool(spec.get("registered"))})
                return f"{path.name}: finished while lb-nc was closed"
            return f"{path.name}: folder is no longer there"
        entry = self.entry_at(path)
        if entry.lb is None:
            entry.lb = spec.get("lb")
        if kind == "file":
            return file_job(self.api, entry, spec.get("mount_id"), spec.get("file_mode"),
                            spec["dest"], self.journal, spec.get("from_mount_id"),
                            self.page_gate)
        if kind == "rename":
            if (path.parent / spec["new_name"]).exists():
                return f"{path.name}: {spec['new_name']} already exists"
            return rename_job(self.api, entry, spec["new_name"], self.journal, self.page_gate)
        if kind == "register":
            return register_job(self.api, entry, self.journal)
        if kind == "checksums":
            if has_checksums(path):
                return f"{path.name}: already has checksums"
            return generate_job(self.api, entry)
        return f"unknown saved job {kind!r}"

    def rebuild(self, saved: dict) -> tuple[list[list[Job]], list[str]]:
        """The saved batches as runnable jobs, and a line for each one that can't resume."""
        try:
            status = self.api.get("/api/pipeline/file/status") or {}
        except ApiError:
            status = {}
        batches, notes = [], []
        for batch in saved.get("batches") or []:
            jobs = []
            for spec in batch:
                try:
                    made = self.job_from(spec, status)
                except (KeyError, TypeError, ValueError) as exc:
                    made = f"unreadable saved job: {exc!r}"
                if isinstance(made, Job):
                    jobs.append(made)
                else:
                    notes.append("  skip " + made)
            if jobs:
                batches.append(jobs)
        return batches, notes

    def resume_dialog(self) -> None:
        """Offer the queue the last session left on disk: resume, show, or discard."""
        saved = self.saved
        if saved is None:
            self.dialog = Message("Saved queue", ["No saved queue."])
            return
        if self.coll is None:
            self.dialog = Message("Saved queue", [
                self.coll_error or "no collection loaded",
                "The saved queue is kept; F9 Menu offers it again."])
            return
        if self.runner.running:
            self.dialog = Message("Saved queue", ["A queue is running — wait for it."])
            return
        batches, notes = self.rebuild(saved)
        jobs = [j for batch in batches for j in batch]

        def resume() -> None:
            self.saved = None
            self.show_log = True
            self.say(f"resuming {len(jobs)} saved job(s)…")
            for batch in batches:
                self.runner.submit(batch)
            self.save_queue()

        def discard() -> None:
            self.saved = None
            self.queue.save([])
            self.say("saved queue discarded")

        if not jobs:
            discard()
            self.dialog = Message("Saved queue", ["Nothing left to resume.", *notes[:12]])
            return
        detail = [j.detail for j in jobs] + notes
        self.dialog = Picker(f"Saved queue — {saved.get('saved', '?')}", [
            (f"Resume {len(jobs)} job(s)", resume),
            ("Show them", lambda: setattr(self, "dialog", Pager(
                "Saved queue", [("jobs", detail)]))),
            ("Discard the saved queue", discard),
        ], [f"The last session left {len(jobs)} job(s) queued."
            + (f" {len(notes)} can't resume." if notes else ""),
            "Esc decides later (F9 Menu); nothing new can be queued until then."])

    def busy(self, jobs: list[Job]) -> bool:
        """True (with a dialog) when jobs can't be queued behind the running queue."""
        if self.runner.running and any(j.label in FOLLOW_UP for j in jobs):
            self.dialog = Message("Busy", ["A queue is running. This one shows its result",
                                           "when it ends, so it can't be queued — wait for it."])
            return True
        return False

    def unqueued(self, jobs: list[Job]) -> tuple[list[Job], int]:
        """Jobs whose folder no running or queued job already claims, and how many were cut."""
        claimed = {j.path for j in self.runner.outstanding() if j.path}
        fresh = [j for j in jobs if not (j.path and j.path in claimed)]
        return fresh, len(jobs) - len(fresh)

    def run(self, jobs: list[Job]) -> None:
        """Start jobs, or queue them behind the running ones. The single path to the runner;
        read-only refuses gated jobs here too."""
        if self.busy(jobs):
            return
        if self.read_only and any(j.gated for j in jobs):
            self.dialog = Message("Read-only", ["read-only mode"])
            return
        if self.saved and any(j.gated for j in jobs):
            self.resume_dialog()               # a new queue would overwrite the saved one
            return
        jobs, cut = self.unqueued(jobs)
        if not jobs:
            self.dialog = Message("Queue", ["Every selected folder is already in the queue."])
            return
        self.show_log = True
        if self.runner.running:
            self.say(f"queued {len(jobs)} job(s) behind the running ones"
                     + (f" ({cut} already queued, skipped)" if cut else ""))
        else:
            self.say(f"running {jobs[0].label}…")
        self.runner.submit(jobs)

    def gate(self, title: str, jobs: list[Job], blurb: list[str], **kw: Any) -> None:
        """Open the confirm dialog, or refuse in read-only mode."""
        if self.read_only:
            self.dialog = Message(title, ["read-only mode"])
            return
        if self.busy(jobs):
            return
        if self.saved and any(j.gated for j in jobs):
            self.resume_dialog()               # decide the saved queue before a new one
            return
        fresh, cut = self.unqueued(jobs)
        if cut:
            blurb = [*blurb, f"  skip {cut} folder(s): already in the queue"]
        if self.runner.running and fresh:
            waiting = len(self.runner.outstanding())
            blurb = [*blurb, f"A queue is running: these are added behind its {waiting} job(s)."]
        if not fresh:
            self.dialog = Message(title, blurb or ["Nothing to do."])
        else:
            self.dialog = Confirm(title, fresh, blurb, **kw)

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
            elif e.status in ("misfiled", "public", "stray"):
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
        jobs = [file_job(self.api, e, None, "move" if e.row else None, dest, self.journal,
                         self.mount_id_of(e.path), self.page_gate) for e, dest in chosen]
        jobs += [register_job(self.api, e, self.journal) for e in register]
        space = self.space_gate("File", chosen) if chosen else []
        if space is None:
            return
        blurb = [f"{len(chosen)} folder(s) to their year-routed location.",
                 "Registered folders are moved; strays use the pipeline file mode and",
                 "are added to the collection. Cross-drive moves are SHA-256 verified",
                 "before the source goes. One at a time, stops at the first failure."]
        guarded = sum(1 for e, _ in chosen if private_marked(e.name, e.path, e.row))
        if guarded:
            blurb += [f"{guarded} private / private-folder folder(s): each is checked live on the",
                      "LB site first; no page (or no answer) → that move is refused."]
        if register:
            blurb += [f"{len(register)} stray(s) already in place are only registered — no",
                      "checksum pass; F4 Pipe them first if unsure."]
        blurb += [*space, *skipped, *refused]
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
        self.move_entries(picked, mount)

    def mount_id_of(self, path: Path) -> int | None:
        """The id of the mount a path sits on."""
        mount = self.coll.mount_for(path) if self.coll else None
        return mount["id"] if mount else None

    def move_entries(self, picked: list[Entry], mount: dict, reroute: bool = False) -> None:
        """Preview, space-check and gate moving entries onto a mount (F6 and rebalance)."""
        todo, skipped = [], []
        for e in picked:
            here = self.coll.mount_for(e.path)
            if e.status == "dup":
                skipped.append(f"  skip {e.name}: collection has LB-{e.lb:05d} at {e.note}")
            elif e.status in ("blocked", "gone"):
                skipped.append(f"  skip {e.name}: {e.note or 'folder is gone'}")
            elif here and here["id"] == mount["id"] and e.status == "canonical":
                skipped.append(f"  skip {e.name}: already on {mount['label']}")
            else:
                todo.append(e)
        try:
            chosen, refused = self.preview(todo, mount["id"]) if todo else ([], [])
        except ApiError as exc:
            self.dialog = Message("Move", [str(exc)])
            return
        moves = [file_job(self.api, e, mount["id"], "move", dest, self.journal,
                          self.mount_id_of(e.path), self.page_gate) for e, dest in chosen]
        space = self.space_gate("Move", chosen) if chosen else []
        if space is None:
            return
        years = sorted({y for e, _ in chosen if (y := self.year_of(e)) is not None})
        stay = [y for y in years if (self.coll.routes.get(y) or {}).get("mount_id")
                != mount["id"]]

        def jobs(reroute: bool) -> list[Job]:
            if not reroute:
                return moves
            return moves + [route_job(self.api, y, mount,
                                      (self.coll.routes.get(y) or {}).get("sub_path") or "",
                                      self.journal, self.coll.routes.get(y))
                            for y in stay]
        blurb = [f"{len(moves)} folder(s) ⇒ {mount['label']} ({mount['root_path']}),",
                 "under each year's route sub-folder. Hash-verified across drives;",
                 "the collection row and qBittorrent follow. Stops at the first failure."]
        guarded = sum(1 for e, _ in chosen if private_marked(e.name, e.path, e.row))
        if guarded:
            blurb += [f"{guarded} private / private-folder folder(s): each is checked live on the",
                      "LB site first; no page (or no answer) → that move is refused."]
        if stay:
            span = f"{stay[0]}–{stay[-1]}" if len(stay) > 1 else str(stay[0])
            blurb += [f"Years {span} route elsewhere: without r these folders show as",
                      "misfiled afterwards. With r, the routes move too — other folders",
                      "of those years left behind then show as misfiled (F8)."]
        blurb += space + skipped + refused
        toggle = ("r", f"re-route {len(stay)} year(s) to {mount['label']} after the moves",
                  jobs) if stay and moves else None
        self.gate("Move to other mount", moves, blurb, toggle=toggle)
        if reroute and toggle and isinstance(self.dialog, Confirm):
            self.dialog.state = True
            self.dialog.jobs = jobs(True)

    def checksum_dialog(self) -> None:
        """c: generate checksums for selected folders that have none."""
        picked = [e for e in self.active.selection() if e.kind == "dir"]
        if not picked:
            self.dialog = Message("Checksums", ["Select folders first (Space tags)."])
            return
        todo = [e for e in picked if not has_checksums(e.path)]
        skipped = [f"  skip {e.name}: already has .ffp/.md5/.st5" for e in picked
                   if e not in todo]
        self.gate("Generate checksums", [generate_job(self.api, e) for e in todo], [
            "Writes _mychecksums.ffp (FLAC fingerprints) and _mychecksums.md5 into each",
            "folder; existing checksum files are never overwritten. Then F4 looks",
            "the folder up by them.", *skipped])

    def rename_dialog(self) -> None:
        """r: apply the pipeline's proposed names to the selected folders."""
        picked = [e for e in self.active.selection() if e.kind == "dir"]
        if not picked:
            self.dialog = Message("Rename", ["Select folders first (Space tags)."])
            return
        jobs, skipped = [], []
        for e in picked:
            result = self.pipeline_results.get(str(e.path))
            proposed = ((result or {}).get("rename") or {}).get("proposed")
            if result is None and e.canon:
                proposed = e.canon                     # the collection row's canonical name
            if result is None and not proposed:
                skipped.append(f"  skip {e.name}: no pipeline result — F4 it first")
            elif not proposed:
                skipped.append(f"  skip {e.name}: name already correct")
            elif (e.path.parent / proposed).exists():
                skipped.append(f"  skip {e.name}: {proposed} already exists")
            else:
                jobs.append(rename_job(self.api, e, proposed, self.journal, self.page_gate))
        self.gate("Apply renames", jobs, [
            "Renames each folder in place to the pipeline's proposed name, or for a",
            "collection folder with no F4 result, the canonical name from its row. The rename",
            "is logged (rename_history), my_collection and qBittorrent follow.",
            *skipped])

    def drop_dialog(self) -> None:
        """x: delete the records of selected gone folders (nothing on disk is touched)."""
        picked = [e for e in self.active.selection() if e.status == "gone" and e.row]
        if not picked:
            self.dialog = Message("Drop record", [
                "Select gone (✗) folders — d → Gone lists every one."])
            return
        self.gate("Drop records", [drop_job(self.api, e.row, self.journal) for e in picked], [
            "Removes each my_collection record whose folder is no longer on disk.",
            "Nothing on disk changes. z (undo) re-adds a record."])

    def relink_dialog(self) -> None:
        """l: point gone records at a surviving copy."""
        jobs, skipped = [], []
        cand = self.other().current()
        if cand and cand.kind == "ghost":
            cand = None
        for e in [e for e in self.active.selection() if e.kind == "dir"]:
            if e.status == "relink" and e.row:
                jobs.append(relink_job(self.api, e.lb, e.row["disk_path"], str(e.path),
                                       self.journal))
            elif e.status == "gone" and e.row:
                if cand and cand.kind == "dir" and cand.lb == e.lb and cand.path.is_dir():
                    jobs.append(relink_job(self.api, e.lb, e.row["disk_path"], str(cand.path),
                                           self.journal))
                else:
                    skipped.append(f"  skip {e.name}: put the other pane's cursor on a folder "
                                   f"with LB-{e.lb:05d}")
            else:
                skipped.append(f"  skip {e.name}: its record isn't gone")
        self.gate("Relink records", jobs, [
            "Points each record at the surviving copy (my_collection only; the folder",
            "stays where it is — F7 files it afterwards if it's misfiled).", *skipped])

    def nft_dialog(self) -> None:
        """n: add or drop the -NFT suffix to match lb_status."""
        jobs, skipped = [], []
        for e in [e for e in self.active.selection() if e.kind == "dir"]:
            if not e.nft or not e.row:
                skipped.append(f"  skip {e.name}: suffix already right")
                continue
            new = apply_nft_suffix(strip_nft_suffix(e.name), e.row.get("lb_status"))
            if (e.path.parent / new).exists():
                skipped.append(f"  skip {e.name}: {new} already exists")
            else:
                jobs.append(rename_job(self.api, e, new, self.journal, self.page_gate))
        self.gate("Fix -NFT suffix", jobs, [
            "Private LBs get -NFT, public ones lose it. Renamed in place; the collection",
            "row and qBittorrent follow. f → NFT mismatch lists every one here.",
            "Each is checked live first: -NFT is only added when the LB has no page on",
            "the LB site, only dropped when it has one; anything else is refused.", *skipped])

    def integrity_dialog(self) -> None:
        """i: run the integrity scan on this pane's mount (the whole collection off-mount)."""
        pane = self.active
        mount = self.coll.mount_for(pane.cwd) if self.coll and not pane.virtual else None
        self.gate("Integrity scan", [integrity_job(self.api, mount)], [
            "Re-checks every collection folder on "
            + (mount["label"] if mount else "every mount") + " against its lbdir (reads",
            "all audio — slow). Results mark folders ! and f → integrity issues lists them."])

    def compare_dialog(self) -> None:
        """=: compare a duplicate (≠) with the collection's copy, then pick a keeper."""
        cur = self.active.current()
        if not cur or cur.status not in ("dup", "relink") or not cur.row:
            self.dialog = Message("Duplicate", ["Put the cursor on a ≠ duplicate folder."])
            return
        if cur.status == "relink":
            self.dialog = Message("Duplicate", ["The collection copy is gone —",
                                                "l relinks the record to this folder."])
            return
        self.compare_ctx = (cur, cur.row)
        self.run([compare_job(self.api, [cur.path, Path(cur.row["disk_path"])],
                              self.compare_result)])

    def compare_picker(self) -> None:
        """After compare_job: show both copies and offer the two ways to resolve."""
        if not self.compare_ctx or len(self.compare_result) != 2:
            return
        entry, row = self.compare_ctx
        lines = []
        for label, r in zip(("THIS copy      ", "COLLECTION copy"), self.compare_result,
                            strict=True):
            lines.append(f"{label} {r['path']}")
            lines.append(f"    lbdir {r.get('status', '?')}: {r.get('pass', 0)}/"
                         f"{r.get('total', 0)} pass, {r.get('mismatch', 0)} mismatch, "
                         f"{r.get('missing', 0)} missing, {r.get('extra', 0)} extra"
                         f"  ·  {r['files']} files {human(r['size'])}")
        other = Path(row["disk_path"])

        def keep_this() -> None:
            self.gate("Keep this copy", [
                relink_job(self.api, entry.lb, str(other), str(entry.path), self.journal),
                aside_job(self.api, other, aside_target(other, self.aside_root(other)),
                          self.journal, self.page_gate, row)],
                ["The record moves to this copy; the old collection copy is set aside",
                 f"in {DUP_DIR}/ on its own drive (nothing is deleted)."])

        def keep_collection() -> None:
            self.gate("Keep the collection copy", [
                aside_job(self.api, entry.path,
                          aside_target(entry.path, self.aside_root(entry.path)), self.journal,
                          self.page_gate, None)],
                [f"This copy is set aside in {DUP_DIR}/ on its own drive (nothing is deleted)."])
        self.dialog = Picker(f"Duplicate LB-{entry.lb:05d}", [
            ("Keep THIS copy — repoint the record, set the collection copy aside", keep_this),
            ("Keep the COLLECTION copy — set this one aside", keep_collection),
            ("Cancel", lambda: None)], lines)

    def aside_root(self, path: Path) -> Path:
        """Where _duplicates/ goes for a folder: its mount root, else its parent."""
        mount = self.coll.mount_for(path) if self.coll else None
        return Path(mount["root_path"]) if mount else path.parent

    def extras_dialog(self) -> None:
        """e: move files the lbdir doesn't list into extras/."""
        picked = [e for e in self.active.selection() if e.kind == "dir"]
        if not picked:
            self.dialog = Message("Extras", ["Select folders first (Space tags)."])
            return
        try:
            res = self.api.post("/api/lbdir/find_extra",
                                {"folders": [str(e.path) for e in picked]})
        except ApiError as exc:
            self.dialog = Message("Extras", [str(exc)])
            return
        if "results" not in res:
            self.dialog = Message("Extras", [str(res.get("error"))])
            return
        jobs, lines = [], []
        for e, r in zip(picked, res["results"], strict=True):
            extra = [f for f in r.get("extra") or [] if not f.startswith("extras/")]
            if r.get("error"):
                lines.append(f"  skip {e.name}: {r['error']}")
            elif not extra:
                lines.append(f"  skip {e.name}: nothing extra")
            else:
                jobs.append(extras_job(self.api, e.path, extra, self.journal))
                lines += [f"    {e.name}/{f}" for f in extra[:4]]
                if len(extra) > 4:
                    lines.append(f"    … and {len(extra) - 4} more")
        self.gate("Move extras", jobs, [
            "Files the lbdir doesn't list move to <folder>/extras/ (qBittorrent follows).",
            *lines])

    def undo_dialog(self) -> None:
        """z: pick a journal record to reverse, newest first."""
        records = self.journal.undoable()
        if not records:
            self.dialog = Message("Undo", ["Nothing to undo."])
            return

        def pick(rec: dict) -> Callable[[], None]:
            return lambda: self.gate("Undo", [undo_job(self.api, rec, self.journal,
                                                        self.page_gate)], [
                "Undo newest first — reversing an older step out of order can fail."])
        self.dialog = Picker("Undo — newest first",
                             [(f"{r['ts']}  {describe(r)}", pick(r)) for r in records])

    def rebalance_dialog(self) -> None:
        """b: measure this pane's mount, then plan whole-year moves to the other pane's."""
        src = self.coll.mount_for(self.active.cwd) \
            if self.coll and not self.active.virtual else None
        dst = self.coll.mount_for(self.other().cwd) \
            if self.coll and not self.other().virtual else None
        if not src or not dst or src["id"] == dst["id"]:
            self.dialog = Message("Rebalance", [
                "This pane shows the drive to empty, the other pane the drive to fill",
                "(two different mounts; d picks a drive)."])
            return
        if same_device(Path(src["root_path"]), Path(dst["root_path"])):
            self.dialog = Message("Rebalance", ["Both mounts are on one filesystem."])
            return
        rows = [r for r in self.coll.rows if r.get("disk_path")
                and (self.coll.mount_for(r["disk_path"]) or {}).get("id") == src["id"]
                and self.coll.row_status(r)[0] == "canonical"
                and not self.coll.in_private(r["disk_path"])
                and (self.coll.routes.get(Collection.year_of(r) or 0) or {}).get("mount_id")
                == src["id"]]
        if not rows:
            self.dialog = Message("Rebalance", [f"No routed folders on {src['label']}."])
            return
        self.plan_ctx = (src, dst, rows)
        self.run([measure_job(self.sizes, [Path(r["disk_path"]) for r in rows])])

    def rebalance_plan(self) -> None:
        """After measure_job: show the whole-year plan; a applies it."""
        if not self.plan_ctx:
            return
        src, dst, rows = self.plan_ctx
        su, du = self.usage(src["root_path"], True), self.usage(dst["root_path"], True)
        if not su or not du:
            self.dialog = Message("Rebalance", ["Free space unreadable on one of the drives."])
            return
        by_year: dict[int, list[dict]] = {}
        for r in rows:
            by_year.setdefault(Collection.year_of(r) or 0, []).append(r)
        year_bytes = {y: sum(self.sizes.get_now(Path(r["disk_path"])) for r in rs)
                      for y, rs in by_year.items()}
        dst_years = [y for y, r in self.coll.routes.items() if r["mount_id"] == dst["id"]]
        from_high = not dst_years or min(dst_years) > max(by_year) or \
            not max(dst_years) < min(by_year)
        steps, chosen = plan_rebalance(year_bytes, su, du, from_high)
        text = [f"{src['label']} {human(su[0])} free of {human(su[1])}  →  "
                f"{dst['label']} {human(du[0])} free of {human(du[1])}", "",
                "  year  folders     moved   " + f"{src['label']:>8} {dst['label']:>8}  (used %)"]
        for i, (year, moved, a, b) in enumerate(steps, 1):
            mark = " ◀ plan" if i == chosen else ""
            text.append(f"  {year}  {len(by_year[year]):>7} {human(moved):>9}   "
                        f"{a:>7.0f}% {b:>7.0f}%{mark}")
        if not steps:
            text.append(f"  nothing fits on {dst['label']} with the 2G reserve")
        years = [y for y, *_ in steps[:chosen]]
        if not chosen:
            text += ["", "Already as balanced as whole years allow."]
        else:
            text += ["", f"Plan: move {len(years)} year(s) {min(years)}–{max(years)} and "
                     f"re-route them to {dst['label']}."]

        def apply() -> None:
            entries = [Entry(Path(r["disk_path"]).name, Path(r["disk_path"]), "dir",
                             "canonical", "", r, int(r["lb_number"]))
                       for y in years for r in by_year[y]]
            self.move_entries(entries, dst, reroute=True)
        self.dialog = PlanView("Rebalance", text, apply if chosen else None)

    def routed_rows(self) -> list[dict]:
        """Rows whose location a route governs: canonical, misfiled, public-in-private."""
        if not self.coll:
            return []
        return [r for r in self.coll.rows if r.get("disk_path") and Collection.year_of(r)
                and self.coll.row_status(r)[0] in ("canonical", "misfiled", "public")
                and self.coll.row_status(r)[1] != PRIVATE_AREA]

    def routes_dialog(self) -> None:
        """w: size every routed folder, then suggest a year → drive layout that fits."""
        if not self.coll or not self.coll.mounts:
            self.dialog = Message("Routes", [self.coll_error or "no mounts loaded"])
            return
        rows = self.routed_rows()
        self.run([measure_job(self.sizes, [Path(r["disk_path"]) for r in rows],
                              "measure-routes")])

    def routes_plan(self) -> None:
        """After measure-routes: compute and show the suggested routing."""
        coll = self.coll
        if coll is None:
            return
        devs: dict[int, str] = {}
        usage: dict[str, tuple[int, int]] = {}
        for m in coll.mounts:
            u = self.usage(m["root_path"], True)
            if u is None:
                self.dialog = Message("Routes", [f"{m['label']} is offline."])
                return
            usage[m["label"]] = u
            try:
                devs[os.stat(m["root_path"]).st_dev] = m["label"]
            except OSError:
                pass
        where: dict[int, dict[str, int]] = {y: {} for y in coll.routes}
        on_drive: dict[str, int] = dict.fromkeys(usage, 0)
        for r in self.routed_rows():
            path = Path(r["disk_path"])
            try:
                label = devs.get(os.stat(path).st_dev, "")
            except OSError:
                continue
            size = self.sizes.get_now(path)
            year = Collection.year_of(r) or 0
            where.setdefault(year, {})
            where[year][label] = where[year].get(label, 0) + size
            if label:
                on_drive[label] += size
        totals = {k: u[1] for k, u in usage.items()}
        fixed = {k: max(0, u[1] - u[0] - on_drive[k]) for k, u in usage.items()}
        plan, keep = None, SPACE_RESERVE
        for frac in PLAN_HEADROOM:          # the most free space per drive that still fits
            keep_of = {k: max(SPACE_RESERVE, int(totals[k] * frac)) for k in usage}
            capacity = {k: totals[k] - fixed[k] - keep_of[k] for k in usage}
            plan = suggest_routes(where, capacity, totals, fixed)
            if plan is not None:
                keep = frac
                break
        lab = {m["id"]: m["label"] for m in coll.mounts}
        text = ["Now:"]
        for k, u in usage.items():
            years = sorted(y for y, r in coll.routes.items() if lab.get(r["mount_id"]) == k)
            span = f"{years[0]}–{years[-1]}" if years else "no years"
            text.append(f"  {k:<8} {span:<11} routed data {human(on_drive[k]):>6}  "
                        f"other {human(fixed[k]):>6}  free {human(u[0]):>6} of {human(u[1])}")
        need = sum(sum(v.values()) for v in where.values())
        slack = sum(totals[k] - fixed[k] for k in usage) - need
        text.append(f"  routed years hold {human(need)}; slack across all drives "
                    f"{human(max(slack, 0))} ({slack / sum(totals.values()):.1%})")
        if plan is None:
            text += ["", "No contiguous year layout fits — free space or add a drive first."]
            self.dialog = PlanView("Suggested routes", text, None)
            return
        kept = f"{keep:.1%} of each drive" if keep else human(SPACE_RESERVE)
        text += ["", f"Suggested (moves {human(plan.moved)} between drives, keeps ≥{kept} free):"]
        changes: list[tuple[int, dict]] = []
        for k in plan.order:
            ys = plan.ranges[k]
            span = f"{ys[0]}–{ys[-1]}" if ys else "no years"
            size = sum(sum(where[y].values()) for y in ys)
            text.append(f"  {k:<8} {span:<11} {human(size):>6}  fill after {plan.fill[k]:.0%}")
            mount = next(m for m in coll.mounts if m["label"] == k)
            changes += [(y, mount) for y in ys if lab.get((coll.routes.get(y) or {})
                                                          .get("mount_id")) != k]
        batches: dict[tuple[str, str], int] = {}
        for y, per in where.items():
            dst = next(k for k in plan.order if y in plan.ranges[k])
            for src, size in per.items():
                if src != dst:
                    key = (src or "elsewhere", dst)
                    batches[key] = batches.get(key, 0) + size
        steps, stuck = move_order(batches, {k: u[0] for k, u in usage.items()})
        text += ["", f"{len(changes)} year route(s) change. Then refile (F8, F7) in this order:"]
        for i, (src, dst, size) in enumerate(steps, 1):
            text.append(f"  {i}. {src} {self.g['dest']} {dst}  {human(size)}")
        for (src, dst), size in stuck.items():
            text.append(f"  !! {src} {self.g['dest']} {dst} {human(size)} doesn't fit yet")
        if not changes:
            text.append("  (routes already match — only the refile is needed)")

        def apply() -> None:
            self.gate("Apply suggested routes", [
                route_job(self.api, y, m, (coll.routes.get(y) or {}).get("sub_path")
                          or str(y), self.journal, coll.routes.get(y)) for y, m in changes],
                ["Re-points the year routes only; nothing moves. Folders then show as",
                 "misfiled — refile them with F7 in the order above (the space check",
                 "refuses a batch that doesn't fit yet). z undoes route changes."])
        self.dialog = PlanView("Suggested routes", text, apply if changes else None)

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
            if cur.note == PRIVATE_AREA:
                text.append(f"private LB under {PRIVATE_DIR} — where it belongs")
            elif cur.status in ("canonical", "misfiled", "public"):
                if cur.status == "public":
                    text.append(f"public now, but filed under {PRIVATE_DIR}")
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
        if cur.canon:
            text.append(f"canonical name  {cur.canon}  (r renames)")
        if cur.nft:
            text.append("NFT: " + ("private LB, add -NFT" if cur.nft == "missing"
                                   else "public LB, drop -NFT") + "  (n fixes)")
        health = self.coll.integrity.get(cur.lb) if self.coll and cur.lb else None
        if health:
            text.append(f"integrity: {health.get('status')}  ({health.get('content_issues', 0)}"
                        f" content, {health.get('tag_issues', 0)} tag, "
                        f"{health.get('missing_count', 0)} missing of "
                        f"{health.get('total_files', 0)}; {health.get('checked_at')})")
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
        items.append(("Misfiled folders (all mounts)",
                      lambda: self.set_root(pane, None, "misfiled")))
        items.append(("Gone — collection paths no longer on disk",
                      lambda: self.set_root(pane, None, "gone")))
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
                          (self.coll.routes.get(y) or {}).get("sub_path") or "",
                          self.journal, self.coll.routes.get(y))
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
            ("Generate checksums for the selection (c)", self.checksum_dialog),
            ("Apply the pipeline's proposed renames (r)", self.rename_dialog),
            ("Re-route the selection's years to the other pane's mount", self.reroute_dialog),
            ("Fix the -NFT suffix of the selection (n)", self.nft_dialog),
            ("Move extra files into extras/ (e)", self.extras_dialog),
            ("Resolve the duplicate under the cursor (=)", self.compare_dialog),
            ("Relink gone records to a surviving copy (l)", self.relink_dialog),
            ("Drop the records of gone folders (x)", self.drop_dialog),
            ("Integrity scan of this pane's drive (i)", self.integrity_dialog),
            ("Rebalance: plan whole-year moves to the other pane's drive (b)",
             self.rebalance_dialog),
            ("Suggest year routes from year sizes and drive space (w)", self.routes_dialog),
            ("Undo (z)", self.undo_dialog),
            ("Saved queue from the last session: resume or discard", self.resume_dialog),
            ("Last pipeline results", lambda: setattr(self, "dialog", Pager(
                "Pipeline", self.results_pages()))),
            ("Stop the queue after the current folder", stop),
            ("Cancel the running pipeline", cancel_pipeline),
        ])

    def tick(self) -> None:
        """Pick up job completion, sizes and flash expiry."""
        if self.runner.running:
            self.dirty = True
            if self.runner.done != self._reloaded[0] \
                    and time.monotonic() - self._reloaded[1] >= RELOAD_EVERY:
                self._reloaded = (self.runner.done, time.monotonic())
                self._free_cache.clear()
                self.reload()              # the panes follow the queue as folders land
        if self.runner.finished:
            self.runner.finished = False
            self._reloaded = (0, 0.0)
            with self.runner.lock:
                ran, self.runner.ran = self.runner.ran, set()
                refused, self.runner.refused = self.runner.refused, []
                failure, self.runner.failure = self.runner.failure, None
            if "rename" in ran:
                self.pipeline_results.clear()          # keyed by the old paths
            if failure:
                label, text = failure
                self.dialog = Message(f"{label}: failed", text + (
                    [f"{len(refused)} refused before that (no live LB page)"] if refused else []))
            elif refused:
                self.dialog = Message(f"done — {len(refused)} refused (no live LB page)",
                                      refused[:12] + ([f"… and {len(refused) - 12} more"]
                                                      if len(refused) > 12 else []))
            elif "pipeline" in ran and "rename" not in ran:
                self.dialog = Pager("Pipeline", self.results_pages())
            elif "compare" in ran:
                self.compare_picker()
            elif "measure" in ran:
                self.rebalance_plan()
            elif "measure-routes" in ran:
                self.routes_plan()
            else:
                tail = list(self.runner.lines)[-10:]
                self.dialog = Message("done", tail or ["ok"])
            self._free_cache.clear()
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
        drives = self.drives_line() if rows >= 16 else ""
        bar = self.runner.running
        body = rows - 1 - 1 - 1 - info_rows - 1 - key_rows - log_rows - bool(drives) - bar
        if body < 3 and log_rows:
            body, log_rows = body + log_rows, 0
        if body < 1:
            info_rows, body = 1, body + info_rows - 1
        self.pane_height = body
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
        if drives:
            out.append([("frame", b["v"]), ("dim", fit(drives, cols - 2, self.g["ellipsis"])),
                        ("frame", b["v"])])
        for text in self.info_strip(info_rows):
            out.append([("frame", b["v"]), ("text", fit(text, cols - 2, self.g["ellipsis"])),
                        ("frame", b["v"])])
        out.append([("frame", b["bl"] + b["h"] * (cols - 2) + b["br"])])
        if bar:
            out.append(self.progress_bar(cols))
        out.extend(self.keybar(cols, len(out)))
        return [pad_line(line, cols, "pane") for line in out[:rows]]

    def pane_header(self, pane: Pane, width: int, narrow: bool = False) -> Line:
        """The pane title (label: path) and its counts."""
        b = self.box
        if pane.virtual and pane.view == "gone":
            title = VIEWS["gone"]
            count = "checking…" if self.checking_gone else f"{len(pane.entries)} gone"
        elif pane.virtual:
            title = VIEWS["misfiled"]
            public = sum(1 for e in pane.entries if e.status == "public")
            count = f"{len(pane.entries)} to refile" + (f" · {public} public" if public else "")
        else:
            mount = self.coll.mount_for(pane.cwd) if self.coll else None
            if mount:
                rel = os.path.relpath(pane.cwd, mount["root_path"])
                title = f"{mount['label']}:/" + ("" if rel == "." else rel)
            else:
                title = str(pane.cwd)
            lbs = [e for e in pane.entries if e.lb is not None]
            off = sum(1 for e in lbs if e.status in OFF)
            count = f"{len(lbs)} LB" + (f" · {off} off" if off else "")
            count += f" · {self.free(pane.cwd)} free"
        if pane.show != "all":
            count = f"[{SHOW_LABELS[pane.show]}] {count}"
        if any(e.kind == "ghost" for e in pane.entries):
            count = f"preview {self.g['dest']} · {count}"
        if pane.tags:
            sizes = [self.sizes.get(e.path) for e in pane.entries
                     if e.key in pane.tags and e.kind == "dir"]
            total = None if any(z is None for z in sizes) else sum(z or 0 for z in sizes)
            count = f"{len(pane.tags)} tagged {human(total)} · {count}"
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
                "tag" if tagged else "ghost" if ghost or entry.kind == "ghost" \
                else "odd" if entry.canon \
                and self.highlight \
                else "text" if entry.kind == "dir" else "pane"
            mark = self.g["cursor"] if on else " "
            rows.append([(role, mark + self.row_text(pane, entry, width - 1))])
        return rows

    def row_text(self, pane: Pane, entry: Entry, width: int) -> str:
        """Name, status glyph and size."""
        e = self.g["ellipsis"]
        if entry.kind == "parent":
            return fit("..", width, e)
        if entry.kind == "ghost":
            return fit(f"{self.g['dest']} {entry.name}", width, e)
        if entry.kind == "file":
            return fit(entry.name, width, e)
        if entry.lb is None:
            return fit(entry.name, width - 6, e) + fit("<DIR>", 6, e, right=True)
        glyph = self.g.get(entry.status, " ")
        flag = "!" if entry.health else "n" if entry.nft else " "
        size = None if entry.status == "gone" else self.sizes.get(entry.path)
        shown = "" if entry.status == "gone" else human(size)
        tail = f" {glyph}{flag}{fit(shown, 5, e, right=True)}"
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
            if cur.nft:
                first += "  ·  NFT: " + ("add -NFT" if cur.nft == "missing" else "drop -NFT")
            if cur.health:
                first += f"  ·  integrity: {cur.health}"
            show = f"LB-{cur.lb:05d}  {row.get('date_str') or ''}  {row.get('location') or ''}"
            if cur.canon and self.highlight:
                show = f"name ≠ canonical {self.g['dest']} {cur.canon}  (r renames)"
            if cur.status in ("misfiled", "public"):
                why = "went public — " if cur.status == "public" else ""
                third = (f"{why}{self.g['dest']} {cur.note}  free: {self.free(cur.note)}"
                         "  (F7 files)")
            elif cur.status == "dup":
                third = f"collection copy: {cur.note}  (= compares and resolves)"
            elif cur.status == "relink":
                third = f"collection path gone: {cur.note}  (l relinks here)"
            elif cur.status == "gone":
                third = "folder not on disk — x drops the record, l relinks it to a copy"
            elif cur.status == "stray":
                third = ("in place, not registered — F7 registers it" if cur.note == IN_PLACE
                         else "not in collection — F7 files and registers it")
            elif cur.status == "blocked":
                third = cur.note
            elif cur.note == PRIVATE_AREA:
                third = f"{self.g['canonical']} private LB, under {PRIVATE_DIR}"
            else:
                third = f"{self.g['canonical']} at its routed location"
            rows = [first, show, third]
        if self.flash[0] and time.monotonic() - self.flash[1] < 6:
            rows.insert(0, f"{self.g['running']} {self.flash[0]}")
        return (rows + ["", "", ""])[:count]

    def usage(self, path: str | Path | None, fresh: bool = False) -> tuple[int, int] | None:
        """(free, total) bytes on the filesystem holding path, re-read at most every 10 s."""
        if path is None:
            return None
        hit = self._free_cache.get(str(path))
        if hit and not fresh and time.monotonic() - hit[0] < 10:
            return hit[1]
        try:
            du = shutil.disk_usage(existing(path))
            value: tuple[int, int] | None = (du.free, du.total)
        except OSError:
            value = None
        self._free_cache[str(path)] = (time.monotonic(), value)
        return value

    def free(self, path: str | Path | None) -> str:
        """Free space on the filesystem holding path, as 1.2T text."""
        value = self.usage(path)
        return human(value[0]) if value else "?"

    def drives_line(self) -> str:
        """Every mount's free space and fill, e.g. DYLAN1 1.2T free (78%)."""
        parts = []
        for m in (self.coll.mounts if self.coll else []):
            value = self.usage(m["root_path"])
            if value is None:
                parts.append(f"{m['label']} offline")
                continue
            free, total = value
            used = round((total - free) / total * 100) if total else 0
            parts.append(f"{m['label']} {human(free)} free ({used}%)")
        return "drives: " + "  ·  ".join(parts) if parts else ""

    def space_check(self, pairs: list[tuple[Entry, str]]) -> tuple[list[str], bool]:
        """What a batch of moves needs per target drive. Returns (lines, won't fit).

        A move within one filesystem is a rename and needs nothing; a cross-drive move
        needs the folder's full size on the target plus SPACE_RESERVE.
        """
        need: dict[str, int] = {}
        where: dict[str, Path] = {}
        for entry, dest in pairs:
            target = existing(dest)
            if same_device(entry.path, target):
                continue
            mount = self.coll.mount_for(dest) if self.coll else None
            label = mount["label"] if mount else str(target)
            need[label] = need.get(label, 0) + self.sizes.get_now(entry.path)
            where[label] = target
        if not need:
            return ["  space: same-drive renames only — nothing to copy"], False
        ahead: dict[str, int] = {}             # cross-drive moves already queued, per target
        for job in self.runner.outstanding():
            if job.cross and job.dest and job.path:
                mount = self.coll.mount_for(job.dest) if self.coll else None
                label = mount["label"] if mount else str(existing(job.dest))
                ahead[label] = ahead.get(label, 0) + self.sizes.get_now(Path(job.path))
        lines, over = [], False
        for label, size in need.items():
            value = self.usage(where[label], fresh=True)
            if value is None:
                lines.append(f"  {label}: needs {human(size)}, free space unreadable")
                over = True
                continue
            queued = ahead.get(label, 0)
            after = value[0] - size - queued
            fits = after >= SPACE_RESERVE
            over = over or not fits
            lines.append(f"  {label}: needs {human(size)} of {human(value[0])} free"
                         + (f" ({human(queued)} queued ahead)" if queued else "")
                         + f" {self.g['dest']} {human(max(after, 0))} after"
                         + ("" if fits else f"  — WON'T FIT ({human(SPACE_RESERVE)} reserve)"))
        return lines, over

    def space_gate(self, title: str, pairs: list[tuple[Entry, str]]) -> list[str] | None:
        """Space lines for the confirm blurb, or None after refusing a batch that won't fit."""
        lines, over = self.space_check(pairs)
        if over:
            self.dialog = Message(f"{title}: not enough space", [
                *lines, "", "Untag some folders or free space on the target first."])
            return None
        return lines

    def progress_bar(self, cols: int) -> Line:
        """The meter above the key bar: this folder's bytes, then the queue.

        move LB-14236 ████████░░░░░░░  42% 360M/817M  queue 3/12 ██░░░░░░  21%
        A job with no byte count (a rename, a route) shows the queue bar alone; a narrow
        terminal drops the queue bar, then the bars, before it drops the numbers.
        """
        job, done, total = self.runner.progress()
        if job is None:
            return pad_line([], cols, "key_num")
        cur, size = job.meter
        frac = min(1.0, cur / size) if size > 0 else 0.0
        qfrac = min(1.0, (done + frac) / total) if total > 0 else 0.0
        head = f" {job.label} "
        nums = f" {frac:4.0%} {human(cur)}/{human(size)} " if size > 0 else ""
        qhead = f" queue {min(done + 1, total)}/{total} "
        qnums = f" {qfrac:4.0%} "
        on, off = self.g["bar_on"], self.g["bar_off"]

        def meter(part: float, width: int) -> Line:
            fill = min(width, round(part * width))
            return [("run", on * fill), ("key_num", off * (width - fill))]

        room = cols - sum(text_width(t) for t in (head, nums, qhead, qnums))
        line: Line = [("key_label", head)]
        if size > 0 and total > 1 and room >= 16:           # folder bar, then queue bar
            wide = room * 3 // 5
            line += meter(frac, wide) + [("key_num", nums), ("key_label", qhead)] \
                + meter(qfrac, room - wide) + [("key_num", qnums)]
        elif size > 0:                                      # folder bar, queue as numbers
            tail = qhead if total > 1 else ""
            room = cols - sum(text_width(t) for t in (head, nums, tail))
            line += meter(frac, max(0, room)) + [("key_num", nums), ("key_label", tail)]
        else:                                               # no byte count: queue bar alone
            line += [("key_label", qhead)] + meter(qfrac, max(0, room)) + [("key_num", qnums)]
        return pad_line(line, cols, "key_num")

    def keybar(self, cols: int, y: int) -> list[Line]:
        """The F-key bar; every slot is clickable."""
        full = ("Help", "Info", "View", "Pipe", "Scan", "Move", "File", "Misfd", "Menu",
                "Quit")
        short = ("Hlp", "Inf", "Viw", "Pip", "Scn", "Mov", "Fil", "Mis", "Mnu", "Qt")
        keys = [f"f{n}" for n in range(1, 11)]
        if cols >= 60:
            _job, done, total = self.runner.progress()
            status = (f" {self.g['running']} running {min(done + 1, total)}/{total} "
                      if self.runner.running else f" LB · {time.strftime('%H:%M')} ")
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
        self.integrity: list[dict] = []
        self.no_page: set[int] = set()

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
        if path.startswith("/api/collection/") and path.split("/")[-1].isdigit() \
                and method in ("PATCH", "DELETE"):
            lb = int(path.split("/")[-1])
            row = next((r for r in self.rows if r["lb_number"] == lb), None)
            if row is None:
                return {"error": "no row"}
            if method == "DELETE":
                self.rows.remove(row)
            else:
                row.update({k: v for k, v in body.items() if k in ("disk_path", "folder_name")})
            return {"ok": True}
        if path.startswith("/api/lb_master/") and path.endswith("/live"):
            lb = int(path.split("/")[3])
            return {"lb_number": lb, "exists": lb not in self.no_page, "status": 200}
        if path == "/api/collection/integrity/status":
            return {"status": self.integrity}
        if path == "/api/collection/integrity/scan":
            return {"ok": True}
        if path == "/api/collection/integrity/scan/status":
            return {"running": False, "folders_done": 1, "folders_total": 1}
        if path == "/api/lbdir/find_extra":
            return {"results": [{"folder": f, "extra": sorted(
                str(x.relative_to(f)) for x in Path(f).rglob("*.jpg")
                if "extras" not in x.relative_to(f).parts)} for f in body["folders"]]}
        if path == "/api/lbdir/move_extras":
            folder = Path(body["folder"])
            for rel in body["files"]:
                (folder / "extras" / rel).parent.mkdir(parents=True, exist_ok=True)
                os.rename(folder / rel, folder / "extras" / rel)
            return {"moved": len(body["files"]), "errors": []}
        if path == "/api/lbdir/check":
            return {"results": [{"folder": f, "status": "pass", "total": 1, "pass": 1,
                                 "mismatch": 0, "missing": 0, "extra": 0}
                                for f in body["folders"]]}
        if path == "/api/rename/apply":
            applied = 0
            for item in body["renames"]:
                Path(item["new_path"]).parent.mkdir(parents=True, exist_ok=True)
                os.rename(item["old_path"], item["new_path"])
                applied += 1
            return {"applied": applied, "errors": []}
        if path.startswith("/api/collection/routes/") and method == "DELETE":
            year = int(path.split("/")[-1])
            self.routes_rows = [r for r in self.routes_rows if r["year"] != year]
            return {"ok": True}
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
        if path == "/api/verify/generate":
            out = []
            for f in body["folders"]:
                target = Path(f) / "_mychecksums.ffp"
                target.write_text("d1t01.flac:0\n")
                out.append({"folder": f, "generated": [str(target)], "errors": []})
            return {"results": out}
        if path == "/api/folder/rename":
            src = Path(body["folder"])
            dst = src.parent / body["new_name"]
            os.rename(src, dst)
            for r in self.rows:
                if r["disk_path"] == str(src):
                    r["disk_path"], r["folder_name"] = str(dst), dst.name
            return {"ok": True, "new_path": str(dst)}
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

    def folder(parent: Path, name: str, lb: int | None, registered: bool = True,
               status: str = "public") -> None:
        (parent / name).mkdir(parents=True, exist_ok=True)
        (parent / name / "d1t01.flac").write_bytes(b"\0" * 1024)
        if lb is not None and registered:
            rows.append({"lb_number": lb, "folder_name": name,
                         "disk_path": str(parent / name), "date_str": name[:10],
                         "location": name[11:].split(" (")[0], "lb_status": status})

    folder(one, "1966-05-17 Manchester, England (LB-00123)", 123)
    folder(one, "1975-11-19 Toronto, Canada (LB-04410)", 4410)
    folder(one, "1987-10-17 London, England (LB-01860)", 1860)             # misfiled
    folder(one, "1995-03-01 Prague, Czech Republic (LB-05555)", 5555, False)  # stray
    folder(one, "1978-06-15 Tokyo, Japan (LB-03003)", 3003, status="private")  # no -NFT
    folder(one, "bd1966-05-26 LB-321 London", None)                          # legacy name
    rows.append({"lb_number": 321, "folder_name": "bd1966-05-26 LB-321 London",
                 "disk_path": str(one / "bd1966-05-26 LB-321 London"),
                 "date_str": "5/26/66", "location": "London, England", "lb_status": "public"})
    folder(two / "1987", "1987-09-05 Tel Aviv, Israel (LB-02311)", 2311)
    (two / "1987" / "1987-09-05 Tel Aviv, Israel (LB-02311)" / "cover.jpg").write_bytes(b"x")
    folder(two / "1987", "1987-10-05 Verona, Italy (LB-07777)", 7777, False)   # stray
    folder(two / "1987", "1975-11-19 Toronto, Canada (LB-04410)-copy", None)
    (two / "1987" / "1975-11-19 Toronto (LB-04410) alt").mkdir()            # dup
    folder(two / "1998", "1998-06-24 Portsmouth, England (LB-09001)", 9001)
    private = base / "DYLAN2" / "PRIVATE LB" / "Batch A"                  # outside Concerts/
    folder(private, "1990-01-12 New Haven, CT (LB-08001)-NFT", 8001, status="private")
    folder(private, "1991-02-20 New York, NY (LB-08002)", 8002)             # went public
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
    global PRIVATE_DIR
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--left", type=Path, help="left pane start (default: first mount)")
    parser.add_argument("--right", type=Path, help="right pane start (default: second mount)")
    parser.add_argument("--api", default=API_URL, help=f"backend URL (default {API_URL})")
    parser.add_argument("--private-dir", default=PRIVATE_DIR,
                        help=f"folder name that holds private LBs (default {PRIVATE_DIR!r})")
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
    PRIVATE_DIR = args.private_dir

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
                  scheme=scheme, ascii_only=ascii_only, queue_path=QUEUE_PATH)
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
        rest = ("the queue behind it is saved and resumes at the next start"
                if app.queue.path else "queued jobs behind it were dropped")
        sys.stdout.write(f"{app.runner.job.label} is still running in the backend; "
                         f"{rest}. Log: {LOG_PATH}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
