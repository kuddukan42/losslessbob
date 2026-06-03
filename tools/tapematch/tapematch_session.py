#!/usr/bin/env python3
"""tapematch_session.py — orchestrate a full tapematch analysis session.

Usage:
    python tapematch_session.py 1995-07-08
    python tapematch_session.py 1995-07-08 --dry-run
    python tapematch_session.py 1995-07-08 --no-tapematch
    python tapematch_session.py 1995-07-08 --report-only

Steps:
    1. Query losslessbob.db for LB entries matching the date
    2. Resolve disk paths from my_collection; fall back to DYLAN drive scan for any not found
    3. Clean examples/tapematch/ of existing folders
    4. Copy found folders to examples/tapematch/
    5. Run tapematch CLI (writes log + results.json), save full log
    6. Archive run to runs/TIMESTAMP_DATE/ with log, report, config, results.json
    7. Insert run/source/pair rows into observations.db
    8. Extract LB page commentary for each entry
    9. Write combined report to last_run_report.md
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

# ── paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent           # losslessbob/
DB_PATH      = PROJECT_ROOT / "data" / "losslessbob.db"
PAGES_DIR    = PROJECT_ROOT / "data" / "site" / "detail"
EXAMPLES_DIR = Path("/mnt/DATA0/examples/tapematch")
SEARCH_ROOTS = [Path("/mnt/DYLAN1"), Path("/mnt/DYLAN2"), Path("/mnt/DYLAN3")]
VENV_PYTHON  = PROJECT_ROOT / ".venv" / "bin" / "python3"
SESSION_DIR  = Path(__file__).parent
REPORT_PATH  = SESSION_DIR / "last_run_report.md"
LOG_PATH     = SESSION_DIR / "last_run.log"
OBS_DB_PATH  = SESSION_DIR / "observations.db"
RUNS_DIR     = SESSION_DIR / "runs"

AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".ape", ".m4a", ".mp3"}

TMP_BASE = Path("/mnt/DATA0/tmp")


# ── observations DB ────────────────────────────────────────────────────────────

OBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,   -- YYYYMMDD_HHMMSS
    concert_date    TEXT NOT NULL,
    location        TEXT,
    n_sources_db    INTEGER,            -- entries in losslessbob.db for this date
    n_sources_found INTEGER,            -- folders actually found on disk
    n_sources_ran   INTEGER,            -- folders included in tapematch run
    n_families      INTEGER,            -- distinct source families detected
    config_json     TEXT,               -- full config.yaml as JSON
    archive_dir     TEXT,               -- path to runs/RUN_ID/ archive folder
    run_at          TEXT,               -- ISO timestamp
    duration_sec    REAL                -- wall time for tapematch
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    concert_date    TEXT NOT NULL,
    lb_number       INTEGER,
    folder_name     TEXT,
    family_id       INTEGER,
    track_count     INTEGER,
    total_dur_sec   REAL,
    perf_dur_sec    REAL,
    trim_head_sec   REAL,
    trim_tail_sec   REAL,
    hf_ceiling_hz   REAL,
    noise_floor_db  REAL,
    dc_asymmetry    REAL,
    nyquist_capped  INTEGER,            -- 0/1 boolean
    speed_ppm       REAL,
    speed_kind      TEXT,               -- aligned/staircase/splice/constant-speed-offset/reference
    dominant_ext    TEXT,               -- .flac / .shn / .wav etc
    lb_rating       TEXT,               -- from LB page header
    lb_timing       TEXT,               -- from LB page header
    lb_source_text  TEXT,               -- full SOURCE/NOTE block from LB page
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS pairs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    concert_date        TEXT NOT NULL,
    lb_a                INTEGER,
    lb_b                INTEGER,
    folder_a            TEXT,
    folder_b            TEXT,
    corr                REAL,           -- residual cross-correlation (0-1)
    tapematch_verdict   TEXT,           -- same_family / different_family
    family_id_a         INTEGER,
    family_id_b         INTEGER,
    speed_ppm_a         REAL,
    speed_ppm_b         REAL,
    speed_kind_a        TEXT,
    speed_kind_b        TEXT,
    hf_ceiling_hz_a     REAL,
    hf_ceiling_hz_b     REAL,
    noise_floor_db_a    REAL,
    noise_floor_db_b    REAL,
    dc_asymmetry_a      REAL,
    dc_asymmetry_b      REAL,
    perf_dur_sec_a      REAL,
    perf_dur_sec_b      REAL,
    track_count_a       INTEGER,
    track_count_b       INTEGER,
    dominant_ext_a      TEXT,
    dominant_ext_b      TEXT,
    lb_says_same        INTEGER,        -- 1=yes 0=no NULL=silent/unknown
    lb_relation_text    TEXT,           -- snippet from LB page mentioning the other LB
    human_judgment      TEXT,           -- confirmed_same/confirmed_different/uncertain/lb_wrong (fill later)
    human_notes         TEXT,           -- free text annotation (fill later)
    run_at              TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"""

def open_obs_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(OBS_DB_PATH))
    conn.executescript(OBS_SCHEMA)
    conn.commit()
    return conn


# ── date helpers ───────────────────────────────────────────────────────────────

def iso_to_db_date(iso: str) -> str:
    """1995-07-08  →  7/8/95"""
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.month}/{d.day}/{str(d.year)[2:]}"


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── losslessbob DB queries ─────────────────────────────────────────────────────

def query_db(date_iso: str) -> tuple[str, list[int]]:
    """Return (location, [lb_numbers]) for the date, or ('', []) if none."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")
    db_date = iso_to_db_date(date_iso)
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT lb_number, location FROM entries WHERE date_str = ? ORDER BY lb_number",
        (db_date,),
    ).fetchall()
    conn.close()
    if not rows:
        return "", []
    return rows[0][1], [r[0] for r in rows]


def resolve_from_collection(lb_numbers: list[int]) -> tuple[dict[int, Path], list[int]]:
    """Look up disk_path for each LB number in my_collection."""
    conn = sqlite3.connect(str(DB_PATH))
    placeholders = ",".join("?" * len(lb_numbers))
    rows = conn.execute(
        f"SELECT lb_number, disk_path FROM my_collection WHERE lb_number IN ({placeholders})",
        lb_numbers,
    ).fetchall()
    conn.close()
    found: dict[int, Path] = {}
    for lb_num, disk_path in rows:
        p = Path(disk_path)
        if p.is_dir():
            found[lb_num] = p
    missing = [n for n in lb_numbers if n not in found]
    return found, missing


# ── helpers ────────────────────────────────────────────────────────────────────

def _lb_tag(lb_num: int) -> str:
    return f"LB-{lb_num:05d}"


def _has_audio(folder: Path) -> bool:
    try:
        return any(f.suffix.lower() in AUDIO_EXTS for f in folder.iterdir() if f.is_file())
    except PermissionError:
        return False


def _dominant_ext(folder: Path) -> str:
    counts: dict[str, int] = defaultdict(int)
    try:
        for f in folder.iterdir():
            if f.suffix.lower() in AUDIO_EXTS:
                counts[f.suffix.lower()] += 1
    except PermissionError:
        pass
    return max(counts, key=counts.__getitem__) if counts else ""


def scan_drives_for(lb_numbers: list[int], year: str) -> dict[int, Path]:
    """Fallback: scan DYLAN drives for LB numbers not in my_collection."""
    want = set(lb_numbers)
    found: dict[int, Path] = {}
    for root in SEARCH_ROOTS:
        if not root.exists() or not want:
            continue
        for folder in root.rglob("*"):
            if not folder.is_dir():
                continue
            try:
                if len(folder.relative_to(root).parts) > 5:
                    continue
            except ValueError:
                continue
            for n in list(want):
                if _lb_tag(n) in folder.name and _has_audio(folder):
                    found[n] = folder
                    want.discard(n)
            if not want:
                break
    return found


def find_lb_folders(lb_numbers: list[int], year: str) -> dict[int, Path]:
    """Resolve LB folder paths: my_collection first, drive scan as fallback.
    Private LBs (no local commentary page) are excluded automatically.
    """
    found, missing = resolve_from_collection(lb_numbers)
    if missing:
        found.update(scan_drives_for(missing, year))
    # Drop private LBs — no local page means no commentary to compare against
    private = [
        n for n, p in list(found.items())
        if any(part in str(p).upper() for part in ("PRIVATE", "NOTORRENT", "NO TORRENT"))
    ]
    for n in private:
        del found[n]
    if private:
        print(f"  Excluded (private/no-torrent): {', '.join(_lb_tag(n) for n in sorted(private))}")
    return found


# ── LB page parsing ────────────────────────────────────────────────────────────

def _strip_bittorrent_blocks(text: str) -> str:
    """Remove (a bittorrent from ...) blocks from curator text.

    These parentheticals describe what an uploader said about their own upload,
    not what the LB curator says about relationships between LB entries.
    Uses a balanced-paren walk so nested parens inside the description don't
    truncate the removal early.
    """
    marker = "(a bittorrent from "
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        idx = text.lower().find(marker, pos)
        if idx == -1:
            parts.append(text[pos:])
            break
        parts.append(text[pos:idx])
        depth = 0
        i = idx
        limit = min(idx + 3000, len(text))
        while i < limit:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        pos = i
    return "".join(parts)


def _page_text(lb_num: int) -> str:
    """Return curator-only plain text from a local LB page.

    Uses BeautifulSoup's full get_text() so bare text nodes between <hr/>
    separators (where key relationship notes like "same recording as LB-XXXX"
    often live) are included, then strips (a bittorrent from ...) parentheticals
    which describe other people's uploads rather than curator relationship notes.
    """
    page = PAGES_DIR / f"{_lb_tag(lb_num)}.html"
    if not page.exists():
        return ""
    html = page.read_text(errors="replace")
    if _BS4:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ", strip=True)
    else:
        text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return _strip_bittorrent_blocks(text)


def extract_lb_commentary(lb_num: int) -> str:
    """Return the commentary block from the local LB page."""
    page = PAGES_DIR / f"{_lb_tag(lb_num)}.html"
    if not page.exists():
        return "*(no local page)*"
    html = page.read_text(errors="replace")
    if _BS4:
        soup = BeautifulSoup(html, "lxml")
        # Older page format: td containing "SOURCE:"
        for td in soup.find_all("td"):
            t = td.get_text(separator=" ", strip=True)
            if re.search(r"SOURCE:", t, re.IGNORECASE):
                return re.sub(r"\s+", " ", t).strip()[:3000]
        # Most pages: commentary lives in the first substantial <p>
        for p in soup.find_all("p"):
            t = p.get_text(separator=" ", strip=True)
            if len(t) > 50:
                return re.sub(r"\s+", " ", t).strip()[:3000]
    # Plain-text fallbacks
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"SOURCE:.{20,3000}", text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(0)[:3000]
    m = re.search(r"<p[^>]*>(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
    if m:
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
        if len(t) > 50:
            return t[:3000]
    return "*(could not parse page)*"


def extract_lb_header(lb_num: int) -> dict[str, str]:
    """Extract rating/timing from LB page header table."""
    page = PAGES_DIR / f"{_lb_tag(lb_num)}.html"
    if not page.exists():
        return {}
    html = page.read_text(errors="replace")
    result: dict[str, str] = {}
    if _BS4:
        soup = BeautifulSoup(html, "lxml")
        for tr in soup.find_all("tr"):
            if tr.find("th") and "Date" in tr.get_text():
                data_row = tr.find_next_sibling("tr")
                if data_row:
                    cells = [td.get_text(strip=True) for td in data_row.find_all("td")]
                    result = dict(zip(["date", "location", "cdr", "rating", "timing"], cells))
                break
    return result


_SAME_RE = re.compile(
    r"same recording|same as|fingerprints.{0,40}match|"
    r"eac match|close match|\bidentical\b",
    re.IGNORECASE,
)
_DIFF_RE = re.compile(r"different recording|different from", re.IGNORECASE)


def extract_lb_relationship(lb_a: int, lb_b: int) -> tuple[int | None, str]:
    """Check LB-a's page for mentions of LB-b.

    Returns (lb_says_same, relation_text):
        lb_says_same = 1 if same, 0 if different, None if not mentioned.

    Iterates ALL occurrences of the LB number so that an early mention in a
    page header doesn't shadow a relationship note later in the commentary.
    """
    text = _page_text(lb_a)
    if not text:
        return None, ""

    pattern = rf"LB-0*{lb_b}\b"
    first_ctx = ""
    for m in re.finditer(pattern, text, re.IGNORECASE):
        start = max(0, m.start() - 250)
        end   = min(len(text), m.end() + 250)
        ctx   = text[start:end].strip()
        if not first_ctx:
            first_ctx = ctx
        if _SAME_RE.search(ctx):
            return 1, ctx
        if _DIFF_RE.search(ctx):
            return 0, ctx
        # ambiguous occurrence — keep iterating

    return None, first_ctx


# ── file ops ───────────────────────────────────────────────────────────────────

def clean_examples() -> None:
    for item in EXAMPLES_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink(missing_ok=True)


def copy_folders(folders: dict[int, Path]) -> None:
    for lb_num, src in sorted(folders.items()):
        dest = EXAMPLES_DIR / src.name
        print(f"  Copying {_lb_tag(lb_num)}: {src.name} …")
        shutil.copytree(str(src), str(dest))


# ── tapematch runner ───────────────────────────────────────────────────────────

def _clean_stale_tmp_dirs() -> None:
    """Delete any tapematch_* dirs left behind by a previously OOM-killed subprocess.

    cli.py registers atexit cleanup, but SIGKILL bypasses atexit.  Calling this
    before each new subprocess ensures orphaned memmaps don't accumulate on disk.
    """
    if not TMP_BASE.exists():
        return
    for d in TMP_BASE.glob("tapematch_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            print(f"  [cleanup] removed stale tmp dir: {d.name}")


def run_tapematch(json_out: Path) -> tuple[str, float]:
    """Run tapematch CLI. Returns (stdout_text, duration_sec)."""
    _clean_stale_tmp_dirs()
    cmd = [
        str(VENV_PYTHON), "-m", "tapematch.cli",
        str(EXAMPLES_DIR),
        "--config", str(SESSION_DIR / "config.yaml"),
        "--json-out", str(json_out),
    ]
    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=str(SESSION_DIR), capture_output=True, text=True)
    duration = time.monotonic() - t0
    output = result.stdout
    if result.returncode != 0:
        output += f"\n[STDERR]\n{result.stderr}"
    return output, duration


# ── run archiving ──────────────────────────────────────────────────────────────

def archive_run(run_id: str, date_iso: str, log_text: str, report_text: str,
                results_json: Path | None) -> Path:
    """Copy run artifacts into runs/RUN_ID/. Returns archive dir path."""
    arch = RUNS_DIR / f"{run_id}_{date_iso}"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "tapematch.log").write_text(log_text, encoding="utf-8")
    (arch / "report.md").write_text(report_text, encoding="utf-8")
    shutil.copy(SESSION_DIR / "config.yaml", arch / "config.yaml")
    if results_json and results_json.exists():
        shutil.copy(results_json, arch / "results.json")
    return arch


# ── DB insertion ───────────────────────────────────────────────────────────────

def insert_run(conn: sqlite3.Connection, run_id: str, date_iso: str, location: str,
               n_db: int, n_found: int, n_ran: int, n_families: int,
               config_json: str, archive_dir: str, run_at: str, duration_sec: float) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO runs
           (run_id, concert_date, location, n_sources_db, n_sources_found,
            n_sources_ran, n_families, config_json, archive_dir, run_at, duration_sec)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, date_iso, location, n_db, n_found, n_ran, n_families,
         config_json, archive_dir, run_at, duration_sec),
    )


def insert_sources(conn: sqlite3.Connection, run_id: str, date_iso: str,
                   results: dict, found_folders: dict[int, Path], run_at: str) -> None:
    for folder_name, s in results["sources"].items():
        lb_num = _lb_num_from_folder(folder_name)
        src_path = found_folders.get(lb_num, EXAMPLES_DIR / folder_name)
        dom_ext = _dominant_ext(EXAMPLES_DIR / folder_name)
        hdr = extract_lb_header(lb_num) if lb_num else {}
        commentary = extract_lb_commentary(lb_num) if lb_num else ""
        conn.execute(
            """INSERT INTO sources
               (run_id, concert_date, lb_number, folder_name, family_id,
                track_count, total_dur_sec, perf_dur_sec, trim_head_sec, trim_tail_sec,
                hf_ceiling_hz, noise_floor_db, dc_asymmetry, nyquist_capped,
                speed_ppm, speed_kind, dominant_ext,
                lb_rating, lb_timing, lb_source_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, date_iso, lb_num, folder_name, s["family_id"],
             s["track_count"], s["total_dur_sec"], s["perf_dur_sec"],
             s["trim_head_sec"], s["trim_tail_sec"],
             s["hf_ceiling_hz"], s["noise_floor_db"], s["dc_asymmetry"],
             int(s["nyquist_capped"]),
             s["speed_ppm"], s["speed_kind"], dom_ext,
             hdr.get("rating", ""), hdr.get("timing", ""), commentary),
        )


def insert_pairs(conn: sqlite3.Connection, run_id: str, date_iso: str,
                 results: dict, run_at: str) -> None:
    names  = results["correlation_matrix"]["names"]
    matrix = results["correlation_matrix"]["values"]
    srcs   = results["sources"]

    for i, j in combinations(range(len(names)), 2):
        na, nb = names[i], names[j]
        sa, sb = srcs[na], srcs[nb]
        lb_a = _lb_num_from_folder(na)
        lb_b = _lb_num_from_folder(nb)
        corr = matrix[i][j]
        same_family = sa["family_id"] == sb["family_id"]

        # Check both directions; prefer a definitive answer
        says_same_ab, rel_ab = extract_lb_relationship(lb_a, lb_b) if lb_a and lb_b else (None, "")
        says_same_ba, rel_ba = extract_lb_relationship(lb_b, lb_a) if lb_a and lb_b else (None, "")
        if says_same_ab is not None:
            lb_says_same, lb_rel = says_same_ab, rel_ab
        elif says_same_ba is not None:
            lb_says_same, lb_rel = says_same_ba, rel_ba
        else:
            lb_says_same, lb_rel = None, ""

        conn.execute(
            """INSERT INTO pairs
               (run_id, concert_date, lb_a, lb_b, folder_a, folder_b,
                corr, tapematch_verdict, family_id_a, family_id_b,
                speed_ppm_a, speed_ppm_b, speed_kind_a, speed_kind_b,
                hf_ceiling_hz_a, hf_ceiling_hz_b, noise_floor_db_a, noise_floor_db_b,
                dc_asymmetry_a, dc_asymmetry_b, perf_dur_sec_a, perf_dur_sec_b,
                track_count_a, track_count_b, dominant_ext_a, dominant_ext_b,
                lb_says_same, lb_relation_text, human_judgment, human_notes, run_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, date_iso, lb_a, lb_b, na, nb,
             corr, "same_family" if same_family else "different_family",
             sa["family_id"], sb["family_id"],
             sa["speed_ppm"], sb["speed_ppm"], sa["speed_kind"], sb["speed_kind"],
             sa["hf_ceiling_hz"], sb["hf_ceiling_hz"],
             sa["noise_floor_db"], sb["noise_floor_db"],
             sa["dc_asymmetry"], sb["dc_asymmetry"],
             sa["perf_dur_sec"], sb["perf_dur_sec"],
             sa["track_count"], sb["track_count"],
             _dominant_ext(EXAMPLES_DIR / na), _dominant_ext(EXAMPLES_DIR / nb),
             lb_says_same, lb_rel, None, None, run_at),
        )


def _lb_num_from_folder(folder_name: str) -> int | None:
    m = re.search(r"LB-(\d+)", folder_name)
    return int(m.group(1)) if m else None


# ── report writer ──────────────────────────────────────────────────────────────

def _lb_source_snippet(lb_num: int, max_len: int = 90) -> str:
    """Return a short first-line source description from the LB commentary."""
    text = extract_lb_commentary(lb_num)
    if text.startswith("*("):
        return ""
    # Trim at first newline or "> " lineage arrow, whichever comes first
    for sep in ("\n", " > ", " >,"):
        idx = text.find(sep)
        if 0 < idx < max_len:
            text = text[:idx]
            break
    text = text.strip().rstrip(",;")
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "…"
    return text


def build_report(date_iso: str, location: str, lb_numbers: list[int],
                 found_folders: dict[int, Path], tapematch_output: str) -> str:
    lines: list[str] = [
        f"# tapematch session — {date_iso} — {location}",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Coverage",
        f"DB entries: **{len(lb_numbers)}** | Found on disk: **{len(found_folders)}**",
        "",
        "| LB | On disk | Rating | Timing | Source | Folder |",
        "|----|---------|--------|--------|--------|--------|",
    ]
    for n in lb_numbers:
        on_disk = "✓" if n in found_folders else "—"
        folder  = found_folders[n].name if n in found_folders else "*(not found)*"
        hdr     = extract_lb_header(n) if n in found_folders else {}
        rating  = hdr.get("rating", "")
        timing  = hdr.get("timing", "")
        snippet = _lb_source_snippet(n) if n in found_folders else ""
        lines.append(f"| {_lb_tag(n)} | {on_disk} | {rating} | {timing} | {snippet} | {folder} |")

    lines += ["", "## tapematch output", "```", tapematch_output.strip(), "```", "",
              "## LB page commentary"]

    for n in lb_numbers:
        if n not in found_folders:
            continue
        hdr    = extract_lb_header(n)
        rating = hdr.get("rating", "")
        timing = hdr.get("timing", "")
        meta   = (f" | rating: {rating}" if rating else "") + (f" | timing: {timing}" if timing else "")
        lines += ["", f"### {_lb_tag(n)}{meta}", extract_lb_commentary(n)]

    return "\n".join(lines)


# ── main ───────────────────────────────────────────────────────────────────────

def suggest_dates(n: int = 20, min_entries: int = 3, max_entries: int = 5) -> None:
    """Print candidate concert dates: collected + paged + not yet analysed."""
    # LB numbers that have a local page
    paged = {
        int(m.group(1))
        for p in PAGES_DIR.glob("LB-*.html")
        if (m := re.search(r"LB-(\d+)\.html", p.name))
    }

    # Already-run dates from observations DB
    done: set[str] = set()
    if OBS_DB_PATH.exists():
        conn = open_obs_db()
        done = {r[0] for r in conn.execute("SELECT DISTINCT concert_date FROM runs").fetchall()}
        conn.close()

    # Query: dates where 3–5 entries are both in my_collection AND have a local page
    lb_conn = sqlite3.connect(str(DB_PATH))
    rows = lb_conn.execute("""
        SELECT e.date_str, e.location, GROUP_CONCAT(e.lb_number ORDER BY e.lb_number) as lbs
        FROM entries e
        JOIN my_collection mc ON e.lb_number = mc.lb_number
        GROUP BY e.date_str
        ORDER BY e.date_str
    """).fetchall()
    lb_conn.close()

    candidates = []
    for date_str, location, lbs_csv in rows:
        lbs = [int(x) for x in lbs_csv.split(",")]
        paged_lbs = [lb for lb in lbs if lb in paged]
        if min_entries <= len(paged_lbs) <= max_entries:
            try:
                d = datetime.strptime(date_str, "%m/%d/%y")
                iso = d.strftime("%Y-%m-%d")
            except ValueError:
                continue
            if iso in done:
                continue
            candidates.append((iso, len(paged_lbs), location, paged_lbs))

    if not candidates:
        print("No candidates found.")
        return

    import random
    random.shuffle(candidates)
    print(f"{'Date':<12}  {'N':>2}  {'Location':<45}  LBs")
    print("-" * 90)
    for iso, cnt, loc, lbs in candidates[:n]:
        lb_str = ", ".join(f"LB-{lb:05d}" for lb in lbs)
        print(f"{iso:<12}  {cnt:>2}  {loc[:45]:<45}  {lb_str}")


def get_year_dates(year: str, min_entries: int = 2) -> list[tuple[str, int, str, list[int]]]:
    """Return collected+paged concert dates for a year, sorted chronologically.

    Returns list of (date_iso, n_paged_entries, location, lb_numbers).
    Only includes dates where at least min_entries LBs are both in
    my_collection and have a local HTML page.  Non-concert entries
    (studio, rehearsal, interview, radio, tv, etc.) are excluded.
    """
    paged = {
        int(m.group(1))
        for p in PAGES_DIR.glob("LB-*.html")
        if (m := re.search(r"LB-(\d+)\.html", p.name))
    }
    lb_conn = sqlite3.connect(str(DB_PATH))
    rows = lb_conn.execute("""
        SELECT e.date_str, e.location, GROUP_CONCAT(e.lb_number ORDER BY e.lb_number) as lbs
        FROM entries e
        JOIN my_collection mc ON e.lb_number = mc.lb_number
        WHERE e.lb_category = 'concert'
        GROUP BY e.date_str
        ORDER BY e.date_str
    """).fetchall()
    lb_conn.close()

    results = []
    for date_str, location, lbs_csv in rows:
        try:
            d = datetime.strptime(date_str, "%m/%d/%y")
            iso = d.strftime("%Y-%m-%d")
        except ValueError:
            continue
        if not iso.startswith(year):
            continue
        lbs = [int(x) for x in lbs_csv.split(",")]
        paged_lbs = [lb for lb in lbs if lb in paged]
        if len(paged_lbs) >= min_entries:
            results.append((iso, len(paged_lbs), location, paged_lbs))
    return sorted(results, key=lambda x: x[0])


def run_date(date_iso: str, dry_run: bool = False,
             no_tapematch: bool = False, report_only: bool = False) -> int:
    """Run a full tapematch session for one concert date."""
    run_id  = make_run_id()
    run_at  = datetime.now().isoformat()
    year    = date_iso[:4]
    print(f"=== tapematch session: {date_iso}  [{run_id}] ===")

    # 1. DB lookup
    print("\n[1] Querying DB …")
    location, lb_numbers = query_db(date_iso)
    if not lb_numbers:
        print(f"  No entries for {date_iso} ({iso_to_db_date(date_iso)})", file=sys.stderr)
        return 1
    print(f"  {len(lb_numbers)} entries — {location}")
    for n in lb_numbers:
        print(f"    {_lb_tag(n)}")

    # 2. Resolve paths
    print("\n[2] Resolving paths from my_collection …")
    found_folders = find_lb_folders(lb_numbers, year)
    missing = [n for n in lb_numbers if n not in found_folders]
    print(f"  Found {len(found_folders)}/{len(lb_numbers)}")
    for n, p in sorted(found_folders.items()):
        print(f"    {_lb_tag(n)}: {p}")
    if missing:
        print(f"  Not found: {', '.join(_lb_tag(n) for n in missing)}")
    if not found_folders:
        print("  No folders found — cannot proceed.", file=sys.stderr)
        return 1
    if len(found_folders) < 2:
        print(f"  Only {len(found_folders)} folder found — need ≥2 sources for tapematch. Skipping.")
        return 2

    if dry_run:
        print("\n[DRY RUN] — stopping before clean/copy/run.")
        return 0

    # ── report-only: skip clean/copy/run ──────────────────────────────────────
    if report_only:
        json_path = SESSION_DIR / "last_results.json"
        log_text  = LOG_PATH.read_text() if LOG_PATH.exists() else "(no log found)"
        print("\n[REPORT ONLY] — using existing last_run.log + last_results.json")
        report_text = build_report(date_iso, location, lb_numbers, found_folders, log_text)
        REPORT_PATH.write_text(report_text, encoding="utf-8")
        arch = archive_run(run_id, date_iso, log_text, report_text,
                           json_path if json_path.exists() else None)
        if json_path.exists():
            results = json.loads(json_path.read_text())
            _log_to_obs_db(run_id, run_at, date_iso, location, lb_numbers,
                           found_folders, results, 0.0, arch)
        print(f"\nReport → {REPORT_PATH}")
        return 0

    # 3. Clean
    print(f"\n[3] Cleaning {EXAMPLES_DIR} …")
    clean_examples()

    # 4. Copy
    print(f"\n[4] Copying {len(found_folders)} folders to {EXAMPLES_DIR} …")
    copy_folders(found_folders)

    # 5. tapematch
    json_path = SESSION_DIR / "last_results.json"
    duration  = 0.0
    if no_tapematch:
        log_text = LOG_PATH.read_text() if LOG_PATH.exists() else "(tapematch skipped)"
        print("\n[5] tapematch skipped — reusing existing log")
    else:
        print("\n[5] Running tapematch …")
        json_path.unlink(missing_ok=True)  # clear stale results from any prior run
        log_text, duration = run_tapematch(json_path)
        LOG_PATH.write_text(log_text)
        print(log_text)

    # 6. Archive
    print("\n[6] Archiving run …")
    report_text = build_report(date_iso, location, lb_numbers, found_folders, log_text)
    arch = archive_run(run_id, date_iso, log_text, report_text,
                       json_path if json_path.exists() else None)
    print(f"  Archive → {arch}")

    # 7. Log to observations DB
    if json_path.exists():
        print("\n[7] Logging to observations.db …")
        results = json.loads(json_path.read_text())
        _log_to_obs_db(run_id, run_at, date_iso, location, lb_numbers,
                       found_folders, results, duration, arch)
    else:
        print("\n[7] No results.json — skipping DB logging (tapematch may have been skipped)")

    # 8. Write report
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\nReport → {REPORT_PATH}")

    return 0


def year_run(year: str, min_entries: int = 2, dry_run: bool = False) -> int:
    """Process all candidate dates for a year, skipping already-done ones.

    Each date is run as a fresh subprocess so that Python heap, page cache,
    and all OS resources are fully released between dates.  The parent process
    only orchestrates: build the todo list, spawn, wait, move on.

    Resumable: dates already recorded in observations.db are skipped.
    Ctrl+C cleanly aborts the loop; re-run with the same --year to continue.
    """
    dates = get_year_dates(year, min_entries)

    done: set[str] = set()
    if OBS_DB_PATH.exists():
        conn = open_obs_db()
        done = {r[0] for r in conn.execute("SELECT DISTINCT concert_date FROM runs").fetchall()}
        conn.close()

    todo = [(iso, n, loc) for iso, n, loc, _ in dates if iso not in done]
    n_skip = len(dates) - len(todo)

    print(f"=== tapematch year run: {year} ===")
    print(f"  Dates with ≥{min_entries} collected+paged entries : {len(dates)}")
    print(f"  Already done (skipping)                          : {n_skip}")
    print(f"  To process                                       : {len(todo)}")

    if not todo:
        print("  Nothing to do.")
        return 0

    script = str(Path(__file__).resolve())

    for idx, (iso, n, loc) in enumerate(todo, 1):
        print(f"\n{'='*60}")
        print(f"  [{idx}/{len(todo)}]  {iso}  —  {loc[:50]}  ({n} entries)")
        print(f"{'='*60}")
        cmd = [str(VENV_PYTHON), script, iso]
        if dry_run:
            cmd.append("--dry-run")
        try:
            result = subprocess.run(cmd, check=False)
            rc = result.returncode
            if rc == 2:
                print(f"  [SKIP] {iso}: only 1 source folder on disk")
            elif rc != 0:
                print(f"  [WARN] {iso}: run_date returned rc={rc} — continuing")
        except KeyboardInterrupt:
            print(f"\nInterrupted at {iso} (date {idx}/{len(todo)}).")
            print(f"Resume:  tapematch_session.py --year {year}")
            return 130

    print(f"\n=== Year {year}: processed {len(todo)} date(s). ===")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a full tapematch analysis session for a concert date")
    ap.add_argument("date", nargs="?", help="Concert date YYYY-MM-DD  (e.g. 1995-07-08)")
    ap.add_argument("--suggest", action="store_true",
                    help="List candidate dates (3–5 collected+paged entries, not yet analysed)")
    ap.add_argument("--suggest-n", type=int, default=20, metavar="N",
                    help="How many candidates to show with --suggest (default 20)")
    ap.add_argument("--year", metavar="YYYY",
                    help="Process all candidate dates for a year, skipping already-done ones")
    ap.add_argument("--min-entries", type=int, default=2, metavar="N",
                    help="Minimum collected+paged entries per date for --year (default 2)")
    ap.add_argument("--dry-run",     action="store_true",
                    help="Show what would be done without cleaning/copying/running")
    ap.add_argument("--no-tapematch", action="store_true",
                    help="Skip the tapematch run (still cleans and copies folders)")
    ap.add_argument("--report-only", action="store_true",
                    help="Skip clean/copy/run; regenerate report+DB from existing last_run.log/results.json")
    args = ap.parse_args(argv)

    if args.suggest:
        suggest_dates(n=args.suggest_n)
        return 0

    if args.year:
        return year_run(args.year, args.min_entries, dry_run=args.dry_run)

    if not args.date:
        ap.error("date is required unless --suggest or --year is used")

    return run_date(args.date,
                    dry_run=args.dry_run,
                    no_tapematch=args.no_tapematch,
                    report_only=args.report_only)


def _log_to_obs_db(run_id: str, run_at: str, date_iso: str, location: str,
                   lb_numbers: list[int], found_folders: dict[int, Path],
                   results: dict, duration: float, arch: Path) -> None:
    import yaml
    cfg_path = SESSION_DIR / "config.yaml"
    cfg_json = json.dumps(results.get("config", {}))

    conn = open_obs_db()
    try:
        insert_run(
            conn, run_id, date_iso, location,
            n_db=len(lb_numbers),
            n_found=len(found_folders),
            n_ran=len(results["sources"]),
            n_families=results["n_families"],
            config_json=cfg_json,
            archive_dir=str(arch),
            run_at=run_at,
            duration_sec=duration,
        )
        insert_sources(conn, run_id, date_iso, results, found_folders, run_at)
        insert_pairs(conn, run_id, date_iso, results, run_at)
        conn.commit()
        n_pairs = len(results["correlation_matrix"]["names"])
        n_pairs = n_pairs * (n_pairs - 1) // 2
        print(f"  Logged: 1 run, {len(results['sources'])} sources, {n_pairs} pairs")
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
