"""
Tests for the WTRF forum torrent scraper (backend/wtrf_scraper.py).

Covers:
  - _filename_from_content_disposition() — Content-Disposition header parsing
    (pure function). Regression coverage for BUG-233: the RFC 5987 extended
    form filename*=UTF-8''realname.torrent used to be mis-parsed as the junk
    filename "UTF-8.torrent", overwriting every download in a batch run.
"""
from __future__ import annotations


class TestFilenameFromContentDisposition:
    def test_plain_filename(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = 'attachment; filename="realname.torrent"'
        assert _filename_from_content_disposition(cd) == "realname.torrent"

    def test_plain_filename_unquoted(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = "attachment; filename=realname.torrent"
        assert _filename_from_content_disposition(cd) == "realname.torrent"

    def test_extended_filename_only(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = "attachment; filename*=UTF-8''realname.torrent"
        assert _filename_from_content_disposition(cd) == "realname.torrent"

    def test_extended_filename_percent_encoded(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        # Space encoded as %20, per RFC 5987 (not '+', which is only a form
        # of legacy application/x-www-form-urlencoded space encoding).
        cd = "attachment; filename*=UTF-8''real%20name.torrent"
        assert _filename_from_content_disposition(cd) == "real name.torrent"

    def test_extended_filename_non_ascii(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        # e2 82 ac is UTF-8 for the euro sign.
        cd = "attachment; filename*=UTF-8''r%e2%82%acal.torrent"
        assert _filename_from_content_disposition(cd) == "r€al.torrent"

    def test_both_plain_and_extended_prefers_plain(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = (
            'attachment; filename="fallback.torrent"; '
            "filename*=UTF-8''realname.torrent"
        )
        assert _filename_from_content_disposition(cd) == "fallback.torrent"

    def test_extended_before_plain_still_prefers_plain(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = (
            "attachment; filename*=UTF-8''realname.torrent; "
            'filename="fallback.torrent"'
        )
        assert _filename_from_content_disposition(cd) == "fallback.torrent"

    def test_neither_present_returns_none(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        assert _filename_from_content_disposition("attachment") is None

    def test_empty_header_returns_none(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        assert _filename_from_content_disposition("") is None

    def test_extended_filename_no_charset_prefix(self):
        from backend.wtrf_scraper import _filename_from_content_disposition

        # Malformed / minimal form with no charset''language'' prefix at all —
        # still decoded rather than left as the raw undecoded value.
        cd = "attachment; filename*=realname.torrent"
        assert _filename_from_content_disposition(cd) == "realname.torrent"

    def test_extended_filename_never_yields_charset_token(self):
        """Regression guard for BUG-233 itself: the old regex captured the
        charset token ('UTF-8') instead of the real filename."""
        from backend.wtrf_scraper import _filename_from_content_disposition

        cd = "attachment; filename*=UTF-8''LB-16644-realname.torrent"
        result = _filename_from_content_disposition(cd)
        assert result != "UTF-8"
        assert result == "LB-16644-realname.torrent"
