"""Feature extractors. Every function takes a pre-built cache and returns a flat
dict of RAW metric values (the things stored in the DB). No decoding, no STFT —
that already happened once in cache.py. Banding/scoring happens later, from the
stored raw values, so thresholds can change without rescanning.

Families:
  clarity   — presence, directness (distance/reverberance), onset clarity
  crowd     — crowd SNR (the big AUD number), intrusion + handling event rates
  tonal     — bass/air/mud/harsh/sibilance balance
  distortion— clipping, crest factor, dropouts, hum
  spatial   — L-R correlation, width, channel balance, azimuth (inter-channel lag)
  hf_native — hiss, air, HF ceiling, lossy brick-wall   (uses NativeProbe)
"""
from __future__ import annotations

import numpy as np

from .audio.cache import NativeProbe, TrackCache
from .config import BANDS


# ─────────────────────────────────────────────────────────────────────────────
# CLARITY
# ─────────────────────────────────────────────────────────────────────────────
def extract_clarity(c: TrackCache) -> dict:
    presence = c.band_db(*_b("presence"))
    ref = c.band_db(*_b("ref_mid"))
    presence_ratio = presence - ref

    # Directness / reverberance via spectral contrast: peak-to-valley spread
    # across sub-bands. A close/direct recording has sharp spectral structure;
    # a distant/roomy one is smeared flat. Computed from the magnitude we have.
    mag = c.stft_mag
    # mean over time, then contrast across log-spaced frequency sub-bands
    spec = mag.mean(axis=1) + 1e-12
    n_sub = 6
    edges = np.logspace(np.log10(50), np.log10(c.sr / 2), n_sub + 1)
    contrasts = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=False):
        m = (c.freqs >= lo) & (c.freqs < hi)
        if m.sum() < 4:
            continue
        sub = np.sort(spec[m])
        k = max(1, len(sub) // 5)
        peak = sub[-k:].mean()
        valley = sub[:k].mean()
        contrasts.append(10 * np.log10(peak / (valley + 1e-12)))
    directness = float(np.mean(contrasts)) / 40.0 if contrasts else 0.0  # ~0..1

    # Onset clarity: how sharp transients are (median onset strength, normalized
    # by broadband energy so it isn't just a loudness proxy)
    onset_clarity = float(np.median(c.onset_env) /
                          (np.median(np.abs(c.mono)) + 1e-9))

    return {
        "presence_ratio_db": presence_ratio,
        "directness": directness,
        "onset_clarity": onset_clarity,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CROWD / AUDIENCE
# ─────────────────────────────────────────────────────────────────────────────
def extract_crowd(c: TrackCache) -> dict:
    # Crowd SNR: music mid-band level during LOUD passages vs the mid-band floor
    # during QUIET passages (which, for an AUD recording, is dominated by crowd).
    quiet = c.quiet_frame_mask(20.0)
    loud = ~quiet
    lo, hi = _b("mid")
    fmask = (c.freqs >= lo) & (c.freqs < hi)
    mid_mag = c.stft_mag[fmask, :]
    mid_db = 10 * np.log10((mid_mag ** 2).sum(axis=0) + 1e-12)
    music_level = float(np.median(mid_db[loud])) if loud.any() else float("nan")
    crowd_floor = float(np.median(mid_db[quiet])) if quiet.any() else float("nan")
    crowd_snr = music_level - crowd_floor

    # Intrusion events: sharp foreground bursts in the speech band during quiet
    # frames (claps/whistles/talkers near the mic). Rate per minute.
    intrusion_rate = _event_rate(c.onset_env, c.times,
                                 thresh_pct=99.0, restrict=quiet)

    # Handling noise: low-frequency (sub/bass) transient thumps — mic bumps,
    # stand knocks, cable handling. Distinct from crowd (broadband, speech band)
    # and clicks (broadband impulsive). Look for sub-100 Hz energy spikes.
    sub_lo, sub_hi = _b("sub")
    smask = (c.freqs >= sub_lo) & (c.freqs < sub_hi)
    sub_env = c.stft_mag[smask, :].sum(axis=0) if smask.any() else np.zeros_like(c.times)
    handling_rate = _event_rate(sub_env, c.times, thresh_pct=99.5)

    return {
        "crowd_snr_db": crowd_snr,
        "intrusion_rate": intrusion_rate,
        "handling_rate": handling_rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TONAL BALANCE
# ─────────────────────────────────────────────────────────────────────────────
def extract_tonal(c: TrackCache) -> dict:
    bass = c.band_db(*_b("bass"))
    mid = c.band_db(*_b("mid"))
    low_mid = c.band_db(*_b("low_mid"))
    presence = c.band_db(*_b("presence"))
    harsh = c.band_db(*_b("harsh"))
    ref = c.band_db(*_b("ref_mid"))
    sib = c.band_db(*_b("sibilance"))
    centroid = _spectral_centroid(c)

    # Harsh as a LOCAL 2-5 kHz prominence above the trend between its flanking
    # bands (ref_mid below, sibilance above) — NOT harsh - ref_mid. The old
    # difference rose monotonically with HF brightness, so brighter (better-rated)
    # recordings looked "harsher" (calibration found harsh_ratio_db tracked the
    # rating POSITIVELY). Subtracting the flank midpoint cancels that overall-tilt
    # confound and leaves only a genuine forward 2-5 kHz bump.
    harsh_excess = harsh - 0.5 * (ref + sib)

    return {
        "bass_ratio_db": bass - mid,           # signed: -thin / +boomy
        "mud_ratio_db": low_mid - presence,     # +: muddy
        "harsh_ratio_db": harsh_excess,         # +: genuine 2-5 kHz forwardness
        "spectral_centroid_hz": centroid,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DISTORTION / DEFECTS  (bulk-rate; clipping & dropouts need time domain)
# ─────────────────────────────────────────────────────────────────────────────
def extract_distortion(c: TrackCache) -> dict:
    x = c.mono
    peak = np.abs(x)
    clip_fraction = float((peak >= 0.9985).mean())

    # crest factor (dB): peak-to-RMS. Low = squashed/over-limited or clipped.
    rms = np.sqrt(np.mean(x ** 2)) + 1e-12
    crest_db = 20 * np.log10((peak.max() + 1e-12) / rms)

    # dropout / click count (see helper). The old z>12 second-difference test
    # counted every sharp musical transient (cymbals/attacks) — medians ran into
    # the thousands and it was useless as a defect gate. The helper instead counts
    # only ISOLATED discontinuities (a click is a lone anomalous sample; sustained
    # HF is music), at a far more extreme threshold.
    dropout_count = _dropout_count(x)

    # mains hum: narrowband excess at 50/60 Hz harmonics vs local floor.
    hum_excess = _hum_excess_db(c)

    # hiss: HF noise persistence, de-confounded from musical brightness (see helper)
    hiss_floor = _hiss_floor_db(c)

    return {
        "clip_fraction": clip_fraction,
        "crest_factor_db": float(crest_db),
        "dropout_count": dropout_count,
        "hum_excess_db": hum_excess,
        "hiss_floor_db": hiss_floor,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SPATIAL  (needs stereo; degrades safely on mono)
# ─────────────────────────────────────────────────────────────────────────────
def extract_spatial(c: TrackCache) -> dict:
    if not c.is_stereo:
        return {
            "lr_corr": float("nan"),
            "stereo_width": 0.0,
            "channel_balance_db": 0.0,
            "azimuth_lag_us": 0.0,
            "_mono": True,
        }
    L, R = c.left, c.right
    n = min(len(L), len(R))
    L, R = L[:n], R[:n]

    lr_corr = float(np.corrcoef(L, R)[0, 1])

    mid = (L + R) / 2
    side = (L - R) / 2
    width = float(np.sqrt(np.mean(side ** 2)) / (np.sqrt(np.mean(mid ** 2)) + 1e-9))

    bal_db = 20 * np.log10((np.sqrt(np.mean(L ** 2)) + 1e-12) /
                           (np.sqrt(np.mean(R ** 2)) + 1e-12))

    # Azimuth / inter-channel delay: lag (in samples) of peak L-R cross-correlation.
    # A nonzero sub-ms lag indicates analog-transfer head-azimuth error. Measured
    # on a decimated slice for speed; converted to microseconds.
    azimuth_us = _azimuth_lag_us(L, R, c.sr)

    return {
        "lr_corr": lr_corr,
        "stereo_width": width,
        "channel_balance_db": float(bal_db),
        "azimuth_lag_us": azimuth_us,
        "_mono": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HF NATIVE  (hiss, air, HF ceiling, lossy) — uses the cheap NativeProbe
# ─────────────────────────────────────────────────────────────────────────────
def extract_hf_native(p: NativeProbe) -> dict:
    if p.psd_db.size == 0:
        return {k: float("nan") for k in
                ("air_ratio_db", "hf_ceiling_hz")} | {"lossy_flag": 0.0}

    air = p.band_db(8000, 16000)
    mid = p.band_db(800, 3500)
    air_ratio = air - mid

    # HF ceiling: highest 1 kHz band whose level sits clearly above the PSD floor.
    floor = float(np.percentile(p.psd_db, 20))
    ceiling = 0.0
    for hz in range(2000, int(p.nyquist_hz) - 1000, 1000):
        if p.band_db(hz, hz + 1000) > floor + 8:
            ceiling = hz

    # Lossy brick-wall: sudden steepening of HF rolloff (a shelf, not a gentle
    # cassette/FM rolloff). Compare slope just below a candidate cutoff to the
    # slope above it. A sharp negative break = MP3/AAC signature.
    lossy = _lossy_brickwall(p)

    return {
        "air_ratio_db": air_ratio,
        "hf_ceiling_hz": ceiling,
        "lossy_flag": lossy,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _b(name: str):
    return BANDS[name]


def _hiss_floor_db(c: TrackCache) -> float:
    """HF noise persistence: 8-11 kHz level in quiet frames minus loud frames.

    Tape/electronic hiss is roughly constant regardless of music level, so it
    dominates the HF band during quiet passages while *musical* HF collapses when
    the music does. quiet-minus-loud HF level therefore isolates the hiss floor
    from musical brightness — the old absolute 8-14 kHz level conflated the two,
    so brighter (better-rated) recordings measured as hissier. Higher (toward 0)
    = more persistent HF noise = hissier; very negative = HF is musical, not hiss.
    Computed at bulk rate (8-11 kHz, just under the 11.025 kHz Nyquist).
    """
    fmask = (c.freqs >= 8000) & (c.freqs < 11000)
    if not fmask.any():
        return float("nan")
    quiet = c.quiet_frame_mask(20.0)
    loud = ~quiet
    if not (quiet.any() and loud.any()):
        return float("nan")
    hf = c.stft_mag[fmask, :]
    hf_db = 10 * np.log10((hf ** 2).sum(axis=0) + 1e-12)
    return float(np.median(hf_db[quiet]) - np.median(hf_db[loud]))


def _spectral_centroid(c: TrackCache) -> float:
    spec = c.stft_mag.mean(axis=1)
    return float((c.freqs * spec).sum() / (spec.sum() + 1e-12))


def _event_rate(env, times, thresh_pct=99.0, restrict=None) -> float:
    if restrict is not None and restrict.any():
        ref = env[restrict]
    else:
        ref = env
    if ref.size == 0:
        return 0.0
    thr = np.percentile(ref, thresh_pct)
    crossings = (env > thr).astype(int)
    events = int(((np.diff(crossings) == 1)).sum())
    minutes = (times[-1] - times[0]) / 60.0 if len(times) > 1 else 1.0
    return events / max(minutes, 1e-6)


def _dropout_count(x: np.ndarray) -> int:
    """Count impulsive clicks / glitches via LOCALLY-NORMALIZED roughness.

    Band-limited music is smooth, so the second difference ``|x[n+1]-2x[n]+x[n-1]|``
    (a "roughness") is bounded; a click is an impulse with huge roughness. Earlier
    detectors thresholded that roughness GLOBALLY, so loud/dynamic passages tripped
    it and the metric rewarded crisp recordings (it correlated +0.43 with the
    rating — better shows looked glitchier). The fix: normalize each sample's
    roughness by the LOCAL roughness level (a ~12 ms rolling mean). A click far
    exceeds its neighbourhood regardless of how loud/dynamic that passage is, so a
    busy drum fill no longer counts while a real click in a quiet passage still
    does — level/dynamics independent. Only NARROW events (<= 3 samples, i.e.
    impulses, not sustained energy) are counted.
    """
    n = len(x)
    if n < 512:
        return 0
    from scipy.ndimage import uniform_filter1d

    rough = np.abs(np.diff(x, n=2))                       # local roughness, len n-2
    local = uniform_filter1d(rough, size=257, mode="nearest") + 1e-9
    hi = (rough / local) > 12.0                            # >> the local roughness
    if not hi.any():
        return 0
    # count contiguous runs (events); keep only narrow ones (clicks, not passages)
    edges = np.diff(hi.view(np.int8))
    starts = np.flatnonzero(edges == 1) + 1
    ends = np.flatnonzero(edges == -1) + 1
    if hi[0]:
        starts = np.r_[0, starts]
    if hi[-1]:
        ends = np.r_[ends, len(hi)]
    widths = ends - starts
    return int((widths <= 3).sum())


def _hum_excess_db(c: TrackCache) -> float:
    """Mains hum as a HARMONIC COMB at 50- or 60-Hz multiples, not a lone peak.

    The old version took the worst single 50/60-Hz-family peak excess over the
    whole-track PSD — but a single bass note landing on a 50/60/100/120-Hz bin
    produces the same lone peak, so the metric tracked bass energy (it rose WITH
    the rating). Real mains hum is a *comb*: the fundamental AND several harmonics
    of the SAME family all stand above the local floor together. Requiring >=3
    harmonics of one family to each exceed the floor (and reporting their median
    excess) rejects musical bass, which never lights up the whole comb.
    """
    f, psd_db = c.psd_freqs, c.psd_db
    best = 0.0
    for mains in (50, 60):
        excesses = []
        for h in range(1, 6):  # fundamental + 4 harmonics
            target = mains * h
            if target >= c.sr / 2:
                break
            peak_band = (f >= target - 2) & (f <= target + 2)
            ref_band = ((f >= target - 20) & (f <= target - 6)) | \
                       ((f >= target + 6) & (f <= target + 20))
            if peak_band.any() and ref_band.any():
                excesses.append(float(psd_db[peak_band].max() - psd_db[ref_band].mean()))
        strong = [e for e in excesses if e > 3.0]
        if len(strong) >= 3:   # a genuine comb, not one stray bass bin
            best = max(best, float(np.median(strong)))
    return best


def _azimuth_lag_us(L, R, sr, max_lag_ms=2.0) -> float:
    # decimate to speed up; azimuth error is broadband so coarse is fine
    step = max(1, len(L) // 200000)
    lch, rch = L[::step], R[::step]
    eff_sr = sr / step
    max_lag = int(max_lag_ms * 1e-3 * eff_sr)
    if max_lag < 1 or len(lch) < 2 * max_lag:
        return 0.0
    lch = (lch - lch.mean()) / (lch.std() + 1e-12)
    rch = (rch - rch.mean()) / (rch.std() + 1e-12)
    # cross-correlation over ±max_lag
    corr = np.correlate(lch[max_lag:-max_lag], rch, mode="valid")
    lag = int(np.argmax(corr) - max_lag)
    return abs(lag) / eff_sr * 1e6  # microseconds


def _lossy_brickwall(p: NativeProbe) -> float:
    f, db = p.psd_freqs, p.psd_db
    # candidate MP3/AAC cutoffs
    for cut in (16000, 19000, 20000, 15000):
        if cut + 2000 > p.nyquist_hz:
            continue
        below = (f >= cut - 2000) & (f < cut)
        above = (f >= cut) & (f < cut + 2000)
        if below.any() and above.any():
            drop = float(db[below].mean() - db[above].mean())
            # a brick wall is a large, sharp drop across a narrow band
            if drop > 25:
                return 1.0
    return 0.0
