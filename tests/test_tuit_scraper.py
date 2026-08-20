"""Parser tests for backend.tuit_scraper.

The HTML fixtures below mirror the real TUIT markup (a Laravel app) but are
hand-written, so no scraped page carrying a session token or member name is
committed to the repo.
"""
import json

import pytest

from backend.tuit_scraper import (
    BrowseRow,
    Recording,
    browse_total,
    merge_row_into_recording,
    parse_browse,
    parse_recording,
    parse_size,
    recording_id_from_url,
    recording_to_json_fields,
    torrent_root_name,
)

BROWSE_HTML = """
<div class="listing">
  <p>1,635 recordings</p>
  <article class="source-row">
    <span class="src-pill aud">AUD</span>
    <span class="row-title">
      <a class="row-title-link" href="https://tangledupintorrents.org/recordings/1837">
        <b>
          <span class="row-date num">1978-10-07</span>
          <span class="row-venue">Civic Center, Providence, Rhode Island, United States</span>
          <span class="free-tag">Free</span>
        </b>
        <span class="row-sub">LB-11637 &middot; 1st gen reel &gt; DAT - clone &gt; tlh</span>
      </a>
    </span>
    <span class="row-meta-strip">
      <span class="format-cell">FLAC 16/44</span>
      <span class="quality-cell" data-q="very-good">Very good</span>
      <span class="metric seed num ">3<span class="sr-only"> seeders</span></span>
      <span class="metric leech num is-zero ">0<span class="sr-only"> leechers</span></span>
      <span class="metric snatch num ">12<span class="sr-only"> snatched</span></span>
      <span class="taper-cell"><span class="taper-name">mjk5510</span></span>
      <span class="uploader-cell">
        <a class="uploader-link" href="https://tangledupintorrents.org/profile/tabby">tabby</a>
      </span>
      <span class="added-cell">
        <time class="added-date" datetime="2026-08-20T00:46:10+00:00">just now</time>
      </span>
    </span>
  </article>
  <article class="source-row">
    <span class="src-pill sbd">SBD</span>
    <span class="row-title">
      <a class="row-title-link" href="/recordings/900">
        <b><span class="row-date num">1966-05-17</span>
           <span class="row-venue">Free Trade Hall, Manchester</span></b>
        <span class="row-sub">unknown lineage</span>
      </a>
    </span>
    <span class="row-meta-strip">
      <span class="format-cell">SHN 16/44</span>
      <span class="metric seed num is-zero ">0<span class="sr-only"> seeders</span></span>
      <span class="taper-cell"><span class="uploader-dash">&mdash;</span></span>
    </span>
  </article>
</div>
"""

RECORDING_HTML = """
<div class="wrap" data-id="1837">
  <div class="hero-copy">
    <div class="eyebrow">7 Oct 1978 &middot; Street Legal Tour &middot; Audience</div>
    <h1>Providence, Civic Center</h1>
    <p class="subtitle">Source 1 of 2 circulating for this show. Considered the definitive tape.</p>
    <span class="src-pill aud">AUD</span>
    <span class="quality-cell" data-q="very-good">Very good</span>
    <span class="free-tag">Freeleech</span>
    <span class="badge">LB verified</span>
    <a href="https://tangledupintorrents.org/show/1837/download">Download .torrent</a>
  </div>
  <div class="spec"><span>Size</span>1,006.42 MB</div>
  <div class="spec"><span>Files</span>37</div>
  <div class="spec"><span>Sources</span>2</div>
  <div class="spec"><span>Uploaded</span>2026</div>
  <div class="swarm">
    <div class="swarm-stat seed"><b class="num">1</b><span>Seeders</span></div>
    <div class="swarm-stat leech"><b class="num">0</b><span>Leechers</span></div>
    <div class="swarm-stat snatch"><b class="num">4</b><span>Snatched</span></div>
  </div>
  <div class="info-grid">
    <div class="kv"><span>Date</span><b>1978-10-07</b></div>
    <div class="kv"><span>Venue</span><b>Civic Center</b></div>
    <div class="kv"><span>Location</span><b>Providence, Rhode Island, United States</b></div>
    <div class="kv"><span>Tour</span><b>Street Legal Tour</b></div>
    <div class="kv"><span>Source</span><b>Audience</b></div>
    <div class="kv"><span>Format</span><b>FLAC 16/44</b></div>
    <div class="kv"><span>LB number</span><b>11637</b></div>
    <div class="kv"><span>Info hash</span>
      <b title="1b00b58b849e69e4b4d9601c257dbd406276f47e">1b00b58b849e&hellip;</b></div>
  </div>
  <div class="uploader"><div><b>tabby</b><span>uploaded 1 minute ago</span></div></div>
  <div class="lineage-chain">
    <span class="lineage-node">1st gen reel</span><span class="lineage-arrow">&rsaquo;</span>
    <span class="lineage-node">DAT - clone</span><span class="lineage-arrow">&rsaquo;</span>
    <span class="lineage-node">tlh</span>
  </div>
  <details><summary class="details-summary">From the info file</summary>
    <p class="description mono-input">Bob Dylan
Civic Center
7 October 1978</p></details>
  <div class="setlist">
    <div class="set-item"><span class="track">1</span>
      <a class="song" href="/song/My+Back+Pages">My Back Pages</a></div>
    <div class="set-item"><span class="track">2</span>
      <a class="song" href="/song/Tangled+Up+In+Blue">Tangled Up In Blue</a></div>
  </div>
  <div class="file-row"><b>bd1978-10-07d1t01.flac</b><span class="right">38.70 MB</span></div>
  <div class="file-row"><b>bd1978-10-07.ffp.txt</b><span class="right">1.59 KB</span></div>
  <div class="compare">
    <div class="compare-row current">
      <span class="src-pill aud">AUD</span>
      <div class="compare-title"><b>11637 &middot; AUD</b>
        <span class="compare-def">You're viewing this &middot; definitive tape</span></div>
      <span class="compare-seed num">1 S</span>
      <span class="compare-snatch num">0 D</span>
      <span class="compare-size num">1,006.42 MB</span>
    </div>
    <a class="compare-row" href="https://tangledupintorrents.org/recordings/1838">
      <span class="src-pill aud">AUD</span>
      <div class="compare-title"><b>11638 &middot; AUD</b></div>
      <span class="compare-seed num">2 S</span>
      <span class="compare-snatch num">5 D</span>
      <span class="compare-size num">785.74 MB</span>
    </a>
  </div>
  <img src="https://tangledupintorrents.org/storage/spectrograms/1837.png">
  <audio src="https://tangledupintorrents.org/storage/samples/1837.mp3"></audio>
</div>
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
        assert browse_total(BROWSE_HTML) == 1635

    def test_full_row_fields(self):
        row = parse_browse(BROWSE_HTML)[0]
        assert row.rec_id == 1837
        assert row.source_type == "AUD"
        assert row.date_str == "1978-10-07"
        assert row.venue_location.startswith("Civic Center, Providence")
        assert row.lb_number == 11637
        assert row.lineage == "1st gen reel > DAT - clone > tlh"
        assert row.format == "FLAC 16/44"
        assert row.quality == "Very good"
        assert row.quality_slug == "very-good"
        assert row.freeleech is True
        assert (row.seeders, row.leechers, row.snatched) == (3, 0, 12)
        assert row.taper == "mjk5510"
        assert row.uploader == "tabby"
        assert row.added_at == "2026-08-20T00:46:10+00:00"
        assert row.added_label == "just now"

    def test_swarm_counts_exclude_screenreader_label(self):
        # "3<span class='sr-only'> seeders</span>" must not parse as 3 + digits
        assert parse_browse(BROWSE_HTML)[0].seeders == 3

    def test_sparse_row_degrades_to_defaults(self):
        row = parse_browse(BROWSE_HTML)[1]
        assert row.rec_id == 900
        assert row.source_type == "SBD"
        assert row.lb_number is None          # no "LB-nnn ·" prefix
        assert row.lineage == "unknown lineage"
        assert row.taper == ""                # em-dash placeholder, not a name
        assert row.freeleech is False
        assert row.quality == ""
        assert row.uploader == ""

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

    def test_info_grid(self, rec):
        assert rec.date_str == "1978-10-07"
        assert rec.venue == "Civic Center"
        assert rec.location == "Providence, Rhode Island, United States"
        assert rec.tour == "Street Legal Tour"
        assert rec.source_label == "Audience"
        assert rec.source_type == "AUD"
        assert rec.format == "FLAC 16/44"

    def test_info_hash_uses_untruncated_title_attribute(self, rec):
        assert rec.info_hash == "1b00b58b849e69e4b4d9601c257dbd406276f47e"
        assert "…" not in rec.info_hash

    def test_hero_copy(self, rec):
        assert rec.title == "Providence, Civic Center"
        assert rec.eyebrow.startswith("7 Oct 1978")
        assert rec.headline.startswith("Source 1 of 2 circulating")

    def test_specs_and_swarm(self, rec):
        assert rec.size_label == "1,006.42 MB"
        assert rec.size_bytes == 1055307857
        assert rec.n_files == 37
        assert rec.n_sources == 2
        assert (rec.seeders, rec.leechers, rec.snatched) == (1, 0, 4)

    def test_flags(self, rec):
        assert rec.freeleech is True
        assert rec.lb_verified is True

    def test_lineage(self, rec):
        assert rec.lineage_nodes == ["1st gen reel", "DAT - clone", "tlh"]
        assert rec.lineage == "1st gen reel > DAT - clone > tlh"

    def test_info_text(self, rec):
        assert rec.info_text.startswith("Bob Dylan")
        assert "7 October 1978" in rec.info_text

    def test_setlist(self, rec):
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
        assert other["seeders"] == 2
        assert other["snatched"] == 5
        assert other["size_label"] == "785.74 MB"

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
        rec = parse_recording(RECORDING_HTML, rec_id=1837)
        assert rec.taper == ""
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


class TestTorrentRootName:
    def _write(self, tmp_path, name: bytes) -> str:
        # Minimal bencoded torrent: only the info.name key matters here.
        body = b"d4:infod4:name" + str(len(name)).encode() + b":" + name + b"ee"
        path = tmp_path / "t.torrent"
        path.write_bytes(body)
        return str(path)

    def test_reads_root_folder_name(self, tmp_path):
        path = self._write(tmp_path, b"1978-11-01 Madison (LB-00707)")
        assert torrent_root_name(path) == "1978-11-01 Madison (LB-00707)"

    def test_handles_utf8_names(self, tmp_path):
        path = self._write(tmp_path, "1978 Señor (LB-1)".encode())
        assert torrent_root_name(path) == "1978 Señor (LB-1)"

    def test_missing_file_returns_none(self, tmp_path):
        assert torrent_root_name(tmp_path / "nope.torrent") is None

    def test_non_torrent_returns_none(self, tmp_path):
        path = tmp_path / "x.torrent"
        path.write_bytes(b"not a torrent")
        assert torrent_root_name(path) is None
