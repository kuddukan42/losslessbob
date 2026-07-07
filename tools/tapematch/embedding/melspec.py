"""melspec.py — shared log-mel front end for Tier C (CC_TAPEMATCH_ADDON Task 7).

ONE implementation used by BOTH training (data.py, on GPU) and inference (infer.py,
on CPU) so the model sees identical features either way — train/infer parity is a
correctness requirement, not an optimisation. Parameters come from config.yaml MEL.

Input:  waveform (B, n_samples) float32 @ 16 kHz.
Output: (B, 1, N_MELS, n_frames) — dB-scaled, per-window standardised (zero-mean/
        unit-var over freq×time), ready for ConvEncoder.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torchaudio


class LogMelSpec(nn.Module):
    def __init__(self, cfg: dict) -> None:
        super().__init__()
        m = cfg["MEL"]
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=cfg["AUDIO"]["FS"],
            n_fft=m["N_FFT"], hop_length=m["HOP"], n_mels=m["N_MELS"],
            f_min=m["F_MIN"], f_max=m["F_MAX"], power=2.0)
        self.to_db = torchaudio.transforms.AmplitudeToDB(stype="power", top_db=m["TOP_DB"])

    def forward(self, wav: torch.Tensor) -> torch.Tensor:
        if wav.dim() == 1:
            wav = wav.unsqueeze(0)
        x = self.to_db(self.mel(wav))                 # (B, n_mels, T)
        # per-window standardisation (robust to level/gain differences across transfers)
        mu = x.mean(dim=(1, 2), keepdim=True)
        sd = x.std(dim=(1, 2), keepdim=True).clamp_min(1e-5)
        x = (x - mu) / sd
        return x.unsqueeze(1)                          # (B, 1, n_mels, T)
