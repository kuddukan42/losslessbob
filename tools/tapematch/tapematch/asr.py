"""Banter/ASR transcript matching — FABLE_TAPEMATCH_LISTENING_SIGNALS.md §3.

Every other TapeMatch signal (``corr``, ``fp_score``, ``env_corr``,
``emb_score``, ``flaw_match_score``) measures the *music*.  This one measures
the *words*: two recordings of the same performance captured the same stage
banter, the same shouted requests and the same applause-gap chatter, in the
same order, at the same relative times.  That evidence survives EQ, generation
loss and awful transfers — i.e. it is strongest exactly where waveform
similarity is weakest.

Pipeline
--------
1. :func:`find_banter_gaps` — low-energy regions of the trimmed performance
   (between-song applause/chatter), from :func:`match.find_quiet_segments`,
   padded, merged and budget-capped.
2. :func:`transcribe_gaps` — faster-whisper over those regions only (never the
   full show), greedy + temperature 0 for determinism, with a confidence gate
   on ``avg_logprob`` / ``no_speech_prob`` because ASR on rough AUD tape
   hallucinates confidently.
3. :func:`banter_score` — fuzzy token overlap between the two sides' utterances
   **plus** timeline self-consistency: the matched utterances must agree on a
   single time offset.  Two tapes of one show share both the words and their
   spacing; two different shows of the same tour share stock phrases at
   unrelated times, which the offset cluster rejects.

Dark-launch contract (spec §0): the score is computed, logged and persisted,
but no ``addon_links`` rule reads it until a distribution study assigns a
threshold.  ``None`` means "signal unavailable for this pair" and must never
be coerced to ``0.0`` — 0.0 means "computed, no corroborating banter found".

faster-whisper is an optional, feature-gated dependency: it is imported lazily
inside :func:`load_model`, and every failure path degrades to ``None``.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field

import numpy as np

from . import match
from .audio import to_mono

logger = logging.getLogger(__name__)

# Filler and function words carry no identifying information — "the", "you know"
# and "alright" match between any two Dylan shows ever recorded. Dropping them
# before scoring is what makes token overlap discriminative rather than a
# measure of how much English both transcripts contain.
_STOPWORDS = frozenset("""
a about all alright am an and any are as at be been but by can cant could did
do does dont for from get go going gonna got gotta had has have he her here hes
him his how huh i id if ill im in is isnt it its just know let like me much my
no not now of oh off ok okay on one or our out really right said say see she so
some thank thanks that thats the their them then there these they this to too
uh um up us very wanna was we well were what when where which who will with
would yeah yes you your youre
""".split())

_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class Utterance:
    """One confidence-gated ASR segment, timed on the trimmed performance clock.

    Attributes:
        t_start: Segment start, seconds from the start of the *trimmed*
            performance (not the raw file) — the same clock every other
            per-source metric uses.
        t_end: Segment end, same clock.
        text: Raw transcript text, whitespace-stripped.
        avg_logprob: Whisper's mean token log-probability for the segment.
        no_speech_prob: Whisper's probability that the segment is not speech.
        tokens: Content tokens after stopword removal, used for scoring.
    """

    t_start: float
    t_end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    tokens: frozenset[str] = field(default_factory=frozenset)

    def as_row(self) -> dict:
        """Return a JSON/DB-friendly dict (used for the ``transcripts`` table)."""
        return {
            "t_start": round(self.t_start, 3),
            "t_end": round(self.t_end, 3),
            "text": self.text,
            "avg_logprob": round(self.avg_logprob, 4),
            "no_speech_prob": round(self.no_speech_prob, 4),
        }


def content_tokens(text: str) -> frozenset[str]:
    """Return the identifying (non-stopword) tokens of *text*.

    Lowercases, strips punctuation, drops stopwords and 1-character tokens.

    Args:
        text: Raw transcript text.

    Returns:
        Frozenset of content tokens; may be empty.
    """
    words = _WORD_RE.findall(text.lower())
    return frozenset(w for w in words if len(w) > 1 and w not in _STOPWORDS)


def make_utterance(t_start: float, t_end: float, text: str,
                   avg_logprob: float, no_speech_prob: float) -> Utterance:
    """Build an :class:`Utterance` with its content tokens precomputed.

    Args:
        t_start: Segment start in trimmed-performance seconds.
        t_end: Segment end in trimmed-performance seconds.
        text: Raw transcript text.
        avg_logprob: Whisper mean token log-probability.
        no_speech_prob: Whisper no-speech probability.

    Returns:
        The populated Utterance.
    """
    clean = " ".join(text.split())
    return Utterance(
        t_start=float(t_start),
        t_end=float(t_end),
        text=clean,
        avg_logprob=float(avg_logprob),
        no_speech_prob=float(no_speech_prob),
        tokens=content_tokens(clean),
    )


# ── 1. gap finding ─────────────────────────────────────────────────────────────

def find_banter_gaps(mono: np.ndarray, sr: int, cfg: dict) -> list[tuple[float, float]]:
    """Return (start_sec, end_sec) regions likely to contain spoken banter.

    Between-song regions are the low-energy parts of the performance envelope:
    applause decays, tuning, and whatever the artist says over it.  Quiet
    seconds come from :func:`match.find_quiet_segments`, padded either side
    (banter routinely starts while the applause is still loud), merged where
    the padding overlaps, and budget-capped so ASR cost stays bounded on a
    3-hour show.

    **Selection is on an even time grid, not by gap length**, and that choice is
    the whole ballgame for a *pair* signal: the two sides only corroborate each
    other if they transcribe the same parts of the show, and "longest quiet
    stretch first" ranks differently on two tapes of one performance (measured
    2026-07-30 — one side transcribed the show intro, the other spent its whole
    budget elsewhere and scored nothing). One window per time bin converges
    because both tapes share a performance structure; ranking by an
    audio-dependent statistic does not.

    The head window is always included: the announcer's intro ("Columbia
    recording artist Bob Dylan") is the single most identifying utterance a
    Dylan tape carries, and it sits in the pre-first-song applause where the
    energy gate is least reliable.

    Args:
        mono: Trimmed mono performance samples (memmap-friendly; read in blocks).
        sr: Sample rate of *mono*.
        cfg: The ``asr`` config block.

    Returns:
        Non-overlapping (start_sec, end_sec) windows, in time order.
    """
    pct = float(cfg.get("gap_energy_percentile", 25.0))
    min_gap = float(cfg.get("gap_min_sec", 4.0))
    pad = float(cfg.get("gap_pad_sec", 30.0))
    max_win = float(cfg.get("gap_max_window_sec", 75.0))
    max_gaps = int(cfg.get("max_gaps", 40))
    total_budget = float(cfg.get("max_total_sec", 1800.0))
    head_sec = float(cfg.get("always_head_sec", 60.0))

    dur_total = len(mono) / float(sr)
    if dur_total <= 0:
        return []

    windows: list[tuple[float, float]] = []
    head_end = 0.0
    if head_sec > 0:
        head_end = min(head_sec, dur_total)
        windows.append((0.0, head_end))

    segments = match.find_quiet_segments(mono, sr, pct, min_gap)
    if segments and max_gaps > 0:
        # One window per equal-width time bin: the longest quiet stretch inside
        # it. Spread beats depth — 20 gaps across the show corroborate better
        # than 20 gaps inside one long tuning break.
        bin_width = dur_total / max_gaps
        best_per_bin: dict[int, tuple[float, float]] = {}
        for center, dur in segments:
            b = min(int(center / bin_width), max_gaps - 1)
            if b not in best_per_bin or dur > best_per_bin[b][1]:
                best_per_bin[b] = (center, dur)
        for center, dur in best_per_bin.values():
            half = min(dur / 2.0 + pad, max_win / 2.0)
            windows.append((max(0.0, center - half), min(dur_total, center + half)))

    windows.sort()
    merged: list[list[float]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    merged = [w for w in merged if w[1] - w[0] >= min_gap]

    # Over budget: drop whole windows, shortest first, rather than truncating —
    # a truncated window is a half-heard sentence. The head window is exempt: it
    # is short by construction (always_head_sec, no gap padding) and would be the
    # dropper's first victim every time, which is the opposite of its priority.
    total = sum(end - start for start, end in merged)
    if total > total_budget:
        protected = {i for i, w in enumerate(merged) if head_end > 0 and w[0] <= 0.0}
        order = sorted((i for i in range(len(merged)) if i not in protected),
                       key=lambda i: merged[i][1] - merged[i][0])
        drop: set[int] = set()
        for i in order:
            if total <= total_budget:
                break
            drop.add(i)
            total -= merged[i][1] - merged[i][0]
        merged = [w for i, w in enumerate(merged) if i not in drop]

    return [(round(start, 3), round(end, 3)) for start, end in merged]


def lag_at(t_ref: float, lag_segments: list[dict]) -> float:
    """Return the lag (seconds) mapping reference time *t_ref* into a source.

    Evaluates the piecewise-linear model from :func:`align.fit_lag_segments`,
    following the pipeline's convention ``t_source = t_ref + lag``. Times
    outside the fitted span clamp to the nearest segment rather than
    extrapolating a fitted rate off the end of the curve.

    Args:
        t_ref: Time on the reference source's trimmed-performance clock.
        lag_segments: ``fit_lag_segments`` output; empty for the reference
            itself or a source with too few valid anchors.

    Returns:
        Lag in seconds; 0.0 when no model is available.
    """
    if not lag_segments:
        return 0.0
    seg = lag_segments[0]
    for candidate in lag_segments:
        if t_ref >= candidate["t_start"]:
            seg = candidate
        else:
            break
    t = min(max(t_ref, seg["t_start"]), seg["t_end"]) if seg["t_end"] > seg["t_start"] else t_ref
    return float(seg["offset_sec"] + seg["rate_ppm"] / 1e6 * t)


def map_window(start: float, end: float, lag_segments: list[dict],
               duration: float) -> tuple[float, float] | None:
    """Map a reference-clock window onto one source's own clock.

    Args:
        start: Window start on the reference clock.
        end: Window end on the reference clock.
        lag_segments: This source's ``fit_lag_segments`` model (empty = identity).
        duration: This source's trimmed performance duration, for clamping.

    Returns:
        The mapped ``(start, end)``, or ``None`` when the window falls outside
        this source's performance (e.g. a tape missing the encore).
    """
    s = start + lag_at(start, lag_segments)
    e = end + lag_at(end, lag_segments)
    s, e = max(0.0, s), min(duration, e)
    if e - s <= 0.0:
        return None
    return (round(s, 3), round(e, 3))


# ── 2. transcription ───────────────────────────────────────────────────────────

_MODEL_CACHE: dict[tuple, object] = {}
_MODEL_LOCK = threading.Lock()


def load_model(cfg: dict):
    """Load (and process-cache) the faster-whisper model described by *cfg*.

    The model is cached per (name, revision, device, compute_type) because a
    session transcribes every source in turn and reloading CTranslate2 weights
    per source would dominate the runtime.

    Args:
        cfg: The ``asr`` config block. Honours ``model``, ``model_revision``,
            ``device``, ``compute_type``, ``cpu_threads``, ``download_root``,
            ``local_files_only``.

    Returns:
        A ``faster_whisper.WhisperModel``, or ``None`` if faster-whisper is not
        installed or the model could not be loaded (signal simply goes NULL).
    """
    key = (
        cfg.get("model", "base"),
        cfg.get("model_revision"),
        cfg.get("device", "cpu"),
        cfg.get("compute_type", "int8"),
    )
    with _MODEL_LOCK:
        if key in _MODEL_CACHE:
            return _MODEL_CACHE[key]
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415 (optional dep)
        except Exception as exc:  # noqa: BLE001 — optional dep, any failure = NULL
            logger.warning("asr: faster-whisper unavailable (%s); banter_score NULL", exc)
            _MODEL_CACHE[key] = None
            return None
        try:
            model = WhisperModel(
                key[0],
                device=key[2],
                compute_type=key[3],
                cpu_threads=int(cfg.get("cpu_threads", 0)),
                download_root=cfg.get("download_root") or None,
                local_files_only=bool(cfg.get("local_files_only", False)),
                revision=key[1] or None,
            )
        except Exception as exc:  # noqa: BLE001 — bad model id, no network, ...
            logger.warning("asr: model load failed (%s); banter_score NULL", exc)
            model = None
        _MODEL_CACHE[key] = model
        return model


def transcribe_gaps(mono: np.ndarray, sr: int, gaps: list[tuple[float, float]],
                    cfg: dict, model=None) -> list[Utterance]:
    """Transcribe *gaps* of *mono* and return confidence-gated utterances.

    Decoding is greedy at temperature 0 with ``condition_on_previous_text``
    off: reproducibility matters more than fluency here, and cross-segment
    conditioning is precisely what makes Whisper invent continuations of
    hallucinated text.

    Args:
        mono: Trimmed mono performance samples at *sr*.
        sr: Sample rate; must be 16000 (Whisper's native rate) — other rates
            are rejected rather than silently mis-timed.
        gaps: (start_sec, end_sec) windows from :func:`find_banter_gaps`.
        cfg: The ``asr`` config block.
        model: Preloaded model; loaded via :func:`load_model` when omitted.

    Returns:
        Utterances on the trimmed-performance clock, in time order. Empty when
        the model is unavailable or nothing cleared the confidence gate.
    """
    if not gaps:
        return []
    if sr != 16000:
        logger.warning("asr: sample rate %d != 16000; skipping transcription", sr)
        return []
    model = model if model is not None else load_model(cfg)
    if model is None:
        return []

    min_logprob = float(cfg.get("min_avg_logprob", -1.0))
    max_no_speech = float(cfg.get("max_no_speech_prob", 0.6))
    min_tokens = int(cfg.get("min_content_tokens", 2))
    language = cfg.get("language", "en") or None

    utterances: list[Utterance] = []
    for start, end in gaps:
        i0, i1 = int(start * sr), min(int(end * sr), len(mono))
        if i1 - i0 < sr:
            continue
        # to_mono, not a bare reshape: a caller handing us a (n, ch) stream
        # would otherwise interleave the channels into nonsense that Whisper
        # transcribes without complaint.
        clip = to_mono(np.asarray(mono[i0:i1], dtype=np.float32))
        try:
            segments, _info = model.transcribe(
                clip,
                language=language,
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=bool(cfg.get("vad_filter", True)),
                word_timestamps=False,
            )
            for seg in segments:
                utt = make_utterance(
                    start + seg.start, start + seg.end, seg.text,
                    seg.avg_logprob, seg.no_speech_prob,
                )
                if utt.avg_logprob < min_logprob or utt.no_speech_prob > max_no_speech:
                    continue
                if len(utt.tokens) < min_tokens:
                    continue
                utterances.append(utt)
        except Exception as exc:  # noqa: BLE001 — one bad clip must not kill the run
            logger.warning("asr: transcription failed for gap %.1f-%.1f (%s)",
                           start, end, exc)
            continue

    utterances.sort(key=lambda u: u.t_start)
    return utterances


# ── 3. pair scoring ────────────────────────────────────────────────────────────

def utterance_similarity(a: Utterance, b: Utterance) -> float:
    """Return the Dice coefficient of two utterances' content tokens.

    Dice rather than Jaccard because the two sides' ASR output routinely
    differs in length (one tape catches a trailing word the other misses), and
    Dice penalises that asymmetry less.

    Args:
        a: First utterance.
        b: Second utterance.

    Returns:
        Similarity in [0, 1]; 0.0 when either side has no content tokens.
    """
    if not a.tokens or not b.tokens:
        return 0.0
    shared = len(a.tokens & b.tokens)
    if not shared:
        return 0.0
    return 2.0 * shared / (len(a.tokens) + len(b.tokens))


def banter_score(utts_a: list[Utterance], utts_b: list[Utterance], cfg: dict,
                 ratio: float = 1.0) -> tuple[float | None, dict]:
    """Score two sources' banter transcripts for same-performance evidence.

    Two independent conditions must hold, which is what separates this from a
    text-similarity toy:

    1. **Words** — utterances pair up above ``min_similarity`` token overlap.
    2. **Timeline** — the paired utterances agree on a *single* time offset
       (``t_b - ratio * t_a``) within ``offset_tolerance_sec``. Same show ⇒ one
       constant offset for every match; different shows with stock phrases
       ("thank you very much") scatter, and the offset cluster discards them.

    ``ratio`` lets the caller pass the pair's known speed ratio so a 1 %-slow
    tape's linearly stretched timestamps still cluster.

    **Denominator (TODO-293 step 2, decided 2026-08-07).** Two scalars are
    computed from the same matches and ``score_mode`` selects which one is
    returned:

    * ``witnesses`` (default) — ``sum(sim) / score_denominator_cap``. A count
      of corroborating witnesses, saturating at the cap.
    * ``rate`` — ``sum(sim) / min(n_a, n_b, cap)``, the original scalar, kept
      so the calibration study can compare both from one transcription pass.

    ``rate`` was demoted because its denominator is built from *tunable ASR
    knobs* (``max_gaps``, ``max_total_sec``, model size, the confidence
    gates), so it is not a stable property of the two recordings: holding the
    real evidence fixed at 2 corroborating utterances, it falls 1.000 → 0.250
    as per-source yield rises 2 → 8. Since raising yield is TODO-293's stated
    next move, every planned improvement would have depressed the score on
    true pairs and invalidated any threshold set beforehand. ``rate`` is also
    evidence-blind: 2-of-2 and 8-of-8 both score 1.000.

    Args:
        utts_a: Side A utterances (trimmed-performance clock).
        utts_b: Side B utterances (same clock).
        cfg: The ``asr`` config block.
        ratio: Speed ratio mapping A's clock onto B's (1.0 = no correction).

    Returns:
        ``(score, detail)``. *score* is ``None`` when the signal is
        unavailable — either side had fewer than ``min_utterances`` usable
        utterances — and a float in [0, 1] otherwise, where 0.0 means
        "computed, no corroborated banter". *detail* carries the diagnostic
        fields (``n_a``, ``n_b``, ``n_matched``, ``offset_sec``) plus both
        candidate scalars (``score_witnesses``, ``score_rate``) for the run
        JSON and the calibration study.
    """
    min_utts = int(cfg.get("min_utterances", 2))
    t_sim = float(cfg.get("min_similarity", 0.5))
    tol = float(cfg.get("offset_tolerance_sec", 5.0))
    min_corrob = int(cfg.get("min_corroborating", 2))
    denom_cap = int(cfg.get("score_denominator_cap", 4))
    mode = str(cfg.get("score_mode", "witnesses"))

    detail: dict = {"n_a": len(utts_a), "n_b": len(utts_b),
                    "n_matched": 0, "offset_sec": None,
                    "score_witnesses": None, "score_rate": None}
    if len(utts_a) < min_utts or len(utts_b) < min_utts:
        return None, detail

    # Candidate matches: every above-threshold cross pair, with the time offset
    # it implies. One utterance may appear in several candidates; the offset
    # cluster below is what resolves the ambiguity.
    candidates: list[tuple[float, float, int, int]] = []
    for ia, ua in enumerate(utts_a):
        for ib, ub in enumerate(utts_b):
            sim = utterance_similarity(ua, ub)
            if sim >= t_sim:
                candidates.append((ub.t_start - ratio * ua.t_start, sim, ia, ib))
    if not candidates:
        detail["score_witnesses"] = detail["score_rate"] = 0.0
        return 0.0, detail

    # Largest set of candidates sharing one offset (within tol). O(n^2) over
    # candidates, which is tiny — utterance counts are in the tens.
    best: list[tuple[float, float, int, int]] = []
    for pivot, _sim, _ia, _ib in candidates:
        group = [c for c in candidates if abs(c[0] - pivot) <= tol]
        if len(group) > len(best):
            best = group
    # Each utterance may corroborate only once, keeping its best-scoring match:
    # one repeated catchphrase must not count as several independent witnesses.
    used_a: dict[int, tuple[float, float, int, int]] = {}
    used_b: set[int] = set()
    for cand in sorted(best, key=lambda c: -c[1]):
        _off, _sim, ia, ib = cand
        if ia in used_a or ib in used_b:
            continue
        used_a[ia] = cand
        used_b.add(ib)
    matches = list(used_a.values())

    detail["n_matched"] = len(matches)
    if matches:
        detail["offset_sec"] = round(float(np.median([m[0] for m in matches])), 3)
    if len(matches) < min_corrob:
        # Single-utterance agreement is noise (spec §3): report no evidence
        # rather than a small positive score.
        detail["score_witnesses"] = detail["score_rate"] = 0.0
        return 0.0, detail

    sim_sum = sum(m[1] for m in matches)
    # Both scalars are always computed, because the expensive step is the
    # transcription, not the arithmetic: one ASR pass hands the TODO-293
    # calibration study both distributions over the identical match set.
    witnesses = min(1.0, sim_sum / float(denom_cap))
    rate = min(1.0, sim_sum / float(min(len(utts_a), len(utts_b), denom_cap)))
    detail["score_witnesses"] = round(witnesses, 4)
    detail["score_rate"] = round(rate, 4)
    return float(rate if mode == "rate" else witnesses), detail


def transcribe_source(mono: np.ndarray, sr: int, cfg: dict,
                      model=None) -> list[Utterance]:
    """Find banter gaps in one source and transcribe them.

    Convenience wrapper over :func:`find_banter_gaps` + :func:`transcribe_gaps`
    for the per-source loop in ``cli.py``.

    Args:
        mono: Trimmed mono performance samples.
        sr: Sample rate (must be 16000).
        cfg: The ``asr`` config block.
        model: Preloaded model, shared across sources in a session.

    Returns:
        Confidence-gated utterances in time order.
    """
    gaps = find_banter_gaps(mono, sr, cfg)
    if not gaps:
        return []
    return transcribe_gaps(mono, sr, gaps, cfg, model=model)
