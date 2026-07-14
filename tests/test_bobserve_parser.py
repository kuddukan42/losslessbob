"""
Tests for the bobserve.com setlist parser (backend/bobserve_parser.py).

Covers three field-quality fixes made against the 391-show 2022+ bobserve
corpus loaded under TODO-228:
  - _normalize_event_type()   — bobserve free-text event_type -> DSN taxonomy
  - _split_bobserve_location() — US 'City, State' / 'City, District, State'
                                  headers vs. the shared City/Region/Country split
  - parse_page() tour_name guard — skip 'Musicians' / 'Info via bobserve:' /
                                    bare-URL lines mistaken for the tour name
"""
from __future__ import annotations

import pytest

from backend.bobserve_parser import _normalize_event_type, _split_bobserve_location, parse_page

# ═══════════════════════════════════════════════════════════════════════════════
# 1. _normalize_event_type()
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizeEventType:
    @pytest.mark.parametrize("raw, expected_normalized, expected_raw_stripped", [
        ("Concert", "concert", "Concert"),
        ("concert - outlaw music festival", "concert", "concert - outlaw music festival"),
        ("benefit - farm aid", "concert", "benefit - farm aid"),
        ("soundcheck", "other", "soundcheck"),
        ("tribute speech - nobel banquet", "other", "tribute speech - nobel banquet"),
        ("rehearsal", "rehearsal", "rehearsal"),
        ("session", "session", "session"),
        ("broadcast", "broadcast", "broadcast"),
        ("interview", "interview", "interview"),
        ("something else entirely", "other", "something else entirely"),
        ("", "other", ""),
        ("  Concert  ", "concert", "Concert"),
    ])
    def test_maps_prefix_to_canonical_taxonomy(
        self, raw, expected_normalized, expected_raw_stripped
    ):
        normalized, raw_stripped = _normalize_event_type(raw)
        assert normalized == expected_normalized
        assert raw_stripped == expected_raw_stripped


# ═══════════════════════════════════════════════════════════════════════════════
# 2. _split_bobserve_location()
# ═══════════════════════════════════════════════════════════════════════════════

class TestSplitBobserveLocation:
    def test_us_two_part_city_state(self):
        result = _split_bobserve_location(["Redding", "California"])
        assert result == {"city": "Redding", "region": "California", "country": ""}

    def test_us_three_part_drops_district(self):
        result = _split_bobserve_location(["Hollywood", "Los Angeles", "California"])
        assert result == {"city": "Los Angeles", "region": "California", "country": ""}

    def test_us_state_match_is_case_insensitive(self):
        result = _split_bobserve_location(["Austin", "texas"])
        assert result == {"city": "Austin", "region": "texas", "country": ""}

    def test_non_us_two_part_unchanged(self):
        result = _split_bobserve_location(["Oslo", "Norway"])
        assert result == {"city": "Oslo", "region": "", "country": "Norway"}

    def test_non_us_three_part_defers_to_shared_split(self):
        result = _split_bobserve_location(["London", "England", "United Kingdom"])
        assert result == {"city": "London", "region": "England", "country": "United Kingdom"}

    def test_single_part_defers_to_shared_split(self):
        result = _split_bobserve_location(["Paris"])
        assert result == {"city": "Paris", "region": "", "country": ""}


# ═══════════════════════════════════════════════════════════════════════════════
# 3. parse_page() tour_name guard
# ═══════════════════════════════════════════════════════════════════════════════

def _write_clipboard_page(tmp_path, blocks: list[list[str]], filename: str):
    """Write a minimal HTML page with a data-clipboard-text blob from *blocks*."""
    clipboard_text = "\n\n".join("\n".join(block) for block in blocks)
    html = f'<html><body><button data-clipboard-text="{clipboard_text}"></button></body></html>'
    path = tmp_path / filename
    path.write_text(html, encoding="utf-8")
    return path


_HEADER_BLOCK = ["July 4, 2023", "Redding, California", "Shasta Lake Amphitheater", "Concert"]
_SONG_BLOCK = ["1. Song A", "2. Song B"]


class TestTourNameGuard:
    def test_normal_tour_line_is_kept(self, tmp_path):
        blocks = [_HEADER_BLOCK, _SONG_BLOCK, ["Rough and Rowdy Ways World Wide Tour", "2023"]]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_1.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_1.html")
        assert rec.tour_name == "Rough and Rowdy Ways World Wide Tour"

    def test_musicians_header_is_skipped_leaving_empty_tour_name(self, tmp_path):
        blocks = [_HEADER_BLOCK, _SONG_BLOCK, ["Musicians"]]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_2.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_2.html")
        assert rec.tour_name == ""

    def test_musicians_header_is_case_insensitive(self, tmp_path):
        blocks = [_HEADER_BLOCK, _SONG_BLOCK, ["musicians"]]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_3.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_3.html")
        assert rec.tour_name == ""

    def test_info_via_bobserve_line_is_skipped(self, tmp_path):
        blocks = [
            _HEADER_BLOCK, _SONG_BLOCK,
            ["Info via bobserve: https://bobserve.com/event/1234"],
        ]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_4.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_4.html")
        assert rec.tour_name == ""

    def test_bare_url_line_is_skipped(self, tmp_path):
        blocks = [_HEADER_BLOCK, _SONG_BLOCK, ["http://example.com/some-event"]]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_5.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_5.html")
        assert rec.tour_name == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. parse_page() event_type normalization + notes preservation (integration)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParsePageEventType:
    def test_festival_concert_is_normalized_with_raw_preserved_in_notes(self, tmp_path):
        header = ["July 4, 2023", "Hollywood, Los Angeles, California",
                  "Hollywood Bowl", "concert - outlaw music festival"]
        blocks = [header, _SONG_BLOCK]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_6.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_6.html")

        assert rec.event_type == "concert"
        assert rec.notes == "event_type_raw: concert - outlaw music festival"
        assert rec.city == "Los Angeles"
        assert rec.region == "California"
        assert rec.country == ""

    def test_case_only_event_type_leaves_notes_empty(self, tmp_path):
        # bobserve's usual casing is "Concert"; a case-only difference from the
        # normalized "concert" carries no extra detail, so notes stays empty
        # rather than filling every row with "event_type_raw: Concert".
        header = ["July 4, 2023", "Redding, California", "Shasta Lake Amphitheater", "Concert"]
        blocks = [header, _SONG_BLOCK]
        path = _write_clipboard_page(tmp_path, blocks, "bobserve_event_7.html")
        rec, _songs, _status = parse_page(path, "bobserve_event_7.html")

        assert rec.event_type == "concert"
        assert rec.notes == ""
