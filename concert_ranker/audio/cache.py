"""Per-track shared spectral cache — the single most important performance object.

THE GUARDRAIL: a track is decoded ONCE and STFT'd ONCE. Every feature extractor
receives a TrackCache and derives its metrics from these pre-computed arrays.
No extractor decodes audio or computes its own STFT. This is what keeps the
15k-corpus wall-clock in days rather than months — the expensive operations
(decode, STFT) happen exactly once per track, and ~15 metrics ride on top of
them as cheap array arithmetic.

Two-rate: the bulk cache is built at BULK_SR (22.05k) for the perceptual
metrics. The native-rate data needed for hiss/air/HF-ceiling/lossy is a SEPARATE,
much cheaper object (NativeProbe) built from only a few short windows at 44.1k,
not a second full decode.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class TrackCache:
    """Everything the bulk-rate feature extractors need, computed once."""
    path: str
    sr: int
    duration_sec: float

    # Time-domain (mono mix used for most analysis; stereo kept for spatial)
    mono: np.ndarray              # shape (n,)
    left: np.ndarray | None       # shape (n,) or None if mono source
    right: np.ndarray | None
    is_stereo: bool

    # Frequency-domain (computed once, shared by all spectral features)
    stft_mag: np.ndarray          # |STFT| magnitude, shape (n_freqs, n_frames)
    freqs: np.ndarray             # shape (n_freqs,) bin center frequencies
    times: np.ndarray             # shape (n_frames,) frame center times (sec)
    psd_db: np.ndarray            # Welch PSD in dB, shape (n_psd_freqs,)
    psd_freqs: np.ndarray

    # Cheap precomputed reductions reused across families
    frame_energy_db: np.ndarray   # per-frame broadband energy, shape (n_frames,)
    onset_env: np.ndarray         # spectral-flux onset strength, shape (n_frames,)

    def band_db(self, lo: float, hi: float) -> float:
        """Mean PSD (dB) in [lo, hi). The workhorse for every band-ratio metric."""
        m = (self.psd_freqs >= lo) & (self.psd_freqs < hi)
        if not m.any():
            return float("nan")
        return float(self.psd_db[m].mean())

    def quiet_frame_mask(self, percentile: float = 20.0) -> np.ndarray:
        """Boolean mask of low-energy frames (musical quiet passages).

        Used by crowd-SNR and hiss: measure the noise/crowd floor where the
        music itself is quiet, not during loud passages.
        """
        thr = np.percentile(self.frame_energy_db, percentile)
        return self.frame_energy_db < thr


@dataclass
class NativeProbe:
    """High-frequency evidence from a few native-rate windows. Cheap.

    Built from NATIVE_N_WINDOWS windows of NATIVE_WINDOW_SEC each, decoded at
    NATIVE_SR. Carries only the averaged native-rate PSD — enough for hiss,
    air, HF ceiling and lossy brick-wall detection, none of which need the
    whole 2-hour file or fine time resolution.
    """
    sr: int
    psd_db: np.ndarray
    psd_freqs: np.ndarray
    nyquist_hz: float

    def band_db(self, lo: float, hi: float) -> float:
        m = (self.psd_freqs >= lo) & (self.psd_freqs < hi)
        if not m.any():
            return float("nan")
        return float(self.psd_db[m].mean())


# ─────────────────────────────────────────────────────────────────────────────
# Cache construction. In production these read real files; here they accept
# arrays so the scoring brain is testable without audio I/O on this machine.
# ─────────────────────────────────────────────────────────────────────────────

def build_track_cache(mono, sr, *, left=None, right=None, n_fft=2048, hop=512,
                       path="<mem>") -> TrackCache:
    """Build the shared cache from already-decoded PCM.

    The real audio/io.py decodes the file (once) and calls this. Kept separate
    so the DSP is unit-testable with synthetic signals.
    """
    from scipy.signal import stft, welch

    mono = np.asarray(mono, dtype=np.float32)
    n = len(mono)
    duration = n / sr

    f, t, Z = stft(mono, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None)
    mag = np.abs(Z).astype(np.float32)

    pf, psd = welch(mono, fs=sr, nperseg=min(4096, n))
    psd_db = (10.0 * np.log10(psd + 1e-12)).astype(np.float32)

    # per-frame broadband energy (dB) from the magnitude we already have
    frame_energy = (mag ** 2).sum(axis=0) + 1e-12
    frame_energy_db = (10.0 * np.log10(frame_energy)).astype(np.float32)

    # spectral-flux onset envelope (half-wave rectified positive spectral diff)
    diff = np.diff(mag, axis=1, prepend=mag[:, :1])
    onset_env = np.maximum(diff, 0).sum(axis=0).astype(np.float32)

    return TrackCache(
        path=path, sr=sr, duration_sec=duration,
        mono=mono, left=left, right=right,
        is_stereo=left is not None and right is not None,
        stft_mag=mag, freqs=f.astype(np.float32), times=t.astype(np.float32),
        psd_db=psd_db, psd_freqs=pf.astype(np.float32),
        frame_energy_db=frame_energy_db, onset_env=onset_env,
    )


def build_native_probe(windows, sr) -> NativeProbe:
    """Average native-rate PSD across the sampled windows.

    `windows` is a list of mono float arrays at native `sr`. Real code samples
    these from the file at NATIVE_SR; here it accepts arrays for testability.
    """
    from scipy.signal import welch
    psds = []
    pf = None
    for w in windows:
        w = np.asarray(w, dtype=np.float32)
        if len(w) < 4096:
            continue
        pf, psd = welch(w, fs=sr, nperseg=4096)
        psds.append(psd)
    if not psds:
        return NativeProbe(sr=sr, psd_db=np.array([]), psd_freqs=np.array([]),
                           nyquist_hz=sr / 2)
    psd_mean = np.mean(psds, axis=0)
    return NativeProbe(
        sr=sr,
        psd_db=(10.0 * np.log10(psd_mean + 1e-12)).astype(np.float32),
        psd_freqs=pf.astype(np.float32),
        nyquist_hz=sr / 2,
    )
