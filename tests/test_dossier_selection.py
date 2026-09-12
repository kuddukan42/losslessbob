"""Tests for the C27 §8 selection rules (TODO-342 dossier redesign, Phase 5, C27).

Covers each rule's pass and fail case: fragments (§8.2, incl. the glued guard),
the verdict pick (best ``pick_rank`` among ``"primary"`` sources), collapse
(§8.3, ``sources.visible_n``), families (§8.4, band size + taper-label
eligibility) and tape wording (§8.4 last bullet, "N tape groups" only when
every visible source is tapematch-analysed).
"""
from __future__ import annotations

import sqlite3

from backend import dossier_anchors as da
from backend import dossier_fields as df
from tests.test_dossier import (
    _insert_entry,
    _insert_event,
    _insert_family,
    _insert_song,
    _insert_song_performance,
    _make_db,
)

# ---------------------------------------------------------------------------
# §8.2 fragments -- pure unit tests over backend.dossier_fields.is_fragment
# ---------------------------------------------------------------------------


def _comp(basis="tracklist", present=None, total=None, glued=False):
    return df.Completeness(
        lb_number=1, basis=basis, songs_present=present, songs_total=total,
        missing=[], partial=[], extra=[], runtime=None, confidence="stated",
        tuit_present=None, fits_show=True, show_bar=False, glued=glued,
    )


class TestIsFragment:
    def test_below_threshold_is_a_fragment(self):
        assert df.is_fragment(_comp(present=5, total=10), None, None)  # 50% < 60%

    def test_at_or_above_threshold_is_not_a_fragment(self):
        assert not df.is_fragment(_comp(present=6, total=10), None, None)  # 60%
        assert not df.is_fragment(_comp(present=10, total=10), None, None)

    def test_glued_ignores_completeness_and_falls_back_to_runtime(self):
        # 0% complete, but glued -- and the runtime clears the bar, so not a fragment.
        comp = _comp(present=0, total=10, glued=True)
        assert not df.is_fragment(comp, 59.0, 60.0)  # 59/60 ~= 98%

    def test_glued_with_no_runtime_data_is_not_a_fragment(self):
        # Can't judge a glued tracklist without a runtime to compare -- not asserted either way.
        comp = _comp(present=0, total=10, glued=True)
        assert not df.is_fragment(comp, None, None)

    def test_runtime_rule_below_threshold_is_a_fragment(self):
        assert df.is_fragment(None, 30.0, 100.0)  # 30% of median

    def test_runtime_rule_at_or_above_threshold_is_not_a_fragment(self):
        assert not df.is_fragment(None, 60.0, 100.0)

    def test_no_data_at_all_is_not_a_fragment(self):
        assert not df.is_fragment(None, None, None)
        assert not df.is_fragment(_comp(basis=None), None, None)


class TestExtraHasInlineNumbering:
    def test_single_marker_in_an_unmatched_title_is_glued(self):
        assert df._extra_has_inline_numbering(["Lenny Bruce 10 Ballad Of A Thin Man"])

    def test_plain_title_is_not_glued(self):
        assert not df._extra_has_inline_numbering(["Forever Young", "Like A Rolling Stone"])


# ---------------------------------------------------------------------------
# §8.2 group classification end to end (backend.dossier_anchors._classify_sources)
# ---------------------------------------------------------------------------


def _selection_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE olof_songs (event_id INTEGER, position INTEGER, song_title TEXT,
                                 subtitle TEXT);
        CREATE TABLE entries (lb_number INTEGER, setlist TEXT, timing TEXT);
        CREATE TABLE tuit_recordings (rec_id INTEGER PRIMARY KEY, lb_number INTEGER,
                                      setlist_json TEXT);
    """)
    songs = ["Song One", "Song Two", "Song Three", "Song Four", "Song Five"]
    conn.executemany(
        "INSERT INTO olof_songs VALUES (1, ?, ?, '')", list(enumerate(songs, start=1)))
    conn.executemany("INSERT INTO entries VALUES (?, ?, ?)", [
        # Full tracklist, all 5 songs -- primary.
        (1, "1. Song One, 2. Song Two, 3. Song Three, 4. Song Four, 5. Song Five", "60min"),
        # Only 2/5 songs -- below 60%, a genuine fragment.
        (2, "1. Song One, 2. Song Two", "20min"),
        # A glued (unsplit) tracklist reading as 0 matched songs, but a near-full runtime.
        (3, "1. Song One 2. Song Two 3. Song Three 4. Song Four", "58min"),
        # Misdated compilation: no overlap with the setlist -- fails G2.
        (4, "1. Unrelated Track One, 2. Unrelated Track Two, 3. Unrelated Track Three", "50min"),
    ])
    return conn


def _visible_members_for(lbs):
    return [(lb, {"timing": None}, {}) for lb in lbs]


class TestClassifySources:
    def test_full_tracklist_is_primary(self):
        conn = _selection_db()
        vm = [
            (lb, {"timing": r[0]}, {}) for lb, r in (
                (1, conn.execute("SELECT timing FROM entries WHERE lb_number=1").fetchone()),
                (2, conn.execute("SELECT timing FROM entries WHERE lb_number=2").fetchone()),
                (3, conn.execute("SELECT timing FROM entries WHERE lb_number=3").fetchone()),
                (4, conn.execute("SELECT timing FROM entries WHERE lb_number=4").fetchone()),
            )
        ]
        classes = da._classify_sources(conn, 1, vm)
        assert classes[1]["group"] == "primary"

    def test_genuine_partial_is_a_fragment(self):
        conn = _selection_db()
        vm = [(lb, {"timing": conn.execute(
            "SELECT timing FROM entries WHERE lb_number=?", (lb,)).fetchone()[0]}, {})
            for lb in (1, 2, 3, 4)]
        classes = da._classify_sources(conn, 1, vm)
        assert classes[2]["group"] == "fragment"

    def test_glued_tracklist_rescued_by_runtime(self):
        conn = _selection_db()
        vm = [(lb, {"timing": conn.execute(
            "SELECT timing FROM entries WHERE lb_number=?", (lb,)).fetchone()[0]}, {})
            for lb in (1, 2, 3, 4)]
        classes = da._classify_sources(conn, 1, vm)
        # 58 min vs a median that includes 60/20/58/50 -> median 55: 58/55 > 60% -> not a fragment.
        assert classes[3]["group"] == "primary"
        assert classes[3]["completeness"]["glued"]

    def test_misdated_compilation_fails_g2(self):
        conn = _selection_db()
        vm = [(lb, {"timing": conn.execute(
            "SELECT timing FROM entries WHERE lb_number=?", (lb,)).fetchone()[0]}, {})
            for lb in (1, 2, 3, 4)]
        classes = da._classify_sources(conn, 1, vm)
        assert classes[4]["group"] == "no_match"

    def test_no_event_id_defaults_every_source_to_primary(self):
        conn = _selection_db()
        classes = da._classify_sources(conn, None, _visible_members_for([1, 2, 3, 4]))
        assert all(c["group"] == "primary" for c in classes.values())


# ---------------------------------------------------------------------------
# Verdict pick + collapse + families, end to end via build_dossier/build_view
# ---------------------------------------------------------------------------


def _build(date_str_slash, date_iso, event_id=1):
    from backend.dossier import build_dossier
    result = build_dossier(date_iso, db_path=None)
    return result


class TestVerdictPickAndFamiliesLive:
    def _fixture(self):
        db_path, conn, tmp_dir = _make_db()
        _insert_entry(conn, 201, "1/2/03", rating="A", timing="10min",
                      source_chain="silver disc")  # a fragment: 2/5 songs, short runtime
        conn.execute("UPDATE entries SET setlist=? WHERE lb_number=201",
                     ("1. Song One, 2. Song Two",))
        _insert_entry(conn, 202, "1/2/03", rating="B", timing="55min")
        conn.execute("UPDATE entries SET setlist=? WHERE lb_number=202",
                     ("1. Song One, 2. Song Two, 3. Song Three, 4. Song Four, 5. Song Five",))
        _insert_event(conn, 1, "2003-01-02", page_filename="p27")
        for i, title in enumerate(
                ["Song One", "Song Two", "Song Three", "Song Four", "Song Five"], start=1):
            _insert_song(conn, 1, i, title)
            _insert_song_performance(conn, 1, i, title.lower(), "2003-01-02")
        conn.execute(
            "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
            "evidence_json, concert_date_iso) VALUES "
            "('1/2/03', 201, 95.0, 1, '[]', '2003-01-02'),"
            "('1/2/03', 202, 80.0, 2, '[]', '2003-01-02')"
        )
        conn.commit()
        return db_path, conn, tmp_dir

    def test_pick_skips_a_fragment_for_the_best_eligible_source(self):
        db_path, conn, tmp_dir = self._fixture()
        try:
            from backend.dossier import build_dossier
            result = build_dossier("2003-01-02", db_path=db_path)
            view = result["view"]
            # 201 is show_picks rank 1 but is a fragment (2/5 songs) -- 202 (rank 2, complete)
            # must become the dossier's verdict pick.
            assert view["fields"]["pick.lb_id"]["value"] == "LB-00202"
            rows = {r["lb_id"]["value"]: r for r in view["rows"]["source"]}
            assert rows["LB-00201"]["group"]["value"] == "fragment"
            assert rows["LB-00202"]["group"]["value"] == "primary"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_fresh_install_defaults_pick_to_recommendation(self):
        # No event/setlist to score against -- build_view must not crash and every
        # source classifies "primary" (§8.2 fallback).
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 301, "3/4/05", rating="A")
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
                "evidence_json, concert_date_iso) VALUES "
                "('3/4/05', 301, 50.0, 1, '[]', '2005-03-04')"
            )
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2005-03-04", db_path=db_path)
            view = result["view"]
            assert view["fields"]["pick.lb_id"]["value"] == "LB-00301"
            assert view["rows"]["source"][0]["group"]["value"] == "primary"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestFamilyLabel:
    def test_confirmed_tapers_and_high_confidence_use_taper_name(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE taper_attributions (lb_number INTEGER, taper_normalised TEXT,
                                             confidence TEXT, conflict INTEGER DEFAULT 0);
        """)
        conn.executemany(
            "INSERT INTO taper_attributions VALUES (?, 'Jane Doe', 'confirmed', 0)",
            [(1,), (2,)],
        )
        assert df.family_taper_label(conn, [1, 2], 0.75) == "Jane Doe's tape"

    def test_below_confidence_floor_falls_back(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE taper_attributions (lb_number INTEGER, taper_normalised TEXT,
                                             confidence TEXT, conflict INTEGER DEFAULT 0);
        """)
        conn.executemany(
            "INSERT INTO taper_attributions VALUES (?, 'Jane Doe', 'confirmed', 0)",
            [(1,), (2,)],
        )
        assert df.family_taper_label(conn, [1, 2], 0.49) is None

    def test_one_unconfirmed_member_falls_back(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE taper_attributions (lb_number INTEGER, taper_normalised TEXT,
                                             confidence TEXT, conflict INTEGER DEFAULT 0);
        """)
        conn.execute("INSERT INTO taper_attributions VALUES (1, 'Jane Doe', 'confirmed', 0)")
        conn.execute("INSERT INTO taper_attributions VALUES (2, 'Jane Doe', 'propagated', 0)")
        assert df.family_taper_label(conn, [1, 2], 0.9) is None

    def test_disagreeing_names_fall_back(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE taper_attributions (lb_number INTEGER, taper_normalised TEXT,
                                             confidence TEXT, conflict INTEGER DEFAULT 0);
        """)
        conn.execute("INSERT INTO taper_attributions VALUES (1, 'Jane Doe', 'confirmed', 0)")
        conn.execute("INSERT INTO taper_attributions VALUES (2, 'John Roe', 'confirmed', 0)")
        assert df.family_taper_label(conn, [1, 2], 0.9) is None


class TestFamilyMembershipLive:
    def test_single_member_family_does_not_render(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 401, "5/6/07")
            _insert_family(conn, 401, "fam-solo", "2007-05-06")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2007-05-06", db_path=db_path)
            assert result["view"]["rows"]["family"] == []
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_two_member_family_renders(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 402, "5/6/07")
            _insert_entry(conn, 403, "5/6/07")
            _insert_family(conn, 402, "fam-duo", "2007-05-06")
            _insert_family(conn, 403, "fam-duo", "2007-05-06")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2007-05-06", db_path=db_path)
            rows = result["view"]["rows"]["family"]
            assert len(rows) == 1
            assert rows[0]["id"]["value"] == "fam-duo"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_single_member_family_still_counts_as_a_tape_group(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            for lb in (411, 412, 413):
                _insert_entry(conn, lb, "5/6/07")
            _insert_family(conn, 411, "fam-solo", "2007-05-06")
            _insert_family(conn, 412, "fam-duo", "2007-05-06")
            _insert_family(conn, 413, "fam-duo", "2007-05-06")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2007-05-06", db_path=db_path)
            assert result["view"]["fields"]["sources.tape_count"]["value"] == "2 tape groups"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_taper_label_beats_tapematch_letter(self):
        # tapematch_family_meta.label is always "Family A/B" -- it must not shadow S8.4.
        db_path, conn, tmp_dir = _make_db()
        try:
            for lb in (421, 422):
                _insert_entry(conn, lb, "5/6/07")
                _insert_family(conn, lb, "fam-t", "2007-05-06")
                conn.execute(
                    "INSERT INTO taper_attributions (lb_number, taper_normalised, confidence,"
                    " evidence_json) VALUES (?, 'Jane Doe', 'confirmed', '[]')", (lb,))
            conn.execute(
                "INSERT INTO tapematch_family_meta (fam_id, concert_date, label, conf,"
                " member_count) VALUES ('fam-t', '2007-05-06', 'Family A', 0.9, 2)")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2007-05-06", db_path=db_path)
            rows = result["view"]["rows"]["family"]
            assert rows[0]["label"]["value"] == "Jane Doe's tape"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestNoEligibleVerdict:
    def test_fragment_only_show_has_no_verdict_pick(self):
        fixture = TestVerdictPickAndFamiliesLive()._fixture
        db_path, conn, tmp_dir = fixture()
        try:
            conn.execute("DELETE FROM entries WHERE lb_number = 202")
            conn.execute("DELETE FROM show_picks WHERE lb_number = 202")
            conn.execute("UPDATE entries SET timing = NULL WHERE lb_number = 201")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2003-01-02", db_path=db_path)
            view = result["view"]
            rows = {r["lb_id"]["value"]: r for r in view["rows"]["source"]}
            assert rows["LB-00201"]["group"]["value"] == "fragment"
            assert view["fields"].get("pick.lb_id", {}).get("value") != "LB-00201"
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# §8.3 collapse count (backend.dossier_claims._collapse_count)
# ---------------------------------------------------------------------------


class TestCollapseCount:
    def test_no_collapse_at_or_below_five_sources(self):
        from backend.dossier_claims import _collapse_count

        view = {"rows": {"source": [
            {"lb_id": {"value": f"LB-{i:05d}", "source": "x"}} for i in range(1, 6)
        ]}}
        assert _collapse_count(view, [1, 2, 3, 4, 5], {
            "lb_rating": {}, "scan": {}, "runtime": {}, "resolution": {}, "soundboard": {},
            "complete": {},
        }) == 5

    def test_collapses_to_pick_plus_three_above_five(self):
        from backend.dossier_claims import _collapse_count

        rows = [
            {"lb_id": {"value": f"LB-{i:05d}", "source": "x"},
             "rank": {"value": i, "source": "show_picks"}}
            for i in range(1, 7)
        ]
        view = {"rows": {"source": rows}}
        axes = {"lb_rating": {}, "scan": {}, "runtime": {}, "resolution": {}, "soundboard": {},
                "complete": {}}
        n = _collapse_count(view, [1, 2, 3, 4, 5, 6], axes)
        assert n == 4  # pick + next 3, no axis leaders

    def test_promotes_an_axis_leader_outside_the_top_four(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_claims import _collapse_count

        rows = [
            {"lb_id": {"value": f"LB-{i:05d}", "source": "x"},
             "rank": {"value": i, "source": "show_picks"}}
            for i in range(1, 7)
        ]
        view = {"rows": {"source": rows}}
        # A superlative claim needs every eligible source to have a usable value
        # (dossier_claims.superlative) -- so all 6 get a scan score, lb 6 the best.
        scan = {i: build_field(50 + i, 1, "s", "stated") for i in range(1, 7)}
        axes = {"lb_rating": {}, "scan": scan, "runtime": {}, "resolution": {},
                "soundboard": {}, "complete": {}}
        n = _collapse_count(view, [1, 2, 3, 4, 5, 6], axes)
        assert n == 5  # pick+3 (1-4) plus the promoted scan leader (6)
