"""Tests for BUG-176: tapematch must not abort the whole run when one source's
track can't be decoded (e.g. a corrupt/truncated file or a non-FLAC file with
a .flac extension).

audio.duration_sec() now raises UnreadableAudioError instead of a bare
RuntimeError, and ingest.source_report() wraps that into
UnreadableSourceError carrying the offending source_dir/track so cli.py can
exclude just that source and continue with the rest.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tapematch import audio, ingest  # noqa: E402


def test_duration_sec_raises_unreadable_audio_error(tmp_path):
    bad = tmp_path / "bd1997-02-09-d1t04.flac"
    bad.write_bytes(b"not a real flac file" * 10)

    try:
        audio.duration_sec(bad)
    except audio.UnreadableAudioError:
        pass
    else:
        raise AssertionError("expected UnreadableAudioError")


def test_source_report_raises_unreadable_source_error(tmp_path):
    source = tmp_path / "1997-02-09 Some Show (LB-14923)"
    source.mkdir()
    bad = source / "bd1997-02-09-d1t04.flac"
    bad.write_bytes(b"not a real flac file" * 10)

    try:
        ingest.source_report(source, {".flac"})
    except ingest.UnreadableSourceError as e:
        assert e.source_dir == source
        assert e.track == bad
    else:
        raise AssertionError("expected UnreadableSourceError")
