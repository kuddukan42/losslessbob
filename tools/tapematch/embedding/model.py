"""model.py — ConvEncoder + NT-Xent/InfoNCE loss for Tier C (CC_TAPEMATCH_ADDON Task 7.2).

Small conv encoder (<=10M params) mapping the shared log-mel front end
(melspec.LogMelSpec, (B,1,N_MELS=64,T)) to an L2-normalized embedding
(B, EMB_DIM=128). Paired with a symmetric NT-Xent loss: positives are the two
augmented views of the same window; ALL other batch entries (both views) are
in-batch negatives, including the sampler-guaranteed same-show hard negatives
(TRAIN.HARD_NEG_MIN_FRAC in config.yaml) — no extra masking needed, the loss
pushes every non-positive pair apart uniformly.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvEncoder(nn.Module):
    """Small conv encoder: (B,1,N_MELS,T) log-mel -> (B,EMB_DIM) L2-normalized.

    Architecture: a stack of stride-2 conv blocks (Conv2d + BatchNorm2d + ReLU)
    downsampling jointly on the frequency and time axes, an adaptive average
    pool to collapse the remaining spatial extent (so arbitrary T is
    supported), then a linear projection to EMB_DIM followed by L2
    normalization. Base channel width and embedding dim come from
    cfg["MODEL"] (config.yaml MODEL block) so param count is config-driven.

    Attributes:
        emb_dim: Output embedding dimensionality.
    """

    def __init__(self, cfg: dict) -> None:
        """Builds the encoder from the MODEL block of config.yaml.

        Args:
            cfg: Full config dict (as produced by yaml.safe_load(config.yaml)).
                Uses cfg["MODEL"]["WIDTH"] (base conv width) and
                cfg["MODEL"]["EMB_DIM"] (output embedding dim).
        """
        super().__init__()
        m = cfg["MODEL"]
        width = int(m["WIDTH"])
        self.emb_dim = int(m["EMB_DIM"])

        def block(c_in: int, c_out: int, stride: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(c_in, c_out, kernel_size=3, stride=stride, padding=1,
                          bias=False),
                nn.BatchNorm2d(c_out),
                nn.ReLU(inplace=True),
            )

        # (B,1,64,T) -> stride-1 stem, then 4x stride-2 blocks downsampling
        # freq+time jointly (64 -> 32 -> 16 -> 8 -> 4; T shrinks likewise).
        self.stem = block(1, width, stride=1)
        self.stage1 = block(width, width, stride=2)
        self.stage2 = block(width, width * 2, stride=2)
        self.stage3 = block(width * 2, width * 2, stride=2)
        self.stage4 = block(width * 2, width * 4, stride=2)

        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(width * 4, self.emb_dim)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """Encodes log-mel spectrograms into L2-normalized embeddings.

        Args:
            mel: (B, 1, N_MELS, T) log-mel tensor, e.g. from melspec.LogMelSpec.

        Returns:
            (B, EMB_DIM) tensor, unit L2 norm along dim=-1.
        """
        x = self.stem(mel)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        x = self.pool(x).flatten(1)          # (B, width*4)
        z = self.proj(x)                     # (B, EMB_DIM)
        return F.normalize(z, p=2, dim=-1)


def nt_xent(z1: torch.Tensor, z2: torch.Tensor, temperature: float) -> torch.Tensor:
    """Symmetric NT-Xent (InfoNCE) loss over a batch of two augmented views.

    z1[i] and z2[i] are the two augmented views of window i (the positive
    pair); every other entry across both views (2B-2 of them) is treated as
    an in-batch negative. The data sampler guarantees >=25%
    (TRAIN.HARD_NEG_MIN_FRAC) of each batch is same-date different-source
    hard negatives, so they simply sit in this in-batch negative set and the
    loss pushes them apart — no extra masking is required.

    Args:
        z1: (B, EMB_DIM) L2-normalized embeddings, view 1.
        z2: (B, EMB_DIM) L2-normalized embeddings, view 2 (same window order).
        temperature: Softmax temperature (config TRAIN.TEMPERATURE).

    Returns:
        Scalar loss tensor.
    """
    batch_size = z1.shape[0]
    z = torch.cat([z1, z2], dim=0)                        # (2B, D)
    sim = torch.matmul(z, z.t()) / temperature             # (2B, 2B)

    n = 2 * batch_size
    self_mask = torch.eye(n, dtype=torch.bool, device=z.device)
    sim = sim.masked_fill(self_mask, float("-inf"))

    # Row i in [0,B) has its positive at i+B; row i in [B,2B) has it at i-B.
    idx = torch.arange(n, device=z.device)
    targets = (idx + batch_size) % n

    return F.cross_entropy(sim, targets)
