"""Parser tests for backend.tuit_scraper.

The HTML fixtures below mirror the real TUIT markup (a Laravel app) but are
hand-written, so no scraped page carrying a session token or member name is
committed to the repo.
"""
import json
from pathlib import Path

import pytest

from backend.tuit_scraper import (
    BrowseRow,
    Recording,
    _unique_torrent_path,
    browse_total,
    merge_row_into_recording,
    parse_browse,
    parse_recording,
    parse_rss,
    parse_size,
    parse_song_page,
    parse_songs_index,
    parse_tour_index,
    parse_tour_page,
    parse_venue_page,
    recording_id_from_url,
    recording_to_json_fields,
    redact_passkey,
    rss_url,
    save_recording_html,
    songs_page_count,
    tour_name_from_url,
    venue_page_count,
)

BROWSE_HTML = """
<nav><a href="/browse"><span class="lbl">Browse</span><span class="n m">5,638</span></a></nav>
<aside>1960s 256 recordings</aside>
<div class="bx-show">
  <div class="bx-row">
    <span class="bx-tile" data-dec="1970">&rsquo;78</span>
    <span class="bx-dt" title="Added 7 h ago (20 Aug 2026, 00:46) by tabby">1978-10-07</span>
    <span class="bx-nm" title="Civic Center, Providence, Rhode Island, United States">
      <a class="bx-link" href="https://tangledupintorrents.org/recordings/1837">
        <b>Civic Center</b>
        <span class="pl"><span class="mdt">1978-10-07 &middot;</span>
          Providence, United States</span>
      </a>
    </span>
    <span class="bx-tp" title="Taper: mjk5510">mjk5510</span>
    <span class="bx-sg">22 songs</span>
    <span class="bx-src"><span class="bx-tag aud">AUD</span></span>
    <span class="bx-lb">LB-11637</span>
    <span class="bx-sz">1 GB</span>
    <span class="bx-peers" title="3 seeding &middot; 0 leeching &middot; 12 snatched">
      <span class="bx-mtr lo"><i class="on"></i><i></i></span>
      <span class="bx-mn lo">3<span class="sr-only"> seeders</span></span>
    </span>
    <a class="bx-dl" aria-label="Download .torrent, Civic Center 1978-10-07"
       href="https://tangledupintorrents.org/show/1837/download"></a>
  </div>
  <div class="bx-subs">
    <div class="bx-row is-sub">
      <span class="bx-tile" data-dec="1970">&rsquo;78</span>
      <span class="bx-dt" title="Added 2026-08-19 (19 Aug 2026, 02:50) by tabby"></span>
      <span class="bx-nm" title="Civic Center, Providence, United States">
        <a class="bx-link" href="https://tangledupintorrents.org/recordings/900">1st gen reel</a>
      </span>
      <span class="bx-tp" title="Taper: "></span>
      <span class="bx-src"><span class="bx-tag sbd">SBD</span></span>
      <span class="bx-lb none">none</span>
      <span class="bx-peers" title="0 seeding &middot; 0 leeching &middot; 0 snatched"></span>
      <a class="bx-dl" aria-label="Download .torrent, Civic Center 1978-10-07"
         href="https://tangledupintorrents.org/show/900/download"></a>
    </div>
  </div>
</div>
"""

RECORDING_HTML = """
<nav class="rc-crumbs">
  <a class="rc-crumb" href="/browse">Browse</a>
  <a class="rc-crumb sub" href="https://tangledupintorrents.org/shows/4247">Show page</a>
  <a class="rc-crumb sub" href="https://tangledupintorrents.org/browse?q=Street+Legal+Tour"
    >Street Legal Tour</a>
</nav>
<section class="rc-hero nocov" data-dec="1970">
  <div class="rc-hero-main">
    <div class="rc-date">7 Oct 1978</div>
    <h1>Civic Center, Providence, United States</h1>
    <div class="rc-stats">
      <span><span class="bx-tag aud">AUD</span> Audience</span>
      <span class="m">LB-11637</span>
      <span>FLAC 16/44</span>
      <span class="m">1 GB</span>
      <span class="m"><span class="rc-dot"></span>1 seeding <i>&middot; 0 leeching</i></span>
      <span class="m">4 downloads</span>
    </div>
    <div class="rc-pills">
      <span class="rc-pill" data-q="very-good">Very good</span>
      <span class="rc-pill good">Freeleech</span>
    </div>
    <div class="rc-act">
      <a class="rl-btn pri" href="https://tangledupintorrents.org/show/1837/download"
        >Download .torrent</a>
    </div>
  </div>
</section>
<div class="rc-player" data-audio="https://tangledupintorrents.org/storage/samples/1837.mp3"></div>
<img class="rc-sgram" src="https://tangledupintorrents.org/storage/spectrograms/1837.png?v=17">
<section class="rl-box rc-setlist">
  <div class="rc-tr sl"><span class="n">1</span>
    <a href="https://tangledupintorrents.org/song/My%20Back%20Pages">My Back Pages</a></div>
  <div class="rc-tr sl"><span class="n">2</span>
    <a href="https://tangledupintorrents.org/song/Tangled%20Up%20In%20Blue"
      >Tangled Up In Blue</a></div>
</section>
<div class="rc-up"><span class="rl-av">T</span>
  <div><b><a class="rl-member" href="https://tangledupintorrents.org/profile/tabby">tabby</a></b>
  <small>uploaded 1 minute ago</small></div>
  <form><input type="hidden" name="recording_id" value="1837"></form>
</div>
<section class="rl-box rc-list" id="same-night">
  <div class="rc-row cur" aria-current="true">
    <span class="rc-nm"><b>mjk5510</b>
      <span>You're viewing this &middot; Very good &middot; FLAC 16/44</span></span>
    <span class="bx-src"><span class="bx-tag aud">AUD</span></span>
    <span class="bx-lb">LB-11637</span>
    <span class="bx-sz">1 GB</span>
    <span class="bx-peers"><span class="bx-mn lo">1</span></span>
    <span class="bx-sz" title="0 completed downloads">0</span>
  </div>
  <div class="rc-row">
    <span class="rc-nm"><b>
      <a class="rc-link" href="https://tangledupintorrents.org/recordings/1838">net taper</a>
      <span class="rc-pill good" title="file listing matches">Lossless Bob match</span></b>
      <span>Excellent &middot; FLAC 16/44</span></span>
    <span class="bx-src"><span class="bx-tag aud">AUD</span></span>
    <span class="bx-lb">LB-11638</span>
    <span class="bx-sz">786 MB</span>
    <span class="bx-peers"><span class="bx-mn ok">2</span></span>
    <span class="bx-sz" title="5 completed downloads">5</span>
  </div>
</section>
<div class="rc-pane" id="rcPane-info"><pre class="rc-nfo">Bob Dylan
Civic Center
7 October 1978</pre></div>
<div class="rc-pane" id="rcPane-chain"><section class="rl-box rc-chain">
  <ol class="rc-steps"><li><span>1st gen reel</span></li><li><span>DAT - clone</span></li>
    <li><span>tlh</span></li></ol>
  <dl class="rc-facts"><div><dt>Taper</dt><dd>mjk5510</dd></div>
    <div><dt>Equipment</dt><dd>reel</dd></div></dl>
</section></div>
<div class="rc-pane" id="rcPane-files">
  <div class="rc-tr f2"><span class="nm">bd1978-10-07d1t01.flac</span>
    <span class="m r">38.70 MB</span></div>
  <div class="rc-tr f2"><span class="nm">bd1978-10-07.ffp.txt</span>
    <span class="m r">1.59 KB</span></div>
</div>
<p class="rc-hash">Bob Dylan Providence 1978<br>
  info hash 1B00B58B849E69E4B4D9601C257DBD406276F47E</p>
"""

class TestHelpers:
    @pytest.mark.parametrize("label,expected", [
        ("1,006.42 MB", 1055307857),
        ("38.70 KB", 39628),
        ("2 GB", 2147483648),
        ("512 B", 512),
    ])
    def test_parse_size(self, label, expected):
        assert parse_size(label) == expected

    @pytest.mark.parametrize("label", ["", "unknown", None, "lots"])
    def test_parse_size_rejects_junk(self, label):
        assert parse_size(label) is None

    def test_recording_id_from_url(self):
        assert recording_id_from_url("/recordings/1837") == 1837
        assert recording_id_from_url(
            "https://tangledupintorrents.org/recordings/42?x=1"
        ) == 42
        assert recording_id_from_url("/shows/1837") is None
        assert recording_id_from_url("") is None


class TestParseBrowse:
    def test_row_count_and_total(self):
        rows = parse_browse(BROWSE_HTML)
        assert len(rows) == 2
        # The nav count, not a decade sidebar's "256 recordings".
        assert browse_total(BROWSE_HTML) == 5638

    def test_full_row_fields(self):
        row = parse_browse(BROWSE_HTML)[0]
        assert row.rec_id == 1837
        assert row.source_type == "AUD"
        assert row.date_str == "1978-10-07"
        assert row.venue_location.startswith("Civic Center, Providence")
        assert row.lb_number == 11637
        assert row.lineage == ""              # a show's top row names the venue
        assert (row.seeders, row.leechers, row.snatched) == (3, 0, 12)
        assert row.taper == "mjk5510"
        assert row.uploader == "tabby"
        assert row.uploader_url.endswith("/profile/tabby")
        assert row.added_at == "2026-08-20T00:46:00+00:00"
        assert row.added_label == "7 h ago"

    def test_sub_row_takes_its_date_from_the_download_label(self):
        row = parse_browse(BROWSE_HTML)[1]
        assert row.rec_id == 900
        assert row.date_str == "1978-10-07"
        assert row.source_type == "SBD"
        assert row.lb_number is None          # "none"
        assert row.lineage == "1st gen reel"
        assert row.taper == ""
        assert (row.seeders, row.leechers, row.snatched) == (0, 0, 0)

    def test_empty_html_yields_no_rows(self):
        assert parse_browse("<html><body></body></html>") == []
        assert browse_total("<html></html>") is None


class TestParseRecording:
    @pytest.fixture(scope="class")
    def rec(self):
        return parse_recording(RECORDING_HTML, rec_id=1837)

    def test_identity_and_show(self, rec):
        assert rec.rec_id == 1837
        assert rec.show_id == 1837
        assert rec.lb_number == 11637
        assert rec.detail_url.endswith("/recordings/1837")
        assert rec.torrent_url.endswith("/show/1837/download")

    def test_reads_id_from_page_when_not_supplied(self):
        assert parse_recording(RECORDING_HTML).rec_id == 1837

    def test_hero(self, rec):
        assert rec.date_str == "1978-10-07"
        assert rec.venue == "Civic Center"
        assert rec.location == "Providence, United States"
        assert rec.tour == "Street Legal Tour"
        assert rec.source_label == "Audience"
        assert rec.source_type == "AUD"
        assert rec.format == "FLAC 16/44"
        assert rec.title == "Civic Center, Providence, United States"
        assert rec.eyebrow == "7 Oct 1978 · Street Legal Tour · Audience"

    def test_info_hash_is_read_from_the_hash_line(self, rec):
        assert rec.info_hash == "1b00b58b849e69e4b4d9601c257dbd406276f47e"

    def test_size_comes_from_the_file_list_not_the_rounded_hero(self, rec):
        assert rec.size_label == "1 GB"
        assert rec.size_bytes == parse_size("38.70 MB") + 1628
        assert rec.n_files == 2
        assert rec.n_sources == 2
        assert rec.headline == "2 recordings of this show"
        assert (rec.seeders, rec.leechers, rec.snatched) == (1, 0, 4)

    def test_flags(self, rec):
        assert rec.freeleech is True
        assert rec.lb_verified is False       # the hero no longer carries it
        assert rec.quality == "Very good" and rec.quality_slug == "very-good"

    def test_taper_and_uploader(self, rec):
        assert rec.taper == "mjk5510"
        assert rec.uploader == "tabby"
        assert rec.uploaded_label == "1 minute ago"

    def test_lineage(self, rec):
        assert rec.lineage_nodes == ["1st gen reel", "DAT - clone", "tlh"]
        assert rec.lineage == "1st gen reel > DAT - clone > tlh"

    def test_info_text(self, rec):
        assert rec.info_text.startswith("Bob Dylan")
        assert "7 October 1978" in rec.info_text

    def test_setlist_urls_keep_the_old_relative_form(self, rec):
        assert len(rec.setlist) == 2
        assert rec.setlist[0] == {
            "track": "1", "song": "My Back Pages", "song_url": "/song/My+Back+Pages",
        }

    def test_files(self, rec):
        assert len(rec.files) == 2
        assert rec.files[0]["name"] == "bd1978-10-07d1t01.flac"
        assert rec.files[1]["size_bytes"] == 1628

    def test_siblings(self, rec):
        assert len(rec.siblings) == 2
        current, other = rec.siblings
        assert current["is_current"] is True
        assert current["url"] == ""
        assert other["is_current"] is False
        assert other["rec_id"] == 1838
        assert other["lb_number"] == 11638
        assert other["lb_match"] is True
        assert other["seeders"] == 2
        assert other["snatched"] == 5
        assert other["size_label"] == "786 MB"

    def test_media_urls(self, rec):
        assert rec.spectrogram_url.endswith("/storage/spectrograms/1837.png")
        assert rec.preview_url.endswith("/storage/samples/1837.mp3")

    def test_missing_sections_do_not_raise(self):
        rec = parse_recording("<div class='wrap'></div>")
        assert rec.rec_id is None
        assert rec.setlist == [] and rec.files == [] and rec.siblings == []
        assert rec.size_bytes is None


class TestMergeRow:
    def test_row_taper_wins_over_blank_detail(self):
        rec = Recording(rec_id=1837)
        row = parse_browse(BROWSE_HTML)[0]
        merge_row_into_recording(rec, row)
        assert rec.taper == "mjk5510"

    def test_detail_values_are_not_overwritten(self):
        rec = Recording(lb_number=11637, lineage="detail lineage", quality="Poor")
        row = BrowseRow(lb_number=999, lineage="row lineage", quality="Great")
        merge_row_into_recording(rec, row)
        assert rec.lb_number == 11637
        assert rec.lineage == "detail lineage"
        assert rec.quality == "Poor"

    def test_blank_detail_fields_are_filled(self):
        rec = Recording()
        row = BrowseRow(lb_number=707, lineage="reel > dat", uploader="tabby",
                        seeders=5, freeleech=True)
        merge_row_into_recording(rec, row)
        assert rec.lb_number == 707
        assert rec.lineage == "reel > dat"
        assert rec.uploader == "tabby"
        assert rec.seeders == 5
        assert rec.freeleech is True

    def test_zero_swarm_counts_are_not_treated_as_missing(self):
        rec = Recording(seeders=0)
        merge_row_into_recording(rec, BrowseRow(seeders=99))
        assert rec.seeders == 0


class TestJsonFields:
    def test_round_trips(self):
        rec = parse_recording(RECORDING_HTML, rec_id=1837)
        fields = recording_to_json_fields(rec)
        assert json.loads(fields["lineage_json"]) == rec.lineage_nodes
        assert len(json.loads(fields["setlist_json"])) == 2
        assert len(json.loads(fields["files_json"])) == 2
        assert len(json.loads(fields["siblings_json"])) == 2


class TestSaveRecordingHtml:
    """save_recording_html() archives the raw detail page."""

    def test_writes_named_file(self, tmp_path):
        path = save_recording_html("<html>x</html>", 42, tmp_path / "html")
        assert path == tmp_path / "html" / "rec-42.html"
        assert path.read_text(encoding="utf-8") == "<html>x</html>"

    def test_overwrites_existing(self, tmp_path):
        save_recording_html("<html>old</html>", 7, tmp_path)
        path = save_recording_html("<html>new</html>", 7, tmp_path)
        assert path.read_text(encoding="utf-8") == "<html>new</html>"

    def test_unwritable_dir_returns_none(self, tmp_path):
        blocker = tmp_path / "blocked"
        blocker.write_text("not a directory")
        assert save_recording_html("<html/>", 1, blocker) is None


class TestUniqueTorrentPath:
    """The tracker's Content-Disposition name is a root folder, not an id."""

    def test_free_name_is_used_as_is(self, tmp_path):
        assert _unique_torrent_path(tmp_path, "track.torrent", b"d1:xi1ee", 1468) == (
            tmp_path / "track.torrent"
        )

    def test_identical_redownload_reuses_the_path(self, tmp_path):
        body = b"d1:xi1ee"
        (tmp_path / "track.torrent").write_bytes(body)
        assert _unique_torrent_path(tmp_path, "track.torrent", body, 1468) == (
            tmp_path / "track.torrent"
        )

    def test_different_torrent_gets_a_rec_scoped_name(self, tmp_path):
        (tmp_path / "track.torrent").write_bytes(b"d1:xi1ee")
        assert _unique_torrent_path(tmp_path, "track.torrent", b"d1:xi2ee", 1469) == (
            tmp_path / "track [tuit-1469].torrent"
        )

    def test_without_a_rec_id_the_name_is_unchanged(self, tmp_path):
        (tmp_path / "track.torrent").write_bytes(b"d1:xi1ee")
        assert _unique_torrent_path(tmp_path, "track.torrent", b"d1:xi2ee", None) == (
            tmp_path / "track.torrent"
        )


TOUR_INDEX_HTML = """
<div class="card">
  <a href="https://tangledupintorrents.org/tour/Never%20Ending%20Tour%201993">
    <b>Never Ending Tour 1993</b><span>77</span><span>shows</span></a>
  <a href="https://tangledupintorrents.org/tour/Country/Nashville">
    <b>Country/Nashville</b><span>42</span><span>shows</span></a>
  <a href="/browse">Browse</a>
</div>
"""

TOUR_PAGE_HTML = """
<h1>Country/Nashville</h1>
<section class="rl-box sh-box">
  <div class="rl-sec"><h2>1969</h2><span class="m">1 show</span></div>
  <a class="rc-tr sh-g sh-g5" data-has="1"
     href="https://tangledupintorrents.org/recordings/1584">
    <span class="m">1969-08-31</span>
    <span class="sh-nm"><b>Woodside Bay</b><span>Isle Of Wight, England</span></span>
    <span class="sh-tags"><span class="sh-own" title="In your collection"></span>
      <span class="bx-tag sbd">SBD</span><span class="bx-tag aud">AUD</span></span>
    <span class="sh-sd" title="4 seeding">4 seeding</span>
    <span class="sh-n has">2 recordings</span>
  </a>
</section>
<section class="rl-box sh-box">
  <div class="rl-sec"><h2>1974</h2><span class="m">1 show</span></div>
  <a class="rc-tr sh-g sh-g5" data-has="0" href="https://tangledupintorrents.org/shows/4273">
    <span class="m">1974-01-03</span>
    <span class="sh-nm"><b>Chicago Stadium</b><span>Chicago, Illinois</span></span>
    <span class="sh-tags"></span><span class="sh-sd"></span>
    <span class="sh-n">no recording</span>
  </a>
</section>
"""

VENUE_PAGE_HTML = """
<div class="rc-th sh-vn"><span>Venue</span><span>Country</span><span>Years</span>
  <span class="r">Shows</span></div>
<div class="rc-tr sh-vn">
  <span class="sh-nm"><a href="https://tangledupintorrents.org/venue/Beacon%20Theatre"
    ><b>Beacon Theatre</b></a><span>New York, New York</span></span>
  <span class="sh-c">United States</span>
  <span class="m">1989&ndash;2023</span><span class="m r">46</span>
</div>
<div class="rc-tr sh-vn">
  <span class="sh-nm"><a href="https://tangledupintorrents.org/venue/Spektrum"
    ><b>Spektrum</b></a><span>Oslo</span></span>
  <span class="sh-c">Norway</span>
  <span class="m">1995</span><span class="m r">13</span>
</div>
<div class="sh-pager"><span class="sh-pager-info">Page 1 of 46</span></div>
"""

class TestParseTourIndex:
    """/tour lists one link per named tour; names come from the URL."""

    def test_only_tour_links_are_returned(self):
        tours = parse_tour_index(TOUR_INDEX_HTML)
        assert [t["name"] for t in tours] == [
            "Never Ending Tour 1993", "Country/Nashville",
        ]

    def test_a_slash_in_a_tour_name_survives_the_url(self):
        assert tour_name_from_url(
            "https://tangledupintorrents.org/tour/Country/Nashville"
        ) == "Country/Nashville"


class TestParseTourPage:
    """Rows carry a full ISO date; data-has says whether a tape circulates."""

    def test_dates_are_read_from_each_row(self):
        rows = parse_tour_page(TOUR_PAGE_HTML)
        assert [r.date_str for r in rows] == ["1969-08-31", "1974-01-03"]

    def test_a_recording_link_means_circulating(self):
        row = parse_tour_page(TOUR_PAGE_HTML)[0]
        assert row.circulating is True
        assert (row.rec_id, row.show_id) == (1584, None)
        assert (row.has_sbd, row.has_aud, row.in_collection) == (True, True, True)
        assert row.seeders == 4

    def test_a_shows_link_means_no_tape_circulates(self):
        row = parse_tour_page(TOUR_PAGE_HTML)[1]
        assert row.circulating is False
        assert (row.rec_id, row.show_id) == (None, 4273)
        assert (row.has_sbd, row.has_aud, row.seeders) == (False, False, None)

    def test_tour_falls_back_to_the_page_heading(self):
        assert parse_tour_page(TOUR_PAGE_HTML)[0].tour == "Country/Nashville"

    def test_an_explicit_tour_name_wins(self):
        rows = parse_tour_page(TOUR_PAGE_HTML, tour="Tour '74")
        assert {r.tour for r in rows} == {"Tour '74"}

    def test_empty_html_is_not_an_error(self):
        assert parse_tour_page("") == []


class TestParseVenuePage:
    """The /venue register is a paginated list of .rc-tr rows."""

    def test_rows_are_parsed_with_their_year_span(self):
        rows = parse_venue_page(VENUE_PAGE_HTML)
        assert len(rows) == 2
        assert (rows[0].venue, rows[0].city, rows[0].country) == (
            "Beacon Theatre", "New York, New York", "United States",
        )
        assert (rows[0].year_first, rows[0].year_last, rows[0].n_shows) == (
            1989, 2023, 46,
        )

    def test_a_single_year_spans_itself(self):
        row = parse_venue_page(VENUE_PAGE_HTML)[1]
        assert (row.year_first, row.year_last) == (1995, 1995)

    def test_page_count_is_read_from_the_result_line(self):
        assert venue_page_count(VENUE_PAGE_HTML) == 46

    def test_page_count_defaults_to_one(self):
        assert venue_page_count("<p>no pager</p>") == 1


SONGS_INDEX_HTML = """
<p>50 a page &middot; page 1 of 17</p>
<div class="rc-tr sg-g">
  <span class="m sg-rank">1</span>
  <span class="nm"><a href="https://tangledupintorrents.org/song/All%20Along%20The%20Watchtower"
    >All Along The Watchtower</a></span>
  <span class="sg-bar"><i style="--p:1"></i><span class="m">2,285</span></span>
  <span class="m r">1974</span><span class="m r">2026</span>
</div>
<div class="rc-tr sg-g">
  <span class="m sg-rank">4</span>
  <span class="nm"><a href="https://tangledupintorrents.org/song/Tangled%20Up%20In%20Blue"
    >Tangled Up In Blue</a></span>
  <span class="sg-bar"><i style="--p:0.7"></i><span class="m">1,620</span></span>
  <span class="m r">1975</span><span class="m r">2018</span>
</div>
"""

SONG_PAGE_HTML = """
<h1>All Along The Watchtower</h1>
<details class="sg-dec" open>
  <summary><b>2020s</b><span><span class="m">111</span> shows</span></summary>
  <div class="sg-pf">
    <span class="bx-dt">2026-06-23</span>
    <span class="bx-nm">
      <a class="bx-link" href="https://tangledupintorrents.org/shows/5025">
        <b>Arizona Financial Theatre</b>
        <span class="pl"><span class="mdt">2026-06-23 &middot;</span> Phoenix, United States</span>
      </a>
      <span class="sg-pf-note">Bob on guitar and electric keyboard</span>
    </span>
    <span class="bx-src"><span class="bx-tag aud">AUD</span></span>
  </div>
  <div class="sg-pf is-bare">
    <span class="bx-dt">2026-06-18</span>
    <span class="bx-nm">
      <a class="bx-link" href="https://tangledupintorrents.org/shows/5030">
        <b>Yaamava' Theater</b>
        <span class="pl"><span class="mdt">2026-06-18 &middot;</span> Highland, United States</span>
      </a>
    </span>
    <span class="bx-src"><span class="sg-none">no recording</span></span>
  </div>
</details>
<details class="sg-dec">
  <summary><b>2010s</b></summary>
  <div class="sg-pf">
    <span class="bx-dt">2011-08-13</span>
    <span class="bx-nm">
      <a class="bx-link" href="https://tangledupintorrents.org/shows/2197">
        <b>Nikon at Jones Beach Theater</b>
        <span class="pl"><span class="mdt">2011-08-13 &middot;</span> Wantagh, United States</span>
      </a>
    </span>
    <span class="bx-src"><span class="bx-tag sbd">SBD</span>
      <span class="sg-more" title="3 recordings of this show">+2</span></span>
  </div>
</details>
"""

class TestParseSongsIndex:
    """The /songs songbook is a paginated list like /venue."""

    def test_rows_carry_counts_and_year_span(self):
        rows = parse_songs_index(SONGS_INDEX_HTML)
        assert [r.song for r in rows] == [
            "All Along The Watchtower", "Tangled Up In Blue",
        ]
        assert rows[0].n_performances == 2285
        assert (rows[0].year_first, rows[0].year_last) == (1974, 2026)

    def test_page_count_is_read_from_the_result_line(self):
        assert songs_page_count(SONGS_INDEX_HTML) == 17

    def test_page_count_defaults_to_one(self):
        assert songs_page_count("<p>nothing</p>") == 1


class TestParseSongPage:
    """A collapsed <details> still carries its rows, so one fetch is enough."""

    def test_every_decade_section_is_parsed(self):
        rows = parse_song_page(SONG_PAGE_HTML)
        assert [r.date_str for r in rows] == [
            "2026-06-23", "2026-06-18", "2011-08-13",
        ]

    def test_a_note_attaches_to_the_row_above_it(self):
        rows = parse_song_page(SONG_PAGE_HTML)
        assert rows[0].note == "Bob on guitar and electric keyboard"
        assert rows[1].note == ""

    def test_source_count_comes_from_the_more_chip(self):
        rows = parse_song_page(SONG_PAGE_HTML)
        assert [r.n_sources for r in rows] == [1, None, 3]
        assert not any(r.is_encore for r in rows)   # no longer rendered

    def test_venue_text_keeps_the_old_dash_form(self):
        assert parse_song_page(SONG_PAGE_HTML)[0].venue_text == (
            "Arizona Financial Theatre — Phoenix, United States")

    def test_show_id_comes_from_the_venue_link(self):
        assert parse_song_page(SONG_PAGE_HTML)[0].show_id == 5025

    def test_song_falls_back_to_the_page_heading(self):
        assert parse_song_page(SONG_PAGE_HTML)[0].song == "All Along The Watchtower"

    def test_empty_html_is_not_an_error(self):
        assert parse_song_page("") == []


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>TUIT — new uploads</title>
  <item>
    <title>Hall &quot;A&quot; — 1997-02-10 (AUD/FLAC)</title>
    <link>https://tangledupintorrents.org/recordings/5119</link>
    <guid isPermaLink="false">tuit-rec-5119</guid>
    <pubDate>Mon, 07 Sep 26 07:36:03 +0000</pubDate>
    <description>Tokyo, Japan · FLAC 16/44</description>
    <enclosure url="https://tangledupintorrents.org/api/v1/torrent/5119?passkey=SECRET"
      length="659150623" type="application/x-bittorrent" />
  </item>
  <item>
    <title>O2 Apollo — 2015-10-27 (AUD/FLAC)</title>
    <link>https://tangledupintorrents.org/recordings/5117</link>
    <guid isPermaLink="false">tuit-rec-5117</guid>
    <pubDate>Sun, 06 Sep 26 17:26:42 +0000</pubDate>
    <description>Manchester, England · taped by Spot · FLAC 16/44</description>
  </item>
  <item>
    <title>Feed format changed</title>
    <link>https://tangledupintorrents.org/other/1</link>
    <guid isPermaLink="false">something-else</guid>
  </item>
</channel></rss>
"""


class TestParseRss:
    """The feed is the cheapest discovery surface — it names rec_ids outright."""

    def test_rec_id_comes_from_the_guid(self):
        items = parse_rss(RSS_XML)
        assert [i.rec_id for i in items] == [5119, 5117, None]

    def test_enclosure_gives_the_torrent_url_and_size(self):
        item = parse_rss(RSS_XML)[0]
        assert item.size_bytes == 659150623
        assert item.torrent_url.endswith("torrent/5119?passkey=SECRET")

    def test_a_missing_enclosure_is_not_an_error(self):
        item = parse_rss(RSS_XML)[1]
        assert (item.torrent_url, item.size_bytes) == ("", None)
        assert item.description.startswith("Manchester, England")

    def test_an_unrecognised_guid_is_kept_not_dropped(self):
        """A silently halved queue is worse than a visible None."""
        assert len(parse_rss(RSS_XML)) == 3

    def test_empty_feed_is_not_an_error(self):
        assert parse_rss("") == []

    def test_rss_url_is_built_from_the_passkey(self):
        assert rss_url("abc123").endswith("/rss/abc123")

    def test_passkey_is_redacted_from_text(self):
        text = "GET /rss/abc123 failed"
        assert redact_passkey(text, "abc123") == "GET /rss/<passkey> failed"

    def test_redaction_with_no_passkey_is_a_no_op(self):
        assert redact_passkey("plain", "") == "plain"


class TestRssTaper:
    """The feed is the only surface a feed-discovered recording's taper is on."""

    def test_taper_is_read_from_the_description(self):
        items = parse_rss(RSS_XML)
        assert any(i.taper == "Spot" for i in items)
        assert all(i.taper == "" for i in items if "taped by" not in i.description)

    def test_as_browse_row_carries_taper_and_added_at(self):
        item = next(i for i in parse_rss(RSS_XML) if i.taper)
        row = item.as_browse_row()
        assert row.rec_id == item.rec_id
        assert row.taper == "Spot"
        assert row.date_str == ""            # everything else is left blank
        if item.pub_date:
            assert row.added_at[:4].isdigit()


_ARCHIVE = Path(__file__).resolve().parent.parent / "data" / "downloads" / "tuit" / "html"


@pytest.mark.skipif(not _ARCHIVE.is_dir(), reason="no archived TUIT pages")
class TestArchivedPages:
    """Parse real archived detail pages, not just the synthetic fixture.

    The synthetic fixture cannot catch a selector that no longer matches the
    live site — that is how the taper field silently read blank on every page.
    """

    def _sample(self, n: int = 60) -> list[Path]:
        # Pages archived before the 2026-11-25 redesign are another layout.
        files = [f for f in sorted(_ARCHIVE.glob("rec-*.html"))
                 if 'class="rc-hero' in f.read_text(encoding="utf-8", errors="replace")]
        if not files:
            pytest.skip("no archived pages in the current layout yet")
        return files[:: max(1, len(files) // n)][:n]

    def test_core_fields_are_populated(self):
        recs = [parse_recording(f.read_text(encoding="utf-8", errors="replace"))
                for f in self._sample()]
        assert recs
        for attr in ("rec_id", "date_str", "venue", "source_type", "info_hash",
                     "size_bytes", "n_files", "torrent_url", "uploader"):
            missing = [r.rec_id for r in recs if not getattr(r, attr)]
            assert len(missing) <= len(recs) // 10, f"{attr} blank on {missing}"

    def test_source_type_and_quality_come_from_the_hero(self):
        for f in self._sample(30):
            rec = parse_recording(f.read_text(encoding="utf-8", errors="replace"))
            assert rec.source_type in ("AUD", "SBD", "FM", "MTX", ""), rec.rec_id
            # The hero's pill and the info grid's label describe the same
            # recording; a sibling card's pill would not agree with the grid.
            expected = {"Audience": "AUD", "Soundboard": "SBD",
                        "Radio": "FM", "Matrix": "MTX"}.get(rec.source_label)
            if expected:
                assert rec.source_type == expected, (rec.rec_id, rec.source_label)
