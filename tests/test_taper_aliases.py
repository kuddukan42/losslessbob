"""Tests for TODO-241: user_taper_aliases (add/remove known-taper handles
without a code edit) — schema idempotency, backend.db merge semantics
(reload_taper_aliases in-place identity, builtin suppression, user-add
universe membership), the /api/tapers/aliases HTTP routes, and one
integration test that a new handle gains an attribution after add + recompute.
"""
import json

import backend.db as db
import backend.taper_attribution as taper_attribution
from tests.test_taper_attribution import _AppClient, _get_attr, _make_db, _seed_entry

# ── Schema idempotency ─────────────────────────────────────────────────────────

def test_schema_idempotent_create_twice():
    db_path, _ = _make_db()
    db.init_db(db_path)  # second call must not raise (CREATE TABLE IF NOT EXISTS)
    conn = db.get_connection(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(user_taper_aliases)").fetchall()}
    assert cols == {"alias_norm", "canonical", "action", "approved", "note",
                    "created_at", "updated_at"}


# ── backend.db merge semantics ─────────────────────────────────────────────────

def test_add_alias_appears_in_merged_dict_and_universe():
    db_path, _ = _make_db()
    assert "brandnewtaper" not in db._KNOWN_TAPER_ALIASES

    row = db.add_taper_alias("BrandNewTaper", "brandnewtaper", db_path=db_path)
    assert row["alias_norm"] == "brandnewtaper"
    assert row["canonical"] == "brandnewtaper"
    assert row["action"] == "add"

    assert db._KNOWN_TAPER_ALIASES["brandnewtaper"] == "brandnewtaper"
    assert "brandnewtaper" in db._TAPER_UNIVERSE


def test_remove_builtin_suppresses_from_merged_dict_and_universe():
    db_path, _ = _make_db()
    assert "spot" in db._KNOWN_TAPER_ALIASES
    assert "spot" in db._TAPER_UNIVERSE

    result = db.remove_taper_alias("spot", db_path=db_path)
    assert result == "suppressed"

    assert "spot" not in db._KNOWN_TAPER_ALIASES
    assert "spot" not in db._TAPER_UNIVERSE
    # Builtin literal table itself is untouched (code, not data).
    assert db._BUILTIN_TAPER_ALIASES["spot"] == "spot"


def test_remove_user_add_row_deletes_outright():
    db_path, _ = _make_db()
    db.add_taper_alias("brandnewtaper", "brandnewtaper", db_path=db_path)
    assert "brandnewtaper" in db._KNOWN_TAPER_ALIASES

    result = db.remove_taper_alias("brandnewtaper", db_path=db_path)
    assert result == "deleted"
    assert "brandnewtaper" not in db._KNOWN_TAPER_ALIASES

    conn = db.get_connection(db_path)
    row = conn.execute(
        "SELECT * FROM user_taper_aliases WHERE alias_norm = ?", ("brandnewtaper",)
    ).fetchone()
    assert row is None


def test_remove_unknown_alias_raises_keyerror():
    db_path, _ = _make_db()
    try:
        db.remove_taper_alias("totallymadeupnothere", db_path=db_path)
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_reload_mutates_known_taper_aliases_in_place():
    """A reference captured before reload must see the update afterward — the
    whole point of TODO-241's in-place mutation (rather than reassignment),
    since backend.taper_attribution / backend.taper_fingerprints import
    _KNOWN_TAPER_ALIASES by name at their own module top level.
    """
    db_path, _ = _make_db()
    ref = db._KNOWN_TAPER_ALIASES  # captured BEFORE the reload below
    assert "brandnewtaper" not in ref

    db.add_taper_alias("brandnewtaper", "brandnewtaper", db_path=db_path)

    assert ref is db._KNOWN_TAPER_ALIASES  # same object, not reassigned
    assert "brandnewtaper" in ref  # and the captured reference sees the update


def test_taper_attribution_alias_index_rebuilds_from_user_add():
    """_ALIAS_KEYS_BY_CANONICAL (mention-snippet reverse index) picks up a new
    user alias once _rebuild_alias_index() runs (called at the top of every
    recompute()).
    """
    db_path, _ = _make_db()
    db.add_taper_alias("brandnewtaper", "brandnewtaper", db_path=db_path)
    taper_attribution._rebuild_alias_index()
    assert "brandnewtaper" in taper_attribution._ALIAS_KEYS_BY_CANONICAL["brandnewtaper"]


def test_taper_attribution_taper_universe_forwards_live_value():
    """taper_attribution._TAPER_UNIVERSE (module __getattr__ forwarding) must
    reflect a reload, not a value bound at import time.
    """
    db_path, _ = _make_db()
    assert "spot" in taper_attribution._TAPER_UNIVERSE
    db.remove_taper_alias("spot", db_path=db_path)
    assert "spot" not in taper_attribution._TAPER_UNIVERSE


# ── HTTP API ────────────────────────────────────────────────────────────────────

def test_api_add_list_delete_alias():
    db_path, tmp_dir = _make_db()
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/aliases",
                            json={"alias": "MySoundMan", "canonical": "mysoundman",
                                  "note": "curator-added 2026-07-16"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["alias"]["alias_norm"] == "mysoundman"
        assert body["alias"]["canonical"] == "mysoundman"

        resp = client.get("/api/tapers/aliases")
        assert resp.status_code == 200
        listing = resp.get_json()
        aliases = {e["alias"]: e for e in listing["entries"]}
        assert aliases["mysoundman"]["origin"] == "user"
        assert listing["counts"]["user_add"] == 1

        resp = client.delete("/api/tapers/aliases/mysoundman")
        assert resp.status_code == 200
        assert resp.get_json()["result"] == "deleted"

        resp = client.get("/api/tapers/aliases")
        aliases = {e["alias"]: e for e in resp.get_json()["entries"]}
        assert "mysoundman" not in aliases

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_delete_builtin_suppresses_and_shows_in_suppressed_list():
    db_path, tmp_dir = _make_db()
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.delete("/api/tapers/aliases/spot")
        assert resp.status_code == 200
        assert resp.get_json()["result"] == "suppressed"

        resp = client.get("/api/tapers/aliases")
        listing = resp.get_json()
        assert "spot" in listing["suppressed"]
        assert not any(e["alias"] == "spot" for e in listing["entries"])

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_delete_unknown_alias_404():
    db_path, tmp_dir = _make_db()
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.delete("/api/tapers/aliases/totallymadeupnothere")
        assert resp.status_code == 404

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_add_requires_curator():
    db_path, tmp_dir = _make_db()
    db.set_curator(False, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/aliases", json={"alias": "x", "canonical": "y"})
        assert resp.status_code == 403

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_api_add_400_on_empty_fields():
    db_path, tmp_dir = _make_db()
    db.set_curator(True, db_path)

    with _AppClient(db_path) as client:
        resp = client.post("/api/tapers/aliases", json={"alias": "", "canonical": "y"})
        assert resp.status_code == 400

        resp = client.post("/api/tapers/aliases", json={"alias": "!!!", "canonical": "y"})
        assert resp.status_code == 400  # normalises to empty string

    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Integration: new handle gains an attribution after add + recompute ────────

def test_new_handle_gains_attribution_after_add_and_recompute():
    db_path, _ = _make_db()
    conn = db.get_connection(db_path)
    _seed_entry(conn, 9001, "Taper: Brandnewtaper\nSource: DAT > FLAC",
                taper_name="brandnewtaper", taper_normalised="brandnewtaper")

    # Before the alias exists, "brandnewtaper" isn't in the known-taper
    # universe, so Layer 0 seeding won't create an attribution for it.
    taper_attribution.recompute(db_path=db_path)
    assert _get_attr(conn, 9001) is None

    db.add_taper_alias("brandnewtaper", "brandnewtaper", db_path=db_path)

    taper_attribution.recompute(db_path=db_path)
    row = _get_attr(conn, 9001)
    assert row is not None
    assert row["taper_normalised"] == "brandnewtaper"
    evidence = json.loads(row["evidence_json"])
    assert any(e["kind"] == "explicit" for e in evidence)
