"""data.py — Tier C training data: hard-negative mining, window cache, batch sampler.

CC_TAPEMATCH_ADDON Task 7.1. Runs in the isolated torch env (.venv-emb).

Design (the crux of Tier C): the discriminative signal is the SAME-SHOW HARD NEGATIVE
— a window from source A and a window from source B of the *same concert at the same
musical moment*. We therefore cache windows on a per-(date, time-slot) grid: for each
multi-source date we pick K anchor times in NOMINAL seconds-into-performance (shared
across sources, speed-corrected), and cache the 1 s window at each anchor for every
source. Windows sharing a (date, slot) are same-show hard negatives of each other;
windows from other dates/slots are easy negatives. Positives are two augmentations of
the SAME window (made in the DataLoader workers).

Curator labels are NEVER used here (self-supervised) — the frozen set stays a valid
measuring instrument. Sources/pairs flagged ``label_suspect=1`` and the 67 Tier-B eval
dates are excluded (no train/eval leakage).

Cache build is a one-time, CPU-parallel step (``build_cache``): each source is decoded
once (per-track ffmpeg → concat, handling .shn), K windows are sliced in RAM, only the
windows are written (full audio discarded). Then ``WindowCache`` mmaps the result.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, Sampler

_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent.parent
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
OBS_DB_PATH = _HERE.parent / "observations.db"
EVAL_SET_PATH = _HERE.parent / "embed_eval_set.json"
CACHE_DIR = _HERE / "audio_cache"
AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".m4a", ".mp3", ".ape"}

log = logging.getLogger("tierc.data")


# ── source selection / disk resolution ──────────────────────────────────────────
def _eval_dates() -> set[str]:
    if EVAL_SET_PATH.exists():
        return set(json.loads(EVAL_SET_PATH.read_text())["dates"])
    return set()


def select_sources(max_dates: int, min_sources: int = 2) -> dict[str, list[dict]]:
    """date -> [{lb, family, trim_head, perf_dur, speed_ppm}] for multi-source training dates.

    Multi-source dates only (need >=2 sources for same-show hard negatives). Excludes the
    Tier-B eval dates and any source on a pair flagged label_suspect=1.
    """
    eval_dates = _eval_dates()
    conn = sqlite3.connect(str(OBS_DB_PATH))
    conn.row_factory = sqlite3.Row
    suspect_lbs: set[tuple[str, int]] = set()
    for r in conn.execute("SELECT concert_date, lb_a, lb_b FROM latest_pairs WHERE label_suspect=1"):
        suspect_lbs.add((r["concert_date"], r["lb_a"]))
        suspect_lbs.add((r["concert_date"], r["lb_b"]))
    by_date: dict[str, list[dict]] = {}
    for r in conn.execute(
        "SELECT concert_date, lb_number AS lb, family_id, trim_head_sec, trim_tail_sec, "
        "perf_dur_sec, total_dur_sec, speed_ppm FROM sources ORDER BY concert_date, id"
    ):
        d = r["concert_date"]
        if d in eval_dates or (d, r["lb"]) in suspect_lbs:
            continue
        rec = {"lb": r["lb"], "family": r["family_id"],
               "trim_head": float(r["trim_head_sec"] or 0.0),
               "perf_dur": float(r["perf_dur_sec"] or r["total_dur_sec"] or 0.0),
               "speed_ppm": float(r["speed_ppm"] or 0.0)}
        by_date.setdefault(d, [])
        if r["lb"] not in {s["lb"] for s in by_date[d]}:  # dedup latest run's sources
            by_date[d].append(rec)
    conn.close()
    dates = [d for d, s in by_date.items() if len(s) >= min_sources]
    dates.sort(key=lambda d: (-len(by_date[d]), d))  # source-dense first
    chosen = dates[:max_dates] if max_dates else dates
    return {d: by_date[d] for d in chosen}


def _resolve_paths(lbs: list[int]) -> dict[int, Path]:
    if not LB_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(LB_DB_PATH))
    try:
        ph = ",".join("?" * len(lbs))
        rows = conn.execute(
            f"SELECT lb_number, disk_path FROM my_collection WHERE lb_number IN ({ph})", lbs
        ).fetchall()
    finally:
        conn.close()
    return {int(lb): Path(p) for lb, p in rows if p}


def _audio_files(folder: Path) -> list[Path]:
    return sorted((f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTS),
                  key=lambda p: str(p).lower())


def _decode_whole(files: list[Path], fs: int, max_seconds: float = 0.0) -> np.ndarray:
    """Per-track decode + concat to mono float32 @ fs (handles .shn — see nmfp_embed).

    Stops once ``max_seconds`` of audio has been decoded (only the needed head of a
    long source is required — anchors live in [0, min_perf]), which roughly halves
    decode time when a complete source is paired with a shorter one.
    """
    parts: list[np.ndarray] = []
    have = 0
    need = int(max_seconds * fs) if max_seconds else 0
    for f in files:
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(f), "-ac", "1", "-ar", str(fs),
             "-f", "f32le", "-"], capture_output=True, timeout=900)
        a = np.frombuffer(p.stdout, dtype=np.float32)
        parts.append(a)
        have += a.shape[0]
        if need and have >= need:
            break
    return np.concatenate(parts) if parts else np.empty(0, np.float32)


# ── cache build (parallel) ──────────────────────────────────────────────────────
def _slice_source(args: tuple) -> tuple | None:
    """Worker: decode one source, slice K windows at the date's shared anchor times."""
    date, src, folder_str, anchors_nominal, fs, win = args
    folder = Path(folder_str)
    files = _audio_files(folder)
    if not files:
        return None
    factor = 1.0 + src["speed_ppm"] * 1e-6
    # only the head up to the last anchor is needed (anchors live in [0, min_perf])
    need_sec = max(anchors_nominal) * factor + src["trim_head"] + win / fs + 2.0
    try:
        mono = _decode_whole(files, fs, max_seconds=need_sec)
    except Exception:  # noqa: BLE001
        return None
    if mono.shape[0] < win:
        return None
    out = np.zeros((len(anchors_nominal), win), np.float16)
    ok = np.zeros(len(anchors_nominal), bool)
    for j, tnom in enumerate(anchors_nominal):
        local = tnom * factor + src["trim_head"]      # nominal -> this source's local time
        a = int(round(local * fs))
        seg = mono[a:a + win]
        if seg.shape[0] == win:
            out[j] = seg.astype(np.float16)
            ok[j] = True
    return date, src["lb"], src["family"], out, ok


def _shard_path(date: str, lb: int) -> Path:
    return CACHE_DIR / "shards" / f"{date}_LB{lb}.npz"


def build_cache(cfg: dict, max_dates: int, slots: int, workers: int) -> None:
    """Decode (parallel) + slice a (date, slot, source) window grid, RESUMABLY.

    Each completed source is written immediately to its own shard under
    ``audio_cache/shards/`` — an interruption never loses work, and re-running skips
    sources whose shard already exists. When all jobs are done, shards are assembled
    into ``windows.npy`` + ``index.json``.
    """
    fs = cfg["AUDIO"]["FS"]
    win = int(cfg["AUDIO"]["WIN_SEC"] * fs)
    (CACHE_DIR / "shards").mkdir(parents=True, exist_ok=True)
    by_date = select_sources(max_dates)
    jobs = []
    for date, srcs in by_date.items():
        lbs = [s["lb"] for s in srcs]
        paths = _resolve_paths(lbs)
        srcs = [s for s in srcs if s["lb"] in paths and paths[s["lb"]].exists()]
        if len(srcs) < 2:
            continue
        min_perf = min(s["perf_dur"] for s in srcs)
        usable = max(min_perf - cfg["AUDIO"]["WIN_SEC"], 1.0)
        anchors = [usable * k / max(slots - 1, 1) for k in range(slots)]  # nominal secs-into-perf
        for s in srcs:
            if not _shard_path(date, s["lb"]).exists():
                jobs.append((date, s, str(paths[s["lb"]]), anchors, fs, win))
    log.info("cache build: %d dates, %d source-jobs to do (resumable), %d slots",
             len(by_date), len(jobs), slots)

    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_slice_source, j) for j in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r is not None:
                date, lb, fam, arr, ok = r
                sel = np.nonzero(ok)[0]
                if sel.size:
                    np.savez(_shard_path(date, lb), win=arr[sel].astype(np.float16),
                             slot=sel.astype(np.int32), lb=int(lb),
                             fam=int(fam) if fam is not None else -1, date=date)
            if done % 50 == 0:
                log.info("  decoded %d/%d source-jobs", done, len(jobs))

    _assemble_shards(cfg, fs, win)


def _assemble_shards(cfg: dict, fs: int, win: int) -> None:
    """Concatenate all per-source shards into windows.npy + index.json."""
    shards = sorted((CACHE_DIR / "shards").glob("*.npz"))
    meta_date, meta_slot, meta_lb, meta_fam = [], [], [], []
    total = 0
    for sh in shards:
        z = np.load(sh, allow_pickle=True)
        total += int(z["win"].shape[0])
    mm = np.lib.format.open_memmap(CACHE_DIR / "windows.npy", mode="w+", dtype=np.float16,
                                   shape=(total, win))
    row = 0
    for sh in shards:
        z = np.load(sh, allow_pickle=True)
        w = z["win"]
        mm[row:row + w.shape[0]] = w
        for sl in z["slot"].tolist():
            meta_date.append(str(z["date"])); meta_slot.append(int(sl))
            meta_lb.append(int(z["lb"])); meta_fam.append(int(z["fam"]))
        row += w.shape[0]
    mm.flush()
    (CACHE_DIR / "index.json").write_text(json.dumps({
        "fs": fs, "win": win, "n": total,
        "date": meta_date, "slot": meta_slot, "lb": meta_lb, "fam": meta_fam,
    }))
    log.info("cache assembled: %d windows from %d shards -> %s", total, len(shards),
             CACHE_DIR / "windows.npy")


# ── dataset + hard-negative batch sampler ───────────────────────────────────────
class WindowCache(Dataset):
    """Mmap the window cache; __getitem__ returns two augmented views + group id.

    group_id = (date, slot) index — items with the same group_id are same-show
    same-moment hard negatives. The two views (aug of the same raw window) are the
    positive pair; augmentation runs here (DataLoader workers) for throughput.
    """

    def __init__(self, cfg: dict, augment_factory) -> None:
        idx = json.loads((CACHE_DIR / "index.json").read_text())
        self.win = idx["win"]
        self.W = np.load(CACHE_DIR / "windows.npy", mmap_mode="r")
        groups = [f"{d}#{s}" for d, s in zip(idx["date"], idx["slot"])]
        uniq = {g: i for i, g in enumerate(sorted(set(groups)))}
        self.group = np.asarray([uniq[g] for g in groups], np.int64)
        self.n = idx["n"]
        self._cfg = cfg
        self._factory = augment_factory
        self._aug = None  # lazily built per worker (rng per worker)

    def __len__(self) -> int:
        return self.n

    def _ensure_aug(self):
        if self._aug is None:
            seed = (torch.initial_seed() % (2 ** 31))
            self._aug = self._factory(self._cfg, np.random.default_rng(seed))
        return self._aug

    def __getitem__(self, i: int):
        aug = self._ensure_aug()
        w = np.asarray(self.W[i], dtype=np.float32)
        v1 = aug(w).astype(np.float32)
        v2 = aug(w).astype(np.float32)
        return torch.from_numpy(v1), torch.from_numpy(v2), int(self.group[i])


class HardNegBatchSampler(Sampler):
    """Batches with >= hard_frac items drawn from multi-item groups (same-show hard negs)."""

    def __init__(self, group: np.ndarray, batch_size: int, hard_frac: float,
                 seed: int = 0, drop_last: bool = True) -> None:
        self.group = group
        self.bs = batch_size
        self.hard_target = int(hard_frac * batch_size)
        self.rng = np.random.default_rng(seed)
        self.drop_last = drop_last
        by_group: dict[int, list[int]] = {}
        for i, g in enumerate(group):
            by_group.setdefault(int(g), []).append(i)
        self.multi = [members for members in by_group.values() if len(members) >= 2]
        self.all_idx = np.arange(len(group))

    def __iter__(self):
        order = self.rng.permutation(len(self.all_idx))
        pos = 0
        n_batches = len(order) // self.bs
        for _ in range(n_batches):
            batch: list[int] = []
            # fill hard-negative quota from multi-item groups
            while len(batch) < self.hard_target and self.multi:
                grp = self.multi[self.rng.integers(len(self.multi))]
                batch.extend(grp)
            batch = batch[:self.bs]
            # fill remainder with a running permutation of all windows (easy negatives)
            while len(batch) < self.bs:
                if pos >= len(order):
                    order = self.rng.permutation(len(self.all_idx)); pos = 0
                batch.append(int(order[pos])); pos += 1
            self.rng.shuffle(batch)
            yield batch[:self.bs]

    def __len__(self) -> int:
        return len(self.group) // self.bs


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier C window-cache builder.")
    ap.add_argument("--max-dates", type=int, default=0, help="0 = all multi-source non-eval dates.")
    ap.add_argument("--slots", type=int, default=48, help="anchor time-slots per date.")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--config", type=Path, default=_HERE / "config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import yaml
    cfg = yaml.safe_load(args.config.read_text())
    build_cache(cfg, args.max_dates, args.slots, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
