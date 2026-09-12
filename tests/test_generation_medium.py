"""Tests for backend.dossier_fields classify_generation (D-05) and classify_medium (D-13), C21.

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
    tmp_dir = tempfile.mkdtemp(prefix="lb_generation_test_")
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


def _entry(c, lb, chain="", category="concert"):
    c.execute(
        "INSERT INTO entries (lb_number, date_str, source_chain, lb_category) VALUES (?, ?, ?, ?)",
        (lb, "1/1/90", chain, category),
    )


def _taper(c, lb, confidence="confirmed", taper="someone"):
    c.execute(
        "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence, evidence_json,"
        " conflict, computed_at) VALUES (?, ?, ?, '[]', 0, '2026-01-01')",
        (lb, taper, confidence),
    )


def _gen(c, lb):
    from backend.dossier_fields import classify_generation
    g = classify_generation(c, lb)
    return g["generation"], g["basis"]


class TestClassifyGeneration:
    @pytest.mark.parametrize("chain,expected", [
        ("BOOTLEG:Mono Mixes; cd > eac > flac", ("silver", "stated")),
        ("voice of promise 7, Label:XAVEL, Silver cds>EAC", ("silver", "stated")),
        ("Near Mint Vinyl LPs > Technics SL1200 > FLAC", ("vinyl", "stated")),
        ("pre-FM reel > DAT > CDR", ("broadcast", "stated")),
        # "Radio Shack" still isn't a broadcast — but mics > recorder now infers master.
        ("Radio Shack mics > Sony D6 > cassette", ("master", "inferred")),
        ("Crown/Radio, Shack Mics on Sony D5", ("unknown", None)),
        ("1st gen cassette > DAT > CDR", ("low_gen", "stated")),
        ("clone of master > CDR", ("low_gen", "stated")),
        ("FLAC received from 'lowgen', no lineage", ("unknown", None)),
        ("Master tape > CDR > EAC", ("master", "stated")),
        # Closed compounds are the same claim without the space (tj, 2026-09-11).
        ("MasterDAT > CDR", ("master", "stated")),
        ("mastercopy > flac", ("master", "stated")),
        ("MasterTape > DAT > DATClone > CD-R", ("low_gen", "stated")),
        # Not generations: a post-transfer credit, a song title, a bootleg's name.
        ("Mastered by LTA > flac", ("unknown", None)),
        ("remastering by the taper > flac", ("unknown", None)),
        ("cut before Masters Of War, aud > cdr", ("unknown", None)),
        # From tj's 2026-09-11 row-by-row review of the 100-LB audit.
        ("2nd Generation Cassettes (from GS> Akai GX95 > Soundforge 9", ("low_gen", "stated")),
        ("Vh1 (on line - stream version> Realtek HD Audio > wav > flac", ("broadcast", "stated")),
        ("Sony PCM-D100 (24bit/48khz ), >USB 3.0 >PC >WaveLab", ("master", "inferred")),
        ("dpa4061 > Tascam DR-100 @24/48 > PC (Sound Forge> flac", ("master", "inferred")),
        ("Soundboard in possession of LTE, transferred to CDR by him >", ("low_gen", "stated")),
        # Nothing names a capture device, so nothing is inferred.
        ("CDs received in a trade > EAC > WAV > FLAC", ("unknown", None)),
        ("Sennheiser MKE2002 -> cassette master -> DAT - clone -> CDR", ("low_gen", "stated")),
        ("", ("unknown", None)),
    ])
    def test_rules_first_match_wins(self, conn, chain, expected):
        with conn:
            _entry(conn, 1, chain)
        assert _gen(conn, 1) == expected

    def test_silver_disc_without_label_is_silver(self, conn):
        with conn:
            _entry(conn, 1, "Silver CD > EAC > FLAC")
        assert _gen(conn, 1) == ("silver", "stated")

    def test_bootleg_titles_row_is_silver(self, conn):
        with conn:
            _entry(conn, 1, "")
            conn.execute("INSERT INTO bootleg_titles (lb_number, title) VALUES (1, 'Some Title')")
        assert _gen(conn, 1) == ("silver", "stated")

    def test_capture_chain_infers_master_whatever_the_taper(self, conn):
        """tj, 2026-09-11: the chain is the evidence, not the attribution.

        The inference used to require a confirmed taper, which made the generation
        field track taper-attribution coverage rather than lineage.
        """
        chain = "SP-CMC-8 > MM-EBM-1 > MicroTrack 24/96"
        with conn:
            _entry(conn, 1, chain)
            _entry(conn, 2, chain)
            _entry(conn, 3, chain)
            _taper(conn, 1, "confirmed")
            _taper(conn, 2, "propagated")
        assert _gen(conn, 1) == ("master", "inferred")
        assert _gen(conn, 2) == ("master", "inferred")
        assert _gen(conn, 3) == ("master", "inferred")

    def test_quarantined_taper_no_longer_blocks_the_inference(self, conn):
        with conn:
            _entry(conn, 1, "SP-CMC-8 > MicroTrack")
            _taper(conn, 1, "confirmed")
            conn.execute(
                "INSERT INTO qc_findings (rule_id, entity_kind, entity_key, severity, detail,"
                " evidence_json, evidence_hash, first_seen, last_seen, status)"
                " VALUES ('R-T3', 'lb', '1', 'error', '', '{}', 'h', '2026-01-01',"
                " '2026-01-01', 'open')"
            )
        assert _gen(conn, 1) == ("master", "inferred")


class TestClassifyMedium:
    @pytest.mark.parametrize("category,chain,expected", [
        ("tv", "", ("audio_from_video", True)),
        ("radio", "", ("audio", True)),
        ("concert", "Channel 9 TV > VHS > DVD", ("audio_from_video", True)),
        ("concert", "audience camcorder > DVD > VOB > wav", ("audio_from_video", False)),
        ("concert", "FM > cassette > CDR", ("audio", True)),
        ("concert", "Radio Shack mics > D6", ("audio", False)),
        ("concert", "Schoeps > DAT", ("audio", False)),
    ])
    def test_signals(self, conn, category, chain, expected):
        from backend.dossier_fields import classify_medium
        with conn:
            _entry(conn, 1, chain, category)
        m = classify_medium(conn, 1)
        assert (m["medium"], m["broadcast"]) == expected

    def test_video_file_extension(self, conn):
        from backend.dossier_fields import classify_medium
        with conn:
            _entry(conn, 1, "")
            conn.execute(
                "INSERT INTO checksums (checksum, filename, chk_type, lb_number, xref)"
                " VALUES ('x', 'VTS_01_1.VOB', 'md5', 1, 0)"
            )
        assert classify_medium(conn, 1)["medium"] == "audio_from_video"

    def test_media_available_and_broadcast_tapers(self, conn):
        from backend.dossier_fields import broadcast_tapers, media_available
        with conn:
            _entry(conn, 1, "", "tv")
            _entry(conn, 2, "audience camcorder > DVD")
            _entry(conn, 3, "Schoeps > DAT")
            for lb in (1, 2, 3):
                _taper(conn, lb)
        assert media_available(conn, [1, 2, 3]) == ["audio", "audio_from_video"]
        assert [lb for lb, _, _ in broadcast_tapers(conn)] == [1]


class TestRuleT5:
    def test_broadcast_source_with_taper_fires(self, conn):
        from backend.qc.rules import RULES, rule_t5
        with conn:
            _entry(conn, 1, "", "tv")
            _entry(conn, 2, "audience camcorder > DVD")
            _taper(conn, 1, taper="lta")
            _taper(conn, 2, taper="someone")
        findings = list(rule_t5(conn))
        assert [(f.entity_key, f.severity) for f in findings] == [("1", "warn")]
        assert "lta" in findings[0].detail
        assert RULES["R-T5"].func is rule_t5
