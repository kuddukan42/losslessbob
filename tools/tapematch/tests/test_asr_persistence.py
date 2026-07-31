"""Persistence tests for the banter/ASR signal (LISTENING_SIGNALS §3).

Covers the observations.db side that ``test_asr.py`` does not: the idempotent
column migration, the ``transcripts`` table, and — because §3 widened a 43-way
INSERT — that ``insert_pairs`` still binds every column it names.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tapematch_session as ts  # noqa: E402


def _source_row(family_id: int) -> dict:
    return {
        "family_id": family_id, "speed_ppm": 0.0, "speed_kind": "reference",
        "hf_ceiling_hz": 16000.0, "noise_floor_db": -60.0, "dc_asymmetry": 0.01,
        "perf_dur_sec": 3600.0, "track_count": 12, "nyquist_capped": 0,
    }


@pytest.fixture()
def obs_db(tmp_path, monkeypatch):
    """An observations.db built by the real schema + migration path."""
    monkeypatch.setattr(ts, "OBS_DB_PATH", tmp_path / "observations.db")
    conn = ts.open_obs_db()
    yield conn
    conn.close()


@pytest.fixture()
def staged(tmp_path, monkeypatch):
    """Two staged source folders, with LB page lookups stubbed out."""
    root = tmp_path / "processing"
    folders = {}
    for lb, name in ((1001, "lb1001_show"), (1002, "lb1002_show")):
        d = root / name
        d.mkdir(parents=True)
        (d / "t01.flac").write_bytes(b"")
        folders[lb] = d
    monkeypatch.setattr(ts, "extract_lb_relationship", lambda a, b: (None, ""))
    return root, folders


def _results(banter_pairs=None, transcripts=None) -> dict:
    return {
        "correlation_matrix": {"names": ["lb1001_show", "lb1002_show"],
                               "values": [[1.0, 0.42], [0.42, 1.0]]},
        "sources": {"lb1001_show": _source_row(1), "lb1002_show": _source_row(1)},
        "secondary_pairs": {},
        "banter_pairs": banter_pairs or {},
        "transcripts": transcripts or {},
    }


def test_migration_adds_the_banter_columns(obs_db):
    cols = {r[1] for r in obs_db.execute("PRAGMA table_info(pairs)")}
    assert {"banter_score", "banter_n_utts_a", "banter_n_utts_b"} <= cols


def test_migration_is_idempotent_on_an_existing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "OBS_DB_PATH", tmp_path / "observations.db")
    ts.open_obs_db().close()
    ts.open_obs_db().close()  # second open must not raise on the ALTERs
    conn = ts.open_obs_db()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pairs)")]
    assert cols.count("banter_score") == 1
    conn.close()


def test_insert_pairs_binds_every_named_column(obs_db, staged):
    """The §3 widening must keep the column list and the placeholders in step."""
    root, folders = staged
    ts.insert_pairs(obs_db, "20260730_120000", "2026-07-30", _results(),
                    folders, "2026-07-30T12:00:00", root_dir=root)
    row = obs_db.execute("SELECT lb_a, lb_b, corr, banter_score FROM pairs").fetchone()
    assert row[:3] == (1001, 1002, 0.42)
    assert row[3] is None  # asr disabled -> NULL, never 0.0


def test_insert_pairs_stores_the_banter_score_and_counts(obs_db, staged):
    root, folders = staged
    results = _results(banter_pairs={
        "lb1001_show|lb1002_show": {"banter_score": 0.75, "n_a": 9, "n_b": 6,
                                    "n_matched": 4, "offset_sec": 2.5},
    })
    ts.insert_pairs(obs_db, "20260730_120000", "2026-07-30", results,
                    folders, "2026-07-30T12:00:00", root_dir=root)
    row = obs_db.execute(
        """SELECT banter_score, banter_n_utts_a, banter_n_utts_b,
                  banter_n_matched, banter_offset_sec FROM pairs""").fetchone()
    assert row == (0.75, 9, 6, 4, 2.5)


def test_insert_pairs_follows_the_lb_order_swap(obs_db, staged):
    """Rows are normalized to (min lb, max lb); the utterance counts must follow."""
    root, folders = staged
    results = _results(banter_pairs={
        # Run JSON order is B|A here — the stored row is A|B, so n_a/n_b swap.
        "lb1002_show|lb1001_show": {"banter_score": 0.5, "n_a": 3, "n_b": 11,
                                    "n_matched": 2, "offset_sec": 1.0},
    })
    results["correlation_matrix"]["names"] = ["lb1002_show", "lb1001_show"]
    ts.insert_pairs(obs_db, "20260730_120000", "2026-07-30", results,
                    folders, "2026-07-30T12:00:00", root_dir=root)
    row = obs_db.execute(
        "SELECT lb_a, lb_b, banter_n_utts_a, banter_n_utts_b FROM pairs").fetchone()
    assert row == (1001, 1002, 11, 3)


def test_insert_transcripts_writes_rows_keyed_by_lb(obs_db, staged):
    _root, folders = staged
    results = _results(transcripts={
        "lb1001_show": [
            {"t_start": 102.0, "t_end": 104.0, "text": "harmonica in the key of G",
             "avg_logprob": -0.31, "no_speech_prob": 0.05},
            {"t_start": 900.5, "t_end": 903.0, "text": "everybody in Boston tonight",
             "avg_logprob": -0.44, "no_speech_prob": 0.11},
        ],
    })
    ts.insert_transcripts(obs_db, "20260730_120000", "2026-07-30", results, folders)
    rows = obs_db.execute(
        "SELECT lb, t_start, text FROM transcripts ORDER BY t_start").fetchall()
    assert rows == [(1001, 102.0, "harmonica in the key of G"),
                    (1001, 900.5, "everybody in Boston tonight")]


def test_insert_transcripts_is_a_noop_without_a_payload(obs_db, staged):
    _root, folders = staged
    ts.insert_transcripts(obs_db, "20260730_120000", "2026-07-30", _results(), folders)
    assert obs_db.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 0


def test_transcripts_index_exists(obs_db):
    names = {r[0] for r in obs_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_transcripts_lb" in names


def test_legacy_db_without_transcripts_table_is_migrated(tmp_path, monkeypatch):
    """A pre-§3 observations.db must gain the table on the next open."""
    db = tmp_path / "observations.db"
    sqlite3.connect(str(db)).close()
    monkeypatch.setattr(ts, "OBS_DB_PATH", db)
    conn = ts.open_obs_db()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transcripts'"
    ).fetchone() is not None
    conn.close()
