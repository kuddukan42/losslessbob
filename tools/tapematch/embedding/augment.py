"""augment.py — transfer-chain audio augmentation (CC_TAPEMATCH_ADDON Task 7.1).

Produces SYNTHETIC POSITIVE views for the Tier C contrastive embedding: two
augmented views of the same window are pulled together by the training loss,
so the augmentation menu must model *observed* real-world tape/transfer
degradation chains rather than generic audio noise. Each op mirrors an
evidence-backed degradation named in CC_TAPEMATCH_ADDON.md 7.1 (speed offsets,
band-limiting, lossy codec lineage, hiss, gain rides, EQ tilt, wow/flutter),
and ``GEN_STACK`` composes 2-3 of them per call — "a 3rd-gen tape is a
composition of degradations."

All parameters (per-op probability + magnitude) live in config.yaml's
``AUGMENT`` block; nothing here is a magic number. Uses numpy + scipy only,
plus a real ffmpeg subprocess round-trip for the MP3 op (no librosa).
"""

from __future__ import annotations

import logging
import subprocess
from fractions import Fraction

import numpy as np
from scipy.signal import butter, correlate, resample_poly, sosfiltfilt

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SEC = 30


class AugmentChain:
    """Composable transfer-chain augmentation for one audio window.

    Each call draws a random subset of degradation ops (per ``GEN_STACK``
    in config), applies each with its own configured probability, and
    returns a same-length 1-D float32 waveform. All randomness is drawn
    from the injected ``rng`` so that two chains seeded with equal-state
    generators produce byte-identical output — required for reproducible
    training runs.

    Attributes:
        cfg: Full embedding config dict (must contain ``AUDIO`` and
            ``AUGMENT`` blocks, per config.yaml).
    """

    def __init__(self, cfg: dict, rng: np.random.Generator | None = None) -> None:
        """Initializes the augmentation chain.

        Args:
            cfg: Embedding config dict; reads ``cfg["AUDIO"]["FS"]`` and the
                ``cfg["AUGMENT"]`` per-op probability/parameter block.
            rng: Numpy random Generator to draw all randomness from. If
                ``None``, a fresh unseeded generator is created (non-
                reproducible — pass an explicit seeded rng for training).
        """
        self._cfg = cfg
        self._acfg = cfg["AUGMENT"]
        self._fs = int(cfg["AUDIO"]["FS"])
        self._rng = rng if rng is not None else np.random.default_rng()
        # (name, bound method, probability) — order here is irrelevant; __call__
        # draws its own random subset/order each invocation.
        self._ops: list[tuple[str, "callable[[np.ndarray], np.ndarray]", float]] = [
            ("speed_warp", self._speed_warp, float(self._acfg["SPEED_WARP"]["P"])),
            ("lowpass", self._lowpass, float(self._acfg["LOWPASS"]["P"])),
            ("mp3", self._mp3_roundtrip, float(self._acfg["MP3"]["P"])),
            ("tape_hiss", self._tape_hiss, float(self._acfg["TAPE_HISS"]["P"])),
            ("level_ride", self._level_ride, float(self._acfg["LEVEL_RIDE"]["P"])),
            ("eq_tilt", self._eq_tilt, float(self._acfg["EQ_TILT"]["P"])),
            ("wow_flutter", self._wow_flutter, float(self._acfg["WOW_FLUTTER"]["P"])),
        ]

    def __call__(self, wav: np.ndarray) -> np.ndarray:
        """Applies a random composed degradation chain to one window.

        Picks a target op count in ``[GEN_STACK.MIN_OPS, GEN_STACK.MAX_OPS]``,
        visits the ops in a random order, and applies each one whose own
        ``P`` roll succeeds until the target count is reached (or the op
        list is exhausted). Output is cropped/zero-padded back to the input
        length so downstream fixed-size windowing is unaffected by any
        length-changing op (speed warp, MP3 round-trip).

        Args:
            wav: 1-D float32 mono waveform at ``cfg["AUDIO"]["FS"]``.

        Returns:
            1-D float32 waveform, same length as ``wav``.
        """
        wav = np.asarray(wav, dtype=np.float32).reshape(-1)
        n = wav.shape[0]
        gs = self._acfg["GEN_STACK"]
        min_ops, max_ops = int(gs["MIN_OPS"]), int(gs["MAX_OPS"])
        target = int(self._rng.integers(min_ops, max_ops + 1))
        order = self._rng.permutation(len(self._ops))

        out = wav
        applied = 0
        for i in order:
            if applied >= target:
                break
            name, fn, p = self._ops[i]
            if self._rng.random() < p:
                out = fn(out)
                applied += 1
        if applied == 0:
            logger.debug("AugmentChain: no op triggered (all P rolls failed this call)")
        return self._fix_length(out, n)

    # -- length bookkeeping ------------------------------------------------

    @staticmethod
    def _fix_length(x: np.ndarray, n: int) -> np.ndarray:
        """Crops or zero-pads ``x`` to exactly ``n`` samples, as float32."""
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        m = x.shape[0]
        if m == n:
            return x
        if m > n:
            return x[:n]
        out = np.zeros(n, dtype=np.float32)
        out[:m] = x
        return out

    # -- ops -----------------------------------------------------------------

    def _speed_warp(self, wav: np.ndarray) -> np.ndarray:
        """Resamples by a random +/- MAX_PCT ratio (tape transport speed offset)."""
        n = wav.shape[0]
        max_pct = float(self._acfg["SPEED_WARP"]["MAX_PCT"])
        pct = self._rng.uniform(-max_pct, max_pct)
        ratio = 1.0 + pct / 100.0
        frac = Fraction(ratio).limit_denominator(1000)
        resampled = resample_poly(wav, frac.numerator, frac.denominator)
        return self._fix_length(resampled, n)

    def _lowpass(self, wav: np.ndarray) -> np.ndarray:
        """Zero-phase Butterworth lowpass at a random cutoff in [F_MIN_HZ, F_MAX_HZ]."""
        cfg = self._acfg["LOWPASS"]
        cutoff = self._rng.uniform(float(cfg["F_MIN_HZ"]), float(cfg["F_MAX_HZ"]))
        nyq = self._fs / 2.0
        wn = min(cutoff / nyq, 0.99)
        sos = butter(6, wn, btype="low", output="sos")
        return sosfiltfilt(sos, wav).astype(np.float32, copy=False)

    def _mp3_roundtrip(self, wav: np.ndarray) -> np.ndarray:
        """Real lossy round-trip: f32le -> MP3 (random KBPS) -> f32le via ffmpeg."""
        n = wav.shape[0]
        kbps = int(self._rng.choice(self._acfg["MP3"]["KBPS"]))
        raw = np.ascontiguousarray(wav, dtype=np.float32).tobytes()

        encode_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le",
            "-ar", str(self._fs), "-ac", "1", "-i", "pipe:0",
            "-f", "mp3", "-b:a", f"{kbps}k", "pipe:1",
        ]
        mp3_bytes = self._run_ffmpeg(encode_cmd, raw)

        decode_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "mp3", "-i", "pipe:0",
            "-f", "f32le", "-ar", str(self._fs), "-ac", "1", "pipe:1",
        ]
        pcm_bytes = self._run_ffmpeg(decode_cmd, mp3_bytes)

        out = np.frombuffer(pcm_bytes, dtype=np.float32)
        if out.size == 0:
            logger.warning("mp3 round-trip (%d kbps) produced empty output; passing through", kbps)
            return wav
        if out.size <= n:
            return self._fix_length(out, n)
        # LAME/ffmpeg's encoder+decoder introduces a fixed frame-alignment delay
        # (observed ~1105 samples @ 16 kHz), so the decoded PCM is a few hundred ms
        # longer than the input with the real content shifted later. Cropping the
        # first n samples naively would return mostly encoder-delay padding and
        # silently misalign the "positive" view from its source. Instead, find the
        # n-sample window inside the decoded signal that best matches the input
        # (FFT cross-correlation over all valid offsets, cheap: <= a few thousand).
        xc = correlate(out.astype(np.float64), wav.astype(np.float64), mode="valid", method="fft")
        best_lag = int(np.argmax(xc))
        return self._fix_length(out[best_lag:best_lag + n], n)

    @staticmethod
    def _run_ffmpeg(cmd: list[str], data: bytes) -> bytes:
        """Runs an ffmpeg pipe:0 -> pipe:1 subprocess and returns stdout bytes."""
        proc = subprocess.run(
            cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=_FFMPEG_TIMEOUT_SEC, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed (exit {proc.returncode}): "
                f"{proc.stderr.decode(errors='replace')[:2000]}"
            )
        return proc.stdout

    def _tape_hiss(self, wav: np.ndarray) -> np.ndarray:
        """Adds gaussian noise at a random SNR drawn from the configured range."""
        lo, hi = self._acfg["TAPE_HISS"]["SNR_DB"]
        snr_db = self._rng.uniform(float(lo), float(hi))
        sig_power = float(np.mean(np.square(wav, dtype=np.float64))) + 1e-12
        noise_power = sig_power / (10.0 ** (snr_db / 10.0))
        noise = self._rng.normal(0.0, np.sqrt(noise_power), size=wav.shape)
        return (wav + noise).astype(np.float32, copy=False)

    def _level_ride(self, wav: np.ndarray) -> np.ndarray:
        """Applies a slow sinusoidal gain envelope up to +/- MAX_DB peak."""
        max_db = float(self._acfg["LEVEL_RIDE"]["MAX_DB"])
        n = wav.shape[0]
        t = np.arange(n, dtype=np.float64) / self._fs
        freq_hz = self._rng.uniform(0.03, 0.15)  # a few slow swells per ~30-60s
        phase = self._rng.uniform(0.0, 2.0 * np.pi)
        depth_db = self._rng.uniform(0.0, max_db)
        gain_db = depth_db * np.sin(2.0 * np.pi * freq_hz * t + phase)
        gain = 10.0 ** (gain_db / 20.0)
        return (wav * gain).astype(np.float32, copy=False)

    def _eq_tilt(self, wav: np.ndarray) -> np.ndarray:
        """Applies a mild linear-in-frequency spectral tilt up to +/- MAX_DB at Nyquist."""
        max_db = float(self._acfg["EQ_TILT"]["MAX_DB"])
        tilt_db = self._rng.uniform(-max_db, max_db)
        n = wav.shape[0]
        spec = np.fft.rfft(wav.astype(np.float64))
        freqs = np.fft.rfftfreq(n, d=1.0 / self._fs)
        nyq = self._fs / 2.0
        gain_db = tilt_db * (freqs / nyq)  # 0 dB at DC -> tilt_db at Nyquist
        spec = spec * (10.0 ** (gain_db / 20.0))
        out = np.fft.irfft(spec, n=n)
        return out.astype(np.float32, copy=False)

    def _wow_flutter(self, wav: np.ndarray) -> np.ndarray:
        """Slow sinusoidal time-warp (+/- MAX_PCT instantaneous rate at RATE_HZ)."""
        cfg = self._acfg["WOW_FLUTTER"]
        max_pct = float(cfg["MAX_PCT"])
        rate_lo, rate_hi = cfg["RATE_HZ"]
        n = wav.shape[0]
        pct = self._rng.uniform(max_pct * 0.3, max_pct)
        rate_hz = self._rng.uniform(float(rate_lo), float(rate_hi))
        phase = self._rng.uniform(0.0, 2.0 * np.pi)

        idx = np.arange(n, dtype=np.float64)
        # displacement amplitude chosen so d(src_idx)/d(idx) has peak deviation
        # pct/100 from unity, i.e. instantaneous speed wobbles by +/- pct%.
        max_disp = (pct / 100.0) * self._fs / (2.0 * np.pi * rate_hz)
        src_idx = idx + max_disp * np.sin(2.0 * np.pi * rate_hz * idx / self._fs + phase)
        src_idx = np.clip(src_idx, 0.0, n - 1.0)
        out = np.interp(src_idx, idx, wav.astype(np.float64))
        return out.astype(np.float32, copy=False)
