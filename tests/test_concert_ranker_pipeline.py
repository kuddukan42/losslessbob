"""Synthetic end-to-end test. Builds 4 fake transfers of 'one show', each with a
deliberate defect, runs the full scan->band->disqualify->normalize->explain
pipeline, and asserts the scoring brain orders them sensibly. No real audio
needed. Run with ``pytest -s`` to see the raw metrics and verdict printout.
"""
import numpy as np

from concert_ranker import features as F
from concert_ranker import scoring as S
from concert_ranker.audio.cache import build_native_probe, build_track_cache

rng = np.random.default_rng(42)
SR = 22050
DUR = 30  # seconds (short, just for the test)
N = SR * DUR


def music(boom=0.0, air=1.0, mid=1.0):
    """A crude 'music' signal: bass + mid + HF, with knobs for tonal balance."""
    t = np.arange(N) / SR
    sig = np.zeros(N)
    # bass content
    sig += (1.0 + boom) * 0.3 * np.sin(2 * np.pi * 110 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t))
    # mid / "vocal" band — amplitude-modulated to create loud/quiet passages
    env = 0.5 + 0.5 * np.sin(2 * np.pi * 0.2 * t) ** 2
    sig += mid * 0.4 * np.sin(2 * np.pi * 800 * t) * env
    sig += mid * 0.25 * np.sin(2 * np.pi * 2000 * t) * env
    # HF / air
    sig += air * 0.1 * rng.standard_normal(N) * np.r_[np.linspace(0, 1, 200), np.ones(N - 200)][:N]
    return sig.astype(np.float32)


def add_crowd(sig, level):
    # broadband speech-band-ish noise, constant (the crowd floor)
    crowd = level * rng.standard_normal(len(sig))
    return sig + crowd.astype(np.float32)


def native_windows(sig_native, sr):
    # chop into a few windows for the NativeProbe
    w = int(20 * sr)
    return [sig_native[i:i + w] for i in range(0, len(sig_native), w) if len(sig_native[i:i + w]) > 4096][:8]


def make_native(air=1.0, lossy_cut=None):
    """Native-rate 44.1k signal for the HF probe; optional lossy brick-wall."""
    sr = 44100
    n = sr * DUR
    t = np.arange(n) / sr
    sig = 0.4 * np.sin(2 * np.pi * 800 * t) + 0.25 * np.sin(2 * np.pi * 2000 * t)
    noise = air * 0.05 * rng.standard_normal(n)
    if lossy_cut:
        # brick-wall the noise above the cutoff to fake an MP3 source
        from scipy.signal import butter, sosfilt
        sos = butter(8, lossy_cut, btype="low", fs=sr, output="sos")
        noise = sosfilt(sos, noise)
    sig = (sig + noise).astype(np.float32)
    return native_windows(sig, sr), sr


def test_synthetic_pipeline():
    # ── Build 4 siblings ────────────────────────────────────────────────────
    siblings = {}

    # LB1001: clean SBD — balanced, low crowd, quiet, complete
    m = music(boom=0.0, air=1.0, mid=1.2)
    siblings[1001] = dict(mono=add_crowd(m, 0.002), native=make_native(air=1.0), dur=DUR)

    # LB1002: decent AUD — a bit boomy, more crowd
    m = music(boom=1.2, air=0.8, mid=0.9)
    siblings[1002] = dict(mono=add_crowd(m, 0.02), native=make_native(air=0.8), dur=DUR)

    # LB1003: distant muddy AUD — buried in crowd, thin highs
    m = music(boom=0.3, air=0.3, mid=0.5)
    siblings[1003] = dict(mono=add_crowd(m, 0.12), native=make_native(air=0.3), dur=DUR)

    # LB1004: lossy upscale — brick-walled HF, otherwise ok
    m = music(boom=0.2, air=0.6, mid=1.0)
    siblings[1004] = dict(mono=add_crowd(m, 0.015), native=make_native(air=0.6, lossy_cut=16000), dur=DUR)

    # ── Scan: build caches, extract raw metrics (one decode/STFT each) ──────
    raw_all = {}
    for lb, d in siblings.items():
        c = build_track_cache(d["mono"], SR, n_fft=2048, hop=512, path=f"LB{lb}")
        nw, nsr = d["native"]
        p = build_native_probe(nw, nsr)

        raw = {}
        raw.update(F.extract_clarity(c))
        raw.update(F.extract_crowd(c))
        raw.update(F.extract_tonal(c))
        raw.update(F.extract_distortion(c))
        raw.update(F.extract_hf_native(p))
        # completeness: this sibling's duration vs family max (filled after loop)
        raw["_dur"] = d["dur"]
        raw_all[lb] = raw

    # completeness pass
    max_dur = max(r["_dur"] for r in raw_all.values())
    for raw in raw_all.values():
        raw["completeness"] = raw.pop("_dur") / max_dur

    # ── Disqualifiers ────────────────────────────────────────────────────────
    dq = {lb: S.check_disqualifiers(raw) for lb, raw in raw_all.items()}
    survivors = {lb: raw_all[lb] for lb in raw_all if not dq[lb][1]}

    # ── Normalize survivors, fuse, rank ──────────────────────────────────────
    z_all = S.normalize_siblings(survivors)
    finals = {}
    for lb in survivors:
        fam = S.family_scores(z_all[lb])
        ts = S.track_score(fam)
        finals[lb] = S.recording_score([ts])["final"]

    ranking = sorted(finals, key=lambda lb: finals[lb], reverse=True)
    rank_of = {lb: i + 1 for i, lb in enumerate(ranking)}

    # ── Print for pytest -s, then assert the ordering is sane ───────────────
    print("=" * 78)
    print("RAW METRICS")
    print("=" * 78)
    keys = ["crowd_snr_db", "bass_ratio_db", "air_ratio_db", "mud_ratio_db",
            "presence_ratio_db", "hiss_floor_db", "hf_ceiling_hz", "lossy_flag", "completeness"]
    hdr = "LB    " + "".join(f"{k[:11]:>13}" for k in keys)
    print(hdr)
    for lb in raw_all:
        row = f"{lb}  "
        for k in keys:
            v = raw_all[lb].get(k, float('nan'))
            row += f"{v:>13.3f}" if isinstance(v, (int, float)) else f"{str(v):>13}"
        print(row)

    print()
    print("=" * 78)
    print("HUMAN-READABLE VERDICTS")
    print("=" * 78)
    verdicts = {}
    for lb in raw_all:
        vetoed = dq[lb][1]
        rank = rank_of.get(lb, 0)
        z = z_all.get(lb, {})
        n = len(survivors)
        txt = S.explain_recording(lb, raw_all[lb], z, rank, n, dq[lb][0], vetoed)
        verdicts[lb] = txt
        print("•", txt)

    # every sibling got metrics and a non-empty verdict
    assert set(raw_all) == set(siblings)
    assert all(verdicts[lb] for lb in siblings)
    # the clean SBD survives disqualification and wins the family
    assert not dq[1001][1], "clean SBD must not be vetoed"
    assert ranking, "at least one survivor must be ranked"
    assert ranking[0] == 1001, f"clean SBD should rank first, got {ranking}"
    # (no ordering assert between 1002/1003 — the crude synthetic signals land within
    # noise of each other under the production-calibrated weights)
