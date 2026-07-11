# FABLE_OLOF_FILES — Olof Björner scraper + schema (Still On The Road + Yearly Chronicles)

Status: SPEC (2026-07-10). Implements TODO-162.
Source-of-truth samples: `data/olof/samples/` (olof_index.html, still.html,
chronologies.html, DSN11050.html, DSN01225_66.html, chron_2002.html,
chron_2002_1-5.html, chron_2002_A.html).

---

## 1. Scope & non-goals

Source: `https://www.bobserve.com/olof/` (Olof Björner's "About Bob").
Two corpora, both in scope — downloaded as local HTML, parsed offline:

1. **Still On The Road session pages** — 219 `DSNnnnnn *.htm` segment files
   (one per tour/session block, **1956–2021**) linked from `still.htm`.
   The primary structured source: per-event setlists, takes, recording info.
2. **Yearly Chronicles** — per-year files linked from `chronologies.htm`
   (**1960–2025**): TOC page (`2002 0.htm`) → body parts (`2002 1-5.htm`,
   `2002 6*.htm`, `2002 7-9.htm`) + **setlist appendix** (`2002 A.htm`).
   Supplies the yearly calendar/diary, "new tapes & bootlegs" provenance
   notes, and — critically — **setlists for 2022+ where DSN coverage ends**.

**Explicit non-goals:**
- **No audio modification of any kind.** Reference metadata only. Archive
  files stay byte-identical to their database records; defects or gaps found
  by cross-referencing Olof data are *reported*, never "fixed".
- No PDF parsing — every document has an `.htm` twin; HTML is the format.
- Song/venue/artist index pages — derivable from event data, not fetched.

## 2. Corpus facts (verified against samples)

Common to both corpora:
- **Microsoft Word HTML exports** (`Generator: Microsoft Word 15` on recent
  files; older files from earlier Word versions), charset **windows-1252**
  (curly apostrophes, `\x92` etc — matches the project's cp1252 rule).
- Attributes largely **unquoted** (`<p class=Kroghead>`); lines hard-wrapped
  mid-phrase ("Community\nMemorial Arena") — text must be joined per
  paragraph before line-level regex work.
- Word paragraph classes are useful *hints* but vary by export era:
  `Kroghead` (event header), `Krog1`/`Krog2`/`Sng` (song/take rows),
  `Noteslista` (notes), `Finstilt` (small print / `[TOP]`). Parse primarily
  by anchors + regex over extracted text, classes as secondary signal.
- Chronicle bodies carry Word index-field junk (`XE "…"` markers, `PAGEREF`/
  hex TOC blobs) that must be stripped before text processing.

### 2.1 DSN event block — concert (DSN11050, 29 May 1990)

Each event starts at `<a name=DSNnnnnn>` inside a `class=Kroghead` header
table. **DSN number = Olof's stable event ID** (ascending chronologically).

```
11050 | Sporting Auditorium / University Of Montreal / Montreal, Quebec, Canada / 29 May 1990
1. Absolutely Sweet Marie
…
14. No More One More Time (Troy Seals-Dave Kirby)     ← cover credit in parens
17. Like A Rolling Stone
—                                                      ← encore separator
18. Mr. Tambourine Man
Concert # 186 of The Never-Ending Tour. … 1990 concert # 16.
Concert # 108 with the second Never-Ending Tour band: Bob Dylan (vocal & guitar), …
6-10, 18 acoustic with the band.                       ← per-song annotations
4, 6, 8, 10, 13, 15, 18 Bob Dylan harmonica.
Notes.  J First concert … (J = Wingdings bullet)
BobTalk: "Somebody told me this is Groucho Marx's birthday …"
Stereo audience recording, 100 minutes.                ← recording info line
Session info updated 6 February 2001.
[TOP]
```

### 2.2 DSN event block — studio session (DSN01225, 21 Jan 1966)

```
1225 | Studio A / Columbia Recording Studios / New York City, New York / 21 January 1966
The 3rd Blonde On Blonde session, produced by Bob Johnston.
1. She's Your Lover Now  take 1: breakdown             ← status: complete/breakdown/
…                                                        rehearsal/false start/incomplete
1-16 Bob Dylan (guitar, piano, …), Michael Bloomfield (guitar), …
Official releases
15 released on THE BOOTLEG SERIES … Columbia 468 086 2, 26 March 1991.
1-13 released on CD 10 of … THE CUTTING EDGE - COLLECTOR's EDITION …
CO-number 89210 She's Your Lover Now
References  Michael Krogsgaard: … / Clinton Heylin: …
```

Event types observed: concerts, studio sessions, rehearsals, radio/TV
broadcasts, interviews, guest appearances.

### 2.3 Yearly Chronicle (2002 sample)

Numbered-section narrative per year:
`1 Introduction · 2 At a glance · 3 Calendar (dated diary entries) ·
4 New releases and recordings — incl. 4.4 New tapes & bootlegs (one
subsection per newly circulating tape, titled "City, Country, D Month YYYY") ·
6 Tour-by-tour: musicians, dates/venues, song stats, live debuts,
ten-most-played · 7 New books · APPENDIX: THE SET-LISTS`.

Appendix (`YYYY A.htm`) format — one numbered entry per show:
```
1.  TD Waterhouse Centre, Orlando, Florida, 31 January 2002
Wait For The Light To Shine (acoustic w band) / Girl From The North Country
(acoustic w band) / … / Blowin' In The Wind (acoustic w band)
```
Slash-separated titles with parenthetical performance annotations. Less
structured than DSN blocks (no encore marker, no recording info) — used as
the setlist source **only for years without DSN coverage (2022+)**.

## 3. Architecture — download once, parse locally

Two decoupled stages; parsing is re-runnable forever without touching the
site, and manually downloaded HTML can be dropped straight into the cache:

1. **Fetcher** `backend/olof_fetcher.py` — mirrors pages verbatim (bytes,
   no re-encoding) into `data/olof/pages/`:
   - `still.htm` + 219 DSN `.htm` files (~90 MB total)
   - `chronologies.htm` + per-year TOC/body/appendix `.htm` files
   - Browser User-Agent required (Cloudflare 403s curl's default — verified);
     ≥2 s between requests, sequential, resume-safe (skip existing unless
     `--refresh`). Site updates a few times a year — fetch is manual only.
2. **Parser** `backend/olof_parser.py` — reads local files, decodes
   **windows-1252**, emits rows. Idempotent upsert; `--file` reparses one
   page. Line regexes over per-paragraph-joined text:
   - header: DSN number, venue lines, `City[, Region][, Country]`,
     `D Month YYYY` → ISO `date_str`
   - songs: `^\d+\.\s+Title( (credits))?`; `take (\d+):?\s*(status)`;
     bare `—` toggles encore
   - trailers: `^Concert # (\d+) of The Never-Ending Tour`,
     `^(\d{4}) concert # (\d+)`,
     `(Mono|Stereo|…) (audience|soundboard|…) recording, (\d+) minutes`,
     `^Session info updated (.+)`
   - `Official releases`: `<positions> released on <TITLE>, <label/cat>,
     <date>` with position range expressions (`1-13`, `1, 6, 15, 17`)
   - chronicle calendar: `^D Month` headings + following paragraphs
   - appendix: `^\d+\.` show header (venue, city, date) + slash-split titles,
     `(annotation)` suffixes captured into `annotations`

**Robustness rule:** every event stores its full block plain text in
`raw_text`; structured columns are best-effort. The parser prints a coverage
report (anchors found vs events emitted, % with ISO date, % with recording
info) so markup drift across 25 years of Word exports surfaces as stats,
not silent loss.

## 4. Schema (backend/db.py, olof_* prefix, setlistfm pattern)

```sql
-- one row per fetched page (crawl bookkeeping, both corpora)
CREATE TABLE IF NOT EXISTS olof_pages (
    filename      TEXT PRIMARY KEY,          -- 'DSN11050 - 1990 Spring Tour of North America.htm'
    url           TEXT NOT NULL DEFAULT '',
    corpus        TEXT NOT NULL DEFAULT '',  -- dsn | chronicle
    segment_title TEXT NOT NULL DEFAULT '',  -- '1990 SPRING TOUR OF NORTH AMERICA' / 'Bob Dylan 2002'
    year          INTEGER,                   -- chronicle pages only
    sha256        TEXT NOT NULL DEFAULT '',
    fetched_at    TEXT NOT NULL DEFAULT '',
    parsed_at     TEXT NOT NULL DEFAULT '',
    parse_status  TEXT NOT NULL DEFAULT '',  -- ok | partial | error:<msg>
    event_count   INTEGER NOT NULL DEFAULT 0
);

-- one row per event; joins to entries/bobdylan_shows/setlistfm_shows via date_str
CREATE TABLE IF NOT EXISTS olof_events (
    event_id        INTEGER PRIMARY KEY,     -- DSN number; appendix shows get year*1000+seq
                                             -- (e.g. 2022017 — no collision, DSN maxes ~5 digits)
    source          TEXT NOT NULL DEFAULT '',-- dsn | chronicle_appendix
    page_filename   TEXT NOT NULL REFERENCES olof_pages(filename),
    event_type      TEXT NOT NULL DEFAULT '',-- concert | session | rehearsal | broadcast | interview | other
    date_str        TEXT NOT NULL DEFAULT '',-- ISO yyyy-mm-dd ('' if unparsed)
    date_raw        TEXT NOT NULL DEFAULT '',
    venue           TEXT NOT NULL DEFAULT '',
    city            TEXT NOT NULL DEFAULT '',
    region          TEXT NOT NULL DEFAULT '',
    country         TEXT NOT NULL DEFAULT '',
    tour_name       TEXT NOT NULL DEFAULT '',-- from DSN segment title / chronicle tour section
    session_title   TEXT NOT NULL DEFAULT '',-- 'The 3rd Blonde On Blonde session, produced by …'
    concert_no_net  INTEGER,                 -- 'Concert # 186 of The Never-Ending Tour'
    concert_no_year INTEGER,                 -- '1990 concert # 16'
    lineup          TEXT NOT NULL DEFAULT '',
    recording_info  TEXT NOT NULL DEFAULT '',-- 'Stereo audience recording, 100 minutes.'
    recording_kind  TEXT NOT NULL DEFAULT '',-- audience | soundboard | studio | broadcast | ''
    recording_mins  INTEGER,
    notes           TEXT NOT NULL DEFAULT '',
    bobtalk         TEXT NOT NULL DEFAULT '',
    releases_raw    TEXT NOT NULL DEFAULT '',
    references_raw  TEXT NOT NULL DEFAULT '',
    updated_raw     TEXT NOT NULL DEFAULT '',-- 'Session info updated 6 February 2001'
    raw_text        TEXT NOT NULL DEFAULT '' -- full block plain text (search + reparse safety net)
);
CREATE INDEX IF NOT EXISTS idx_olof_events_date ON olof_events(date_str);
CREATE INDEX IF NOT EXISTS idx_olof_events_tour ON olof_events(tour_name);

-- one row per performed song / studio take
CREATE TABLE IF NOT EXISTS olof_songs (
    event_id     INTEGER NOT NULL REFERENCES olof_events(event_id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    song_title   TEXT NOT NULL DEFAULT '',
    credits      TEXT NOT NULL DEFAULT '',   -- cover writer(s) from parens
    is_encore    INTEGER NOT NULL DEFAULT 0,
    take_number  INTEGER,                    -- studio rows only
    take_status  TEXT NOT NULL DEFAULT '',   -- complete | breakdown | rehearsal | false start | incomplete
    annotations  TEXT NOT NULL DEFAULT '',   -- 'acoustic w band', 'harmonica', … 
    released_on  TEXT NOT NULL DEFAULT '',   -- release titles resolved from position ranges, '; '-joined
    PRIMARY KEY (event_id, position)
);
CREATE INDEX IF NOT EXISTS idx_olof_songs_title ON olof_songs(song_title);

-- chronicle calendar/diary entries: one row per dated item
CREATE TABLE IF NOT EXISTS olof_chronicle (
    year         INTEGER NOT NULL,
    seq          INTEGER NOT NULL,           -- order within the year's calendar
    date_str     TEXT NOT NULL DEFAULT '',   -- ISO where the entry has a resolvable date
    date_raw     TEXT NOT NULL DEFAULT '',   -- '31 January'
    entry_text   TEXT NOT NULL DEFAULT '',   -- cleaned paragraph(s), XE/PAGEREF junk stripped
    PRIMARY KEY (year, seq)
);
CREATE INDEX IF NOT EXISTS idx_olof_chronicle_date ON olof_chronicle(date_str);

-- 'New tapes & bootlegs' subsections: circulation provenance per tape
CREATE TABLE IF NOT EXISTS olof_new_tapes (
    year         INTEGER NOT NULL,           -- chronicle year = when it entered circulation
    seq          INTEGER NOT NULL,
    title        TEXT NOT NULL DEFAULT '',   -- 'Sydney, Australia, 24 February 1986'
    date_str     TEXT NOT NULL DEFAULT '',   -- ISO show date parsed from title, '' if a range/box set
    body_text    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (year, seq)
);
CREATE INDEX IF NOT EXISTS idx_olof_new_tapes_date ON olof_new_tapes(date_str);
```

Idempotency per project rules: `CREATE TABLE IF NOT EXISTS` + `PRAGMA
table_info` checks before any later `ALTER TABLE`.

## 5. How this serves LosslessBob (integration map)

The archive's unit of truth is a show-date; every Olof table joins on
`date_str`, alongside `bobdylan_shows` and `setlistfm_shows`. What each
data point buys:

1. **Setlists — attribution verification.** LB folders carry tracklists;
   matching them against `olof_songs` per date can (a) confirm or challenge
   a recording's date attribution — misdated tapes are endemic in
   circulation — and (b) detect incomplete sets (missing songs / partial
   tapes), feeding both the integrity system and tapematch's
   partial/incomplete-set judgments. Olof is *the* authoritative Dylan
   setlist source, covers eras where setlist.fm is thin, and via the
   chronicle appendix extends past DSN's 2021 cutoff.
2. **Recording info — duration and lineage sanity.** `recording_kind` +
   `recording_mins` per date gives an expected length and source type
   (audience/soundboard) to check archive entries against: a 45-minute file
   set for a "100 minutes" show is flagged as partial; a folder labeled SBD
   for a date Olof knows only as audience recording is flagged for review.
   Also a direct prior for tapematch duration comparisons.
3. **Tour names (TODO-153).** Every DSN event inherits its segment title;
   coverage is complete 1956–2021 where setlist.fm's `tour_name` is largely
   empty. Fallback chain becomes setlistfm → olof.
4. **Circulation provenance (`olof_new_tapes`).** When a tape first
   circulated and in what form — display on show pages, and a cross-check
   for taper-attribution work (FABLE_TAPER_ATTRIBUTION): a lineage claiming
   a source that per Olof only surfaced years later is suspect.
5. **Song-level rarity for ranking/insight.** `olof_songs` across all years
   yields per-song play counts, live debuts, and last-played gaps — exactly
   the "rare song" signal the unified-ranking and listening/insight specs
   want, computed locally with no extra API.
6. **Studio take detail.** Take numbers, statuses, and per-take official
   release mappings enable matching studio bootlegs/outtake sets at track
   level and labeling which takes in a folder are officially released.
7. **Context for the GUI.** NET concert #, BobTalk, notes, and the
   chronicle diary give each show page a narrative layer; `olof_chronicle`
   is also a browsable year-timeline surface on its own.
8. **Cross-source triangulation.** Where entries, setlistfm, and olof
   disagree (venue, city, date) the disagreement itself is a data-quality
   signal worth surfacing in curator mode.

## 6. Phasing (small committed bites)

- **P1 — fetcher + mirror:** `olof_fetcher.py`, `olof_pages` table; download
  219 DSN pages + chronicle pages. Verify: file counts, sha256s recorded.
- **P2 — DSN event parser:** `olof_events` (header, trailers, raw_text; no
  song rows yet). Verify: coverage report; spot-check ~5 known dates
  against the archive.
- **P3 — DSN song/take parser:** `olof_songs` incl. take status, encore,
  annotation ranges, release-range resolution. Verify: a known 1990 show
  matches setlistfm rows; DSN01225 yields 17 takes with statuses.
- **P4 — chronicles:** calendar → `olof_chronicle`, new tapes →
  `olof_new_tapes`, appendix setlists (2022+ only) → `olof_events`/
  `olof_songs` with synthetic IDs.
- **P5 — surfacing:** backend endpoints (by date, by event, year timeline),
  tour-name fallback wiring, setlist-vs-folder comparison report, gui_next
  show-page panel. i18n via `/gui-next-i18n`.

## 7. Risks

- **Export-era drift:** files span ~25 years of Word exports; class names
  and structure vary. Mitigated by anchor+regex parsing, raw_text capture,
  and the P2 coverage gate before investing in P3/P4.
- **Chronicle noise:** `XE`/`PAGEREF` field junk, inconsistent appendix
  headers (duplicated dates, missing commas observed in 2002 sample) —
  appendix parsing must tolerate malformed headers and fall back to raw.
- **Cloudflare:** plain fetches 403 (verified); browser UA works today. If
  it hardens, the local-file pipeline still works — manual download.
- **Encoding traps:** cp1252 curly quotes in titles ("She's") must be
  normalized when joining against archive/setlistfm titles (existing
  normalization helpers apply).

## 8. Deferred

- Chronicle tour-statistics sections (most-played tables, album stats) —
  derivable from `olof_songs`; parse only if a GUI need appears.
- `still uncirculated, incomplete.htm` — Olof's list of known-but-
  uncirculated/incomplete tapes; attractive for completeness auditing
  (`olof_uncirculated` table). Small page; candidate rider on P4.
- Interviews, Theme Time Radio Hour, covers, Words Fill My Head sections.
