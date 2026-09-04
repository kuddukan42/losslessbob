"""calibration.py — a stable identity for the verdict-relevant part of a config.

TODO-333: ``recording_families`` in the app DB does not represent one
algorithm's opinion. It represents whatever the pipeline believed on the day
each date happened to be run, and nothing in the schema records which. The
``runs.config_json`` blob cannot answer the question either, because it splits
runs that are behaviourally identical: over the 3,062 latest runs it hashes to
more than ten distinct values, but only nine keys ever changed VALUE — every
other difference is a key that simply did not exist yet in an older config.

This module defines the *calibration identity*: the subset of a config that can
change a clustering verdict, normalised so that behaviourally identical configs
hash the same. Three normalisations do the collapsing:

1. **Absent means default.** A key added to config.yaml later, at the value the
   code already used, does not start a new era. Every decision key therefore
   declares its code default here (:data:`DECISION_KEYS`); the default must
   match the fallback the consuming module passes to ``.get()``.
2. **A disabled block contributes only its off switch.** ``addon_links.rule_a``
   at ``t_flaw`` 0.45 and 0.60 are the same calibration while the rule is
   disabled — the threshold cannot reach a verdict. When ``enabled`` is false
   the block collapses to ``{"enabled": False}``.
3. **Non-decision keys are dropped.** Model paths, thread counts, download
   roots and other environment knobs change nothing about a verdict.

The hash is deliberately NOT a promise that two runs sharing it produced
comparable numbers — a code change with no config change is invisible to it.
It answers one question only: which configuration was this verdict computed
under. Pair it with ``runs.run_at`` when code provenance matters.

Usage:
    from tapematch.calibration import calibration_hash, calibration_view
    h = calibration_hash(cfg)          # 12 hex chars
    view = calibration_view(cfg)       # the normalised subset that was hashed
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

# Every config key that can change a clustering verdict, as a dotted path with
# the default the code applies when the key is absent. Grouped by the block
# they live in; a block listed in GATED_BLOCKS collapses when its gate is off.
#
# Two kinds of key qualify: thresholds the verdict predicate reads directly
# (tapematch/verdict.py), and signal-generation parameters that change the
# METRIC VALUES that predicate compares — a different fingerprint band or
# anchor count produces different numbers against the same thresholds, so it is
# as much a calibration change as moving a threshold.
DECISION_KEYS: dict[str, Any] = {
    # -- signal generation, always active ------------------------------------
    "audio.analysis_sr": 16000,
    "audio.mono_mix": False,
    "ingest.audio_exts": [".flac", ".wav", ".aiff", ".aif", ".shn", ".m4a", ".mp3", ".ape"],
    "trim.frame_sec": 1.0,
    "trim.hop_sec": 0.5,
    "trim.flatness_music_max": 0.45,
    "trim.min_sustain_sec": 8.0,
    "trim.pad_keep_sec": 5.0,
    "trim.min_dynamic_range_db": 10.0,
    "anchors.n_anchors": 12,
    "anchors.window_sec": 45.0,
    "anchors.onset_percentile": 99.0,
    "anchors.prefer_quiet": True,
    "align.max_lag_sec": 90.0,
    "align.ratio_flag_ppm": 200,
    "align.ratio_confidence_min": 6.0,
    "align.pyin_fallback": True,
    "align.step_flag_sec": 0.5,
    "lineage.hf_ceiling_probe_hz": [14000, 16000, 19000, 20000],
    "lineage.dropout_z": 6.0,
    # -- primary correlation and its clustering bar --------------------------
    "match.ratio_search_min": 0.97,
    "match.ratio_search_max": 1.03,
    "match.ratio_search_steps": 121,
    "match.cluster_threshold": 0.45,
    # TODO-325's two corroboration floors. Dark in the shipped config; absent
    # means "no floor", which is the historical behaviour.
    "match.secondary_primary_floor": None,
    "match.fingerprint_primary_floor": None,
    # -- secondary match (windowed coverage + quiet-segment hiss) ------------
    "secondary_match.window_sec": 60.0,
    "secondary_match.hop_sec": 30.0,
    "secondary_match.local_lag_sec": 10.0,
    "secondary_match.window_corr_threshold": 0.30,
    "secondary_match.coverage_threshold": 0.35,
    "secondary_match.high_ppm_threshold": 5000,
    "secondary_match.quiet_energy_percentile": 25,
    "secondary_match.min_quiet_sec": 3.0,
    "secondary_match.hiss_lag_sec": 3.0,
    "secondary_match.hiss_corr_threshold": 0.20,
    "secondary_match.hiss_frac_threshold": 0.40,
    "secondary_match.hiss_merge_frac": 0.60,
    "secondary_match.hiss_merge_median": 0.65,
    "secondary_match.hiss_merge_median_lofi": 0.40,
    "secondary_match.hiss_lofi_ceiling_hz": 12000,
    "secondary_match.short_window_sec": 15.0,
    "secondary_match.short_hop_sec": 5.0,
    "secondary_match.staircase_window_sec": 5.0,
    "secondary_match.staircase_hop_sec": 2.0,
    "secondary_match.staircase_window_corr_threshold": None,
    "secondary_match.staircase_coverage_threshold": None,
    # -- fingerprint ---------------------------------------------------------
    "fingerprint.window_start_sec": 180.0,
    "fingerprint.window_dur_sec": 600.0,
    "fingerprint.nperseg": 1024,
    "fingerprint.hop": 512,
    "fingerprint.peak_neighborhood_t": 5,
    "fingerprint.peak_neighborhood_f": 3,
    "fingerprint.fanout": 5,
    "fingerprint.dt_bins": 100,
    "fingerprint.hf_band_hz": None,
    "fingerprint.match_threshold": 0.60,
    "fingerprint.cluster_threshold": 0.50,
    "fingerprint.cluster_threshold_staircase": None,
    "fingerprint.cluster_threshold_curator": None,
    # TODO-234/235 mitigation (b): "source" (either side staircase-flagged) or
    # "pair" (both). Absent in the shipped config; the code default is "source".
    "fingerprint.staircase_scope": "source",
    "fingerprint.staircase_corroboration.enabled": False,
    "fingerprint.staircase_corroboration.min_windowed_frac": None,
    "fingerprint.staircase_corroboration.min_hiss_frac": None,
    "fingerprint.staircase_corroboration.min_hiss_median": None,
    "fingerprint.triplet.enabled": False,
    "fingerprint.triplet.tmin_sec": 0.5,
    "fingerprint.triplet.tmax_sec": 8.0,
    "fingerprint.triplet.fanout": 4,
    "fingerprint.triplet.cluster_threshold": None,
    # -- optional signals, each gated ----------------------------------------
    "refine.enabled": True,
    "refine.max_iter": 2,
    "refine.stop_ppm": 5.0,
    "refine.trigger_min_ppm": 2000,
    "refine.trigger_corr_ceiling": 0.6,
    "polarity.enabled": False,
    "polarity.rescue_corr_ceiling": 0.6,
    "flaw_fingerprint.enabled": False,
    "flaw_fingerprint.quiet_energy_percentile": 25,
    "flaw_fingerprint.min_quiet_sec": 3.0,
    "flaw_fingerprint.dropout_frame_sec": 0.02,
    "flaw_fingerprint.dropout_local_window_sec": 2.0,
    "flaw_fingerprint.dropout_depth_db": 20.0,
    "flaw_fingerprint.dropout_min_sec": 0.04,
    "flaw_fingerprint.dropout_max_sec": 0.8,
    "flaw_fingerprint.click_local_window_ms": 50.0,
    "flaw_fingerprint.click_sigma": 6.0,
    "flaw_fingerprint.click_max_dur_ms": 5.0,
    "flaw_fingerprint.click_cap": 200,
    "flaw_fingerprint.cut_frame_sec": 0.1,
    "flaw_fingerprint.cut_sigma": 4.0,
    "flaw_fingerprint.flaw_min_events": 5,
    "flaw_fingerprint.tol_sec": 0.5,
    "spectral_stationarity.enabled": False,
    "spectral_stationarity.window_sec": 60.0,
    "spectral_stationarity.hop_sec": 30.0,
    "spectral_stationarity.local_lag_sec": 10.0,
    "spectral_stationarity.n_mels": 32,
    "spectral_stationarity.stft_nperseg": 1024,
    "spectral_stationarity.stft_hop": 256,
    "spectral_stationarity.min_frames_per_window": 20,
    "spectral_stationarity.noise_floor_margin_db": 6.0,
    "spectral_stationarity.stationarity_norm_db": 6.0,
    "spectral_stationarity.stationarity_min_windows": 6,
    "envelope_corr.enabled": False,
    "envelope_corr.band_lo_hz": 200.0,
    "envelope_corr.band_hi_cap_hz": 2000.0,
    "envelope_corr.filter_order": 6,
    "envelope_corr.frame_rate_hz": 20.0,
    "envelope_corr.min_overlap_min": 10.0,
    # -- evidence-combination rules ------------------------------------------
    "addon_links.rule_a.enabled": False,
    "addon_links.rule_a.t_flaw": None,
    "addon_links.rule_a.min_events": None,
    "addon_links.rule_b.enabled": False,
    "addon_links.rule_b.t_stat": None,
    "addon_links.rule_b.t_env": None,
    "addon_links.rule_c.enabled": False,
    "addon_links.rule_c.t_emb": None,
    "addon_links.rule_c.t_flaw_weak": None,
    "addon_links.rule_c.t_stat": None,
    "addon_links.rule_d.enabled": False,
    "addon_links.rule_d.t_emb": None,
    "addon_links.rule_d.live_embed": False,
    # -- ASR / banter (section 3, dark) --------------------------------------
    "asr.enabled": False,
    "asr.model": "base",
    "asr.language": "en",
    "asr.gap_energy_percentile": 25.0,
    "asr.gap_min_sec": 4.0,
    "asr.gap_pad_sec": 30.0,
    "asr.gap_max_window_sec": 75.0,
    "asr.max_gaps": 60,
    "asr.always_head_sec": 60.0,
    "asr.max_total_sec": 2400.0,
    "asr.vad_filter": True,
    "asr.min_avg_logprob": -1.0,
    "asr.max_no_speech_prob": 0.8,
    "asr.min_content_tokens": 2,
    "asr.min_utterances": 2,
    "asr.min_similarity": 0.5,
    "asr.offset_tolerance_sec": 5.0,
    "asr.min_corroborating": 2,
    "asr.score_mode": "witnesses",
    "asr.score_denominator_cap": 4,
}

# Blocks that collapse to their off switch alone when the gate key is falsey.
# Maps block prefix -> gate key within that block.
GATED_BLOCKS: dict[str, str] = {
    "refine": "enabled",
    "polarity": "enabled",
    "flaw_fingerprint": "enabled",
    "spectral_stationarity": "enabled",
    "envelope_corr": "enabled",
    "fingerprint.staircase_corroboration": "enabled",
    "fingerprint.triplet": "enabled",
    "addon_links.rule_a": "enabled",
    "addon_links.rule_b": "enabled",
    "addon_links.rule_c": "enabled",
    "addon_links.rule_d": "enabled",
    "asr": "enabled",
}

# Keys present in config.yaml that deliberately carry no calibration identity:
# they select hardware, paths or model artefacts, not decisions. Listed so the
# drift test can require every config key to be classified one way or the other.
NON_DECISION_KEYS: frozenset[str] = frozenset({
    "asr.model_revision",
    "asr.device",
    "asr.compute_type",
    "asr.cpu_threads",
    "asr.download_root",
    "asr.local_files_only",
})


# The subset of DECISION_KEYS that tapematch/verdict.py reads directly, i.e.
# thresholds applied to already-computed pair metrics. A config difference
# confined to these keys can be REPLAYED against stored pair rows — the metrics
# do not change, only the bars applied to them. A difference touching any other
# decision key changes the metric values themselves and can only be resolved by
# re-running the audio.
VERDICT_ONLY_KEYS: frozenset[str] = frozenset({
    "match.cluster_threshold",
    "match.secondary_primary_floor",
    "match.fingerprint_primary_floor",
    "secondary_match.coverage_threshold",
    "secondary_match.hiss_merge_frac",
    "secondary_match.hiss_merge_median",
    "secondary_match.hiss_merge_median_lofi",
    "secondary_match.hiss_lofi_ceiling_hz",
    "fingerprint.cluster_threshold",
    "fingerprint.cluster_threshold_staircase",
    "fingerprint.cluster_threshold_curator",
    "fingerprint.staircase_scope",
    "fingerprint.staircase_corroboration.enabled",
    "fingerprint.staircase_corroboration.min_windowed_frac",
    "fingerprint.staircase_corroboration.min_hiss_frac",
    "fingerprint.staircase_corroboration.min_hiss_median",
    "fingerprint.triplet.enabled",
    "fingerprint.triplet.cluster_threshold",
    "addon_links.rule_a.enabled",
    "addon_links.rule_a.t_flaw",
    "addon_links.rule_a.min_events",
    "addon_links.rule_b.enabled",
    "addon_links.rule_b.t_stat",
    "addon_links.rule_b.t_env",
    "addon_links.rule_c.enabled",
    "addon_links.rule_c.t_emb",
    "addon_links.rule_c.t_flaw_weak",
    "addon_links.rule_c.t_stat",
    "addon_links.rule_d.enabled",
    "addon_links.rule_d.t_emb",
})


def _get(cfg: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """Look up a dotted path; return ``(present, value)``."""
    cur: Any = cfg
    for part in path.split("."):
        if not isinstance(cur, Mapping) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _gate_off(cfg: Mapping[str, Any], block: str) -> bool:
    """Whether a gated block's switch is off (absent counts as off)."""
    present, value = _get(cfg, f"{block}.{GATED_BLOCKS[block]}")
    return not (present and value)


def calibration_view(cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Normalise a config down to the values that can change a verdict.

    Args:
        cfg: A loaded config.yaml, or a stored ``runs.config_json`` blob parsed
            back into a dict. May be partial — absent keys take their default.

    Returns:
        A flat ``{dotted_key: value}`` dict, sorted by key, holding one entry
        per decision key that is live under this config. A gated block whose
        switch is off contributes only its gate key.
    """
    off = {block for block in GATED_BLOCKS if _gate_off(cfg, block)}
    view: dict[str, Any] = {}
    for path, default in DECISION_KEYS.items():
        block = next((b for b in off if path.startswith(b + ".")), None)
        if block is not None and path != f"{block}.{GATED_BLOCKS[block]}":
            continue
        present, value = _get(cfg, path)
        view[path] = value if present else default
    return dict(sorted(view.items()))


def calibration_hash(cfg: Mapping[str, Any], length: int = 12) -> str:
    """Stable short hash of a config's calibration identity.

    Args:
        cfg: As for :func:`calibration_view`.
        length: Hex characters to keep (default 12, ~48 bits — collision-free
            for the handful of eras a corpus this size can hold).

    Returns:
        The first ``length`` hex characters of the SHA-256 of the canonical
        JSON encoding of :func:`calibration_view`.
    """
    canonical = json.dumps(calibration_view(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]
