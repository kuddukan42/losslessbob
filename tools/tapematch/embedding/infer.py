"""infer.py — Tier C CPU-batch inference (CC_TAPEMATCH_ADDON Task 7.2/7.3).

Embeds the Tier-B evaluation sources with the trained ConvEncoder and writes the SAME
per-source cache format as nmfp_embed.py (``emb`` [N,128] L2-normalized, ``t`` [N] =
nominal seconds-into-performance) so the existing ``embed_eval.py`` measures the
p10(TP)-p90(TN) gap identically. Writes to a SEPARATE cache dir (default
``embed_cache_tierc``) to preserve the nmfp cache for comparison.

Window layout matches nmfp_embed.py exactly (5×60 s excerpts, 1 s windows @ 0.5 s hop,
speed-corrected nominal time) — the model differs, the sampling does not.

    tools/tapematch/.venv-emb/bin/python tools/tapematch/embedding/infer.py \
        --ckpt tools/tapematch/embedding/ckpt/tierc.pt
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
from pathlib import Path

import numpy as np
import torch
import yaml

from melspec import LogMelSpec
from model import ConvEncoder

_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent.parent
LB_DB_PATH = PROJECT_ROOT / "data" / "losslessbob.db"
EVAL_SET_PATH = _HERE.parent / "embed_eval_set.json"
AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".m4a", ".mp3", ".ape"}
N_EXCERPTS, EXCERPT_SEC = 5, 60.0

log = logging.getLogger("tierc.infer")


def _excerpt_starts(trim_head: float, perf_dur: float) -> list[float]:
    usable = max(perf_dur - EXCERPT_SEC, 0.0)
    if usable <= 0:
        return [trim_head]
    return [trim_head + usable * i / (N_EXCERPTS - 1) for i in range(N_EXCERPTS)]


def _resolve_paths(lbs: list[int]) -> dict[int, Path]:
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


def _decode_whole(files: list[Path], fs: int) -> np.ndarray:
    parts = []
    for f in files:
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(f), "-ac", "1", "-ar", str(fs),
             "-f", "f32le", "-"], capture_output=True, timeout=900)
        parts.append(np.frombuffer(p.stdout, dtype=np.float32))
    return np.concatenate(parts) if parts else np.empty(0, np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier C embedding inference.")
    ap.add_argument("--config", type=Path, default=_HERE / "config.yaml")
    ap.add_argument("--ckpt", type=Path, default=None, help="defaults to config CHECKPOINT.")
    ap.add_argument("--cache", type=Path, default=_HERE.parent / "embed_cache_tierc")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap sources (debug).")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(args.config.read_text())
    fs = cfg["AUDIO"]["FS"]
    win = int(cfg["AUDIO"]["WIN_SEC"] * fs)
    hop = int(cfg["AUDIO"]["HOP_SEC"] * fs)
    dev = torch.device(args.device)
    mel = LogMelSpec(cfg).to(dev).eval()
    model = ConvEncoder(cfg).to(dev).eval()
    ckpt = args.ckpt or (PROJECT_ROOT / cfg["CHECKPOINT"])
    state = torch.load(ckpt, map_location=dev)
    model.load_state_dict(state["model"] if "model" in state else state)
    log.info("loaded %s", ckpt)

    @torch.no_grad()
    def embed_windows(mono: np.ndarray) -> np.ndarray:
        n = (mono.shape[0] - win) // hop + 1
        if n <= 0:
            return np.empty((0, cfg["MODEL"]["EMB_DIM"]), np.float32)
        segs = np.stack([mono[k * hop:k * hop + win] for k in range(n)]).astype(np.float32)
        outs = []
        for s in range(0, n, args.batch):
            wv = torch.from_numpy(segs[s:s + args.batch]).to(dev)
            outs.append(model(mel(wv)).cpu().numpy())
        return np.vstack(outs).astype(np.float32)

    es = json.loads(EVAL_SET_PATH.read_text())
    paths_by_date = {d: _resolve_paths([s["lb"] for s in ss]) for d, ss in es["sources"].items()}
    done = skip = fail = 0
    todo = [(date, s) for date, srcs in es["sources"].items() for s in srcs]
    if args.limit:
        todo = todo[:args.limit]
    for date, s in todo:
        if True:
            out = args.cache / date / f"LB{s['lb']}.npz"
            if out.exists() and not args.force:
                skip += 1
                continue
            folder = paths_by_date.get(date, {}).get(int(s["lb"]))
            if folder is None or not folder.exists():
                log.warning("  MISS %s LB%s", date, s["lb"]); fail += 1; continue
            try:
                mono_all = _decode_whole(_audio_files(folder), fs)
                total = mono_all.shape[0] / fs
                trim_head = float(s.get("trim_head_sec") or 0.0)
                perf = min(float(s.get("perf_dur_sec") or s.get("total_dur_sec") or total), total)
                factor = 1.0 + float(s.get("speed_ppm") or 0.0) * 1e-6
                embs, times = [], []
                for st in _excerpt_starts(trim_head, perf):
                    a = int(round(st * fs))
                    e = embed_windows(mono_all[a:a + int(EXCERPT_SEC * fs)])
                    if e.shape[0] == 0:
                        continue
                    embs.append(e)
                    times.extend((st - trim_head + (k * hop + win / 2.0) / fs) / factor
                                 for k in range(e.shape[0]))
                if not embs:
                    raise RuntimeError("no excerpts")
                emb = np.vstack(embs).astype(np.float32)
                t = np.asarray(times[:emb.shape[0]], np.float32)
                out.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(out, emb=emb, t=t)
                done += 1
            except Exception as e:  # noqa: BLE001
                log.warning("  FAIL %s LB%s: %s", date, s["lb"], e); fail += 1
    print(f"tierc infer: extracted={done} skip={skip} fail={fail} -> {args.cache}/")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
