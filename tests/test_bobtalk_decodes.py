"""Tests for the bobtalk ASR decode cache (TODO-303).

The cache exists so re-scoring is free; these pin the two properties that make
it safe to trust — a hit is only served for the exact model and window geometry
that produced it, and a half-written decode never counts as a complete one.
"""
import sqlite3
import sys
import types

import numpy as np
import pytest

from backend import bobtalk_decodes as dec
from tools import bobtalk_locate as loc

MODEL = "large-v3"
CT = "float16"
PRE, POST = 55.0, 25.0


@pytest.fixture()
def cache():
    """An in-memory decode cache with the schema applied."""
    conn = sqlite3.connect(":memory:")
    dec.ensure_schema(conn)
    yield conn
    conn.close()


def _windows(n=3, prefix="window"):
    return [dec.Window(i, i * 100.0, i * 100.0 + 80.0, f"{prefix} {i} text")
            for i in range(n)]


def test_ensure_schema_is_idempotent(cache):
    dec.ensure_schema(cache)
    dec.ensure_schema(cache)
    tables = {r[0] for r in cache.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"bobtalk_decode_runs", "bobtalk_decode_windows"} <= tables


def test_roundtrip_preserves_order_and_text(cache):
    assert dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows()) == 3
    got = dec.load_windows(cache, 212, MODEL, CT, PRE, POST)
    assert [w.index for w in got] == [0, 1, 2]
    assert got[1].text == "window 1 text"
    assert got[2].t_start == 200.0 and got[2].t_end == 280.0


def test_miss_returns_none_not_empty_list(cache):
    assert dec.load_windows(cache, 999, MODEL, CT, PRE, POST) is None


def test_empty_decode_is_a_hit_not_a_miss(cache):
    """A recording with no boundaries is cached, and must not re-decode."""
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, [])
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) == []


def test_different_model_misses(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    assert dec.load_windows(cache, 212, "base", CT, PRE, POST) is None


def test_different_geometry_misses(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    assert dec.load_windows(cache, 212, MODEL, CT, 90.0, POST) is None
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, 40.0) is None


def test_different_compute_type_misses(cache):
    """int8 and float16 decode the same audio differently; never share an entry."""
    dec.save_windows(cache, 212, MODEL, "int8", PRE, POST, _windows())
    assert dec.load_windows(cache, 212, MODEL, "float16", PRE, POST) is None
    assert dec.load_windows(cache, 212, MODEL, "int8", PRE, POST) is not None


def test_device_is_recorded_but_not_part_of_the_key(cache):
    """A GPU pass must reuse a CPU pass at the same quantisation, not redo it."""
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows(), device="cpu")
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is not None
    assert cache.execute(
        "SELECT device FROM bobtalk_decode_runs").fetchone()[0] == "cpu"


def test_schema_discards_a_cache_predating_the_compute_type_key():
    """A legacy table missing a key column is dropped, not silently reused."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE bobtalk_decode_windows (
        lb_number INTEGER, model TEXT, pre_sec REAL, post_sec REAL,
        window_index INTEGER, t_start REAL, t_end REAL, text TEXT)""")
    conn.execute("INSERT INTO bobtalk_decode_windows VALUES (212,'large-v3',55,25,0,0,80,'x')")
    dec.ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bobtalk_decode_windows)")}
    assert "compute_type" in cols
    assert conn.execute("SELECT COUNT(*) FROM bobtalk_decode_windows").fetchone()[0] == 0
    conn.close()


def test_geometry_key_tolerates_float_representation(cache):
    dec.save_windows(cache, 212, MODEL, CT, 55.0, 25.0, _windows())
    assert dec.load_windows(cache, 212, MODEL, CT, 55.0000000001, 25.0) is not None


def test_resave_replaces_rather_than_appends(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows(4, "old"))
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows(2, "new"))
    got = dec.load_windows(cache, 212, MODEL, CT, PRE, POST)
    assert len(got) == 2
    assert all(w.text.startswith("new") for w in got)


def test_partial_decode_is_not_served_as_complete(cache):
    """A run row claiming more windows than exist must read as a miss."""
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows(3))
    cache.execute("DELETE FROM bobtalk_decode_windows WHERE window_index = 2")
    cache.commit()
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is None


def test_wholly_textless_cache_entry_reads_as_a_miss(cache):
    """Poison written before the write-side guard existed must not be served."""
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST,
                     [dec.Window(i, i * 100.0, i * 100.0 + 80.0, "") for i in range(3)])
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is None


def test_one_window_with_text_is_enough_to_serve(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST,
                     [dec.Window(0, 0.0, 80.0, ""), dec.Window(1, 100.0, 180.0, "hello")])
    assert len(dec.load_windows(cache, 212, MODEL, CT, PRE, POST)) == 2


def test_orphan_windows_without_a_run_row_read_as_a_miss(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    cache.execute("DELETE FROM bobtalk_decode_runs")
    cache.commit()
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is None


def test_summary_accounts_per_model_and_geometry(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows(3), decode_sec=3600.0)
    dec.save_windows(cache, 213, MODEL, CT, PRE, POST, _windows(2), decode_sec=1800.0)
    dec.save_windows(cache, 212, "base", CT, PRE, POST, _windows(1))
    rows = {r["model"]: r for r in dec.summary(cache)}
    assert rows[MODEL]["recordings"] == 2
    assert rows[MODEL]["windows"] == 5
    assert rows[MODEL]["decode_hours"] == pytest.approx(1.5)
    assert rows[MODEL]["chars"] > 0
    assert rows["base"]["recordings"] == 1


def test_prune_by_model_leaves_other_models_intact(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    dec.save_windows(cache, 212, "base", CT, PRE, POST, _windows())
    assert dec.prune(cache, model="base") == 1
    assert dec.load_windows(cache, 212, "base", CT, PRE, POST) is None
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is not None


def test_prune_by_lb_number(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    dec.save_windows(cache, 213, MODEL, CT, PRE, POST, _windows())
    assert dec.prune(cache, lb_numbers=[213]) == 1
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is not None
    assert dec.load_windows(cache, 213, MODEL, CT, PRE, POST) is None


def test_prune_with_empty_lb_list_is_a_no_op(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    assert dec.prune(cache, lb_numbers=[]) == 0
    assert dec.load_windows(cache, 212, MODEL, CT, PRE, POST) is not None


def test_prune_all_clears_both_tables(cache):
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    dec.save_windows(cache, 213, "base", CT, 10.0, 10.0, _windows())
    assert dec.prune(cache) == 2
    assert cache.execute("SELECT COUNT(*) FROM bobtalk_decode_windows").fetchone()[0] == 0
    assert cache.execute("SELECT COUNT(*) FROM bobtalk_decode_runs").fetchone()[0] == 0


def _stub_tapematch(monkeypatch, texts):
    """Install fake ``tapematch.asr``/``ingest`` modules yielding *texts* per window."""
    seq = list(texts)
    ingest = types.ModuleType("tapematch.ingest")
    ingest.concat_source = lambda *a, **k: (
        np.zeros(16000 * len(seq) * 100, dtype=np.float32), 16000,
        [16000 * 100 * i for i in range(len(seq))])
    asr = types.ModuleType("tapematch.asr")
    asr.load_model = lambda cfg: object()
    calls = {"n": 0}

    def transcribe_gaps(mono, sr, gaps, cfg, model=None):
        text = seq[calls["n"]] if calls["n"] < len(seq) else ""
        calls["n"] += 1
        return [types.SimpleNamespace(text=text)] if text else []

    asr.transcribe_gaps = transcribe_gaps
    pkg = types.ModuleType("tapematch")
    pkg.asr, pkg.ingest = asr, ingest
    monkeypatch.setitem(sys.modules, "tapematch", pkg)
    monkeypatch.setitem(sys.modules, "tapematch.asr", asr)
    monkeypatch.setitem(sys.modules, "tapematch.ingest", ingest)


def test_a_fully_empty_decode_raises_and_caches_nothing(cache, monkeypatch):
    """A dead decoder returns cleanly per window; that must not read as silence.

    ``transcribe_gaps`` swallows per-window failures, so a missing CUDA library
    yields a clean run of empty windows. Caching that, or letting it replace
    stored locations, is the TODO-293 silent-failure shape all over again.
    """
    _stub_tapematch(monkeypatch, ["", "", ""])
    cfg = {"model": "large-v3", "device": "cuda", "compute_type": "float16"}
    with pytest.raises(RuntimeError, match="no text"):
        loc.decode_windows(212, "/nonexistent", cfg, [".flac"], "large-v3", cache)
    assert dec.load_windows(cache, 212, "large-v3", "float16",
                            loc.PRE_SEC, loc.POST_SEC) is None


def test_a_partly_empty_decode_is_kept(cache, monkeypatch):
    """Quiet windows are normal; only a wholly textless recording is a failure."""
    _stub_tapematch(monkeypatch, ["", "thank you friends", ""])
    cfg = {"model": "large-v3", "device": "cpu", "compute_type": "int8"}
    got = loc.decode_windows(212, "/nonexistent", cfg, [".flac"], "large-v3", cache)
    assert len(got) == 3
    assert dec.load_windows(cache, 212, "large-v3", "int8",
                            loc.PRE_SEC, loc.POST_SEC) is not None


def test_cache_never_holds_olof_quote_text(cache):
    """The cache stores what WE heard, never Olof's curated text.

    Location rows reference ``olof_events.bobtalk`` by index on purpose; the
    cache must not become a second, drifting copy of that text.
    """
    dec.save_windows(cache, 212, MODEL, CT, PRE, POST, _windows())
    cols = {r[1] for r in cache.execute("PRAGMA table_info(bobtalk_decode_windows)")}
    assert "quote_index" not in cols and "quote" not in cols
