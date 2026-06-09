"""
Tests for lookup_checksums() in backend/db.py.

Covers the fix landed 2026-06-03:
  BUG-130 — SHN sets incorrectly flagged INCOMPLETE because the completeness
             check counted foo.wav (shntool) as a separate missing track even
             when the user provided the MD5 of foo.shn (the same track).

             Fix: completeness now groups DB checksums by base filename so that
             foo.shn and foo.wav share the same "track" — if ANY of a track's
             checksums was matched, the track is considered covered.

All tests use a temp-file DB seeded directly via SQL.  The bloom filter is
not populated (None), so all checksums pass through to SQLite — that is the
correct behaviour for tests (no false negatives possible).
"""

import os
import shutil
import tempfile

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_db_with_shn_set(tracks: list[dict]) -> tuple[str, str]:
    """Create a temp DB seeded with checksum entries for LB-1.

    Each dict in `tracks` should have keys:
        shn_chk  — MD5 of the .shn file (chk_type='m', filename='<name>.shn')
        wav_chk  — shntool checksum of the decoded .wav (chk_type='s', filename='<name>.wav')
        name     — base track name, e.g. 'track01'

    Returns (db_path, tmp_dir).
    """
    tmp_dir = tempfile.mkdtemp(prefix="lb_lookup_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    conn = db.get_connection(db_path)

    # Minimal entries row so FK constraints don't block
    conn.execute(
        "INSERT OR IGNORE INTO entries(lb_number, status) VALUES(1, 'ok')"
    )

    for t in tracks:
        conn.execute(
            "INSERT INTO checksums(checksum, filename, chk_type, lb_number, xref)"
            " VALUES(?,?,?,?,?)",
            (t["shn_chk"], f"{t['name']}.shn", "m", 1, 0),
        )
        conn.execute(
            "INSERT INTO checksums(checksum, filename, chk_type, lb_number, xref)"
            " VALUES(?,?,?,?,?)",
            (t["wav_chk"], f"{t['name']}.wav", "s", 1, 0),
        )
    conn.commit()

    return db_path, tmp_dir


# ---------------------------------------------------------------------------
# BUG-130: SHN completeness — foo.shn + foo.wav treated as same track
# ---------------------------------------------------------------------------

class TestLookupChecksumsSnhCompleteness:
    """Providing only the SHN MD5s for a fully-owned SHN set must yield MATCHED, not INCOMPLETE.

    Before the fix the DB had N tracks each with two checksums (.shn MD5 and .wav shntool).
    Providing only the .shn MD5s left the N .wav shntool entries as "missing", so the set
    was marked MATCHED (INCOMPLETE) in detail and INCOMPLETE in the lb_summary.
    """

    TRACKS = [
        {"name": "track01", "shn_chk": "a" * 32, "wav_chk": "b" * 32},
        {"name": "track02", "shn_chk": "c" * 32, "wav_chk": "d" * 32},
        {"name": "track03", "shn_chk": "e" * 32, "wav_chk": "f" * 32},
    ]

    def test_shn_md5s_only_yields_matched_not_incomplete(self):
        """Providing only SHN MD5s for a fully-owned SHN set must give MATCHED status."""
        db_path, tmp = _make_db_with_shn_set(self.TRACKS)
        try:
            import backend.db as db
            # Input: only the .shn MD5 checksums (what a user would have in their .md5 file)
            parsed = [(t["shn_chk"], f"{t['name']}.shn", "m") for t in self.TRACKS]
            summary, detail = db.lookup_checksums(parsed, db_path=db_path)

            # Every detail row that matched should have status MATCHED, not MATCHED (INCOMPLETE)
            matched_rows = [d for d in detail if d["lb_number"] == 1]
            assert matched_rows, "No rows matched LB-1 — seed data not found"
            for row in matched_rows:
                assert row["status"] == "MATCHED", (
                    f"Expected MATCHED but got {row['status']!r} for {row['filename']!r}. "
                    "BUG-130 regression: wav shntool entries counted as missing tracks."
                )

            # lb_summary for LB-1 must not be INCOMPLETE
            lb1_summary = next(
                (s for s in summary["lb_summary"] if s["lb_number"] == 1), None
            )
            assert lb1_summary is not None
            assert lb1_summary["status"] != "INCOMPLETE", (
                f"lb_summary status is {lb1_summary['status']!r}, expected MATCHED. "
                "BUG-130 regression."
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_wav_shntool_only_also_yields_matched(self):
        """Providing only the shntool .wav checksums should also yield MATCHED."""
        db_path, tmp = _make_db_with_shn_set(self.TRACKS)
        try:
            import backend.db as db
            parsed = [(t["wav_chk"], f"{t['name']}.wav", "s") for t in self.TRACKS]
            summary, detail = db.lookup_checksums(parsed, db_path=db_path)

            matched_rows = [d for d in detail if d["lb_number"] == 1]
            assert matched_rows
            for row in matched_rows:
                assert row["status"] == "MATCHED", (
                    f"Got {row['status']!r} for {row['filename']!r}"
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_partial_set_still_incomplete(self):
        """Providing checksums for only 1 of 3 tracks must still yield INCOMPLETE."""
        db_path, tmp = _make_db_with_shn_set(self.TRACKS)
        try:
            import backend.db as db
            # Only provide the first track's SHN MD5
            first = self.TRACKS[0]
            parsed = [(first["shn_chk"], f"{first['name']}.shn", "m")]
            summary, detail = db.lookup_checksums(parsed, db_path=db_path)

            lb1_summary = next(
                (s for s in summary["lb_summary"] if s["lb_number"] == 1), None
            )
            assert lb1_summary is not None
            assert lb1_summary["status"] == "INCOMPLETE", (
                f"Expected INCOMPLETE for a partial match but got {lb1_summary['status']!r}"
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_mixed_shn_and_wav_checksums_still_matched(self):
        """Providing a mix of SHN MD5s and WAV shntool checksums for different tracks
        must still resolve to MATCHED (all tracks covered by at least one checksum)."""
        db_path, tmp = _make_db_with_shn_set(self.TRACKS)
        try:
            import backend.db as db
            parsed = [
                (self.TRACKS[0]["shn_chk"], "track01.shn", "m"),
                (self.TRACKS[1]["wav_chk"], "track02.wav", "s"),
                (self.TRACKS[2]["shn_chk"], "track03.shn", "m"),
            ]
            summary, detail = db.lookup_checksums(parsed, db_path=db_path)

            lb1_summary = next(
                (s for s in summary["lb_summary"] if s["lb_number"] == 1), None
            )
            assert lb1_summary is not None
            assert lb1_summary["status"] != "INCOMPLETE", (
                f"Got {lb1_summary['status']!r}; all tracks should be covered."
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
