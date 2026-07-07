#!/usr/bin/env python3
"""audit_fn.py — Task 1 (Tier 0) FN forensic audit + label-noise quantification.

Implements ``instructions/CC_TAPEMATCH_ADDON.md`` Task 1: the corr<0.05 false-negative
population (frozen-set positives the current precision-safe config still verdicts
``different_family``) conflates two populations — (a) true same-lineage pairs whose
HF fine structure was destroyed by lossy/band-limited lineage, and (b) curator label
noise (different recordings mislabeled as the same family). This script:

  1. Recomputes the *current* FN set faithfully (same machinery as
     ``regression.py score --cached``: ``tapematch.verdict.cluster_verdicts`` over
     stored raw metrics with the committed ``config.yaml``), restricted to
     ``corr < 0.05`` (the population the spec extrapolates over).
  2. Draws a stratified sample of 60: 20 speed-corrected / 20 speed-unknown /
     20 staircase-involved, secondarily stratified on
     |hf_ceiling_a - hf_ceiling_b| (>1 kHz vs <=1 kHz).
  3. For each sampled pair, builds an evidence dossier (LB source texts, curator
     relation text, per-side raw metrics, a throwaway 4-band envelope-correlation
     quick check decoded directly from disk — no session/staging-dir involvement,
     so the CONCURRENCY HAZARD in CALIBRATION_PROGRESS.md does not apply here) and
     a heuristic ``label_assessment`` verdict.
  4. Writes ``FN_AUDIT_REPORT.md`` (dossier + headline label-noise-rate table with a
     Wilson 95% CI extrapolated to the corr<0.05 population, and the re-based recall
     ceiling this implies).
  5. Flags every ``suspect-label`` pair via ``pairs.label_suspect = 1`` (nullable
     INTEGER column; NULL means not-assessed, never written as 0 — see
     ``tapematch_session.open_obs_db``). Frozen-set labels themselves are never
     edited in place.

Read-only against audio (a short direct-decode window per source, not a tapematch
session); read/write against observations.db only for the new label_suspect column.

Usage:
    .venv/bin/python3 tools/tapematch/audit_fn.py
    .venv/bin/python3 tools/tapematch/audit_fn.py --skip-audio   # dossier only, no envelope check
    .venv/bin/python3 tools/tapematch/audit_fn.py --seed 7 --n-per-category 20
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import regression as R  # noqa: E402
import tapematch_session as TS  # noqa: E402
from tapematch import ingest as I  # noqa: E402
from tapematch import match as M  # noqa: E402
from tapematch import audio as A  # noqa: E402
from tapematch import verdict as V  # noqa: E402

logger = logging.getLogger("audit_fn")

OBS_DB_PATH = _HERE / "observations.db"
CONFIG_PATH = _HERE / "config.yaml"
REPORT_PATH = _HERE / "FN_AUDIT_REPORT.md"

CORR_THRESHOLD = 0.05          # population of interest: FN with corr < this
HF_GAP_SPLIT_HZ = 1000.0       # secondary stratification split
DEFAULT_N_PER_CATEGORY = 20
DEFAULT_SEED = 42

# Throwaway 4-band envelope-corr quick check (Task 1.2; see Task 4 math in the
# spec for the production version). Direct ffmpeg window decode — bypasses the
# shared staging dir entirely, so it does NOT trigger the live-session
# concurrency hazard documented in CALIBRATION_PROGRESS.md.
QC_SR_HZ = 16000
QC_WINDOW_SEC = 90.0
QC_MAX_LAG_SEC = 20.0
QC_TRACK_SKIP_SEC = 15.0       # skip past track-start fades/clicks
QC_N_BANDS = 4
QC_LO_HZ = 200.0
QC_HI_CAP_HZ = 4000.0
QC_RELIABLE_SPEED_KINDS = {"aligned", "constant-speed-offset", "reference"}


# ── FN population ────────────────────────────────────────────────────────────

def _current_fn_population(conn) -> tuple[dict, list[dict]]:
    """Return (frozen, fn_rows) where fn_rows are corr<0.05 FN pairs under the
    *current committed* config (config.yaml), computed the same way
    ``regression.py score --cached`` computes the frozen-set confusion matrix.

    Each fn_row dict carries: id, run_id, concert_date, lb_a, lb_b, corr,
    speed_kind_a/b, speed_ppm_a/b, hf_ceiling_hz_a/b, noise_floor_db_a/b,
    dc_asymmetry_a/b, perf_dur_sec_a/b, track_count_a/b, dominant_ext_a/b,
    lb_says_same, lb_relation_text.
    """
    frozen = R._load_frozen()
    truth_map = R._truth_map(frozen)
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    lineage = V.load_lineage_pairs(R.LB_DB_PATH) if R.LB_DB_PATH.exists() else set()
    frozen_dates = R._dates_of(frozen)
    cols = R._pair_columns(conn)

    cand_pred: dict[tuple, bool] = {}
    for date in sorted(frozen_dates):
        cp, _recomputed = R._candidate_verdicts_for_date(conn, cols, date, cfg, lineage, cfg)
        cand_pred.update(cp)

    fn_keys = {k for k, truth in truth_map.items() if truth == 1 and not cand_pred.get(k, False)}
    logger.info("frozen positives=%d  current FN (all corr)=%d", sum(truth_map.values()), len(fn_keys))

    pos_by_key: dict[tuple, list[str]] = {}
    for a, b, date in frozen["positives"]:
        pos_by_key.setdefault((min(a, b), max(a, b)), []).append(date)

    row_cols = [
        "id", "run_id", "concert_date", "lb_a", "lb_b", "corr",
        "speed_kind_a", "speed_kind_b", "speed_ppm_a", "speed_ppm_b",
        "hf_ceiling_hz_a", "hf_ceiling_hz_b", "noise_floor_db_a", "noise_floor_db_b",
        "dc_asymmetry_a", "dc_asymmetry_b", "perf_dur_sec_a", "perf_dur_sec_b",
        "track_count_a", "track_count_b", "dominant_ext_a", "dominant_ext_b",
        "lb_says_same", "lb_relation_text",
    ]
    sel = ", ".join(row_cols)
    fn_rows: list[dict] = []
    for key in fn_keys:
        for date in pos_by_key.get(key, []):
            r = conn.execute(
                f"SELECT {sel} FROM latest_pairs WHERE concert_date=? AND lb_a=? AND lb_b=?",
                (date, key[0], key[1]),
            ).fetchone()
            if r is None:
                continue
            row = dict(zip(row_cols, r))
            if row["corr"] is None or row["corr"] >= CORR_THRESHOLD:
                continue
            fn_rows.append(row)

    logger.info("corr<%.2f FN population=%d", CORR_THRESHOLD, len(fn_rows))
    return frozen, fn_rows


def _speed_category(row: dict) -> str:
    ska, skb = row.get("speed_kind_a"), row.get("speed_kind_b")
    if ska == "staircase/splice" or skb == "staircase/splice":
        return "staircase"
    if ska == "speed-unknown" or skb == "speed-unknown":
        return "speed-unknown"
    return "speed-corrected"


def _hf_bucket(row: dict) -> str:
    a, b = row.get("hf_ceiling_hz_a"), row.get("hf_ceiling_hz_b")
    if a is None or b is None:
        return "<=1kHz"  # unknown gap treated as the non-distinguishing bucket
    return ">1kHz" if abs(a - b) > HF_GAP_SPLIT_HZ else "<=1kHz"


def _stratified_sample(fn_rows: list[dict], n_per_category: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    buckets: dict[str, dict[str, list[dict]]] = {}
    for row in fn_rows:
        cat = _speed_category(row)
        hf = _hf_bucket(row)
        buckets.setdefault(cat, {}).setdefault(hf, []).append(row)

    sample: list[dict] = []
    for cat in ("speed-corrected", "speed-unknown", "staircase"):
        cat_buckets = buckets.get(cat, {})
        hi = list(cat_buckets.get(">1kHz", []))
        lo = list(cat_buckets.get("<=1kHz", []))
        rng.shuffle(hi)
        rng.shuffle(lo)
        half = n_per_category // 2
        take_hi = min(half, len(hi))
        take_lo = min(n_per_category - take_hi, len(lo))
        picked = hi[:take_hi] + lo[:take_lo]
        remaining = n_per_category - len(picked)
        if remaining > 0:
            leftover = hi[take_hi:] + lo[take_lo:]
            rng.shuffle(leftover)
            picked += leftover[:remaining]
        if len(picked) < n_per_category:
            logger.warning("category %s: only %d/%d pairs available (population exhausted)",
                            cat, len(picked), n_per_category)
        for row in picked:
            row["_category"] = cat
            row["_hf_bucket"] = _hf_bucket(row)
        sample.extend(picked)
    return sample


# ── LB source text ───────────────────────────────────────────────────────────

def _source_text(conn, run_id: str, concert_date: str, lb_number: int) -> str:
    r = conn.execute(
        "SELECT lb_source_text FROM sources WHERE run_id=? AND concert_date=? AND lb_number=?",
        (run_id, concert_date, lb_number),
    ).fetchone()
    return (r[0] or "") if r else ""


# ── taper / lineage heuristics ───────────────────────────────────────────────

_DIFF_RECORDING_RE = re.compile(
    r"(?:this|it)\s+is\s+a\s+different\s+recording"
    r"|not\s+the\s+same\s+recording"
    r"|different\s+recording\s+(?:than|from)"
    r"|different\s+source\s+(?:than|from)"
    r"|not\s+the\s+same\s+show",
    re.IGNORECASE,
)


def _explicit_different_recording(row: dict, text_a: str, text_b: str) -> tuple[bool, str | None]:
    """Highest-priority suspect signal: curator text directly asserting the two
    LBs are different recordings. ``lb_relation_text`` is already pair-scoped
    (extracted by matching the counterpart's LB number), so any hit there is
    trusted outright. Raw ``lb_source_text`` is scanned too, but only accepted
    if the counterpart's LB number appears near the match (avoids false hits
    from a note about some unrelated third LB)."""
    rel = row.get("lb_relation_text") or ""
    m = _DIFF_RECORDING_RE.search(rel)
    if m:
        start, end = max(0, m.start() - 40), min(len(rel), m.end() + 60)
        return True, rel[start:end].strip()
    for text, other_lb in ((text_a, row["lb_b"]), (text_b, row["lb_a"])):
        other = str(other_lb)
        for m in _DIFF_RECORDING_RE.finditer(text or ""):
            window = text[max(0, m.start() - 150):min(len(text), m.end() + 150)]
            if other in window:
                return True, window.strip()
    return False, None


_TAPER_LABEL_RE = re.compile(
    r"(?:taper|taped\s+by|recorded\s+by|recording\s+by|mic(?:ed|s|rophones?)?\s+by)"
    r"\s*[:\-]?\s*([A-Z][A-Za-z.\']+(?:\s+[A-Z][A-Za-z.\']+){0,2})"
)


def _extract_taper(text: str) -> str | None:
    if not text:
        return None
    m = _TAPER_LABEL_RE.search(text)
    if not m:
        return None
    name = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".,;")
    return name.lower() if len(name) >= 3 else None


def _taper_conflict(text_a: str, text_b: str) -> tuple[bool, str | None, str | None]:
    ta, tb = _extract_taper(text_a), _extract_taper(text_b)
    if not ta or not tb:
        return False, ta, tb
    wa, wb = set(ta.split()), set(tb.split())
    return wa.isdisjoint(wb), ta, tb


def _duration_mismatch(row: dict) -> tuple[bool, float | None]:
    da, db = row.get("perf_dur_sec_a"), row.get("perf_dur_sec_b")
    if not da or not db:
        return False, None
    ratio = da / db
    ppm_a, ppm_b = row.get("speed_ppm_a"), row.get("speed_ppm_b")
    if ppm_a is not None and ppm_b is not None:
        speed_ratio = (1_000_000.0 + ppm_b) / (1_000_000.0 + ppm_a)
        if speed_ratio:
            ratio = ratio / speed_ratio
    return abs(ratio - 1.0) > 0.15, ratio


def _explanatory_lineage(row: dict) -> tuple[bool, str]:
    ext_a = (row.get("dominant_ext_a") or "").lower()
    ext_b = (row.get("dominant_ext_b") or "").lower()
    if ext_a and ext_b and ext_a != ext_b and (ext_a == ".mp3" or ext_b == ".mp3"):
        return True, f"format mismatch ({ext_a or '?'} vs {ext_b or '?'}) — lossy transcode explains HF collapse"
    hf_a, hf_b = row.get("hf_ceiling_hz_a"), row.get("hf_ceiling_hz_b")
    if hf_a is not None and hf_b is not None and abs(hf_a - hf_b) > HF_GAP_SPLIT_HZ \
            and min(hf_a, hf_b) < 8000:
        return True, (f"hf_ceiling gap {abs(hf_a - hf_b):.0f} Hz with narrow side "
                       f"{min(hf_a, hf_b):.0f} Hz — consistent with a band-limited generation")
    if row.get("lb_says_same") and (row.get("lb_relation_text") or "").strip():
        return True, "curator relation text affirmatively links the two LBs"
    return False, ""


def _label_assessment(row: dict, text_a: str, text_b: str, env: dict | None) -> tuple[str, str]:
    diff_hit, diff_snip = _explicit_different_recording(row, text_a, text_b)
    if diff_hit:
        return "suspect-label", f'relation/source text explicitly asserts a different recording: "{diff_snip}"'
    conflict, taper_a, taper_b = _taper_conflict(text_a, text_b)
    dur_bad, dur_ratio = _duration_mismatch(row)
    if conflict:
        return "suspect-label", f"source_texts name different tapers ({taper_a!r} vs {taper_b!r})"
    if dur_bad:
        return "suspect-label", (f"performance-duration ratio {dur_ratio:.2f} (speed-corrected) "
                                  f">15% off unity — different length/setlist")
    explanatory, reason = _explanatory_lineage(row)
    if explanatory:
        return "plausible-same-lineage", reason
    if env and env.get("mean_corr") is not None and env["mean_corr"] >= 0.30:
        return "plausible-same-lineage", f"quick 4-band envelope corr={env['mean_corr']:.2f} despite corr<0.05"
    return "indeterminate", "no distinguishing evidence in source text, format, hf_ceiling, or envelope check"


# ── throwaway 4-band envelope quick check (direct decode, no session) ───────

def _ffmpeg_window(path: Path, start_sec: float, dur_sec: float, sr: int) -> np.ndarray | None:
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start_sec):.3f}",
             "-t", f"{dur_sec:.3f}", "-i", str(path),
             "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"],
            capture_output=True, check=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("ffmpeg window decode failed for %s: %s", path, e)
        return None
    x = np.frombuffer(r.stdout, dtype=np.float32)
    return x if x.size else None


def _quick_envelope_check(lb_a: int, lb_b: int, found: dict, row: dict) -> dict | None:
    if lb_a not in found or lb_b not in found:
        return None
    try:
        tracks_a = I.list_tracks(found[lb_a], TS.AUDIO_EXTS)
        tracks_b = I.list_tracks(found[lb_b], TS.AUDIO_EXTS)
    except OSError as e:
        logger.warning("track listing failed for LB-%05d/LB-%05d: %s", lb_a, lb_b, e)
        return None
    if not tracks_a or not tracks_b:
        return None
    idx = min(len(tracks_a), len(tracks_b)) // 2
    path_a = tracks_a[min(idx, len(tracks_a) - 1)]
    path_b = tracks_b[min(idx, len(tracks_b) - 1)]

    xa = _ffmpeg_window(path_a, QC_TRACK_SKIP_SEC, QC_WINDOW_SEC, QC_SR_HZ)
    pad = QC_MAX_LAG_SEC
    xb = _ffmpeg_window(path_b, QC_TRACK_SKIP_SEC - pad, QC_WINDOW_SEC + 2 * pad, QC_SR_HZ)
    if xa is None or xb is None:
        return None

    ska, skb = row.get("speed_kind_a"), row.get("speed_kind_b")
    ppm_a, ppm_b = row.get("speed_ppm_a"), row.get("speed_ppm_b")
    if (ppm_a is not None and ppm_b is not None
            and ska in QC_RELIABLE_SPEED_KINDS and skb in QC_RELIABLE_SPEED_KINDS):
        ratio = (1_000_000.0 + ppm_b) / (1_000_000.0 + ppm_a)
        if abs(ratio - 1.0) > 1e-6:
            try:
                xb = A.resample_ratio(xb, ratio, sr=QC_SR_HZ)
            except Exception as e:
                logger.warning("resample_ratio failed for LB-%05d/LB-%05d: %s", lb_a, lb_b, e)

    caps = [v for v in (row.get("hf_ceiling_hz_a"), row.get("hf_ceiling_hz_b"), QC_HI_CAP_HZ)
            if v is not None]
    top_cap = max(min(caps), QC_LO_HZ * 2.0)
    edges = np.linspace(QC_LO_HZ, top_cap, QC_N_BANDS + 1)

    band_corr: list[float | None] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        try:
            res = M.lowband_envelope_corr(xa, xb, QC_SR_HZ, band_hz=(float(lo), float(hi)),
                                          max_lag_sec=QC_MAX_LAG_SEC)
            band_corr.append(res["corr"])
        except Exception as e:
            logger.warning("band env corr failed (%.0f-%.0f Hz) LB-%05d/LB-%05d: %s",
                            lo, hi, lb_a, lb_b, e)
            band_corr.append(None)
    valid = [c for c in band_corr if c is not None]
    return {
        "bands_hz": [(float(lo), float(hi)) for lo, hi in zip(edges[:-1], edges[1:])],
        "band_corr": band_corr,
        "mean_corr": float(np.mean(valid)) if valid else None,
        "track_idx": idx,
    }


# ── stats ─────────────────────────────────────────────────────────────────

def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, center - half), min(1.0, center + half)


# ── report ────────────────────────────────────────────────────────────────

def _fmt(v, prec=1):
    return "—" if v is None else f"{v:.{prec}f}"


def _truncate(text: str, n: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n].rstrip() + " …[truncated]"


def _pair_section(row: dict, text_a: str, text_b: str, env: dict | None,
                  assessment: str, reason: str) -> str:
    a, b, date = row["lb_a"], row["lb_b"], row["concert_date"]
    lines = [
        f"### LB-{a:05d} / LB-{b:05d} — {date} "
        f"({row['_category']}, hf-gap {row['_hf_bucket']})",
        "",
        f"- **label_assessment:** `{assessment}` — {reason}",
        f"- **corr:** {_fmt(row['corr'], 4)}   "
        f"**speed_kind:** {row.get('speed_kind_a')} / {row.get('speed_kind_b')}   "
        f"**speed_ppm:** {_fmt(row.get('speed_ppm_a'))} / {_fmt(row.get('speed_ppm_b'))}",
        f"- **hf_ceiling_hz:** {_fmt(row.get('hf_ceiling_hz_a'), 0)} / "
        f"{_fmt(row.get('hf_ceiling_hz_b'), 0)}   "
        f"**noise_floor_db:** {_fmt(row.get('noise_floor_db_a'))} / "
        f"{_fmt(row.get('noise_floor_db_b'))}   "
        f"**dc_asymmetry:** {_fmt(row.get('dc_asymmetry_a'), 3)} / "
        f"{_fmt(row.get('dc_asymmetry_b'), 3)}",
    ]
    da, db = row.get("perf_dur_sec_a"), row.get("perf_dur_sec_b")
    ratio = da / db if da and db else None
    lines.append(
        f"- **perf_dur_sec:** {_fmt(da, 0)} / {_fmt(db, 0)} (ratio {_fmt(ratio, 3)})   "
        f"**track_count:** {row.get('track_count_a')} / {row.get('track_count_b')}   "
        f"**dominant_ext:** {row.get('dominant_ext_a')} / {row.get('dominant_ext_b')}"
    )
    if env is None:
        lines.append("- **4-band envelope quick check:** unavailable (audio not resolved/decodable)")
    else:
        bands = ", ".join(
            f"[{lo:.0f}-{hi:.0f}Hz]={_fmt(c, 3)}"
            for (lo, hi), c in zip(env["bands_hz"], env["band_corr"])
        )
        lines.append(f"- **4-band envelope quick check** (track idx {env['track_idx']}, "
                     f"±{QC_MAX_LAG_SEC:.0f}s lag search): {bands}   "
                     f"mean={_fmt(env['mean_corr'], 3)}")
    lines.append(f"- **lb_relation_text:** {_truncate(row.get('lb_relation_text') or '(none)')}")
    lines.append(f"- **lb_source_text A (LB-{a:05d}):** {_truncate(text_a)}")
    lines.append(f"- **lb_source_text B (LB-{b:05d}):** {_truncate(text_b)}")
    lines.append("")
    return "\n".join(lines)


def _write_report(sample: list[dict], dossiers: list[str], fn_population_n: int,
                  total_positives: int, seed: int) -> None:
    counts = {"suspect-label": 0, "plausible-same-lineage": 0, "indeterminate": 0}
    by_cat: dict[str, dict[str, int]] = {}
    for row in sample:
        counts[row["_assessment"]] += 1
        by_cat.setdefault(row["_category"], {"suspect-label": 0, "plausible-same-lineage": 0,
                                             "indeterminate": 0})[row["_assessment"]] += 1

    n = len(sample)
    suspect = counts["suspect-label"]
    rate = suspect / n if n else 0.0
    lo, hi = _wilson_ci(suspect, n)

    # sensitivity: indeterminate pairs treated as suspect (upper bound)
    suspect_upper = suspect + counts["indeterminate"]
    rate_upper = suspect_upper / n if n else 0.0
    lo_u, hi_u = _wilson_ci(suspect_upper, n)

    def _ceiling(r: float) -> float:
        return (total_positives - r * fn_population_n) / total_positives

    lines = [
        "# FN_AUDIT_REPORT.md — Task 1 (Tier 0) FN forensic audit",
        "",
        "Generated by `tools/tapematch/audit_fn.py` "
        "(`instructions/CC_TAPEMATCH_ADDON.md` Task 1). Read-only analysis; "
        "no frozen-set labels edited; `pairs.label_suspect` flags suspect pairs only.",
        "",
        "## Headline",
        "",
        f"- FN population scored (corr < {CORR_THRESHOLD}, current committed config): "
        f"**{fn_population_n}** pairs (frozen-set total positives: {total_positives}).",
        f"- Stratified sample: **{n}** pairs "
        f"(target {DEFAULT_N_PER_CATEGORY}/category x 3 categories, seed={seed}).",
        f"- Sample verdicts: suspect-label={counts['suspect-label']}, "
        f"plausible-same-lineage={counts['plausible-same-lineage']}, "
        f"indeterminate={counts['indeterminate']}.",
        "",
        "| category | n | suspect-label | plausible-same-lineage | indeterminate |",
        "|---|---|---|---|---|",
    ]
    for cat in ("speed-corrected", "speed-unknown", "staircase"):
        c = by_cat.get(cat, {"suspect-label": 0, "plausible-same-lineage": 0, "indeterminate": 0})
        cn = sum(c.values())
        lines.append(f"| {cat} | {cn} | {c['suspect-label']} | {c['plausible-same-lineage']} "
                     f"| {c['indeterminate']} |")
    lines += [
        "",
        "### Label-noise rate + re-based recall ceiling",
        "",
        f"- **Point estimate:** {rate*100:.1f}% ({suspect}/{n}) suspect-label, "
        f"Wilson 95% CI [{lo*100:.1f}%, {hi*100:.1f}%].",
        f"- Extrapolated to the {fn_population_n}-pair corr<{CORR_THRESHOLD} population: "
        f"~{rate*fn_population_n:.0f} pairs "
        f"(CI [{lo*fn_population_n:.0f}, {hi*fn_population_n:.0f}]).",
        f"- **Re-based recall ceiling** (perfect matcher on the remaining true positives): "
        f"~{_ceiling(rate)*100:.1f}% "
        f"(CI [{_ceiling(hi)*100:.1f}%, {_ceiling(lo)*100:.1f}%]).",
        "",
        f"- Sensitivity (worst case — every `indeterminate` pair is actually suspect): "
        f"rate {rate_upper*100:.1f}% (CI [{lo_u*100:.1f}%, {hi_u*100:.1f}%]), "
        f"recall ceiling ~{_ceiling(rate_upper)*100:.1f}% "
        f"(CI [{_ceiling(hi_u)*100:.1f}%, {_ceiling(lo_u)*100:.1f}%]).",
        "",
        "### Methodology notes",
        "",
        "- FN population = frozen-set positives (`regression_set.json`) the current "
        "committed `config.yaml` still verdicts `different_family`, computed via the "
        "same `tapematch.verdict.cluster_verdicts` path `regression.py score --cached` "
        "uses, restricted to `corr < 0.05`.",
        "- `label_assessment` heuristic (transparent, not a black box — reviewers should "
        "spot-check): `suspect-label` if source_texts name disjoint taper handles, or "
        "the speed-corrected performance-duration ratio is >15% off unity; "
        "`plausible-same-lineage` if format differs (one side MP3), or hf_ceiling gap "
        ">1 kHz with the narrow side <8 kHz (band-limited generation), or the curator "
        "relation text affirmatively links the two LBs, or the quick envelope check "
        "mean corr >=0.30; else `indeterminate`.",
        "- The 4-band envelope quick check is a throwaway heuristic (single mid-track "
        "window, +/-20s lag search, best-available speed ratio only when both sides "
        "carry a reliable `speed_kind`) — supporting evidence only, never decisive "
        "alone for `suspect-label`.",
        "",
        "## Per-pair dossier",
        "",
    ]
    lines.extend(dossiers)
    REPORT_PATH.write_text("\n".join(lines))


# ── main ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n-per-category", type=int, default=DEFAULT_N_PER_CATEGORY)
    ap.add_argument("--skip-audio", action="store_true",
                    help="skip the 4-band envelope quick check (dossier + assessment only)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(levelname)s %(name)s: %(message)s")

    conn = TS.open_obs_db()  # applies the idempotent label_suspect ALTER
    try:
        frozen, fn_rows = _current_fn_population(conn)
        total_positives = len(frozen["positives"])
        sample = _stratified_sample(fn_rows, args.n_per_category, args.seed)
        logger.info("sampled %d pairs for dossier", len(sample))

        found: dict[int, Path] = {}
        if not args.skip_audio:
            all_lbs = sorted({lb for row in sample for lb in (row["lb_a"], row["lb_b"])})
            found, _missing = TS.resolve_from_collection(all_lbs)
            logger.info("resolved %d/%d sampled LB numbers on disk", len(found), len(all_lbs))

        dossiers: list[str] = []
        suspect_ids: list[int] = []
        for i, row in enumerate(sample, 1):
            a, b = row["lb_a"], row["lb_b"]
            logger.info("[%d/%d] LB-%05d/LB-%05d %s (%s)", i, len(sample), a, b,
                       row["concert_date"], row["_category"])
            text_a = _source_text(conn, row["run_id"], row["concert_date"], a)
            text_b = _source_text(conn, row["run_id"], row["concert_date"], b)
            env = None
            if not args.skip_audio:
                try:
                    env = _quick_envelope_check(a, b, found, row)
                except Exception as e:
                    logger.warning("envelope quick check crashed for LB-%05d/LB-%05d: %s", a, b, e)
            assessment, reason = _label_assessment(row, text_a, text_b, env)
            row["_assessment"] = assessment
            if assessment == "suspect-label":
                suspect_ids.append(row["id"])
            dossiers.append(_pair_section(row, text_a, text_b, env, assessment, reason))

        for pid in suspect_ids:
            conn.execute("UPDATE pairs SET label_suspect=1 WHERE id=?", (pid,))
        conn.commit()
        logger.info("flagged %d pairs as label_suspect=1", len(suspect_ids))

        _write_report(sample, dossiers, len(fn_rows), total_positives, args.seed)
    finally:
        conn.close()

    print(f"report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
