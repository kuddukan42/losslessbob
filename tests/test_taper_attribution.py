"""Tests for backend.taper_attribution: Layer 0 seeding, Layer 1 propagation,
conflict detection, taper_confirmations (confirm/reject), idempotency, and
the Phase 2 curator confirm/reject HTTP API.
"""
import json
import os
import shutil
import tempfile

import backend.db as db
import backend.paths as _paths
import backend.taper_attribution as taper_attribution


def _make_db():
    tmp_dir = tempfile.mkdtemp(prefix="lb_taper_attr_test_")
    db_path = os.path.join(tmp_dir, "test.db")
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)
    db.init_db(db_path)
    return db_path, tmp_dir


def _seed_entry(conn, lb, description, taper_name=None, taper_normalised=None,
                 same_as=None, derived_from=None):
    """Insert matching entries + entry_lineage rows, bypassing real text parsing
    so tests can exercise Layer 0/1 logic against controlled inputs."""
    conn.execute(
        "INSERT OR REPLACE INTO entries(lb_number, description) VALUES (?, ?)",
        (lb, description),
    )
    conn.execute(
        """INSERT OR REPLACE INTO entry_lineage
           (lb_number, taper_name, source_chain, taper_normalised, mentions_lb,
            same_as_lb, derived_from_lb, better_than_lb, parse_confidence, source_text_hash)
           VALUES (?, ?, NULL, ?, '[]', ?, ?, '[]', 'medium', 'test')""",
        (lb, taper_name, taper_normalised,
         json.dumps(same_as or []), json.dumps(derived_from or [])),
    )
    conn.commit()


def _seed_family(conn, fam_id, concert_date, members, review_flag=0):
    conn.executemany(
        "INSERT OR REPLACE INTO recording_families(lb_number, fam_id, concert_date)"
        " VALUES (?, ?, ?)",
        [(lb, fam_id, concert_date) for lb in members],
    )
    conn.execute(
        """INSERT OR REPLACE INTO tapematch_family_meta
           (fam_id, concert_date, member_count, review_flag) VALUES (?, ?, ?, ?)""",
        (fam_id, concert_date, len(members), review_flag),
    )
    conn.commit()


def _get_attr(conn, lb):
    row = conn.execute("SELECT * FROM taper_attributions WHERE lb_number = ?", (lb,)).fetchone()
    return dict(row) if row else None


# ── Layer 0 ────────────────────────────────────────────────────────────────────

def test_layer0_explicit_label_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 100, "Taper: Spot\nSource: Schoeps > DAT > FLAC",
                taper_name="spot", taper_normalised="spot")

    stats = taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 100)
    assert row is not None
    assert row["confidence"] == "confirmed"
    assert row["taper_normalised"] == "spot"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "explicit" for e in evidence)
    assert stats["confirmed"] == 1


def test_layer0_series_code_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 101, "LTB, DAT > FLAC, no further info.",
                taper_name="ltb", taper_normalised="ltb")

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 101)
    assert row["confidence"] == "confirmed"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "series_code" for e in evidence)


def test_layer0_bare_mention_propagated():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 102, "Great show, thanks to spot for the tape.",
                taper_name="spot", taper_normalised="spot")

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 102)
    assert row["confidence"] == "propagated"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "mention" for e in evidence)


def test_unknown_taper_not_seeded():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 103, "Taper: J. Random Fan\nSource: unknown",
                taper_name="j random fan", taper_normalised="j random fan")

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 103) is None


def test_dolphinsmile_excluded_from_universe():
    assert "dolphinsmile" not in taper_attribution._TAPER_UNIVERSE

    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 104, "Taper: dolphinsmile\nSource: X",
                taper_name="dolphinsmile", taper_normalised="dolphinsmile")

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 104) is None


# ── Layer 1 propagation ────────────────────────────────────────────────────────

def test_layer1_family_propagation():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 200, "Taper: Spot\nSource: Schoeps > DAT",
                taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 201, "Audience recording, no taper info given.")
    _seed_entry(conn, 202, "Another copy, no taper listed.")
    _seed_family(conn, "F1", "1975-01-01", [200, 201, 202])

    taper_attribution.recompute(db_path=db_path)

    for lb in (201, 202):
        row = _get_attr(conn, lb)
        assert row is not None, f"LB-{lb} should have been propagated"
        assert row["confidence"] == "propagated"
        assert row["taper_normalised"] == "spot"
        assert row["conflict"] == 0
        evidence = json.loads(row["evidence_json"])
        assert any(e["kind"] == "family" and e.get("fam_id") == "F1" for e in evidence)

    # confirmed row itself is untouched
    row200 = _get_attr(conn, 200)
    assert row200["confidence"] == "confirmed"


def test_layer1_same_as_and_derived_from():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 300, "Taper: Hide\nSource: Neumann > DAT",
                taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 301, "Exact same recording as LB-300.", same_as=[300])
    _seed_entry(conn, 302, "Transferred from LB-300 master.", derived_from=[300])

    taper_attribution.recompute(db_path=db_path)

    row301 = _get_attr(conn, 301)
    assert row301["taper_normalised"] == "hide"
    assert row301["confidence"] == "propagated"
    assert any(e["kind"] == "same_as" for e in json.loads(row301["evidence_json"]))

    row302 = _get_attr(conn, 302)
    assert row302["taper_normalised"] == "hide"
    assert any(e["kind"] == "derived_from" for e in json.loads(row302["evidence_json"]))


def test_layer1_multi_hop_propagation():
    """Propagated nodes push too (spec §4.2): confirmed -> A -> B via two hops."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 400, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 401, "No taper info.", same_as=[400])
    _seed_entry(conn, 402, "No taper info either.", same_as=[401])

    taper_attribution.recompute(db_path=db_path)

    row402 = _get_attr(conn, 402)
    assert row402 is not None
    assert row402["taper_normalised"] == "spot"
    assert row402["confidence"] == "propagated"


# ── Conflicts ──────────────────────────────────────────────────────────────────

def test_conflict_two_confirmed_tapers_in_family():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 500, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 501, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 502, "No taper info.")
    _seed_family(conn, "F2", "1976-01-01", [500, 501, 502])

    stats = taper_attribution.recompute(db_path=db_path)

    row500 = _get_attr(conn, 500)
    row501 = _get_attr(conn, 501)
    assert row500["confidence"] == "confirmed" and row500["conflict"] == 0
    assert row501["confidence"] == "confirmed" and row501["conflict"] == 0

    row502 = _get_attr(conn, 502)
    assert row502 is not None
    assert row502["conflict"] == 1
    evidence = json.loads(row502["evidence_json"])
    candidates = {e["detail"] for e in evidence if e["kind"] == "conflict"}
    assert any("spot" in d for d in candidates)
    assert any("hide" in d for d in candidates)
    assert stats["conflict"] == 1


def test_weak_edge_does_not_override_strong_resolution():
    """A review-flagged (weak) family with a candidate taper must not touch a
    node the strong pass already resolved (spec: weak loses to strong, no conflict)."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 600, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 601, "No taper info.", same_as=[600])  # strong: resolves to spot
    _seed_entry(conn, 602, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    # Weak (review-flagged) family linking the already-strong-resolved 601 to 602 (hide).
    _seed_family(conn, "F3-weak", "1977-01-01", [601, 602], review_flag=1)

    taper_attribution.recompute(db_path=db_path)

    row601 = _get_attr(conn, 601)
    assert row601["taper_normalised"] == "spot"
    assert row601["conflict"] == 0


# ── taper_confirmations (MASTER, F2) ───────────────────────────────────────────

def test_confirmation_is_sticky_confirmed():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 700, "Plain audience recording, no taper info at all.")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (700, "spot", "confirm"),
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 700)
    assert row["confidence"] == "confirmed"
    assert row["taper_normalised"] == "spot"
    assert row["confirmed_at"] is not None
    assert any(e["kind"] == "confirmation" for e in json.loads(row["evidence_json"]))


def test_rejection_suppresses_output():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 701, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (701, "spot", "reject"),
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    assert _get_attr(conn, 701) is None


def test_rejection_does_not_suppress_different_taper():
    """A reject on (lb, taper=X) must not block a legitimately different taper Y
    for the same lb — only the specific rejected pair is suppressed."""
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 702, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (702, "spot", "reject"),  # rejects a taper this entry doesn't even have
    )
    conn.commit()

    taper_attribution.recompute(db_path=db_path)

    row = _get_attr(conn, 702)
    assert row is not None
    assert row["taper_normalised"] == "hide"


# ── Idempotency (spec §7) ───────────────────────────────────────────────────────

def test_idempotent_rerun():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 800, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 801, "No taper info.", same_as=[800])
    _seed_entry(conn, 802, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 803, "No taper info.")
    _seed_family(conn, "F4", "1978-01-01", [802, 803])
    conn.execute(
        "INSERT INTO taper_confirmations(lb_number, taper_normalised, action) VALUES (?, ?, ?)",
        (900, "mjs", "confirm"),
    )
    _seed_entry(conn, 900, "No taper info.")

    stats1 = taper_attribution.recompute(db_path=db_path)
    rows1 = {
        r["lb_number"]: (r["taper_normalised"], r["confidence"], r["conflict"])
        for r in conn.execute("SELECT * FROM taper_attributions")
    }

    stats2 = taper_attribution.recompute(db_path=db_path)
    rows2 = {
        r["lb_number"]: (r["taper_normalised"], r["confidence"], r["conflict"])
        for r in conn.execute("SELECT * FROM taper_attributions")
    }

    assert rows1 == rows2
    for key in ("total", "confirmed", "propagated", "inferred", "conflict"):
        assert stats1[key] == stats2[key], f"Mismatch on {key}: {stats1[key]} vs {stats2[key]}"


def test_dry_run_does_not_write():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1000, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")

    stats = taper_attribution.recompute(db_path=db_path, dry_run=True)

    assert stats["confirmed"] == 1
    assert _get_attr(conn, 1000) is None


def test_write_targets_db_path_not_queue_binding():
    """When the singleton queue is bound to another DB, the wholesale
    DELETE+reinsert of taper_attributions must still land in the recompute's
    db_path (BUG-246: first-init-wins queue caused reads and writes to split
    across databases, wiping the live table)."""
    import backend.db_queue as db_queue

    db_path_a, _ = _make_db()  # binds the queue (if this test runs first)
    db.init_db(db_path_a)
    queue_db = db_queue.get_write_queue().db_path

    db_path_b, _ = _make_db()
    assert str(queue_db) != str(db_path_b)  # queue still bound to its first DB
    conn_b = db.get_connection(db_path_b)
    _seed_entry(conn_b, 1300, "Taper: Spot\nSource: X",
                taper_name="spot", taper_normalised="spot")

    taper_attribution.recompute(db_path=db_path_b)

    in_b = conn_b.execute("SELECT COUNT(*) FROM taper_attributions").fetchone()[0]
    assert in_b == 1  # landed in the DB that was read from
    conn_q = db.get_connection(queue_db)
    in_q = conn_q.execute(
        "SELECT COUNT(*) FROM taper_attributions WHERE lb_number = 1300").fetchone()[0]
    assert in_q == 0  # and NOT in the queue's DB


# ── Phase 2 curator confirm/reject HTTP API ────────────────────────────────────

class _AppClient:
    """Context manager wiring backend.app's create_app() to a temp DB path,
    mirroring tests/test_library_picks_api.py's pattern.
    """

    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self._orig_db_path = _paths.DB_PATH
        self._orig_module_db_path = getattr(db, "DB_PATH", None)
        _paths.DB_PATH = self.db_path
        db.DB_PATH = self.db_path
        from backend.app import create_app
        app = create_app()
        return app.test_client()

    def __exit__(self, *exc):
        _paths.DB_PATH = self._orig_db_path
        if self._orig_module_db_path is not None:
            db.DB_PATH = self._orig_module_db_path


def _get_confirmation(conn, lb):
    row = conn.execute(
        "SELECT * FROM taper_confirmations WHERE lb_number = ?", (lb,)
    ).fetchone()
    return dict(row) if row else None


def test_confirm_route_sets_confirmed_and_records_confirmation():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1100, "Audience recording, no taper info given.")
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1100/confirm", json={"taper": "spot"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["lb_number"] == 1100
        assert body["attribution"]["taper_normalised"] == "spot"
        assert body["attribution"]["confidence"] == "confirmed"
        assert body["attribution"]["confirmed_at"] is not None
        assert any(e["kind"] == "confirmation" for e in body["attribution"]["evidence"])

    conf = _get_confirmation(conn, 1100)
    assert conf["action"] == "confirm"
    assert conf["taper_normalised"] == "spot"
    row = _get_attr(conn, 1100)
    assert row["confidence"] == "confirmed"

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_confirm_route_sources_taper_from_existing_attribution():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1101, "Great show, thanks to spot for the tape.",
                taper_name="spot", taper_normalised="spot")
    taper_attribution.recompute(db_path=db_path)  # seeds a 'propagated' row
    assert _get_attr(conn, 1101)["confidence"] == "propagated"
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1101/confirm", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["attribution"]["taper_normalised"] == "spot"
        assert body["attribution"]["confidence"] == "confirmed"

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_confirm_route_400_when_no_attribution_and_no_taper():
    db_path, tmp_dir = _make_db()
    _seed_entry(db.get_connection(db_path), 1102, "No taper info at all.")
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1102/confirm", json={})
        assert resp.status_code == 400

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_reject_route_deletes_matching_attribution_and_records_confirmation():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1103, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    taper_attribution.recompute(db_path=db_path)
    assert _get_attr(conn, 1103) is not None
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1103/reject", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["lb_number"] == 1103
        assert body["attribution"] is None

    conf = _get_confirmation(conn, 1103)
    assert conf["action"] == "reject"
    assert conf["taper_normalised"] == "spot"
    assert _get_attr(conn, 1103) is None

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_reconfirm_after_reject_overwrites_prior_decision():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1104, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    taper_attribution.recompute(db_path=db_path)
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1104/reject", json={})
        assert resp.status_code == 200
        assert resp.get_json()["attribution"] is None
        assert _get_confirmation(conn, 1104)["action"] == "reject"

        # Attribution row is gone, so the taper must be supplied explicitly.
        resp = client.post("/api/tapers/attributions/1104/confirm", json={"taper": "spot"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["attribution"]["confidence"] == "confirmed"
        assert body["attribution"]["taper_normalised"] == "spot"

    conf = _get_confirmation(conn, 1104)
    assert conf["action"] == "confirm"
    row = _get_attr(conn, 1104)
    assert row["confidence"] == "confirmed"

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_confirm_and_reject_routes_403_when_not_curator():
    db_path, tmp_dir = _make_db()
    _seed_entry(db.get_connection(db_path), 1105, "Taper: Spot\nSource: X",
                taper_name="spot", taper_normalised="spot")
    taper_attribution.recompute(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/attributions/1105/confirm", json={})
        assert resp.status_code == 403

        resp = client.post("/api/tapers/attributions/1105/reject", json={})
        assert resp.status_code == 403

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Phase 2 read API: GET single + filtered list (no curator gate) ────────────

def test_get_route_returns_null_when_no_attribution():
    db_path, tmp_dir = _make_db()
    _seed_entry(db.get_connection(db_path), 1200, "No taper info at all.")
    db.set_curator(False, db_path)  # explicitly non-curator: read route must not gate

    with _AppClient(db_path) as client:
        resp = client.get("/api/tapers/attributions/1200")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body == {"lb_number": 1200, "attribution": None}

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_get_route_returns_attribution_with_evidence():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1201, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    taper_attribution.recompute(db_path=db_path)
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/tapers/attributions/1201")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["lb_number"] == 1201
        assert body["attribution"]["taper_normalised"] == "spot"
        assert body["attribution"]["confidence"] == "confirmed"
        assert any(e["kind"] == "explicit" for e in body["attribution"]["evidence"])

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_route_filters_by_confidence_taper_and_conflict():
    db_path, tmp_dir = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 1300, "Taper: Spot\nSource: X", taper_name="spot", taper_normalised="spot")
    _seed_entry(conn, 1301, "Taper: Hide\nSource: Y", taper_name="hide", taper_normalised="hide")
    _seed_entry(conn, 1302, "No taper info.")
    _seed_family(conn, "F5", "1979-01-01", [1300, 1301, 1302])
    db.set_curator(False, db_path)

    taper_attribution.recompute(db_path=db_path)

    with _AppClient(db_path) as client:
        resp = client.get("/api/tapers/attributions")
        assert resp.status_code == 200
        all_rows = resp.get_json()["attributions"]
        lb_set = {r["lb_number"] for r in all_rows}
        assert {1300, 1301, 1302}.issubset(lb_set)
        assert all("evidence" in r and isinstance(r["evidence"], list) for r in all_rows)

        resp = client.get("/api/tapers/attributions?confidence=confirmed")
        confirmed_lbs = {r["lb_number"] for r in resp.get_json()["attributions"]}
        assert {1300, 1301}.issubset(confirmed_lbs)
        assert 1302 not in confirmed_lbs

        resp = client.get("/api/tapers/attributions?taper=spot")
        spot_rows = resp.get_json()["attributions"]
        assert all(r["taper_normalised"] == "spot" for r in spot_rows)
        assert 1300 in {r["lb_number"] for r in spot_rows}

        resp = client.get("/api/tapers/attributions?conflict=1")
        conflict_rows = resp.get_json()["attributions"]
        assert all(r["conflict"] == 1 for r in conflict_rows)
        assert 1302 in {r["lb_number"] for r in conflict_rows}

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_list_and_get_routes_no_curator_gate():
    """Read routes must return 200 (never 403) regardless of curator flag."""
    db_path, tmp_dir = _make_db()
    _seed_entry(db.get_connection(db_path), 1400, "No taper info at all.")
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        assert client.get("/api/tapers/attributions").status_code == 200
        assert client.get("/api/tapers/attributions/1400").status_code == 200

    shutil.rmtree(tmp_dir, ignore_errors=True)
