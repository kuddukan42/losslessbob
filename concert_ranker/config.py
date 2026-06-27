"""Externalized configuration for concert_ranker.

Every threshold that maps a raw metric to a human-readable band, and every
scoring weight, lives here as a named constant. This is deliberate: per the
"scan once" requirement, the audio scan stores RAW aggregated metric values in
the DB, and all banding / scoring / ranking is derived from those stored values.
That means thresholds can be re-tuned and the whole corpus re-categorized
WITHOUT re-scanning a single audio file.

Constants marked `# CALIBRATE` are provisional first-principles values. They are
intended to be fitted by calibrate/ against the existing LB A-F ratings +
SBD/AUD source class + mined human commentary, then written back here (or into
the DB-stored override table). Do not trust them as ranking-grade until fitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────────────
# Audio / two-rate strategy
# ─────────────────────────────────────────────────────────────────────────────
# Bulk pass: clarity, crowd, tonal-balance, onset, handling, stereo. 22.05 kHz
# is plenty (the discriminating signal is sub-10 kHz) and halves STFT cost.
BULK_SR = 22050

# Native pass: hiss (8-14k), air (8-16k), HF ceiling, lossy brick-wall. These
# need real high-frequency content. We do NOT decode the whole file at native
# rate — only a handful of short windows (these signals are stationary enough).
NATIVE_SR = 44100
NATIVE_WINDOW_SEC = 20.0
NATIVE_N_WINDOWS = 8          # sampled across the performance body

STFT_N_FFT = 2048
STFT_HOP = 512


# ─────────────────────────────────────────────────────────────────────────────
# Frequency bands (Hz). Single source of truth — features read these.
# ─────────────────────────────────────────────────────────────────────────────
BANDS = {
    "sub":        (20,    80),
    "bass":       (80,    250),
    "low_mid":    (250,   800),
    "ref_mid":    (800,   2000),   # neutral anchor for ratios
    "mid":        (800,   3500),   # vocal presence / intelligibility
    "presence":   (1000,  4000),
    "harsh":      (2000,  5000),   # forward glare
    "sibilance":  (5000,  9000),   # essy / fatiguing
    "air":        (8000,  16000),
    "hiss":       (8000,  14000),
}


# ─────────────────────────────────────────────────────────────────────────────
# Polarity registry: +1 means higher metric = BETTER, -1 means higher = WORSE.
# Used by normalization so every metric pushes the score the correct direction.
# ─────────────────────────────────────────────────────────────────────────────
POLARITY = {
    # clarity
    "presence_ratio_db":     +1,
    # directness: scan-8 data (n=2798) shows rho=-0.272 and commentary Δ/σ=-0.82 —
    # bad recordings score HIGHER (spectral imbalance artifact, not proximity).
    # Kept in QUALITY_MODEL with weight=-0.31 where it earns CV Spearman, but
    # excluded from family comparison (polarity=0) and labeling (removed from QUALITY_BANDS).
    "directness":             0,
    # onset_clarity: rho=-0.131, commentary Δ/σ=+0.04 — no clarity signal, slight
    # negative correlation with quality (crowd noise inflates onset_env). Excluded.
    "onset_clarity":          0,
    # crowd / audience
    "crowd_snr_db":          +1,   # signal above crowd floor: higher = better
    "intrusion_rate":        -1,
    "handling_rate":         -1,
    # tonal (these are *deviation* magnitudes; closer to 0 = better, handled
    # specially in banding — polarity here is for the |value| used in fusion)
    "bass_ratio_db":          0,   # signed; banded both directions, not fused linearly
    "air_ratio_db":           0,
    "mud_ratio_db":          -1,   # higher low-mid excess = worse
    "harsh_ratio_db":        -1,
    "sibilance_ratio_db":    -1,
    "sibilance_crest":       -1,
    # distortion / defects
    "clip_fraction":         -1,
    "true_peak_dbtp":        -1,
    "crest_factor_db":       +1,   # higher crest = more dynamic / less squashed
    # noise
    "hiss_floor_db":         -1,   # higher (less negative) hiss floor = worse
    "hum_excess_db":         -1,
    # spatial
    "lr_corr":                0,   # banded (fake-stereo high / phase-problem low)
    "stereo_width":           0,   # preference axis, banded not linearly fused
    "channel_balance_db":    -1,   # |imbalance| — but stored signed, |.| in fusion
    "azimuth_lag_us":        -1,   # |inter-channel delay| in microseconds
    # informational (not fused)
    "hf_ceiling_hz":          0,
    "dynamic_range_dr":       0,
    "spectral_centroid_hz":   0,
    "lufs_integrated":        0,
    # speech-band SNR (TODO-191): already extracted; needs calibration to validate
    "speech_band_snr_db":     +1,   # higher SNR = more intelligible vocals
    # waveform distortion (TODO-191)
    "brickwall_score":        -1,   # smooth between-peak ramps = pre-amp overload
    "single_ch_transient_count": -1,  # mic hits (L/R asymmetric impulses)
    # HF source-type signatures (TODO-189)
    "minidisc_score":         -1,   # ATRAC lossy encoding (lego parapets)
    "dat32k_flag":            -1,   # 32 kHz DAT = Nyquist at 16k (bandwidth loss)
    "cassette_flag":          -1,   # cassette tape HF rolloff
    "tv_band_flag":            0,   # CRT monitor band — informational, not a defect
    # text features from curator description (TODO-188)
    "txt_clipping":           -1,
    "txt_brickwall":          -1,
    "txt_limiting":           -1,
    "txt_digipop":            -1,
    "txt_dropout":            -1,
    "txt_gap":                -1,
    "txt_mic_hit":            -1,
    "txt_hf_streak":          -1,
    "txt_compression":        -1,
    "txt_minidisc":           -1,
    "txt_floating_parapet":   -1,
    "txt_32k_dat":            -1,
    "txt_talking":            -1,
    "txt_singing":            -1,
    "txt_remaster":           -1,
    "txt_tv_band":             0,   # informational
    "txt_cassette":           -1,
    "txt_eac_match":          -1,
}


# ─────────────────────────────────────────────────────────────────────────────
# HARD DISQUALIFIERS — these VETO a recording rather than averaging into a score.
# A tripped disqualifier produces a human label and removes the recording from
# (or heavily demotes it within) the sibling ranking. They are NOT fused.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Disqualifier:
    metric: str
    threshold: float
    direction: str   # "above" or "below" threshold trips it
    label: str       # human-readable verdict
    veto: bool = True  # True = exclude from ranking; False = heavy demerit only


# crowd_snr_db threshold fitted from scan_id 3 (73 AUD): worst ~5% sit below -1.4.
# hum_excess_db was reworked in round 3 to require a 50/60 Hz harmonic COMB (no
# longer confounded with bass); kept high pending a real comb-hum case.
#
# dropout_count DISABLED 2026-06-25 (TODO-183). The locally-normalized-roughness
# rework de-confounded on a small stratified subset (rho +0.43 -> -0.04) but the
# fresh full scan (scan_id 8, 2798 AUD, the scan that was meant to validate it)
# shows the confound is NOT gone at scale: rho vs rating = +0.417, and median
# dropout_count by tier runs A:118 A-:55 B:27 B-:12 ... C/D ~6-17 — i.e. the BEST
# recordings score HIGHEST. The detector still measures transient/HF density
# (drum attacks, full-bandwidth dynamics), not defects, so no threshold can make
# it a valid veto. Removed from DISQUALIFIERS until the detector is reworked to
# actually isolate digital clicks/dropouts from musical transients. (It was never
# a QUALITY_MODEL predictor, so scores are unaffected.)
DISQUALIFIERS = [
    Disqualifier("lossy_flag",       0.5,    "above", "lossy source suspected", veto=True),
    # Disqualifier("dropout_count", 150, "above", "has dropouts/glitches", veto=False),
    #   ^ disabled — confounded with fidelity at scale (see note above).
    Disqualifier("hum_excess_db",    10.0,   "above", "audible mains hum",      veto=False),
    Disqualifier("clip_fraction",    0.02,   "above", "significant clipping",   veto=False),
    Disqualifier("completeness",     0.90,   "below", "incomplete (missing material)", veto=False),
    Disqualifier("crowd_snr_db",     -1.4,   "below", "buried in crowd",        veto=False),
    Disqualifier("lr_corr",          -0.1,   "below", "stereo phase problem",   veto=False),
]


# ─────────────────────────────────────────────────────────────────────────────
# BANDS → human categories. Each entry: ordered list of (cutoff, label).
# Evaluated low→high; first cutoff the value is <= wins. Final label is the
# "else" (value above all cutoffs). `signed` ratios use a symmetric scheme.
#
# CALIBRATED from scan_id 6 (2026-06-24, 697-show decade-stratified sample;
# cutoffs = ~320 AUD percentiles, the dominant fittable class). Supersedes the
# scan_id 3 (117-show) fit. The de-confounded metrics held at scale — AUD rho vs
# rating: hiss_floor_db -0.64 (now the strongest predictor), harsh_ratio_db -0.03
# (neutral). Net over the 696-show sample: label-fires 1117 -> 930.
# Re-fit with: concert_ranker calibrate --by-decade  (then re-derive percentiles).
# KNOWN ERA VARIATION (candidate for per-decade bands): AUD hiss_floor_db median
# swings -2.0 (1960s tape) -> -8.1 (2000s digital); crowd/centroid vary moderately.
# A single global band therefore reads 1960s recordings as hissier (which they are);
# per-era bands would rank more fairly WITHIN a decade. See TODO-183.
# ─────────────────────────────────────────────────────────────────────────────

# Signed tonal axes: negative label / neutral / positive label.
# (low_cut, low_label, high_cut, high_label)  -> between cuts = neutral ("balanced")
# Cuts = AUD p10 / p90.
SIGNED_BANDS = {
    # bass_ratio_db = bass - mid. Very negative = thin, very positive = boomy.
    "bass_ratio_db":  (7.3, "thin / bass-light", 25.8, "boomy / bass-heavy"),
    # air_ratio_db = air - mid. Negative = dull/closed, positive = airy/bright.
    "air_ratio_db":   (-40.3, "dull / closed",   -18.9, "bright / airy"),
    # stereo width: near 0 = mono-ish, high = wide
    "stereo_width":   (0.02, "effectively mono",  0.73, "very wide"),
}

# One-directional severity bands: (cutoff, label) ascending; higher = worse.
# Cuts = AUD p70 / p90 / p98 (mud, harsh); crowd_snr reversed (low = worse) at
# p10 / p30 / p60 (widened to restore "crowd-heavy" recall); hiss at p15/p70/p90/p98.
# sibilance unchanged (no data — not produced by the scan).
SEVERITY_BANDS = {
    "mud_ratio_db":       [(16.6, None), (23.0, "slightly muddy"), (33.5, "muddy")],
    "harsh_ratio_db":     [(2.3, None), (5.5, "a little forward"), (8.8, "harsh")],
    "sibilance_ratio_db": [(3.0, None), (6.0, "slightly essy"), (10.0, "sibilant")],
    "hiss_floor_db":      [(-9.7, "very quiet"), (-2.1, None), (-0.3, "some hiss"), (-0.02, "hissy")],
    "crowd_snr_db":       [(2.1, "buried in crowd"), (4.5, "crowd-heavy"), (6.9, "some crowd"), (999, "clean")],
}

# Quality (positive-is-good) bands: (cutoff, label) ascending.
# presence cuts = AUD p15 / p40 / p75. dynamic_range_dr unchanged (not produced
# by the scan yet). directness REMOVED — scan-8 shows bad recordings score higher
# (spectral imbalance, not proximity); labels were inverted. See POLARITY note.
QUALITY_BANDS = {
    "presence_ratio_db":  [(-9.4, "distant / recessed vocals"), (-5.9, "slightly recessed"),
                           (-3.75, "present vocals"), (999, "very forward vocals")],
    "dynamic_range_dr":   [(7.0, "compressed / squashed"), (11.0, "moderate dynamics"), (999, "open dynamics")],
}


# ─────────────────────────────────────────────────────────────────────────────
# PER-DECADE BANDS. Recording technology shifts the raw scales a lot across eras
# (AUD hiss_floor_db "hissy" cut runs +0.6 in the 1960s tape era down to -1.4 in
# the 2000s digital era), so judging every show against one global band reads
# vintage recordings as systematically hissier/duller. These per-decade cutoffs
# (AUD percentiles per decade from scan_id 6) let the scorer band a recording
# against the norms of its OWN era; the scorer falls back to the global bands
# above when a recording's decade is unknown or not represented here.
# sibilance_ratio_db / dynamic_range_dr stay global (not produced by the scan).
# Re-derive with: concert_ranker calibrate --by-decade  then refit per decade.
# ─────────────────────────────────────────────────────────────────────────────
_DECADE_CUTS = {
    1960: {  # n=53 AUD
        "mud": [17.75, 23.0, 29.18], "harsh": [3.03, 6.14, 8.82],
        "hiss": [-8.81, -0.84, -0.21, 0.6], "crowd": [4.0, 7.5, 9.97],
        "bass": [3.66, 21.35], "air": [-44.4, -24.55], "width": [0.0, 0.61],
        "presence": [-10.24, -6.4, -4.25],
    },
    1970: {  # n=59 AUD
        "mud": [19.11, 29.52, 33.65], "harsh": [0.75, 4.88, 6.55],
        "hiss": [-8.01, -1.44, -0.17, -0.08], "crowd": [2.15, 3.92, 5.61],
        "bass": [11.36, 28.78], "air": [-39.09, -23.22], "width": [0.03, 0.65],
        "presence": [-11.27, -6.71, -4.27],
    },
    1980: {  # n=58 AUD
        "mud": [14.4, 24.4, 33.71], "harsh": [3.69, 7.33, 9.56],
        "hiss": [-8.04, -1.1, -0.34, -0.11], "crowd": [2.0, 4.02, 5.69],
        "bass": [7.78, 31.17], "air": [-39.56, -24.04], "width": [0.09, 0.95],
        "presence": [-9.28, -5.0, -2.54],
    },
    1990: {  # n=58 AUD
        "mud": [16.05, 19.37, 22.9], "harsh": [3.33, 7.64, 8.89],
        "hiss": [-10.72, -1.49, -0.21, 0.15], "crowd": [1.04, 2.91, 5.5],
        "bass": [6.84, 24.5], "air": [-42.7, -18.72], "width": [0.23, 0.74],
        "presence": [-8.36, -5.39, -3.1],
    },
    2000: {  # n=49 AUD
        "mud": [17.13, 21.44, 27.26], "harsh": [-0.4, 3.13, 4.87],
        "hiss": [-10.47, -6.04, -3.63, -1.42], "crowd": [2.93, 5.0, 6.98],
        "bass": [11.02, 24.61], "air": [-28.4, -16.52], "width": [0.09, 0.61],
        "presence": [-8.27, -6.41, -4.92],
    },
    2010: {  # n=43 AUD
        "mud": [14.69, 18.62, 21.35], "harsh": [1.47, 2.83, 4.16],
        "hiss": [-10.79, -6.01, -3.27, -1.02], "crowd": [4.06, 6.26, 7.89],
        "bass": [6.77, 23.64], "air": [-34.51, -21.91], "width": [0.0, 0.82],
        "presence": [-8.16, -5.61, -4.0],
    },
}


def _build_decade_bands(c: dict) -> dict:
    """Assemble {SIGNED, SEVERITY, QUALITY} band dicts from one decade's cutoffs.

    Mirrors the global band structure. ``crowd_snr_db`` is deliberately held on
    the GLOBAL (absolute) band — it measures actual crowd level, so a soundboard
    should read "clean" regardless of class/era. Relativizing it made ~60% of
    soundboards read "some crowd"/"crowd-heavy" (clean shows judged against their
    cleaner-than-AUD peers). sibilance/dynamic_range likewise stay global (no
    per-decade data). Everything else (hiss, tonal) is class/era-relative.
    """
    return {
        "SIGNED": {
            "bass_ratio_db": (c["bass"][0], "thin / bass-light", c["bass"][1], "boomy / bass-heavy"),
            "air_ratio_db": (c["air"][0], "dull / closed", c["air"][1], "bright / airy"),
            "stereo_width": (c["width"][0], "effectively mono", c["width"][1], "very wide"),
        },
        "SEVERITY": {
            "mud_ratio_db": [(c["mud"][0], None), (c["mud"][1], "slightly muddy"), (c["mud"][2], "muddy")],
            "harsh_ratio_db": [(c["harsh"][0], None), (c["harsh"][1], "a little forward"), (c["harsh"][2], "harsh")],
            "sibilance_ratio_db": SEVERITY_BANDS["sibilance_ratio_db"],
            "hiss_floor_db": [(c["hiss"][0], "very quiet"), (c["hiss"][1], None),
                              (c["hiss"][2], "some hiss"), (c["hiss"][3], "hissy")],
            "crowd_snr_db": SEVERITY_BANDS["crowd_snr_db"],  # absolute — see docstring
        },
        "QUALITY": {
            "presence_ratio_db": [(c["presence"][0], "distant / recessed vocals"),
                                  (c["presence"][1], "slightly recessed"),
                                  (c["presence"][2], "present vocals"), (999, "very forward vocals")],
            "dynamic_range_dr": QUALITY_BANDS["dynamic_range_dr"],
        },
    }


# {decade_int: {"SIGNED": {...}, "SEVERITY": {...}, "QUALITY": {...}}}
DECADE_BANDS = {decade: _build_decade_bands(cuts) for decade, cuts in _DECADE_CUTS.items()}


# ─────────────────────────────────────────────────────────────────────────────
# PER-CLASS BANDS (HYBRID). An A-rated SBD and an A-rated AUD are not on the same
# curve (design decision #5): line sources have lower hiss (scan_id 6 median
# hiss_floor_db AUD -5.2 / SBD -9.2), so SBD/FM band hiss + tonal against
# soundboard norms. BUT crowd_snr_db is held GLOBAL (see _build_decade_bands):
# relativizing crowd made ~60% of soundboards read "some crowd"/"crowd-heavy"
# (an 8.5-dB SBD has far less crowd than any AUD, so it should read "clean") —
# crowd level is meaningful absolutely. Within-class *ranking* is already handled
# by MAD-z over same-show siblings. Fit from the 165 SBD in scan_id 6 (class-
# global; SBD-per-decade deferred — too sparse, esp. 2010s n=7). FM (n=27) reuses
# the SBD set. The "crowd" cuts below are retained for reference but unused.
# ─────────────────────────────────────────────────────────────────────────────
_SBD_CUTS = {
    "mud": [15.63, 19.35, 24.3], "harsh": [2.2, 4.36, 9.39],
    "hiss": [-12.36, -6.39, -2.68, -0.16], "crowd": [4.78, 7.05, 9.36],
    "bass": [10.22, 22.78], "air": [-40.66, -18.81], "width": [0.02, 0.59],
    "presence": [-6.89, -5.67, -3.47], "directness": [0.13, 0.15],
}

# {source_class: {"SIGNED": {...}, "SEVERITY": {...}, "QUALITY": {...}}}
CLASS_BANDS = {"SBD": _build_decade_bands(_SBD_CUTS)}

_GLOBAL_BANDS = {"SIGNED": SIGNED_BANDS, "SEVERITY": SEVERITY_BANDS, "QUALITY": QUALITY_BANDS}


def decade_of(year: int | None) -> int | None:
    """Floor a 4-digit year to its decade (e.g. 1987 -> 1980); None passes through."""
    return (year // 10) * 10 if year else None


def resolve_band_set(decade: int | None = None,
                     source_class: str | None = None) -> dict:
    """Pick the band set for a recording's class + era.

    Resolution order: SBD/FM → the class-global SBD bands; otherwise (AUD /
    UNKNOWN / unknown) → the recording's per-decade bands; falling back to the
    global bands when the decade is unknown or unrepresented.
    """
    if source_class in ("SBD", "FM") and "SBD" in CLASS_BANDS:
        return CLASS_BANDS["SBD"]
    return DECADE_BANDS.get(decade, _GLOBAL_BANDS)


# ─────────────────────────────────────────────────────────────────────────────
# ABSOLUTE QUALITY MODEL. A ridge regression that predicts the LB rating rank
# (1=F .. 13=A+) from the validated metrics, giving every recording a standalone
# 0-100 score + A+..F letter grade — independent of the within-family ranking.
# Inputs are median-imputed then standardized by (mean, std); predicted rank =
# intercept + weights·z. Re-fit when the metric set or calibration sample changes.
# (AUD-fit; applied to all classes — SBD/FM grades are approximate, see TODO-183.)
#
# REFIT 2026-06-25 on scan_id 8 (2798 rated AUD, the full by-decade overnight scan
# — 6x the previous 466). 5-fold CV (3 seeds) correlation to the real LB rating:
# Spearman 0.664, 75.9% within one letter tier. Predictors chosen by forward
# selection over a 14-metric pool (alpha=0.3 ridge); every weight's sign matches
# its univariate direction (no confound). The previous 466-fit model's headline
# 0.65 was small-sample-optimistic — it scored only Spearman 0.561 / 46% within-1
# on this full set, mostly from a mis-centered intercept (it was fit on a
# middle-tier-focused sample; the collection's true mean rank is ~9.8 = B/A-).
# The forward-selected set dropped the old HF metrics (hf_ceiling/centroid/air/
# crest) as collinear, keeping complementary signals (mud/onset/harsh/presence/
# directness/bass/crowd_snr/hiss). dropout_count excluded — confounded (TODO-183).
# dff_vert_occ = log1p(dff_reports.vert_occ) added 2026-06-25 (+0.005 CV rho);
# injected at rerank time from dff_reports table (no re-scan needed). 89% coverage.
# ─────────────────────────────────────────────────────────────────────────────
QUALITY_MODEL = {
    "predictors": ["hiss_floor_db", "bass_ratio_db", "mud_ratio_db", "onset_clarity",
                   "directness", "crowd_snr_db", "dff_vert_occ",
                   "harsh_ratio_db", "presence_ratio_db"],
    "median": [-7.2012, 17.2119, 13.2268, 2.4367, 0.1463, 6.4412, 1.0986, 0.0167, -5.4416],
    "mean":   [-6.9222, 16.9675, 13.3818, 2.5187, 0.1488, 6.6034, 1.499, 0.253, -5.5205],
    "std":    [3.6268, 5.753, 5.0761, 0.6596, 0.022, 2.9169, 1.569, 3.3036, 2.6386],
    "intercept": 9.80772,
    "weights":   [-0.5916, 0.3482, -0.7161, -0.6886, -0.3097, 0.4154, -0.1274, -0.5952, 0.5796],
}

# ─────────────────────────────────────────────────────────────────────────────
# SBD/FM ABSOLUTE QUALITY MODEL. The AUD model above mis-grades soundboards —
# mud_ratio_db/presence_ratio_db/spectral_centroid_hz/crowd_snr_db barely track
# the SBD rating (|rho| < 0.25; AUD-specific confounds), while harsh_ratio_db
# and directness do and aren't in the AUD set. Fit on scan 9: 506 SBD+FM
# recordings (479 SBD + 27 FM) all scanned with the current dropout detector,
# joined to entries.rating. AUD model applied to this set: Spearman 0.429,
# 73.5% within one tier. This fit: Spearman 0.562, 80.2% within one tier
# (5-fold CV, alpha=0.5). dropout_count tested (rho=-0.077, p=0.082, weight
# ~0) — not predictive with consistent detector values, excluded.
# ─────────────────────────────────────────────────────────────────────────────
QUALITY_MODEL_SBD = {
    "predictors": ["hiss_floor_db", "hf_ceiling_hz", "crest_factor_db",
                   "air_ratio_db", "harsh_ratio_db", "directness"],
    "median": [-9.139, 13000.0, 17.2608, -27.3748, 0.5015, 0.1439],
    "mean":   [-8.9559, 12180.83, 17.2514, -27.7598, 0.8914, 0.1453],
    "std":    [4.3211, 2573.7456, 2.2494, 8.7013, 2.9918, 0.025],
    "intercept": 10.36759,
    "weights": [-0.19358, 0.17295, 0.32164, 0.07951, -0.16199, -0.41081],
}


# ─────────────────────────────────────────────────────────────────────────────
# Feature-family fusion weights. Within-family metrics are MAD-z normalized
# across the sibling set, combined per family, then families combined to a
# track score; tracks aggregate to a recording score.
# ─────────────────────────────────────────────────────────────────────────────
FAMILY_WEIGHTS = {
    "clarity":    1.0,
    "crowd":      2.0,   # heaviest: intelligibility dominates AUD listenability
    "tonal":      1.0,
    "distortion": 1.5,
    "spatial":    0.8,
}

# Recording-score components (Codex-derived, kept):
RECORDING_SCORE = {
    "mean_track_quality":   1.0,
    "consistency":          0.5,   # low intra-recording variance = better
    "worst_track_penalty":  0.5,   # protect against one terrible track / bad splice
}


# ─────────────────────────────────────────────────────────────────────────────
# Source-class conditioning. Calibration fits thresholds WITHIN each class,
# because an A-rated AUD and an A-rated SBD are not on the same absolute curve.
# ─────────────────────────────────────────────────────────────────────────────
SOURCE_CLASSES = ("SBD", "AUD", "FM", "UNKNOWN")


@dataclass
class Config:
    bulk_sr: int = BULK_SR
    native_sr: int = NATIVE_SR
    native_window_sec: float = NATIVE_WINDOW_SEC
    native_n_windows: int = NATIVE_N_WINDOWS
    n_fft: int = STFT_N_FFT
    hop: int = STFT_HOP
    bands: dict = field(default_factory=lambda: dict(BANDS))
    polarity: dict = field(default_factory=lambda: dict(POLARITY))
    family_weights: dict = field(default_factory=lambda: dict(FAMILY_WEIGHTS))


def default_config() -> Config:
    return Config()
