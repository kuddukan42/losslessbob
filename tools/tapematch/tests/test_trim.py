"""performance_envelope guard: skip trim on heavily-compressed sources.

Root cause (2026-07-03, live 2025-11-16/17 Glasgow dates): flatness never
gates in practice (tonal synthetic and real recordings alike stay well under
flatness_music_max), so is_music is driven entirely by the fixed p10+6dB
energy threshold. When a source's crowd-padding-vs-performance energy
contrast has been compressed below ~10dB (heavy normalisation/limiting), the
energy signal chatters in and out of that gate every frame instead of
forming sustained blocks, producing spurious multi-minute head/tail cuts.
min_dynamic_range_db bails out to the full recording in that case -- same
safe fallback the function already uses when no sustained region is found.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import trim  # noqa: E402

SR = 16000
CFG = {"trim": {
    "frame_sec": 1.0, "hop_sec": 0.5, "flatness_music_max": 0.45,
    "min_sustain_sec": 8.0, "pad_keep_sec": 5.0, "min_dynamic_range_db": 10.0,
}}

# pad(15s) + music(30s) + pad(15s), matching real crowd/performance/crowd shape.
PAD_SEC, MUSIC_SEC = 15.0, 30.0


def _make_stream(pad_amp: float, music_amp: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pad_n, music_n = int(PAD_SEC * SR), int(MUSIC_SEC * SR)

    def tone_block(n, amp):
        t = np.arange(n) / SR
        x = amp * np.sin(2 * np.pi * 220.0 * t) + amp * 0.5 * np.sin(2 * np.pi * 440.0 * t)
        return (x + 0.001 * rng.standard_normal(n)).astype(np.float32)

    head = tone_block(pad_n, pad_amp)
    body = tone_block(music_n, music_amp)
    tail = tone_block(pad_n, pad_amp)
    return np.concatenate([head, body, tail]).reshape(-1, 1)


def test_wide_dynamic_range_trims_to_performance_window():
    """~26 dB pad/music gap (normal untouched tape) -> trims out the padding."""
    stream = _make_stream(pad_amp=0.01, music_amp=0.2)
    s0, s1 = trim.performance_envelope(stream, SR, CFG)
    # start/end are the detected onset/offset minus/plus pad_keep_sec (5s margin).
    expected_start = PAD_SEC - CFG["trim"]["pad_keep_sec"]
    expected_end = PAD_SEC + MUSIC_SEC + CFG["trim"]["pad_keep_sec"]
    assert expected_start - 2.0 < s0 < expected_start + 2.0, f"expected start near {expected_start}s, got {s0}"
    assert expected_end - 2.0 < s1 < expected_end + 2.0, f"expected end near {expected_end}s, got {s1}"


def test_narrow_dynamic_range_skips_trim():
    """~4 dB pad/music gap (heavily normalised/compressed source) -> below
    min_dynamic_range_db, must keep the full recording rather than guess."""
    stream = _make_stream(pad_amp=0.13, music_amp=0.2)
    s0, s1 = trim.performance_envelope(stream, SR, CFG)
    total_sec = len(stream) / SR
    assert s0 == 0.0
    assert s1 == total_sec


def test_boundary_just_above_threshold_still_trims():
    """~12 dB gap, just above the 10 dB guard -> normal trim behaviour holds."""
    stream = _make_stream(pad_amp=0.05, music_amp=0.2)
    s0, s1 = trim.performance_envelope(stream, SR, CFG)
    total_sec = len(stream) / SR
    assert not (s0 == 0.0 and s1 == total_sec), "expected a real trim, guard fired incorrectly"
