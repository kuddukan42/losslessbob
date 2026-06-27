"""Feature extractors. Every function takes a pre-built cache and returns a flat
dict of RAW metric values (the things stored in the DB). No decoding, no STFT —
that already happened once in cache.py. Banding/scoring happens later, from the
stored raw values, so thresholds can change without rescanning.

Families:
  clarity   — presence, directness (distance/reverberance), onset clarity
  crowd     — crowd SNR (the big AUD number), intrusion + handling event rates
  tonal     — bass/air/mud/harsh/sibilance balance
  distortion— clipping, crest factor, dropouts, hum, brickwall, single-ch hits
  spatial   — L-R correlation, width, channel balance, azimuth (inter-channel lag)
  hf_native — hiss, air, HF ceiling, lossy, mini-disc, 32k DAT, cassette, TV band
  text      — curator description flaw vocabulary (DB-side, no audio needed)
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

    # Speech-band SNR: 1-4 kHz intelligibility band during loud (music) frames
    # vs quiet (crowd/noise) frames. Captures whether vocals are audible above
    # the noise floor in the range that drives perceived vocal clarity.
    # Validated against commentary labels; unlike presence_ratio_db this is
    # SNR-based (not a spectral ratio), so it tracks muffled/distant labeling.
    sp_lo, sp_hi = _b("presence")
    sp_mask = (c.freqs >= sp_lo) & (c.freqs < sp_hi)
    sp_mag = c.stft_mag[sp_mask, :]
    sp_db = 10 * np.log10((sp_mag ** 2).sum(axis=0) + 1e-12)
    quiet = c.quiet_frame_mask(20.0)
    loud = ~quiet
    sp_music = float(np.median(sp_db[loud])) if loud.any() else float("nan")
    sp_floor = float(np.median(sp_db[quiet])) if quiet.any() else float("nan")
    speech_band_snr = sp_music - sp_floor

    return {
        "presence_ratio_db": presence_ratio,
        "directness": directness,
        "onset_clarity": onset_clarity,
        "speech_band_snr_db": speech_band_snr,
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
    dropout_count = _dropout_count(c)

    # mains hum: narrowband excess at 50/60 Hz harmonics vs local floor.
    hum_excess = _hum_excess_db(c)

    # hiss: HF noise persistence, de-confounded from musical brightness (see helper)
    hiss_floor = _hiss_floor_db(c)

    brickwall = _brickwall_score(c)
    single_ch = _single_channel_transient_count(c)

    return {
        "clip_fraction": clip_fraction,
        "crest_factor_db": float(crest_db),
        "dropout_count": dropout_count,
        "hum_excess_db": hum_excess,
        "hiss_floor_db": hiss_floor,
        "brickwall_score": brickwall,
        "single_ch_transient_count": single_ch,
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

    # Source-type HF signatures (TODO-189, TODO-190)
    minidisc = _minidisc_parapet_score(p)
    dat32k = _32k_dat_flag(p)
    cassette = _cassette_rolloff_flag(p)
    tv_band = _tv_band_flag(p)

    return {
        "air_ratio_db": air_ratio,
        "hf_ceiling_hz": ceiling,
        "lossy_flag": lossy,
        "minidisc_score": minidisc,
        "dat32k_flag": dat32k,
        "cassette_flag": cassette,
        "tv_band_flag": tv_band,
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


def _dropout_count(c: TrackCache) -> int:
    """Count true digital dropouts: silence gaps, stuck samples, and digipops.

    The previous locally-normalized roughness approach measured musical transient
    density — better recordings with sharper attacks scored *higher* (rho=+0.417
    on 2798 AUD, disabled 2026-06-25). Three defect signatures modelled on
    DigiFlawFinder (sffog.com) — a tool validated across thousands of DAT transfers:

    1. Silence gaps (DFF "Drops"): a very short (<500 ms) near-zero segment
       inside loud audio — CD read errors, buffer underruns, tape drop-outs.
    2. Stuck samples (DFF "Horizontals"): 5+ consecutive identical float values
       — a frozen digital buffer; impossible in naturally-flowing audio.
    3. Digipops (DFF "Verticals"): a single-sample anomaly that creates exactly
       two consecutive large first-differences of similar magnitude — the jump IN
       and the jump OUT of the bad sample. A musical transient only jumps in one
       direction, producing an asymmetric pair; requiring symmetry (min/max > 0.5)
       rejects sharp attacks while catching genuine single-sample defects.
    """
    x = c.mono
    sr = c.sr
    n = len(x)
    frame = max(64, sr // 200)            # ~5 ms at 22050 Hz
    if n < frame * 6:
        return 0

    # ── Silence gap detection ─────────────────────────────────────────────────
    n_f = n // frame
    rms = np.sqrt((x[:n_f * frame].reshape(n_f, frame) ** 2).mean(axis=1))

    nz = rms[rms > 1e-8]
    if len(nz) == 0:
        return 0
    med = float(np.median(nz))
    silent_thresh = med * 0.01            # < 1% of median RMS
    loud_thresh = med * 0.10             # > 10% of median RMS
    max_gap_frames = max(2, int(0.5 * sr / frame))   # 500 ms cap

    silent = rms < silent_thresh
    loud = rms > loud_thresh
    count = 0
    i = 1                                 # skip frame 0 (no left flank possible)
    while i < n_f:
        if silent[i]:
            j = i
            while j < n_f and silent[j]:
                j += 1
            length = j - i
            if length <= max_gap_frames:
                left_loud = loud[max(0, i - 3):i].any()
                right_loud = loud[j:min(n_f, j + 3)].any()
                if left_loud and right_loud:
                    count += 1
            i = j
        else:
            i += 1

    # ── Stuck sample detection ────────────────────────────────────────────────
    # diff == 0.0 exactly means consecutive identical PCM values. Require >= 4
    # consecutive zeros (5+ identical samples) — physically impossible in
    # band-limited flowing audio. Two gates prevent false positives:
    # (a) the surrounding frame must be loud (rules out intentional silence);
    # (b) the stuck value must be non-trivial (rules out a run frozen at 0.0,
    #     which is indistinguishable from a long fade-out or pre-roll silence).
    d = np.diff(x)
    is_zero = d == 0.0
    if is_zero.any():
        edges = np.diff(is_zero.view(np.int8))
        starts = np.flatnonzero(edges == 1) + 1
        ends = np.flatnonzero(edges == -1) + 1
        if is_zero[0]:
            starts = np.r_[0, starts]
        if is_zero[-1]:
            ends = np.r_[ends, len(is_zero)]
        long_runs = (ends - starts) >= 4
        if long_runs.any():
            run_starts = starts[long_runs]
            fi = np.clip(run_starts // frame, 0, n_f - 1)
            stuck_val = np.abs(x[run_starts])
            in_loud_context = loud[fi]
            non_trivial = stuck_val > loud_thresh
            count += int((in_loud_context & non_trivial).sum())

    # ── Digipop / vertical detection (DFF "Verticals") ───────────────────────
    # A single bad sample creates exactly two consecutive large first-differences:
    # the jump IN and the jump OUT — both roughly equal in magnitude. A musical
    # transient only has one large jump (the attack) then a smaller decay step,
    # so the pair is asymmetric. Gate: both diffs must exceed 0.10, width == 2,
    # and min/max ratio > 0.5 (symmetric pair), in a loud frame.
    d_abs = np.abs(d)
    big_v = d_abs > 0.10
    if big_v.any():
        edges_v = np.diff(big_v.view(np.int8))
        sv = np.flatnonzero(edges_v == 1) + 1
        ev = np.flatnonzero(edges_v == -1) + 1
        if big_v[0]:
            sv = np.r_[0, sv]
        if big_v[-1]:
            ev = np.r_[ev, len(big_v)]
        exact_two = (ev - sv) == 2
        if exact_two.any():
            rs = sv[exact_two]
            d1 = d_abs[rs]
            d2 = d_abs[rs + 1]
            symmetric = np.minimum(d1, d2) > 0.5 * np.maximum(d1, d2)
            if symmetric.any():
                fi_v = np.clip(rs[symmetric] // frame, 0, n_f - 1)
                count += int(loud[fi_v].sum())

    return count


def _hum_excess_db(c: TrackCache) -> float:
    """Mains hum as a HARMONIC COMB at 50- or 60-Hz multiples, not a lone peak.

    Previous v1 (single-peak): tracked bass energy (rose WITH rating — confounded).
    Previous v2 (comb, ≥3 harmonics): still confounded at +0.117 rho because the
    shared Welch PSD uses nperseg=4096 → Δf≈5.4 Hz. At that resolution, G1 bass
    (49 Hz) and 50 Hz mains share the same bin; the 100 Hz and 250 Hz harmonic
    windows are empty (no bin within ±2 Hz). Fix: dedicated high-res Welch
    (nperseg = sr×2 → Δf=0.5 Hz) with a ±0.5 Hz peak window — tight enough to
    separate 49 Hz bass from 50 Hz mains and reliably land in every harmonic bin.
    """
    from scipy.signal import welch as _welch
    x = c.mono
    sr = c.sr
    # 2-second segments → 0.5 Hz resolution; long enough for stable low-frequency
    # estimates while staying tractable even for short tracks.
    nperseg = min(len(x), sr * 2)
    if nperseg < sr // 2:          # track too short for reliable low-freq PSD
        return 0.0
    f, psd = _welch(x, fs=sr, nperseg=nperseg)
    psd_db = 10.0 * np.log10(psd + 1e-12)

    best = 0.0
    for mains in (50, 60):
        excesses = []
        for h in range(1, 8):      # fundamental + 6 harmonics (more votes = more robust)
            target = mains * h
            if target >= sr / 2:
                break
            # ±0.5 Hz: catches exactly the harmonic bin, rejects adjacent bass notes
            peak_band = (f >= target - 0.5) & (f <= target + 0.5)
            ref_band = ((f >= target - 20) & (f <= target - 3)) | \
                       ((f >= target + 3)  & (f <= target + 20))
            if peak_band.any() and ref_band.any():
                excesses.append(float(psd_db[peak_band].max() - psd_db[ref_band].mean()))
        strong = [e for e in excesses if e > 3.0]
        if len(strong) >= 3:       # genuine comb: ≥3 harmonics each >3 dB above local floor
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


def _brickwall_score(c: TrackCache) -> float:
    """Detect pre-amp brickwall saturation via mid-amplitude slope regularity.

    Brickwalled audio shows smooth diagonal/curved ramps connecting waveform
    peaks — the hardware continuously loses detail, not just at the peak.
    Natural music maintains rapid slope variation at any amplitude level (many
    frequency components crossing simultaneously). Brickwalled audio has very
    low slope variance in mid-amplitude regions but retains natural complexity
    at the peaks.

    The reference is the slope variance in LOUD frames (near the waveform peaks),
    where even brickwalled audio retains its natural character. If loud frames
    themselves have near-zero slope variance, the signal is too simple to measure
    (e.g. pure tone), and 0.0 is returned rather than a spurious score.

    Score: 1.0 = brickwall-like (smooth between-peak ramps), 0.0 = natural.
    """
    x = c.mono
    sr = c.sr
    n = len(x)
    frame = max(64, sr // 100)   # ~10 ms at 22050 Hz
    n_f = n // frame
    if n_f < 20:
        return 0.0

    xf = x[:n_f * frame].reshape(n_f, frame)
    env = np.abs(xf).max(axis=1)
    peak = float(env.max())
    if peak < 1e-4:
        return 0.0

    # First-difference slope variance per frame, normalized by envelope²
    # so the measure is shape (not loudness): a diagonal ramp → variance ≈ 0.
    d = np.diff(xf, axis=1)         # shape (n_f, frame-1)
    slope_var = d.var(axis=1)
    env_sq = env ** 2 + 1e-12
    nsv = slope_var / env_sq        # normalized slope variance

    # Mid-amp frames: the between-peak region where brickwall's smooth ramps live
    # Loud frames: the waveform peaks, which retain natural complexity even in
    # brickwalled audio and serve as the reference for "what complex looks like"
    mid_mask = (env >= 0.20 * peak) & (env <= 0.75 * peak)
    loud_mask = env >= 0.75 * peak

    if mid_mask.sum() < 5 or loud_mask.sum() < 5:
        return 0.0

    nsv_mid = float(np.median(nsv[mid_mask]))
    nsv_loud = float(np.median(nsv[loud_mask]))

    # Simple signals (pure tone, triangle wave) have near-zero nsv even at
    # peaks — not a brickwall, just a simple waveform. Return 0 to avoid
    # spurious scores.
    if nsv_loud < 1e-10:
        return 0.0

    # Natural: nsv_mid ≈ nsv_loud (complex everywhere)
    # Brickwalled: nsv_mid << nsv_loud (smooth ramps, complex peaks)
    ratio = nsv_mid / nsv_loud
    return float(max(0.0, min(1.0, 1.0 - ratio)))


def _single_channel_transient_count(c: TrackCache) -> int:
    """Count large transients that appear on ONE channel only (mic hits).

    A microphone cable hit or bump touches only one channel of the recording —
    the shock travels through one L or R cable. The visual signature (lb_mic_hit.JPG)
    shows a sharp spike only on one channel while the other remains flat.
    Detects frames where one channel spikes to > 30% of peak while the other
    stays at < 10% of that spike — physically impossible for music (which is
    inherently correlated at the preamp). Returns 0 for mono recordings.
    """
    if not c.is_stereo:
        return 0
    L, R = c.left, c.right
    n = min(len(L), len(R))
    if n < 1000:
        return 0
    L, R = L[:n], R[:n]

    frame = max(64, c.sr // 200)   # ~5 ms at 22050 Hz
    n_f = n // frame
    if n_f < 4:
        return 0
    L_f = np.abs(L[:n_f * frame].reshape(n_f, frame)).max(axis=1)
    R_f = np.abs(R[:n_f * frame].reshape(n_f, frame)).max(axis=1)

    overall_peak = max(float(L_f.max()), float(R_f.max()))
    if overall_peak < 1e-4:
        return 0

    ch_max = np.maximum(L_f, R_f)
    ch_min = np.minimum(L_f, R_f)

    # Spike: one channel dominates (≥ 2× the other) and the bigger channel
    # exceeds 30% of the track peak (i.e. it's a real signal, not noise).
    # A clean stereo signal has ch_min/ch_max ≥ ~0.80 (channels within 20%
    # of each other); threshold 0.50 gives a comfortable safety margin.
    is_spike = (ch_max > 0.30 * overall_peak) & (ch_min < 0.50 * ch_max)

    if not is_spike.any():
        return 0

    # Count isolated events; require > 10-frame gap to avoid counting one hit
    # multiple times across adjacent frames
    spike_idx = np.flatnonzero(is_spike)
    count = 0
    last = -20
    for fi in spike_idx:
        if fi - last > 10:
            count += 1
            last = int(fi)
    return count


def _minidisc_parapet_score(p: NativeProbe) -> float:
    """Estimate mini-disc encoding probability from the averaged native-rate PSD.

    The ATRAC codec alternates its cutoff (e.g. 16 kHz → 17 kHz → 16 kHz) on
    consecutive encoder frames, leaving a characteristic "shoulder" in the
    averaged PSD: the 15–17 kHz region is partially filled (each cutoff-step
    contributes to the average) while above 17 kHz is empty. This creates a
    stepped, irregular ceiling shape rather than the smooth gradual rolloff
    of cassette or the perfectly clean wall of 32k DAT.

    Score: 0.0 = not mini-disc, 1.0 = strong mini-disc signature.
    Note: detection is approximate from the averaged PSD; a per-frame STFT
    would see the alternating steps more clearly but requires a separate pass.
    """
    f, db = p.psd_freqs, p.psd_db
    if not f.size or p.nyquist_hz < 17000:
        return 0.0

    floor_db = float(np.percentile(db, 15))
    ref_db = float(p.band_db(1000, 14000))  # broadband signal reference

    # The MD shoulder: energy clearly present in 15-16 kHz (not a clean wall
    # at 16k like 32k DAT) but mostly gone above 17 kHz
    e_15_16 = p.band_db(15000, 16000)
    e_16_17 = p.band_db(16000, 17000)
    e_17_19 = p.band_db(17000, 19000)

    if any(v is None or (isinstance(v, float) and np.isnan(v))
           for v in (e_15_16, e_16_17, e_17_19)):
        return 0.0

    # Shoulder must be significantly below broadband but above noise floor
    shoulder_15 = e_15_16 - ref_db
    shoulder_16 = e_16_17 - ref_db
    above_level = e_17_19 - floor_db

    # Mini-disc signature: partial energy in 15-17k, empty above 17k
    # The -4 / -14 window captures the "faded" shoulder (not a clean wall,
    # not full-bandwidth), and > 17k must be at or near the noise floor.
    in_shoulder_range = (-15 < shoulder_15 < -3) or (-15 < shoulder_16 < -3)
    above_empty = above_level < 5.0

    # Also check the alternating roughness: if 15-16k is substantially
    # different from 16-17k (>6 dB step), the alternating pattern is visible
    alternation = abs(e_15_16 - e_16_17) > 6.0

    if in_shoulder_range and above_empty and alternation:
        return 1.0
    if in_shoulder_range and above_empty:
        return 0.5
    return 0.0


def _32k_dat_flag(p: NativeProbe) -> float:
    """Detect 32 kHz DAT recordings: clean Nyquist wall at exactly 16 kHz.

    The most unambiguous HF signature: perfectly horizontal cutoff at 16 kHz
    with essentially zero energy above, and rich full content below. Unlike
    mini-disc (stepped ceiling) or cassette (gradual slope), this is a hard
    wall — the Nyquist filter of a 32 kHz sample rate.
    """
    f, db = p.psd_freqs, p.psd_db
    if not f.size or p.nyquist_hz < 18000:
        return 0.0  # native rate must be at least 36 kHz to see 16k wall

    floor_db = float(np.percentile(db, 15))
    e_below = p.band_db(12000, 16000)   # should be strong
    e_above = p.band_db(16000, 20000)   # should be at noise floor

    if any(v is None or (isinstance(v, float) and np.isnan(v))
           for v in (e_below, e_above)):
        return 0.0

    drop = e_below - e_above
    above_floor = e_above - floor_db

    # 32k DAT: large drop across the 16k boundary AND above is at noise floor
    # Require >30 dB drop (sharper than cassette ~10-15 dB, and sharper than MP3
    # which often has some leakage). The above-floor gate (<4 dB) confirms empty.
    if drop > 30 and above_floor < 4.0:
        # Extra check: content below 16k must be rich (not just bass)
        e_mid_hf = p.band_db(10000, 15000)
        ref = p.band_db(1000, 8000)
        if e_mid_hf is not None and ref is not None:
            mid_hf_relative = e_mid_hf - ref
            # Mid-HF should not be dramatically weaker than broadband (would
            # indicate already-rolled-off source, not a hard Nyquist wall)
            if mid_hf_relative > -20:
                return 1.0
    return 0.0


def _cassette_rolloff_flag(p: NativeProbe) -> float:
    """Detect cassette tape transfers by gradual HF rolloff above ~17-18 kHz.

    Cassette tape: energy present at 17-18 kHz (it extends to ~20 kHz but with
    increasing hiss/noise above ~18k). The rolloff is GRADUAL (tapers from full
    energy to nothing across 3-5 kHz), contrasting with the hard Nyquist wall
    of 32k DAT or the stepped ceiling of mini-disc.

    Also checks that the HF ceiling is in the cassette range (17-19k) without
    a lossy-brickwall flag (so we don't confuse MP3 rolloff with cassette).
    """
    f, db = p.psd_freqs, p.psd_db
    if not f.size or p.nyquist_hz < 20000:
        return 0.0

    floor_db = float(np.percentile(db, 15))

    e_15_17 = p.band_db(15000, 17000)
    e_17_18 = p.band_db(17000, 18000)
    e_18_20 = p.band_db(18000, 20000)

    if any(v is None or (isinstance(v, float) and np.isnan(v))
           for v in (e_15_17, e_17_18, e_18_20)):
        return 0.0

    # Gradual slope: 15-17k → 17-18k should decrease noticeably but not sharply
    slope_low = e_15_17 - e_17_18   # moderate drop (5-20 dB = tape rolloff)
    slope_high = e_17_18 - e_18_20  # further drop above 18k
    above_floor = e_18_20 - floor_db  # 18-20k: tape noise, not music

    # Cassette signature:
    # - 15-17k present (above floor + 5 dB)
    # - gradual rolloff (5-20 dB from 15-17k to 17-18k)
    # - 18-20k near or slightly above noise floor (tape hiss, not music)
    # - NOT a sharp wall (that would be 32k DAT or lossy)
    has_content_below = (e_15_17 - floor_db) > 5.0
    gradual_mid_slope = 5 < slope_low < 25
    gentle_high_slope = 0 < slope_high < 20
    above_is_noisy = -2 < above_floor < 12  # some signal but not full-strength

    if has_content_below and gradual_mid_slope and gentle_high_slope and above_is_noisy:
        return 1.0
    return 0.0


def _tv_band_flag(p: NativeProbe) -> float:
    """Detect CRT TV/monitor band: pulsing narrow stripe near 15.6 kHz.

    When an analog source is captured near a CRT monitor, the cathode-ray tube
    emits at its horizontal scan frequency (~15.6 kHz PAL / ~15.75 kHz NTSC),
    recording as a thin bright band in the spectrogram. The LB site notes it
    "cannot be heard by most people" — it is informational, NOT a quality
    degrader, and should be kept separate from hiss detection.

    Two signatures: (1) a narrow elevated peak at 14.5-16.5 kHz in the averaged
    PSD (above its neighbors by ≥ 6 dB), and (2) high variance of that peak
    across the sampled windows (it pulses in/out of brightness, unlike steady
    hiss or a fixed tone which would have low variance).
    """
    f, db = p.psd_freqs, p.psd_db
    if not f.size or p.nyquist_hz < 15000:
        return 0.0

    tv_mask = (f >= 14500) & (f < 16500)
    lo_mask = (f >= 13000) & (f < 14500)
    hi_mask = (f >= 16500) & (f < 18000)

    if not (tv_mask.any() and lo_mask.any() and hi_mask.any()):
        return 0.0

    tv_peak = float(db[tv_mask].max())
    neighbor_mean = float(0.5 * (db[lo_mask].mean() + db[hi_mask].mean()))
    elevation = tv_peak - neighbor_mean

    if elevation < 6.0:
        return 0.0  # not elevated enough to be a distinct band

    # Check pulsing using per-window PSDs: TV band pulses in/out, unlike
    # steady hiss (low variance) or full-band music content.
    if p.window_psds_db is not None and p.window_psds_db.shape[0] >= 3:
        win_tv = p.window_psds_db[:, tv_mask].max(axis=1)  # per-window peak
        win_lo = p.window_psds_db[:, lo_mask].mean(axis=1)
        # Elevation relative to lower-neighbor per window
        win_elev = win_tv - win_lo
        tv_variance = float(np.std(win_elev))
        # Pulsing TV band: std across windows ≥ 2 dB (it varies noticeably);
        # steady hiss or a music peak is much more consistent
        if tv_variance < 2.0:
            return 0.0

    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# TEXT FEATURES  (DB-side; no audio — called at calibration / rerank time)
# ─────────────────────────────────────────────────────────────────────────────

def extract_text(description: str | None) -> dict:
    """Flaw-vocabulary features from a LB description string.

    Thin wrapper around :mod:`concert_ranker.text_features` so all feature
    extraction can be called through the same ``features`` module. The returned
    dict has the same keys as :data:`text_features.TEXT_FEATURE_KEYS`.
    """
    from .text_features import extract_text_features
    return extract_text_features(description)
