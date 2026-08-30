"""Tests for the taper curation workbench read model (backend.taper_curation).

All tests use a temp-file DB — the real data/losslessbob.db is never touched.
"""
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def curation():
    """Yield (module, db_path) bound to a throwaway database with fixture rows."""
    tmp_dir = tempfile.mkdtemp(prefix="lbcuration_test_")
    db_path = os.path.join(tmp_dir, "test.db")

    import backend.paths as _paths
    _paths.DATA_DIR = type(_paths.DATA_DIR)(tmp_dir)

    import backend.db as db
    from backend import taper_curation as tc
    db.init_db(db_path)
    conn = db.get_connection(db_path)
    with conn:
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, location, description,"
            " taper_name, source_chain, status) VALUES"
            " (1, '10/7/78', 'Providence', 'taped by spot, thanks to jtt for the transfer',"
            "  'spot', 'AUD > DAT', 'ok')")
        conn.execute(
            "INSERT INTO entries (lb_number, date_str, location, description,"
            " taper_name, status) VALUES"
            " (2, '11/1/78', 'Madison', 'nothing useful here', 'wobblycandidate', 'ok')")
        conn.execute(
            "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
            " evidence_json, conflict) VALUES (1, 'spot', 'confirmed', '[]', 0)")
        conn.execute(
            "INSERT INTO entry_lineage (lb_number, taper_name, taper_normalised)"
            " VALUES (2, 'wobblycandidate', 'wobblycandidate')")
        conn.execute(
            "INSERT INTO tuit_recordings (rec_id, lb_number, taper, source_type, quality)"
            " VALUES (10, 1, 'spot', 'AUD', 'Very good')")
        conn.execute(
            "INSERT INTO tuit_recordings (rec_id, lb_number, taper, source_type)"
            " VALUES (11, 2, 'unknown', 'AUD')")
    try:
        yield tc, db_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


class TestNormalisation:
    """canonical() / is_placeholder() / exclusion_reason()."""

    def test_placeholder_text_is_not_a_taper(self, curation):
        tc, _ = curation
        assert tc.is_placeholder("Unknown") is True
        assert tc.canonical("unknown") == ""
        assert tc.is_placeholder("spot") is False

    def test_builtin_not_taper_is_flagged(self, curation):
        tc, _ = curation
        assert tc.exclusion_reason("jtt") == "not_taper_builtin"

    def test_unrecognised_text_is_unknown(self, curation):
        tc, _ = curation
        assert tc.exclusion_reason("wobblycandidate") == "unknown_text"

    def test_known_taper_has_no_reason(self, curation):
        tc, _ = curation
        assert tc.exclusion_reason("spot") is None


class TestAgreement:
    """The derived cross-source verdict."""

    def test_all_named_alike_agrees(self, curation):
        tc, _ = curation
        assert tc.agreement("spot", "spot", "spot", True) == "agree"

    def test_differing_names_conflict(self, curation):
        tc, _ = curation
        assert tc.agreement("spot", "bach", "", True) == "conflict"

    def test_tuit_alone_is_new_evidence(self, curation):
        tc, _ = curation
        assert tc.agreement("", "spot", "", True) == "tuit_only"

    def test_nothing_scraped_says_so(self, curation):
        tc, _ = curation
        assert tc.agreement("", "", "", False) == "not_scraped"


class TestListRows:
    """The paged wide join."""

    def test_row_carries_every_source(self, curation):
        tc, db_path = curation
        row = tc.list_rows(q="1", db_path=db_path)["rows"][0]
        assert row["lb_number"] == 1
        assert row["attribution"]["taper"] == "spot"
        assert row["tuit"]["taper"] == "spot"
        assert row["entry"]["taper_name"] == "spot"
        assert row["agreement"] == "agree"

    def test_unscraped_entry_has_no_tuit_block(self, curation):
        tc, db_path = curation
        conn_rows = tc.list_rows(tuit="not_scraped", db_path=db_path)["rows"]
        assert all(r["tuit"] is None for r in conn_rows)

    def test_placeholder_tag_is_not_has_taper(self, curation):
        tc, db_path = curation
        lbs = [r["lb_number"] for r in tc.list_rows(tuit="has_taper", db_path=db_path)["rows"]]
        assert lbs == [1]  # LB-2's TUIT tag is the literal 'unknown'

    def test_candidates_report_barred_names(self, curation):
        tc, db_path = curation
        row = tc.list_rows(q="1", db_path=db_path)["rows"][0]
        by_canon = {c["canonical"]: c["status"] for c in row["candidates"]}
        assert by_canon.get("spot") == "known"
        assert by_canon.get("jtt") == "not_taper_builtin"

    def test_bad_sort_rejected(self, curation):
        tc, db_path = curation
        with pytest.raises(ValueError):
            tc.list_rows(sort="nonsense", db_path=db_path)

    def test_bad_tuit_filter_rejected(self, curation):
        tc, db_path = curation
        with pytest.raises(ValueError):
            tc.list_rows(tuit="sideways", db_path=db_path)


class TestIsolatedTexts:
    """Both isolated-text populations."""

    def test_unknown_text_is_grouped(self, curation):
        tc, db_path = curation
        groups = tc.isolated_texts(kind="unknown", db_path=db_path)["groups"]
        assert any(g["canonical"] == "wobblycandidate" and g["count"] == 1 for g in groups)

    def test_excluded_scan_finds_barred_mention(self, curation):
        tc, db_path = curation
        groups = tc.isolated_texts(kind="excluded", refresh=True, db_path=db_path)["groups"]
        jtt = next(g for g in groups if g["canonical"] == "jtt")
        assert jtt["reason"] == "not_taper_builtin"
        assert jtt["sample_lbs"] == [1]

    def test_bad_kind_rejected(self, curation):
        tc, db_path = curation
        with pytest.raises(ValueError):
            tc.isolated_texts(kind="whatever", db_path=db_path)


class TestRollupAndText:
    """taper_rollup() and text_hits()."""

    def test_rollup_counts_both_sides(self, curation):
        tc, db_path = curation
        spot = next(r for r in tc.taper_rollup(db_path=db_path) if r["taper"] == "spot")
        assert spot["attributed"] == 1
        assert spot["confirmed"] == 1
        assert spot["tuit"] == 1
        assert spot["in_universe"] is True

    def test_text_hits_returns_snippets(self, curation):
        tc, db_path = curation
        hits = tc.text_hits(1, "spot", db_path=db_path)
        assert hits and "spot" in hits[0]

    def test_text_hits_on_missing_entry_is_empty(self, curation):
        tc, db_path = curation
        assert tc.text_hits(999, "spot", db_path=db_path) == []
