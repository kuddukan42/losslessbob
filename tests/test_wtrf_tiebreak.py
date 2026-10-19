"""Tests for TODO-194: WTRF tie-breaker + placeholder taper exclusion.

Fixtures mirror the TODO's audit cases (LB-16596 positive tie, LB-16644
zero-signal tie, "same source recording" placeholder). No network: every HTTP
seam of find_torrent_for_lb is monkeypatched.
"""
from __future__ import annotations

import datetime as dt

import pytest


class TestPlaceholderTaper:
    @pytest.mark.parametrize("name", [
        "same source recording", "Same Source Recording", "unknown", "N/A", "", None,
    ])
    def test_placeholders(self, name):
        from backend.wtrf_scraper import _is_placeholder_taper

        assert _is_placeholder_taper(name)

    @pytest.mark.parametrize("name", ["mkws", "dolphinsmile", "Jeff Z"])
    def test_real_handles(self, name):
        from backend.wtrf_scraper import _is_placeholder_taper

        assert not _is_placeholder_taper(name)

    def test_placeholder_does_not_score_taper_round(self):
        from backend.wtrf_scraper import _score_candidate

        entry = {"lb_number": 1, "taper_name": "same source recording",
                 "source_chain": "", "description": ""}
        body = "this is the same source recording as the other one"
        score, sigs = _score_candidate(body, [], entry)
        assert "taper_match" not in sigs and score == 0

    def test_real_taper_still_scores(self):
        from backend.wtrf_scraper import _score_candidate

        entry = {"lb_number": 1, "taper_name": "mkws", "source_chain": "", "description": ""}
        score, sigs = _score_candidate("taped by mkws", [], entry)
        assert sigs.get("taper_match") == "mkws" and score == 20


class TestParseAttachmentBytes:
    def test_sums_units(self):
        from backend.wtrf_scraper import _parse_attachment_bytes

        assert _parse_attachment_bytes("a.torrent (12.5 KB) b.txt (1 MB)") == 12800 + 1048576

    def test_none(self):
        from backend.wtrf_scraper import _parse_attachment_bytes

        assert _parse_attachment_bytes("no sizes here") == 0


def _cand(score, url, sigs=None):
    return (score, dict(sigs or {"filename_matches": 72, "equipment_matches": 1}), url, "t")


class TestBreakTie:
    def test_lb16596_earliest_post_wins(self):
        """LB-16596: topics 60197/60199 tie at 733; earlier post is the original."""
        from backend.wtrf_scraper import _break_tie

        tied = [_cand(733, "topic=60199"), _cand(733, "topic=60197")]
        meta = {
            "topic=60197": {"post_date": dt.date(2026, 5, 1)},
            "topic=60199": {"post_date": dt.date(2026, 5, 9)},
        }
        assert _break_tie(tied, meta) == 1

    def test_attachment_count_when_dates_equal(self):
        from backend.wtrf_scraper import _break_tie

        d = dt.date(2026, 5, 1)
        tied = [_cand(733, "a"), _cand(733, "b")]
        meta = {"a": {"post_date": d, "attachment_count": 1},
                "b": {"post_date": d, "attachment_count": 3}}
        assert _break_tie(tied, meta) == 1

    def test_identical_metadata_stays_ambiguous(self):
        from backend.wtrf_scraper import _break_tie

        d = dt.date(2026, 5, 1)
        tied = [_cand(733, "a"), _cand(733, "b")]
        meta = {"a": {"post_date": d}, "b": {"post_date": d}}
        assert _break_tie(tied, meta) is None

    def test_lb16644_zero_signal_tie_not_broken(self):
        """LB-16644: topics 59943/59965 tie at score=5 (has_torrent only)."""
        from backend.wtrf_scraper import _break_tie

        tied = [_cand(5, "topic=59943", {"has_torrent": True}),
                _cand(5, "topic=59965", {"has_torrent": True})]
        meta = {"topic=59943": {"post_date": dt.date(2026, 1, 1)},
                "topic=59965": {"post_date": dt.date(2026, 2, 1)}}
        assert _break_tie(tied, meta) is None


class TestFindTorrentTie:
    """find_torrent_for_lb end to end with every network seam mocked."""

    def _run(self, monkeypatch, tmp_path, posts):
        import backend.db as db
        import backend.wtrf_scraper as ws

        entry = {"lb_number": 16596, "date_str": "05/01/26", "taper_name": "",
                 "source_chain": "", "description": ""}
        checks = [{"chk_type": "x", "checksum": "", "filename": f"f{i}.flac"}
                  for i in range(3)]
        monkeypatch.setattr(db, "get_entry",
                            lambda lb, db_path=None: {"entry": entry, "checksums": checks})
        monkeypatch.setattr(db, "lookup_checksum_owners", lambda h, db_path=None: {})
        monkeypatch.setattr(ws, "get_credentials", lambda svc: ("u", "p"))
        monkeypatch.setattr(ws, "_get_session", lambda u, p: object())
        monkeypatch.setattr(ws, "_search_board",
                            lambda *a, **k: [(u, "t") for u in posts])
        monkeypatch.setattr(ws, "_fetch_topic", lambda s, url, d: posts[url])
        monkeypatch.setattr(ws, "_download_torrent",
                            lambda *a, **k: tmp_path / "x.torrent")
        return ws.find_torrent_for_lb(16596, 16, tmp_path, delay=0)

    @staticmethod
    def _post(day, count=1):
        return {"body_text": "f0.flac f1.flac f2.flac", "torrent_url": "http://x/t",
                "topic_title": "", "attachment_text": "", "post_date": dt.date(2026, 5, day),
                "attachment_count": count, "attachment_bytes": 0}

    def test_tie_resolved_to_earliest(self, monkeypatch, tmp_path):
        posts = {"http://w/?topic=60199.0": self._post(9),
                 "http://w/?topic=60197.0": self._post(1)}
        res = self._run(monkeypatch, tmp_path, posts)
        assert res["ok"] and res["topic_url"].endswith("60197.0")
        assert res["signals"]["tiebreak"] == "earliest_post"
        assert res["signals"]["tied_with"] == ["http://w/?topic=60199.0"]

    def test_unresolvable_tie_records_candidates(self, monkeypatch, tmp_path):
        posts = {"http://w/?topic=1.0": self._post(1), "http://w/?topic=2.0": self._post(1)}
        res = self._run(monkeypatch, tmp_path, posts)
        assert res["confidence"] == "ambiguous"
        assert set(res["signals"]["tied_candidates"]) == set(posts)
