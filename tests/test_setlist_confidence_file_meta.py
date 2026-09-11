"""Tests for backend.dossier_fields setlist_confidence (D-09) and file_meta (D-11), C22.

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
from __future__ import annotations

import os
import shutil
import tempfile

import pytest


@pytest.fixture
def conn():
    """Yield a connection to a throwaway database with the full schema."""
    tmp_dir = tempfile.mkdtemp(prefix="lb_setlist_filemeta_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    c = db.get_connection(db_path)
    try:
        yield c
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _event(c, event_id, date_str, notes="", recording_mins=None, event_type="concert"):
    c.execute(
        "INSERT OR IGNORE INTO olof_pages (filename) VALUES ('test.htm')"
    )
    c.execute(
        "INSERT INTO olof_events (event_id, date_str, event_type, notes, recording_mins,"
        " page_filename) VALUES (?, ?, ?, ?, ?, 'test.htm')",
        (event_id, date_str, event_type, notes, recording_mins),
    )


def _songs(c, event_id, titles):
    for i, title in enumerate(titles, start=1):
        c.execute(
            "INSERT INTO olof_songs (event_id, position, song_title) VALUES (?, ?, ?)",
            (event_id, i, title),
        )


def _entry(c, lb, date_str, timing="", cdr="", description="", source_chain=""):
    c.execute(
        "INSERT INTO entries (lb_number, date_str, timing, cdr, description, source_chain)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (lb, date_str, timing, cdr, description, source_chain),
    )


def _sfm(c, setlistfm_id, date_str, titles):
    c.execute(
        "INSERT INTO setlistfm_shows (setlistfm_id, date_str) VALUES (?, ?)",
        (setlistfm_id, date_str),
    )
    for i, title in enumerate(titles, start=1):
        c.execute(
            "INSERT INTO setlistfm_setlist (setlistfm_id, set_index, position, set_position,"
            " track_name) VALUES (?, 0, ?, ?, ?)",
            (setlistfm_id, i, i, title),
        )


def _tuit_recording(c, lb, format_="", lineage="", size_bytes=None, n_files=None, verified=1):
    c.execute(
        "INSERT INTO tuit_recordings (rec_id, lb_number, format, lineage, size_bytes, n_files,"
        " lb_verified) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lb, lb, format_, lineage, size_bytes, n_files, verified),
    )


class TestSetlistConfidence:
    def test_corroborated_reads_complete(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1986-02-24")
            songs = [f"Song {i}" for i in range(1, 26)]
            _songs(conn, 1, songs)
            _sfm(conn, "sfm1", "1986-02-24", songs)
        sc = setlist_confidence(conn, 1, [])
        assert (sc["status"], sc["verdict"], sc["songs_listed"]) == ("complete", "corroborated", 25)

    def test_disputed_reads_partial_with_notice(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1975-12-08")
            _songs(conn, 1, [])  # Olof has 0 (pre-parser-fix shape)
            other = [f"Song {i}" for i in range(1, 23)]
            _sfm(conn, "sfm1", "1975-12-08", other)
            c2 = conn.execute(
                "INSERT INTO bobdylan_shows (bobdylan_url, date_str) VALUES ('bd1', ?)",
                ("1975-12-08",),
            )
            for i, title in enumerate(other, start=1):
                conn.execute(
                    "INSERT INTO bobdylan_setlist (bobdylan_url, position, track_name)"
                    " VALUES ('bd1', ?, ?)", (i, title),
                )
        sc = setlist_confidence(conn, 1, [])
        assert sc["status"] == "partial"
        assert sc["verdict"] == "disputed"
        # The notice must name the count actually in dispute — ours — not only the
        # sources', which routinely agree with each other and disagree with Olof.
        assert sc["notice"] is not None
        assert "Olof lists 0" in sc["notice"]
        assert "lists 22" in sc["notice"]

    def test_unavailable_when_nobody_has_a_setlist(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1960-01-01")
            _songs(conn, 1, [])
        sc = setlist_confidence(conn, 1, [])
        assert sc["status"] == "unavailable"

    def test_incomplete_note_forces_partial(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1966-03-05", notes="Incomplete setlist taken from memory.")
            _songs(conn, 1, [f"Song {i}" for i in range(1, 4)])
        sc = setlist_confidence(conn, 1, [])
        assert (sc["status"], sc["basis"]) == ("partial", "incomplete_note")

    def test_synthetic_short_fixture_reads_partial_from_runtime(self, conn):
        """A 7-song fixture with a runtime implying far more songs -> partial (plan accept case)."""
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1990-01-01")
            _songs(conn, 1, [f"Song {i}" for i in range(1, 8)])  # 7 songs
            # ~120 min at 6.33 min/song implies ~19 songs -- gap of 12, over threshold.
            _entry(conn, 100, "1/1/90", timing="120min")
        sc = setlist_confidence(conn, 1, [100])
        assert sc["status"] == "partial"
        assert sc["basis"] == "runtime"
        assert sc["expected_songs"] > 7

    def test_no_runtime_signal_defaults_complete(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1990-01-01")
            _songs(conn, 1, [f"Song {i}" for i in range(1, 8)])
            _entry(conn, 100, "1/1/90", timing="")
        sc = setlist_confidence(conn, 1, [100])
        assert sc["status"] == "complete"
        assert sc["expected_songs"] is None

    def test_short_runtime_gap_within_threshold_stays_complete(self, conn):
        from backend.dossier_fields import setlist_confidence
        with conn:
            _event(conn, 1, "1990-01-01")
            _songs(conn, 1, [f"Song {i}" for i in range(1, 21)])  # 20 songs
            # 20 * 6.33 ~= 127 min; give 133min -> expected ~21, gap 1 -- under threshold.
            _entry(conn, 100, "1/1/90", timing="133min")
        sc = setlist_confidence(conn, 1, [100])
        assert sc["status"] == "complete"


class TestFileMeta:
    def test_file_record_wins_and_shows_both_when_they_differ(self, conn):
        """LB-08485 accept case (plan D-11 / audit M1)."""
        from backend.dossier_fields import file_meta
        with conn:
            _entry(
                conn, 8485, "3/29/10", cdr="2",
                description="Source: DPA 4061's > MMA6000 > Edirol R-09HR (24bit/96kHz),"
                            " Lineage: SDHC card > PC > WAV (24bit/96kHz) > Soundforge"
                            " (Edit, sampling convert to 16bit/44.1kHz)> TLH > FLAC",
            )
            _tuit_recording(
                conn, 8485, format_="FLAC 16/44",
                lineage="SDHC card > PC > WAV (24bit/96kHz) > Soundforge (Edit, sampling"
                        " convert to 16bit/44.1kHz) > TLH > FLAC",
                size_bytes=714814259, n_files=23,
            )
            for i in range(1, 21):
                conn.execute(
                    "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref)"
                    " VALUES (?, ?, 'f', 8485, 0)", (f"chk{i}", f"track{i:02d}.flac"),
                )
        fm = file_meta(conn, 8485)
        assert fm["resolution"] == "16/44 file · recorded 24/96"
        assert fm["file_res"] == "16/44"
        assert fm["recorded_res"] == "24/96"
        assert fm["filesize"] == 714814259
        assert fm["filecount"] == 20
        assert fm["disc_count"] == 2

    def test_lineage_only_labelled_recorded_not_file(self, conn):
        from backend.dossier_fields import file_meta
        with conn:
            _entry(conn, 1, "1/1/90", description="Lineage: DAT (16bit/48kHz) > CDR > EAC > FLAC")
        fm = file_meta(conn, 1)
        assert fm["resolution"] == "recorded 16/48"
        assert fm["file_res"] is None

    def test_null_resolution_renders_dash(self, conn):
        from backend.dossier_fields import file_meta
        with conn:
            _entry(conn, 1, "1/1/90")
        fm = file_meta(conn, 1)
        assert fm["resolution"] == "—"
        assert fm["filesize"] is None
        assert fm["filecount"] is None

    def test_filecount_falls_back_to_tuit_n_files_without_checksums(self, conn):
        from backend.dossier_fields import file_meta
        with conn:
            _entry(conn, 1, "1/1/90")
            _tuit_recording(conn, 1, format_="FLAC 16/44", n_files=15)
        assert file_meta(conn, 1)["filecount"] == 15

    @pytest.mark.parametrize("cdr,expected", [
        ("", None), ("0", None), ("-1", None), ("7", None), ("1", 1), ("6", 6), ("abc", None),
    ])
    def test_disc_count_range(self, conn, cdr, expected):
        from backend.dossier_fields import file_meta
        with conn:
            _entry(conn, 1, "1/1/90", cdr=cdr)
        assert file_meta(conn, 1)["disc_count"] == expected
