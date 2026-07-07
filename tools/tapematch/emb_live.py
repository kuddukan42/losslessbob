#!/usr/bin/env python3
"""emb_live.py — populate ``pairs.emb_score`` / ``pairs.emb_score_global`` during a
live tapematch session so ``addon_links.rule_d`` can fire live (TODO-200).

Historically the Tier B embedding scores were only ever written offline
(``nmfp_embed.py`` -> ``emb_score_pairs.py`` -> ``persist_emb_scores.py``): a live
re-run inserted fresh ``pairs`` rows with NULL emb, so Rule D abstained on that
date until the batch post-process re-ran (TIER_B_FULLSET_REPORT.md, Caveat 1).

This module closes that gap. Called once from ``tapematch_session._log_to_obs_db``
immediately after ``insert_pairs`` (with the same open connection, before commit),
it:

    1. ensures a per-source embedding cache exists — for cache misses it invokes
       ``nmfp_embed.py`` under the isolated ``.venv-nmfp`` TF env (the main
       ``.venv`` cannot import TensorFlow);
    2. scores every cross-source pair of the session with the exact conventions of
       ``emb_score_pairs.score_pair`` (aligned +/-2s -> ``emb_score``; global
       cosine-max -> ``emb_score_global``);
    3. writes those scores onto the session's just-inserted rows (keyed by
       ``run_id``), never overwriting a non-NULL value with NULL.

It is a no-op unless BOTH ``addon_links.rule_d.enabled`` and
``addon_links.rule_d.live_embed`` are true. Every failure mode (missing
``.venv-nmfp``, extraction crash/timeout, uncached source) degrades to leaving the
emb columns NULL — which makes Rule D abstain, the safe default.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import subprocess
import sys
import tempfile
from itertools import combinations
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import emb_score_pairs as ESP  # noqa: E402  (reuse the exact per-pair scoring)

CONFIG_PATH = _HERE / "config.yaml"
CACHE_DIR = _HERE / "embed_cache"
TMP_DIR = _HERE / "tmp"
VENV_NMFP_PY = _HERE / ".venv-nmfp" / "bin" / "python"
NMFP_EMBED = _HERE / "nmfp_embed.py"

# nmfp decodes each whole performance and runs a model forward on every 1s window;
# generous so a multi-source date never times out under normal load.
EXTRACT_TIMEOUT_SEC = 3600

log = logging.getLogger("emb_live")

_LB_RE = re.compile(r"LB-(\d+)")


def sources_from_results(results: dict, found_folders: dict[int, Path]) -> list[dict]:
    """Build the per-source metadata list from a session ``results`` dict.

    Mirrors the ``embed_eval_set.json``-shaped source records that
    ``nmfp_embed.py`` consumes (``lb`` + speed/trim/duration fields), reading
    them straight from ``results["sources"]`` (keyed by folder name) and mapping
    each folder to its LB number via ``found_folders``.

    Args:
        results: The tapematch results dict; ``results["sources"]`` maps a folder
            name to that source's measured metadata.
        found_folders: Mapping of LB number to its resolved audio folder ``Path``
            (its ``.name`` is the folder-name key used in ``results``).

    Returns:
        A list of source dicts, one per resolved source, each carrying ``lb`` and
        the ``trim_head_sec`` / ``perf_dur_sec`` / ``total_dur_sec`` / ``speed_ppm``
        fields ``nmfp_embed.py`` reads. Sources whose folder yields no LB number
        are skipped (they would be unresolvable and unscorable anyway).
    """
    name_to_lb: dict[str, int] = {p.name: lb for lb, p in found_folders.items()}
    out: list[dict] = []
    for folder_name, s in (results.get("sources") or {}).items():
        lb = name_to_lb.get(folder_name)
        if lb is None:
            m = _LB_RE.search(folder_name)
            lb = int(m.group(1)) if m else None
        if lb is None:
            continue
        out.append({
            "lb": int(lb),
            "folder": folder_name,
            "trim_head_sec": s.get("trim_head_sec"),
            "perf_dur_sec": s.get("perf_dur_sec"),
            "total_dur_sec": s.get("total_dur_sec"),
            "speed_ppm": s.get("speed_ppm"),
        })
    return out


def _missing_sources(date_iso: str, sources: list[dict], cache_dir: Path) -> list[dict]:
    """Sources with no ``<cache_dir>/<date>/LB<lb>.npz`` embedding cache yet."""
    return [s for s in sources
            if not (cache_dir / date_iso / f"LB{s['lb']}.npz").exists()]


def _extract_missing(date_iso: str, missing: list[dict], cache_dir: Path) -> None:
    """Run ``nmfp_embed.py`` for cache-missing sources; never raises.

    Writes a temporary ``embed_eval_set.json``-shaped worklist under ``tmp/``
    (project-scoped, never ``/tmp``) and invokes ``nmfp_embed.py`` under the
    isolated ``.venv-nmfp`` env. A missing venv, non-zero exit, timeout, or any
    other failure is logged as a warning and swallowed: the affected sources stay
    uncached, so their pairs score NULL and Rule D abstains (the safe default).
    """
    if not VENV_NMFP_PY.exists():
        log.warning("emb_live: %s absent — skipping embedding extraction; %d source(s) "
                    "stay NULL (Rule D abstains).", VENV_NMFP_PY, len(missing))
        return

    worklist = {
        "spec": "emb_live live-session worklist (TODO-200)",
        "sources": {date_iso: missing},
    }
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(TMP_DIR), prefix=f"emb_worklist_{date_iso}_",
            suffix=".json", delete=False,
        ) as fh:
            json.dump(worklist, fh)
            tmp_path = Path(fh.name)

        cmd = [str(VENV_NMFP_PY), str(NMFP_EMBED),
               "--eval-set", str(tmp_path), "--cache", str(cache_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=EXTRACT_TIMEOUT_SEC)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            log.warning("emb_live: nmfp_embed exited %d; some sources may stay NULL. "
                        "tail: %s", proc.returncode, tail)
    except subprocess.TimeoutExpired:
        log.warning("emb_live: nmfp_embed timed out after %ds; sources stay NULL "
                    "(Rule D abstains).", EXTRACT_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001  (any failure -> NULL emb, which is safe)
        log.warning("emb_live: nmfp_embed failed (%s); sources stay NULL.", exc)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _write_pair(conn: sqlite3.Connection, run_id: str, lb_lo: int, lb_hi: int,
                tol2: float | None, tol0: float | None, counts: dict[str, int]) -> None:
    """UPDATE one session pair row, never writing NULL over a non-NULL value."""
    row = conn.execute(
        "SELECT emb_score, emb_score_global FROM pairs "
        "WHERE run_id = ? AND lb_a = ? AND lb_b = ?",
        (run_id, lb_lo, lb_hi),
    ).fetchone()
    if row is None:
        return
    existing = {"emb_score": row[0], "emb_score_global": row[1]}
    for value, column in ((tol2, "emb_score"), (tol0, "emb_score_global")):
        if value is None:
            # Never overwrite a (possibly already-populated) column with NULL.
            counts["skipped_null"] += 1
            continue
        value = float(value)
        if existing[column] is not None and existing[column] == value:
            continue  # already correct
        conn.execute(
            f"UPDATE pairs SET {column} = ? WHERE run_id = ? AND lb_a = ? AND lb_b = ?",
            (value, run_id, lb_lo, lb_hi),
        )
        counts["updated"] += 1


def _score_and_write(conn: sqlite3.Connection, run_id: str, date_iso: str,
                     sources: list[dict], cache_dir: Path) -> dict[str, int]:
    """Score every cross-source pair and write onto this session's rows."""
    counts = {"scored": 0, "updated": 0, "skipped_null": 0, "self_skipped": 0}
    lbs = sorted({int(s["lb"]) for s in sources if s.get("lb") is not None})
    src_cache: dict[tuple[str, int], tuple | None] = {}
    for lb_a, lb_b in combinations(lbs, 2):
        lb_lo, lb_hi = min(lb_a, lb_b), max(lb_a, lb_b)
        if lb_lo == lb_hi:  # self-pair: unmeasurable by this signal, never link
            counts["self_skipped"] += 1
            continue
        tol2, tol0 = ESP.score_pair(date_iso, lb_lo, lb_hi, cache_dir, src_cache)
        counts["scored"] += 1
        _write_pair(conn, run_id, lb_lo, lb_hi, tol2, tol0, counts)
    return counts


def populate_live_emb_scores(
    conn: sqlite3.Connection, run_id: str, date_iso: str, sources: list[dict],
    *, config_path: Path = CONFIG_PATH, cache_dir: Path = CACHE_DIR,
) -> dict[str, int]:
    """Compute and store live embedding scores for one session's pairs (TODO-200).

    No-op unless ``addon_links.rule_d`` is both ``enabled`` and ``live_embed``. When
    active it ensures the per-source embedding cache (invoking ``nmfp_embed.py``
    under ``.venv-nmfp`` for misses), scores every cross-source pair via
    ``emb_score_pairs.score_pair``, and writes ``emb_score`` / ``emb_score_global``
    onto the session's just-inserted ``pairs`` rows. Does not commit — the caller
    owns the transaction. Every failure degrades to leaving emb columns NULL, so
    Rule D abstains rather than mis-merges.

    Args:
        conn: Open ``observations.db`` connection with this session's ``pairs``
            rows already inserted (same transaction, uncommitted is fine).
        run_id: The session's run id; scopes the ``UPDATE`` to its own rows.
        date_iso: Concert date ``YYYY-MM-DD``.
        sources: Per-source metadata list (see :func:`sources_from_results`).
        config_path: ``config.yaml`` to read the ``rule_d`` flags from.
        cache_dir: ``embed_cache`` directory root.

    Returns:
        A small counters dict for logging: ``status`` (``"disabled"`` /
        ``"no_sources"`` / ``"ok"``) plus ``scored`` / ``updated`` /
        ``skipped_null`` / ``self_skipped`` when scoring ran.
    """
    try:
        cfg = yaml.safe_load(config_path.read_text()) or {}
    except OSError as exc:
        log.warning("emb_live: cannot read %s (%s); treating as disabled.", config_path, exc)
        return {"status": "disabled"}
    rule_d = (cfg.get("addon_links", {}) or {}).get("rule_d", {}) or {}
    if not rule_d.get("enabled") or not rule_d.get("live_embed"):
        return {"status": "disabled"}

    if len([s for s in sources if s.get("lb") is not None]) < 2:
        return {"status": "no_sources"}

    missing = _missing_sources(date_iso, sources, cache_dir)
    if missing:
        _extract_missing(date_iso, missing, cache_dir)

    counts = _score_and_write(conn, run_id, date_iso, sources, cache_dir)
    counts["status"] = "ok"
    log.info("emb_live %s: scored=%d updated=%d skipped_null=%d",
             date_iso, counts["scored"], counts["updated"], counts["skipped_null"])
    return counts
