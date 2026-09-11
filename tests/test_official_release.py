"""Tests for backend.dossier_fields D-03 (official_release, TODO-342 C19) and
backend.qc.rules.rule_r1. Uses an in-memory olof_events/olof_songs schema and a
small synthetic allowlist so these tests never depend on the live corpus or
backend/assets/official_releases.json.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.dossier_fields import (
    ReleaseAllowlistEntry,
    classify_release_string,
    normalize_title_key,
    official_release,
    release_overrides,
    split_release_tokens,
    strip_release_prefix,
)
from backend.qc.rules import rule_r1

_ALLOW = [
    ReleaseAllowlistEntry(
        title="Biograph", year=1985, kind="compilation", official=True,
        patterns=(__import__("re").compile(r"\bbiograph\b", __import__("re").IGNORECASE),),
    ),
    ReleaseAllowlistEntry(
        title="Wolfgang's Vault", year=None, kind="bootleg", official=False,
        patterns=(__import__("re").compile(r"wolfgang.s vault", __import__("re").IGNORECASE),),
    ),
]


@pytest.fixture
def conn():
    """A throwaway in-memory DB with just the tables official_release() reads."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE olof_events (
            event_id INTEGER PRIMARY KEY, date_str TEXT NOT NULL DEFAULT '',
            releases_raw TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE olof_songs (
            event_id INTEGER NOT NULL, position INTEGER NOT NULL,
            song_title TEXT NOT NULL DEFAULT '', released_on TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (event_id, position)
        );
        CREATE TABLE release_classifications (
            title_key TEXT PRIMARY KEY, official INTEGER NOT NULL DEFAULT 0,
            decided_by TEXT, decided_at TEXT, note TEXT
        );
        """
    )
    return c


def _insert_event(conn, event_id, date_str, releases_raw=""):
    conn.execute(
        "INSERT INTO olof_events (event_id, date_str, releases_raw) VALUES (?, ?, ?)",
        (event_id, date_str, releases_raw),
    )


def _insert_song(conn, event_id, position, title, released_on=""):
    conn.execute(
        "INSERT INTO olof_songs (event_id, position, song_title, released_on) VALUES"
        " (?, ?, ?, ?)",
        (event_id, position, title, released_on),
    )


class TestNormalizeTitleKey:
    def test_folds_case_and_punctuation(self):
        assert normalize_title_key("Biograph, Columbia C5X!") == "biograph-columbia-c5x"

    def test_never_empty(self):
        assert normalize_title_key("") != ""
        assert normalize_title_key(None) != ""

    def test_truncates_long_strings_with_digest_suffix(self):
        long_text = "x" * 200
        key = normalize_title_key(long_text)
        assert len(key) <= 89  # 80 + '-' + 8 hex chars
        assert key.startswith("x" * 80)


class TestClassifyReleaseString:
    def test_allowlist_match(self):
        key, title, official = classify_release_string("BIOGRAPH, Columbia", _ALLOW, {})
        assert title == "Biograph"
        assert official is True

    def test_unmatched_is_unclassified(self):
        key, title, official = classify_release_string("some random string", _ALLOW, {})
        assert title is None
        assert official is None

    def test_override_wins_over_allowlist(self):
        key = normalize_title_key("BIOGRAPH, Columbia")
        _, title, official = classify_release_string(
            "BIOGRAPH, Columbia", _ALLOW, {key: False},
        )
        assert official is False


class TestOfficialRelease:
    def test_no_event_returns_none(self, conn):
        assert official_release(conn, 999, allowlist=_ALLOW) is None

    def test_whole_show_official_line_is_full(self, conn):
        _insert_event(conn, 1, "1965-06-01", "Released on BIOGRAPH, Columbia C5X, 1985")
        _insert_song(conn, 1, 1, "Song A")
        _insert_song(conn, 1, 2, "Song B")
        result = official_release(conn, 1, allowlist=_ALLOW)
        assert result["status"] == "full"
        assert result["whole_show"] is True
        assert result["whole_show_title"] == "Biograph"

    def test_every_position_covered_is_full(self, conn):
        _insert_event(conn, 2, "1986-02-24")
        _insert_song(conn, 2, 1, "Song A", "BIOGRAPH, Columbia")
        _insert_song(conn, 2, 2, "Song B", "BIOGRAPH, Columbia")
        result = official_release(conn, 2, allowlist=_ALLOW)
        assert result["status"] == "full"
        assert result["whole_show"] is False

    def test_partial_coverage(self, conn):
        _insert_event(conn, 3, "1986-02-24")
        _insert_song(conn, 3, 1, "Song A", "BIOGRAPH, Columbia")
        _insert_song(conn, 3, 2, "Song B", "Wolfgang's Vault")
        result = official_release(conn, 3, allowlist=_ALLOW)
        assert result["status"] == "partial"

    def test_part_and_uncertain_never_promote_to_full(self, conn):
        _insert_event(conn, 4, "1986-02-24")
        _insert_song(conn, 4, 1, "Song A", "(part) BIOGRAPH, Columbia")
        _insert_song(conn, 4, 2, "Song B", "(uncertain) BIOGRAPH, Columbia")
        result = official_release(conn, 4, allowlist=_ALLOW)
        assert result["status"] == "partial"
        for s in result["songs"]:
            assert s["official"] is False
            assert s["partial"] is True

    def test_no_official_match_is_none(self, conn):
        _insert_event(conn, 5, "1975-12-08")
        _insert_song(conn, 5, 1, "Song A", "Wolfgang's Vault")
        _insert_song(conn, 5, 2, "Song B")
        result = official_release(conn, 5, allowlist=_ALLOW)
        assert result["status"] == "none"

    def test_position_specific_line_is_not_whole_show(self, conn):
        _insert_event(conn, 6, "1986-02-24", "4, 9 released on BIOGRAPH, Columbia")
        _insert_song(conn, 6, 1, "Song A")
        _insert_song(conn, 6, 4, "Song D")
        result = official_release(conn, 6, allowlist=_ALLOW)
        assert result["whole_show"] is False
        assert result["status"] == "none"  # no olof_songs row carries the released_on token

    def test_release_classifications_table_wins(self, conn):
        conn.execute(
            "INSERT INTO release_classifications (title_key, official) VALUES (?, 0)",
            (normalize_title_key("BIOGRAPH, Columbia"),),
        )
        _insert_event(conn, 7, "1986-02-24")
        _insert_song(conn, 7, 1, "Song A", "BIOGRAPH, Columbia")
        result = official_release(conn, 7, allowlist=_ALLOW)
        assert result["status"] == "none"
        assert result["songs"][0]["matches"][0]["official"] is False


class TestSplitAndStripHelpers:
    def test_split_release_tokens(self):
        assert split_release_tokens("A; B ; C") == ["A", "B", "C"]
        assert split_release_tokens("") == []
        assert split_release_tokens(None) == []

    def test_strip_release_prefix_part(self):
        text, is_part, is_uncertain = strip_release_prefix("(part) BIOGRAPH")
        assert (text, is_part, is_uncertain) == ("BIOGRAPH", True, False)

    def test_strip_release_prefix_uncertain(self):
        text, is_part, is_uncertain = strip_release_prefix("(uncertain) BIOGRAPH")
        assert (text, is_part, is_uncertain) == ("BIOGRAPH", False, True)

    def test_strip_release_prefix_none(self):
        assert strip_release_prefix("BIOGRAPH") == ("BIOGRAPH", False, False)


class TestReleaseOverrides:
    def test_empty_when_table_missing(self):
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        assert release_overrides(c) == {}

    def test_reads_rows(self, conn):
        conn.execute(
            "INSERT INTO release_classifications (title_key, official) VALUES ('x', 1)"
        )
        assert release_overrides(conn) == {"x": True}


class TestRuleR1:
    def test_unclassified_string_yields_one_finding(self, conn):
        _insert_event(conn, 1, "1975-12-08", "Released on Some Obscure Fan CD, 1999")
        _insert_song(conn, 1, 1, "Song A")
        findings = list(rule_r1(conn))
        assert len(findings) == 1
        f = findings[0]
        assert f.entity_kind == "release"
        assert f.severity == "warn"
        assert f.evidence["count"] == 1
        assert "1975-12-08" in f.evidence["dates"]

    def test_classified_strings_produce_no_finding(self, conn):
        _insert_event(conn, 1, "1986-02-24")
        _insert_song(conn, 1, 1, "Song A", "BIOGRAPH, Columbia")
        _insert_song(conn, 1, 2, "Song B", "Wolfgang's Vault")
        findings = list(rule_r1(conn))
        assert findings == []

    def test_override_suppresses_finding(self, conn):
        raw = "Some Obscure Fan CD, 1999"
        line = f"Released on {raw}"
        conn.execute(
            "INSERT INTO release_classifications (title_key, official) VALUES (?, 0)",
            (normalize_title_key(line),),
        )
        _insert_event(conn, 1, "1975-12-08", line)
        _insert_song(conn, 1, 1, "Song A")
        findings = list(rule_r1(conn))
        assert findings == []

    def test_repeated_string_groups_into_one_finding_with_count(self, conn):
        raw = "Released on Some Obscure Fan CD, 1999"
        _insert_event(conn, 1, "1975-12-08", raw)
        _insert_event(conn, 2, "1975-12-09", raw)
        _insert_song(conn, 1, 1, "Song A")
        _insert_song(conn, 2, 1, "Song A")
        findings = list(rule_r1(conn))
        assert len(findings) == 1
        assert findings[0].evidence["count"] == 2
        assert findings[0].evidence["dates"] == ["1975-12-08", "1975-12-09"]

    def test_position_specific_line_not_double_counted_against_whole_show(self, conn):
        # A leading-digit line only contributes via olof_songs.released_on, not
        # again as a "whole-show" candidate.
        _insert_event(conn, 1, "1986-02-24", "4 released on Some Obscure Fan CD, 1999")
        _insert_song(conn, 1, 4, "Song D", "Some Obscure Fan CD, 1999")
        findings = list(rule_r1(conn))
        assert len(findings) == 1
        assert findings[0].evidence["count"] == 1
