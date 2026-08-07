"""Unit tests for the banter/ASR signal (LISTENING_SIGNALS §3).

Pure-function level only: no faster-whisper model, no audio decode. The
transcription step itself is exercised through a stub model so the gating and
timestamp arithmetic are covered without a 75 MB download.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tapematch import asr  # noqa: E402

CFG = {
    "gap_energy_percentile": 25.0,
    "gap_min_sec": 2.0,
    "gap_pad_sec": 5.0,
    "gap_max_window_sec": 40.0,
    "max_gaps": 40,
    "max_total_sec": 1800.0,
    "min_avg_logprob": -1.0,
    "max_no_speech_prob": 0.6,
    "min_content_tokens": 2,
    "min_utterances": 2,
    "min_similarity": 0.5,
    "offset_tolerance_sec": 5.0,
    "min_corroborating": 2,
    "score_denominator_cap": 4,
    "score_mode": "witnesses",
}


def utt(t: float, text: str, logprob: float = -0.3, no_speech: float = 0.1):
    """Build an Utterance at time *t* (1 s long) for the scoring tests."""
    return asr.make_utterance(t, t + 1.0, text, logprob, no_speech)


# ── tokenisation ───────────────────────────────────────────────────────────────

def test_content_tokens_drops_stopwords_and_punctuation():
    assert asr.content_tokens("Thank you very much, Boston!") == frozenset({"boston"})


def test_content_tokens_pure_filler_is_empty():
    assert asr.content_tokens("Well, alright, thank you, yeah.") == frozenset()


def test_content_tokens_keeps_apostrophes_as_one_token():
    assert "rollin'" in asr.content_tokens("we're rollin' now")


# ── similarity ─────────────────────────────────────────────────────────────────

def test_similarity_identical_text_is_one():
    a = utt(10.0, "this here's a song about a hard rain")
    assert asr.utterance_similarity(a, utt(12.0, "this here's a song about a hard rain")) == 1.0


def test_similarity_ignores_disjoint_filler():
    a = utt(10.0, "alright, harmonica in the key of G")
    b = utt(10.0, "yeah well harmonica in the key of G")
    assert asr.utterance_similarity(a, b) == 1.0


def test_similarity_zero_without_shared_content():
    a = utt(10.0, "everybody sing along now")
    b = utt(10.0, "guitar solo coming up")
    assert asr.utterance_similarity(a, b) == 0.0


def test_similarity_empty_tokens_is_zero():
    assert asr.utterance_similarity(utt(0.0, "yeah well"), utt(0.0, "ok thanks")) == 0.0


# ── banter_score ───────────────────────────────────────────────────────────────

def test_none_when_a_side_has_too_few_utterances():
    """NULL means 'signal unavailable' and must never be reported as 0.0."""
    score, detail = asr.banter_score(
        [utt(0.0, "harmonica in the key of G")],
        [utt(3.0, "harmonica in the key of G"), utt(60.0, "thanks Boston crowd")],
        CFG,
    )
    assert score is None
    assert detail["n_a"] == 1 and detail["n_b"] == 2


def test_same_show_scores_on_consistent_offset():
    a = [utt(10.0, "harmonica in the key of G"),
         utt(120.0, "everybody in Boston tonight"),
         utt(300.0, "this song is about a hurricane")]
    b = [utt(13.0, "harmonica in the key of G"),
         utt(123.0, "everybody in Boston tonight"),
         utt(303.0, "this song is about a hurricane")]
    score, detail = asr.banter_score(a, b, CFG)
    assert score is not None and score > 0.0
    assert detail["n_matched"] == 3
    assert detail["offset_sec"] == pytest.approx(3.0, abs=0.01)


def test_scattered_offsets_do_not_corroborate():
    """Stock phrases at unrelated times: matched words, incoherent timeline."""
    a = [utt(10.0, "everybody in Boston tonight"),
         utt(400.0, "this song is about a hurricane"),
         utt(900.0, "harmonica in the key of G")]
    b = [utt(2000.0, "everybody in Boston tonight"),
         utt(500.0, "this song is about a hurricane"),
         utt(3300.0, "harmonica in the key of G")]
    score, detail = asr.banter_score(a, b, CFG)
    assert score == 0.0
    assert detail["n_matched"] == 1  # only the largest offset cluster survives


def test_single_match_is_noise_not_evidence():
    a = [utt(10.0, "this song is about a hurricane"), utt(500.0, "guitar tuning break")]
    b = [utt(12.0, "this song is about a hurricane"), utt(800.0, "wrong words entirely")]
    score, detail = asr.banter_score(a, b, CFG)
    assert score == 0.0
    assert detail["n_matched"] == 1


def test_repeated_catchphrase_counts_once_per_utterance():
    """One utterance may corroborate only once, however many partners it has."""
    a = [utt(10.0, "thank you Boston Massachusetts"), utt(20.0, "alright yeah well ok")]
    b = [utt(10.0, "thank you Boston Massachusetts"),
         utt(11.0, "thank you Boston Massachusetts"),
         utt(12.0, "thank you Boston Massachusetts")]
    score, detail = asr.banter_score(a, b, CFG)
    assert detail["n_matched"] == 1
    assert score == 0.0


def test_speed_ratio_rescues_a_stretched_clock():
    """A 2%-slow tape drifts far past the offset tolerance without the ratio."""
    a = [utt(100.0, "harmonica in the key of G"),
         utt(2000.0, "everybody in Boston tonight"),
         utt(4000.0, "this song is about a hurricane")]
    b = [utt(102.0, "harmonica in the key of G"),
         utt(2040.0, "everybody in Boston tonight"),
         utt(4080.0, "this song is about a hurricane")]
    assert asr.banter_score(a, b, CFG)[0] == 0.0
    score, detail = asr.banter_score(a, b, CFG, ratio=1.02)
    assert score > 0.0 and detail["n_matched"] == 3


def test_score_is_bounded_and_denominator_capped():
    """20 matched utterances must not score 5.0 — the score stays in [0, 1]."""
    a = [utt(i * 10.0, f"unique phrase number {i} spoken here") for i in range(20)]
    b = [utt(i * 10.0 + 4.0, f"unique phrase number {i} spoken here") for i in range(20)]
    score, detail = asr.banter_score(a, b, CFG)
    assert detail["n_matched"] == 20
    assert score == 1.0


# ── denominator: TODO-293 step 2 ───────────────────────────────────────────────
#
# The shipped scalar is 'witnesses' = sum(sim)/cap. These tests pin the two
# properties that demoted 'rate' = sum(sim)/min(n_a, n_b, cap), so a future
# session cannot quietly reinstate a yield-dependent denominator.

_SHARED = ["harmonica in the key of G", "everybody in Boston tonight",
           "this song is about a hurricane", "Tony Garnier playing bass guitar"]
_FILLER_A = ["spotlight swung toward stage left", "someone spilled beer nearby",
             "taper adjusted his microphone stand", "long pause before highway",
             "crowd chanted for another encore", "harmonica case fell over"]
_FILLER_B = ["unrelated chatter about parking lots", "muffled merchandise announcement",
             "loud whistle pierced my ears", "friend asked whether we leave",
             "rain started falling outside venue", "usher blocked the aisle"]


def _sides(n_utts: int, n_shared: int):
    """Two sides with *n_utts* utterances each, *n_shared* of them corroborating.

    Filler shares no content tokens across sides, so it never corroborates.
    """
    a = [utt(i * 100.0, t) for i, t in enumerate(_SHARED[:n_shared] + _FILLER_A[:n_utts - n_shared])]
    b = [utt(i * 100.0 + 3.0, t)
         for i, t in enumerate(_SHARED[:n_shared] + _FILLER_B[:n_utts - n_shared])]
    return a, b


@pytest.mark.parametrize("n_utts", [2, 3, 4, 6])
def test_witnesses_scalar_is_independent_of_yield(n_utts):
    """Fixed evidence (2 corroborations) must score the same at any yield.

    The denominator is built from tunable ASR knobs (max_gaps, model size, the
    confidence gates), so a yield-dependent scalar is not a stable property of
    the two recordings and cannot carry a threshold across a config change.
    """
    score, detail = asr.banter_score(*_sides(n_utts, 2), CFG)
    assert detail["n_matched"] == 2
    assert score == pytest.approx(2.0 / CFG["score_denominator_cap"])


def test_rate_scalar_still_penalises_yield():
    """Why 'rate' was demoted: same evidence, score collapses as yield rises."""
    cfg = {**CFG, "score_mode": "rate"}
    scores = [asr.banter_score(*_sides(n, 2), cfg)[0] for n in (2, 3, 4, 6)]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 1.0 and scores[-1] < 0.6


def test_witnesses_scalar_grows_with_corroboration_count():
    """4-of-4 is stronger evidence than 2-of-2 and must outrank it."""
    weak, _ = asr.banter_score(*_sides(4, 2), CFG)
    strong, _ = asr.banter_score(*_sides(4, 4), CFG)
    assert strong > weak


def test_both_scalars_are_always_reported():
    """One transcription pass must hand the calibration study both curves.

    They diverge only below the cap: ``rate``'s denominator is
    ``min(n_a, n_b, cap)``, so at a yield of 2 with cap 4 it reads 1.0 where
    ``witnesses`` reads 0.5. That thin-yield regime is precisely the observed
    one (2-9 gated utterances per source, matched a subset).
    """
    score, detail = asr.banter_score(*_sides(2, 2), CFG)
    assert detail["score_witnesses"] == pytest.approx(score)
    assert detail["score_witnesses"] == pytest.approx(0.5)
    assert detail["score_rate"] == pytest.approx(1.0)


def test_both_scalars_reported_as_zero_below_corroboration_floor():
    a = [utt(10.0, "this song is about a hurricane"), utt(500.0, "guitar tuning break")]
    b = [utt(12.0, "this song is about a hurricane"), utt(800.0, "wrong words entirely")]
    score, detail = asr.banter_score(a, b, CFG)
    assert score == 0.0
    assert detail["score_witnesses"] == 0.0 and detail["score_rate"] == 0.0


# ── gap finding ────────────────────────────────────────────────────────────────

def _synthetic_show(sr: int = 16000) -> np.ndarray:
    """120 s of 'music' with quiet 20 s breaks at 40 s and 90 s."""
    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 0.3, size=120 * sr).astype(np.float32)
    x[40 * sr:60 * sr] *= 0.01
    x[90 * sr:110 * sr] *= 0.01
    return x


NO_HEAD = dict(CFG, always_head_sec=0.0)


def test_find_banter_gaps_locates_the_quiet_breaks():
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, NO_HEAD)
    assert gaps, "expected the two engineered breaks to be found"
    assert any(g[0] <= 50.0 <= g[1] for g in gaps)
    assert any(g[0] <= 100.0 <= g[1] for g in gaps)


def test_find_banter_gaps_returns_sorted_disjoint_windows():
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, CFG)
    assert all(gaps[i][1] <= gaps[i + 1][0] for i in range(len(gaps) - 1))
    assert all(start < end for start, end in gaps)


def test_head_window_is_always_transcribed():
    """The announcer's intro must never be crowded out by louder-gap ranking."""
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, CFG)
    assert gaps[0][0] == 0.0


def test_head_window_survives_a_tight_budget():
    """The head is the shortest window, so a naive shortest-first dropper eats
    it — exactly the regression seen on 2003-05-11 (LB-01015) on 2026-07-30."""
    cfg = dict(CFG, always_head_sec=30.0, max_total_sec=60.0)
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, cfg)
    assert gaps and gaps[0][0] == 0.0
    assert len(gaps) > 1, "budget should still admit at least one real gap"


def test_selection_spreads_across_the_show_not_into_one_break():
    """One window per time bin: a 200 s tuning break must not eat the budget."""
    sr = 16000
    rng = np.random.default_rng(11)
    x = rng.normal(0.0, 0.3, size=600 * sr).astype(np.float32)
    x[50 * sr:250 * sr] *= 0.01     # one enormous early break
    x[400 * sr:420 * sr] *= 0.01    # one modest late break
    gaps = asr.find_banter_gaps(x, sr, dict(NO_HEAD, max_gaps=6))
    assert any(g[0] >= 350.0 for g in gaps), "late break must still be selected"


def test_find_banter_gaps_respects_the_total_budget():
    cfg = dict(CFG, max_total_sec=12.0, always_head_sec=0.0)
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, cfg)
    assert sum(end - start for start, end in gaps) <= 12.0


def test_budget_drops_whole_windows_rather_than_truncating():
    """A truncated window is a half-heard sentence — drop the shortest instead."""
    cfg = dict(CFG, max_total_sec=25.0, always_head_sec=0.0)
    gaps = asr.find_banter_gaps(_synthetic_show(), 16000, cfg)
    assert all(end - start >= cfg["gap_min_sec"] for start, end in gaps)


def test_find_banter_gaps_on_uniform_audio_is_safe():
    """Constant-energy input has no real breaks; must not crash or over-select."""
    x = np.full(60 * 16000, 0.2, dtype=np.float32)
    gaps = asr.find_banter_gaps(x, 16000, CFG)
    assert isinstance(gaps, list)


def test_find_banter_gaps_on_empty_audio_is_safe():
    assert asr.find_banter_gaps(np.zeros(0, dtype=np.float32), 16000, CFG) == []


# ── reference-clock window mapping ─────────────────────────────────────────────

def _segments(*specs):
    """Build fit_lag_segments-shaped dicts from (t_start, t_end, offset, ppm)."""
    return [{"t_start": a, "t_end": b, "offset_sec": o, "rate_ppm": p,
             "n_anchors": 3, "r2": 1.0} for a, b, o, p in specs]


def test_lag_at_without_a_model_is_identity():
    assert asr.lag_at(1234.0, []) == 0.0


def test_lag_at_applies_offset_and_rate():
    segs = _segments((0.0, 3600.0, 12.0, 1000.0))  # +12 s, +1000 ppm drift
    assert asr.lag_at(0.0, segs) == pytest.approx(12.0)
    assert asr.lag_at(3600.0, segs) == pytest.approx(12.0 + 3.6)


def test_lag_at_picks_the_segment_containing_the_time():
    segs = _segments((0.0, 1000.0, 5.0, 0.0), (1000.0, 2000.0, 42.0, 0.0))
    assert asr.lag_at(500.0, segs) == pytest.approx(5.0)
    assert asr.lag_at(1500.0, segs) == pytest.approx(42.0)


def test_lag_at_clamps_beyond_the_fitted_span():
    """Extrapolating a fitted rate off the end of the curve invents drift."""
    segs = _segments((0.0, 1000.0, 0.0, 10000.0))
    assert asr.lag_at(5000.0, segs) == pytest.approx(asr.lag_at(1000.0, segs))


def test_map_window_shifts_into_the_source_clock():
    segs = _segments((0.0, 3600.0, 30.0, 0.0))
    assert asr.map_window(100.0, 160.0, segs, 3600.0) == (130.0, 190.0)


def test_map_window_is_identity_for_the_reference():
    assert asr.map_window(100.0, 160.0, [], 3600.0) == (100.0, 160.0)


def test_map_window_returns_none_past_the_end_of_a_short_tape():
    """A tape missing the encore has no window there — NULL, not a bogus clip."""
    assert asr.map_window(5000.0, 5060.0, [], 4000.0) is None


def test_map_window_clamps_a_negative_start():
    segs = _segments((0.0, 3600.0, -20.0, 0.0))
    mapped = asr.map_window(0.0, 60.0, segs, 3600.0)
    assert mapped is not None and mapped[0] == 0.0


# ── transcription gating (stub model) ──────────────────────────────────────────

class _StubModel:
    """Stands in for WhisperModel; returns *segments* for every clip."""

    def __init__(self, segments):
        self._segments = segments
        self.calls: list[int] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(len(audio))
        return list(self._segments), SimpleNamespace(language="en")


def _seg(start, end, text, avg_logprob=-0.3, no_speech_prob=0.1):
    return SimpleNamespace(start=start, end=end, text=text,
                           avg_logprob=avg_logprob, no_speech_prob=no_speech_prob)


def test_transcribe_gaps_offsets_times_to_the_performance_clock():
    model = _StubModel([_seg(2.0, 4.0, "harmonica in the key of G")])
    x = np.zeros(200 * 16000, dtype=np.float32)
    utts = asr.transcribe_gaps(x, 16000, [(100.0, 130.0)], CFG, model=model)
    assert len(utts) == 1
    assert utts[0].t_start == pytest.approx(102.0)
    assert utts[0].t_end == pytest.approx(104.0)


def test_transcribe_gaps_drops_low_confidence_and_contentless_segments():
    model = _StubModel([
        _seg(1.0, 2.0, "clear stage banter about Boston"),
        _seg(3.0, 4.0, "hallucinated nonsense here", avg_logprob=-2.5),
        _seg(5.0, 6.0, "mostly speech free", no_speech_prob=0.95),
        _seg(7.0, 8.0, "yeah well"),  # no content tokens after stopwords
    ])
    x = np.zeros(60 * 16000, dtype=np.float32)
    utts = asr.transcribe_gaps(x, 16000, [(0.0, 30.0)], CFG, model=model)
    assert [u.text for u in utts] == ["clear stage banter about Boston"]


def test_transcribe_gaps_rejects_non_16k_audio():
    model = _StubModel([_seg(1.0, 2.0, "should never be reached")])
    x = np.zeros(60 * 44100, dtype=np.float32)
    assert asr.transcribe_gaps(x, 44100, [(0.0, 30.0)], CFG, model=model) == []
    assert model.calls == []


def test_transcribe_gaps_survives_a_failing_clip():
    class _Boom(_StubModel):
        def transcribe(self, audio, **kwargs):
            raise RuntimeError("ctranslate2 exploded")

    x = np.zeros(60 * 16000, dtype=np.float32)
    assert asr.transcribe_gaps(x, 16000, [(0.0, 30.0)], CFG, model=_Boom([])) == []


def test_missing_faster_whisper_yields_no_utterances(monkeypatch):
    """The optional dep being absent must degrade to NULL, never raise."""
    monkeypatch.setattr(asr, "load_model", lambda cfg: None)
    x = np.zeros(60 * 16000, dtype=np.float32)
    assert asr.transcribe_gaps(x, 16000, [(0.0, 30.0)], CFG) == []


def test_as_row_is_json_ready():
    row = utt(12.3456, "harmonica in the key of G").as_row()
    assert row["t_start"] == 12.346
    assert set(row) == {"t_start", "t_end", "text", "avg_logprob", "no_speech_prob"}
