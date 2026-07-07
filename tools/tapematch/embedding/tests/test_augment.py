"""Tests for embedding/augment.py — transfer-chain augmentation (CC_TAPEMATCH_ADDON
Task 7.1). Fast synthetic-signal tests only; no live audio, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tools/tapematch
from embedding.augment import AugmentChain  # noqa: E402

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"
CFG = yaml.safe_load(_CONFIG_PATH.read_text())
FS = int(CFG["AUDIO"]["FS"])
N = FS  # 1 s window, matches AUDIO.WIN_SEC

_OP_NAMES = [
    "_speed_warp", "_lowpass", "_mp3_roundtrip", "_tape_hiss",
    "_level_ride", "_eq_tilt", "_wow_flutter",
]


def _tone_plus_noise(seed: int = 1) -> np.ndarray:
    """Simple sine + gaussian noise signal for length/finite/changed checks."""
    rs = np.random.RandomState(seed)
    t = np.arange(N, dtype=np.float64) / FS
    wav = 0.3 * np.sin(2 * np.pi * 440.0 * t) + 0.05 * rs.randn(N)
    return wav.astype(np.float32)


def _broadband_signal(seed: int = 7) -> np.ndarray:
    """Band-limited noise (200-4000 Hz) — a continuous spectral envelope like real
    audio, needed for a meaningful log-magnitude-spectrum similarity check (a pure
    tone's line spectrum shifts entirely out of its bins under a few-% speed warp
    and gives a spuriously low point-wise correlation; broadband content does not).
    """
    rs = np.random.RandomState(seed)
    noise = rs.randn(N)
    sos = butter(4, [200.0 / (FS / 2), 4000.0 / (FS / 2)], btype="band", output="sos")
    wav = sosfiltfilt(sos, noise)
    wav = wav / (np.max(np.abs(wav)) * 1.2)
    return wav.astype(np.float32)


def _logmag_spectrum(x: np.ndarray) -> np.ndarray:
    return np.log(np.abs(np.fft.rfft(x.astype(np.float64))) + 1e-6)


def _make_chain(seed: int = 0) -> AugmentChain:
    return AugmentChain(CFG, np.random.default_rng(seed))


@pytest.mark.parametrize("op_name", _OP_NAMES)
def test_op_finite_same_length_and_changed(op_name: str) -> None:
    """Every op individually: finite output, same length as input, and actually
    changes the signal (not a silent no-op)."""
    wav = _tone_plus_noise()
    chain = _make_chain(seed=123)
    fn = getattr(chain, op_name)
    out = fn(wav.copy())

    assert out.dtype == np.float32
    assert out.shape == wav.shape
    assert np.all(np.isfinite(out))
    assert not np.allclose(out, wav, atol=1e-6)


def test_mp3_roundtrip_correlates_but_not_identical() -> None:
    """MP3 op is a real lossy round-trip: output tracks the input waveform closely
    (it isn't garbage) but is not byte/value-identical (it IS lossy)."""
    wav = _tone_plus_noise()
    chain = _make_chain(seed=5)
    out = chain._mp3_roundtrip(wav.copy())

    assert not np.array_equal(out, wav)
    corr = np.corrcoef(wav.astype(np.float64), out.astype(np.float64))[0, 1]
    assert corr > 0.8, f"mp3 round-trip waveform corr too low: {corr}"


def test_chain_deterministic_under_equal_seed_rng() -> None:
    """Two AugmentChain instances seeded with equal-state Generators must produce
    byte-identical output — required for reproducible training runs."""
    wav = _broadband_signal()
    chain_a = AugmentChain(CFG, np.random.default_rng(42))
    chain_b = AugmentChain(CFG, np.random.default_rng(42))

    out_a = chain_a(wav.copy())
    out_b = chain_b(wav.copy())

    assert np.array_equal(out_a, out_b)


def test_chain_output_shape_dtype_finite() -> None:
    wav = _broadband_signal()
    chain = _make_chain(seed=9)
    out = chain(wav.copy())

    assert out.dtype == np.float32
    assert out.shape == wav.shape
    assert np.all(np.isfinite(out))


@pytest.mark.parametrize("seed", range(10))
def test_chain_stays_similar_to_source(seed: int) -> None:
    """A full augmented view must stay a plausible SYNTHETIC POSITIVE of the
    source — sanity that GEN_STACK composition doesn't destroy the signal.
    Uses Pearson corr of the two log-magnitude spectra (shift/phase-robust,
    unlike waveform corr under speed warp) against a modest bar.
    """
    wav = _broadband_signal()
    chain = AugmentChain(CFG, np.random.default_rng(seed))
    out = chain(wav.copy())

    corr = np.corrcoef(_logmag_spectrum(wav), _logmag_spectrum(out))[0, 1]
    assert corr > 0.3, f"seed={seed}: augmented view diverged too far, corr={corr}"


def test_output_length_matches_input_for_odd_length() -> None:
    """Non-round input lengths must still round-trip through length-changing ops
    (speed warp, mp3) back to the exact input length via crop/zero-pad."""
    wav = _tone_plus_noise()[: N - 37]  # deliberately not window-aligned
    chain = _make_chain(seed=3)
    out = chain(wav.copy())
    assert out.shape == wav.shape
