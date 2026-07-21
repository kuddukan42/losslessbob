"""
Regression tests: the extras/ set-aside subtree stays out of checksum ops.

Covers fixes landed 2026-07-19:
  BUG-259 — generate_checksums() rglob hashed audio under extras/ into a fresh
            top-level _mychecksums sidecar, feeding the superseded fileset's
            hashes back into pipeline lookup (BUG-257 through a new door).
  BUG-260 — verify_folder() parsed sidecars under extras/ and counted extras/
            audio, so a reconciled folder wedged on 'incomplete' (extras-only
            sidecar) or silently re-verified set-aside files.

All tests are pure unit tests; no network, no Flask, no real DB.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import checksum_utils


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


MAIN_BYTES = b"RIFF-main-take-1"
ALT_BYTES = b"RIFF-alt-take-1"


def _make_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "1999-11-01 Somewhere [LB-99999]"
    (folder / "extras").mkdir(parents=True)
    (folder / "d1t01.wav").write_bytes(MAIN_BYTES)
    return folder


class TestGenerateSkipsExtras:
    """BUG-259: generate_checksums must not hash audio under extras/."""

    def test_extras_audio_not_in_generated_sidecar(self, tmp_path):
        folder = _make_folder(tmp_path)
        (folder / "extras" / "alt-t01.wav").write_bytes(ALT_BYTES)

        result = checksum_utils.generate_checksums(str(folder))
        assert not result["errors"]
        md5s = list(folder.glob("*_mychecksums*.md5"))
        assert md5s
        text = md5s[0].read_text()
        assert "extras/" not in text
        assert "d1t01.wav" in text

    def test_subfolder_audio_still_included(self, tmp_path):
        folder = _make_folder(tmp_path)
        (folder / "CD2").mkdir()
        (folder / "CD2" / "d2t01.wav").write_bytes(b"RIFF-disc-2")

        checksum_utils.generate_checksums(str(folder))
        text = next(folder.glob("*_mychecksums*.md5")).read_text()
        assert "CD2/d2t01.wav" in text


class TestVerifyIgnoresExtras:
    """BUG-260: verify_folder must ignore extras/ sidecars and audio."""

    def test_extras_only_sidecar_does_not_wedge_incomplete(self, tmp_path):
        # BUG-257 folder shape: extras/ carries the alternate transfer's
        # sidecar but not its audio.
        folder = _make_folder(tmp_path)
        (folder / "chk.md5").write_text(f"{_md5(MAIN_BYTES)}  d1t01.wav\n")
        (folder / "extras" / "alt.md5").write_text(f"{_md5(b'ALT')}  alt-t01.wav\n")

        r = checksum_utils.verify_folder(str(folder))
        assert r["status"] == "pass"
        assert r["missing"] == 0
        assert r["total"] == 1

    def test_full_extras_subtree_excluded_from_counts(self, tmp_path):
        # Full move_extras result: sidecar + audio both set aside.
        folder = _make_folder(tmp_path)
        (folder / "chk.md5").write_text(f"{_md5(MAIN_BYTES)}  d1t01.wav\n")
        (folder / "extras" / "alt-t01.wav").write_bytes(ALT_BYTES)
        (folder / "extras" / "alt.md5").write_text(f"{_md5(ALT_BYTES)}  alt-t01.wav\n")

        r = checksum_utils.verify_folder(str(folder))
        assert r["status"] == "pass"
        assert r["total"] == 1
        assert r["extra"] == 0
