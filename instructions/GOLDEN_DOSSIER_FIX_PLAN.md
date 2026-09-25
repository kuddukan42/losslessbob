# Golden-dossier correction plan (C32a–h)

Source: adversarial review of the 16 golden dossiers (2026-09-24), claude.ai doc 6479ca28-7469-440c-9256-e891039330d4. Scratch evidence: `.debug/dossier_review/`.

## Status

| Chunk | Phase | State | Commit |
|---|---|---|---|
| C32a | A — land TODO-347 instrument notes | done | 0c088313 |
| C32b | B — Olof/bobserve parser fixes | done (live reparse = tj, TODO-350) | df6c9475 |
| C32c | C — dossier field fixes | done (setlist 0-song notice + premiere tooltip moved to F) | 313137e3 |
| C32d | D — picks & source selection | done (live show_picks recompute in H) | 76540a77 |
| C32e | E — taper attribution | done (live recompute in H) | f85da368 |
| C32f | F — template, links, export | done | 4b955042, 426b1340 |
| C32g | G — tools/dossier_audit.py | done | 5c4bc4d0 |
| C32h | H — live rebuild + regenerate + verify golden set | done — awaiting tj review of the regenerated set | fe6b333c, e2d49e89, 4f9c526d |

**Resume (2026-09-25).** All chunks done. Live DB rebuilt with tj's go-ahead (backup
`data/backups/losslessbob_preC32h_20260925_0637.db`): Olof reparse + song_performances
(TODO-350), forced parse_lineage, attribute_tapers, compute_show_picks (rank-1 changed on
447/3,939 dates), `backend.qc run` (R-O1 255→21), Bob Links crawl (2,508 pages). Golden set
re-exported to ~/Documents/projects/losslessbob_dossiers (old export kept in
`.debug/dossier_review/old_export/`); `tools/dossier_audit.py` on it: 0 structural / 0 link
findings, 8 setlist diffs that are source conflicts (Uranium Rock vs Rock 'Em Dead, 1965
broadcast order, 1999 Simon medley split, bobdylan.com omissions, "The Lakes…"). Next: tj
reviews the regenerated set (C32 sign-off).

## Context

The adversarial review of the 16 golden dossiers found wrong picks, false taper credits, mis-grouped
source tables, dropped songs, mangled personnel, dead links and debug output. The full review is in the
[Golden Dossiers — Adversarial Review](https://claude.ai/code/artifact/6479ca28-7469-440c-9256-e891039330d4) doc.

Three explore passes traced each finding to code. Most have one root cause, and several are upstream:

- The Olof parser has a paren-count guard, missing section boundaries and no sentence split.
- Every `olof_pages` row predates the BUG-337 fix (77a77c63), so titles like "Tim es" are stale data.
- The ranker never reads lineage text, so a 320 kbps stream capture wasn't vetoed.
- `show_picks` is per date, not per show, so a two-show day shares one ranking.
- Taper propagation runs through a misparsed `same_as` link.

**Goal:** fix the causes, not the 16 pages. Then regenerate the golden set, and add an automated audit so these checks run again without tj.

**Constraints:**
- Work on branch `feat/dossier-redesign`. Stage only the files each phase touches; the tree has unrelated changes (scraper, TUIT, GUI screens).
- **Live Olof reparse and the `song_performances` rebuild are tj-only** (memory, TODO-350). Everything else, including `show_picks` and taper recompute, runs from a session.
- Delegate implementation to sonnet agents, one phase each. Fable reviews diffs, runs verification and does bookkeeping. Commit per phase with subject tag `[dossier C32x]` (x = a…h).

## Phase A — Land the staged TODO-347 work (instrument tally → notes)

This work is already staged: `dossier_fields.instrument_segments`/`render_instrument_segments`, the anchor swap to `stats.instrument_notes`, the template and `tests/test_dossier_fields.py`.
- Run the 7 dossier suites. Commit `feat(backend): TODO-347 …`.
- It fixes the "harp × 17 / violin × 17" tally finding.

## Phase B — Olof and bobserve parser fixes (code + tests only, no live write)

Changes in `backend/olof_parser.py`:
1. Replace `if title_text.count("(") > 1: break` (~l.1072) with a personnel test: `Name (instrument words)` using `_INSTRUMENT_RE` vocabulary. Fixes 1999-06-11 (14 → 16 songs) and 1989-06-13 (0 → 16).
2. In `_classify_special_line` (~l.579), treat `Bootlegs?` and `References?`/`Reference.` as section boundaries. Reuse `_SECTION_END_RE` (l.214). Fixes bootleg titles and Kokay references appearing in bobtalk (~224 events).
3. In `_resolve_annotations_and_releases` (~l.1127), split a position-list line's tail on `\.\s+(?=\d+[\s,–-])` into separate clauses. Fixes "17 Howie Epstein …" landing on 11/23/25.
4. Widen `_RELEASE_KEYWORD_RE` (l.222) with `included in`, `released both as`. Let `_RELEASE_ITEM_RE`/`_release_entries` accept `and parts of N, M` and skip a `( … )` aside. Fixes the Scorsese film note on 5/19 and the lost 3/12.
5. In lineup capture (~l.1218), when a `Bob Dylan (` line ends in `:`, append the following band-member lines (Tom Petty …, The Queens Of Rhythm …).

Other changes:

6. `backend/bobserve_parser.py:293`: use `_split_title_parts` (olof_parser l.795) and store `subtitle`. Fixes "And I'll Go Mine" and "Philosopher Pirate" appearing as writer credits.
7. `backend/bobtalk.py:98` `_CATALOGUE_CODE_RE`: allow `[\s-]*` in codes (QR-21/22, TSP-CD-107). Have `is_metadata_line` (l.164) reject `^Reference` and `\bRecords\b`. This is defence in depth for already-parsed rows.
8. `song_index.normalize_song_title`: drop the space before `'` and fold `alnum` collisions ("tim es" → "times"), so canonicals stop inheriting the stale titles.

- **Tests:** extend `tests/test_olof_parser_fixes.py` with one case per item, using raw HTML snippets from the named events.
- **In-memory gate:** run `tools/olof_reparse_diff.py` on a DB copy. Every changed row must fall in an explained bucket (the C05 gate: UNEXPLAINED 0).
- **Hand-off:** give tj the single live command (reparse → `song_index.run()` → `compute_song_performances`), per TODO-350. Phases C–F don't wait on it; only Phase H does.

## Phase C — Dossier field fixes (`backend/dossier_fields.py`, `dossier_anchors.py`, `dossier.py`)

1. **Personnel** (`parse_band_lineup` ~l.2185, `_base_clause` l.2136):
   - Strip `_RANGE_PREFIX_RE` before `_MEMBER_RE`, so the range prefix no longer ends up inside the first member's name.
   - Fall back to the text before `:` when the part after it is empty.
   - Capture `with <Band>` as `band.label` (e.g. "with Tom Petty & The Heartbreakers").
   - Parse plain comma lists (bobserve 2022+) as members.
   - Show the full Olof range text as the Personnel line: "1-13, 16-22 …" rather than names only.
   - The per-range clauses (Baez 8-13, Rivera 6,7,16-22) come from `_lineup_range_clauses` and render as the instrument/format line from Phase A.
   - Apply the same sentence split as B3 in `_lineup_range_clauses` (l.2233).
2. **Show-level notes off song rows:** generalise `broadcast_set_labels` (l.2584) from broadcast clauses to any recording/video/audience clause:
   - A clause covering every song goes to `context.session_notes`, deduplicated against `olof_events.notes`.
   - A contiguous range becomes a set band label.
   - Fixes "stereo PA recording; mono audience recording" ×23 and "audience video" ×7.
3. **Setlist confidence:** `setlist_confidence` (l.1848) returns `partial` when the event has an open R-O1 (`_open_finding_events`, l.769). When Olof parses 0 songs, render a notice: "Setlist not parsed from Olof — see bobserve / bobdylan.com". Don't render an empty table.
4. **Canonical titles:** in `dossier._build_setlist` (l.644-669), display `song_performances.song_canonical` by position when present. Fall back to the Olof title.
5. **Official release** (`official_release` l.1120, anchor `dossier_anchors.py:664`):
   - When every song shares one allowlisted title, set `whole_show_title` from it.
   - When `whole_show` is true, flag every song.
   - Render "Officially released: *<title>*" in the header.
   - Fixes 1975-12-04 (names the 2019 box) and 1965-06-01 (1 of 12 flagged under "full").
6. **Venue** (`dossier.py:488-493`, `dossier_anchors._build_venue_geo` l.1140):
   - Name priority: `dylan_performances`/setlist.fm before bobdylan.com (GM Place, not "General Motors Arena").
   - Try every source name for the geocode lookup.
   - Change the centroid query (`dossier.py:543`) to match the city as well as the date.
   - Key `venue_gazetteer._norm_city` on city+country, so Birmingham UK ≠ Birmingham AL.
   - Always render the Venue card (name, city, run, city history). Render the map only when coordinates and `map_focus` exist.
   - Add Brazil and any other country in the golden set to `_COUNTRY_MAP_META`.
7. **City history** (`_concert_rows` l.1302): exclude hotel, studio, rehearsal and TV-studio venues with a venue-word regex (hotel|room|studio(s)|rentals|rehears). Measure before/after on 3,867 rows; don't rely on NULL concert numbers.
8. **Premiere badge** (`dossier_claims.py:97`): change the text to "tour premiere", with the tour name in a tooltip. This removes "the 1990 The Fastbreak Tour" and the phone overflow. Update `test_dossier_claims.py:248`.

## Phase D — Picks and source selection (`concert_ranker/`, `dossier*.py`)

1. **Lossy lineage veto:**
   - Add a `txt_lossy_lineage` pattern to `concert_ranker/text_features.py`: `stream(ing)? audio`, `\d{2,3}\s*kbps`, `\bmp3\b|\baac\b|\bm4a\b`, `wolfgang'?s vault|\bW\.?V\.? stream`, `youtube`. Guard against "no mp3", "not from mp3" and "lossless".
   - Feed it `entries.source_chain` as well as the description in `cli._inject_text`.
   - Add a veto `Disqualifier("lossy_lineage", …, "lossy source stated in lineage")` in `config.py`.
   - Fixes LB-10440 (1975-12-08).
2. **Dossier excludes vetoed sources:**
   - Add an `excluded` group in `_classify_sources` (`dossier_anchors.py:447`), read from `quality_recording_scores.vetoed` plus the D1 rule.
   - `compare_sources` skips excluded LBs for the pick, the runner-up and alternates.
   - Excluded rows render in their own collapsed "Excluded (lossy)" group.
3. **Per-show picks on two-show days:**
   - New `dossier_fields.show_source_split(conn, event, entries)`.
     - (a) Parse Olof's "LB-numbers for this concert: LB-2637, …" from `olof_events.notes` (430 events).
     - (b) Else use lineage words: afternoon/early/aft/1st show versus evening/late/eve/2nd show, via `show_part_key`.
     - (c) Unassigned sources stay on both pages under an "unassigned to a show" band.
   - `build_dossier` (`dossier.py:1228`) filters entries through it.
   - `picks.py` scores per `(date, event_id)` for dates with multiple concert events. Add an `event_id` column to `show_picks`, using `PRAGMA table_info` before `ALTER TABLE`; `_load_picks` reads by event.
   - Test the split in `tests/test_dossier_two_show.py`.
4. **Score ledger** (`picks.py`):
   - (a) Make the audio term absolute: `0.25 × (scan − corpus median scan)`, clamped ±10, with the median computed once per recompute.
   - (b) Label the unrated base "no LB rating (baseline 40)", not "+40".
   - (c) Rename the curated weight: "10haaf's picks" becomes **"listed in 10haaf's catalogue"**, weight 8 → 2. The importer takes every LB he mentions, so the list isn't a set of picks. carbonbit keeps 8 only if its list is a real pick list; verify in `tools/import_curated_lists.py`.
   - (d) Template: "Composite score" becomes "Pick score", with a tooltip saying it is a relative ranking with no 100 cap.
   - (e) Vetoed sources get no audio term.
   - Recompute `show_picks` from the session (`tools/compute_show_picks.py`) after tests pass.
5. **vs. runner-up / alternates:**
   - Carry `runner_up` LB in the field value (`dossier_anchors.py:675`).
   - The template prefixes each diff "pick" or "runner-up LB-x", formats values through `format_value`, and states runner-up advantages as "LB-x is longer (253 vs 100 min)".
   - Group alternates by LB (`compare_sources` l.3183) so each LB prints once with all its axes.
   - "character:" renders as two labelled lines.
6. **Source type sanity:** at `dossier_anchors.py:1007`, when `entries.source_type` = Audience but the description has `BOOTLEG:` and matches a soundboard family member, or `db.classify_source_type` disagrees, mark the type `disputed` with a tooltip.

## Phase E — Taper attribution (`backend/db.py`, `backend/taper_attribution.py`, `dossier_fields.taper_render`)

1. `extract_lb_references` (`db.py:3010`): add a negation guard, so "none of the flaws … described in LB-x" doesn't create a `same_as` link. Fixes the 1999 spread.
2. `_propagate_strong` (`taper_attribution.py:601`): never propagate onto Soundboard, ALD, broadcast, or matrix sources. Load `entries.source_type` plus `classify_medium`.
3. Conflicts:
   - Run `_mark_conflicts` on every connected group, weak families included for display purposes.
   - In the dossier, a family with 2+ distinct confirmed tapers renders each pill as "disputed" (1995 Family A, 1987 cb/ltd).
   - Add R-T6 "family taper conflict" (warn) in `backend/qc/rules.py`, mapped in `dossier_qc.py:365`.
4. Series-code matching (`db.py:1730`): require the code to be a whole token bound to a taper phrase (taped/recorded/source/taper/by) or to start the lineage. Fixes "not as warm as nti" → net taper i on LB-10396.
5. `_EXPLICIT_TAPER_LABEL_RE` (`db.py:2086`): add `recorded by`, `recording by`, `a <x> recording`. LB-16029 sway becomes explicit/confirmed.
6. `taper_render`:
   - When there's no attribution but `entry_lineage.taper_name` has taper context, render the name as "stated" (the badpainter case).
   - Fix the pill tier check (`dossier.html:600`), which can never match.
7. Recompute attributions (`taper_attribution.recompute`, calling `db.reload_taper_aliases()` first) and rerun QC R-T rules. Record before/after counts: propagated credits on SBD/ALD (live 10 + 1) → 0.

## Phase F — Template, links and export (`backend/templates/dossier.html`, `dossier.py`, `tools/dossier_golden.py`)

1. **Theme:** an inline `<head>` script uses the stored choice, else `matchMedia('(prefers-color-scheme: light)')`. Drop the hard-coded `data-theme="dark"`. Print rule works in both themes. The toggle label reflects the current theme.
2. **Fallback values:** the runtime, disc and file cells test `field.source`/`is number`, not truthiness (l.547, 609, 610, 619). This removes "0 min" and "— disc(s)". Filesize goes through `filesizeformat`. "16/44 file" becomes "16-bit/44.1 kHz".
3. **Family grouping** (l.505-587): keep families contiguous, ordered by each family's best rank. Unaffiliated rows get an "Other sources" band. The family header shows the family's full size. The internal family id and basis move out of hidden spans into Jinja comments (the anchor-coverage test accepts template-source keys). Add a space before the confidence %.
4. **Bobtalk:** one `<p>` per quote (l.664), never a list repr.
5. **Typography:**
   - Context blocks (chronicle, notes, personnel) use `--sans` at body size. Bobtalk quotes keep serif italic at body size.
   - Length cells get `white-space:nowrap`.
   - On phone widths, badges wrap below the title.
6. **QC footer:**
   - `WithheldEntry` gains `lb`; `withhold_row` skips fields already unavailable.
   - Render one line per LB+rule: "LB-07981 · 14 fields withheld · R-E2 (tracklist doesn't fit this show)".
   - The `local_fields` path list goes into a comment.
7. **Links:**
   - Remove `_OLOF_HOME` bjorner.com (parked) and use the bobserve Olof index.
   - Footer credit: "Olof Björner's Still on the Road (via bobserve.com)".
   - "catalog: LosslessBob" → the pick's detail page (`lbb_x.url`) until the LB site root is live. The root link is dropped, not left pointing at a placeholder.
   - **Boblinks:** a new `tools/import_boblinks_index.py` crawls the tour-guide pages (`dates*.html`, `pre1995s.html`) into a small `boblinks_pages(date_iso, url)` table, using `CREATE TABLE IF NOT EXISTS`. `_build_xref` links only known pages; otherwise the card says "no Bob Links page for this date". Probing showed the URL pattern is unreliable: 031695s is 404, 050397s is 200, 060898s is 404.
8. **Run strip:**
   - Pass `link_mode` through the route → `build_dossier` → `build_view`.
   - The in-app viewer uses `?date=` links; the golden export uses `'none'`.
   - `export_html` rewrites run links to exported stems when that date is exported, else a plain span styled as "not linked", not `.cur`.
9. `lint_l1`/L2 must stay clean. New wording avoids first/last/only/best outside `claim()`.

## Phase G — Automated audit tool (replaces hand review)

`tools/dossier_audit.py` turns this session's `.debug/dossier_review` scripts into a repeatable check over an export directory.

It checks:
- Every external link: HTTP status and title, plus date match for LB, bobserve and bobdylan pages.
- Parked or placeholder detection ("Coming Soon", "almost here").
- Internal links resolve.
- Setlist diff vs bobserve (`data-clipboard-text`) and bobdylan.com.
- Structural lints: no `['` repr, no "0 min", no "— disc", no EXCLUDED source among alternates, family rows contiguous, no source under a family it isn't in.
- Pick lineage has no stream/kbps words.
- An afternoon/evening page doesn't pick the other show's tape.
- Phone-width overflow via playwright-core (the `.debug/dossier_review/shot2.mjs` pattern).

Output is a one-line-per-finding report. Offline mode caches fetches under `.debug/`. Add a `tests/test_dossier_audit.py` unit test for the structural lints on a synthetic page.

## Phase H — Regenerate and verify the golden set

1. After tj's live reparse:
   - `/backend-restart`.
   - Recompute `show_picks` and taper attributions, then `python -m backend.qc run`.
   - Re-cut the fixture: `.venv/bin/python3 tools/make_fixture_db.py --golden`, then `tools/dossier_golden.py --check`, expecting 15/15.
2. Export: `tools/dossier_golden.py --html ~/Documents/projects/losslessbob_dossiers`.
3. Run `tools/dossier_audit.py` on the export. The target is 0 structural findings. Remaining setlist diffs must be the known sources conflicts: Uranium Rock vs Rock 'Em Dead, and bobdylan.com omissions.
4. Take screenshots of all pages dark, light and phone. Check the 16 findings in the review doc one by one, and write a disposition column (fixed / upstream-accepted / deferred) into the doc.
5. Bookkeeping:
   - `/session-close`: CHANGELOG, open or close BUG entries per phase, TODO-350 note.
   - Update the plan-doc C32 row.
   - Push.
   - Then ask tj to review the regenerated set.

## Deliberately not changed

- Olof's own typos in lineup/notes text ("Richard Manual", "sudience") stay verbatim (`data-verbatim`).
- The Uranium Rock / Rock 'Em Dead conflict isn't resolved; Olof is kept.
- The Sydney 24–25 Feb "run" boundary isn't changed.
- The *Hard to Handle* film mention isn't added unless the allowlist already covers it.

## Verification (per phase)

- **Tests:** `.venv/bin/python3 -m pytest tests/test_dossier*.py tests/test_olof_parser_fixes.py tests/test_taper_attribution.py tests/test_qc*.py tests/test_setlist_confidence_file_meta.py -q`, plus the ranker tests for Phase D.
- **Tests that are expected to change** (update deliberately, not blindly):
  - `test_dossier.py:357/361/428` (links)
  - `test_dossier_qc.py:228-311` (withheld shape)
  - `test_dossier_claims.py:248`
  - `test_taper_attribution.py:118, 158-260`
  - `test_dossier_selection.py:229/325`
  - `test_dossier_two_show.py`
- **Live check:** `/backend-restart`, then GET `/api/dossier/html?date=` for 1974-01-06 (both shows), 1975-12-08, 1999-06-11 and 1995-03-16, and eyeball against the findings.
- **CI green on push.** Phase H is the end-to-end gate.
