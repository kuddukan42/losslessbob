"""Generate a synthetic 5-source scenario and run the pipeline end-to-end.

Lineage truth:
  src_A  = independent audience capture #1   (own noise floor + reverb)
  src_B  = independent audience capture #2   (different noise + reverb)
  src_C  = clone of A, re-tracked + different head/tail padding
  src_D  = clone of A, +0.30% speed offset (analog dub) + re-padded
  src_E  = EQ child of B (high-shelf boost)
Expected clustering:  {A, C, D}  and  {B, E}
"""
import sys, shutil
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, lfilter

SR = 16000
RNG = np.random.default_rng(7)


def make_performance(dur_sec=90):
    """Structured, music-like shared signal (the invariant)."""
    n = int(dur_sec * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    # several 'songs' with partials and amplitude envelopes
    for k, (f0, a, s, e) in enumerate([
        (110, 0.6, 2, 22), (147, 0.5, 24, 46),
        (98, 0.55, 48, 70), (165, 0.5, 72, 88)]):
        env = ((t > s) & (t < e)).astype(float)
        # smooth the envelope edges
        env = lfilter(np.ones(SR)/SR, 1, env)
        for h, amp in enumerate([1, 0.5, 0.3, 0.2], start=1):
            sig += a * amp * env * np.sin(2*np.pi*f0*h*t + 0.1*h)
    # broadband percussion -> sharp shared transients (real audio has these;
    # makes cross-correlation unimodal instead of a tonal comb)
    drng = np.random.default_rng(99)
    beat = int(0.5 * SR)
    for pos in range(int(2*SR), int(88*SR), beat):
        hit = drng.normal(0, 1, 1200) * np.exp(-np.arange(1200)/120)
        sig[pos:pos+1200] += 0.4 * hit
    return sig.astype("float32")


def add_capture(perf, noise_seed, reverb_ms, crowd_seed):
    """Simulate one independent audience capture: shared perf + unique noise,
    room reverb, and crowd transients with this taper's own timing."""
    rng = np.random.default_rng(noise_seed)
    n = len(perf)
    noise = rng.normal(0, 0.02, n).astype("float32")        # unique noise floor
    # simple reverb: short exponential IR, unique per position
    ir_n = int(reverb_ms/1000*SR)
    ir = np.exp(-np.arange(ir_n)/(0.3*ir_n)) * rng.normal(0, 1, ir_n)
    ir[0] = 1.0
    wet = lfilter(ir, 1, perf)[:n]
    crowd = _crowd(n, crowd_seed)
    mix = 0.7*perf + 0.3*wet + noise + crowd
    return (mix / (np.max(np.abs(mix))+1e-6) * 0.9).astype("float32")


def _crowd(n, seed):
    rng = np.random.default_rng(seed)
    c = np.zeros(n)
    for _ in range(40):                                     # claps/yells
        pos = rng.integers(0, n-2000)
        burst = rng.normal(0, 0.3, 1500) * np.exp(-np.arange(1500)/300)
        c[pos:pos+1500] += burst
    return c.astype("float32")


def pad(x, head_sec, tail_sec, seed):
    rng = np.random.default_rng(seed)
    h = rng.normal(0, 0.05, int(head_sec*SR)).astype("float32")  # crowd padding
    tl = rng.normal(0, 0.05, int(tail_sec*SR)).astype("float32")
    return np.concatenate([h, x, tl])


def write_tracks(stream, outdir, n_tracks, nested=False, seed=0):
    """Cut stream into n_tracks with non-standard names; optionally d1/d2."""
    outdir.mkdir(parents=True, exist_ok=True)
    cuts = np.linspace(0, len(stream), n_tracks+1).astype(int)
    names = ["opener", "song two", "the-third", "jam", "encore", "outro",
             "intro2", "tuneup", "ballad", "closer"]
    for i in range(n_tracks):
        seg = stream[cuts[i]:cuts[i+1]]
        nm = f"{i+1:02d} {names[i % len(names)]}.flac"
        if nested:
            sub = outdir / ("d1" if i < n_tracks//2 else "d2")
            sub.mkdir(exist_ok=True)
            sf.write(sub / nm, seg, SR)
        else:
            sf.write(outdir / nm, seg, SR)


def build(root):
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    perf = make_performance()

    A = add_capture(perf, noise_seed=1, reverb_ms=80, crowd_seed=11)
    B = add_capture(perf, noise_seed=2, reverb_ms=140, crowd_seed=22)

    # C: clone of A, different tracking + padding
    C = A.copy()
    # D: clone of A with +0.30% speed (resample), re-padded
    D = resample_poly(A, 1000, 1003).astype("float32")
    # E: EQ child of B -- high shelf boost
    E = lfilter([1.6, -0.6], [1.0], B).astype("float32")
    E = (E / (np.max(np.abs(E))+1e-6) * 0.9).astype("float32")

    write_tracks(pad(A, 12, 25, 100), root/"src_A", 5, nested=False)
    write_tracks(pad(B, 30, 8, 200),  root/"src_B", 6, nested=True)
    write_tracks(pad(C, 5, 40, 300),  root/"src_C", 4, nested=False)
    write_tracks(pad(D, 18, 15, 400), root/"src_D", 5, nested=True)
    write_tracks(pad(E, 22, 20, 500), root/"src_E", 6, nested=False)
    print(f"built synthetic scenario at {root}")
    print("truth: {A,C,D} share source; {B,E} share source (E=EQ child of B)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/processing")
