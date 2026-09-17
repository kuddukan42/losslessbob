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


class TestFetchTopicScoping:
    """Only the opening post's attachments belong to the topic."""

    _PAGE = """
    <html><head><title>1978-11-01 Madison</title></head><body>
    <div class="postarea">
      <div class="keyinfo">« on: August 06, 2025, 10:00:00 »</div>
      <div class="post"><div class="inner" id="msg_100">first post, no torrent</div></div>
    </div>
    <div class="postarea">
      <div class="keyinfo">« Reply #1 on: August 07, 2025, 10:00:00 »</div>
      <div class="post"><div class="inner" id="msg_101">re-up of another show</div></div>
      <div class="attachments">
        <a href="index.php?action=dlattach;topic=1.0;attach=9">LB-00999.torrent</a>
      </div>
    </div>
    </body></html>
    """

    class _Resp:
        def __init__(self, text):
            self.text = text
            self.url = "http://www.watchingtheriverflow.org/index.php?topic=1.0"

    def test_a_reply_attachment_is_not_the_first_posts(self, monkeypatch):
        from backend import wtrf_scraper

        monkeypatch.setattr(wtrf_scraper.time, "sleep", lambda _s: None)

        class _S:
            def get(self, url, timeout=None, headers=None):
                return TestFetchTopicScoping._Resp(TestFetchTopicScoping._PAGE)

        post = wtrf_scraper._fetch_topic(_S(), "http://x/index.php?topic=1.0", 0)
        assert post["body_text"].strip() == "first post, no torrent"
        assert post["torrent_url"] is None
        assert post["attachment_text"] == ""
        assert str(post["post_date"]) == "2025-08-06"

    def test_the_first_posts_own_attachment_is_found(self, monkeypatch):
        from backend import wtrf_scraper

        monkeypatch.setattr(wtrf_scraper.time, "sleep", lambda _s: None)
        page = self._PAGE.replace(
            '<div class="post"><div class="inner" id="msg_100">first post, no torrent</div></div>',
            '<div class="post"><div class="inner" id="msg_100">first post</div></div>'
            '<div class="attachments"><a href="index.php?action=dlattach;attach=3">'
            'LB-00707.torrent</a></div>',
        )

        class _S:
            def get(self, url, timeout=None, headers=None):
                return TestFetchTopicScoping._Resp(page)

        post = wtrf_scraper._fetch_topic(_S(), "http://x/index.php?topic=1.0", 0)
        assert post["attachment_text"] == "LB-00707.torrent"
        assert post["torrent_url"].endswith("attach=3")
