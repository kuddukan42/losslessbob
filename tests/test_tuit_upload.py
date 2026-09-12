"""Tests for backend.tuit_upload — payload composition and the POST gates.

Nothing here touches the network or the real database. The tracker is stubbed
with fake sessions, and every DB test runs against a temp-file schema.
"""
import json
import os
import shutil
import tempfile

import pytest

from backend import tuit_upload


def _make_db() -> tuple[str, str]:
    """Create a fresh temp DB with the full schema. Returns (db_path, tmp_dir)."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtuitup_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    db.init_db(db_path)
    return db_path, tmp_dir


@pytest.fixture
def dbmod():
    """Yield backend.db bound to a throwaway database."""
    import backend.db as db
    db_path, tmp_dir = _make_db()
    try:
        yield db, db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def folder():
    """Yield a throwaway recording folder with sidecars but no real audio."""
    tmp_dir = tempfile.mkdtemp(prefix="lbtuitup_folder_")
    try:
        yield tmp_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FakeSession:
    """Stands in for a logged-in requests.Session over /api/shows/search."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _FakeResponse(self.payload)


# ── Vocabulary mapping ───────────────────────────────────────────────────────


def test_every_mapped_value_is_a_real_form_option():
    """Nothing in the maps may fall outside the form's closed selects."""
    assert set(tuit_upload.SOURCE_TYPE_MAP.values()) <= set(tuit_upload.SOURCE_TYPES)
    assert set(tuit_upload.QUALITY_MAP.values()) <= set(tuit_upload.QUALITIES)


def test_source_type_map_covers_the_entries_vocabulary():
    """The six values entries.source_type actually holds all map."""
    for observed in ("Audience", "Soundboard", "ALD", "FM/Pre-FM", "Mixed"):
        assert tuit_upload.SOURCE_TYPE_MAP[observed.lower()] in tuit_upload.SOURCE_TYPES


# ── Folder inspection ────────────────────────────────────────────────────────


def test_read_ffp_returns_the_sidecar_text(folder):
    with open(os.path.join(folder, "set.ffp"), "w", encoding="utf-8") as fh:
        fh.write("d1t01.flac:abc123\n")
    assert "d1t01.flac:abc123" in tuit_upload.read_ffp(folder)


def test_read_ffp_is_empty_without_a_sidecar(folder):
    assert tuit_upload.read_ffp(folder) == ""


def test_find_info_file_prefers_the_largest_non_checksum_text(folder):
    with open(os.path.join(folder, "info.txt"), "w", encoding="utf-8") as fh:
        fh.write("lineage and notes\n" * 50)
    with open(os.path.join(folder, "tiny.nfo"), "w", encoding="utf-8") as fh:
        fh.write("x")
    with open(os.path.join(folder, "set.md5.txt"), "w", encoding="utf-8") as fh:
        fh.write("checksums\n" * 500)
    picked = tuit_upload.find_info_file(folder)
    assert picked is not None and picked.name == "info.txt"


def test_find_info_file_skips_files_over_the_cap(folder):
    with open(os.path.join(folder, "huge.txt"), "w", encoding="utf-8") as fh:
        fh.write("x" * (tuit_upload.MAX_INFO_BYTES + 1))
    assert tuit_upload.find_info_file(folder) is None


def test_probe_audio_falls_back_to_the_extension(folder):
    """An unreadable file still tells us the format from its name."""
    with open(os.path.join(folder, "d1t01.shn"), "wb") as fh:
        fh.write(b"not really shorten")
    probed = tuit_upload.probe_audio(folder)
    assert probed["format"] == "shn"
    assert probed["bit_depth"] is None


def test_probe_audio_on_an_empty_folder(folder):
    assert tuit_upload.probe_audio(folder)["files_probed"] == 0


# ── Show resolution ──────────────────────────────────────────────────────────


def test_find_show_takes_the_only_match():
    session = _FakeSession([
        {"id": 3479, "date": "1978-10-07", "venue": "Civic Center", "city": "Providence"},
    ])
    show = tuit_upload.find_show(session, "1978-10-07")
    assert show["id"] == 3479


def test_find_show_disambiguates_a_two_show_date_by_venue():
    session = _FakeSession([
        {"id": 1, "date": "1974-01-06", "venue": "Chicago Stadium", "city": "Chicago"},
        {"id": 2, "date": "1974-01-06", "venue": "The Spectrum", "city": "Philadelphia"},
    ])
    assert tuit_upload.find_show(session, "1974-01-06", "The Spectrum")["id"] == 2


def test_find_show_refuses_an_ambiguous_date():
    session = _FakeSession([
        {"id": 1, "date": "1974-01-06", "venue": "Chicago Stadium", "city": "Chicago"},
        {"id": 2, "date": "1974-01-06", "venue": "The Spectrum", "city": "Philadelphia"},
    ])
    assert tuit_upload.find_show(session, "1974-01-06") is None


def test_find_show_drops_rows_for_another_date():
    session = _FakeSession([{"id": 9, "date": "1966-05-17", "venue": "Free Trade Hall"}])
    assert tuit_upload.find_show(session, "1978-10-07") is None


def test_find_show_without_a_date_makes_no_request():
    session = _FakeSession([])
    assert tuit_upload.find_show(session, "") is None
    assert session.calls == []


# ── Field composition ────────────────────────────────────────────────────────


def _seed_entry(db, db_path, **over):
    """Insert one entry plus an olof_events concert on the same date."""
    row = {"lb_number": 707, "date_str": "10/7/78", "location": "Providence, RI",
           "rating": "A-", "source_type": "Audience", "taper_name": "Some Taper",
           "source_chain": "AUD > Master Cassette > DAT > FLAC",
           "description": "excellent sound"}
    row.update(over)
    with db.get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, location, rating, source_type,"
            " taper_name, source_chain, description)"
            " VALUES (:lb_number, :date_str, :location, :rating, :source_type,"
            " :taper_name, :source_chain, :description)", row)
        # olof_events.page_filename is a FK onto olof_pages.
        conn.execute("INSERT OR IGNORE INTO olof_pages (filename) VALUES ('x.htm')")
        conn.execute(
            "INSERT INTO olof_events (source, page_filename, event_type, date_str,"
            " venue, city, region, country, tour_name)"
            " VALUES ('dsn', 'x.htm', 'concert', '1978-10-07', 'Civic Center',"
            " 'Providence', 'Rhode Island', 'USA', 'Street Legal Tour')")
        conn.commit()
    return row


def test_build_fields_maps_the_catalogue_onto_the_form(dbmod, folder):
    db, db_path = dbmod
    _seed_entry(db, db_path)
    with open(os.path.join(folder, "d1t01.flac"), "wb") as fh:
        fh.write(b"fake")
    with open(os.path.join(folder, "set.ffp"), "w", encoding="utf-8") as fh:
        fh.write("d1t01.flac:abc\n")

    fields, warnings = tuit_upload.build_fields(707, folder, db_path)

    assert fields["lb_number"] == "707"
    assert fields["source_type"] == "audience"
    assert fields["audio_quality"] == "very-good"
    assert fields["format"] == "flac"
    assert fields["taper"] == "Some Taper"
    assert fields["lineage"].startswith("AUD >")
    assert fields["ffp"].startswith("d1t01.flac")
    assert fields["new_show_date"] == "1978-10-07"
    assert fields["new_venue"] == "Civic Center"
    assert fields["new_state"] == "Rhode Island"
    assert fields["new_tour"] == "Street Legal Tour"
    # The fake flac cannot be decoded, so depth and rate are honest gaps.
    assert any(w.startswith("bit_depth") for w in warnings)


def test_build_fields_warns_on_an_unmappable_source_type(dbmod, folder):
    db, db_path = dbmod
    _seed_entry(db, db_path, source_type="Wax cylinder")
    fields, warnings = tuit_upload.build_fields(707, folder, db_path)
    assert "source_type" not in fields
    assert any("source_type" in w for w in warnings)


def test_build_fields_warns_on_a_circa_date(dbmod, folder):
    db, db_path = dbmod
    _seed_entry(db, db_path, date_str="5/xx/87")
    fields, warnings = tuit_upload.build_fields(707, folder, db_path)
    assert fields["new_show_date"] == ""
    assert any(w.startswith("date:") for w in warnings)


# ── Gates ────────────────────────────────────────────────────────────────────


def test_prepare_upload_refuses_a_private_entry(dbmod, monkeypatch):
    db, db_path = dbmod
    monkeypatch.setattr(tuit_upload.database, "is_seedable_to_tracker",
                        lambda lb, p=None: (False, "lb_private"))
    with pytest.raises(RuntimeError, match="lb_private"):
        tuit_upload.prepare_upload(707, db_path=db_path)


def test_prepare_upload_refuses_without_a_local_folder(dbmod, monkeypatch):
    db, db_path = dbmod
    monkeypatch.setattr(tuit_upload.database, "is_seedable_to_tracker",
                        lambda lb, p=None: (True, None))
    monkeypatch.setattr(tuit_upload.database, "get_folders_for_lb",
                        lambda lb, p=None: [])
    with pytest.raises(RuntimeError, match="no local folder"):
        tuit_upload.prepare_upload(707, db_path=db_path)


def test_prepare_upload_flags_a_duplicate_and_files_a_prepared_row(dbmod, folder, monkeypatch):
    db, db_path = dbmod
    _seed_entry(db, db_path)
    monkeypatch.setattr(tuit_upload.database, "is_seedable_to_tracker",
                        lambda lb, p=None: (True, None))
    monkeypatch.setattr(tuit_upload.database, "get_folders_for_lb",
                        lambda lb, p=None: [folder])
    monkeypatch.setattr(tuit_upload.database, "tuit_has_recording",
                        lambda lb=None, h="", p=None: {"rec_id": 1837, "info_hash": ""})

    payload = tuit_upload.prepare_upload(707, make_torrent=False, db_path=db_path)

    assert any(w.startswith("duplicate:") for w in payload.warnings)
    assert payload.upload_id is not None
    rows = db.get_tuit_uploads(707, db_path)
    assert rows and rows[0]["status"] == "prepared"
    assert json.loads(rows[0]["payload_json"])["fields"]["lb_number"] == "707"


def test_post_upload_refuses_a_duplicate():
    payload = tuit_upload.UploadPayload(
        lb_number=707, fields={}, torrent_path="/nonexistent.torrent",
        warnings=["duplicate: TUIT already has /recordings/1837 for LB-00707"],
    )
    result = tuit_upload.post_upload(None, payload)
    assert result["ok"] is False
    assert result["error"].startswith("duplicate:")


def test_post_upload_refuses_without_a_torrent(dbmod):
    db, db_path = dbmod
    payload = tuit_upload.UploadPayload(lb_number=707, fields={}, torrent_path="")
    result = tuit_upload.post_upload(None, payload, db_path=db_path)
    assert result["ok"] is False
    assert "torrent_file" in result["error"]


# ── Bookkeeping ──────────────────────────────────────────────────────────────


def test_tuit_has_recording_matches_infohash_then_lb(dbmod):
    db, db_path = dbmod
    with db.get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO tuit_recordings (rec_id, lb_number, info_hash)"
            " VALUES (1837, 707, 'DEADBEEF')")
        conn.commit()
    assert db.tuit_has_recording(info_hash="deadbeef", db_path=db_path)["rec_id"] == 1837
    assert db.tuit_has_recording(lb_number=707, db_path=db_path)["rec_id"] == 1837
    assert db.tuit_has_recording(lb_number=999, db_path=db_path) is None


def test_upload_rows_round_trip(dbmod):
    db, db_path = dbmod
    upload_id = db.add_tuit_upload(lb_number=707, status="prepared",
                                   info_hash="abc", db_path=db_path)
    db.update_tuit_upload(upload_id, {"status": "uploaded", "rec_id": 1900}, db_path)
    row = db.get_tuit_uploads(707, db_path)[0]
    assert (row["status"], row["rec_id"]) == ("uploaded", 1900)


def test_shn_gets_an_assumed_16_bit_depth(dbmod, folder):
    """Shorten reports no depth; TUIT labels every SHN it holds 16/44."""
    db, db_path = dbmod
    _seed_entry(db, db_path)
    with open(os.path.join(folder, "d1t01.shn"), "wb") as fh:
        fh.write(b"not really shorten")
    fields, warnings = tuit_upload.build_fields(707, folder, db_path)
    assert fields["format"] == "shn"
    assert fields["bit_depth"] == "16"
    assert any("assumed 16" in w for w in warnings)


def test_flac_without_a_depth_is_left_blank(dbmod, folder):
    """The assumption is shn-only — a flac that will not decode stays a gap."""
    db, db_path = dbmod
    _seed_entry(db, db_path)
    with open(os.path.join(folder, "d1t01.flac"), "wb") as fh:
        fh.write(b"fake")
    fields, warnings = tuit_upload.build_fields(707, folder, db_path)
    assert "bit_depth" not in fields
    assert any(w.startswith("bit_depth: probed") for w in warnings)


def test_description_is_dropped_when_an_info_file_is_attached(dbmod, folder, monkeypatch):
    db, db_path = dbmod
    _seed_entry(db, db_path)
    with open(os.path.join(folder, "info.txt"), "w", encoding="utf-8") as fh:
        fh.write("lineage and notes\n" * 20)
    monkeypatch.setattr(tuit_upload.database, "is_seedable_to_tracker",
                        lambda lb, p=None: (True, None))
    monkeypatch.setattr(tuit_upload.database, "get_folders_for_lb",
                        lambda lb, p=None: [folder])
    monkeypatch.setattr(tuit_upload.database, "tuit_has_recording",
                        lambda lb=None, h="", p=None: None)

    payload = tuit_upload.prepare_upload(707, make_torrent=False, db_path=db_path)

    assert payload.info_path is not None
    assert "description" not in payload.fields
    assert any(w.startswith("description: dropped") for w in payload.warnings)
