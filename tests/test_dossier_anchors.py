"""Tests for backend.dossier_anchors (TODO-342 dossier redesign, C25).

Covers: (a) every registered anchor resolves to its fallback on a fresh
install DB (required anchors just need to be present); (b) a populated
fixture shows real values, source and confidence for a representative
subset; (c) ``filter_view``/``filter_dossier_sections(local_analysis=False)``
strips every ``local_analysis``-marked anchor; (d) registry sanity (unique
keys, the ``prefix[].sub`` / ``prefix[]`` / scalar key convention, tiers
1-4).
"""
from __future__ import annotations

import pytest

from backend.dossier_anchors import ANCHORS, filter_view
from tests.test_dossier import (
    _insert_entry,
    _insert_event,
    _insert_family,
    _insert_song,
    _insert_song_performance,
    _make_db,
)

_SCALAR_KEYS = sorted(k for k in ANCHORS if "[]." not in k)
_ROW_KEYS = sorted(k for k in ANCHORS if "[]." in k)


# ---------------------------------------------------------------------------
# (d) Registry sanity
# ---------------------------------------------------------------------------

class TestRegistrySanity:
    def test_keys_unique(self):
        keys = [a.key for a in ANCHORS.values()]
        assert len(keys) == len(set(keys))

    def test_every_key_matches_its_dict_key(self):
        for key, anchor in ANCHORS.items():
            assert anchor.key == key

    @pytest.mark.parametrize("key", list(ANCHORS))
    def test_tier_in_range(self, key):
        assert 1 <= ANCHORS[key].tier <= 4

    @pytest.mark.parametrize("key", list(ANCHORS))
    def test_section_is_valid(self, key):
        assert ANCHORS[key].section in ("header", "setlist", "sources", "context")

    def test_convention_list_keys_end_in_brackets(self):
        for key in _SCALAR_KEYS:
            if key.endswith("[]"):
                # A standalone list anchor -- fine, just confirming the shape below.
                assert key.count("[]") == 1

    def test_convention_row_keys_have_prefix_and_sub(self):
        for key in _ROW_KEYS:
            prefix, sub = key.split("[].", 1)
            assert prefix and sub
            assert "[]." not in sub or sub.endswith("[]")  # only a trailing list sub

    def test_registry_is_exhaustive_per_plan(self):
        # Sanity floor -- the plan's four tables list ~90 rows once every
        # "a . b" / ".x / .y" grouping is split into individual keys.
        assert len(ANCHORS) >= 85


# ---------------------------------------------------------------------------
# (a) Fresh-install degrade
# ---------------------------------------------------------------------------

class TestFreshInstallFallback:
    @pytest.fixture()
    def fresh_view(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2000-07-28", db_path=db_path)
            assert "ambiguous" not in result
            yield result["view"]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @pytest.mark.parametrize("key", _SCALAR_KEYS)
    def test_scalar_anchor_present_or_fallback(self, fresh_view, key):
        anchor = ANCHORS[key]
        assert key in fresh_view["fields"], f"{key} missing from view"
        f = fresh_view["fields"][key]
        if anchor.fallback_kind == "required":
            return  # only presence is guaranteed for a required anchor
        assert f["confidence"] == "unavailable"
        if anchor.fallback_kind == "value":
            assert f["value"] == anchor.fallback_value
        else:
            assert f["value"] is None

    def test_row_prefixes_present_even_when_empty(self, fresh_view):
        prefixes = {k.split("[].", 1)[0] for k in _ROW_KEYS}
        for prefix in prefixes:
            assert prefix in fresh_view["rows"]


# ---------------------------------------------------------------------------
# (b) Populated fixture — real values for a representative subset
# ---------------------------------------------------------------------------

class TestPopulatedFixture:
    @pytest.fixture()
    def populated_view(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "3/29/10", location="Zepp Tokyo",
                           rating="A", timing="72min",
                           source_type="AUD",
                           source_chain="Schoeps CMC6 > Sound Devices 744T > CDR")
            _insert_event(conn, 1, "2010-03-29", page_filename="p1")
            conn.execute(
                "UPDATE olof_events SET venue='Zepp Tokyo', city='Tokyo', country='Japan', "
                "tour_name='2010 Tour of Japan', "
                "lineup='Bob Dylan (vocal, guitar, harmonica), Tony Garnier (bass)', "
                "bobtalk='Thank you very much.', notes='some notes' WHERE event_id=1"
            )
            _insert_song(conn, 1, 1, "Rainy Day Women #12 & 35")
            _insert_song(conn, 1, 2, "Forever Young")
            _insert_song_performance(conn, 1, 1, "rainy day women #12 & 35", "2010-03-29")
            _insert_song_performance(conn, 1, 2, "forever young", "2010-03-29")
            _insert_family(conn, 101, "2010-03-29#fam1", "2010-03-29")
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
                "evidence_json, concert_date_iso) VALUES "
                "('3/29/10', 101, 90.0, 1, '[]', '2010-03-29')"
            )
            conn.commit()
            from backend.dossier import build_dossier
            result = build_dossier("2010-03-29", db_path=db_path)
            assert "ambiguous" not in result
            yield result["view"]
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_show_date_and_venue(self, populated_view):
        f = populated_view["fields"]
        assert f["show.date.long"]["value"] == "Mar 29, 2010"
        assert f["show.venue"]["value"] == "Zepp Tokyo"
        assert f["show.venue"]["confidence"] == "stated"
        assert f["show.tour"]["value"] == "2010 Tour of Japan"

    def test_song_rows_have_position_and_title(self, populated_view):
        rows = populated_view["rows"]["song"]
        titles = [r["title"]["value"] for r in rows]
        assert titles == ["Rainy Day Women #12 & 35", "Forever Young"]
        assert rows[0]["position"]["value"] == 1
        assert rows[0]["position"]["confidence"] == "stated"

    def test_source_row_generation_and_lineage(self, populated_view):
        rows = populated_view["rows"]["source"]
        assert len(rows) == 1
        row = rows[0]
        assert row["lb_id"]["value"] == "LB-00101"
        assert row["generation"]["value"] == "master"
        assert row["generation"]["confidence"] == "inferred"
        assert row["generation"]["source"] == "D-05 classify_generation"
        assert row["lineage"]["value"] == "Schoeps CMC6 > Sound Devices 744T > CDR"
        assert row["runtime"]["value"] == 72.0

    def test_band_members_parsed(self, populated_view):
        f = populated_view["fields"]["band.members[]"]
        names = [m["name"] for m in f["value"]]
        assert "Bob Dylan" in names
        assert "Tony Garnier" in names

    def test_pick_populated_from_recommendation(self, populated_view):
        f = populated_view["fields"]
        assert f["pick.lb_id"]["value"] == "LB-00101"
        assert f["pick.lb_id"]["confidence"] == "stated"
        assert f["ledger.total"]["value"] == 90.0

    def test_family_row(self, populated_view):
        rows = populated_view["rows"]["family"]
        assert len(rows) == 1
        assert rows[0]["id"]["value"] == "2010-03-29#fam1"
        assert rows[0]["size"]["value"] == 1

    def test_derived_from_traced(self, populated_view):
        f = populated_view["fields"]["show.venue"]
        assert f["derived_from"] == ["d1.show.venue"]


# ---------------------------------------------------------------------------
# (c) local_analysis filtering
# ---------------------------------------------------------------------------

class TestFilterStripsLocalAnalysis:
    @pytest.fixture()
    def full_result(self):
        db_path, conn, tmp_dir = _make_db()
        try:
            _insert_entry(conn, 101, "7/28/00")
            conn.commit()
            conn.execute(
                "INSERT INTO show_picks (concert_date, lb_number, pick_score, pick_rank, "
                "evidence_json, concert_date_iso) VALUES "
                "('7/28/00', 101, 90.0, 1, '[]', '2000-07-28')"
            )
            conn.commit()
            from backend.dossier import build_dossier
            yield build_dossier("2000-07-28", db_path=db_path)
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_local_analysis_keys_present_when_true(self, full_result):
        assert "ledger.total" in full_result["view"]["fields"]

    def test_filter_view_strips_all_local_analysis_keys(self, full_result):
        filtered = filter_view(full_result["view"], local_analysis=False)
        local_keys = [k for k, a in ANCHORS.items() if a.local_analysis and "[]." not in k]
        for key in local_keys:
            assert key not in filtered["fields"], f"{key} should have been stripped"
        local_row_subs = {
            (k.split("[].", 1)[0], k.split("[].", 1)[1])
            for k, a in ANCHORS.items() if a.local_analysis and "[]." in k
        }
        for prefix, sub in local_row_subs:
            for row in filtered["rows"].get(prefix, []):
                assert sub not in row, f"{prefix}[].{sub} should have been stripped"

    def test_filter_dossier_sections_strips_view_too(self, full_result):
        from backend.dossier import filter_dossier_sections
        filtered = filter_dossier_sections(full_result, local_analysis=False)
        assert "ledger.total" not in filtered["view"]["fields"]
        # Non-local-analysis facts survive.
        assert "show.date.long" in filtered["view"]["fields"]

    def test_section_filtering_drops_setlist_and_context_anchors(self, full_result):
        filtered = filter_view(full_result["view"], sections={"header", "sources"})
        for key, anchor in ANCHORS.items():
            if "[]." in key:
                continue
            if anchor.section in ("setlist", "context"):
                assert key not in filtered["fields"]
            else:
                assert key in filtered["fields"]
