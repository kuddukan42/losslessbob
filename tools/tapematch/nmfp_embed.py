#!/usr/bin/env python3
"""nmfp_embed.py — Task 6.1 real embedding extraction with neural-music-fp.

The ``nmfp`` backend of the Tier B harness. MUST run under the isolated env
``tools/tapematch/.venv-nmfp`` (TensorFlow 2.13 / py3.11 / essentia) — the main
pinned ``.venv`` cannot import TF. It reproduces the authors' exact preprocessing
(essentia ``Melspec_layer`` with the checkpoint's own config) on our collection
audio and writes the per-source window-embedding cache
``embed_cache/<date>/LB<lb>.npz`` (arrays ``emb`` [N,128] float32, ``t`` [N] =
nominal seconds-into-performance) that the model-free ``embed_eval.py`` consumes.

Faithful by construction: fingerprints are computed on exactly-8000-sample (1 s @
8 kHz) segments at 0.5 s hop — the same L/H the model was trained/evaluated with —
so no resampling/parameter drift can shift the embedding vs the released weights.

    tools/tapematch/.venv-nmfp/bin/python tools/tapematch/nmfp_embed.py
    # options: --limit N (debug), --force (re-extract cached), --batch 512
    # --eval-set PATH: any embed_eval_set.json-shaped source list (default:
    #   embed_eval_set.json) — e.g. fullset_sources.json / pilot_sources.json
    #   from build_fullset_worklist.py. Cache layout/skip-if-cached unchanged.
    # --n-excerpts N: excerpts per source (default 5, evenly spans the
    #   performance) — e.g. --n-excerpts 12 for a densification pilot.
    #   --cache DIR: write to an alternate cache dir instead of embed_cache/.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
EVAL_SET_PATH = _HERE / "embed_eval_set.json"
CACHE_DIR = _HERE / "embed_cache"
VENDOR = _HERE / "vendor" / "neural-music-fp"
CONFIG_PATH = VENDOR / "config" / "nmfp-triplet.yaml"
AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".m4a", ".mp3", ".ape"}

N_EXCERPTS = 5
EXCERPT_SEC = 60.0
SEG_LEN = 8000      # 1 s @ 8 kHz  (model SEGMENT_DUR * FS)
SEG_HOP = 4000      # 0.5 s hop
FS = 8000

log = logging.getLogger("nmfp_embed")


# ── window layout (matches embed_extract.py) ────────────────────────────────────
def _excerpt_starts(
    trim_head: float, perf_dur: float, n_excerpts: int = N_EXCERPTS
) -> list[float]:
    usable = max(perf_dur - EXCERPT_SEC, 0.0)
    if usable <= 0:
        return [trim_head]
    return [trim_head + usable * i / (n_excerpts - 1) for i in range(n_excerpts)]


# ── disk resolution / decode ────────────────────────────────────────────────────
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


def _decode_whole(files: list[Path]) -> np.ndarray:
    """Decode the whole gapless-concatenated performance to mono float32 @ 8 kHz.

    Decodes each track individually and concatenates the PCM (gapless). Per-file
    decode is used rather than ffmpeg's concat demuxer because Shorten (.shn) files
    carry no duration/timestamps, which makes the demuxer stop after the first track.
    Excerpts are then sliced from this array at exact sample positions.
    """
    parts: list[np.ndarray] = []
    for f in files:
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(f),
             "-ac", "1", "-ar", str(FS), "-f", "f32le", "-"],
            capture_output=True, timeout=600)
        parts.append(np.frombuffer(proc.stdout, dtype=np.float32))
    return np.concatenate(parts) if parts else np.empty(0, np.float32)


def _segments(mono: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """(K, 8000) segments + their in-excerpt centre times (s)."""
    if mono.shape[0] < SEG_LEN:
        return np.empty((0, SEG_LEN), np.float32), []
    n = (mono.shape[0] - SEG_LEN) // SEG_HOP + 1
    segs = np.empty((n, SEG_LEN), np.float32)
    centres = []
    for j in range(n):
        s = j * SEG_HOP
        segs[j] = mono[s:s + SEG_LEN]
        centres.append((s + SEG_LEN / 2.0) / FS)
    return segs, centres


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 6.1 nmfp embedding extraction.")
    ap.add_argument("--eval-set", type=Path, default=EVAL_SET_PATH)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    ap.add_argument("--batch", type=int, default=512, help="segments per model forward.")
    ap.add_argument("--n-excerpts", type=int, default=N_EXCERPTS,
                     help="excerpts per source, evenly spanning the performance.")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # ── build model + mel front-end from the checkpoint's own config ────────────
    sys.path.insert(0, str(VENDOR))
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import tensorflow as tf
    from nmfp.utils import load_config
    from nmfp.model.utils import get_fingerprinter, get_checkpoint_index_and_restore_model
    from nmfp.audio_processing.melspectrogram import Melspec_layer

    cfg = load_config(str(args.config))
    cfg["TRAIN"]["MIXED_PRECISION"] = False  # force float32 on CPU (weights are float32)
    m_in = cfg["MODEL"]["INPUT"]
    mel = Melspec_layer(
        segment_duration=cfg["MODEL"]["AUDIO"]["SEGMENT_DUR"],
        fs=cfg["MODEL"]["AUDIO"]["FS"],
        n_fft=m_in["STFT_WIN"], stft_hop=m_in["STFT_HOP"], n_mels=m_in["N_MELS"],
        f_min=m_in["F_MIN"], f_max=m_in["F_MAX"],
        dynamic_range=m_in["DYNAMIC_RANGE"], scale=m_in["SCALE"])
    m_fp = get_fingerprinter(cfg, trainable=False)

    # checkpoint dir = the folder containing ckpt-*.index (unzipped under the config's LOG_ROOT).
    ck_root = args.config.parent.parent / "logs" / "nmfp" / "fma-nmfp_deg" / "checkpoint"
    idx_files = list(ck_root.rglob("ckpt-*.index"))
    if not idx_files:
        sys.exit(f"error: no ckpt-*.index under {ck_root} — run download-models.sh (nmfp-triplet).")
    ck_dir = idx_files[0].parent
    get_checkpoint_index_and_restore_model(m_fp, str(ck_dir))

    def embed(segs: np.ndarray) -> np.ndarray:
        """(K,8000) -> (K,128) fingerprints."""
        X = mel.compute_batch(segs)              # (K, F, T)
        X = X[..., np.newaxis].astype(np.float32)  # (K, F, T, 1)
        outs = []
        for s in range(0, X.shape[0], args.batch):
            outs.append(np.asarray(m_fp(X[s:s + args.batch], training=False)))
        return np.vstack(outs).astype(np.float32)

    # sanity: fingerprints must be non-degenerate + L2-normalized (model L2-normalizes).
    probe = embed(np.random.default_rng(0).standard_normal((4, SEG_LEN)).astype(np.float32))
    log.info("model OK — probe emb shape %s, norms %s", probe.shape,
             np.round(np.linalg.norm(probe, axis=1), 3).tolist())

    # ── extract every eval-set source ───────────────────────────────────────────
    es = json.loads(args.eval_set.read_text())
    todo = [(d, s) for d, ss in es["sources"].items() for s in ss]
    if args.limit:
        todo = todo[:args.limit]
    paths_by_date = {d: _resolve_paths([s["lb"] for s in ss]) for d, ss in es["sources"].items()}

    done = skipped = failed = 0
    for date, s in todo:
        out = args.cache / date / f"LB{s['lb']}.npz"
        if out.exists() and not args.force:
            skipped += 1
            continue
        try:
            folder = paths_by_date.get(date, {}).get(int(s["lb"]))
            if folder is None or not folder.exists():
                log.warning("  MISS %s LB%s: not in my_collection / folder absent", date, s["lb"])
                failed += 1
                continue
            files = _audio_files(folder)
            if not files:
                raise FileNotFoundError("no audio files")
            mono_all = _decode_whole(files)
            if mono_all.shape[0] < SEG_LEN:
                raise RuntimeError("decoded audio too short / decode failed")
            total_sec = mono_all.shape[0] / FS
            trim_head = float(s.get("trim_head_sec") or 0.0)
            perf = min(float(s.get("perf_dur_sec") or s.get("total_dur_sec") or total_sec), total_sec)
            factor = 1.0 + float(s.get("speed_ppm") or 0.0) * 1e-6

            all_emb, all_t = [], []
            for st in _excerpt_starts(trim_head, perf, args.n_excerpts):
                a = int(round(st * FS))
                mono = mono_all[a:a + int(EXCERPT_SEC * FS)]
                segs, centres = _segments(mono)
                if segs.shape[0] == 0:
                    continue
                all_emb.append(embed(segs))
                all_t.extend((st - trim_head + c) / factor for c in centres)
            if not all_emb:
                raise RuntimeError("no decodable excerpts")
            emb = np.vstack(all_emb).astype(np.float32)
            t = np.asarray(all_t[:emb.shape[0]], np.float32)
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, emb=emb, t=t)
            done += 1
            if done % 20 == 0:
                log.info("  %d extracted (last %s LB%s: %d windows)", done, date, s["lb"], emb.shape[0])
        except Exception as e:  # noqa: BLE001
            log.warning("  FAIL %s LB%s: %s", date, s["lb"], e)
            failed += 1

    print(f"nmfp extraction: extracted={done} cached-skip={skipped} failed={failed} → {args.cache}/")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
