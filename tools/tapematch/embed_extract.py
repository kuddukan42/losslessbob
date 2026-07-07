#!/usr/bin/env python3
"""embed_extract.py — Task 6.1 embedding extraction (Tier B).

Extraction half of the ``instructions/CC_TAPEMATCH_ADDON.md`` Task 6 harness. For
every source in ``embed_eval_set.json`` it embeds 1 s windows (0.5 s hop) over 5
evenly-spaced 60 s excerpts (reusing the stored trim bounds), and caches the
per-source window embeddings to ``embed_cache/<date>/LB<lb>.npz`` (arrays ``emb``
[N,D] float32 and ``t`` [N] = nominal perf-seconds, i.e. the window centre divided
by the source's own speed factor so both recordings of a concert share a timeline).
``embed_eval.py`` then consumes that cache — the fragile model dependency lives only
here, never in the numpy-only scoring/gate tool.

Backends (``--backend``):
  * ``synthetic`` — NO audio/model; lays windows out from the eval-set metadata and
    emits deterministic pseudo-embeddings. Proves the extract→score→gate plumbing on
    the real eval-set structure. (Different-LB pairs share no lineage signal here, so
    the gate will read ≈0 — a plumbing check, not a separation measurement.)
  * ``nmfp`` — the spec-ideal degradation-robust neural fingerprint
    (raraz15/neural-music-fp, ISMIR 2025; TF 2.13 / 8 kHz). Requires an isolated
    Python 3.11 env — see MODEL SETUP below. Has the discriminative fingerprint head
    that should separate same-show different-source captures.
  * ``muq`` — torch-native music foundation embedding (OpenMuQ/MuQ). Installs cleanly
    on this Python 3.13 + the RTX 3080, but is a raw foundation model (no fingerprint
    head) → weaker, false-negative-prone probe. Fallback only.

MODEL SETUP (nmfp): no conda/uv/py3.11 on this host — bootstrap an isolated env
(pip install uv; uv python install 3.11; uv venv .venv-nmfp --python 3.11), install
tensorflow-cpu==2.13 + neural-music-fp deps, `./download-models.sh` the `nmfp-triplet`
Zenodo checkpoint, and point ``_NmfpBackend`` at it. Kept out of the pinned main .venv.

Serialise with any live tapematch session only if it competes for I/O — this reads
collection audio directly (seek-based excerpts), it does NOT use the shared
/mnt/DATA0 staging dir, so it is independent of the matcher's staging hazard.

    .venv/bin/python3 tools/tapematch/embed_extract.py --backend synthetic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
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
AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".m4a", ".mp3", ".ape"}

N_EXCERPTS = 5
EXCERPT_SEC = 60.0
WIN_SEC = 1.0
HOP_SEC = 0.5

log = logging.getLogger("embed_extract")


# ── window layout (shared by all backends) ──────────────────────────────────────
def _excerpt_starts(trim_head: float, perf_dur: float) -> list[float]:
    """5 evenly-spaced 60 s excerpt start times inside the trimmed performance region."""
    usable = max(perf_dur - EXCERPT_SEC, 0.0)
    if usable <= 0:  # very short source: a single excerpt from the head
        return [trim_head]
    return [trim_head + usable * i / (N_EXCERPTS - 1) for i in range(N_EXCERPTS)]


def _window_offsets() -> list[float]:
    """Centre offsets (s) of 1 s / 0.5 s-hop windows within one 60 s excerpt."""
    n = int((EXCERPT_SEC - WIN_SEC) / HOP_SEC) + 1
    return [WIN_SEC / 2.0 + HOP_SEC * i for i in range(n)]


def _nominal_times(src: dict) -> np.ndarray:
    """Nominal *seconds-into-performance* for every window of a source.

    Measured from ``trim_head`` (a shared time origin across recordings of one
    concert) and divided by the source's own speed factor, so window i of two
    different transfers of the same show lands at the same nominal time and the
    ±tol neighbourhood in embed_eval.py actually finds partners.
    """
    trim_head = float(src.get("trim_head_sec") or 0.0)
    perf = float(src.get("perf_dur_sec") or src.get("total_dur_sec") or 0.0)
    ppm = float(src.get("speed_ppm") or 0.0)
    factor = 1.0 + ppm * 1e-6
    offs = _window_offsets()
    times = []
    for st in _excerpt_starts(trim_head, perf):
        for o in offs:
            times.append((st - trim_head + o) / factor)
    return np.asarray(times, dtype=np.float32)


# ── disk resolution ─────────────────────────────────────────────────────────────
def _resolve_paths(lbs: list[int]) -> dict[int, Path]:
    """lb_number -> disk_path from my_collection (mirrors tapematch_session)."""
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


def _ffprobe_dur(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", str(path)],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _decode_excerpt(files: list[Path], cum: list[float], start: float, dur: float,
                    sr: int) -> np.ndarray:
    """Decode [start, start+dur) of the concatenated timeline to mono float32 @ sr.

    Excerpts stay within a single file in practice (60 s « a set); if one straddles a
    boundary we decode from the file it starts in and accept truncation at the seam.
    """
    idx = max(0, np.searchsorted(cum, start, side="right") - 1)
    local = start - cum[idx]
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{local:.3f}", "-t", f"{dur:.3f}",
         "-i", str(files[idx]), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, timeout=120)
    return np.frombuffer(proc.stdout, dtype=np.float32)


# ── backends ────────────────────────────────────────────────────────────────────
class _SyntheticBackend:
    """Audio-free plumbing backend: deterministic per-(lb,window) unit vectors."""
    name = "synthetic"
    dim = 128

    def extract(self, date: str, src: dict) -> tuple[np.ndarray, np.ndarray]:
        t = _nominal_times(src)
        lb = int(src["lb"])
        emb = np.empty((t.shape[0], self.dim), dtype=np.float32)
        for i in range(t.shape[0]):
            seed = int(hashlib.sha1(f"{lb}:{i}".encode()).hexdigest()[:8], 16)
            emb[i] = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
        return emb, t


class _AudioBackend:
    """Base for real model backends: shared decode + window batching; subclass embeds."""
    name = "audio"
    sr = 8000

    def _embed_windows(self, mono: np.ndarray) -> np.ndarray:  # pragma: no cover - model
        raise NotImplementedError

    def extract(self, date: str, src: dict, folder: Path) -> tuple[np.ndarray, np.ndarray]:
        files = _audio_files(folder)
        if not files:
            raise FileNotFoundError(f"no audio in {folder}")
        durs = [_ffprobe_dur(f) for f in files]
        cum = [0.0]
        for d in durs:
            cum.append(cum[-1] + d)
        trim_head = float(src.get("trim_head_sec") or 0.0)
        perf = float(src.get("perf_dur_sec") or src.get("total_dur_sec") or cum[-1])
        ppm = float(src.get("speed_ppm") or 0.0)
        factor = 1.0 + ppm * 1e-6
        offs = _window_offsets()
        embs: list[np.ndarray] = []
        times: list[float] = []
        for st in _excerpt_starts(trim_head, perf):
            mono = _decode_excerpt(files, cum, st, EXCERPT_SEC, self.sr)
            if mono.size < int(WIN_SEC * self.sr):
                continue
            wv = self._embed_windows(mono)  # [n_win, D]
            n = wv.shape[0]
            embs.append(wv)
            times.extend((st - trim_head + offs[i]) / factor for i in range(min(n, len(offs))))
        if not embs:
            raise RuntimeError(f"no decodable excerpts for LB{src['lb']} ({folder})")
        emb = np.vstack(embs).astype(np.float32)
        t = np.asarray(times[:emb.shape[0]], dtype=np.float32)
        return emb, t


class _NmfpBackend(_AudioBackend):
    """raraz15/neural-music-fp (TF 2.13, 8 kHz). Load via the isolated .venv-nmfp env."""
    name = "nmfp"
    sr = 8000

    def __init__(self) -> None:  # pragma: no cover - runs in a separate env
        raise NotImplementedError(
            "The real nmfp extraction runs in the isolated TF 2.13 env, not this py3.13 "
            "backend. Use: tools/tapematch/.venv-nmfp/bin/python tools/tapematch/nmfp_embed.py "
            "(self-contained; writes the same embed_cache/<date>/LB<lb>.npz that embed_eval.py reads).")


class _MuqBackend(_AudioBackend):
    """OpenMuQ/MuQ torch foundation embedding (24 kHz). Fallback probe."""
    name = "muq"
    sr = 24000

    def __init__(self) -> None:  # pragma: no cover - requires model env
        raise NotImplementedError(
            "muq backend requires torch + the muq package + OpenMuQ/MuQ weights in an "
            "isolated .venv-emb env. Wire MuQ.from_pretrained(...) here.")


def _make_backend(name: str):
    return {"synthetic": _SyntheticBackend, "nmfp": _NmfpBackend, "muq": _MuqBackend}[name]()


def main() -> int:
    ap = argparse.ArgumentParser(description="Task 6.1 embedding extraction.")
    ap.add_argument("--backend", choices=["synthetic", "nmfp", "muq"], default="synthetic")
    ap.add_argument("--eval-set", type=Path, default=EVAL_SET_PATH)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR)
    ap.add_argument("--force", action="store_true", help="re-extract even if cached.")
    ap.add_argument("--limit", type=int, default=0, help="cap sources (debug).")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.eval_set.exists():
        sys.exit(f"error: {args.eval_set.name} not found — run build_embed_eval_set.py first.")
    es = json.loads(args.eval_set.read_text())
    backend = _make_backend(args.backend)

    # flatten sources; resolve disk paths per date for audio backends.
    todo: list[tuple[str, dict]] = []
    for date, srcs in es["sources"].items():
        for s in srcs:
            todo.append((date, s))
    if args.limit:
        todo = todo[:args.limit]

    paths_by_date: dict[str, dict[int, Path]] = {}
    if args.backend != "synthetic":
        for date, srcs in es["sources"].items():
            paths_by_date[date] = _resolve_paths([s["lb"] for s in srcs])

    done = skipped = failed = 0
    for date, s in todo:
        out = args.cache / date / f"LB{s['lb']}.npz"
        if out.exists() and not args.force:
            skipped += 1
            continue
        try:
            if args.backend == "synthetic":
                emb, t = backend.extract(date, s)
            else:
                folder = paths_by_date.get(date, {}).get(int(s["lb"]))
                if folder is None or not folder.exists():
                    log.warning("  MISS %s LB%s: not in my_collection / folder absent", date, s["lb"])
                    failed += 1
                    continue
                emb, t = backend.extract(date, s, folder)
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, emb=emb.astype(np.float32), t=t.astype(np.float32))
            done += 1
        except Exception as e:  # noqa: BLE001 - keep going; report at end
            log.warning("  FAIL %s LB%s: %s", date, s["lb"], e)
            failed += 1

    print(f"backend={backend.name}  extracted={done}  cached-skip={skipped}  failed={failed}  "
          f"→ {args.cache}/")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
