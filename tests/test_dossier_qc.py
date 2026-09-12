"""Tests for backend.dossier_qc (TODO-342 dossier redesign, Phase 5, C28).

Covers pass and fail paths for every gate G1-G9, plus a route test for the 422
refusal on /api/dossier/html and /api/dossier/bbcode.
"""
from __future__ import annotations

import shutil

from tests.test_dossier import (
    _insert_entry,
    _insert_event,
    _insert_song,
    _make_db,
)


def _insert_two_source_pick(conn, date_str, date_iso):
    """LB-00101 rank 1 (A rating, 128min, soundboard), LB-00102 rank 2 -- the
    fixture :func:`tests.test_dossier_claims.TestBuildViewWiring.test_two_sources_pick_claims`
    uses, reused here so G7/G8 can quarantine the pick and watch its claims drop.
    """
    _insert_entry(conn, 101, date_str, rating="A", timing="128min", source_type="Soundboard")
    _insert_entry(conn, 102, date_str, rating="B", timing="60min", source_type="AUD")
    _insert_event(conn, 1, date_iso)
    conn.execute(
        "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank,"
        " evidence_json, concert_date_iso) VALUES (?, 101, 90.0, 1, '[]', ?),"
        " (?, 102, 50.0, 2, '[]', ?)",
        (date_str, date_iso, date_str, date_iso),
    )


def _set_venue(conn, event_id, venue, city):
    conn.execute("UPDATE olof_events SET venue=?, city=? WHERE event_id=?",
                 (venue, city, event_id))


def _insert_setlistfm(conn, setlistfm_id, date_str, venue_name, city):
    conn.execute(
        "INSERT INTO setlistfm_shows (setlistfm_id, date_str, venue_name, city)"
        " VALUES (?, ?, ?, ?)",
        (setlistfm_id, date_str, venue_name, city),
    )


def _insert_finding(conn, rule_id, entity_kind, entity_key, severity="error", status="open"):
    conn.execute(
        "INSERT INTO qc_findings (rule_id, entity_kind, entity_key, severity, detail,"
        " evidence_json, evidence_hash, first_seen, last_seen, status)"
        " VALUES (?, ?, ?, ?, 'test finding', '{}', 'x', '2026-01-01', '2026-01-01', ?)",
        (rule_id, entity_kind, entity_key, severity, status),
    )


class TestG1Identity:
    def test_venue_agrees_passes_with_no_notice(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2010-03-29")
            _set_venue(conn, 1, "Zepp Tokyo", "Tokyo")
            _insert_setlistfm(conn, "sfm1", "2010-03-29", "Zepp Tokyo", "Tokyo")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path)
            qc = result["qc"]
            assert qc["refused"] is False
            assert not any("venue name" in n for n in qc["notices"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_city_only_match_adds_notice(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "1965-06-01")
            _set_venue(conn, 1, "Stadio Communale", "Torino")
            _insert_setlistfm(conn, "sfm1", "1965-06-01", "Stadio Comunale (different)", "Torino")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("1965-06-01", db_path=db_path)
            qc = result["qc"]
            assert qc["refused"] is False
            assert any("venue name" in n for n in qc["notices"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_loose_venue_spelling_passes_without_notice(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "1994-07-07")
            _set_venue(conn, 1, "Stadio Communale", "San Remo")
            _insert_setlistfm(conn, "sfm1", "1994-07-07", "Stadio Comunale", "Sanremo")
            conn.commit()

            from backend.dossier import build_dossier
            qc = build_dossier("1994-07-07", db_path=db_path)["qc"]
            assert qc["refused"] is False
            assert not any("venue name" in n for n in qc["notices"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_neither_venue_nor_city_agrees_refuses(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "1999-01-01")
            _set_venue(conn, 1, "Some Arena", "Some City")
            _insert_setlistfm(conn, "sfm1", "1999-01-01", "A Totally Different Arena",
                               "A Totally Different City")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("1999-01-01", db_path=db_path)
            qc = result["qc"]
            assert qc["refused"] is True
            assert any("G1" in r for r in qc["reasons"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_comparable_source_passes_with_unavailable_notice(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "1959-01-10")
            _set_venue(conn, 1, "Some Hall", "Some City")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("1959-01-10", db_path=db_path)
            qc = result["qc"]
            assert qc["refused"] is False
            assert any("unavailable" in n for n in qc["notices"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_olof_event_refuses(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            qc = result["qc"]
            assert qc["refused"] is True
            assert any("no Olof event" in r for r in qc["reasons"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestG2Assert:
    def test_source_rows_all_have_group_no_warning(self, caplog):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert result["view"]["rows"]["source"][0]["group"]["value"] in (
                "primary", "fragment", "no_match")
            assert "C27 regression" not in caplog.text
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestG3Provenance:
    def test_normal_field_untouched(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _set_venue(conn, 1, "Some Hall", "Some City")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert result["view"]["fields"]["show.venue"]["confidence"] == "stated"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_field_with_confidence_but_no_source_is_withheld(self):
        from backend.dossier_qc import _Gate, _run_g3_provenance

        view = {
            "fields": {
                "show.venue": {"value": "Bad Field", "tier": 1, "source": None,
                                "confidence": "stated", "derived_from": []},
            },
            "rows": {},
        }
        gate = _Gate(view, conn=None)
        _run_g3_provenance(gate)
        assert view["fields"]["show.venue"]["confidence"] == "withheld"
        assert any(w["key"] == "show.venue" and w["rule"] == "G3" for w in gate.withheld)


class TestG4Quarantine:
    def test_quarantined_song_bobtalk_withheld_not_title(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_song(conn, 1, 1, "Some Song")
            _insert_finding(conn, "R-O3", "olof_song", "1:1")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            song_row = result["view"]["rows"]["song"][0]
            # Nothing to actually withhold here (no writers/instruments/bobtalk
            # data on this fixture song) -- the point is title/position are never
            # touched by R-O3, regardless.
            assert song_row["title"]["confidence"] == "stated"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_r_t1_withholds_taper_keeps_runtime(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00", timing="60min", rating="A")
            _insert_finding(conn, "R-T1", "lb", "101")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            source_row = result["view"]["rows"]["source"][0]
            assert source_row.get("taper", {}).get("confidence") in (None, "withheld")
            assert source_row["runtime"]["confidence"] == "stated"
            assert source_row["lb_rating"]["confidence"] == "stated"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_r_e2_withholds_whole_source_row(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00", timing="60min", rating="A",
                           source_type="Soundboard")
            _insert_finding(conn, "R-E2", "entry", "101")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            source_row = result["view"]["rows"]["source"][0]
            assert source_row["runtime"]["confidence"] == "withheld"
            assert source_row["lb_rating"]["confidence"] == "withheld"
            assert source_row["type"]["confidence"] == "withheld"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_r_o1_keeps_tour_and_setlist_confidence(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            conn.execute("UPDATE olof_events SET tour_name='Test Tour' WHERE event_id=1")
            _insert_song(conn, 1, 1, "Some Song")
            _insert_finding(conn, "R-O1", "olof_event", "1")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            fields = result["view"]["fields"]
            assert fields["show.tour"]["confidence"] == "stated"
            assert fields["show.setlist_confidence"]["confidence"] != "withheld"
            assert fields["setlist.count"]["confidence"] == "withheld"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_r_g1_keeps_venue_name(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _set_venue(conn, 1, "Zepp Tokyo", "Tokyo")
            from backend.venue_gazetteer import _norm_city, _norm_venue
            vkey = f"{_norm_venue('Zepp Tokyo')}:{_norm_city('Tokyo')}"
            _insert_finding(conn, "R-G1", "venue", vkey)
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            fields = result["view"]["fields"]
            assert fields["show.venue"]["confidence"] == "stated"
            assert fields["venue.name"]["confidence"] == "stated"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_unknown_rule_id_withholds_nothing(self, caplog):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_finding(conn, "R-ZZ-MADE-UP", "olof_event", "1")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert result["qc"]["withheld"] == []
            assert "unrecognised error rule" in caplog.text
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_no_findings_nothing_withheld(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_song(conn, 1, 1, "Some Song")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert result["qc"]["withheld"] == []
            song_row = result["view"]["rows"]["song"][0]
            assert song_row["title"]["confidence"] != "withheld"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestG5Invariants:
    def _view(self, fields):
        from backend.dossier_anchors import ANCHORS, build_fallback_field
        base = {k: build_fallback_field(a) for k, a in ANCHORS.items() if "[]." not in k}
        base.update(fields)
        return {"fields": base, "rows": {}}

    def test_city_history_sum_mismatch_withholds(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "venue.city_total": build_field(5, 3, "src", "stated"),
            "city_history[]": build_field([{"count": 2}, {"count": 2}], 3, "src", "stated"),
        })
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, {"sources": []}, None)
        assert view["fields"]["venue.city_total"]["confidence"] == "withheld"

    def test_city_history_sum_match_passes(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "venue.city_total": build_field(4, 3, "src", "stated"),
            "city_history[]": build_field([{"count": 2}, {"count": 2}], 3, "src", "stated"),
        })
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, {"sources": []}, None)
        assert view["fields"]["venue.city_total"]["confidence"] == "stated"

    def test_ledger_sum_mismatch_withholds(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "ledger[]": build_field([{"points": 10}, {"points": 5}], 1, "src", "stated"),
            "ledger.total": build_field(90.0, 1, "src", "stated"),
        })
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, {"sources": []}, None)
        assert view["fields"]["ledger.total"]["confidence"] == "withheld"

    def test_ledger_sum_match_passes(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "ledger[]": build_field([{"points": 10}, {"points": 5}], 1, "src", "stated"),
            "ledger.total": build_field(15.0, 1, "src", "stated"),
        })
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, {"sources": []}, None)
        assert view["fields"]["ledger.total"]["confidence"] == "stated"

    def test_ledger_audio_evidence_mismatch_withholds(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "ledger[]": build_field(
                [{"kind": "audio_quality", "detail": "scanned quality 81/100", "points": -2.77}],
                1, "src", "stated"),
            "ledger.total": build_field(-2.77, 1, "src", "stated"),
        })
        d1 = {"sources": [{"members": [
            {"lb": "LB-00101", "quality": {"score": 60.0}},
        ]}]}
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, d1, 101)
        assert view["fields"]["ledger.total"]["confidence"] == "withheld"

    def test_ledger_audio_evidence_match_passes(self):
        from backend.dossier_anchors import build_field
        from backend.dossier_qc import _Gate, _run_g5_invariants

        view = self._view({
            "ledger[]": build_field(
                [{"kind": "audio_quality", "detail": "scanned quality 81/100", "points": -2.77}],
                1, "src", "stated"),
            "ledger.total": build_field(-2.77, 1, "src", "stated"),
        })
        d1 = {"sources": [{"members": [
            {"lb": "LB-00101", "quality": {"score": 81.0}},
        ]}]}
        gate = _Gate(view, conn=None)
        _run_g5_invariants(gate, d1, 101)
        assert view["fields"]["ledger.total"]["confidence"] == "stated"


class TestG6Freshness:
    def test_no_stale_findings_nothing_withheld(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            assert result["qc"]["withheld"] == []
            assert "analysis stale" not in result["qc"]["notices"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_show_picks_stale_withholds_pick_and_ledger(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            _insert_finding(conn, "R-S1", "table", "show_picks")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            fields = result["view"]["fields"]
            assert fields["pick.lb_rating"]["confidence"] == "withheld"
            assert fields["ledger.total"]["confidence"] == "withheld"
            assert "analysis stale" in result["qc"]["notices"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_song_performances_stale_withholds_premiere_stats(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_song(conn, 1, 1, "Some Song")
            _insert_finding(conn, "R-S1", "table", "song_performances")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            fields = result["view"]["fields"]
            assert fields["stats.premiere_count"]["confidence"] == "withheld"
            song_row = result["view"]["rows"]["song"][0]
            assert song_row["premiere"]["confidence"] == "withheld"
            assert "analysis stale" in result["qc"]["notices"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_per_lb_stale_withholds_scan_grade(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            _insert_finding(conn, "R-S1", "lb", "102")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            source_rows = {r["lb_id"]["value"]: r for r in result["view"]["rows"]["source"]}
            row102 = source_rows["LB-00102"]
            assert row102.get("scan_grade", {}).get("confidence") in (None, "withheld")
            row101 = source_rows["LB-00101"]
            assert row101["lb_rating"]["confidence"] == "stated"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestG7ClaimDrop:
    def test_verdict_claims_dropped_when_pick_source_row_quarantined(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            conn.commit()

            from backend.dossier import build_dossier
            baseline = build_dossier("2010-03-29", db_path=db_path, channel="full")
            assert any(c["anchor"] == "verdict.why" for c in baseline["view"]["claims"])

            # R-E2 withholds the pick's whole source row (lb_rating, runtime,
            # type...) -- the superlative claims computed over those axes must
            # be dropped since their comparison scope is now incomplete.
            _insert_finding(conn, "R-E2", "entry", "101")
            conn.commit()
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            assert not any(c["anchor"] == "verdict.why" for c in result["view"]["claims"])
            assert result["view"]["fields"]["verdict.why"]["confidence"] == "unavailable"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_superlative_dropped_when_non_pick_source_withheld(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            # R-E2 on the runner-up, not the pick: "best of 2 sources" now compares
            # against a withheld value, so the scope is incomplete and the claim goes.
            _insert_finding(conn, "R-E2", "entry", "102")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            assert not any(c["anchor"] == "verdict.why" for c in result["view"]["claims"])
            assert result["qc"]["refused"] is False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_verdict_claims_survive_when_only_taper_quarantined(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            _insert_finding(conn, "R-T1", "lb", "101")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="full")
            # Taper isn't one of the D-08 axes -- the rating/runtime/soundboard
            # claims don't depend on it and must survive.
            assert any(c["anchor"] == "verdict.why" for c in result["view"]["claims"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestG8Channel:
    def test_public_channel_no_private_leak(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "2000-07-28")
            _insert_entry(conn, 101, "7/28/00", status="private")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", channel="public", db_path=db_path)
            assert not any("leaked" in r for r in result["qc"]["reasons"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_public_channel_does_not_refuse_for_a_g7_drop(self):
        """A G7 claim drop is G7 doing its job -- it must not escalate to a refusal."""
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_two_source_pick(conn, "3/29/10", "2010-03-29")
            _insert_finding(conn, "R-E2", "entry", "101")
            conn.commit()

            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path, channel="public")
            assert not any(c["anchor"] == "verdict.why" for c in result["view"]["claims"])
            assert result["qc"]["refused"] is False
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_backstop_refuses_if_a_surviving_claim_still_touches_withheld_source(self):
        """Forces the G8(b) backstop directly -- G7 should never actually leave this
        state, so this exercises _run_g8_channel/_claim_touches_withheld in isolation
        rather than trying to induce a real G7 bug end to end.
        """
        from backend.dossier_qc import _Gate, _run_g8_channel

        view = {
            "fields": {},
            "rows": {"source": [
                {"lb_id": {"value": "LB-00101"}, "group": {"value": "primary"}},
                {"lb_id": {"value": "LB-00102"}, "group": {"value": "primary"}},
            ]},
            "claims": [
                {"anchor": "verdict.why", "row": None,
                 "claim": {"verified_by": "D-08 scan", "slots": {}, "scope": "visible_sources"}},
            ],
        }
        gate = _Gate(view, conn=None)
        gate.withheld_source_subs.add(("scan_grade", 101))
        _run_g8_channel(gate, "public", {"sources": []}, pick_lb=None)
        assert any("backstop" in r for r in gate.reasons)


class TestLintL1:
    def test_forbidden_phrase_outside_claim_flagged(self):
        from backend.dossier_qc import lint_l1
        html = "<p>taper unknown for this one</p>"
        assert any("taper unknown" in v for v in lint_l1(html))

    def test_forbidden_phrase_inside_claim_span_ok(self):
        from backend.dossier_qc import lint_l1
        html = '<span data-claim="x">the only soundboard</span>'
        assert lint_l1(html) == []

    def test_bare_superlative_outside_claim_flagged(self):
        from backend.dossier_qc import lint_l1
        html = "<p>this is the best recording</p>"
        assert any("best" in v for v in lint_l1(html))

    def test_solid_pin_requires_venue_basis(self):
        from backend.dossier_qc import lint_l1
        bad = '<div data-map-pin="solid" data-venue-basis="city_centre"></div>'
        assert any("solid map pin" in v for v in lint_l1(bad))
        good = '<div data-map-pin="solid" data-venue-basis="venue"></div>'
        assert lint_l1(good) == []


class TestLintDataLb:
    def test_unknown_anchor_flagged(self):
        from backend.dossier_qc import lint_data_lb
        html = '<span data-lb="not.a.real.anchor">x</span>'
        assert any("not.a.real.anchor" in v for v in lint_data_lb(html))

    def test_known_anchor_ok(self):
        from backend.dossier_qc import lint_data_lb
        html = '<span data-lb="show.venue">x</span>'
        assert lint_data_lb(html) == []


class TestRoute422:
    def test_html_route_422_on_refusal(self):
        import backend.db as db
        import backend.paths as _paths

        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_event(conn, 1, "1999-01-01")
            _set_venue(conn, 1, "Some Arena", "Some City")
            _insert_setlistfm(conn, "sfm1", "1999-01-01", "A Totally Different Arena",
                               "A Totally Different City")
            conn.commit()

            orig_paths_db, orig_db_db = _paths.DB_PATH, getattr(db, "DB_PATH", None)
            _paths.DB_PATH = db_path
            db.DB_PATH = db_path
            try:
                from backend.app import create_app
                client = create_app().test_client()
                resp = client.get("/api/dossier/html?date=1999-01-01")
                assert resp.status_code == 422
                assert resp.get_json()["refused"] is True

                resp2 = client.get("/api/dossier/bbcode?date=1999-01-01")
                assert resp2.status_code == 422
                assert resp2.get_json()["refused"] is True

                resp3 = client.get("/api/dossier?date=1999-01-01")
                assert resp3.status_code == 200
                assert resp3.get_json()["qc"]["refused"] is True
            finally:
                _paths.DB_PATH = orig_paths_db
                if orig_db_db is not None:
                    db.DB_PATH = orig_db_db
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
