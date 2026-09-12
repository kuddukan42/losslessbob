"""Tests for backend.dossier_claims (TODO-342 dossier redesign, C26; audit C3).

Covers the comparator contract -- ties reported, partial scope, disputed /
withheld / missing input -> no claim -- plus the D-04 / D-07 / D-02 claim
builders, slot rendering (inferred marker inside the sentence), the two T4
templates, ``filter_view`` claim stripping and the ``build_view`` wiring.
"""
from __future__ import annotations

import shutil

import pytest

from backend.dossier_anchors import build_field, filter_view
from backend.dossier_claims import (
    TEMPLATES,
    chronicle,
    claim_text,
    comparison,
    exclusive,
    render_segments,
    rotation_claim,
    run_position_claim,
    song_claims,
    superlative,
    tour_position_claim,
    usable,
    verdict_why,
)
from tests.test_dossier import _insert_entry, _insert_event, _make_db


def _f(value, confidence="stated", tier=1):
    return build_field(value, tier, "test", confidence, ["t"])


# ---------------------------------------------------------------------------
# superlative
# ---------------------------------------------------------------------------

class TestSuperlative:
    def test_sole_leader(self):
        c = superlative(1, {1: _f(90), 2: _f(80), 3: _f(70)}, text_key="best_scan",
                        verified_by="t")
        assert c is not None
        assert c["kind"] == "superlative" and c["ties"] == 0
        assert claim_text(c) == "best scanned quality of the 3 sources"

    def test_tie_is_reported(self):
        c = superlative(1, {1: _f(90), 2: _f(90), 3: _f(70)}, text_key="best_scan",
                        verified_by="t")
        assert c is not None and c["ties"] == 1
        assert c["text_key"] == "best_scan_tied"
        assert claim_text(c).startswith("tied best")

    def test_all_way_tie_is_no_claim(self):
        assert superlative(1, {1: _f(90), 2: _f(90)}, text_key="best_scan",
                           verified_by="t") is None

    def test_beaten_subject_is_no_claim(self):
        assert superlative(1, {1: _f(80), 2: _f(90)}, text_key="best_scan",
                           verified_by="t") is None

    def test_partial_scope_missing_value_is_no_claim(self):
        assert superlative(1, {1: _f(90), 2: None, 3: _f(70)}, text_key="best_scan",
                           verified_by="t") is None
        assert superlative(1, {1: _f(90), 2: _f(None)}, text_key="best_scan",
                           verified_by="t") is None

    @pytest.mark.parametrize("confidence", ["disputed", "withheld", "unavailable"])
    def test_unusable_input_is_no_claim(self, confidence):
        assert superlative(1, {1: _f(90), 2: _f(70, confidence)}, text_key="best_scan",
                           verified_by="t") is None
        assert superlative(1, {1: _f(90, confidence), 2: _f(70)}, text_key="best_scan",
                           verified_by="t") is None

    def test_single_candidate_is_no_claim(self):
        assert superlative(1, {1: _f(90)}, text_key="best_scan", verified_by="t") is None

    def test_subject_outside_scope_is_no_claim(self):
        assert superlative(9, {1: _f(90), 2: _f(70)}, text_key="best_scan",
                           verified_by="t") is None

    def test_tie_floor(self):
        # 127 vs 126 is within the 2-minute rounding floor: a tie, not a lead.
        c = superlative(1, {1: _f(127.0), 2: _f(126.0), 3: _f(60.0)},
                        text_key="longest_runtime", verified_by="t", tie_floor=2.0)
        assert c is not None and c["text_key"] == "longest_runtime_tied"
        # The other side of the floor: 125 is beaten by 127 -> no claim for 125.
        assert superlative(2, {1: _f(127.0), 2: _f(125.0)}, text_key="longest_runtime",
                           verified_by="t", tie_floor=2.0) is None
        # A within-floor deficit still reads as a tie, never as a lead.
        c = superlative(2, {1: _f(127.0), 2: _f(126.0), 3: _f(60.0)},
                        text_key="longest_runtime", verified_by="t", tie_floor=2.0)
        assert c is not None and c["ties"] == 1

    def test_key_unrankable_value_is_no_claim(self):
        from backend.dossier_claims import _rating_key

        assert superlative(1, {1: _f("A"), 2: _f("??")}, text_key="highest_lb_rating",
                           verified_by="t", key=_rating_key) is None
        c = superlative(1, {1: _f("A"), 2: _f("A-"), 3: _f("B+")}, text_key="highest_lb_rating",
                        verified_by="t", key=_rating_key)
        assert c is not None and c["ties"] == 0

    def test_derived_from_unions_inputs(self):
        a = build_field(90, 1, "x", "stated", ["qrs"])
        b = build_field(70, 1, "x", "stated", ["entries"])
        c = superlative(1, {1: a, 2: b}, text_key="best_scan", verified_by="cmp")
        assert c["derived_from"] == ["qrs", "entries", "claim:cmp"]


# ---------------------------------------------------------------------------
# exclusive / comparison
# ---------------------------------------------------------------------------

class TestExclusive:
    def test_only(self):
        c = exclusive(1, {1: _f(True), 2: _f(False), 3: _f(False)},
                      text_key="only_soundboard", verified_by="t")
        assert c is not None and claim_text(c) == "the only soundboard of the 3 sources"

    def test_two_true_is_no_claim(self):
        assert exclusive(1, {1: _f(True), 2: _f(True)}, text_key="only_soundboard",
                         verified_by="t") is None

    def test_unknown_other_is_no_claim(self):
        assert exclusive(1, {1: _f(True), 2: None}, text_key="only_soundboard",
                         verified_by="t") is None

    def test_disputed_is_no_claim(self):
        assert exclusive(1, {1: _f(True), 2: _f(False, "disputed")},
                         text_key="only_complete", verified_by="t") is None

    def test_subject_false_is_no_claim(self):
        assert exclusive(1, {1: _f(False), 2: _f(True)}, text_key="only_complete",
                         verified_by="t") is None


class TestComparison:
    def test_higher(self):
        c = comparison(_f(84.1), _f(79.0), other_label="LB-08476", text_key="higher_scan_than",
                       verified_by="t")
        assert claim_text(c) == "higher scanned quality than LB-08476 (84.1 vs 79)"

    def test_equal_is_no_claim(self):
        assert comparison(_f(80), _f(80), other_label="x", text_key="higher_scan_than",
                          verified_by="t") is None

    def test_floor(self):
        assert comparison(_f(127.0), _f(126.0), other_label="x",
                          text_key="longer_runtime_than", verified_by="t", floor=2.0) is None
        assert comparison(_f(128.0), _f(126.0), other_label="x",
                          text_key="longer_runtime_than", verified_by="t", floor=2.0)

    def test_disputed_is_no_claim(self):
        assert comparison(_f("24/96", "disputed"), _f("16/44"), other_label="x",
                          text_key="higher_resolution_than", verified_by="t") is None


# ---------------------------------------------------------------------------
# D-04 / D-07 / D-02 builders
# ---------------------------------------------------------------------------

def _run(size=3, position=3, claims_ok=True, venue="Zepp Tokyo"):
    ids = list(range(1, size + 1))
    return {"venue": venue, "position": position, "size": size,
            "dates": [f"2010-03-{20 + i}" for i in ids], "event_ids": ids,
            "claims_ok": claims_ok}


def _rotation(pcts, verified=None, scope="of the 3-night Zepp Tokyo run"):
    verified = verified or [True] * len(pcts)
    sib = [{"event_id": i + 1, "date": "d", "pct": p, "new": 1, "verified": v,
            "disputed": p is not None and not v}
           for i, (p, v) in enumerate(zip(pcts, verified, strict=True))]
    return {"pct": pcts[-1], "siblings": sib, "scope": scope}


class TestRotationClaim:
    def test_biggest(self):
        c = rotation_claim(3, _rotation([40, 50, 72]), _run())
        assert claim_text(c) == "biggest setlist rotation of the 3-night Zepp Tokyo run"
        assert c["scope"] == "venue_run" and not c["local_analysis"]

    def test_tied(self):
        c = rotation_claim(3, _rotation([72, 50, 72]), _run())
        assert c["text_key"] == "biggest_rotation_tied" and c["ties"] == 1

    def test_unverified_sibling_is_no_claim(self):
        assert rotation_claim(3, _rotation([40, 50, 72], [True, False, True]), _run()) is None

    def test_missing_sibling_pct_is_no_claim(self):
        assert rotation_claim(3, _rotation([None, 50, 72]), _run()) is None

    def test_incomplete_run_is_no_claim(self):
        assert rotation_claim(3, _rotation([40, 50, 72]), _run(claims_ok=False)) is None

    def test_partial_siblings_is_no_claim(self):
        rot = _rotation([50, 72])
        assert rotation_claim(2, rot, _run()) is None

    def test_single_night_is_no_claim(self):
        assert rotation_claim(1, _rotation([72]), _run(size=1, position=1)) is None


class TestPositions:
    def _tour(self, position, size=15, claims_ok=True):
        return {"name": "2010 Tour of Japan", "net_number": 1, "position": position,
                "size": size, "is_first": position == 1, "is_last": position == size,
                "claims_ok": claims_ok}

    def test_tour_not_last_says_n_of_m(self):
        # Audit M4: 2010-03-29 is show 14 of 15, never "closing the tour".
        c = tour_position_claim(self._tour(14))
        assert claim_text(c) == "show 14 of 15 on the 2010 Tour of Japan"
        assert "last" not in claim_text(c)

    def test_tour_last_and_first(self):
        assert tour_position_claim(self._tour(15))["text_key"] == "tour_closing"
        assert tour_position_claim(self._tour(1))["text_key"] == "tour_opening"

    def test_tour_guard(self):
        assert tour_position_claim(self._tour(15, claims_ok=False)) is None
        assert tour_position_claim(self._tour(1, size=1)) is None
        assert tour_position_claim(None) is None

    def test_run(self):
        assert claim_text(run_position_claim(_run(7, 7))) == \
            "closing night of the 7-night Zepp Tokyo run"
        assert run_position_claim(_run(7, 1))["text_key"] == "run_opening"
        assert claim_text(run_position_claim(_run(7, 3))) == "night 3 of 7 at Zepp Tokyo"
        assert run_position_claim(_run(7, 7, claims_ok=False)) is None
        assert run_position_claim(_run(1, 1)) is None


class TestSongClaims:
    def _hist(self, gate=True, premiere=True, gap_badge=True):
        return {"tour_name": "2010 Tour of Japan", "gate_passed": gate, "songs": [
            {"position": 4, "premiere_badge": premiere and gate, "gap_badge": False,
             "last_played": "2009-11-01", "gap_shows": 20},
            {"position": 9, "premiere_badge": False, "gap_badge": gap_badge,
             "last_played": "2002-05-01", "gap_shows": 412},
        ]}

    def test_premiere_and_gap(self):
        out = song_claims(self._hist())
        assert claim_text(out[4][0]) == "new to the 2010 Tour of Japan"
        assert claim_text(out[9][0]) == "first performance since 2002-05-01 (412 shows)"

    def test_failed_gate_no_premiere(self):
        # premiere_badge can't be True without the gate, but guard both anyway.
        hist = self._hist(gate=False)
        hist["songs"][0]["premiere_badge"] = True
        assert 4 not in song_claims(hist)

    def test_no_gap_badge_no_since(self):
        assert 9 not in song_claims(self._hist(gap_badge=False))

    def test_none(self):
        assert song_claims(None) == {}


# ---------------------------------------------------------------------------
# Rendering + T4 templates
# ---------------------------------------------------------------------------

class TestRendering:
    def test_inferred_marker_inside_sentence(self):
        segs = render_segments("{g} source", {"g": _f("master", "inferred")})
        assert segs[0] == {"text": "master", "slot": "g", "inferred": True}
        assert segs[1]["slot"] is None and not segs[1]["inferred"]

    def test_dict_value_renders_name(self):
        segs = render_segments("taped by {t}", {"t": _f({"name": "hide", "marker": None})})
        assert segs[-1]["text"] == "hide"

    def test_usable(self):
        assert usable(_f(0)) and not usable(None) and not usable(_f(None))
        assert not usable(_f(1, "withheld"))

    def test_every_template_renders(self):
        import string

        for key, tpl in TEMPLATES.items():
            names = {n for _, n, _, _ in string.Formatter().parse(tpl) if n}
            segs = render_segments(tpl, {n: _f("x") for n in names})
            assert "{" not in "".join(s["text"] for s in segs), key


class TestT4:
    def test_verdict_why_uses_fields_and_claims(self):
        fields = {
            "pick.lb_rating": _f("A"),
            "pick.scan_grade": _f("A-"),
            "pick.taper.name": _f({"name": "hide"}, "inferred"),
            "pick.generation": _f("master", "inferred", 3),
            "pick.curated_in[]": _f([{"list_label": "10haaf's picks"}]),
        }
        claims = {"scan": superlative(1, {1: _f(90), 2: _f(80)}, text_key="best_scan",
                                      verified_by="t")}
        why = verdict_why(fields, claims)
        assert why["text"] == ("LB rating A; scanned quality A-, best scanned quality of the "
                               "2 sources; taped by hide; master source; in 10haaf's picks.")
        assert [s["text"] for s in why["segments"] if s["inferred"]] == ["hide", "master"]
        assert why["claims"] == ["best_scan"]

    def test_verdict_why_skips_unusable(self):
        fields = {"pick.lb_rating": _f("—", "unavailable"), "pick.scan_grade": _f(None)}
        assert verdict_why(fields, {}) is None

    def test_chronicle(self):
        fields = {"context.chronicle": _f("Olof's line.", tier=4)}
        run = run_position_claim(_run(7, 7))
        out = chronicle(fields, run, None)
        assert out["text"] == "Closing night of the 7-night Zepp Tokyo run. Olof's line."
        assert chronicle({}, None, None) is None
        assert chronicle(fields, None, None)["text"] == "Olof's line."


# ---------------------------------------------------------------------------
# filter_view + build_view wiring
# ---------------------------------------------------------------------------

def _claim_entry(anchor, local):
    c = superlative(1, {1: _f(2), 2: _f(1)}, text_key="best_scan", verified_by="t",
                    local_analysis=local)
    return {"anchor": anchor, "row": None, "claim": c}


class TestFilterView:
    def test_local_claims_stripped(self):
        view = {"fields": {}, "rows": {}, "claims": [
            _claim_entry("verdict.alternates[]", True),
            _claim_entry("song[].premiere", False),
            _claim_entry("context.chronicle", False),
        ]}
        kept = filter_view(view, local_analysis=False)["claims"]
        assert [c["anchor"] for c in kept] == ["song[].premiere", "context.chronicle"]
        assert len(filter_view(view)["claims"]) == 3

    def test_section_filter_drops_claims_with_anchor(self):
        view = {"fields": {}, "rows": {}, "claims": [_claim_entry("song[].premiere", False)]}
        assert filter_view(view, sections={"context"})["claims"] == []


class TestBuildViewWiring:
    def test_fresh_install_has_empty_claims(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()
            from backend.dossier import build_dossier

            view = build_dossier("2000-07-28", db_path=db_path)["view"]
            assert view["claims"] == []
            assert view["fields"]["verdict.why"]["confidence"] == "unavailable"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_two_sources_pick_claims(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "3/29/10", rating="A", timing="128min",
                           source_type="Soundboard")
            _insert_entry(conn, 102, "3/29/10", rating="B", timing="60min", source_type="AUD")
            _insert_event(conn, 1, "2010-03-29")
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
                "evidence_json, concert_date_iso) VALUES "
                "('3/29/10', 101, 90.0, 1, '[]', '2010-03-29'),"
                "('3/29/10', 102, 50.0, 2, '[]', '2010-03-29')"
            )
            conn.commit()
            from backend.dossier import build_dossier

            view = build_dossier("2010-03-29", db_path=db_path, channel="full")["view"]
            texts = {claim_text(c["claim"]) for c in view["claims"]}
            assert "highest LB rating of the 2 sources" in texts
            assert "longest runtime of the 2 sources" in texts
            assert "the only soundboard of the 2 sources" in texts
            why = view["fields"]["verdict.why"]
            assert why["tier"] == 4 and why["value"]["text"].startswith("LB rating A, highest")
            assert "verdict.why" in view["fields"]["prov.local_fields[]"]["value"]
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
