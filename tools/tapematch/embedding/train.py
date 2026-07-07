"""train.py — Tier C contrastive training loop (CC_TAPEMATCH_ADDON Task 7.2).

Self-supervised NT-Xent: positives = two augmentations of the same window; negatives =
the rest of the batch, with >=25% guaranteed same-show hard negatives by the sampler.
Curator labels are never used. GPU (RTX 3080); checkpoint → config CHECKPOINT.

    tools/tapematch/.venv-emb/bin/python tools/tapematch/embedding/train.py \
        --epochs 30 --device cuda
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader

from augment import AugmentChain
from data import WindowCache, HardNegBatchSampler
from melspec import LogMelSpec
from model import ConvEncoder, nt_xent

_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent.parent
log = logging.getLogger("tierc.train")


def _lr_at(step: int, total: int, warmup: int, base: float) -> float:
    if step < warmup:
        return base * step / max(warmup, 1)
    p = (step - warmup) / max(total - warmup, 1)
    return base * 0.5 * (1 + math.cos(math.pi * min(p, 1.0)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier C contrastive training.")
    ap.add_argument("--config", type=Path, default=_HERE / "config.yaml")
    ap.add_argument("--epochs", type=int, default=0, help="0 = config TRAIN.EPOCHS.")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--max-steps", type=int, default=0, help="debug cap.")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = yaml.safe_load(args.config.read_text())
    tr = cfg["TRAIN"]
    torch.manual_seed(tr["SEED"]); np.random.seed(tr["SEED"])
    dev = torch.device(args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu")
    epochs = args.epochs or tr["EPOCHS"]

    ds = WindowCache(cfg, AugmentChain)
    sampler = HardNegBatchSampler(ds.group, tr["BATCH_SIZE"], tr["HARD_NEG_MIN_FRAC"], tr["SEED"])
    loader = DataLoader(ds, batch_sampler=sampler, num_workers=tr["NUM_WORKERS"],
                        pin_memory=(dev.type == "cuda"), persistent_workers=tr["NUM_WORKERS"] > 0)
    log.info("dataset: %d windows, %d groups, %d batches/epoch",
             ds.n, int(ds.group.max()) + 1, len(sampler))

    mel = LogMelSpec(cfg).to(dev).eval()      # fixed front end (no params)
    model = ConvEncoder(cfg).to(dev).train()
    opt = torch.optim.AdamW(model.parameters(), lr=tr["LR"], weight_decay=tr["WEIGHT_DECAY"])
    total_steps = len(sampler) * epochs
    temp = tr["TEMPERATURE"]

    step = 0
    t0 = time.monotonic()
    for ep in range(epochs):
        run = 0.0
        for v1, v2, _grp in loader:
            lr = _lr_at(step, total_steps, tr["WARMUP_STEPS"], tr["LR"])
            for g in opt.param_groups:
                g["lr"] = lr
            v1 = v1.to(dev, non_blocking=True); v2 = v2.to(dev, non_blocking=True)
            with torch.no_grad():
                m1, m2 = mel(v1), mel(v2)
            z1, z2 = model(m1), model(m2)
            loss = nt_xent(z1, z2, temp)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            run += float(loss)
            step += 1
            if step % 50 == 0:
                log.info("ep%d step%d loss=%.4f lr=%.2e (%.1fs)",
                         ep, step, run / 50, lr, time.monotonic() - t0)
                run = 0.0
            if args.max_steps and step >= args.max_steps:
                break
        if args.max_steps and step >= args.max_steps:
            break

    ckpt = PROJECT_ROOT / cfg["CHECKPOINT"]
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(), "cfg": cfg, "steps": step}, ckpt)
    log.info("saved %s (%d steps, %.1f min)", ckpt, step, (time.monotonic() - t0) / 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
