"""Task 2.4 synthetic tests for the shared-flaw event fingerprint
(CC_TAPEMATCH_ADDON.md Task 2): dropout/click/cut extraction, pair scoring
under speed warp, and independent-flaw rejection. No live audio.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tapematch import match  # noqa: E402

SR = 16000
CFG = {"flaw_fingerprint": {
    "quiet_energy_percentile": 25, "min_quiet_sec": 3.0,
    "dropout_frame_sec": 0.02, "dropout_local_window_sec": 2.0,
    "dropout_depth_db": 20.0, "dropout_min_sec": 0.04, "dropout_max_sec": 0.8,
    "click_local_window_ms": 50.0, "click_sigma": 6.0, "click_max_dur_ms": 5.0,
    "click_cap": 200,
    "cut_frame_sec": 0.1, "cut_sigma": 4.0,
    "flaw_min_events": 5, "tol_sec": 0.5,
    "merge_threshold": 0.6, "min_events_merge": 8,
}}


DUR_SEC = 40.0
TAIL_SEC = 12.0   # >25% of DUR_SEC so the quiet-percentile threshold cleanly
                  # separates this tail from the (near-stationary) body instead
                  # of landing inside the body's own float-level jitter.


def _base_signal(dur_sec: float, seed: int) -> np.ndarray:
    """Tone + noise bed — a plausible "recording" with no flaws.

    Noise kept modest relative to the tone so the tone (not broadband noise)
    dominates the spectral centroid — needed for the cut-detector test, where
    the injected splice must move the centroid, not just add noise power.

    Ends in an unambiguous near-silent tail (last `TAIL_SEC`): a pure
    stationary tone+noise bed has virtually IDENTICAL per-second energy
    throughout, so `find_quiet_segments`'s energy-percentile threshold would
    otherwise sit on a knife-edge inside that near-degenerate cluster and flag
    a handful of essentially-random one-second frames as "quiet" (including,
    by bad luck, frames near an injected flaw) — a synthetic-signal artifact,
    not a real-recording behaviour. A clearly-quiet block that is >25% of the
    duration keeps the whole threshold-boundary jitter confined to that block.
    """
    rng = np.random.default_rng(seed)
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    x = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.01 * rng.standard_normal(n)
    tail0 = int((dur_sec - TAIL_SEC) * SR)
    x[tail0:] = 0.002 * rng.standard_normal(n - tail0)
    return x.astype(np.float32)


def _inject_dropout(x: np.ndarray, t_sec: float, dur_sec: float = 0.2) -> np.ndarray:
    y = x.copy()
    i0 = int(t_sec * SR)
    i1 = i0 + int(dur_sec * SR)
    y[i0:i1] *= 0.03   # ~ -30 dB
    return y


def _inject_click(x: np.ndarray, t_sec: float, amp: float = 6.0) -> np.ndarray:
    y = x.copy()
    i0 = int(t_sec * SR)
    y[i0] += amp
    return y


def _inject_cut(x: np.ndarray, t_sec: float, cut_dur_sec: float = 3.0) -> np.ndarray:
    """Bounded splice-in: for `cut_dur_sec`, swap in a louder, higher-pitched
    tone (both RMS and spectral centroid jump at the seam — the joint
    signature), then restore the original signal. Bounded (rather than
    running to the end of the array) so it never overwrites the quiet tail
    `_base_signal` relies on for `find_quiet_segments`.
    """
    y = x.copy()
    i0 = int(t_sec * SR)
    i1 = min(len(x), i0 + int(cut_dur_sec * SR))
    n2 = i1 - i0
    t2 = np.arange(n2) / SR
    y[i0:i1] = (0.5 * np.sin(2 * np.pi * 2500.0 * t2)
               + 0.01 * np.random.default_rng(99).standard_normal(n2)).astype(np.float32)
    return y


def _make_flawed(seed: int, dropout_t=10.0, click_t=5.0, cut_t=20.0,
                 dur_sec: float = DUR_SEC) -> np.ndarray:
    x = _base_signal(dur_sec, seed)
    x = _inject_dropout(x, dropout_t)
    x = _inject_click(x, click_t)
    x = _inject_cut(x, cut_t)
    return x


def _kinds_near(events, kind: str, t_sec: float, tol: float = 0.5) -> list:
    return [e for e in events if e[1] == kind and abs(e[0] - t_sec) < tol]


# ── 2.1: extraction ───────────────────────────────────────────────────────

def test_extract_flaw_events_finds_injected_dropout():
    x = _base_signal(DUR_SEC, seed=1)
    x = _inject_dropout(x, 10.0)
    events = match.extract_flaw_events(x, SR, CFG)
    hits = _kinds_near(events, "dropout", 10.0)
    assert hits, f"expected a dropout near t=10.0, got {events}"


def test_extract_flaw_events_finds_injected_click():
    x = _base_signal(DUR_SEC, seed=2)
    x = _inject_click(x, 5.0)
    events = match.extract_flaw_events(x, SR, CFG)
    hits = _kinds_near(events, "click", 5.0)
    assert hits, f"expected a click near t=5.0, got {events}"


def test_extract_flaw_events_finds_injected_cut():
    x = _base_signal(DUR_SEC, seed=3)
    x = _inject_cut(x, 20.0)
    events = match.extract_flaw_events(x, SR, CFG)
    hits = _kinds_near(events, "cut", 20.0, tol=0.3)
    assert hits, f"expected a cut near t=20.0, got {events}"


def test_extract_flaw_events_all_three_kinds():
    x = _make_flawed(seed=4)
    events = match.extract_flaw_events(x, SR, CFG)
    kinds = {k for _t, k, _s in events}
    assert kinds == {"dropout", "click", "cut"}, f"got kinds {kinds}"
    assert _kinds_near(events, "dropout", 10.0)
    assert _kinds_near(events, "click", 5.0)
    assert _kinds_near(events, "cut", 20.0, tol=0.3)


def test_extract_flaw_events_excludes_between_song_quiet_gap():
    """A long, genuinely quiet between-song gap must NOT register as a dropout."""
    rng = np.random.default_rng(5)
    n = int(30.0 * SR)
    t = np.arange(n) / SR
    x = 0.2 * np.sin(2 * np.pi * 220.0 * t) + 0.03 * rng.standard_normal(n)
    # A 4s near-silent gap (well past the 800ms dropout cap and long enough to
    # register as a quiet segment) starting at t=12.
    i0, i1 = int(12.0 * SR), int(16.0 * SR)
    x[i0:i1] = 0.0005 * rng.standard_normal(i1 - i0)
    x = x.astype(np.float32)
    events = match.extract_flaw_events(x, SR, CFG)
    dropouts_in_gap = [e for e in events if e[1] == "dropout" and 12.0 <= e[0] <= 16.0]
    assert not dropouts_in_gap, f"quiet gap misdetected as dropout(s): {dropouts_in_gap}"


# ── 2.2: pair scoring ──────────────────────────────────────────────────────

def test_flaw_match_score_none_below_min_events():
    few_a = [(1.0, "click", 8.0), (2.0, "click", 8.0)]
    few_b = [(1.0, "click", 8.0), (2.0, "click", 8.0)]
    assert match.flaw_match_score(few_a, few_b, 1.0, 0.0, CFG) is None


def _synth_events(n: int, seed: int, dur_sec: float = 1200.0) -> list:
    rng = np.random.default_rng(seed)
    kinds = ["dropout", "click", "cut"]
    out = []
    for _ in range(n):
        out.append((float(rng.uniform(0, dur_sec)), kinds[int(rng.integers(0, 3))],
                    float(rng.uniform(1.0, 10.0))))
    out.sort(key=lambda e: e[0])
    return out


def test_flaw_match_score_inherited_flaws_near_one_under_speed_warp():
    """B is A's event timeline mapped through a +5000ppm warp — same lineage."""
    events_a = _synth_events(20, seed=10)
    ppm = 5000.0
    ratio = 1.0 + ppm * 1e-6
    offset = 1.3   # small constant alignment offset
    events_b = [(offset + ratio * t, k, s) for t, k, s in events_a]
    score = match.flaw_match_score(events_a, events_b, ratio, offset, CFG)
    assert score is not None
    assert score >= 0.95, f"expected near-1.0 inherited-flaw score, got {score}"


def test_flaw_match_score_inherited_flaws_near_one_under_negative_speed_warp():
    events_a = _synth_events(20, seed=11)
    ppm = -5000.0
    ratio = 1.0 + ppm * 1e-6
    offset = -0.4
    events_b = [(offset + ratio * t, k, s) for t, k, s in events_a]
    score = match.flaw_match_score(events_a, events_b, ratio, offset, CFG)
    assert score is not None
    assert score >= 0.95, f"expected near-1.0 inherited-flaw score, got {score}"


def test_flaw_match_score_independent_flaws_near_zero():
    events_a = _synth_events(20, seed=20)
    events_b = _synth_events(20, seed=21)   # independent random timeline
    score = match.flaw_match_score(events_a, events_b, 1.0, 0.0, CFG)
    assert score is not None
    assert score <= 0.15, f"expected near-0 independent-flaw score, got {score}"


def test_flaw_match_score_never_coerces_none_to_zero():
    # Absence of events (below flaw_min_events) must stay None, not become 0.0.
    result = match.flaw_match_score([], [], 1.0, 0.0, CFG)
    assert result is None
    assert not isinstance(result, float)
