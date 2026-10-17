"""Throwaway Tier C embedding probe (2026-07-03) on a 7-date calibration set with
independently-documented ground truth (curator lineage text + prior tapematch
audio history where available), per user request to see how the rejected
from-scratch contrastive encoder (Tier C, tools/tapematch/embedding/, checkpoint
ckpt/tierc.pt -- REJECTED on the strict Task 6/7 gap gate, dormant) scores real
pairs outside the frozen regression set.

Reuses embedding/infer.py's exact windowing/extraction convention (5x60s excerpts,
1s windows/0.5s hop, speed-corrected nominal time) and embed_eval.py's exact
pair-scoring convention (median A-window cosine-max to B, aligned tol or global),
pointed at these 17 sources directly instead of the frozen embed_eval_set.json.

Not part of the shipped pipeline. Run under the isolated torch env:
    tools/tapematch/.venv-emb/bin/python tools/tapematch/_tierc_probe.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

EMB_DIR = Path("/home/tjenkins/Documents/losslessbob/tools/tapematch/embedding")
sys.path.insert(0, str(EMB_DIR))
from melspec import LogMelSpec  # noqa: E402
from model import ConvEncoder  # noqa: E402

CKPT = EMB_DIR / "ckpt" / "tierc.pt"
CFG = yaml.safe_load((EMB_DIR / "config.yaml").read_text())
FS = CFG["AUDIO"]["FS"]
WIN = int(CFG["AUDIO"]["WIN_SEC"] * FS)
HOP = int(CFG["AUDIO"]["HOP_SEC"] * FS)
N_EXCERPTS, EXCERPT_SEC = 5, 60.0

# (date, lb, folder, trim_head_sec, perf_dur_sec, speed_ppm, ground_truth_group)
# ground_truth_group: sources sharing the same group string are asserted same-source.
SOURCES = [
    # 2025-04-11 West Lafayette -- 3 distinct sources (confirmed this session, near-zero corr all pairs)
    ("2025-04-11", 16316, "/mnt/DYLAN3/Concerts/2025/2025-04-11 West Lafayette, Indiana (LB-16316)", 46.0, 6181.5, 0.0, "2025-04-11-a"),
    ("2025-04-11", 16317, "/mnt/DYLAN3/Concerts/2025/2025-04-11 West Lafayette, Indiana (LB-16317)", 107.0, 6174.5, -66.30496396475837, "2025-04-11-b"),
    ("2025-04-11", 16347, "/mnt/DYLAN3/Concerts/2025/2025-04-11 West Lafayette, Indiana (LB-16347)", 20.0, 6239.0, -6716.220548164786, "2025-04-11-c"),
    # 2025-11-16 Glasgow -- LB-16525/16544 same source (0.924 primary corr post-fix), LB-16524 distinct
    ("2025-11-16", 16524, "/mnt/DYLAN3/Concerts/2025/2025-11-16 Glasgow, Scotland (LB-16524)", 15.0, 6318.0, -961.6670623614488, "2025-11-16-distinct"),
    ("2025-11-16", 16525, "/mnt/DYLAN3/Concerts/2025/2025-11-16 Glasgow, Scotland (LB-16525)", 0.0, 6292.9701875, 0.0, "2025-11-16-same"),
    ("2025-11-16", 16544, "/mnt/DYLAN3/Concerts/2025/2025-11-16 Glasgow, Scotland, SEC Armadillo (LB-16544)", 0.0, 6292.9701875, 0.0, "2025-11-16-same"),
    # 2025-11-17 Glasgow -- ALL 3 same source per user; LB-16545 is a full stem-separated remix
    ("2025-11-17", 16526, "/mnt/DYLAN3/Concerts/2025/2025-11-17 Glasgow, Scotland (LB-16526)", 0.0, 6284.348875, 0.0, "2025-11-17-same"),
    ("2025-11-17", 16545, "/mnt/DYLAN3/Concerts/2025/2025-11-17 Glasgow, Scotland (LB-16545)", 0.0, 6220.458375, 7271.027655578521, "2025-11-17-same"),
    ("2025-11-17", 16546, "/mnt/DYLAN3/Concerts/2025/2025-11-17 Glasgow, Scotland (LB-16546)", 0.0, 6284.348875, 0.0, "2025-11-17-same"),
    # 1996-11-04 Spartanburg -- LB-12343/14002 same source (curator text + fp_score=0.44 same_family
    # across 3 independent historical runs)
    ("1996-11-04", 12343, "/mnt/DYLAN1/Concerts/1996/1996-11-04 Spartanburg, SC (LB-12343)", 0.0, 7314.8536875, -232.45146333628065, "1996-11-04-same"),
    ("1996-11-04", 14002, "/mnt/DYLAN1/Concerts/1996/1996-11-04 Spartanburg, SC (LB-14002)", 0.0, 7312.20025, 29.943141942823104, "1996-11-04-same"),
    # 1990-08-12 Edmonton -- LB-12353/12257 same source (curator text + fp_score=0.42 same_family,
    # torrent-comment taper-ID correction confirms same taper)
    ("1990-08-12", 12353, "/mnt/DYLAN1/Concerts/1990/1990-08-12 Edmonton, AB (LB-12353)", 0.0, 4810.0003125, -62.37018825561158, "1990-08-12-same"),
    ("1990-08-12", 12257, "/mnt/DYLAN1/Concerts/1990/1990-08-12 Edmonton, AB (LB-12257)", 0.0, 4855.8270625, -10518.132241967514, "1990-08-12-same"),
    # 2002-02-18 Tupelo -- LB-4088/331 distinct ("This is not the same recording as LB-331")
    ("2002-02-18", 4088, "/mnt/DYLAN1/Concerts/2002/2002-02-18 Tupelo, Mississippi, BancorpSouth Center (LB-04088)", 153.5, 7837.0, 5804.389434732826, "2002-02-18-a"),
    ("2002-02-18", 331, "/mnt/DYLAN1/Concerts/2002/2002-02-18 BancorpSouth Center, Tupelo, Mississippi (LB-00331)", 18.0, 7906.0, 0.0, "2002-02-18-b"),
    # 1995-11-05 Austin -- LB-3674/899 distinct ("Appears to be different recording from LB-899")
    ("1995-11-05", 3674, "/mnt/DYLAN1/Concerts/1995/1995-11-05 Austin Music Hall, Austin, TX (LB-03674)", 0.0, 7288.5, 0.0, "1995-11-05-a"),
    ("1995-11-05", 899, "/mnt/DYLAN1/Concerts/1995/1995-11-05 Austin Music Hall, Austin, TX (LB-00899)", 4.0, 7237.5, 4046.6321243524117, "1995-11-05-b"),
]

AUDIO_EXTS = {".flac", ".wav", ".shn", ".aiff", ".aif", ".m4a", ".mp3", ".ape"}


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


def _excerpt_starts(trim_head: float, perf_dur: float) -> list[float]:
    usable = max(perf_dur - EXCERPT_SEC, 0.0)
    if usable <= 0:
        return [trim_head]
    return [trim_head + usable * i / (N_EXCERPTS - 1) for i in range(N_EXCERPTS)]


def main() -> None:
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    mel = LogMelSpec(CFG).to(dev).eval()
    model = ConvEncoder(CFG).to(dev).eval()
    state = torch.load(CKPT, map_location=dev)
    model.load_state_dict(state["model"] if "model" in state else state)
    print(f"loaded {CKPT} on {dev}")

    @torch.no_grad()
    def embed_windows(mono: np.ndarray) -> np.ndarray:
        n = (mono.shape[0] - WIN) // HOP + 1
        if n <= 0:
            return np.empty((0, CFG["MODEL"]["EMB_DIM"]), np.float32)
        segs = np.stack([mono[k * HOP:k * HOP + WIN] for k in range(n)]).astype(np.float32)
        outs = []
        for s in range(0, n, 512):
            wv = torch.from_numpy(segs[s:s + 512]).to(dev)
            outs.append(model(mel(wv)).cpu().numpy())
        return np.vstack(outs).astype(np.float32)

    cache: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] = {}
    for date, lb, folder, trim_head, perf_dur, speed_ppm, _grp in SOURCES:
        print(f"embedding {date} LB-{lb} ...")
        mono_all = _decode_whole(_audio_files(Path(folder)), FS)
        factor = 1.0 + speed_ppm * 1e-6
        embs, times = [], []
        for st in _excerpt_starts(trim_head, perf_dur):
            a = int(round(st * FS))
            e = embed_windows(mono_all[a:a + int(EXCERPT_SEC * FS)])
            if e.shape[0] == 0:
                continue
            embs.append(e)
            times.extend((st - trim_head + (k * HOP + WIN / 2.0) / FS) / factor
                         for k in range(e.shape[0]))
        emb = np.vstack(embs).astype(np.float32)
        t = np.asarray(times[:emb.shape[0]], np.float32)
        norm = np.linalg.norm(emb, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        cache[(date, lb)] = (emb / norm, t)
        print(f"  {emb.shape[0]} windows")

    def pair_score(a, b, tol):
        ea, ta = a
        eb, tb = b
        sims = ea @ eb.T
        if tol <= 0:
            return float(np.median(sims.max(axis=1)))
        maxima = []
        for i in range(ea.shape[0]):
            mask = np.abs(tb - ta[i]) <= tol
            if mask.any():
                maxima.append(float(sims[i, mask].max()))
        return float(np.median(maxima)) if maxima else None

    print("\n=== pairwise emb_score (tol=2s aligned / tol=0 global) vs ground truth ===")
    dates = sorted(set(d for d, *_ in SOURCES))
    same_scores, distinct_scores = [], []
    for date in dates:
        entries = [(lb, grp) for d, lb, folder, th, pd, sp, grp in SOURCES if d == date]
        print(f"\n{date}:")
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                lb_i, grp_i = entries[i]
                lb_j, grp_j = entries[j]
                a, b = cache[(date, lb_i)], cache[(date, lb_j)]
                s2 = pair_score(a, b, 2.0)
                s0 = pair_score(a, b, 0.0)
                same = grp_i == grp_j
                tag = "SAME-SOURCE" if same else "distinct"
                print(f"  LB-{lb_i} / LB-{lb_j} [{tag}]: tol2={s2:.3f}  tol0(global)={s0:.3f}"
                      if s2 is not None else
                      f"  LB-{lb_i} / LB-{lb_j} [{tag}]: tol2=None  tol0(global)={s0:.3f}")
                (same_scores if same else distinct_scores).append((s2, s0))

    def summarize(name, vals):
        v2 = [v[0] for v in vals if v[0] is not None]
        v0 = [v[1] for v in vals if v[1] is not None]
        if v2:
            print(f"{name} tol2: n={len(v2)} min={min(v2):.3f} median={np.median(v2):.3f} max={max(v2):.3f}")
        if v0:
            print(f"{name} tol0: n={len(v0)} min={min(v0):.3f} median={np.median(v0):.3f} max={max(v0):.3f}")

    print("\n=== summary ===")
    summarize("same-source  ", same_scores)
    summarize("distinct     ", distinct_scores)


if __name__ == "__main__":
    main()
