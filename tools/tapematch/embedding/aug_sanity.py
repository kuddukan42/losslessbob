"""aug_sanity.py — Gate 7.3.1 augmentation-invariance sanity check (CC_TAPEMATCH_ADDON 7.3).

Loads the trained Tier C checkpoint and measures cosine similarity between each
sampled cached window's "clean" embedding (raw window, unaugmented) and the
embedding of one augmented view (``augment.AugmentChain``, the full training
augmentation menu). Gate 7.3.1 requires self-vs-aug cosine >= 0.8 (mean/median):
the encoder must be invariant to the transfer-chain degradations it was trained
against (a bar the earlier content-based "invariance triplet" signal never had).

    tools/tapematch/.venv-emb/bin/python tools/tapematch/embedding/aug_sanity.py \
        --device cuda
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch
import yaml

from augment import AugmentChain
from melspec import LogMelSpec
from model import ConvEncoder

_HERE = Path(__file__).resolve().parent
CACHE_DIR = _HERE / "audio_cache"
PROJECT_ROOT = _HERE.parent.parent.parent

log = logging.getLogger("tierc.aug_sanity")


def _load_model(
    cfg: dict, ckpt_path: Path, device: torch.device
) -> tuple[LogMelSpec, ConvEncoder]:
    """Loads the shared mel front end and trained encoder onto ``device``.

    Args:
        cfg: Embedding config dict (config.yaml).
        ckpt_path: Path to the trained checkpoint (train.py output).
        device: Torch device to run inference on.

    Returns:
        A ``(mel, model)`` tuple, both in eval mode.
    """
    mel = LogMelSpec(cfg).to(device).eval()
    model = ConvEncoder(cfg).to(device).eval()
    state = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(state["model"] if "model" in state else state)
    log.info("loaded checkpoint %s (%d steps)", ckpt_path, state.get("steps", -1))
    return mel, model


@torch.no_grad()
def _embed(
    mel: LogMelSpec, model: ConvEncoder, wav: np.ndarray, device: torch.device
) -> np.ndarray:
    """Embeds a single 1-D waveform window.

    Args:
        mel: Shared log-mel front end.
        model: Trained ConvEncoder.
        wav: 1-D float32 waveform at the config sample rate.
        device: Torch device to run on.

    Returns:
        An ``(EMB_DIM,)`` L2-normalized numpy vector.
    """
    t = torch.from_numpy(np.asarray(wav, dtype=np.float32)).unsqueeze(0).to(device)
    z = model(mel(t))
    return z.squeeze(0).cpu().numpy()


def main() -> int:
    """Runs the Gate 7.3.1 aug-sanity check and logs the cosine-similarity distribution."""
    ap = argparse.ArgumentParser(description="Gate 7.3.1 augmentation sanity check.")
    ap.add_argument("--config", type=Path, default=_HERE / "config.yaml")
    ap.add_argument("--ckpt", type=Path, default=None, help="defaults to config CHECKPOINT.")
    ap.add_argument("--n-samples", type=int, default=200)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(args.config.read_text())
    device = torch.device(
        args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu"
    )
    ckpt_path = args.ckpt or (PROJECT_ROOT / cfg["CHECKPOINT"])
    mel, model = _load_model(cfg, ckpt_path, device)

    idx = json.loads((CACHE_DIR / "index.json").read_text())
    windows = np.load(CACHE_DIR / "windows.npy", mmap_mode="r")
    n_total = idx["n"]

    rng = np.random.default_rng(args.seed)
    n_sample = min(args.n_samples, n_total)
    sample_ids = rng.choice(n_total, size=n_sample, replace=False)
    aug = AugmentChain(cfg, np.random.default_rng(args.seed + 1))

    sims: list[float] = []
    for count, i in enumerate(sample_ids):
        raw = np.asarray(windows[i], dtype=np.float32)
        z_self = _embed(mel, model, raw, device)
        aug_view = aug(raw)
        z_aug = _embed(mel, model, aug_view, device)
        cos = float(
            np.dot(z_self, z_aug)
            / (np.linalg.norm(z_self) * np.linalg.norm(z_aug) + 1e-12)
        )
        sims.append(cos)
        if (count + 1) % 50 == 0:
            log.info("  %d/%d windows processed", count + 1, n_sample)

    arr = np.asarray(sims, dtype=np.float64)
    mean, median, minimum = float(arr.mean()), float(np.median(arr)), float(arr.min())
    p10 = float(np.percentile(arr, 10))
    log.info(
        "aug-sanity (n=%d): mean=%.4f median=%.4f min=%.4f p10=%.4f",
        arr.size, mean, median, minimum, p10,
    )
    gate_min = float(cfg["EVAL"]["SELF_AUG_MIN"])
    passed = mean >= gate_min and median >= gate_min
    log.info(
        "GATE 7.3.1 (self-vs-aug >= %.2f mean/median): %s",
        gate_min, "PASS" if passed else "FAIL",
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
