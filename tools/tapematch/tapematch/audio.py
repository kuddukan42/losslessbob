"""Audio IO and DSP helpers built on soundfile + scipy."""
from __future__ import annotations
import json
import subprocess
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from math import gcd


def _ffprobe_info(path: str) -> dict:
    """Return {channels, samplerate, duration} for formats soundfile can't read.

    SHN and some other formats carry no frame-count header, so duration is
    obtained by decoding to null and reading the final stats time stamp.
    """
    import re
    r = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "a:0",
         "-show_entries", "stream=channels,sample_rate:format=duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(r.stdout)
    stream = data["streams"][0]
    channels = int(stream["channels"])
    samplerate = int(stream["sample_rate"])

    raw_dur = data.get("format", {}).get("duration")
    if raw_dur:
        duration = float(raw_dur)
    else:
        # No header duration (e.g. SHN): measure by decoding to null
        r2 = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-stats", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        m = re.search(r"time=(\d+):(\d+):([\d.]+)", r2.stderr)
        if not m:
            raise RuntimeError(f"could not determine duration for {path!r}")
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))

    return {"channels": channels, "samplerate": samplerate, "duration": duration}


def _ffmpeg_load(path: str, target_sr: int, mono: bool = False):
    """Decode + resample via ffmpeg pipe. Returns (samples (n,ch), sr)."""
    channels = _ffprobe_info(path)["channels"]
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-f", "f32le", "-ar", str(target_sr), "-ac", str(channels), "pipe:1"],
        capture_output=True, check=True,
    )
    x = np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, channels)
    if mono and channels > 1:
        x = x.mean(axis=1, keepdims=True)
    return x, target_sr


def load(path, target_sr, mono=False):
    """Load an audio file at native rate, resample to target_sr.
    Returns (samples, sr). samples shape: (n,) mono or (n, ch) stereo."""
    try:
        x, sr = sf.read(str(path), always_2d=True, dtype="float32")  # (n, ch)
    except sf.LibsndfileError:
        return _ffmpeg_load(str(path), target_sr, mono)
    if sr != target_sr:
        g = gcd(sr, target_sr)
        up, down = target_sr // g, sr // g
        x = resample_poly(x, up, down, axis=0).astype("float32")
        sr = target_sr
    if mono and x.shape[1] > 1:
        x = x.mean(axis=1, keepdims=True)
    return x, sr


def to_mono(x):
    return x.mean(axis=1) if x.ndim == 2 and x.shape[1] > 1 else x.reshape(-1)


def duration_sec(path):
    try:
        info = sf.info(str(path))
        return info.frames / info.samplerate
    except sf.LibsndfileError:
        return _ffprobe_info(str(path))["duration"]


def resample_ratio(x, ratio):
    """Resample x by `ratio` (output_len ≈ len*ratio) to correct a speed offset.
    ratio>1 stretches (was running fast), ratio<1 compresses."""
    # rational approximation of ratio
    from fractions import Fraction
    frac = Fraction(ratio).limit_denominator(100000)
    return resample_poly(x, frac.numerator, frac.denominator, axis=0).astype("float32")
