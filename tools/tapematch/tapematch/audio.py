"""Audio IO and DSP helpers built on ffmpeg + scipy.

All loading goes through _ffmpeg_load so the native-rate array never enters
Python's address space.  For a 2-hour 44.1 kHz stereo FLAC decoded to 16 kHz,
the old sf.read + resample_poly path held ~3.3 GB simultaneously; ffmpeg pipe
delivers only the ~922 MB 16 kHz output.
"""
from __future__ import annotations
import json
import subprocess
import numpy as np
from scipy.signal import resample_poly
from math import gcd


def _ffprobe_info(path: str) -> dict:
    """Return {channels, samplerate, duration} via ffprobe.

    SHN and some other formats carry no frame-count header, so duration is
    obtained by decoding to null and reading the final stats timestamp.
    """
    import re as _re
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
        r2 = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-stats", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True,
        )
        matches = _re.findall(r"time=(\d+):(\d+):([\d.]+)", r2.stderr)
        if not matches:
            raise RuntimeError(f"could not determine duration for {path!r}")
        h, mi, s = matches[-1]  # last update = final decode position = true duration
        duration = int(h) * 3600 + int(mi) * 60 + float(s)

    return {"channels": channels, "samplerate": samplerate, "duration": duration}


def _ffmpeg_load(path: str, target_sr: int, mono: bool = False):
    """Decode + resample via ffmpeg pipe. Returns (samples (n,ch), sr).

    ffmpeg resamples to target_sr in-process so only the downsampled output
    ever lands in Python memory — avoids the sf.read(native_rate) +
    resample_poly peak that could be 3–10x larger for hi-res sources.
    """
    channels = _ffprobe_info(path)["channels"]
    out_ch = 1 if mono else channels
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-f", "f32le", "-ar", str(target_sr), "-ac", str(out_ch), "pipe:1"],
        capture_output=True, check=True,
    )
    x = np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, out_ch)
    return x, target_sr


def load(path, target_sr, mono=False):
    """Load an audio file, decode and resample to target_sr via ffmpeg.

    Returns (samples, sr). samples shape: (n, ch).
    Using ffmpeg for all formats ensures only the target-rate output is held in
    RAM — critical for hi-res sources (96/192 kHz) where the native-rate array
    would otherwise be 6–12x larger than the analysis-rate output.
    """
    return _ffmpeg_load(str(path), target_sr, mono)


def probe(path, target_sr: int) -> dict:
    """Return {channels, frames} for a file without decoding audio.

    Uses libsndfile header read for formats it supports (fast, no subprocess);
    falls back to ffprobe for SHN / M4A / MP3.  frames is the expected sample
    count at target_sr, used by concat_source for pre-allocation.
    """
    try:
        import soundfile as sf
        info = sf.info(str(path))
        channels = info.channels
        frames = round(info.frames / info.samplerate * target_sr)
    except Exception:
        p = _ffprobe_info(str(path))
        channels = p["channels"]
        frames = round(p["duration"] * target_sr)
    return {"channels": channels, "frames": frames}


def to_mono(x):
    return x.mean(axis=1) if x.ndim == 2 and x.shape[1] > 1 else x.reshape(-1)


def duration_sec(path):
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return info.frames / info.samplerate
    except Exception:
        return _ffprobe_info(str(path))["duration"]


def resample_ratio(x, ratio):
    """Resample x by `ratio` (output_len ≈ len*ratio) to correct a speed offset.
    ratio>1 stretches (was running fast), ratio<1 compresses."""
    from fractions import Fraction
    frac = Fraction(ratio).limit_denominator(100000)
    return resample_poly(x, frac.numerator, frac.denominator, axis=0).astype("float32")
