"""Tests for emb_live.py (TODO-200): live-session population of
``pairs.emb_score`` / ``pairs.emb_score_global`` for ``addon_links.rule_d``.

Covers:
- (a) scoring path: synthesized small npz caches -> expected emb columns on the
  session's pairs row;
- (b) missing ``.venv-nmfp`` -> no crash, rows stay NULL;
- (c) a non-NULL emb value is never overwritten with NULL;
- (d) disabled flags (``enabled`` or ``live_embed`` off) -> no-op.

No TensorFlow / audio: caches are hand-written npz, extraction is forced down its
missing-venv branch, and scores come from ``emb_score_pairs.score_pair`` on those
caches (numpy only).
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import emb_live  # noqa: E402

PAIRS_SCHEMA = """
CREATE TABLE pairs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    concert_date     TEXT NOT NULL,
    lb_a             INTEGER,
    lb_b             INTEGER,
    emb_score        REAL,
    emb_score_global REAL
);
"""

DATE = "1990-06-01"
RUN_ID = "20260704_000000"


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(PAIRS_SCHEMA)
    return conn


def _insert_pair(conn: sqlite3.Connection, lb_a: int, lb_b: int,
                 emb=None, emb_g=None) -> None:
    conn.execute(
        "INSERT INTO pairs (run_id, concert_date, lb_a, lb_b, emb_score, "
        "emb_score_global) VALUES (?,?,?,?,?,?)",
        (RUN_ID, DATE, lb_a, lb_b, emb, emb_g),
    )
    conn.commit()


def _write_cache(cache_dir: Path, lb: int, seed: int = 0) -> None:
    """Write a small deterministic npz so cosine-max between any two is 1.0."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(128).astype(np.float32)
    emb = np.tile(v, (3, 1)).astype(np.float32)      # 3 identical windows
    t = np.array([0.0, 1.0, 2.0], dtype=np.float32)  # aligned within tol=2s
    d = cache_dir / DATE
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / f"LB{lb}.npz", emb=emb, t=t)


def _write_config(tmp_path: Path, *, enabled: bool = True,
                  live_embed: bool = True) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "addon_links:\n"
        "  rule_d:\n"
        f"    enabled: {str(enabled).lower()}\n"
        "    t_emb: 0.75\n"
        f"    live_embed: {str(live_embed).lower()}\n"
    )
    return cfg


def _sources(*lbs: int) -> list[dict]:
    return [{"lb": lb, "folder": f"{DATE} X (LB-{lb:05d})",
             "trim_head_sec": 0.0, "perf_dur_sec": 100.0,
             "total_dur_sec": 100.0, "speed_ppm": 0.0} for lb in lbs]


def test_scoring_path_populates_columns(tmp_path, monkeypatch):
    """(a) Cached embeddings -> emb_score/emb_score_global written on the row."""
    cache_dir = tmp_path / "embed_cache"
    _write_cache(cache_dir, 100, seed=1)
    _write_cache(cache_dir, 200, seed=2)
    cfg = _write_config(tmp_path)
    # Two identical unit-vector sources -> cosine 1.0 for both conventions.
    _write_cache(cache_dir, 100, seed=7)
    _write_cache(cache_dir, 200, seed=7)

    conn = _make_conn()
    _insert_pair(conn, 100, 200)
    counts = emb_live.populate_live_emb_scores(
        conn, RUN_ID, DATE, _sources(100, 200),
        config_path=cfg, cache_dir=cache_dir)

    assert counts["status"] == "ok"
    row = conn.execute(
        "SELECT emb_score, emb_score_global FROM pairs "
        "WHERE run_id=? AND lb_a=100 AND lb_b=200", (RUN_ID,)).fetchone()
    assert row[0] is not None and row[1] is not None
    # Identical unit vectors -> cosine 1.0 (float32 rounding), well above t_emb.
    assert row[0] == pytest.approx(1.0, abs=1e-4)
    assert row[1] == pytest.approx(1.0, abs=1e-4)


def test_missing_venv_leaves_null(tmp_path, monkeypatch):
    """(b) No cache + absent .venv-nmfp -> no crash, columns stay NULL."""
    cache_dir = tmp_path / "embed_cache"  # empty: every source is a cache miss
    cfg = _write_config(tmp_path)
    monkeypatch.setattr(emb_live, "VENV_NMFP_PY", tmp_path / "nope" / "python")

    conn = _make_conn()
    _insert_pair(conn, 100, 200)
    counts = emb_live.populate_live_emb_scores(
        conn, RUN_ID, DATE, _sources(100, 200),
        config_path=cfg, cache_dir=cache_dir)

    assert counts["status"] == "ok"
    row = conn.execute(
        "SELECT emb_score, emb_score_global FROM pairs WHERE run_id=?",
        (RUN_ID,)).fetchone()
    assert row[0] is None and row[1] is None


def test_null_never_overwrites_non_null(tmp_path, monkeypatch):
    """(c) A pre-existing non-NULL emb value survives an unscorable re-run."""
    cache_dir = tmp_path / "embed_cache"  # empty -> new scores are None
    cfg = _write_config(tmp_path)
    monkeypatch.setattr(emb_live, "VENV_NMFP_PY", tmp_path / "nope" / "python")

    conn = _make_conn()
    _insert_pair(conn, 100, 200, emb=0.91, emb_g=0.83)
    emb_live.populate_live_emb_scores(
        conn, RUN_ID, DATE, _sources(100, 200),
        config_path=cfg, cache_dir=cache_dir)

    row = conn.execute(
        "SELECT emb_score, emb_score_global FROM pairs WHERE run_id=?",
        (RUN_ID,)).fetchone()
    assert row[0] == 0.91 and row[1] == 0.83


def test_disabled_flags_are_no_op(tmp_path, monkeypatch):
    """(d) rule_d.live_embed=false (and enabled=false) -> no work, no writes."""
    cache_dir = tmp_path / "embed_cache"
    _write_cache(cache_dir, 100, seed=7)
    _write_cache(cache_dir, 200, seed=7)

    # If extraction/scoring ran, it would touch the row; assert it does not.
    def _boom(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("scoring ran while disabled")

    monkeypatch.setattr(emb_live, "_score_and_write", _boom)

    for enabled, live in ((True, False), (False, True), (False, False)):
        cfg = _write_config(tmp_path, enabled=enabled, live_embed=live)
        conn = _make_conn()
        _insert_pair(conn, 100, 200)
        counts = emb_live.populate_live_emb_scores(
            conn, RUN_ID, DATE, _sources(100, 200),
            config_path=cfg, cache_dir=cache_dir)
        assert counts["status"] == "disabled"
        row = conn.execute(
            "SELECT emb_score, emb_score_global FROM pairs WHERE run_id=?",
            (RUN_ID,)).fetchone()
        assert row[0] is None and row[1] is None
