[2026-09-03] — tapematch: false-merge census; link mechanism attribution; collection gap list;
  TODO-334 premise corrected; TODO-333/335/336 filed
Added: tools/tapematch/census_false_merge.py — TODO-336. The mirror of census_contradicted.py:
  the 114 pairs where LB commentary says different but the latest run merged them. Splits them by
  the leg the clusterer actually merged on, not by a corr cut — lb_error_candidate 14 (primary corr
  0.82–0.99, catalogue-correction candidates, none lineage-linked in entry_lineage), weak_link 41
  (fingerprint_staircase 21 / fingerprint 13 / windowed 6 / rule_d 1 — the TODO-325 floor's validation
  set), chained 59 (no direct leg fires; transitive, so TODO-319's problem and out of reach of any
  pairwise floor). The TODO filed the latter two as one 100-pair queue; they are not one queue.
  Also measures a label-quality caveat nobody had checked: lb_says_same=0 comes from a _DIFF_RE hit
  anywhere in a ±250-char window around the other side's LB number, with no check that the denial is
  about the pair — in 30 of the 114 the phrase names a THIRD LB number, so those rows are proximity
  artifacts, not curator disagreement. Each row carries denial_scope (84 pair_scoped / 30 third_party).
  Metadata only, no audio decoded. Artifacts: tools/tapematch/FALSE_MERGE_CENSUS.md (tracked) and
  data/tapematch/false_merge_queue.json (gitignored, machine-readable, for re-running after a floor).
Changed: tools/tapematch/tapematch/verdict.py: new link_mechanism() names the first OR-leg that links
  a pair (primary / windowed / hiss / fingerprint / fingerprint_staircase / triplet / rule_a-d), and
  pair_links() now delegates to it, so the boolean verdict and the named mechanism cannot drift apart.
  The four addon rules move into an ADDON_RULES tuple, replacing _addon_links(). No behaviour change —
  same evaluation order, same thresholds; the 484-test tapematch suite passes unchanged.
Added: tools/tapematch/tests/test_link_mechanism.py — 19 tests: per-leg naming, primary wins over every
  other leg, addon rules reported by name and inert when disabled, and pair_links == (mechanism is not
  None) on every fixture.
Added: tools/tapematch/build_gap_list.py — TODO-334. Resolves the n_sources_db vs n_sources_found
  shortfall in observations.db per LB number instead of per count, into four buckets: present /
  private / unranked / absent. Over the 3,061 run dates (14,215 catalogued recordings): present
  12,017, private 2,069, unranked 110, absent 19. The 1,414-recording shortfall was read as an
  acquisition gap when TODO-334 was filed; it is not. Only 19 recordings are genuinely off disk
  (18 of them with no my_collection row at all). The 2,069 "private" ones are on disk WITH audio
  and are dropped by find_lb_folders' PRIVATE/NOTORRENT path rule, because a private entry has no
  local LB page and so no commentary to corroborate a merge against — meaning ~15% of the corpus
  on run dates has never been matched, concentrated in the 1990s (1,157) and 1980s (316), with 87
  dates holding at least as many private recordings as ingested ones. Metadata only, no audio
  decoded, no directory walked except to test existence. Refuses to write when a DYLAN drive is
  unmounted: every "absent" verdict is a filesystem existence test, so an unmounted drive would
  invent thousands of false acquisition targets.
Added: tools/tapematch/GAP_LIST.md (tracked summary) + data/tapematch/gap_list.json (gitignored,
  per-date bucket lists). Regenerate with .venv/bin/python3 tools/tapematch/build_gap_list.py.
Changed: TODO.md — TODO-334 rewritten around the corrected premise; what remains of it is the
  policy question (should tapematch ingest private sources and mark the families
  commentary-uncorroborated?), which should be gated behind the TODO-325 corroboration floor rather
  than shipped first. Also filed TODO-333 (latest-run configs hash to 10+ distinct calibrations,
  largest covering 876 of 3,062 dates; verdict provenance unrecorded), TODO-335 (7,198 of 9,131
  source tapes are single-copy, a lower bound since over-merge can only shrink it; redundancy by
  era 1.86 in 1974, 1.6–1.8 in 1995–97, 1.05–1.17 from 2017), and TODO-336 (114 pairs where LB says
  different and the run merged them — the polarity CONTRADICTED_CENSUS.md never covered; 14
  decisive at corr ≥ 0.75, 100 below threshold and better held as a TODO-325 validation set).

[2026-09-02] — tapematch: one merge predicate for display + clustering; superseded-run fix; TODO-325 sweep
Fixed: tools/tapematch/tapematch/cli.py — BUG-329. The SECONDARY MATCH section hand-rolled its own
  will_merge expression (windowed OR hiss-frac+median OR fp cluster bar) to print "→ SECONDARY LINK"
  vs "→ hiss evidence (below merge threshold)", while the real merge was decided later by
  verdict.pair_links; the copy ignored the staircase/curator fp relaxations, the lo-fi hiss median,
  the triplet fingerprint and addon_links, so a pair could print "below merge threshold" and still be
  merged (repro: 20260710_030008_1997-12-05). New _merge_tag() derives the tag from verdict.pair_links
  itself. The report block had to move below _pair_metrics (which needs the emb/ASR passes), so
  SECONDARY MATCH now prints after BANTER/ASR; the "=== CLUSTERS ===" header moved down with it so
  section order still reads SECONDARY MATCH → CLUSTERS. Negative tag reworded "→ below merge
  threshold" — the old text claimed hiss evidence for windowed- and fingerprint-only pairs.
Added: tools/tapematch/tests/test_merge_tag.py — pins _merge_tag ≡ pair_links, incl. the BUG-329 case.
Fixed: tools/tapematch/next_batch.py — TODO-326. ranked(newest_per_date=True) built by_date from
  eligible_dirs(), which already drops analysed runs, so members[-1:] picked the newest *pending* run
  and happily handed back a superseded older run once a date's newest was analysed — two contradictory
  analysis.md files per date. New _iter_run_dirs()/_has_analysis()/newest_run_dir_by_date()/
  superseded_eligible_dirs(): the newest run is now computed over ALL run dirs, and the date is dropped
  when that run is already analysed. --stats excludes superseded dirs and reports their count.
Added: tools/tapematch/tests/test_next_batch.py — 5 cases over the newest/superseded matrix.
Changed: data/tapematch/runs/{20260715_055200_2008-09-01,20260715_122016_2009-08-04,
  20260715_133621_2009-11-05}/analysis.md — SUPERSEDED banner on the older of each contradictory pair
  (the 2026-07-18 re-runs supersede them; the app DB already reflects the newer clustering). No
  deletions. Untracked — data/ is gitignored.
Added: tools/tapematch/tapematch/verdict.py — TODO-325 / BUG-331. Two dark config keys, both absent
  from the shipped config so behaviour is byte-identical: match.secondary_primary_floor
  (_secondary_corroborated — windowed/hiss/fp/triplet links must also show corr >= floor) and
  match.fingerprint_primary_floor (_fingerprint_corroborated — the same floor scoped to the
  fingerprint/triplet legs only). addon_links is deliberately ungated (folding Rule D in costs
  150-230 tp).
Added: tools/tapematch/tests/{test_secondary_primary_floor.py,test_fingerprint_primary_floor.py}.
Changed: tools/tapematch/CALIBRATION_PROGRESS.md + config.yaml — the sweep behind both keys.
  BUG-331 root cause: the two reported merges came from the staircase-relaxed fp bar (fp 0.417/0.420
  vs cluster_threshold_staircase 0.40), not from a staircase "link" — 2006-10-27 no longer merges
  under today's config (the 2026-07-17 staircase_corroboration gate fixed it incidentally), but
  2008-07-08 LB-06272/06304 still does, corroborated only by noise-floor hiss (frac 0.134, median
  0.079 against 0.05 floors) at corr 0.030, and it is live in the DB with no newer run. A UNIFORM
  primary floor cannot fix it: 1980-12-04 is a real taper-corroborated merge on a windowed leg at
  corr 0.0215, LOWER than the false merge's 0.0295. Scoping the floor to the fingerprint legs
  separates them by mechanism. Recommended fingerprint_primary_floor 0.10 (fixes BUG-331 and all
  three 1990-06-01 pairs, 0 new frozen-set fp, -91 tp / -11 fp; preserves 1980-12-04, 1993-10-03 and
  1995-09-27's core pair) with 0.05 as the cheaper buy (-50 tp / -7 fp, same two fixes). NOT enabled
  — thresholds need tj sign-off. 465 tapematch tests pass.

[2026-09-02] — tapematch: 26-run tail batch analysed, backlog drained; forum subject flag fallback
Added: backend/country_flags.py — flag_for_location(), the fallback for concert dates Olof's corpus
  does not cover (the 1975 Rolling Thunder gap left US shows unflagged). Splits a free-text
  entries.location on commas/semicolons/brackets and looks each part up in the existing name table.
  Returns a flag only when exactly one country is named — "Mexico, Missouri" names two, so none —
  and deliberately does not recognise two-letter abbreviations ("DE" is Delaware or Germany). Five
  free-text-only spellings added to _NAME_TO_CODE (usa, u.s.a., u.s., uk, u.k.).
Changed: backend/forum_poster.py — _build_subject() falls back to flag_for_location(entry.location)
  when flag_for_date() finds nothing. BOOTLEG titles still get no flag. (Carried over uncommitted
  from the previous session; recorded here.)
Changed: tests/test_country_flags.py — coverage for the fallback, incl. the ambiguous-parts and
  abbreviation cases. 18 pass.
Changed: TODO.md — TODO-319 (tapematch chain-clustering over-merges) corroborated with the
  2026-09-02 batch rather than opening a duplicate. 14 of 26 dirs came back needs-review, 56%
  against a 32% all-time base rate (996/3100), and the excess is almost entirely that mechanism.
  Worst case 2010-03-28 Tokyo: 8 recordings in one family at mean intra-corr 0.058, 3 pairs with
  secondary hiss evidence and 28 chain-unverified, against distinct rigs and noise floors spanning
  -72 to -89 dB. Noted the skew — the tail batch is all 6-11-entry dates, so a fix wants validating
  against high-entry-count dates specifically.
Note: /tapematch-batch 30 wrote the last 26 eligible analysis.md files (5 sonnet subagents on
  date-group-safe partitions; the 1991-02-10, 2004-10-14 and 2002-10-11 same-date pairs each went
  to one agent). 12 looks-correct / 14 needs-review. backend.tapematch_sync then ran: 3,062 dates,
  9,132 families, 12,035 recordings linked, 24,226 pairs, 0 errors. next_batch.py --stats is now
  0 eligible dirs — the complete-set queue is drained. The ~995 run dirs still lacking analysis.md
  fail the complete-set rule and requeue only when their secondary sources land. Run outputs live
  under data/, which is gitignored, so none of the 26 files appear in this commit.
Note: 2002-10-11 has two analyses reaching different family counts (older run 5, newer 8) because
  the two tapematch runs clustered differently; both were still pending so both were written. The
  analyses agree on the real structure and name the newer one correct. This is the situation
  TODO-326 already describes — no new ticket opened.

[2026-09-01] — chore: cleanup pass — obsolete material moved to archive/, nothing deleted
Added: archive/ — a single holding area for material that is no longer part of the working
  tree. Nothing was deleted; every item can be moved straight back. archive/README.md is the
  manifest and records what was deliberately left alone. Contents: venvs/venv-broken-py313
  (642 MB dead 3.13 virtualenv superseded by .venv), build-artifacts/gui_next-dist-1.2.0-2026-05-29
  (electron-builder output incl. a 124 MB AppImage, built at v1.2.0 against a tree now at 1.4.0),
  scratch/taper-tier-2026-07-17 (the former .scratch/ — one-off taper tier recompute scripts and a
  standalone taper_review.html draft, superseded by backend/taper_review.html and /taper-curation),
  debug/ (318 .debug/ artifacts dated before 2026-08-01), attic/ (the pre-existing top-level attic/
  moved verbatim, so there is one archive rather than two) and tools-throwaway/ (_qbt_sysctl.conf,
  _qbt_tune.sh, _route_audit.py, _route_dryrun.py — the tools/_<name> throwaway convention; the
  route pair shipped its work in 62cbb8f2/TODO-317).
Changed: .gitignore — archive/venvs, archive/build-artifacts, archive/debug and archive/scratch are
  ignored (bulky and machine-local); archive/attic and archive/tools-throwaway stay tracked.
Changed: pyproject.toml — ruff excludes archive/, alongside the existing tools/ exclusion. The
  archived scripts are kept verbatim; the pre-commit hook would otherwise auto-fix retired code.
Changed: PROJECT.md file-structure tree — the attic/ line becomes the archive/ subtree.
Changed: .claude/hooks/path_guard.py — its refusal messages and docstring pointed temp files at
  .scratch/, which no longer exists and contradicted CLAUDE.md; they now say .debug/. Message text
  only, no change to what the hook blocks.
Removed: data/webengine_cache/ (1.2 MB) and the WEBENGINE_DIR constant in backend/paths.py, on tj's
  call. The directory was a Qt WebEngine profile cache written by the PyQt6 attachments tab, which
  was removed with the legacy GUI on 2026-07-16; grep found no reader of the constant anywhere in
  the tree, only its definition. Deleted, not archived. 1594 tests still pass.
Note: .debug/ itself and its electron/ and screenshots/ subdirs stay in place — /verify writes to
  those exact paths. Nothing under data/ was touched; archive/README.md lists the stale-looking
  candidates there (webengine_cache/ orphaned by the PyQt6 removal, the lossless_bob.db /
  losslessbob.db pair) for tj to judge. Verified: 1594 backend tests pass, check_project_refs.py
  exits clean.

[2026-09-01] — fix: four integrity defects — wrong-concert prose in analysis bundles, one LB folder spliced end to end, re-serialised mirror attachments, and a forum gate that disagreed with its own banner
Fixed: tools/tapematch/prep_analysis_input.py:
  BUG-328. Every `LB-<n>` in report.md was globbed straight into `LBF-<padded>-*.txt` with no check that
  the id belonged to the run's date, so a typo in uploader prose pulled a different concert's info file
  in alongside the run's own sources — `"Source: LB-0897"` on 1999-06-20 attached LB-00897 (1981-06-30
  London), and `"LB-1711"` on 1999-07-24 attached LB-01711 (1999-06-26 Las Vegas). The analysis writer
  was then handed prose from the wrong show and asked to reconcile it, which is exactly the input that
  manufactures false "needs review" flags. The bundle now derives the run's date (dir-name suffix, report
  title as fallback) and the coverage table's LB numbers, and checks every other reference against
  `entries.date_str`. Off-date and unknown-date references are still attached — a genuine cross-reference
  is evidence — but under a "Cross-references from commentary — NOT sources for this run" heading tagged
  `[DIFFERENT DATE: ...]` / `[DATE UNKNOWN]`. A missing or unreadable DB degrades to treating every
  prose-only reference as unverified rather than trusting it.
Fixed: tools/tapematch/tapematch/ingest.py:
  BUG-327. `list_tracks` rglob'd the whole source tree and concatenated it. Its two de-dup passes only
  remove copies that are the *same* audio — `_dedupe_formats` (one file per `(parent, stem)`) and
  `_dedupe_subtrees` (byte-identical subtrees) — so LB-07173's top-level `d1`/`d2` plus its nested
  "(REMASTERED)_fixed" `d1`/`d2`, which differ in bytes, were both walked into one 3:27:33 stream against
  a 1:32:48 date median, flagged `[INFLATED]`, and put the whole date's correlations and clustering in
  question. New `_select_version` runs after the de-dup passes: a nested directory is a second pass when
  its track keys (directory path + stem, relative to that directory) overlap the keys outside it by ≥80%
  over ≥3 tracks. The outer pass is kept — the nested copy is a re-master or fix in every observed case,
  and picking by track count would be fooled by patch dirs like `d1/fix/Track08.fix.flac` that repeat a
  track rather than add one — and the dropped pass is named in a warning that reaches report.md so it can
  be analysed by pointing a run at that subfolder. LB-07173 now ingests 11 tracks, down from 25.
Fixed: backend/site_crawler.py, tools/refetch_html_attachments.py:
  TODO-329 (carried over from the previous session, unrecorded until now). `is_rewritten_html` decided by
  extension alone, so an uploader's DigiFlawFinder report or md5 listing that happens to end in `.html`
  went through BeautifulSoup on the way to `data/site/files/` — bare attributes gained quotes, tags were
  lowercased and closed, and the mirrored copy came out 5-8% larger (smaller on malformed input, where the
  parser dropped what it could not read). Its bytes could then never match the recorded `body_sha256`, so
  `seed_overlay` could not source the sidecar and left it to the swarm. Anything under `/files/` is now
  treated as an attachment and mirrored verbatim whatever its extension; only browsable pages, whose
  server-absolute links must be made relative for `file://`, are still rewritten.
  `tools/refetch_html_attachments.py` repairs already-mirrored copies through `site_crawler._save` itself
  so the two cannot drift, skipping any row that already hashes correct. Repair pass is complete: 14,147
  attachments mirrored, 0 needing a re-fetch.
Fixed: backend/app.py:
  BUG-334 (carried over from the previous session, unrecorded until now). The forum post gate ran
  `checksum_utils.verify_folder`, a sweep of whatever loose sidecars sit in the folder. LB-03696 carries an
  uppercase `.ffp` and a lowercase `.md5` for the same 32 tracks; the sweep counted each convention as its
  own expected fileset and blocked the post as "incomplete" with half the files missing, while the LBDIR
  manifest — the very verdict the forum preview banner shows the user — verified clean. The gate now reads
  `_lbdir_status_for_lb`'s `split.audio`: a mismatch (swapped or re-encoded audio, BUG-120) blocks
  unconditionally, missing audio blocks but remains overridable, and non-audio entries never gate. Banner
  and gate now agree on the same folder.
Added: tools/tapematch/tests/test_prep_analysis_input.py, tools/tapematch/tests/test_version_selection.py:
  23 tests covering date matching, coverage-table extraction, the cross-reference split, the no-DB
  fallback, LB-07173's exact layout, and the layouts that must NOT be treated as two passes (multi-disc
  shows with repeated filenames, nested bonus material, flat folders).

[2026-08-31] — fix: forum topic links now actually reach the clipboard, and the toast waits
Fixed: gui_next/src/main/index.ts, gui_next/src/preload/index.ts, gui_next/src/renderer/src/lib/clipboard.ts:
  BUG-333. The renderer copied forum topic URLs with `navigator.clipboard.writeText`, which in a packaged
  build (a file:// document) rejects with "Document is not focused" whenever the write fires while the
  context menu or forum modal that triggered the post is closing — i.e. every real path into "post to
  WTRF". The rejection was swallowed. Copying now goes through a `clipboard:write` IPC handler backed by
  Electron's main-process clipboard module, which has no focus precondition, exposed as
  `window.api.writeClipboard` and wrapped by `copyText()`; the web API stays as a browser-only fallback.
  Every `navigator.clipboard.writeText` call site in the renderer was moved onto the helper.
Changed: gui_next/src/renderer/src/components/primitives.tsx: `Toast` gained `detail` and `sticky`. A
  toast carrying `detail` renders it verbatim in a selectable monospace block with Copy and Dismiss
  buttons and never auto-dismisses — a link the curator watched disappear after 3.5s is a link they have
  to go find on the board again.
Changed: gui_next/src/renderer/src/lib/useLibraryActions.tsx,
  gui_next/src/renderer/src/screens/ScreenCollection.tsx: both forum-post paths (single and batch) now
  park the topic URLs in a sticky toast and say whether the copy landed. ScreenCollection's batch had
  discarded `topic_url` outright and its single-post toast rendered the literal key
  `collection.toast.postedWithUrl`, which does not exist in en.json; its duplicate local `Toast` was
  deleted in favour of the shared primitive.
Added: locale keys `library.toast.postedForumNotCopied`, `library.toast.linksNotCopiedSuffix`,
  `collection.toast.postedCopied`, `collection.toast.postedNotCopied` — de/fr/es/it/nl filled via
  /gui-next-i18n (5,863 DeepL chars).

[2026-08-31] — chore: reseed 584 TUIT recordings stalled on the partial-overlay gate
Changed: qBittorrent runtime setting (not in the repo): `max_concurrent_http_announces` lowered 20 -> 5
  after a 200-torrent sample showed 33% of tuit announces at status 4 'timed out'. Adding 584 torrents in
  an hour, atop the 1,833 already tagged, flooded a ~21-member tracker's announce endpoint; torrents that
  fail to announce are dropped from its peer list, so the site's seeding count falls while the local
  client still believes it is seeding. Logged as TODO-330.
Fixed: no code change — 584 recordings that had refused to seed were re-run with `allow_partial_overlay`
  and accepted. Every one had already hardlinked 100% of its audio and was refused only over a few KB of
  uploader sidecars. A tally over all 592 stalled overlays found NOT ONE unresolved audio file: 525 .txt,
  272 .md5, 249 .html, 59 .jpg, 30 .ffp. Causes, per torrent: 512 'no local source' (the uploader's own
  checksum/info files, which only the swarm has), 203 a size mismatch against the site mirror, 85 a
  wrong-size local variant. The remainder now downloads into the overlay, never the collection.
  TUIT seeded total 1,833 -> 2,417. One holdout, rec 2750 / LB-2725 (Montpellier 1995-07-27), refused for
  an unrelated reason: its linked folder no longer shares enough files with the torrent.
Added: TODO-329 — the site mirror re-serialises every .html attachment through BeautifulSoup, inflating
  the LBF DigiFlawFinder files 5-8% so their bytes can never match an uploader's copy. Root-caused this
  session to site_crawler._save + html_utils.rewrite_links; backend/scraper.py:440 already saves
  attachments verbatim, so the two fetch paths disagree. Deferred by request until the reseed finished.

[2026-08-30] — feat: seed to WTRF from a list of forum links, with its own overlay
Added: backend/tracker_seed.py: the tracker-agnostic half of the TUIT seeding pipeline, lifted out of
  tools/tuit_sync.py and parameterised by a `SeedOptions` dataclass. Same three gates as before —
  `is_seedable_to_tracker` (lb_status must be 'public'), the torrent root must name a linked collection
  folder, and `torrent_verify` must hash that folder to 100% locally — with the overlay as gate 3's
  fallback. The tracker name now drives the overlay root and the qBittorrent tag, so WTRF assembles at
  `<mount>/WTRF Seeds` and TUIT keeps `<mount>/TUIT Seeds`; the two never share a directory, because the
  same show's torrents differ in their LBF sidecars.
Added: backend/wtrf_seed.py: walks a pasted list of WTRF topic links to the recordings they seed —
  first post → LB number + `.torrent` attachment → download → tracker_seed. The LB number is read from
  the post, in priority order attachment filename ("LB-00008.torrent", definitive) → topic title → body;
  a field naming several distinct LB numbers is reported ambiguous and refused rather than guessed at,
  since seeding the wrong recording under someone else's post cannot be taken back. A line may pin the
  entry explicitly by writing "LB-00123" before the URL. Link canonicalisation collapses scheme, `www.`,
  `#msg` anchors and `.msgNNNN`/page offsets, so one topic is walked once whatever form it was copied in.
Added: backend/app.py: `POST /api/wtrf/seed_links` streams the batch as SSE (start / link / done),
  single-instance guarded like the crawl; `POST /api/entry/<lb>/seed_wtrf` seeds one entry, using a
  supplied `topic_url` when the curator has the link and falling back to the board search otherwise.
  Both refuse a non-public entry before spending a forum round-trip. The overlay defaults ON here,
  unlike the TUIT CLI: a WTRF torrent carries the LBF sidecars the curated folder does not keep, so
  seeding in place all but always falls a fraction short.
Added: gui_next ScreenScraper: a "WTRF Seeding" tab — paste box, seeding options, Seed/Dry-run buttons,
  live SSE log, and a recent-attempts table. Its strip card counts only rows with a `seed_folder`, since
  the LB-first crawl also marks rows 'qbt_added' when it adds a torrent to *download*.
Added: gui_next library actions: a per-recording "Seed to WTRF" action in the share group, on both the
  context menu and the detail panel.
Changed: backend/db.py: `wtrf_downloads` gains `seed_folder` (idempotent PRAGMA-guarded ALTER) and a
  'not_seeded' status, mirroring `tuit_downloads`; `add_wtrf_download` takes the new column.
Changed: tools/tuit_sync.py: delegates to backend/tracker_seed.py — 261 lines lighter, behaviour and
  the `TUIT Seeds` overlay root unchanged.
Fixed: backend/seed_overlay.py: the source index was flat and basename-keyed, which broke on every
  nested torrent. Real WTRF posts are box sets — `<root>/artwork/`, `<root>/<show>/cd-1|cd-2/…` — so
  none of the audio was ever seen (it lives below the top level the index scanned), and the basenames
  that were seen collide: "84 Revisited" repeats `01 Track01.flac` four times across its discs. The
  index now walks recursively and registers each file under every suffix of its relative path, and
  `_resolve_source` matches longest-suffix-first with an exact size check, so `cd-1/01 Track01.flac`
  is distinguished from `cd-2/01 Track01.flac` instead of being a coin toss. `plan_overlay` gained
  `link_dirs` — further collection folders to hardlink from — because a torrent can span several LB
  entries, each filed in its own folder. New `resolvable_files()` scores a folder by that same rule.
Fixed: backend/seed_overlay.py: `snapshot_folder` was also flat, so the collection-untouched guard
  could not see a write into a nested `cd-1/`. It now walks the tree and keys on the relative path.
Fixed: backend/tracker_seed.py: `best_source_folder` scored folders by top-level audio basenames and
  so scored every nested collection folder at zero. It now uses `resolvable_files()`.
Changed: backend/wtrf_seed.py: several LB numbers in a post is no longer refused outright. Prose
  cannot distinguish a cross-reference (a body opening `LB-11872` that mentions `LB-11880` as the
  batch the artwork ships in) from a genuinely two-entry torrent (`…LB-14777+ LB-14778.torrent`), so
  the post only nominates and the torrent's contents decide: new `pick_by_content()` scores each
  candidate's folder by the files the torrent actually wants, drops the ones supplying nothing, and
  hands the rest to the overlay as `link_dirs`. Only when content cannot separate them is the link
  refused. Non-public candidates are excluded before scoring, so one can never win.
Added: tests/test_wtrf_seed.py, tests/test_seed_overlay.py: 35 + 39 tests, covering link parsing and
  canonicalisation, LB-resolution priority, the content pick (multi-entry kept, cross-reference
  dropped, non-public excluded, wrong-size same-name rejected), nested/colliding-basename sourcing,
  sibling-folder supply, and the recursive untouched guard.

Fixed: backend/wtrf_seed.py: a scheme-less paste was silently dropped as "no WTRF topic links found".
  `_URL_RE` required an `http(s)://` prefix, but the browser's address bar displays the URL without
  one, so that is what a copy usually yields — `www.watchingtheriverflow.org/index.php?topic=…`. The
  pattern now also matches a bare forum host and a forum-relative `index.php?…`, and new
  `_absolutise()` prepends the scheme; `_resolve_url` could not be used for this, since it reads a
  bare host as a relative path and would glue it onto FORUM_BASE. Trailing prose punctuation is
  trimmed, so a link pasted mid-sentence still resolves.

Added: backend/wtrf_seed.py: a paste often contains no links at all. Copying a forum round-up post as
  plain text collapses every hyperlink to its bare `www.watchingtheriverflow.org` display text — the
  href does not survive — so the LB numbers beside them are the only thing left, and they are enough.
  New `SeedTarget` is either a topic link or a bare LB number; `parse_seed_targets()` reads both from
  one paste (a bare host line contributes nothing but no longer suppresses the LB numbers around it),
  and an LB-only target is resolved by searching the board via `wtrf_scraper.find_torrent_for_lb`,
  inheriting its refusal to download below 'medium' confidence. `seed_from_links` gained the two
  `_prepare_from_link` / `_prepare_from_lb` branches that converge on the shared seeding gates.
Added: backend/wtrf_seed.py: `expand_lb_shorthand()` reads "LB-11486/88" as the two entries it
  abbreviates — 11486 and 11488, *not* the range through 11487, which is a different show two years
  later. Because a mis-expansion would seed the wrong recording, each expansion is kept only when the
  entry exists and carries the same date as the base; anything else is dropped and logged.
Changed: gui_next ScreenScraper: the WTRF tab counts seed *targets* rather than lines mentioning the
  forum host — the old count was exactly wrong for a round-up paste, where every such line is a
  hyperlink's leftover display text and none of them is a target.

Verified live against WTRF: topic 43459 assembled the two-entry "84 Revisited" box set to 100% from
  two collection folders (72 files, all hardlinked, nlink=2, no extra disk) and qBittorrent reports it
  seeding at 100%; topic 53461 correctly dropped the cross-referenced LB-11880 and seeded LB-11872
  (25/25 files). Topics 53463/53465/53467, pasted in all three scheme-less/relative shapes, seeded
  3/3 at 25/25 files each. All seven collection folders independently confirmed unmodified afterwards;
  every one of the 172 overlay files has a link count of 2, so no bytes were duplicated. A real
  round-up paste containing zero URLs yielded 8 targets (including the LB-11486/88 expansion), and
  LB-12653/12654 seeded 2/2 through the board search at 'definitive' confidence.

[2026-08-30] — feat(gui): LBDIR pipeline status in the forum post preview; Bob-O-Matic footer loses its version
Added: backend/app.py: `GET /api/entry/<lb>/lbdir_status` returns the LBDIR pipeline verdict for an
  LB's filed collection folder — the same `verify_folder_lbdir` check the pipeline's LBDIR step runs,
  resolved against the folder's own manifest first (strict), then the LB's site attachment for its
  xref fileset. Reuses the pipeline's cached per-folder verdict (`pipeline_folder_state`) whenever the
  stat fingerprint still matches, so a folder the pipeline already checked answers in ~10 ms instead
  of ~70 s of re-hashing; a live check is written back into the same cache. `?force=1` re-verifies.
  Status is `unknown` (reason `no_disk_path` / `folder_missing`) when there is nothing to check —
  never silently "ok".
Changed: backend/app.py: the LBDIR step's status/label mapping moved out of the pipeline row builder
  into module-level `_lbdir_verdict()`, so the pipeline row and the new endpoint cannot drift apart.
Changed: gui_next ScreenCollection ForumModal: a tone-coloured status strip above the Subject field
  shows the LBDIR verdict, the pass/missing/mismatch/extra counts, whether the answer came from cache,
  and a Re-check button (force). Fetched asynchronously on open so the modal never blocks on hashing.
Changed: gui_next locales: `collection.forum.lbdir.*` added to en.json and translated to de/fr/es/it/nl.
Changed: backend/forum_poster.py: the post footer is now "Brought to you by <name>, via the
  Bob-O-Matic." — the app version is gone, and the now-unused `backend.version` import with it.
Changed: backend/app.py: `lbdir_status` is now audio-first. `_lbdir_split_counts()` separates the
  manifest's audio entries from its text entries (unlisted disk files counted apart, excluded from
  either total), and `_lbdir_forum_view()` derives the shown verdict from the audio bucket alone —
  a folder whose music is intact reads green, and the text population gets its own descriptive line
  instead of dragging the colour down. The strict `_lbdir_verdict()` shape the pipeline consumes is
  unchanged and still cached alongside.
Added: backend/app.py: `_lbdir_reconcile_text()` — before judging a folder, missing *non-audio*
  manifest entries are recovered automatically: in-folder copies at the wrong path are moved to the
  path the manifest expects, and entries the site mirror still holds are copied in. Exact-MD5 matches
  only (a name-only match is a different revision of the document and stays a human decision), audio
  is never moved or copied, and nothing is ever deleted. LB-03442's two "missing" files were both
  text and both recoverable — it now reads green with 54/54 audio pass.
Changed: gui_next ScreenCollection ForumModal: the strip's colour follows the audio verdict, with a
  second line describing the text files, files auto-restored this check, and unlisted extras.
Added: backend/country_flags.py: country flag emoji for a show's location, and forum subject lines
  now carry one as a prefix — the board's own convention (verified against 400 topics on WTRF board
  16: 🇺🇸 22x, 🇩🇪 6x, 🇸🇪 3x, the Scotland subdivision flag 3x; SMF 2.0 is UTF-8 and passes four-byte
  emoji in topic titles unchanged). `flag_for_date()` resolves through `olof_events` by parsed date,
  its `country` first and then its `region` — which for a US show is the only column carrying the
  location, and which the page parser also filled with whole countries ("The Netherlands"), Canadian
  provinces and typos ("Irelandw"). Both columns map by name through one table that is exhaustive
  over the values actually in the corpus. Resolves 15,409 of 16,611 collection rows (92.8%); the
  1,202 misses are almost all dates with no Olof event at all (studio, rehearsal, compilation).
  Anything ambiguous returns no flag rather than a guess — Yugoslavia, the USSR and Czechoslovakia
  are deliberately unmapped, while East/West Germany resolve to 🇩🇪. England/Scotland/Wales get their
  subdivision flags, matching the board; Northern Ireland has none and falls back to 🇬🇧.
Changed: backend/forum_poster.py: `_build_subject()` prefixes that flag. BOOTLEG subjects never get
  one — a compilation has no single country. An unresolved location leaves the subject untouched.

[2026-08-30] — feat(backend): TODO-327 taper curation workbench; TUIT detail-page HTML archived
Added: backend/taper_curation.py: read model joining every source that has an opinion about a
  recording's taper — entries text, entry_lineage parse, taper_attributions + evidence,
  taper_confirmations, tuit_recordings (uploader-declared handle, or None = "not scraped") and
  recording_families/tapematch_family_meta/tapematch_pairs (label, member count, family conf and
  strongest scored pair = the quality of the match behind a propagated credit). Also isolated_texts(),
  which surfaces the two populations that never became a credit: *excluded* (resolves to a barred
  canonical) and *unknown* (nothing the vocabulary knows). The excluded half only exists in raw
  description text — the parser drops those names before entry_lineage — so it comes from a
  full-corpus regex scan (~12s), cached on an entry-count/vocabulary fingerprint.
Added: backend/taper_curation.html + /taper-curation: three tabs over 16.7k entries. Workbench is a
  dense grid (LB / date / attribution / TUIT / LB text / match / state) beside a detail pane holding
  the source comparison, the full LB description with every known alias highlighted by verdict, and
  the decide row; j/k/c/t/r/u keyboard flow, multi-select bulk, presets for the queues that matter
  (TUIT taper with no attribution, sources disagree, engine conflicts, propagated + undecided).
  Isolated text lists the excluded/unknown groups with add-as-taper / alias-of / not-a-taper actions;
  Tapers is a per-canonical rollup including TUIT tag counts. Reads are ungated; every write reuses
  the existing curator-gated confirm/reject/unresolved, bulk and vocabulary routes, so decisions stay
  in taper_decision_log exactly as /taper-review records them.
Added: backend/app.py: GET /api/tapers/curation, /api/tapers/curation/isolated,
  /api/tapers/curation/tapers, /api/tapers/curation/text/<lb>, and the /taper-curation page route.
Changed: backend/taper_curation.py agreement(): a vocabulary-barred name is not a competing opinion,
  so gear/source-type text sitting in entries.taper_name ("master", "sbd") cannot fill the "sources
  disagree" queue; merely-unknown names still count, since flagging one not-a-taper in the isolated
  tab is the loop the two tabs are meant to form. TUIT placeholder text ("unknown", "unidentified",
  "n/a") is treated as no tag at all, in the filters and the verdict alike.
Fixed: backend/taper_curation.py exclusion_reason(): a curator's `user_taper_flags` not-a-taper call
  was invisible unless the canonical also happened to be an alias value, so flagging a plain-text
  token ('bootleg') left it counting as a live opinion in the agreement verdict. The flags table is
  now read at every read entry point (and invalidates the cached description scan). Flagging
  'bootleg' + a full /api/derived/recompute took the "sources disagree" queue 1,463 -> 1,317.
Added: backend/taper_curation.html: a blacklist action beside every taper suggestion. Description
  text like 'first rehearsal' or 'excellent sound' reads as a candidate handle until somebody rules
  on it, so the Decide row and the names-found chips now carry a one-click blacklist writing a
  user_taper_flags not_taper row — it drops out of _TAPER_UNIVERSE for the parser, the attribution
  engine and every workbench surface at once. A blacklisted name is no longer offered for confirm at
  all: it renders as 'blacklisted' with only a re-admit button, so a ruled-out text cannot be
  confirmed by reflex. Existing derived rows still need /api/derived/recompute.
Added: backend/taper_curation.html: admitting a name to the vocabulary from wherever it is shown —
  confirm() refuses anything outside _TAPER_UNIVERSE, which blocked exactly the names curation
  exists to add (a real handle that only ever appeared as a TUIT tag, e.g. Black Rider). Every
  out-of-vocabulary candidate now carries a '+ vocab' button, the names-found chips carry
  '+ add'/'re-admit', the Tapers tab gained per-row Include-as-taper / Not-a-taper actions, and
  confirming an excluded name asks once and adds it before retrying. A *barred* canonical gets a
  user_taper_flags is_taper row, an *unknown* one gets a vocabulary entry; taper_rollup() now
  returns `excluded` so the UI can pick the right one.
Added: backend/tuit_scraper.py save_recording_html() + fetch_recording(html_dir=...), and
  tools/tuit_sync.py --html-dir / --no-save-html: every fetched /recordings/<id> page is archived
  verbatim to data/downloads/tuit/html/rec-<id>.html by default. The parsed fields are lossy, and a
  re-fetch costs another hit on a 21-member private tracker.

[2026-08-22] — chore(tapematch): TODO-323 step 2 — post-fix verdict diff; 4 stale analyses rewritten
Added: tools/tapematch/bug326_diff.py: parses the `=== CLUSTERS ===` block of each post-fix run and
  of its newest pre-fix predecessor, compares the two LB partitions, and buckets every date
  SAME/CHANGED/NO-PRIOR/UNUSABLE. It also reads the INGEST block and reports which sources actually
  shrank on re-ingest, which is what distinguishes a real de-dup effect from an unrelated corpus
  change. Reporting only; exit status is always 0.
Fixed: four pre-fix analysis.md files whose verdicts rested on a doubled, track-interleaved stream
  (BUG-326) rewritten as superseded, each keeping its original table as the record of what the
  pre-fix run said and pointing at the post-fix run as authoritative:
  runs/20260721_201619_1969-08-31 (LB-05444 splits out of LB-05457+LB-07385, 9 -> 10 families —
  this also answers that run's own open question about which LB owned the Family 2 correlation:
  on clean ingest it is LB-05457); runs/20260603_133817_1989-06-21 (LB-02142 merges into
  LB-06976+LB-08351, 3 -> 2, and its "staircase" note turns out to be an artefact of the doubled
  stream); runs/20260702_144047_1990-11-10 (LB-08282 joins LB-01201+LB-01215, 6 -> 5);
  runs/20260720_145852_2012-07-03 (Family 3 breaks up, 5 -> 7). Three of the four corrections vindicate
  taper commentary that the pre-fix run had contradicted, and the 2012-07-03 split confirms an
  over-merge that run's own analysis had already flagged as suspected — the fix moved the data
  toward the human-readable evidence in every case, which is the strongest signal it was real.
Changed: TODO-323 closed. The diff's most useful result is the negative one: 33 of 43 dates came
  back SAME, so the de-dup changed no family assignment there and their existing verdicts stand
  untouched. 4 dates had no prior run at all; 1991-06-21's pre-fix run was incomplete (no CLUSTERS
  section) so it had no verdict to invalidate — its post-fix run is complete and unanalysed, and
  /tapematch-batch will pick it up normally. The fifth CHANGED date, 1981-06-29, needed no rewrite:
  no analysis.md existed on either side, and its change is not a de-dup effect at all — no source
  shrank, a new source (LB-16657) simply entered the corpus between the two runs.
Notes: backend.tapematch_sync re-run afterwards returns unchanged totals (3,062 dates / 9,132
  families / 12,035 recordings / 0 errors), confirming recording_families already reflected the
  post-fix clustering — the stale data was in the written analyses, not in the DB.

[2026-08-22] — chore(bookkeeping): close out the BUG-326 re-run leftovers; tuit_sync --rescan
Added: tools/tuit_sync.py, backend/db.py: a `--rescan` flag, and the `get_tuit_download_rec_ids()`
  helper behind it. By default `--pages`/`--limit` now skip recordings that already have a
  tuit_downloads attempt and log how many were skipped, so repeated nightly runs advance through
  the catalogue instead of re-scanning the same head of the listing every time; `--rescan` restores
  the old include-everything behaviour and `--rec` is unaffected (explicit ids always process).
  `--limit` also switched from tuit_scraper.fetch_recent to paging fetch_browse_page until the
  limit is filled, because skipping already-seen ids out of a single fixed-size recent fetch would
  otherwise return fewer rows than asked for. This is the pacing enabler TODO-315 (full-catalogue
  crawl) calls for; the crawl itself is still not run, so TODO-315 stays open. Note fetch_recent
  now has no callers in the tree — left in place as scraper API rather than removed here.
  Verified: 63 tuit tests pass (tests/test_tuit_db.py, tests/test_tuit_scraper.py).
Changed: tools/tapematch/bug326_scan.py: promoted out of the tools/_ throwaway namespace (was
  tools/_bug326_scan.py). TODO-323 explicitly says to regenerate the affected-folder list from the
  scan rather than trust a stale copy, so the script has to outlive the session that wrote it.
  tools/_bug326_launch.sh deleted — its detached batch ran to completion.
Changed: TODO-323 marked In Progress with a progress note. Step 1 is COMPLETE: all 43 affected
  dates were re-run (bug326_rerun_queue.txt fully marked done, log ends "Batch complete: 43
  date(s) processed"), producing data/tapematch/runs/20260821_*. Step 2 — diff the new family
  assignments against the pre-fix runs and re-write only the analysis.md files whose verdict
  actually changed — has NOT been started, so the task is not closed. Recorded there because it is
  a live trap: 26 of the 43 new dirs already carry an analysis.md written by the nightly
  /tapematch-batch cron, which analyses a run dir on its own and never diffs it against the
  superseded run, so those files must not be mistaken for step 2 having been done.
Added: tools/tapematch/bug326_rerun_queue.txt: the completed re-run queue, committed as the record
  of which dates were reprocessed and when.

[2026-08-22] — chore(tapematch): seventh 50-run tapematch batch; one new clustering bug
Added: data/tapematch/runs/<50 dirs>/analysis.md: verdicts for 50 complete-set run dirs spanning
  2002-08-23 through 2008-07-08, fanned out to five claude-sonnet-5 subagents holding disjoint
  10-dir lists partitioned on date-group boundaries (the 2003-04-25, 2006-07-11 and 2006-10-27
  same-date pairs each went to a single agent, so a date is never judged twice independently).
  45 clean; 5 written as needs-review. Four of the five are the older half of a same-date pair and
  are superseded by their own re-run, which the analysis.md cross-references: 2003-04-25 (a merge on
  0.027 residual correlation against LB-02477's own "different recording than previous"),
  2006-07-11 (a split contradicting LB-04191's documented same-recording-with-channel-swap claim),
  2006-10-27 (see BUG-331). The fifth, 2005-06-11, is a standing judgment call rather than a
  suspected defect: the merge rests only on secondary evidence (windowed 0.48, hiss 0.70) at a
  0.394 primary correlation, with two unrelated taper credits and no same-source claim either way.
Added: BUGS.md: BUG-331 — a "staircase/splice" lag curve merges two sources into one family even
  when residual correlation is near-zero and SECONDARY MATCH reports no evidence at all. Two
  independent instances this batch (2008-07-08 at corr 0.030; 2006-10-27 at near-zero across two
  differently-credited taper rigs). The staircase rule is documented as a lower fingerprint bar,
  not a standalone same-source link, so a pair clearing no secondary evidence should not merge.
Changed: recording_families / tapematch_family_meta refreshed via backend.tapematch_sync:
  3,062 dates processed, 9,132 families written, 12,035 recordings linked, 0 errors.
Notes: batch 2 turned up another commentary-audit DISAGREES false positive fired by truncated
  table-header boilerplate (2003-10-12) — more evidence for the still-open TODO-322, no new task
  filed. Backlog after this batch: 733 eligible complete-set dirs / 625 dates, all machine-triaged
  clear, 0 attention.

[2026-08-21] — chore(tapematch): TODO-324 steps 1-2 — BUG-330 re-check queue built and triaged
Added: tools/tapematch/todo324_scan.py, tools/tapematch/todo324_recheck_queue.tsv: the scan
  TODO-324 asks for, plus the evidence needed to aim step 3. For every [DISTINCT SOURCE] line whose
  source results.json records as speed-unknown, it collects the corroboration that exists
  INDEPENDENTLY of the discredited line and buckets the row. Of 3,678 affected rows across 2,006 run
  dirs: SAFE-COMMENTARY 751 (508 dirs, 182 with an analysis.md) — a taper's own info file asserts
  the split, so the verdict never needed the line; AT-RISK-UNCORROBORATED 2,144 (1,410 dirs, 782
  with analysis); AT-RISK-DISAGREES 729 (482 dirs, 268 with analysis); CONFLICTED-SUBTHRESHOLD 54
  (41 dirs, 22 with analysis) — the sharp bucket, where the same source carries real hiss or
  fingerprint overlap that missed the merge bar while being declared "entirely different recording"
  off an untrusted ratio. Those two claims cannot both hold, and the conflict overlaps BUG-329.
  Nothing is CONTRADICTED outright: no affected source sits on a "→ SECONDARY LINK" line.
Changed: two heuristics were wrong on their first pass and are worth recording, since both failed
  in the direction that quietly shrinks the queue. (1) Distinctness claims were read from report.md's
  commentary block, which truncates each LB to a few hundred characters — the assertions almost
  always fall outside it. The scan now reads data/site/files/LBF-*.txt, the same prose
  prep_analysis_input.py bundles, via a single directory index (a per-LB glob over ~99k files was
  far too slow). (2) The claim regex matched "alternate recordings I am sharing for this date" and
  mined the trailing track-list LB ids as if they were a claim, crediting verdicts with
  corroboration they never had; a comparative connector (than/from/as/...) is now required. Same
  boilerplate-false-positive shape as TODO-322. Verified against a hand-read case (1984-07-05, where
  three sources are explicitly asserted distinct and a fourth has no LB id at all).

[2026-08-21] — fix(tapematch): [DISTINCT SOURCE] no longer concludes from a rejected speed ratio
Fixed: tools/tapematch/tapematch/cli.py: BUG-330. The DIAGNOSTICS section-3 loop triaged singleton
  sources on abs(speed_info[name]["ppm"]) > ppm_thr alone, never reading the "kind" or
  "ratio_confidence" it already stored beside that ppm. When estimate_ratio_v2 fails its confidence
  gate the matrix pass sets kind="speed-unknown", forces ratio 1.0 and skips resampling, so the
  retained ppm is precisely the estimate that was thrown away — and the diagnostic both gated on it
  and printed it as a measured "+36200 ppm speed offset". The second premise was circular: the
  correlations it called near-zero were computed unresampled, and a same-source copy several percent
  off speed cannot correlate that way, so the low correlation was partly an artifact of the same
  failed estimate. Added _speed_offset_trusted(), which quotes a ppm only if neither lag-curve pass
  (initial reference, re-selected central reference) called the source speed-unknown — mirroring
  align.union_staircase_sources, and leaving staircase sources quotable because that classification
  comes from the lag-curve shape rather than the ratio search. An untrusted source with near-zero
  correlation now gets [SPEED UNRESOLVED], which reports ratio confidence against the threshold,
  best cross-family correlation and best fingerprint Dice, says the unresampled correlation cannot
  rule same-source in or out, and concludes nothing. [DISTINCT SOURCE] and [REMASTER?] are now
  reachable only on a trusted offset.
Changed: tools/tapematch/triage_analysis.py: ALLOWED_TAGS deliberately omits [SPEED UNRESOLVED], so
  a date carrying it ESCALATES instead of auto-clearing. Comment records why.
Changed: tools/tapematch/WORKFLOW.md, tools/tapematch/DATA_PRODUCED.md: document the new tag and
  narrow the [DISTINCT SOURCE] description to trusted offsets.
Added: tools/tapematch/tests/test_speed_trust_diagnostic.py: six tests over _speed_offset_trusted
  (either pass objecting withholds the claim, staircase stays quotable, unknown source defaults to
  trusted). Full tapematch suite 401 passed; backend tapematch tests 87 passed.
Added: TODO.md: TODO-324. The fix changes future runs only. Scanning data/tapematch/runs found
  3,678 of 5,458 existing [DISTINCT SOURCE] lines (67%, across 2,006 run dirs) name a source whose
  results.json records speed_kind "speed-unknown", and 1,869 of those sit in runs that already have
  a written analysis.md. Those verdicts need re-checking, targeted rather than by bulk re-run; the
  affected population skews to off-speed bootleg CD/vinyl pressings, so expect real merges.

[2026-08-21] — chore(tapematch): cleared the two short-duration sources; filed BUG-330
Added: BUGS.md: BUG-330. Checking LB-06780 (1987-07-19) and LB-06698 (1969-08-31), the two
  unexplained short durations left over from the batch, cleared both as ingest defects: each is a
  flat single-directory folder whose on-disk track count matches report.md exactly (11 and 17), and
  each is a partial commercial bootleg CD pressing, so the [INCOMPLETE] flags are correct and
  BUG-327 does not apply. The check did surface a real defect in how both were diagnosed. cli.py
  gates its [DISTINCT SOURCE] line on abs(ppm) > ppm_thr and prints that ppm as a measured speed
  offset, without consulting speed_info[name]["kind"] or ["ratio_confidence"] — so for a
  speed-unknown source it is gated on the untrusted estimate the pipeline already discarded at
  cli.py:398 and quotes it as evidence. The other half of the evidence is circular: correlation ran
  at ratio 1.0, and a same-source copy 3.6-5.7% off speed cannot correlate without resampling. Both
  sources were called "entirely different recording" on that basis. The verdicts may still be right
  (the fingerprint pass ran on 53 and 64 cross-family pairs and linked neither), but they do not
  follow from the printed evidence.
Changed: BUGS.md: BUG-327 now records that these two were checked and excluded, replacing the note
  that they still needed a look.

[2026-08-21] — chore(bookkeeping): sixth 50-run tapematch batch; three new tapematch data-integrity bugs
Added: data/tapematch/runs/*/analysis.md: wrote 50 missing analysis write-ups (fanned out to five
  claude-sonnet-5 subagents holding disjoint dir lists; every date group was 1/1, so no group was
  split across agents). Backlog fell from 858 eligible dirs / 743 dates to 808 / 693, and the
  attention queue from 27 to 1. Synced the batch into the app DB with backend.tapematch_sync:
  3,062 dates processed, 9,132 families written, 12,035 recordings linked, 24,226 pairs, 0 errors.
  22 of the 50 dates carry a "needs review" verdict; the heaviest is 1997-12-18, an 11-way Family 1
  merge at mean intra-corr 0.101 built largely on chained secondary links, whose own commentary
  audit already flagged three DISAGREES.
Added: BUGS.md: three bugs found by the batch rather than by the source-identity calls themselves.
  BUG-327 — LB-07173 (1993-08-28) ingests at 25 tracks / 3:27:33 against a 1:32:48 median. Filed
  first as a missed de-dup case; inspecting the folder showed the opposite. It holds the show
  twice, as top-level d1/d2 and a nested "(REMASTERED)_fixed" copy with its own d1/d2, and the two
  are not byte-identical (412.9 MB vs 467.9 MB for d1), so both de-dup passes are correct to leave
  them alone and concat_source simply glues an original to a remaster. The fix is source-level
  version selection, not wider de-duplication, which would discard a real recording. BUG-328 — prep_analysis_input.py globs an LBF info file
  for every \bLB-(\d+)\b in a source's commentary with no date check, so uploader typos splice a
  different concert's lineage prose into the bundle (LB-00897/1981-06-30 into the 1999-06-20 run,
  LB-01711/1999-06-26 into 1999-07-24). BUG-329 — cli.py's SECONDARY MATCH display and the
  clustering step evaluate the merge decision separately and disagree: 1997-12-05 prints
  "hiss evidence (below merge threshold)" for LB-03909/LB-16114 and merges them into Family 1
  anyway, and that family reaches recording_families through tapematch_sync.
Note: TODO-323 stays open. Its re-run leg is finished — all 43 dates in
  tools/tapematch/bug326_rerun_queue.txt are marked done, and this batch analysed the resulting
  20260821_* run dirs — but its remaining legs are not: the new family assignments have not been
  diffed against the pre-fix ones, and the superseded run dirs still hold analysis.md files whose
  verdicts were written from doubled streams. BUG-327 is a separate defect that the re-runs were
  never going to clear, since it is not a de-duplication failure.

[2026-08-21] — fix(tapematch): ingest counted the same track twice in dual-format folders
Fixed: tools/tapematch/tapematch/ingest.py: BUG-326. list_tracks matched every file whose suffix
  appeared in config audio_exts, which lists eight formats at once, with no de-duplication. A
  source folder holding the same show as both WAV and FLAC therefore yielded every track twice
  (LB-10250: 17+17 -> 34, LB-10257: 19+19 -> 38), and a folder holding a duplicated directory tree
  yielded the whole show twice (LB-03685: CD 1..4 byte-identical to D1..4 -> 108 for a 54-track
  show). The rglob walk was never at fault; nothing collapsed the duplicates. The damage was worse
  than the inflated count report.md's [INFLATED] line already noted: _natural_key sorts
  '..._01.flac' immediately before '..._01.wav', so concat_source built a stream repeating every
  track back to back, leaving the source unalignable against its siblings rather than merely twice
  as long — which is why LB-10250 scored 0.003 against all seven of its siblings. Added two passes:
  _dedupe_formats keeps one file per (parent, stem) by a lossless-first preference order, and
  _dedupe_subtrees drops any top-level subfolder whose (stem, size) signature repeats one already
  kept. Both log what they dropped. Verified on the real folders: 34 -> 17, 38 -> 19, 108 -> 54,
  each matching its own info file, with D1..D4 pairing correctly to CD 1..CD 4 rather than
  collapsing onto one disc.
Added: tools/tapematch/tests/test_ingest_list_tracks.py: four regressions — both real-world shapes,
  lossy fallback when no lossless copy exists, and a genuine multi-disc show that must NOT be
  deduped (the first draft of that fixture gave every disc identical bytes and correctly deduped
  all eight subtrees, which is what surfaced the need for the negative case). Full suite 395 passed.
Changed: TODO.md: TODO-321 closed — the investigation it asked for is done and the answer was "not
  a walk bug", re-filed as BUG-326. TODO-323 opened for the re-run: a scan of all 13,067 concert
  folders under /mnt/DYLAN1 and /mnt/DYLAN2 found 50 affected folders (44 dual-format, 6 duplicated
  subtree) over 52 LBs and 43 dates, touching 44 existing run dirs of which 32 already carry a
  written analysis.md that may be wrong for the affected source. That is 0.4% of the corpus, well
  short of the "meaningful slice" this session first guessed at before measuring.

[2026-08-21] — chore(docs): fifth 50-run tapematch batch; doubled-ingest and audit-heuristic tasks filed
Changed: data/tapematch/runs/ (gitignored): a fifth 50-run batch, same 5x10 sonnet fan-out over
  disjoint dir lists prepared by the parent session; 31/50 flagged for review. Every dir came back
  1/1 on next_batch.py's date-group column, so the partition could not split a date. All five
  agents ran to completion first try — no mid-batch drop and no resume needed, unlike the previous
  two batches. Backlog now 826 dirs / 717 dates; the attention queue is effectively drained
  (86 -> 7) since this batch and the last took the attention-first ordering, leaving 819 clear
  dirs as the remainder. Sync clean: 3060 dates, 9113 families, 12011 recordings, 24053 pairs,
  0 errors.
Changed: TODO.md: two new tasks, and corroboration appended to the three filed by the previous
  batch. TODO-321 — an LB's ingested track count and duration come back almost exactly 2x what
  its own info file states, tripping report.md's [INFLATED] diagnostic and distorting every
  correlation it takes part in: LB-10250 (34 tracks vs a documented 17), LB-03685 (108 vs ~54),
  LB-10257 (38 vs a stated 19), plus LB-05444/LB-05457 resolving to one shared folder ingested as
  a single 40-track blob. The open question is whether the duplication is on disk or in the ingest
  walk; if it is the walk, that is a code defect and re-files as a BUG. TODO-322 — the
  commentary-audit DISAGREES flag keyword-matches info-file prose and fires on boilerplate and
  bonus-track filler (confirmed spurious on 1984-06-04 and 1995-03-31), costing reader attention
  on every run where it misfires without corrupting stored data; scope the match to the lineage
  portion or require a named LB number. TODO-318 and TODO-319 both gained materially larger
  evidence sets rather than new tasks: 318's polarity validation set grew past the original five
  1984 dates (1995-06-15, 2009-04-02, 1997-08-23, 1984-06-09, plus processing-defeated under-merges
  on 1978-12-10 and 1984-06-04), and 319's over-merge pattern has a new worst case in 2007-04-08,
  where all 7 recordings collapsed into one family against four explicit taper contradictions.
  TODO-320 took LB-06631, whose lineage text describes an unrelated 1971 event.

[2026-08-21] — chore(docs): fourth 50-run tapematch batch; polarity-rescue and over-merge tasks filed
Changed: data/tapematch/runs/ (gitignored): a fourth 50-run batch, same 5x10 sonnet fan-out over
  disjoint dir lists prepared by the parent session; 31/50 flagged for review. Every dir came back
  1/1 on next_batch.py's date-group column, so the partition could not split a date. One agent
  stopped at 4 of 10 and was resumed by name to finish the rest from its own transcript — the same
  failure and the same cheap recovery as the 2026-08-20 batch, which is now the expected pattern
  rather than a surprise. Backlog now 905 dirs / 782 dates (attention 86, clear 819). Sync clean:
  3060 dates, 9113 families, 12011 recordings, 0 errors.
Changed: TODO.md: three tasks filed from cross-run patterns the batch exposed. TODO-318 —
  five 1984-tour shows (Boston, Hamburg, Basel, Rome, Miami) each carry taper commentary claiming
  channels swapped and/or wavs phase-inverted, and each reads near-zero mid-mid correlation and
  split into distinct families. An agent read that as a missing capability; it is not. TODO-184
  shipped match.polarity_aware_corr / polarity_rescue on 2026-06-24 and cli.py:473-490 wires it,
  but config.yaml polarity.enabled is false, held back pending validation on real multi-source
  dates because enabling it decodes stereo in Pass 1 (~461 MB mono -> ~1.2 GB stereo peak RAM) and
  the matcher threshold is calibrated on mid-mid. These five dates are exactly the validation set
  that config comment asks for. TODO-319 — recordings chained into families with no confirmed
  pairwise correlation to any member, against taper commentary, on seven dates (2010-03-23 Tokyo
  is the worst: all 6 merged with zero confirmed pairwise evidence). Ordered behind TODO-318,
  since some may be genuine same-source pairs the disabled rescue would have scored correctly.
  TODO-320 — three per-LB data fixes: LB-04433's info file describes a piano-era show under
  2002-04-30, LB-14883 and LB-14908 excluded by ingest failures on unreadable files, LB-11041
  spans two show dates.

[2026-08-20] — chore(docs): third 50-run tapematch batch; unrouted-collection work package filed
Changed: data/tapematch/runs/ (gitignored): a third 50-run batch, same 5x10 sonnet fan-out over
  disjoint dir lists prepared by the parent session; 32/50 flagged for review. Every dir in the
  batch came back 1/1 on next_batch.py's date-group column, so the partition could not split a
  date. One agent dropped on an API error with 9 of its 10 written; resuming it by name finished
  the tenth from its own transcript, no re-prep needed. Backlog now 1065 dirs / 902 dates
  (attention 246, clear 819). Sync clean: 3060 dates, 9113 families, 12011 recordings, 0 errors.
  The dominant flag pattern this round is a taper's own "same source as LB-xxxxx" claim sitting
  against a near-zero correlation, plus several unexplained [INCOMPLETE] flags.
Changed: tools/tapematch/CONTRADICTED_EMB_SECOND_PASS.md: regenerated from the current
  observations.db (uncommitted from an earlier session, recorded here). The corpus shrank
  1822 -> 1766 pairs as re-runs superseded old observations, and Tier A rule_d-qualifying went
  46 -> 0 — the 34 alignment_failure and 10 unexplained pairs that previously cleared the 0.75
  bar no longer do. The document's verdict is unchanged and now rests on a cleaner base: the
  contradicted corpus remains statistically indistinguishable from the curator-silent control,
  and the unexplained bucket is 90.0% control-like.
Added: instructions/UNROUTED_COLLECTION_BACKLOG.md (written 2026-08-17, never committed):
  work package for the 1,976 in-scope my_collection folders whose disk_path sits outside the
  routed mount roots — ~1.36 TB across PRIVATE LB (now-public, status=ok), both LB HOPPER trees,
  LK Collections, and Double LBs. 1,968 resolve cleanly, 8 blocked no_date, zero destination
  collisions. Filed as TODO-317; status remains not started.
Added: tools/_route_audit.py, tools/_route_dryrun.py: read-only audit and filing dry-run behind
  that package (routed-vs-unrouted census; canonical name + destination for every unrouted
  folder, to .debug/unrouted_plan.csv). Throwaway by convention — delete when TODO-317 closes.

[2026-08-19] — fix(backend): overlay seeding must not require matching folder names
Fixed: tools/tuit_sync.py: the torrent-root/folder name match was applied to the overlay path as
  well as the direct path, and wrongly — an overlay is *created* with the torrent's root name and
  sources files by basename, so the collection folder may be named anything. The check is a
  leftover from the pre-overlay design, where a client resolving <save_path>/<root>/… genuinely
  did need the names to agree. It rejected 5 of 5 real recordings whose audio matched 100%
  (19/19, 19/19, 19/19, 20/20, 20/20) purely because the uploader's folder naming differs from
  the collection's. Name matching now gates only the in-place path.
Added: tools/tuit_sync.py _best_source_folder(): when no folder carries the torrent's name, the
  source is chosen by content — the linked folder supplying the most of the torrent's audio.
Verified: 6 recordings now seeding from overlays across DYLAN1/DYLAN2 — 4.09 GB of audio shared
  by hardlink for 31.4 MB of actual disk. Two are at 99.83%/99.92% pending 0.7 MB of uploader
  extras (JPEGs, Thumbs.db) that exist neither locally nor on losslessbob.com; taken with
  --allow-partial-overlay so the remainder downloads into the overlay. Every collection folder
  untouched, qBittorrent downloaded=0 on all six.

[2026-08-19] — feat(backend): detect seed overlays orphaned by a collection move or delete
Added: backend/seed_overlay.py overlay_status() / find_overlays_for_lb() / warn_if_seeded():
  a hardlink follows the inode, so renaming or moving a collection folder *within* its volume
  leaves an overlay perfectly healthy and needs no repair (verified: inode and link count
  unchanged, overlay still verifies 100%). A delete — or a cross-volume move, which is
  copy + rmtree — drops the link count to 1, and the overlay silently becomes the sole holder of
  those bytes, so the disk space is never reclaimed. Detection uses link counts rather than
  paths, so it stays correct after any rename.
Changed: backend/filer.py: start_file_job()'s cross-device branch now calls warn_if_seeded()
  immediately before shutil.rmtree() of the source. Warning only, wrapped so a lookup failure can
  never block filing; the same-device os.rename() path is untouched because it is harmless.
Added: tools/tuit_sync.py --check-overlays: lists the seed folder currently in force per LB
  (newest attempt wins), labels it [overlay] or [direct], reports MB shared with the collection
  vs MB held only by the overlay, and exits 1 when any are orphaned.
Added: tests/test_seed_overlay.py: 5 more tests covering the rename-is-harmless case and the
  delete / simulated cross-volume-move cases that do orphan an overlay.

[2026-08-19] — feat(backend): seed TUIT torrents from an overlay, collection untouched
Added: backend/seed_overlay.py: builds a seedable folder outside the collection so a recording
  can seed at 100% without a byte being written to curated files. Audio is hardlinked from the
  collection (same inode — 1,059.9 MB cost nothing on LB-00707); LBF sidecars are copied from
  data/site/files; anything still short is left to the swarm and lands in the overlay. Overlays go
  to <mount>/TUIT Seeds — the source's own filesystem, since the drives are separate NTFS volumes
  and hardlinks cannot cross a mount, and outside the …/Concerts roots in collection_mounts so the
  disk scanner will not index them as collection folders.
  The subtle part: a torrent piece can straddle a file boundary, so a file next to missing data
  can be written to while the client completes that piece. plan_overlay() computes the piece span
  of every file and demotes any hardlink that shares a piece with unresolved data to a copy, so a
  client write can never reach a collection inode. build_overlay() snapshots the source and the
  caller re-checks it afterwards; the run aborts if anything moved.
Added: backend/db.py get_site_file_urls(): maps LBF filenames to their original losslessbob.com
  URLs from site_inventory. The crawl rewrote links inside saved HTML, so data/site/files holds
  2,412,606 B where the torrent wants 2,281,077 B (the row's local_sha256 != body_sha256 flags
  exactly this). Re-fetching the URL returned a byte-exact original.
Changed: tools/tuit_sync.py: --overlay makes the 100% gate a fallback instead of a refusal, with
  --overlay-root, --refetch-sidecars, --max-fetch-mb (default 25) and --allow-partial-overlay.
  Verified end to end on LB-00707: 32 hardlinked, 3 copied, 1 re-fetched, 0 left to the swarm →
  overlay verified 100%, added to qBittorrent, state stalledUP with downloaded=0. The collection
  folder still has its original 32 files and none of the 4 sidecars.
Added: tests/test_seed_overlay.py: 23 tests including the piece-boundary demotion rule, inode
  identity for hardlinks, refetch size rejection, and explicit collection-untouched assertions.

[2026-08-19] — fix(backend): BUG-325 — TUIT seeding must never write to a collection folder
Fixed: tools/tuit_sync.py: --seed added LB-00707 to qBittorrent at 99.70%, which means the client
  would have downloaded the 10 absent files (4 missing text sidecars plus a partial .shn) straight
  into /mnt/DYLAN2/Concerts/1978/…(LB-00707). Caught by tj before any data moved — the torrent was
  stopped and removed with deleteFiles=false at downloaded=0, so the folder was never touched.
  Seeding is now refused unless the folder verifies at exactly 100%.
Added: backend/torrent_verify.py: a real bencode reader (the previous regex peek at info.name
  could not see piece hashes) plus verify_folder(), which streams the folder through the torrent's
  SHA1 piece hashes read-only, zero-filling absent regions so covering pieces fail. Reports
  percent, missing files and size mismatches. Independently reproduced qBittorrent's 99.70% on
  LB-00707 in 0.7s. Nothing in the module opens a file for writing.
Added: backend/db.py is_seedable_to_tracker(): lb_status is the authority — only 'public' may be
  seeded ('private'/'missing'/'nonexistent'/unknown are refused). Counterpart to
  is_postable_to_forum(). A first draft also blocked on folder-path markers (PRIVATE LB,
  NOTORRENT); tj ruled lb_status is the signal, so the path heuristics were dropped.
Changed: tools/tuit_sync.py: --force-seed removed outright — it was the exact footgun. Seed status
  'no_local_files' renamed 'not_seeded', now covering refusal by status, name mismatch or
  incomplete verification, with the reason recorded in tuit_downloads.error.
Added: tools/tuit_sync.py --set-credentials: prompts for username + password (getpass, no echo),
  stores them in the keyring and verifies with a real login. For rotating the password without
  putting it in a file or in shell history.
Added: tests/test_torrent_verify.py: 30 tests over torrents built from real bytes with genuine
  piece hashes — complete/missing/wrong-size/corrupted-byte/renamed-folder cases, plus assertions
  that verification creates no files and changes no mtimes.

[2026-08-19] — feat(scraper): TODO-314 — TUIT private-tracker integration (catalogue + seed)
Added: backend/tuit_scraper.py: scraper for tangledupintorrents.org, a ~21-member private Bob
  Dylan tracker (Laravel; CSRF _token + session-cookie login, no JSON API — /api is 404). Parses
  two surfaces: /browse listing rows (source type, date, venue, LB number, lineage, format,
  quality, swarm counts, taper, uploader, added-time; 1,635 recordings at 50/page) and
  /recordings/<id> detail pages (full info hash from the title attribute, size, file list with
  per-file sizes, setlist, sibling sources for the same show, info-file text, spectrogram and
  preview URLs, /show/<id>/download torrent link). merge_row_into_recording() reconciles the two,
  with the listing authoritative for taper and freeleech. torrent_root_name() reads info.name via
  a minimal bencode scan so a fetched torrent can be name-matched against a collection folder.
  Every request is separated by a 3s default delay — the site's robots.txt is a blanket
  Disallow whose own comment scopes it to search indexes, and /rules + /terms carry no
  prohibition on automated access, but a 21-member tracker gets human pacing regardless.
Added: backend/db.py: tuit_recordings (one row per site recording id; every rendered field kept,
  list-shaped fields as JSON blobs, first_seen_at preserved across refreshes) and tuit_downloads
  (fetch/seed attempts, mirroring wtrf_downloads) plus accessors upsert_tuit_recording,
  get_tuit_recording(s), add/update/get_tuit_downloads.
Added: backend/db.py: get_folders_for_lb() — resolves an LB number to on-disk folders, reading
  my_collection.disk_path (16,610 rows) first and folder_lb_link (228) second. folder_lb_link
  alone was not enough: it only covers freshly downloaded folders, not the filed collection.
Added: tools/tuit_sync.py: CLI to sync the newest N recordings (default 5), whole listing pages,
  or specific ids; --fetch-torrents saves the personalised .torrent; --seed then locates the
  local files and hands the torrent to qBittorrent via add_torrent_for_seeding, tagged "tuit".
  A seed is refused unless the torrent's root folder name matches the local folder name —
  a mismatch silently turns a seed into a fresh download — with --force-seed to override.
Added: tests/test_tuit_scraper.py, tests/test_tuit_db.py: 58 tests over hand-written HTML
  fixtures (no scraped page with a session token is committed) and temp-file DBs.
Changed: backend/credentials.py: SERVICE_TUIT added, with a /run/secrets mapping like WTRF.
  Credentials imported into the OS keyring and the plaintext tuit.cred deleted.
Changed: .gitignore: *.cred — tuit.cred was sitting untracked and unignored in the project root.
Verified: logged in as kuddukan, synced the newest 5 recordings (every column populated), fetched
  LB-00707's torrent and added it to qBittorrent — it matched the collection folder and came up
  at 99.7%, all 26 .shn audio files recognised, only text sidecars outstanding.

[2026-08-19] — chore(docs): 50-run tapematch batch fanned out to subagents; BUG-324 title residue
Changed: .claude/commands/tapematch-batch.md: removed the false claim that subagents hit a hard
  Write-tool block on .md files — the only PreToolUse hook in .claude/settings.json is a path
  guard for writes outside the project root. Documented the real fan-out constraint instead:
  next_batch.py is stateless and only reports dirs lacking analysis.md, so concurrent agents each
  calling it are handed the same dirs. The parent session must run steps 1-2 once, partition the
  dirs into disjoint per-agent lists, and forbid agents from calling next_batch.py /
  prep_analysis_input.py themselves. Step 4 attribution now records the model that actually wrote
  the file (the subagent's id when fanned out), not the orchestrator's.
Changed: data/tapematch/runs/ (gitignored): 50 analysis.md written by 5 parallel sonnet agents,
  10 disjoint dirs each; 33/50 flagged for review. Backlog 1315 -> 1265 eligible. Family sync
  clean: 3060 dates, 9113 families, 12011 recordings linked, 0 errors.
Changed: data/tapematch/runs/ (gitignored): a second 50-run batch, same 5x10 sonnet fan-out;
  35/50 flagged for review. Backlog 1265 -> 1215 dirs / 1038 dates. Sync clean (3060 dates,
  9113 families, 12011 recordings, 0 errors). The triage_analysis.py --apply pre-step was a
  no-op this round: AUTO=0, ESCALATE=2020 — the trivially-clean tier is drained, so every
  remaining dir needs real judgment.
Changed: tools/tapematch/next_batch.py: same-date run dirs are now emitted contiguously as a
  date group, tagged i/j in a new trailing column, and a batch size rounds up to the group
  boundary so a date is never split across two writers. Two agents in the batch above analysed
  2010-11-24 from separate run dirs and returned contradictory verdicts (one called the
  LB-09012/LB-15230 merge spurious, the other reported three families) — 163 of 875 pending
  dates have multiple runs, so this was systemic, not a one-off. Added --newest-per-date to skip
  superseded re-runs (1215 dirs collapse to 1038 dates), and --stats now reports dirs and dates
  separately.
Changed: tools/tapematch/ANALYSIS_WRITER_PROMPT.md: added a fourth verdict outcome, "anomaly
  explained", for a flagged [INFLATED]/[INCOMPLETE] run whose cause the sources themselves
  document (bonus disc, opener set, multi-show box set, taper's own "partial" note). The old
  wording pushed every such flag into "needs review", which is why the batch came back 35/50
  flagged — a rate that makes the queue unreadable; the writers had already started inventing an
  undocumented "flag explained" category to cope. Also replaced the blanket "never contradict
  report.md's clusters" ban with a documented-override rule: state the clustered result first,
  then the contradicting commentary, then mark it needs review.
Changed: .claude/commands/tapematch-batch.md: fan-out must partition on date-group boundaries
  (check the i/j column) — a blind split -l on the batch listing can cut a date in half.
Fixed: data/tapematch/runs/*/report.md, */analysis.md: BUG-324 — 44 title lines (41 report.md,
  3 analysis.md) still carried the pre-BUG-280 +100y date, e.g. "tapematch session — 2061-09-06".
  BUG-280's fix (c4e9b1e2, 2026-07-29) renamed the run dirs and backfilled the DBs but never
  rewrote markdown already on disk. Swept with the run dir name as the authoritative date,
  rewriting only dates exactly 100 years ahead of it so real 2025/2026 shows were untouched.
  Also amended the stale prose notes in 7 analysis.md files that described this as a live
  report-generator defect and told readers to chase it in the code — the generator has been
  correct since 2026-07-29.
Note: two further leads from the batch were checked and are NOT bugs — the 2026-04-29 "mixed
  date" folder is half of a Crystal Cat two-show release (LB-16664+LB-16665, Rochester and
  Tyler), and 1998-06-28's LB-15721 has an "Aud>FM>..." lineage with commentary reading
  "Obviously, an audience tape", i.e. one source with confusing prose, not two bundled.

[2026-08-17] — fix(backend): BUG-323 — temp WAV decoding no longer fills the 2.7 GB /tmp partition
Added: backend/tmp_utils.py: audio_tmp_dir() — probes LOSSLESSBOB_TMPDIR, then /mnt/DATA0/tmp
  (458 GB), returns None to mean "system temp dir"; result cached, reset_cache() for tests and
  drive remounts. Generalises the precedent already used in tools/tapematch/tapematch/cli.py:161.
Fixed: backend/checksum_utils.py, backend/sox_utils.py, backend/ab_clips.py, backend/bobtalk.py:
  every tempfile.mkstemp/mkdtemp for decoded audio now passes dir=audio_tmp_dir(). Decoded WAV is
  ~10x its FLAC/SHN source, so a few concurrent decodes — or one process killed before its
  finally-block unlink — could fill /tmp (107 MB of orphaned WAVs from 2026-08-08 did exactly
  that; the other 1.1 GB was an ad-hoc /tmp/shnwav decode loop from a 2026-08-10 session).
Added: tests/test_tmp_utils.py: 5 tests — env override, unwritable-override fallback, caching,
  empty scratch-base list, writability of the selected dir.
Changed: .claude/CLAUDE.md: temp-files section — no bulk audio in /tmp; ad-hoc decodes go to
  /mnt/DATA0/tmp/<name>/ and are deleted in the same session; backend code uses audio_tmp_dir().

[2026-08-17] — feat(backend): TODO-313 — master taper list curation on /taper-review
Added: backend/db.py user_taper_flags (USER_TABLES, never exported) — the runtime override on
  _NOT_TAPER, which is a code-level frozenset and so could not be changed from the UI at all.
  'not_taper' rows exclude a canonical from _TAPER_UNIVERSE (the name stays an alias value, so
  the parser still collapses its spellings, but the engine never seeds it); 'is_taper' rows
  re-admit a builtin-excluded one. Applied in reload_taper_aliases *after* the _NOT_TAPER
  subtraction, so an explicit local call always beats the shipped default.
Added: backend/db.py list_taper_vocabulary() — the canonical-keyed master list, the counterpart
  to TODO-241's alias-keyed admin. Groups the flat 431-alias table by canonical and unions in
  _NOT_TAPER plus any flagged names: 32 of the 35 shipped exclusions — dolphinsmile among them —
  are never alias *values*, so grouping the alias table alone hid them and left that call
  irreversible. Reports not_taper_origin so a shipped judgement is distinguishable from a local one.
Added: backend/db.py set_taper_flag/clear_taper_flag and merge_tapers(). A merge repoints user
  alias rows, writes user 'add' overrides for builtin alias keys (the builtin table is code and is
  never edited), and rewrites taper_confirmations — leaving those behind would point sticky
  MASTER-tier curator decisions at a canonical nothing resolves to any more, silently voiding real
  work. Derived attributions are deliberately not rewritten; attributions_pending reports how many
  are stale until the next recompute.
Added: backend/app.py GET/POST /api/tapers/vocabulary, POST /api/tapers/vocabulary/<canonical>/flag
  and POST /api/tapers/vocabulary/merge. Read open, the three writes curator-gated, matching the
  rest of the taper API.
Added: backend/taper_review.html fourth "Taper list" tab — 331 names searchable by canonical *or*
  alias (a curator hunting a variant knows the alias, not the canonical), six filters, and a
  per-row curate panel with alias add/remove, the not-a-taper toggle, reset-to-shipped-default,
  and merge/rename. Destructive actions confirm and say plainly that they change the shared
  vocabulary corpus-wide rather than one entry.
Changed: the old collapsed "Taper aliases" section retired into that tab — it was a flat 431-row
  list that could not express either question a curator actually asks.
Note: curated vocabulary stays USER-tier for now. Promoting it to MASTER so it ships to other
  installs alongside taper_confirmations is deferred to a follow-up by decision.

[2026-08-17] — feat(backend): TODO-312 follow-up — /taper-review usable on a phone
Changed: backend/taper_review.html — Entries and Tapers collapse from 9-column tables into
  stacked cards below 760px. The markup stays a real table and each cell carries a data-label
  that becomes its heading in the card layout, so there is still only one render path. Before
  this the columns a decision actually turns on (attributed taper, tier, decision, the Review
  button) sat off-screen behind a horizontal scroll on a phone. The Queue tab was already
  mobile-first and is unchanged.
Added: two phone-only controls, because both of their desktop homes are in the table header the
  card layout hides — a sort dropdown in the filter bar, and a "Select page" button standing in
  for the header's select-all checkbox.
Changed: the entry's own parsed taper is dropped from the phone card (it is context, not a
  decision input, and is still in the expanded Review panel), and the select checkbox moved to
  the card's top-right corner instead of claiming a labelled row.
Verified: headless Chromium at 390×844 (iPhone 14 logical px, isMobile/hasTouch) over all three
  tabs, the expanded review panel, and the bulk bar — no horizontal body overflow anywhere, no
  JS errors, tap-driven selection and "Select page" both working.

[2026-08-17] — feat(backend): TODO-312 — taper attribution curation console at /taper-review
Added: backend/db.py taper_decision_log (USER_TABLES, so it never ships in a master export) —
  an append-only audit trail carrying prev_action/prev_taper alongside each decision. The
  decisions themselves stay in the MASTER-tier taper_confirmations; this only records how they
  got there, and that prev_* pair is what makes an undo possible without a full recompute.
Added: backend/taper_attribution.py _log_decision(), called inside the existing transactions of
  confirm/reject/mark_unresolved and *before* the taper_confirmations upsert (that ordering is
  what captures the prior state). Logging lives in the engine rather than the routes so
  tools/attribute_tapers.py and any other caller are recorded too.
Added: backend/taper_attribution.py revert_decision() — replays the recorded prev_action through
  the matching public function with source='revert', itself logged, so history stays append-only.
  Undoing a first-ever decision is the one case with nothing to replay: it deletes the
  taper_confirmations row *and* the derived taper_attributions row (the decision had already
  rewritten the latter to confidence='confirmed', which would otherwise outlive its confirmation)
  and returns needs_recompute: true.
Added: backend/taper_attribution.py list_review_rows() / taper_rollup() / list_decisions() —
  the console's read layer. One join (entries → taper_attributions → taper_confirmations) carries
  entry context inline, replacing the old page's per-card /api/entry/<lb> round trip, with facet
  counts computed per-dimension so a filter chip's number is what switching to it would yield.
Added: backend/app.py GET /api/tapers/review, GET /api/tapers/review/tapers,
  GET /api/tapers/decisions (open, matching the existing attribution reads) plus curator-gated
  POST /api/tapers/attributions/bulk and POST /api/tapers/decisions/<id>/revert. Bulk applies
  each LB independently and reports per-row outcomes, so one bad row (e.g. a taper outside the
  known-taper universe) doesn't sink the batch; batches cap at 500.
Changed: backend/taper_review.html rewritten as a three-tab console. It previously reached only
  the ~96-row mention-conflict slice; the other ~8,550 attributions across 273 handles had no
  review surface at all. Queue keeps the original one-card flow and its conflict=1&kind=mention
  default, with presets for wider slices. Entries is the filterable table — facet chips, search,
  paging, checkbox multi-select into bulk confirm/reject/unresolved, and a row expander with
  evidence, decision history and Revert. Tapers is the per-handle rollup, ordered by undecided
  count, that drills into Entries filtered to a handle — the surface for spotting alias variants
  and era outliers. Tab/filters/page live in location.hash so any view is linkable.
Fixed: date sorting in the new queries. entries.date_str is M/D/YY, which sorts and MIN/MAXes
  wrong as text ('10/1/23' < '9/9/06'), so the rollup's span and the date sort go through a SQL
  rewrite to YYYY-MM-DD; the two-digit year pivots at 40 (corpus spans 1958–present).
Fixed: the page now disables every write control behind one banner when GET /api/curator reports
  non-curator, instead of 403-toasting per click, and reacts to hashchange so a pasted or
  Back-navigated view actually switches tabs.
Note: verifying the revert path ran a full taper_attribution.recompute() against the production
  DB, moving the derived table 8,641 → 8,646 rows and 131 → 136 conflicts. taper_attributions is
  USER-tier and rebuilt wholesale by design; taper_confirmations was unaffected at 109 rows.

[2026-08-17] — feat(gui): TODO-305/304 — the LB ledger and catalogue-sync screens, plus locales
Added: gui_next ScreenLbdirLedger.tsx (/lbdir/ledger): the full per-entry ledger the coverage
  screen's "View full ledger" action was missing — every countable LB row with its state
  (verified / held / unmatched / missing), source family, filed date and needs-review flag.
  Filter chips (all / in collection / missing / no family yet / needs review), free-text search
  over LB#/date/location, 100-row paging, and `?lb=<n>` deep-linking that lands on the page
  holding that entry. Filter/page/query live in the URL so a view survives a reload.
Added: gui_next ScreenLbdirSync.tsx (/lbdir/sync): installed-catalogue header, a manual
  "Check LB for an update" (GET /api/master/github_check, install still happens in Setup), and
  the snapshot import history with per-update entry delta and status-change count.
Added: backend/lb_coverage.py get_ledger() / get_snapshots() + GET /api/lb/coverage/ledger and
  GET /api/lb/snapshots in backend/app.py. The ledger shares _held_sql() with the coverage
  payload, so the two screens can never disagree about what "held" means.
Added: backend/db.py lb_snapshot_history table + _record_snapshot_history(), written by
  import_master_db() (new `source` arg: "github" | "file"). meta only ever holds the *current*
  master_version, so without this table there is no per-update diff to show. A DB that installed
  its catalogue before this shipped gets one synthetic row derived from meta, flagged as such.
Changed: gui_next ScreenCoverage.tsx — "View full ledger" now goes to /lbdir/ledger instead of
  standing in with /collection; new "Sync history" ghost action alongside it.
Changed: gui_next locales de/fr/es/it/nl — TODO-304's ~60 coverage-screen strings translated
  along with the ~60 new ledger/sync keys (DeepL, 10,508 chars). Remaining still-English values
  are proper nouns and identical cognates ("LB", "GitHub", "Format").
Added: tests/test_lb_coverage.py — 10 tests over ledger state/filters/paging/search/deep-link
  and snapshot history, including one asserting import_master_db() writes exactly one row.
[2026-08-16] — fix(backend): TODO-311 — an already-measured folder is never re-scanned
Fixed: backend/ranker_jobs.py plan_scan(): a backlog run forked a NEW scan_id whenever the
  effective ranker config differed at all from the stored one. A single scoring-only tweak
  (`polarity['sibilance_ratio_db'] -1 -> 0`) therefore orphaned scan 18's 16,099 measured LBs
  and queued a full corpus re-scan — 14,558 folders of audio decode to recover data that was
  already on disk and still valid, since polarity is read by scoring.py, not by extraction.
  Backlog runs now append to the scan holding the most measurements taken with the *current
  extraction config*, and plan only the LBs missing from it.
Added: concert_ranker/config.py SCORING_ONLY_FIELDS / extraction_config() /
  extraction_fingerprint() — the config split that decides what actually invalidates a
  measurement. A new scan is created only when the fingerprint changes.
Added: quality_scans.extraction_key (backend/db.py SCHEMA_SQL + concert_ranker/lb/repo.py
  ensure_schema, both with PRAGMA table_info guards and a backfill from each scan's stored
  config_json) + repo.reusable_scan_id() / same_key_scan_ids() / adopt_metrics(). Adoption
  copies rows measured under a sibling same-key scan into the active one (INSERT OR IGNORE),
  so the 21 rows the stopped fork had written are reused rather than re-decoded — ranking is
  per-scan_id, so measurements have to live under the scan being ranked.
Fixed: backend/refresh.py — the Home card's "pending" for ranker_scan counted raw
  my_collection under MAX(scan_id), ignoring the non-concert/non-public exclusions the scan
  itself applies, so it read 16,496 against a plan of 14,558 and reset to the whole
  collection whenever an empty fork appeared. Both ranker steps now count through the
  planner's own code via a new RefreshStep.backlog_fn (callable backlog, used when the count
  cannot be standalone SQL; falls back to backlog_sql, and returns None -> 'unknown' when the
  quality tables are absent). ranker_scan's watermark is MAX(quality_recording_metrics
  .scored_at) — when anything was last actually measured — not MAX(quality_scans.started_at),
  which dated an empty fork as a fresh scan.
Changed: concert_ranker/cli.py — worklist eligibility SQL factored into _worklist_from_where()
  and reused by the new collection_backlog_count(), so the pill and the run's `planned` cannot
  drift; backend/ranker_jobs.py run_rerank() defaults to the active scan, not the newest
  scan_id (which would score an empty fork).
Live effect: ranker_scan pending 16,496 -> 454, active scan 18 (16,099 rows) reused; the
  running full re-scan was stopped. Tests: +7 (test_concert_ranker, test_pipeline_jobs,
  test_refresh), full suite 1,330 passing.

[2026-08-16] — feat(backend): TODO-309 — the chronicle parser gets a registry step and a route
Added: backend/refresh.py step `olof_chronicle_parse` (T3, wholesale, upstream olof_fetch) +
  backend/refresh_exec.py inproc executor calling backend.olof_chronicle_parser.run_parse.
  The module has existed since the Olof work but nothing called it: no route, no STEPS entry,
  no tool — chronicle pages were fetched by olof_fetch and parsed by nothing, and Phase 3's
  rescope of olof_parse to corpus='dsn' (correct for the step that exists) left them with no
  freshness signal at all.
Added: POST /api/olof/chronicle_parse (backend/app.py) — mirrors /api/olof/parse: synchronous,
  409 while the olof fetch job runs, 503 without bs4/lxml, one refresh_step_runs row under its
  own step_id. Verified live on '2016 A Wonderful Answer.htm' (21 chronicle rows).
Changed: song_index upstream now includes olof_chronicle_parse — the chronicle parser writes
  olof_events/olof_songs too, so a stale chronicle parse leaves the song index short those
  performances. On the live DB the new step reports stale/backlog 0 and song_index correctly
  flips to blocked; a Run clears both.
Note: the backlog predicate is scoped to `corpus='chronicle' AND year IS NOT NULL`.
  chronologies.htm (the year index) carries no year, so no parser can ever consume it —
  counting it would pin the backlog at 1 forever, the exact failure that forced olof_parse's
  rescope. Pinned by a test; executor tiering is now 8 inproc + 5 job + 15 manual (28 steps).
Locale: `pipeline.steps.olof_chronicle_parse` added in all 6 languages.

[2026-08-16] — feat(backend/gui): pipeline refresh Phase 4 — human queues as first-class blockers
Added: backend/queues.py: RefreshQueue registry of the four human review queues — taper
  conflicts (129 pending), setlist-fingerprint suggestions (242 LBs), staged xref filesets (0)
  and TapeMatch date curation (3,057 of 3,060) — counted from the app DB only, never
  tools/tapematch/observations.db, which nightly analysis holds locked for hours. Two kinds:
  'gate' (expected to drain to zero → badge, step attention, chain advisory) and 'backlog'
  (open-ended → ratio only, never a badge, because a badge that never reaches zero teaches the
  user to ignore all of them). Counts are decision units, not rows: 691 suggestion rows are 242
  decisions. queue_counts()/attention_by_step()/pending_total()/snapshot(); no new tables.
Added: backend/app.py: GET /api/refresh/queues — the standalone route so the sidebar badge can
  poll four sub-millisecond counts without recomputing the 27-step plan every minute.
Added: tools/refresh_status.py: --queues prints the queue table; --chain now also prints the
  plan's advisories.
Changed: backend/refresh.py: every step dict carries an `attention` list and the response
  carries `queues` + `queue_pending_total` (gate queues only), fed by a lazy, guarded import of
  queues.py — the dependency runs queues→refresh, never the reverse. A pending queue never
  changes a step's state: stale/blocked/fresh/unknown keep their Phase 1 meanings exactly, and
  a test asserts no step's state differs when queues are made unavailable.
Changed: backend/refresh_exec.py: plan_chain() returns `advisories` (one per pending gate queue
  blocking a runnable step, plus a kind='publish' entry when master_publish is runnable —
  inventory open question 4 answered as an advisory, not a gate). Display-only: /start and the
  409 path are untouched, so no queue can ever refuse a chain.
Added: gui_next DataFreshnessCard.tsx: "Waiting on you" panel below the trigger groups. Gate
  queues get a warn pill, their action line and a Review deep link; a clear gate stays visible
  muted with a check rather than disappearing, so an empty queue can be confirmed empty. The
  TapeMatch backlog renders as a ratio + thin bar with no pill and no colour. Steps a queue
  names get a quiet "⚑ N to review" marker after the state chip — deliberately not coloured
  like stale. Chain-preview advisories render above Confirm, which stays enabled.
  xref_filesets is display-only per tj: count and explanation, no Review button, and the card
  calls no /api/xref_ingest/ route.
Added: gui_next AppShell.tsx + lib/navigation.ts: NAV_QUEUE_BADGES maps gate queues onto the
  Library and Fingerprint nav items, polled every 60s. TapeMatch (backlog) and xref (no local
  resolution path) are deliberately unbadged.
Changed: gui_next ScreenLibrary.tsx: one-shot `?view=` search param (same consume-then-clear
  shape as `?lb=`) so /library?view=taperReview lands on the taper review filter.
Added: tests/test_queues.py (18 tests) + attention/advisory additions to test_refresh.py and
  test_refresh_exec.py. Locales: refresh.queues.* in all six files. Wiki: new
  docs/wiki/Pipeline-Refresh.md covering all four phases.
  Closes TODO-310; PIPELINE_REFRESH_PHASE4.md moved to instructions/complete/.

[2026-08-16] — feat(backend/gui): pipeline refresh Phase 3 — chained execution in dependency order
Added: backend/refresh_exec.py: StepExecutor + EXECUTORS registry tiering all 27 refresh.STEPS
  into 'inproc' (7), 'job' (5) and 'manual' (15, each with an honest one-line reason shown
  verbatim in the GUI); plan_chain() building an ordered chain for either scope — per-step
  "run this and everything it's blocked on" (transitive stale-ancestor walk; a blocked
  ancestor contributes its ancestors, not itself-as-work) or per-trigger "refresh every stale
  step in T1", pulling prerequisites across trigger boundaries; and run_chain_claimed(), the
  sequential chain runner under one _CHAIN JobState claim. Every executor callable resolves
  lazily inside its wrapper so concert_ranker/numpy and bs4/lxml stay out of backend startup.
  (TODO-308, spec instructions/PIPELINE_REFRESH_PHASE3.md)
Added: backend/db.py: refresh_chain_runs table (+ USER_TABLES, never exported in master) and
  record_chain_run(), one insert at completion through _run_queued_write. refresh_step_runs
  stays the authoritative freshness signal; this table is so "what did that chain actually
  do?" survives the restart D8 otherwise eats.
Added: backend/app.py: POST /api/olof/parse and POST /api/bobserve/parse — the two CLI-only
  parsers become routes, since they are the direct downstream of Phase 2's fetch buttons and
  a fetch that chains into a copyable <code> string is not a chain. Both 409 while their
  fetcher runs (parsing a half-written mirror yields a coverage summary that reads as data
  loss) and record their own refresh_step_runs row. Plus the five /api/refresh/chain/*
  routes (preview, start, status, stop, history); start re-plans server-side rather than
  trusting a posted plan, 409s on blocked_by_running or an existing claim, and returns
  noop when nothing is runnable.
Added: backend/scraper.py: plan_range() — the /api/scrape/start worklist builder extracted
  verbatim (private exclusion, sequential gap fill, sort) so a chain can plan a scrape with
  no Flask request context. The route now calls it and is otherwise unchanged.
Added: backend/activity.py: refresh_chain JobAdapter appended (append preserves the legacy
  busy_snapshot precedence order) with its lazy status wrapper and _PROGRESS_FIELDS entry;
  `current` carries the running step_id, so the status bar names the step.
Added: gui_next/.../components/DataFreshnessCard.tsx: per-trigger "Refresh Tn" header
  buttons, "Run chain" on every blocked row, and a preview dialog listing the ordered
  runnable steps with cost pills plus a "won't run" section carrying each manual step's
  reason — not collapsed when it is longer than the runnable list, because on this registry
  that list is the honest headline. Live done/total polling with a nested sub_progress bar
  for job-mode steps, Stop, and a one-line outcome. Phase 2's RUNNABLE map and RunControl
  are untouched. New refresh.chain.* + appShell.statusBar.activity.refresh_chain keys in all
  six locales.
Added: tools/refresh_status.py: --chain <step_id|Tn> prints the plan without running
  anything — the dry-run surface the GUI dialog is built on.
Fixed: backend/refresh.py: olof_parse's backlog_sql counted corpus IN ('dsn','chronicle')
  but the step only runs the DSN parser (olof_parser.run_parse selects WHERE corpus='dsn').
  One chronicle page — chronologies.htm, the year index, which has no year, so the chronicle
  parser will not take it either — sat in the backlog permanently, so olof_parse could never
  report fresh and song_index stayed blocked behind it forever. Under Phase 3 that also
  defeated the "a re-run is cheap" noop skip: every chain containing olof_parse would have
  re-run a 65-second full reparse for good. Scoped backlog_sql/last_run_sql to corpus='dsn'.
  Verified live: olof_parse now reads fresh, song_index moved blocked -> stale, and a second
  chain over olof_parse finished in under 3s with a 'noop' run record.

[2026-08-13] — feat(gui): sidebar nav visibility toggle + DB Editor cache-invalidation fix
Added: gui_next/src/renderer/src/lib/navVisibilityStore.ts: persisted zustand store
  (key lbb-nav-visibility) tracking hidden nav item ids. AboutDialog.tsx: new 5th
  "Options" tab listing every sidebar nav item, grouped/ordered as NAV_GROUPS, with a
  checkbox per item to hide it from the left panel; Home stays mandatory. AppShell.tsx:
  Sidebar filters each group's items against the hidden set and skips rendering a
  group's header entirely when every item in it is hidden. (TODO-307)
Fixed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: commitChanges() and
  deleteSelected() only called local loadRows() and never invalidated the
  library-catalog/collection-prefetch/library-badges react-query caches (staleTime:
  Infinity), so DB Editor row edits/deletes on any table (e.g. entries) never showed
  up on the Collection tab or sidebar count until app restart — only the alias
  add/delete flows invalidated collection-prefetch. Added a shared
  invalidateLibraryCaches() helper and call it from both. (BUG-322)

[2026-08-13] — feat(backend/gui): pipeline refresh Phase 2 — CLI-only steps become Run buttons
Added: backend/job_progress.py: JobState/JobStopped — one shared thread-safe progress dict,
  atomic try_begin() claim, and cooperative stop()/sleep() primitive for background pipeline
  jobs, modelled on backend/geocoder.py's inline pattern but reusable (and closing that
  pattern's check-then-set race across concurrent POSTs).
  backend/config_version.py: hashes the effective merged taper-alias config and two separate
  concert_ranker/config.py constant slices (extraction vs. banding/scoring) into meta, so
  config-only edits (spec Sec 1c's Phase 1 gap) stop reporting as "unknown" on the freshness
  card — refresh.py's version signal now takes precedence over backlog (a config change is
  stale even at backlog 0).
  backend/ranker_jobs.py: backend-side concert_ranker wrapper — plan_scan()/
  run_scan_claimed()/run_rerank(), chunked (4×workers) so Stop is honored mid-scan, always
  reranks after (including a partial/stopped scan). Reuses concert_ranker.cli's
  collection_worklist/rerank (promoted from _collection_worklist/_rerank, private aliases
  kept) instead of duplicating the non-concert/non-public exclusion logic.
  db.refresh_step_runs + db.record_step_run(): the first durable run-record any of these
  steps has ever had — one insert at completion (status ok/noop/stopped/error), closing the
  D8 backend-restart-loses-history gap and giving ranker_rerank (whose output table has no
  timestamp column) a real last_run for the first time.
  8 new routes in backend/app.py: POST/GET/POST {olof,bobserve}/fetch{,/status,/stop},
  ranker/scan{,/status,/stop}, POST ranker/rerank. Ungated (same rationale as
  /api/geocode/run); ranker/scan defaults to backlog-only, a full rescan needs an explicit
  {mode:'all'} plus a GUI confirm.
Changed: backend/olof_fetcher.py, backend/bobserve_fetcher.py: retrofit for stop/progress —
  run_fetch() now claims via JobState (raises if already running), run_fetch_claimed() is
  the route's thread target, every time.sleep() in the discovery/fetch loops and the 429/
  retry backoff is now an interruptible JobState.sleep() (stop honored within ~1s instead
  of up to 30s; an in-flight requests.get(timeout=30) is the one exception, documented).
  backend/refresh.py: _last_run_record() merges refresh_step_runs into last_run (the newer
  of watermark vs. newest successful run-record) with a new last_run_source field;
  _step_state() gains keyword-only version_state/last_run_status/last_run_source args and a
  new precedence (config changed > backlog > last-run-failed > blocked > watermark >
  unknown/fresh); olof_fetch/bobserve_fetch/ranker_scan/ranker_rerank/attribute_tapers
  registry entries get real how_to_run routes + version_key; ranker_scan's backlog_sql is
  rescoped to the latest scan_id so the card's number matches the route's planned count.
  backend/activity.py: three JobAdapter rows (olof_fetching, bobserve_fetching,
  ranker_scanning) appended, screen_route="/" since the freshness card is these jobs' only
  UI. run_backend.py: multiprocessing.freeze_support() as main()'s first statement (a
  packaged build's frozen scan would otherwise re-launch the exe instead of a Pool worker).
  concert_ranker/cli.py: _collection_worklist/_rerank promoted to public
  collection_worklist/rerank (private aliases kept) so backend/ranker_jobs.py isn't reaching
  into underscore names.
  gui_next/.../DataFreshnessCard.tsx: the four wrapped steps get a real "Run" button (a
  RUNNABLE map) — fetchers get a single ConfirmDialog naming the politeness delay,
  ranker_scan gets a two-option dialog (Scan backlog (N) / Full rescan with a danger-toned
  warning), a running job polls its status route every 2s with a Stop button, ranker_rerank
  (synchronous) awaits its POST directly; every other row keeps the Phase 1 copyable-
  text/nav-button behaviour untouched. version.state=='changed' appends a tooltip hint.
  tools/refresh_status.py: new VER column (ok/chg/—).
Added: gui_next/src/renderer/src/locales/*.json: refresh.{run,stop,running,alreadyRunning,
  runFailed,confirmFetch,confirmFetchBody,confirmScanTitle,scanBacklog,scanAll,
  scanAllWarning,scanNoBacklog,versionChanged} + appShell.statusBar.activity.
  {olof_fetching,bobserve_fetching,ranker_scanning}, translated de/fr/es/it/nl via
  /gui-next-i18n.
Closes: TODO-306.

[2026-08-13] — feat(gui): DB Editor edits long-text columns in a textarea
Changed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: the inline cell editor was
  a single-line <input>, so pasting a multi-line value (a setlist, a source chain) into a
  cell collapsed it to one line — the blocker for filling private-LB metadata (entries rows
  with status='private' / metadata_source='private_import') by copy-paste from an external
  source. Columns in the new LONG_TEXT_COLUMNS set (setlist, description, source_chain,
  timing, note/notes, comment) now open an 8-row resizable <textarea> that preserves
  newlines; in it Enter inserts a newline and Ctrl/Cmd+Enter commits, while every other
  column keeps the old input with Enter-to-commit. Esc still cancels in both. The editing
  cell drops its nowrap/max-width clamp while a textarea is open. No backend change — the
  existing /api/dbedit/table/entries/row PATCH already round-trips multi-line values.
Added: gui_next/src/renderer/src/locales/*.json: dbeditor.edit.multilineHint (the textarea
  tooltip), translated de/fr/es/it/nl via /gui-next-i18n.

[2026-08-12] — feat(backend/gui): pipeline refresh Phase 1 — the freshness planner
Added: instructions/PIPELINE_REFRESH_INVENTORY.md, instructions/PIPELINE_REFRESH_PHASE1.md:
  a 57-step inventory of everything needed to bring the app up to date (four triggers
  T1–T4, the dependency DAG, disjoints D1–D8), and the Phase 1 spec built on it. The
  inventory's key finding: there is no staleness *ledger*, but the underlying signal
  already exists in the tables — most derived tables carry a computed_at/parsed_at/
  imported_at/fetched_at stamp that is written today and read by nothing. Phase 1 is
  therefore "read the ledger that already exists", not "build one": no schema, no writes,
  no existing code path changed.
Added: backend/refresh.py: the registry + planner. 27 declarative RefreshStep rows
  (modeled on activity.py's JOB_ADAPTERS, same "observe, never own" rule) each declaring
  a trigger, a kind, its upstream step_ids (the DAG written down once — fixes D3 for read
  purposes), a display-only how_to_run, and one or more signals. State is the most severe
  result across signals: a **backlog** count where one is computable, falling back to an
  upstream **watermark** comparison only when no backlog signal exists — so backlog=0 is
  never overridden by a newer upstream stamp, which is the alert-fatigue false positive
  that would have made the card ignorable. compute_plan() evaluates in topological order
  so a step downstream of a stale one reports `blocked` naming the culprit rather than
  double-reporting the symptom.
Added: backend/refresh.py `_parse_ts()`: the one timestamp normalizer. olof_pages is the
  lone ISO-'T' writer (861 rows) while every other stamp column is space-separated, and
  'T' (0x54) sorts after ' ' (0x20), so naive string comparison inverts within a single
  day — and olof parse → song_index is exactly such a cross-format comparison, i.e. a live
  bug rather than a hypothetical. Every comparison in the module goes through _parse_ts();
  none happen in SQL across tables. meta.master_published_at is additionally tz-aware UTC
  while everything else is naive local, so tz-aware values are converted to local and
  stripped before comparing.
Added: backend/app.py: GET /api/refresh/status — thin read-only wrapper over compute_plan(),
  registered beside /api/lb/coverage, optional ?trigger=T1 filter narrowing steps and counts.
  No curator gate; a missing table degrades that step to `unknown` rather than raising.
Added: backend/refresh.py `_publish_lag()`: the D7 fix — publishing was the only trigger
  whose neglect was invisible locally, because the cost lands on other installations. Counts
  are taken from lb_status_history (real status *transitions*) rather than
  lb_master.last_status_at, which a full reconcile re-stamps on every row and would have
  reported the entire 16,703-row catalogue as "changed" the day after any rebuild; the honest
  live figure is 260 transitions + 252 entries scraped since the 2026-07-14 publish.
Added: tools/refresh_status.py: single-line-per-row CLI report (--trigger, --stale-only,
  --json, --db, --exit-nonzero-if-stale for later cron use; exit 0 by default since it is a
  report, not a gate).
Added: gui_next/.../components/DataFreshnessCard.tsx, screens/ScreenHome.tsx: a Home card,
  not a new screen — following the ScreenGaps→Library-rows precedent (TODO-270) rather than
  proliferating screens. Stale/blocked rows grouped by trigger with age, backlog and the
  how_to_run string; publish lag called out separately; a muted footnote counts the steps
  with no freshness signal. Nothing new becomes executable: route steps that map to an
  existing screen get a "Go to screen" link, everything else is copyable text (Phase 2 turns
  those into buttons). The card hides itself entirely when the route is absent or errors, so
  older installs see nothing rather than an error banner.
Added: tests/test_refresh.py (25 tests): _step_state truth table including the
  backlog-beats-watermark false-positive guard and blocked-over-stale precedence; _parse_ts
  cross-format regression asserting the ISO-'T'-vs-space inversion both ways; every registry
  backlog_sql/last_run_sql executes against a real init_db schema with the right arity (the
  guard that catches a renamed column the day it is renamed instead of silently reporting
  `unknown` forever); DAG integrity and cycle detection; missing-table → unknown, no raise.
Known gaps, reported honestly as `unknown` rather than guessed: xref ingest, attachments
  reconcile, mirror crawl, WTRF, bootlegs, site-data publish, preservation, archive.org have
  no queryable local signal; ranker rerank has a backlog but no timestamp column anywhere, so
  its watermark is reported as unavailable rather than inferred. Config-only inputs (spec §1c:
  _KNOWN_TAPER_ALIASES, concert_ranker config, TapeMatch thresholds) move no timestamp at all;
  a `version` signal for them is a write, so it belongs to Phase 2 (TODO-306).
Changed: PROJECT.md: + backend/refresh.py and tests/test_refresh.py structure rows,
  GET /api/refresh/status route reference, DataFreshnessCard on the ScreenHome row.

[2026-08-12] — feat(backend/gui): "Complete against LB" coverage award screen + BUG-321 gap-definition reconciliation
Added: backend/lb_coverage.py, backend/app.py: GET /api/lb/coverage — a read-only
  snapshot/coverage/stats payload (LB master label + version, entries_total/held/missing,
  coverage_pct, per-decade held/total, recordings, families, a deterministic sorted
  recording_families ledger_sha256, first_entry_filed_at/days_active). Every query is guarded by
  a sqlite_master table check so a fresh or partial DB returns a zeroed payload instead of 500ing.
Added: gui_next/.../screens/ScreenCoverage.tsx, App.tsx, components/AboutDialog.tsx,
  lib/tokens.ts, index.css: the /about/coverage progress screen from
  instructions/design_handoff_lb_coverage_award — one component whose award treatment is a state,
  not a separate screen, with a client-side canvas certificate renderer + export modal. Reached
  from the About dialog's "Collection progress" row, deliberately not a sidebar destination, but a
  real deep-linkable route so the milestone survives a reload. The award gold is a fixed per-mode
  ramp (--lbb-award-{mid,hi,lo,soft,on}) rather than an accent, so the milestone reads identically
  under all eight accents and both frame palettes.
Fixed: backend/lb_coverage.py, backend/db.py: BUG-321 — the coverage screen reported 92 missing
  entries (99.5%) while the Collection screen's "Not in collection" chip showed 0 rows off the
  same DB. Two independent definitions of "gap": coverage counted held LBs with a plain
  my_collection join and excluded lb_status 'missing' from the denominator, while
  get_missing_from_collection folded lb_alias twins but also required entries.status='ok'. Of the
  92: 57 were owned via an alias twin (coverage wrong), 32 were entries.status='private' and 3
  entries.status='missing' (the list wrong — its public/private chips could never show a private
  row). New _held_sql() folds lb_alias in either direction for both entries_held and the
  by_decade rollup and degrades to the direct test when lb_alias is absent;
  _HELD_EXCLUDED_STATUSES narrowed to ('nonexistent',) since 'missing' (tape exists, LB page
  gone) is a fillable gap already pinned by tests/test_db_writes.py; the entries.status='ok'
  filter is gone. Both surfaces now report 35 gaps / 99.79% against live data (all 35 private —
  4 with metadata, 31 stripped). Full suite 1200 passed; /gui-check clean.
Added: tests/test_lb_coverage.py: payload-contract, by_decade bucketing, ledger-hash determinism,
  fresh-DB zeroing, and an alias-folding regression test.
Changed: backend/forum_poster.py, backend/app.py, gui_next/.../ScreenCollection.tsx: forum posts
  now carry a SHARE_EMBARGO_NOTICE line under the metadata banner, and the pre-post integrity
  gate distinguishes 'fail' (checksum mismatch — never skippable, BUG-120) from 'incomplete'
  (fewer files than the sidecar lists, which can be a stale sidecar); the latter returns
  skippable:true and the forum modal offers a "post anyway" checkbox that sets
  skip_integrity_check.
Added: TODO-304 (translate the ~60 new coverage/About locale keys — en.json only so far),
  TODO-305 (the handoff's /lbdir/ledger and /lbdir/sync routes are unbuilt; spec stays in
  instructions/).

[2026-08-10] — fix(gui): BUG-319 — "Not in collection" rows get right-click + a detail pane
Fixed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: the not-owned view was a
  dead-end list — rows carried only onDoubleClick (Quick Lookup), and both the grid's
  `gridTemplateColumns` and the RecordingDetailPanel render condition explicitly excluded
  `notOwned`, so nothing could be selected or inspected. Rows now select (`missingSelectedId`,
  click toggles), right-click opens the shared Library action menu built by
  `buildRecordingActions` with `owned: false` — Open LB page / Copy LB number / Add to wishlist —
  and the selection mounts the same `RecordingDetailPanel` the Library and owned-collection views
  use, with no Collection tab (there is no copy to manage). `missingDetailRow` prefers the catalog
  row from `libRowByLb` (source/description/picks/taper badges) and falls back to a row synthesized
  from the missing-LB payload; it resolves against `filteredMissingRows`, so flipping the
  public/private chip drops a selection that left the list. Verified with the driver against live
  data (Tier A; Tier B is down — BUG-320): selected row renders the panel with the Not owned /
  Public / pick badges and an Add to wishlist primary, right-click renders the 3-item acquire menu.
Added: BUGS.md: BUG-320 — electron_driver Tier B (--electron) dies with playwright
  "Process failed to launch!" right after Xvfb comes up; Tier A unaffected.

[2026-08-10] — feat(gui): TapeMatch triage-rail query field + year brush + windowed list
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx: implemented the
  design_handoff_tapematch_rail_filter add-on for the §2 triage-queue rail. `parseQueryTokens`
  classifies whitespace-separated tokens (status word, year, decade, 2-digit year, date prefix,
  month/day, free text) and ANDs across classes, ORs within one; a pointer-driven year-brush
  histogram (total + needs-you segments, computed from the status-chip+query-staged set, not the
  final range-scoped one) with decade chips scopes the list to a year range; the rail is now
  year-grouped and windowed (fixed 46px row / 26px header, precomputed offset table, binary-search
  visible slice with 8-item overscan) so it stays responsive at the real ~3,195-date crawl index
  instead of the four-chip original. `/` focuses the query field, `↑`/`↓` move the cursor without
  leaving it, `esc` clears then blurs; cursor auto-scroll now seeks the offset table directly since
  the target row may not be mounted. Verified against live data (backend on :5174, `/verify
  --renderer-only`): grammar, decade chips, brush dimming and the windowed list all behaved as
  spec'd. TODO-275 (i18n) description updated — the add-on's new strings add to that debt.
Changed: instructions/README.md, instructions/complete/design_handoff_tapematch_rail_filter/: spec
  moved to complete/, indexed.

[2026-08-09] — fix(gui/backend): BUG-317/BUG-318 — dossier PDF export, and cross-reference links that 404'd
Fixed: gui_next/src/renderer/src/components/library/DossierExportModal.tsx: choosing PDF saved an
  HTML file. The URL handed to window.api.printDossierPdf omitted inline=1, so the response carried
  `Content-Disposition: attachment` — the hidden print window treated the navigation as a download
  (loadURL rejects ERR_FAILED, printToPDF never runs) and Electron's default download handler wrote
  dossier-<date>.html. The print URL now sets inline=1; verified as a 4-page PDF.
Fixed: backend/dossier.py: the Olof cross-reference card 404'd on every 2022+ show. Those shows are
  ingested from bobserve's own setlist database and their olof_events.page_filename is the synthetic
  local name of the scraped page ('bobserve_event_<id>.html'), which does not exist on the Olof
  mirror. _bobserve_event_id() now recognises it: the Bobserve card deep-links
  bobserve.com/setlist?event=<id> (instead of the year index) and is flagged `is_source`, and the
  Olof card falls back to the chronicle index rather than fabricating a mirror link. DSN-era shows
  are unchanged — they still deep-link the exact mirror page ingested.
Changed: backend/templates/dossier.html: the context/setlist/footer credits follow the `is_source`
  card, so a bobserve-sourced show is credited to Bobserve instead of attributing its setlist to
  Olof Björner. The xref card's host label is derived from the link actually emitted rather than the
  source's home page, which had it advertising bjorner.com for a bobserve.com URL.
Added: tests/test_dossier.py: TestXrefDeepLinks — DSN page deep-links the Olof mirror, bobserve page
  deep-links bobserve and leaves the Olof card on the chronicle index.

[2026-08-09] — feat(gui): My Collection now uses the Library's recording detail panel
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: selecting a row opened a
  screen-local detail panel with a different layout and a different feature set than the one the
  Library screen shows for the same recording. It now mounts the shared RecordingDetailPanel —
  same identity block, Overview/Picks/Taper/Olof/Assets/Seed & Share/Quality tabs, checksums and
  action bar — so both screens describe a recording identically. The panel is fed the catalog row
  when the LB is in it (it carries source/description/pick/taper data the collection payload
  lacks) and falls back to the collection row otherwise.
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: `extraTabs` / `renderExtraTab`
  props on RecordingDetailPanel — a host screen can append its own tabs.
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx: a "Collection" tab (via the above)
  holding everything the shared panel has no place for and that would otherwise have been lost:
  disk path / size / discs, audio-format and linked-LB pills, personal rating + listen count with
  Log listen / Edit personal info, and the per-record torrent and forum management (qBittorrent
  add/remove, regenerate, relocate, delete file, delete record, open post, delete post).
Added: gui_next/src/renderer/src/lib/useLibraryActions.tsx: the ActionHandlers bag and its overlay
  UI (context menu, toast, confirm, dossier modal), extracted verbatim from ScreenLibrary.tsx so
  both screens drive the panel through one implementation instead of two.
Added: gui_next/src/renderer/src/lib/libraryPanelData.ts: useLibraryHistoryMap / useAttachCountMap,
  the two lb_number-keyed panel side-data maps, extracted for the same reason. Both reuse the
  react-query keys the screens already share, so the second consumer costs no extra fetch.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: consumes the two new modules; ~330
  lines of handler/overlay code removed with no behavior change.
Changed: gui_next/src/renderer/src/locales/*.json: new collection.detail.discs and
  collection.detail.tabCollection keys, translated for de/fr/es/it/nl.

[2026-08-09] — fix(backend): BUG-316 — a "nonexistent" LB override now applies and hides the LB
Fixed: backend/app.py: PUT /api/lb_master/<lb>/manual rejected status="nonexistent" with a 400 even
  though the DB Editor's override modal offers it and lb_master's CHECK constraint allows it. Both
  that route and the GET /api/lb_master status filter now accept it.
Fixed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: addOverride() read the JSON response
  but never inspected it, so the 400 above rendered as a success toast and the override looked
  applied when it had not been. It now throws on an error body.
Fixed: backend/db.py: get_missing_from_collection() joined lb_master only to display lb_status and
  had no filter on it, so an LB confirmed never to have existed stayed in the Collection screen's
  Missing-LBs list forever. It now excludes 'nonexistent' rows, matching the same exclusion in
  gap_analysis.py and timeline.py. 'missing' rows are still listed — the tape exists, the page is
  gone, so it remains a real gap.
Added: tests/test_db_writes.py: TestMissingFromCollection — three tests pinning that an unowned
  entry is listed, a 'nonexistent' override hides it, and a 'missing' override does not.
Changed: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: the alias panel's table scrolls
  within a 220px max-height with a sticky header row (uncommitted from the prior session).

[2026-08-09] — fix(gui): Verify stage shows full md5/ffp digests instead of 12-char stubs
Fixed: gui_next/src/renderer/src/components/pipeline/VerifyDetail.tsx: the expected/actual md5 and
  ffp columns rendered `hash.slice(0, 12) + '…'`, so a mismatch could not actually be compared by
  eye — the differing bytes are usually past character 12. All four digest columns now print the
  complete hash. The cells override TD's nowrap/ellipsis clipping (wrap + break-all) so no
  character is lost at any density or font-size setting, the columns widened 130→180px, and the
  table sits in a horizontal-scroll wrapper with a 1150px min-width so narrow panels scroll rather
  than squeeze the digests. Digest headers/cells are left-aligned now that they wrap.

[2026-08-08] — fix(backend): BUG-315 — an LB override now takes the lbdir manifest with it
Fixed: backend/app.py: _find_lbdir_in_folder() took the first lbdir*.txt in the folder whatever
  LB it belonged to, so after "Override LB#" / "Pin & continue" the LBDIR stage kept verifying
  against the manifest the *previous* match had copied in (and /api/lbdir/retrieve answered
  "already_present" instead of fetching the right one). It now takes the resolved LB and accepts
  only that LB's manifest (LBF-NNNNN- prefix, or its canonical when the pin is an alias) or an
  untagged folder-supplied lbdir.txt; another LB's manifest is ignored so the correct one is
  retrieved. All five call sites (pipeline LBDIR step + prefetch trigger, /api/lbdir/check,
  retrieve, reconcile, find_extra) pass the pinned/resolved LB.
Changed: backend/app.py: same-day follow-up — the first cut rejected another LB's manifest
  outright, which stopped double-LB folders (pinned to the entry that has no lbdir attachment of
  its own, e.g. LB-03043 of the 2986/3043 pair) from checking against the sibling's manifest at
  all. Rejection is now the `strict=True` mode, used only where the question is "must I retrieve
  this LB's manifest?" (pipeline fetch decision, /api/lbdir/retrieve); everywhere else a
  mismatched manifest is the last-resort fallback, and the pipeline no longer parks on
  "Fetching LBDIR…" when it has a manifest it could verify against.
Added: tests/test_lbdir_manifest_scope.py — 9 cases pinning the selector: this LB's manifest wins,
  untagged accepted, alias→canonical accepted, other-LB manifest invisible to strict callers but
  usable as a fallback.

[2026-08-08] — feat(gui): "Send to LosslessBob pipeline" right-click action for Nemo
Added: tools/nemo/ — a Cinnamon/Nemo action that queues one or MORE selected folders on the
  Pipeline screen. Transport is a drop file in ~/.local/share/losslessbob/pipeline-inbox/, not
  argv or a single-instance lock: in dev the app is started by `npm run dev`, whose argv the
  launcher owns, and a drop written before the app exists still survives a cold start.
  install-nemo-action.sh substitutes the repo path into the .nemo_action and installs it.
Added: gui_next/src/main/index.ts watches that inbox (150ms debounce — a drop fires several
  fs events, and the sender renames the file into place so a half-written list is never read),
  drains it at startup, focuses the window, and writes ~/.local/share/losslessbob/gui.pid so the
  sender can tell a running app from a cold one. Batches that land before the renderer mounts are
  buffered and handed over by the new pipeline:consumePending IPC; later ones push on
  pipeline:folders. Renderer side: App.tsx PipelineInbox adds the paths to the folder queue and
  navigates to /pipeline. No new user-facing strings, so no locale work.
Note: the sender prefers `npm run dev` over gui_next/dist/*.AppImage — that dist build is months
  old, and silently starting it instead of the working tree looks like the app losing its changes.

[2026-08-08] — feat(backend): TODO-303 — search whole shows, and re-gate the confidence rule
Added: backend/bobtalk.windows_from_utterances + tools/bobtalk_locate.py --full-show (now the
  DEFAULT; --boundaries keeps the old pass). The first corpus run located 998 of 3,301 quotes with
  one window per track split, but boundary windows hear only about a fifth of a show, so quotes
  spoken away from a split were unreachable at any threshold. A full-show decode is now cut into
  overlapping 80s/40s windows at MATCH time, not decode time — the cache holds raw utterances, so
  re-cutting or re-tokenising costs a --rescore rather than a re-decode.
Changed: the confidence rule is now geometry-dependent (backend.bobtalk.gate_for, one knob so the
  invalid combinations cannot be built). Measured on 8 recordings / 36 quotes decoded under BOTH
  geometries: boundary + the shipped best-vs-runner-up rule located 7, full-show + the same rule 7,
  full-show + MIN_DICE alone 14 (10 of them right, by reading the ASR text against Olof's line).
  MIN_RATIO does not survive the geometry change: the runner-up is a MAXIMUM over the noise draws,
  so ~160 sliding windows inflate it far above what ~25 disjoint boundary windows produced, and the
  3-6x separation it was calibrated on collapses to 1.1-1.7x for visibly correct matches.
  Percentile-of-bulk variants do not rescue it — p90 accepted 14 of 14 (a bare threshold in
  disguise), p96 13, p98 10. So GEOM_FULL drops the ratio gate and raises the floor instead
  (MIN_DICE_FULL 0.40; the sample keeps 9, 7 right), accepting a real false-positive rate — a play
  button on the wrong 80 seconds — for double the yield. tj's call. Known failure mode: LONG quotes
  (band intros, tour stories) whose token set cannot fit an 80s window score low and drift onto song
  lyrics. runner_up is still computed and stored under a separation radius, as provenance for
  re-gating from cache later.
Added: bobtalk_locations.geometry, backfilled to 'boundaries' for every pre-existing row, and part
  of the corpus runner's resume key — otherwise rows from the weaker pass make a full-show run skip
  the recording and the upgrade silently covers nothing. The decode cache keys full-show under a
  (-1,-1) sentinel geometry, so both passes of one recording coexist.
Changed: the empty-decode guard now also fires when a full-show decode returns ZERO utterances —
  under that geometry a silent decoder failure has no textless windows to be caught by.
Changed: gui_next DetailPanel bobtalk rows — play is now play/pause with a stop button that rewinds
  without discarding the cut clip. Locale keys in all 6 languages.
Measured: full-show ASR costs ~65x realtime on the RTX 3080 (92 s for a 100-minute show), NOT the
  ~600x quoted from the tapematch §3 experiment. One best source per date is therefore ~20-25 h of
  GPU time, not the ~15 h estimated for the boundary pass.

[2026-08-07] — feat(backend): TODO-303 — cache ASR decodes, and run them on the GPU
Added: backend/bobtalk_decodes.py + data/bobtalk_decodes.db — the decoded window TEXT is now kept,
  so re-scoring costs no CPU. bobtalk_locations still stores only a timestamp; this is a separate,
  derived, discardable database (the fingerprints.db precedent) precisely so it can be thrown away
  once MIN_DICE/MIN_RATIO settle, without touching the main DB or its backups. Two tables keyed on
  (lb_number, model, compute_type, pre_sec, post_sec): changing a threshold or content_tokens now
  re-scores from cache, while changing the model, quantisation or window geometry misses and
  re-decodes, because those genuinely change what was heard. device is recorded but deliberately
  NOT in the key — a CPU and GPU pass at the same quantisation should share an entry. A run row
  whose window count disagrees with the stored windows reads as a miss, so a decode killed halfway
  cannot be served as a complete one. Sizing: ~10 KB/recording, so a full corpus run is ~30-50 MB.
Added: tools/bobtalk_locate.py --rescore (re-score from cache, never runs ASR — 0.3 s vs 67 s, and
  needs no audio on disk), --cache-summary, --prune-cache [MODEL], --device, --compute-type.
Changed: the locate pass now runs on CUDA by default. config.yaml's asr block pins device: cpu for
  the tapematch batch signal; this is a different workload (large-v3, on demand) so it picks its own
  device rather than inheriting that. On the RTX 3080, large-v3 float16 decodes LB-00212's 29
  windows in 31 s against 443 s on CPU int8 — ~14x, and end-to-end per recording drops 7.5 min ->
  67 s, now dominated by SHN->PCM ingest rather than Whisper. Corpus scope re-estimates: all 3,275
  recordings ~61 h (was ~400 h), one best source per date ~15 h (was ~95 h).
Fixed: BUG-314 — a failed CUDA decode silently overwrote good locations with none. CTranslate2
  links cuBLAS at first use rather than at load, and asr.transcribe_gaps swallows per-window
  failures by design, so a missing libcublas.so.12 turned a 154-minute show into 29 empty windows
  and a clean exit 0 — which cached the emptiness and replaced LB-00212's 6/10 stored locations
  with 0/10. Same silent-failure shape as the vad_filter bug in TODO-293. Guarded three ways:
  detect_device() dlopens cuBLAS/cuDNN and falls back to CPU unless they load; decode_windows()
  raises when no window yielded any text; load_windows() refuses to serve a textless entry, so
  poison written before the write-side guard existed cannot leak. Rows restored.
Changed: requirements.txt — nvidia-cublas-cu12==12.9.1.4, nvidia-cudnn-cu12==9.13.1.26, OPTIONAL
  and GPU-only (~1.2 GB). Omit them and the pass runs ~14x slower but correctly. pip needs scratch
  space on a large filesystem; /tmp here is 1.8 GB, so TMPDIR=~/.cache/pip-tmp.
Note: float16 located 5/10 quotes where CPU int8 located 6/10. Not a method regression — the four
  strong matches (0.81, 0.78, 0.70, 0.60) are identical on both, and the difference is entirely in
  quotes sitting on the separation rule: two scored 0.37 at 1.85x and 1.95x runner-up, just under
  MIN_RATIO 2.0, where int8 had put one of them at 3.1x. This is why compute_type is in the key.
Tests: 23 new in tests/test_bobtalk_decodes.py (key isolation per model/quantisation/geometry,
  device-not-in-key, partial and textless decodes reading as misses, the legacy-table drop, prune
  filters, and the guard that a wholly empty decode raises rather than caching). 43 pass across
  test_bobtalk_decodes.py + test_bobtalk.py; ruff clean.
Remaining for TODO-303: still the corpus-run scope decision, now much cheaper — see the figures
  above.

[2026-08-07] — feat(gui): TODO-303 GUI — play buttons for located bobtalk quotes
Added: BobtalkZone + BobtalkQuoteRow in the Library DetailPanel's existing Olof tab. Reads
  GET /api/bobtalk/<lb> and renders each located quote with a play button; clicking it POSTs to
  /api/bobtalk/clip, which cuts the clip on demand, and plays it through a hidden <audio> element
  (same pattern as the TapeMatch A/B player). The zone renders nothing at all when no quotes are
  located, so a recording that has not been through the locate pass shows no empty shell.
Design: the renderer deliberately does NOT re-split ev.bobtalk to attach buttons inline. quote_index
  is assigned by backend.bobtalk's parser, and a second implementation in TypeScript would drift and
  hang play buttons on the wrong lines. The API already returns each located quote's text, so the
  zone renders that; the full block still shows above it in OlofEventCard. Since only about half of
  an event's quotes typically locate, a quote without a button is the normal case, not a defect.
Added: library.bobtalk.{label,playAt,clipFailed} in en.json, translated to de/fr/es/it/nl via DeepL
  (4,983 chars; {{clock}} placeholders preserved).
Verified: gui-check PASS — node types 0 errors, renderer types 0 errors, production build clean.
  Locate pass re-run on LB-00212 after the parser fix: 6 of 10 quotes located (was 3 of 6), the
  recovered quote now the strongest match in the show at 0.81 vs 0.14. The separation rule behaved
  exactly as designed on two quotes that both scored 0.37 — one passed at 3.1x its runner-up, the
  other failed at 1.5x.
Remaining for TODO-303: decide the corpus-wide run scope (3,275 recordings at ~7 min each is ~400
  single-stream hours; one best source per date is ~95 h and still covers every show).

[2026-08-07] — feat(backend): TODO-303 backend — locate Olof's bobtalk in our audio
Added: backend/bobtalk.py. Parses an olof_events.bobtalk block into matchable quotes (dropping the
  catalogue/release lines that bleed into that field), scores each quote against decoded audio
  windows by Dice overlap, and decides confidence by SEPARATION rather than magnitude: a match must
  clear MIN_DICE 0.30 *and* beat the runner-up window by MIN_RATIO 2.0. That rule comes straight
  from the PoC, where every true match beat its runner-up 3-6x while every failure tied it. No ASR
  dependency by design — it takes token sets, so the logic is unit-testable without faster-whisper.
Added: bobtalk_locations table (lb_number, event_id, quote_index, t_start, dice, runner_up,
  confident, model), idempotent CREATE + PRAGMA-checked ALTER. Stores a REFERENCE, never the text:
  quote_index indexes into the olof_events block, which is joined back at read time, so the row is
  a timestamp and edits to Olof's text flow through. A re-run replaces a recording's rows rather
  than appending, so re-locating with a better model leaves no stale timestamps.
Added: tools/bobtalk_locate.py — the ASR half. Decodes one window around EVERY track boundary and
  lets each quote pick its own; it deliberately does not infer the window from setlist position,
  which drifts and failed in both directions on the PoC. Requires large-v3 + vad_filter:False.
Added: GET /api/bobtalk/<lb> (low-confidence matches excluded unless ?all=1, so an unresolved match
  degrades to "no play button" rather than one that jumps to the wrong moment) and
  POST /api/bobtalk/clip, which reuses the existing A/B clip cache and its range-capable
  /api/ab_clip/<file> serving route.
Fixed: backend/ab_clips.py — _ffprobe_duration now falls back to a decode-to-null probe when the
  container reports no duration. SHN carries no frame-count header, so every .shn track previously
  measured 0.0s, which made every offset look out of range. FLAC always reports duration and never
  reaches the new path. Also generalised folder_flac_durations into folder_audio_durations(glob)
  so non-FLAC folders are reachable; the FLAC entry point is unchanged and delegates.
Note: bobtalk playback resolves tracks through tapematch's ingest.list_tracks ordering (rglob,
  directories first, natural sort within name). A stored t_start is an offset into that exact
  concatenation, and plain glob would miss d1/-style disc layouts entirely.
Tests: 18 new in tests/test_bobtalk.py (parsing, metadata-bleed rejection, the separation rule,
  tie-means-not-confident, re-save replacement, reference-not-copy semantics). Full backend suite
  1,144 passed. Verified live: clip extraction from a .shn folder produced a playable WAV.
Remaining for TODO-303: the GUI half (render the bobtalk block with a per-quote play button) and
  a decision on how widely to run the locate pass.

[2026-08-07] — docs: file TODO-303, locate Olof's bobtalk in our audio (PoC passed)
Added: TODO-303. tj's idea, and it inverts TODO-293's failed approach — stop asking ASR to PRODUCE
  transcripts, use Olof's curated bobtalk as the target and use ASR only to LOCATE it. Fuzzy-matching
  a garbled decode against a KNOWN string is far easier than open transcription, so large-v3's
  fidelity ceiling stops mattering, and the stored artifact is a timestamp rather than a transcript.
Data: olof_events.bobtalk populated for 859 events (median 538 chars), 674 of them in the 70s-90s;
  812 of 826 bobtalk dates have audio on disk (3,275 source recordings); 766/859 also have
  olof_songs setlist rows; positional cues present (606 'before', 436 'after', 198 'introduction',
  542 naming a known song). Also found 18 bobtalk sidecar files inside collection folders.
PoC: 1978-12-16 Hollywood Sportatorium (ev5020 / LB-00212, 154 min, 29 tracks == 29 songs). Decode a
  window at EVERY track boundary once, then argmax Dice per quote via asr.content_tokens. 5 of 10
  quotes located confidently, 2 marginal, 3 no-match — and every confident match beats its runner-up
  by 3-6x while every failure ties its runner-up, so best-vs-second-best is a self-calibrating
  confidence rule needing no threshold. 443s per source (8 threads, batch running concurrently).
Learned: do NOT infer the boundary from setlist position — track/setlist mapping drifts and guessing
  failed in both directions (an after-cue correction moved one quote 0.49 -> 0.06); scan all
  boundaries. Track filenames are numeric, so title->filename matching is impossible. Needs
  large-v3 + vad_filter:False. No production code changed; throwaway scripts removed.

[2026-08-07] — docs(scraper): TODO-293 — era hypothesis rejected; ASR failures are model-size artifacts
Rejected: the "talkative era" hypothesis. Re-ran full-show ASR on 1979-11-01 Warfield (gospel tour,
  the most talkative era in the collection) with vad_filter off. Utterance density is 0.110/sec vs
  0.107/sec for 2003-04-18 — indistinguishable. VAD on/off is a ~58x effect (0.0019/sec); era is not
  measurable beside it. The apparent "50 min of speech per gospel show" is an artifact: with VAD off
  Whisper transcribes sung material too, so it measures vocal fraction, not stage talk.
Found: vad_filter:False alone is NOT the fix — it trades a silent failure for a noisy one. 330 of
  653 full-show utterances unique; output dominated by Whisper repetition loops on music.
  Restricting ASR to find_banter_gaps windows does not rescue it (energy-quiet windows still contain
  music): 27 windows/2193s gave 0 utts with VAD on, 207 utts at 78 unique with VAD off.
Found: both failures are substantially model-size artifacts. On 6 gospel windows (476s), VAD off —
  base 59 segs/27 unique (46%, 8s); large-v3 44/36 (82%, 92s); large-v3 + anti-loop params 46/40
  (87%, 95s). Anti-loop = compression_ratio_threshold 2.0 / repetition_penalty 1.15 /
  no_repeat_ngram_size 3, all supported by faster-whisper and NONE currently set by
  asr.transcribe_gaps. Fidelity improves only partly: on the controlled 2003-05-11 announcer intro,
  large-v3 recovers the most identifying line correctly where base garbled it, but the middle of the
  same announcement is still wrong — and wrong more dangerously, since base emits obvious garbage
  while large-v3 emits fluent confident errors.
Cost: large-v3/int8 ~5-6x realtime on 8 threads (~17-20 min per 100-min show); ~1,100 single-stream
  hours across all 3,924 runs, so a library-wide pass must be selective or parallel.
Bearing: none of this rescues the §3 pair signal (still no non-boilerplate positive). It does
  establish transcripts as viable for stage-banter DOCUMENTATION (curated, timestamped back into the
  audio) and NOT viable for detecting lyric variation, where a confidently mis-decoded word is
  indistinguishable from a real change. No code or config changed; findings in CALIBRATION_PROGRESS.md.

[2026-08-07] — docs(scraper): TODO-293 — full-show ASR experiment; coverage is not the limiter, VAD is
Measured: transcribed all five 2003-05-11 sources end to end (one window = whole show, no gap
  selection, no lag mapping) against the known family split (1 true-same pair, 9 true-different).
  Cost is a non-issue — ~10s per 97-minute source, ~600x realtime — so full-show coverage is free
  and the config's "coverage is the scarce resource" note is wrong; speech is scarce.
Found: yield rose only 2-9 -> 6-13 utterances/source, and the extra material is consecutive
  fragments of just two speech events (announcer intro, band intro). A 2003 Dylan show carries
  ~50 seconds of speech. Discrimination got WORSE: 7 of 9 true-different pairs now score above
  zero, and every match on every pair — including all 7 on the true pair — is a fragment of the
  same scripted announcer intro. That intro is tour boilerplate, confirmed by recovering the same
  announcement from 2003-04-18 Dallas.
Corrected: CALIBRATION_PROGRESS.md's documented "correct negative" (LB-01015/01046, "different
  tapers, no shared banter") is not one — the pair shares the whole intro and scores 0.708 once
  coverage reaches it. The 0.0 was a coverage artifact.
Found (highest value): vad_filter:true is the real limiter and fails SILENTLY. Full-show ASR on
  2003-04-18 (98 min) and 2003-11-01 Rome (121 min) returned ZERO utterances each; not the
  confidence gates, since it stays zero with min_avg_logprob/max_no_speech_prob/min_content_tokens
  all disabled. With vad_filter:False the same Dallas source yields 32 utterances in its first
  300s at no_speech_prob 0.63 — inside the shipped 0.8 gate. Silero VAD discards
  announcer-over-crowd-noise before Whisper sees it, NULLing banter_score for entire dates.
  Cost without VAD is ~100x realtime (~60s/source), still affordable.
Found (defect, unfixed): consecutive fragments of ONE sentence count as independent witnesses
  toward min_corroborating — the 0.708 pair's four "corroborations" are four chunks of a single
  announcement ~9s apart. Affects the shipped windowed path too (always_head_sec guarantees the
  intro is transcribed). Filed against step 1; must be fixed before any threshold.
Scope: three dates, all 2002-03, an era when Dylan barely addressed audiences — re-run on a 1970s
  date before drawing a corpus-wide conclusion. No code or config changed by this experiment;
  findings recorded in CALIBRATION_PROGRESS.md and TODO-293.

[2026-08-07] — feat(scraper): TODO-293 step 2 — banter_score is now matched-count-aware
Decided: the §3 banter/ASR scalar's denominator. Step 2's stated premise was false — it assumed
  banter_n_matched was persisted and the question re-derivable without re-transcribing, but
  observations.db holds 33,103 pairs with ZERO non-NULL banter_score and an empty transcripts
  table (asr.enabled:false means no session ever writes it; the 2003-05-11 figures came from an
  unarchived dev run). Decision taken analytically against asr.banter_score instead.
Changed: tools/tapematch/tapematch/asr.py — new `score_mode`. Default `witnesses` =
  sum(sim)/score_denominator_cap, a saturating count of corroborating witnesses. `rate` keeps the
  old sum(sim)/min(n_a,n_b,cap). rate was demoted for two defects, both reproduced against the
  real function: (1) its denominator is assembled from tunable ASR knobs (max_gaps, max_total_sec,
  model size, both confidence gates), so with evidence held fixed at 2 corroborations the score
  falls 1.000 -> 0.500 as yield rises 2 -> 4 — and raising yield is this signal's own stated next
  move, so every planned improvement would have depressed true pairs and invalidated any threshold
  set beforehand; (2) evidence-blind — 2-of-2 and 8-of-8 both scored 1.000.
Changed: both scalars are always computed and persisted, because the expensive step is
  transcription, not arithmetic: pairs.banter_score carries the selected one, new
  pairs.banter_score_rate always carries rate (idempotent ALTER, tapematch_session.py), and both
  reach results.json via banter_pairs. The step-1 distribution study now gets both curves over an
  identical match set from a single ASR pass.
Changed: config.yaml — score_denominator_cap 8 -> 4. Its meaning changed: under rate it was only a
  ceiling on min(n_a,n_b); under witnesses it sets the whole scale, and at 8 every real pair would
  compress into ~[0.25,0.5] with 1.0 unreachable (observed yield is 2-9 gated utterances/source,
  matched a subset). At 4: 2 matches -> 0.50, 3 -> 0.75, 4+ -> 1.0. PROVISIONAL, step 1 confirms.
Unchanged: min_corroborating floor, offset clustering, per-utterance dedup. Signal stays dark
  (asr.enabled: false, no addon_links rule reads it) — which is why the scalar was free to change
  now and would not have been after a rule shipped.
Tests: 5 new in tools/tapematch/tests/test_asr.py, incl. one re-asserting rate's yield penalty so
  it cannot be quietly reinstated. 45 pass in test_asr.py; 24 pass across the persistence,
  migration, emb_live and rerun-queue suites.

[2026-08-07] — docs: recover BUG-278 from BUGS.md, lost by a bad ledger edit
Fixed: BUGS.md was empty, but that was only mostly correct. BUG-278 (tapematch rule_d never fires
  live) was never closed — it was silently dropped. In b1ba0aa3 the BUG-309 block was inserted over
  BUG-278's title line, orphaning BUG-278's body under BUG-309's header; 929be8e2 then deleted the
  merged block from BUGS.md while archiving only BUG-309 to BUGS_DONE.md. Entry recovered verbatim
  from `git show 929be8e2^:BUGS.md` and restored with its title line repaired.
Audited: no other losses. BUG-210/309/310 were closed legitimately 2026-08-04 (all three present in
  BUGS_DONE.md); every BUG id 1–313 is accounted for except 67/136/147/148, which never existed in
  any commit (skipped numbers, confirmed by pickaxe over all history).
Changed: BUGS.md — status line corrected to "re-run PAUSED at 49/79" (was "in progress"), plus a
  LEDGER NOTE recording the loss and a resume block: queue at 49/79 (last 2003-05-09, next
  2003-05-11), no process running, resumable batch command, and the post-batch steps (family
  re-sync, CONTRADICTED_EMB_SECOND_PASS.md regen, then close BUG-278 + TODO-273).

[2026-08-06] — docs: close TODO-274, breadcrumbs/global search removal confirmed as final (won't-do)
Closed: TODO-274 (won't-do — tj confirmed no relocation wanted for the breadcrumb trail or global
  search field removed from AppShell's Topbar; the code change from that earlier session stands as-is).

[2026-08-06] — fix(backend): close TODO-297, reconcile moved/renamed collection files by hash
Changed: backend/db.py: add file_inventory.xxh3 partial index (ok rows), file_integrity_scans.files_moved
  column + migration, find_ok_inventory_by_xxh3() batch lookup helper.
Changed: backend/file_integrity.py: scan_mount's missing-sweep force-flushes pending upserts, then
  batch-checks each about-to-be-missing row's xxh3 against other 'ok' inventory rows (any mount)
  before flagging it. A match means the content already surfaced elsewhere this pass or a prior one,
  so the stale row is dropped (files_moved) instead of coexisting with the new location as a
  missing+new pair. Verified live: relocate a file, rescan, old row gone, destination stays ok,
  files_missing stays 0.
Changed: gui_next/.../ScreenFileIntegrity.tsx: surface files_moved in the recent-scans list.
Closed: TODO-301 (won't-do — sized the 'uncorrected'/'corrected' regex change: uncorrected is a
  1-LB/2-file edge case, corrected spans 97 files/40 LBs and would need asymmetric confidence logic
  tj judged not worth building).

[2026-08-06] — feat(db): close TODO-302, read collection-folder sidecars and split receipt faults by audio impact
Both gaps were found by running LB-15933 — the entry TODO-296 was opened on — through the real
  verify/lookup/lbdir pipeline. Result: /api/verify passes 28/28 against the uploader's sidecars,
  the lbdir check fails 1 of 38, and the lookup returns 55/56 matched with the odd one a bare
  NOT FOUND. So the originally-reported bug is real and reproducible, and the audit could not see
  it for two separate reasons.
Changed: backend/checksum_provenance.py — the attachment mirror is not complete evidence.
  LB-15933's site attachment is FFP-only; the uploader's MD5 (the value that actually disagrees)
  exists nowhere in data/site/files/, only in the .md5 shipped inside the torrent and sitting in
  the collection folder. classify_collection_source() + iter_collection_sources() now read
  .ffp/.md5/.st5 sidecars out of every my_collection folder, excluding the app's own
  *_mychecksums_* files (those hash the user's copy, not the uploader's intent) and lbdir*.txt
  copies (already the lbdir reference). Recorded with source_kind='collection'. Opt-in via
  run_audit(include_collection=True) / lb checksum-audit --include-collection, because it walks
  16.5k folders and is disk-bound. A folder that fails to stat is skipped quietly — an unmounted
  drive must never read as an absence of evidence.
Changed: tools/checksum_dispute_report.py — receipt_fault conflated two different findings.
  MD5 hashes the whole file, FFP hashes the decoded audio inside it, so an MD5-only disagreement
  whose FFP agrees means the recording is bit-identical and only the container moved — a retag,
  not a damaged transfer. split_receipt_verdicts() replaces it with audio_differs (the FFP moved),
  retag (MD5-only, FFP agrees) and receipt_unknown (MD5-only, no FFP to decide). Findings sourced
  from a collection folder carry a 'from collection' badge.
Changed: cli.py — checksum-audit --include-collection, and from_collection in the summary line.
Live run (84,157 sources, 21,973 of them collection sidecars): 570 isolated mismatches, paired
  into 312 findings across 93 LBs — 191 db_error, 13 audio_differs, 27 retag, 9 receipt_unknown,
  72 lbdir_only, 177 carrying an orphan value. 49 findings are visible only through collection
  sidecars. LB-15933 d1t14 is now caught at high confidence (27 rows agree, 1 disagrees) and
  correctly classified retag: uploader MD5 b54789c5…, DB and lbdir both 5840da36…, FFP
  c8d16745… agreeing everywhere. Jeff's copy is the same audio with a rewritten container, and
  the user holding the uploader's original still fails an MD5 lookup — which is the bug as
  reported.
Added: tests/test_checksum_dispute_report.py — 16 tests over the reference pairing and the
  retag/damage split. tests/test_checksum_provenance.py gains collection-source coverage (39).

[2026-08-06] — feat(db): close TODO-300, judge every checksum source against both the DB and Jeff's lbdir
Changed: backend/checksum_provenance.py — the audit had one reference (the checksums table), so it
  could only ever ask "is the DB value wrong?". Corrected premise from tj: Jeff does not transcribe
  the uploader's checksums, he generates his own from the folder after he has downloaded it. That
  makes the lbdir manifest an independent witness to a different question — the uploader published
  one set of checksums, did Jeff actually receive the fileset exactly as intended? A disagreement
  there means the bytes that reached him are not the bytes the uploader hashed (damaged transfer,
  re-encode, substituted file), which is invisible to a DB-only check and is the upstream cause of
  a DB value that "wrongly" records a file that arrived broken. New Reference class +
  load_db_reference() / load_lbdir_reference() (self-scope lbdir only — an xref manifest describes
  another entry's fileset and would poison the reference; an lbdir is never checked against
  itself); run_audit() now runs each source past both references and stores one row per reference.
  kind is now structural — isolated_mismatch | set_divergence — with reference_kind carrying which
  reference, and new columns reference_checksum/reference_file/displaced_to. displaced_to names the
  track that already holds the source's value under a different name (renumbered rip, same audio —
  not a damaged file). lookup_checksums()'s rescue path filters to reference_kind='db', since the
  DB is the only thing a user lookup was scored against, so API/GUI behaviour is unchanged.
  ensure_schema() drops a pre-reference_kind table instead of migrating it (all rows are derived;
  the 9,513 stored rows were all status=open with no curator notes, so nothing human was lost).
Added: tools/checksum_dispute_report.py — standalone HTML report at .debug/checksum_disputes.html.
  Merges the two per-reference rows for a track into one finding, because the pairing is what
  names the culprit: db_error (uploader + lbdir agree, only the DB differs → a transcription error
  fixable in one row), receipt_fault (DB + lbdir agree and both differ from the uploader → the LB
  itself carries a file that never arrived intact), lbdir_only. Cards carry the entry's
  date/venue/taper/source/timing/rating, the three checksums side by side, the witnessing source
  manifests, agreement ratios, and badges for orphan values (uploader hash present in no checksums
  row at all — a user with that exact file gets a bare NOT FOUND today), displacements, suspect
  filenames and xref evidence. Self-contained, light/dark, sticky filters + search.
Changed: cli.py — checksum-audit gains --db-only (skip the lbdir reference) and --reference db|lbdir
  (filter --list); the listing and summary now print the reference each dispute is against.
Live run (62,184 sources, 30s): 454 isolated mismatches — 187 high / 99 medium against the DB
  (reproducing the prior audit), and 147 high / 19 medium against the lbdir, i.e. tracks that did
  not reach Jeff as published, on 39 LBs. Paired into 289 findings across 78 LBs: 180 db_error,
  38 receipt_fault, 71 lbdir_only, of which 159 carry an orphan value.

[2026-08-05] — feat(db): close TODO-296, detect LB-database checksums that contradict their own provenance
Added: backend/checksum_provenance.py — cross-checks the checksums table against the uploader
  checksum files already mirrored in data/site/files/, without touching a collection folder.
  classify_source() sorts every LBF-* attachment into lbdir vs uploader, self vs xref, and marks
  names whose own words say their values are the discarded ones (bd00-09-23bad.md5.txt);
  iter_source_rows() re-reads it via parse_lbdir_file (handles both the sectioned lbdir layout and
  a flat .ffp/.md5/.st5); audit_attachment() compares by (lb, basename, chk_type) against the set
  of hashes the DB holds for that key, so an LB legitimately carrying two filesets is not flagged.
  The critical split: a source agreeing on >=3 rows and disagreeing on <=25% is kind=db_mismatch
  (one corrupted DB value); a source disagreeing across the whole set is kind=set_divergence — a
  remaster filed under the same LB reusing track filenames, informational only. Confidence is high
  for a self, non-suspect source and medium for xref/suspect ones. Findings persist in the new
  MASTER table checksum_disputes with a curator verdict (open/confirmed/dismissed) that re-running
  the audit preserves.
Changed: backend/db.py — checksum_disputes added to MASTER_TABLES and created by init_db();
  lookup_checksums() now looks every remaining NOT FOUND up in the dispute index by
  source_checksum and attaches dispute{lb_number, db_checksum, source_file, confidence, status,
  detail_url}, plus a `disputed` count in the summary. Status strings are unchanged — the item is
  still unmatched against the DB, the caller just learns why. This is the recovery path for the
  reported failure: the user's audio is fine, its hash is exactly what the uploader published, and
  only the DB's transcription is wrong.
Added: backend/app.py — GET /api/checksum-disputes (filter by lb/status, all=1 for the low-
  confidence divergences), PUT /api/checksum-disputes/<id> (curator-only verdict).
Added: cli.py — `lb checksum-audit [--lb N] [--include-lbdir] [--list] [--all]`, a local pass
  needing no server; 62,184 attachments in ~8s.
Added: tests/test_checksum_provenance.py — 22 tests covering classification, the isolated-vs-
  divergent split, MIN_AGREE, Windows subdirectory prefixes in checksums.filename, multi-fileset
  LBs, verdict persistence across re-runs, and the rescue index.
Catalogue (the TODO asked for it first): 98,718 attachments over 15,205 LBs — 20,533 lbdir,
  64,021 other txt, 12,414 DFF reports. 34,502 non-lbdir files carry 744k hash rows over 14,357
  LBs, so most of the library has an independent witness. Provenance was tracked nowhere in the
  schema before this. First pass: 287 db_mismatch (188 high / 99 medium), 9,627 set_divergence;
  78 high-confidence source values appear nowhere in checksums, so those are live false NOT FOUNDs
  today. LB-15933 produced no dispute — its lbdir, its .ffp attachment and the DB all agree on
  d1t14, so that report needs evidence from outside the mirror. Triage + GUI surfacing: TODO-299.

[2026-08-05] — fix(backend): close BUG-313, file integrity indexed files outside the collection
Fixed: backend/file_integrity.py — scan_mount() inventoried every file under a mount root and
  resolved the owning LB only after hashing, so files belonging to no collection folder were
  stored with lb_number NULL ("unlinked" in ScreenFileIntegrity) and then reported as missing
  once they moved or were deleted. The walk now resolves the LB first and skips anything outside
  a collection folder — the inventory covers collection files only, and non-collection bytes are
  never read. Added _purge_unlinked(), which deletes pre-existing unlinked rows at the start of
  each scan; verify_batch() drops any it still encounters.
Added: tests/test_file_integrity.py — test_files_outside_collection_folders_are_never_inventoried.

[2026-08-05] — fix(backend): close BUG-312, file integrity progress bar stuck on indeterminate shimmer
Fixed: backend/file_integrity.py scan_mount() never set progress['total'] during an index/verify
  tree walk, so ScreenFileIntegrity.tsx's ScanProgressBar always fell back to a fixed 40%-width
  shimmer animation regardless of real progress — read as the scan being permanently stuck at a
  small percentage. Now seeds total from the file_inventory row count already loaded in memory
  (no extra I/O); verified live against a real scan (total:258338, files_seen climbing to
  completion).

[2026-08-05] — fix(backend): close BUG-311, file integrity scan hang on stalled drive read
Fixed: backend/file_integrity.py — hash_file()/Path.stat() calls in scan_mount(),
  verify_batch(), and rebaseline() had no I/O timeout, so a stalled network mount or a
  failing sector blocked the scan thread forever with no exception raised and no response
  to Cancel. Added _with_timeout() (30s, IO_TIMEOUT_SECONDS) around those calls; a timeout
  now surfaces as an "unreadable" row (logged) and the scan moves on, instead of freezing
  progress indefinitely.

[2026-08-04] — chore(bookkeeping): close BUG-210, stray lossless_bob.db gitignored
Fixed: BUG-210 (backend/lossless_bob.db reappearing untracked) closed won't-fix/by-design —
  root cause confirmed 2026-07-27 as an ad hoc sqlite3.connect() typo, not app code. Added
  backend/lossless_bob.db to .gitignore so the stray file no longer shows as noise.

[2026-08-04] — fix(backend): close BUG-309 + BUG-310, pipeline rename/lbdir gaps
Fixed: /api/folder/rename (app.py:9096) resolved qBittorrent-sync lb_number only from
  my_collection/Pin-and-continue — both unset for the typical single-LB auto-rename candidate,
  so the sync silently no-op'd (BUG-309). Now accepts an optional lb_number in the request body
  (the pipeline's lookup match, mirroring /api/pipeline/file/start) and returns qbt_synced/
  qbt_error. gui_next ScreenPipeline.tsx applyRename() sends lb_number and toasts the result,
  mirroring applyFile(). New locale keys pipeline.rename.qbtSynced/qbtSyncFailed added to all
  6 locales via DeepL.
Fixed: backend/paths.py find_lbdir_attachment(lb_number) had no xref parameter — on the 1,473
  LBs with both a canonical and an xref-N lbdir attachment on disk, it returned whichever
  Path.iterdir() yielded first, filesystem-order-dependent. LB-16420 (my_collection.xref=0,
  canonical) was resolving to xref-02147's manifest instead of its own (tj's manually-added
  bug note, filed as BUG-310 and fixed same session). find_lbdir_attachment(lb_number, xref=0)
  now matches by fileset id (docs/XREF_SEMANTICS.md §3); added app.py _resolve_xref_for_folder()
  reading my_collection.xref (falling back to the folder name's -xrefNNNNN tag); threaded xref
  through /api/lbdir/retrieve, the pipeline's Step 3 lbdir fetch + P3 prefetch trigger, and
  integrity_monitor's collection scan. Alias-resolution fallback now only fires for xref=0
  lookups. Verified both directions on LB-16420 and LB-5058 (has both variants).

[2026-07-31] — fix(tapematch): repair the 7 BUG-277 self-pair dates (TODO-276) + close BUG-279
Fixed: the 7 dates whose pair/family rows were attributed to the wrong LB number under the
  pre-BUG-277 first-match regex — 1989-07-16, 1988-06-07, 1988-06-25, 1988-07-20, 1988-09-11,
  1988-09-23, 1993-06-19 — re-run live (34 min, all exit 0) and re-synced. New runs carry 0
  self-pairs; tapematch_pairs in the app DB has 0; all 7 dates now point at the 20260731 runs
  with corrected recording_families membership.
  1993-06-19 behaved exactly as TODO-276's watch item predicted: extract_own_lb_number still
  collides there (both folders -> LB-1929), because that folder inverts the convention — its
  OWN number is the bracketed `[LB-02072]` and the trailing 1929 is the xref. The
  DB-authoritative my_collection path resolves it, confirmed by --dry-run before committing to
  the re-run, so _assert_no_self_pair never had to abort.
  The 7 stale lb_a==lb_b rows stay in observations.db under their original June run_ids;
  _pick_best_run no longer selects those runs, so they are inert history, not live data.
  Side effect: all 7 dates now have an un-analysed run and re-entered the batch backlog
  (1545 -> 1548 eligible). 6 of 7 triage 'attention' on R1_contradiction — expected, the xref
  lineage claims on these folders are real and that is what R1 measures.
Fixed: BUG-279 ledger entry — the fix shipped 2026-07-27 but the entry was left in BUGS.md.
  Re-verified before closing: tapematch suite 383 passed in 29s, 0 runs written to
  observations.db, so the conftest _spawn guard is holding.

[2026-07-31] — feat(tapematch): rule-based auto-triage for the analysis backlog
Added: instructions/complete/TAPEMATCH_AUTOFLAG_SPEC.md — spec + calibration record. Only 1,397 of 3,037
  dates with a completed TapeMatch run have an analysis.md, and tapematch_sync reads the human
  "needs review" verdict out of that prose, so the other 1,640 carried no review signal at all
  (~62 more nights of /tapematch-batch to close). Everything else already worked without the
  prose — families/pairs cover 3,036 dates today.
Added: backend/tapematch_autoflag.py — machine 'clear'/'attention' verdict per date computed from
  observations.db alone. Four rules survived calibration against the 1,362 labelled dates
  (130 human-flagged): R1 an info-file same-source claim contradicted by near-zero correlation
  (prec 0.23 / rec 0.68), R3 duration outlier vs the date median (0.19/0.46), R7 4+ sources with
  no pair correlating at all (0.18/0.22), R5 label_suspect (0.25/0.02). R2 (low-confidence merge,
  0.07) and R4 (coverage gap, 0.05) were REJECTED — both fire below the 9.5% base rate, i.e.
  they are anti-signals. R6 staircase is deferred: segment count is not discontinuity detection,
  the real logic in cli.py was never surfaced to observations.db, so 0.00 measures a bad proxy.
  `python -m backend.tapematch_autoflag` reprints the calibration table so the operating point
  stays re-checkable as the labelled set grows ~25/night.
  Read the result asymmetrically: as a flag it is weak (0.19 precision — the human reads lineage
  prose the rules cannot see), as a CLEAR signal it is strong (802 no-fire dates, 97.4% of them
  human-judged clean). That retires 783 un-analysed dates to the back of the queue at a measured
  2.6% miss rate (accepted by tj) and concentrates prose work on 892.
Changed: backend/db.py — tapematch_family_meta gains auto_triage / auto_triage_reasons, with the
  usual PRAGMA table_info guard. Deliberately NOT folded into review_flag/review_reason: those
  mean a human read the prose, and merging a 0.19-precision heuristic in would have silently
  degraded a field dossier.py and taper_attribution.py already trust.
Changed: backend/tapematch_sync.py — compute_triage() runs once per sync over all dates and
  populates the new columns alongside the existing analysis.md verdict. Verified: 3,037/3,037
  dates now non-NULL, review_flag unchanged at 440 rows / 130 dates.
Added: tools/tapematch/next_batch.py + .claude/commands/tapematch-batch.md — the batch queue now
  orders by triage (attention first, most rules first, then fewest entries) instead of directory
  name. Note for whoever runs it: triage_analysis.py does NOT solve this problem — on the current
  backlog it yields AUTO=0 / ESCALATE=2,344, since any merge escalates.
[2026-07-30] — feat(tapematch): §3 banter/ASR transcript matching (built, dark-launched)
Added: tools/tapematch/tapematch/asr.py — FABLE_TAPEMATCH_LISTENING_SIGNALS.md §3. Every other
  TapeMatch signal measures the music; this one measures the words. Gap finder (low-energy
  between-song regions via match.find_quiet_segments) -> faster-whisper over those windows only
  (greedy, temperature 0, confidence-gated on avg_logprob/no_speech_prob) -> `banter_score`:
  Dice overlap of content tokens PLUS timeline agreement — matched utterances must share one
  time offset, which is what separates a real match from two shows colliding on stock stage
  phrases. Requires >=2 corroborating utterances (spec §3: singles are noise).
Added: observations.db `transcripts` table (run_id, lb, t_start/t_end on the TRIMMED performance
  clock, text, avg_logprob, no_speech_prob) + idempotent `pairs.banter_score`,
  `banter_n_utts_a/b`, `banter_n_matched`, `banter_offset_sec`. Transcripts are stored keyed by
  lb + time because the spec's reuse cases live outside TapeMatch: mislabel hunter, song-centric
  index, taper attribution.
Added: tools/tapematch/tests/test_asr.py + test_asr_persistence.py — 46 tests, no model download
  (a stub model covers the gating and timestamp arithmetic). test_asr_persistence.py also covers
  insert_pairs, which had no test at all before this session widened its 43-way INSERT.
Changed: tools/tapematch/tapematch/cli.py — windows are picked ONCE on the run's reference source
  and mapped into every other source through its fit_lag_segments model (TODO-235's persisted lag
  curve), not detected per source. This is the load-bearing design decision: a pair signal only
  corroborates if both sides transcribe the same moments, and per-source gap detection does not
  converge on that — measured on 2003-05-11, where one tape caught the band intro and the other
  spent its whole budget elsewhere and scored 0.0. lag_segments_out moved earlier (pure
  reordering) so the ASR block can read it.
Changed: tools/tapematch/config.yaml — new `asr:` block, **enabled: false**. Per spec §0 the
  signal ships dark: computed and persisted, but no addon_links rule reads it until a
  distribution study assigns a threshold. verdict.py registers `banter_score` in METRIC_KEYS with
  no rule attached. NULL = unavailable; 0.0 = computed, no corroborating banter.
Changed: requirements.txt, PROJECT.md — faster-whisper==1.2.1, OPTIONAL and feature-gated
  (lazy import; absent -> signal NULL, pipeline unaffected).
Verified on real audio (2003-05-11 Solomons MD): LB-01097/13538 scored **0.778** with 2
  corroborating utterances at a consistent -16.3 s offset — both tapes independently caught
  "[George Recile] is on the drums" — on a pair whose waveform corr is only 0.233. That is
  exactly §3's target case: same performance, very different-sounding tapes, music-based
  similarity weak, words decisive. The different-taper pair LB-01015/01046 correctly scored 0.0.
  Cost: 11-30 s per source for ~1600 s of selected audio (vad_filter skips the music) — compute
  is not the constraint, utterance yield is. Full detail + the two empirically-set gates in
  CALIBRATION_PROGRESS.md; calibration is TODO-293.

[2026-07-30] — fix(env): rebuild .venv on Python 3.14 (system 3.13 removed out from under it)
Fixed: .venv — the system python moved 3.13 -> 3.14 and /usr/bin/python3.13 no longer exists, so
  .venv/bin/python3 (a symlink to /usr/bin/python3) resolved to 3.14 while site-packages stayed
  on python3.13/. EVERY .venv/bin/python3 call in the repo — backend, tapematch, tests — was
  failing with ModuleNotFoundError: No module named 'numpy'. Recreated the venv on 3.14 and
  reinstalled requirements.txt: all pins resolve unchanged (numpy 2.4.6, scipy 1.17.1, ...).
  Also restored the dev/audio packages that live in the venv but not in requirements.txt —
  pytest 9.0.3, ruff 0.15.16, pre-commit 4.6.0, uv, pip, deepl 1.30.0, librosa 0.11.0,
  soxr 1.1.0 (tapematch imports the last two: pitch_ratio_pyin and resample_ratio).
  1070 backend tests + 383 tapematch tests green afterwards. The dead 3.13 venv was moved to
  .venv-broken-py313/ rather than deleted — remove it when convinced nothing is missing.
Changed: .gitignore — .numba_cache/ (written under tools/tapematch/tests/ when pytest imports
  librosa directly; cli.py routes its own cache to NUMBA_CACHE_DIR, plain collection does not).

[2026-07-29] — chore(docs): bump actions/setup-node v4 → v5 (Node 20 runtime deprecation)
Changed: .github/workflows/ci.yml, .github/workflows/release.yml — all three actions/setup-node@v4
  uses bumped to @v5. v4 declares `runs-using: node20` for its own wrapper, which GitHub has
  deprecated, so runners were force-running it on Node 24 and emitting a warning annotation on every
  CI run. v5 declares node24 natively. This concerns only the action's own JavaScript shim — the
  project still builds on Node 22 (`node-version: '22'`, unchanged at all three call sites).
  release.yml was included because the same annotation would otherwise resurface on the next release.
  No other action was affected: checkout is already @v5 and setup-python @v6.

[2026-07-29] — chore(docs): renumber 44 historical duplicate BUG/TODO ids; add ledger.py doctor
Changed: BUGS_DONE.md, TODO_DONE.md — 33 ids were reused across the four ledger files, all from the
  hand-numbered era before tools/ledger.py landed (2026-07-07); the newest collision dated 2026-07-01,
  so the allocator itself was never at fault (next_id() takes max() across open+done). BUG-107 alone
  named five different bugs. For each group the tools/ledger_dedup.py _pick_authoritative() winner
  keeps the id; the other 44 entries were reassigned to BUG-281..308 / TODO-277..292 and each gained a
  `Formerly: <OLD-ID> (duplicate, opened <date>)` field so references in immutable git commit messages
  stay decodable. Both *_DONE.md files gained a dated header note stating that ids in commit messages
  and in CHANGELOG entries predating 2026-07-29 may use the pre-renumber numbering.
Fixed: BUGS_DONE.md — the BUG-217 block at line 984 was a byte-identical copy of the one at line 332
  (diffed to zero output before deleting), not a numbering collision; deleted rather than renumbered.
  BUG-116b, a hand-patched letter-suffix id that had started a second competing convention, was
  normalised into the numeric allocation. The now-obsolete "renumbering is pending the TODO-209 dedup
  pass" NOTE inside the former BUG-193 (now BUG-302) was removed — the `Formerly:` field supersedes it.
Changed: 18 cross-reference files rewritten at ~110 sites — CHANGELOG.md, CHANGELOG_ARCHIVE.md,
  PROJECT.md, BEST_PRACTICES.md, pyproject.toml, backend/{app,db,integrity_monitor,scheduler}.py,
  docs/wiki/Collection-Pipeline.md, gui_next AboutDialog.tsx + ScreenMounts.tsx, three instructions/
  files, tools/tapematch/{BASELINE.md,calibrate_lowband.py} + two of its tests. Every edit is a
  comment, docstring, or prose token; no executable code changed. Sites were assigned by date window
  for dated docs and by subject match for undated code refs.
  11 sites were deliberately left unchanged: CHANGELOG_ARCHIVE.md:779/798 are dated 2026-05-26, when
  only one BUG-107/110/111/115 existed each — and those are the keep-winners, so no edit is the
  correct result, not merely the safe one. CHANGELOG.md:3160/3161/3175/3179 and TODO_DONE.md:405/662
  are prose *about* the duplication problem; renumbering ids inside them would make the sentences
  self-contradicting. (CHANGELOG.md:3175 had flagged this exact work on 2026-07-08 and deferred it.)
Added: tools/ledger.py — `doctor` subcommand, the permanent guard: exits non-zero listing any id whose
  header appears twice across the four ledger files, or any letter-suffixed id. Exits 0 today.
  tests/test_ledger_doctor.py covers clean / duplicate / letter-suffix for both kinds (8 tests).
Changed: tools/ledger_dedup.py — cross-reference search widened from a fixed CROSS_REF_ROOTS allowlist
  (which missed PROJECT.md, backend/, gui_next/, tests/, pyproject.toml) to `git grep` over the whole
  tracked repo; gained an idempotent `--apply` mode (a second run is a no-op).
Changed: .claude/commands/session-close.md — Step 7's manual "no BUG/TODO number used twice" bullet,
  which could never pass against the historical data and so resurfaced every session, replaced by
  running `ledger.py doctor` and requiring exit 0.
Verified: doctor exit 0; 0 duplicate headers; 0 letter-suffix ids; 44 `Formerly:` fields (28 BUG +
  16 TODO); next-id → BUG-309 / TODO-293; check_project_refs.py exit 0; tests 1070 passed;
  gui-check node types 0 / renderer types 0 / build PASS.

[2026-07-29] — fix: BUG-280 (1961–68 dates land in 2061–68) and BUG-277 (shadowed LB tag)
Fixed: tools/tapematch/tapematch_session.py — BUG-280. All three date-parse sites used
  datetime.strptime(date_str, "%m/%d/%y"), inheriting Python's POSIX %y pivot (00–68 → 2000–2068),
  so Dylan's 1961–1968 material resolved to 2061–2068 and sorted to the end of the TapeMatch triage
  queue as future shows. New parse_db_date() helper re-anchors any parse landing in the future back
  to the prior century, used at all three sites. Backfill: 41 run dirs under data/tapematch/runs/
  renamed 20xx→19xx; concert_date corrected in observations.db (runs/sources/pairs +
  runs.archive_dir) and data/losslessbob.db (tapematch_pairs, tapematch_family_meta, and
  recording_families — the last not named in the original report but equally affected). Verified 0
  tapematch_date_curation rows existed for the 41 dates before mutating. Post-fix: 0 future-dated
  dirs or rows remain, 565 tapematch_pairs rows now carry 196x dates. The analyses themselves were
  always sound — only the date label was wrong. Regression tests in tests/test_parse_db_date.py.
Fixed: tools/tapematch/tapematch/ingest.py, tapematch/cli.py, tapematch_session.py, emb_live.py —
  BUG-277. _lb_num() took the FIRST LB-\d+ match in a staged folder name, so an embedded
  cross-reference ("… [fixed LB-2204]-LB-10437-v") shadowed the folder's own trailing tag,
  producing self-pairs (lb_a == lb_b) that correlate 1.0 by construction and read as spurious
  same_family merges. New ingest.extract_own_lb_number() strips bracketed segments then takes the
  LAST remaining match; shared by cli.py, the session's regex fallback, and emb_live.py's
  sources_from_results(), which carried the identical bug (found while auditing other folder-name
  readers). name_to_lb is now authoritative — a miss logs a warning instead of silently trusting
  the regex — and new _assert_no_self_pair() raises before insert rather than writing a corrupt
  row. 6 of the 7 live collisions now resolve from the folder name alone; 1993-06-19
  (LB-1929/LB-2072) is unresolvable by filename and depends on the DB path, with the assertion as
  backstop. Tests in tests/test_lb_num_extraction.py. Data repair of the 7 dates is TODO-276.
Added: TODO-276 — re-run the 7 BUG-277 dates to clear stale wrong-LB pair/family rows; needs a
  live session, deferred so it does not collide with the nightly cron.

[2026-07-29] — docs: close §10.6/Q7 won't-do on evidence; file BUG-280 (1961–68 dates)
Changed: instructions/complete/design_handoff_tapematch_curation/WORK_PACKAGE.md — D19 records the
  recordings-per-date measurement that closes the handoff's last open design question. §10.6 is
  drawn at "34 recordings / 561 pairs — the practical worst case in the library"; across all 3,037
  synced dates the true maximum is 26 recordings / 325 pairs (1974-01-31, MSG) and nothing reaches
  30. Its parked "recommended additions" (sticky row/column headers, the .tmFamRule family-boundary
  rule) are therefore won't-do rather than pending-design: the rule would draw ~15 lines through a
  date whose 15 families are 11 solos, and sticky headers serve one date in 3,037. Verified the real
  worst case in Electron at 1920×1080 — compact mode fits the 26×26 grid with no horizontal scroll.
  The compact threshold (past 20 recordings) fires on exactly 2 dates corpus-wide. Also logs the
  phase-8 repair: ReportSheet.tsx was left mid-refactor and non-compiling under a resume-log entry
  claiming gui-check green.
Added: BUGS.md BUG-280 — all three strptime(date_str, "%m/%d/%y") sites in
  tools/tapematch/tapematch_session.py inherit Python's POSIX %y century pivot (00–68 → 20xx), so
  Dylan's 1961–1968 shows resolve to 2061–2068 while 1969+ is correct. 41 dates, 41 run dirs under
  data/tapematch/runs/ and 41 tapematch_pairs.concert_date values are future-dated and sort to the
  end of the TapeMatch triage queue. The analyses are sound — only the date label is wrong — and no
  tapematch_date_curation row is affected, so no curation record needs remapping.

[2026-07-29] — feat: TapeMatch Curation phase 8 — the §12 run diff; the build is complete
Added: backend/app.py — GET /api/tapematch/runs?date= lists every run for a date, newest first
  (the two pickers §12/Q8 asked for; 1989-06-04 has 15), and
  GET /api/tapematch/run_snapshot?date=&run_id= returns that named run's own sources + pairs so
  the renderer can diff two runs as a pure function. Both read-only, both probe their optional
  columns, both degrade to empty on a locked observations.db. tests/test_tapematch_routes.py —
  44 pass (3 new, incl. a two-run fixture proving the snapshot is the named run, not the latest).
  Landed as commit f880d85f, unlogged until now.
Added: gui_next/src/renderer/src/lib/runDiff.ts — the pure diff. §12.2's successor mapping (each
  base family is inherited by the head family holding the plurality of its members, so a
  carved-out family reports `split out of base F1` rather than "unchanged"), the sorted-pair-key
  guard §12's implementation note demands, and §12.5's judgment reconciliation. Checked against
  README §12.2's own fixture before wiring — base F1 `11201 11458 11340 11977` splitting into F1
  (`11201 11458` + `13022`) and F3 (`11340 11977`) reproduces the design's reading exactly — then
  against live runs of 1989-06-04 (5→4 families, one merge, one flipped call) and 1996-07-13.
Added: gui_next/src/renderer/src/components/tapematch/RunDiffSheet.tsx — `Compare runs` in the
  date header opens the sheet: run bar, four stat tiles, families with `+`/struck-through chips,
  the §12.3 delta matrix (fill = magnitude, ring + `!` = the call flipped), the §12.4 pair table
  and §12.5's judgment-impact rows. §12.1's pipeline-cause list is stated as underivable rather
  than guessed — run artifacts record no threshold set (Q2 already made cause prose forward-only).
Changed: gui_next/src/renderer/src/components/tapematch/ReportSheet.tsx — the portalled overlay
  (scrim, sheet chrome, focus trap, Esc, scroll lock) extracted to
  components/tapematch/SheetShell.tsx (D18) so §11 and §12 are the same object to the curator;
  ReportSheet keeps only its own header controls and body. No behaviour change — 123 lines out.
Changed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — `Compare runs` button,
  the two run/snapshot queries (fetched only once the sheet opens), and the default comparison:
  previous run vs current, which is the pair that answers the question §12 exists for. Picks
  reset on date change; a diff row can open that pair's dossier.
Changed: instructions/design_handoff_tapematch_curation/ → instructions/complete/ (build closed,
  all nine phases shipped); PROJECT.md + instructions/README.md updated for the new path.
Changed: tools/tapematch/rerun_bug278.txt — BUG-278 rule_d re-run progress, 49 of 79 dates done.

[2026-07-28] — feat: TapeMatch Curation phase 9 — the §10 edge and transient states
Fixed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — every loading flag was
  keyed on react-query v5's isLoading, which is isPending && isFetching; under
  PersistQueryClientProvider a query's fetchStatus stays idle until the IndexedDB restore
  finishes, so isLoading is false exactly while nothing is known and no skeleton ever showed on
  a cold start. Keyed on isPending now. The visible symptom was the triage rail rendering its
  empty state — "Nothing here." — for the seconds /api/tapematch/dates (3,195 dates) was in
  flight, telling the curator the queue was empty.
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the §10 states. §10.1
  skeletons: a shared primitive whose sweep is deliberately faint (4.5% white, dropped under
  prefers-reduced-motion) so it doesn't fight the matrix's own colour coding, rail skeleton
  rows, and a matrix skeleton that renders the real grid — same template, same aspect-ratio
  cells, same diagonal — off the recording count, which is known long before any pair
  measurement, so nothing reflows when values arrive. §10.2 fetch error: the real request,
  error, run id and attempt count in a mono detail block, a Retry, and the required
  reassurance that saved judgments are safe; the date header keeps what it knows and overrides
  the status pill to `unavailable`, drops the run pill and swaps the verdict line. §10.3 the
  rail's empty state now states the outcome in the filter's own terms with a `Show all dates`
  link. §10.4 zero-recording dates get a mute state naming both cause and recovery. §10.5
  single-recording dates collapse to a solo card and the section retitles to Recording; Accept
  families stays enabled there (nothing to rubber-stamp). §8's drawer gains its slide-in, a
  focus trap and focus-restore to whatever opened it.
Changed: instructions/design_handoff_tapematch_curation/WORK_PACKAGE.md — phase 9 marked done,
  decisions D14 (skeleton names the pair count, not a fake done count), D15 (§10.4's two ghost
  actions have nothing to open) and D16 (isPending, not isLoading) recorded. §10.6 was already
  built in phase 2; its sticky-header/family-rule additions stay unbuilt pending the design
  answer README itself asks for (Q7).

[2026-07-28] — feat: TapeMatch Curation phase 7 — the report.md view (§11)
Added: backend/app.py — GET /api/tapematch/report?date=. Same run resolution and read-only disk
  read as /api/tapematch/analysis (report.md is analysis.md's sibling in the run's archive dir),
  plus run_dir, which the sheet header prints so a curator can find the file on disk. A run that
  never wrote report.md still returns its run_id/run_dir with report_md null, rather than
  pretending the date has no run; 409 locked kept for the observations.db read.
Added: gui_next/src/renderer/src/lib/reportMd.ts — sectioning parser for report.md. Splits the
  `## tapematch output` fence on its own `=== MARKER ===` lines into one panel each (A1, with
  the one-line/≤90-char inline rule and the DIAGNOSTICS/CLUSTERS open-by-default set), reads
  Coverage's `DB entries: **n** | Found on disk: **m**` figures and rows (A3), and builds the
  outline with counts only where a count means something and the parenthetical kept on both
  entries when two markers collapse to the same short label (A2). Checked against all six
  documents in the handoff's real_output/ before any of it was wired.
Added: gui_next/src/renderer/src/components/tapematch/ReportSheet.tsx — the §11 overlay itself,
  portalled to document.body so it sits over the workspace (which stays visible: the report is
  reference material consulted during review) and so §11.1's print block can scope itself by
  hiding every other body child. Rendered/Raw toggle, Copy/Download/Print, outline rail with
  nested markers, LB chips carrying family swatches, clickable audit rows, a stale banner when
  judgments post-date the file, and dashed `YOUR JUDGMENT` annotations marking what is not part
  of the generated document. Prose blocks go through react-markdown; LB chips inside them are
  injected by walking the rendered children, because its components map covers element nodes
  only.
Changed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — `Open report.md` is
  live (it was a disabled placeholder), the report query is enabled only while the sheet is
  open, Esc closes the report before the dossier, focus returns to the button on close, and an
  LB chip / audit row click closes the sheet onto the workspace selection it names. Also
  corrected the Accept-families tooltip, which still named observations.db · curation_accepts
  after that record moved to the app DB.
Changed: gui_next/package.json — react-markdown 10.1.0 and remark-gfm 4.0.1 added --save-exact
  (design handoff Q5: use a real markdown renderer, pinned; do not write a parser).
Changed: tests/test_tapematch_routes.py — 4 new cases for the report route (text + run_dir, a
  run with no report.md, unknown date / absent DB, missing param); 41 pass.
Changed: PROJECT.md — the new route in the Flask table, and the ScreenTapeMatchCuration entry
  now describes §11 instead of listing it as unbuilt.
Changed: .claude/CLAUDE.md, .claude/hooks/session_brief.sh — the harness's "put temp files in
  the scratchpad" instruction is now contradicted where it is actually read: a Temp files rule
  at the top of CLAUDE.md and an [OVERRIDE] block in the session briefing. Writing to
  /tmp/.../scratchpad is hard-blocked by the PreToolUse hook and aborts the turn mid-task; it
  had happened three times across sessions, so the counter-instruction belongs in the injected
  context, not only in memory.

[2026-07-28] — feat: TapeMatch Curation replaces ScreenTapeMatch at /tapematch
Changed: backend/db.py, backend/app.py — the accept record moved out of observations.db into
  the app DB as tapematch_date_curation (USER table, same columns). Reversing the same-day
  decision below on tj's call to pick the best schema: nothing in the tapematch pipeline reads
  an accept, and observations.db is write-locked for hours by the nightly analysis runs, so
  storing it there meant an accept could 409 purely because a batch was mid-flight. In the app
  DB it is also covered by the master export's USER_TABLES exclusion (it stays local, survives a
  master import) and created by the normal init_db schema pass instead of an ad-hoc CREATE TABLE
  on every write. The route still reads observations.db read-only to resolve the run and take
  n_judged/n_families, so the 409 path remains for that read alone. GET /api/tapematch/dates
  reads curated/curated_at from the app DB, which means the triage rail keeps showing curated
  state even while a run holds observations.db. The interim curation_accepts table was dropped
  from observations.db, which is now byte-for-byte back to its pipeline-owned schema.
Removed: gui_next/src/renderer/src/screens/ScreenTapeMatch.tsx — the read-only v1–v4 TapeMatch
  screen (TODO-170/215/231/232), replaced by ScreenTapeMatchCuration now that the phase-6 write
  path put it at parity. /tapematch serves the curation screen and the existing nav entry needs
  no change; /tapematch/curation redirects there with its query string intact, so links made
  while it was being built still work.
Changed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — ported the three things
  the old screen had that the new one didn't, so retiring it costs nothing: crawl start/stop
  buttons in the §1 top bar (this was the app's only control for the library crawl; the shell
  scripts remain the single-instance authority, 409 = already running), the LB deep-link into
  the Library detail panel (`/library?lb=`, TODO-215 sub-feature 3) on the dossier's two LB
  headings, and the raw analysis.md behind a disclosure under the §7 cards (§7 is a *reading* of
  that document, and when a card looks wrong the next question is what the file actually says —
  §11's overlay is report.md, a different file).
Changed: tests/test_tapematch_routes.py — accept tests assert the row lands in the app DB and
  that observations.db's table list is untouched; 37 pass. Full suite 1055 pass.
Changed: PROJECT.md — tapematch_date_curation schema section, accept/dates route entries
  rewritten, the ScreenTapeMatch row removed and ScreenTapeMatchCuration's rewritten as the
  shipped screen.
Note: the curation screen is NOT internationalised — it is hardcoded English, so the TapeMatch
  screen has lost its de/fr/es/it/nl translations until TODO-275 (opened for it). The retired
  screen's tapematch.* locale keys are deliberately left in locales/*.json to seed that pass.

[2026-07-28] — feat: TapeMatch Curation phase 6 (write path — judgment save + Accept families)
Added: backend/app.py — POST /api/tapematch/dates/accept, the curation screen's §3
  "Accept families". [SUPERSEDED the same day by the entry above: the record was first written
  to observations.db as an additive curation_accepts table, and now lives in the app DB's
  tapematch_date_curation. The column set and semantics below are unchanged.] n_judged is counted
  server-side from pairs.human_judgment rather than taken from the client, so the stored record
  reflects the DB at accept time; re-accepting a date replaces its row, because a rerun can move
  the run under it. n_families is probed with PRAGMA table_info like the pairs route's secondary
  metrics. 400 missing_fields / 404 no_run / 409 locked, same shapes as the judgment route.
Changed: backend/app.py — GET /api/tapematch/dates now also carries curated/curated_at (see the
  superseding entry above for where they are read from).
Changed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the judgment control's
  Save is wired to the shipped POST /api/tapematch/pairs/judgment, keeping WORK_PACKAGE D4's
  explicit Cancel/Save rather than §10.7's optimistic model (409 `locked` is a real state an
  optimistic button would have to lie about), plus §10.7's save-status line: Saving… / Saved
  14:22 · LB wrong (fading back to the explainer after 4 s) / a persistent failure line with a
  Retry button. `Accept families` gains its §3 count suffix and §10.5's single-recording
  special case (enabled at zero judgments, because the "judge something first" rule exists to
  stop rubber-stamping pair decisions and a solo date has none). The judged count is server
  truth refetched after each save, not a local queue — with an explicit Save nothing is ever
  queued, so the button suffix, the new top-bar pill and the accept record's n_judged all count
  the same non-null human_judgment rows and cannot drift apart. `curated` now populates the
  triage rail's fourth status and wins over conflict/review: it is the curator's own terminal
  verdict, so an accepted date leaves the "Needs you" queue.
Changed: tests/test_tapematch_routes.py — 6 new tests (37 pass): accept records the row and
  counts judgments server-side, resolves the run when omitted, upserts on re-accept, 400 on a
  missing date, 404 with no observations.db, and dates reporting curated before/after an accept
  (including the missing-table case). The two exact-dict dates assertions gained the new keys.
Changed: PROJECT.md — Flask route table: the new accept route, and dates' curated/curated_at.
Note: verified against live data with /verify --electron on 1989-06-04, then reverted — the
  accepted row was deleted and the test pair judgment cleared, so the only durable change to
  observations.db is the new (empty) curation_accepts table. The test write used `uncertain`
  deliberately: confirmed_same/confirmed_different are calibration truth for regression.py.

[2026-07-28] — feat: TapeMatch Curation phase 5 (analysis verdict cards §7)
Added: gui_next/src/renderer/src/lib/analysisMd.ts — parser for a run's analysis.md, for the
  curation screen's §7 stack. No backend change: /api/tapematch/analysis already returns the whole
  document (it has to, for §11's raw view), and these are rendering rules, so they live next to
  the thing that renders them. Implements the design handoff's answers — B1's subject rule (the
  text left of the first em-dash is a ref, a `Family n`, or neither; the first two are cards, the
  third is a statement about the run), B1.1's body blocks (`label: value` becomes a key/value row
  and a quoted value takes the quote treatment, which is what makes a headline-less card readable),
  B1.2's statement blocks, B2's ordered tone table (MISS/contradiction → bad; INCOMPLETE, speed
  offset, LOW CONFIDENCE, reliability caveats, coverage gaps → warn; else info) matched with
  quoted spans stripped so scraped LB commentary can't set a card's severity, A5's trailing-emoji
  strip and A8's HTML-entity decode. Checked against all six real_output/ documents first:
  1993-06-27 → 20 cards (its eleven ref-only ones all info), 1996-07-13 → bad ref card + family
  card + `Audit table` statement, 1998-06-14 → `Coverage gap` statement + two contradiction cards,
  2018-08-26 → zero cards and the A6 clean sentence.
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the §7 section itself:
  tone-barred cards, dashed statement blocks with a tone-tinted key, A6's clean-date line (a dot
  and the generator's own sentence — a clean date has no findings, and dressing that as a card
  devalues the card), the not-on-disk and algorithm-note meta lines. A7's ref is quoted verbatim
  from the document and clicks through the normalised lb_a < lb_b key into the dossier, but only
  when it names exactly two LBs the date actually has a pair for (D9). The family chip's swatch is
  tinted from analysis.md's own Family column, since the app DB's fam_id is member-derived and
  carries no run family number; its click-to-select-members behaviour is deferred to phase 9 (D8).
Changed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the dossier's LB-page
  quote now clamps to 3 lines with Show more past ~240 characters and decodes HTML entities (A8).
  Scrape debris stays visible deliberately; the clamp keeps it out of the default view.

[2026-07-28] — feat: TapeMatch Curation phase 4 (speed & lag strip §6)
Added: backend/app.py — GET /api/tapematch/sources?date= returns one row per recording
  ({lb_number, speed_kind, speed_ppm, family_id, folder_name, lag_ref_lb}) from observations.db's
  sources table. Its own route rather than another field on /api/tapematch/pairs: the data is
  source-shaped, and the speed strip is the one view that still has something to show on a
  single-recording date, which has no pairs at all. Rows come from the LATEST run holding sources
  for the date (the rule ab_clips.get_source_info already uses), not the possibly-stale run_id
  synced into tapematch_pairs, so a rerun's new speed_kind shows immediately. Columns probed with
  PRAGMA table_info; a missing or locked observations.db, or an unanalysed date, returns
  sources: [] with a null run_id rather than failing the request.
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the §6 speed & lag strip.
  Signed square-root axis (sign(p)·√|p|) across 4–96% of the width, because ppm on the real corpus
  spans four orders of magnitude and a linear axis piles every dot on the origin; ticks at domain
  min / ref / max with a true minus sign and thousands separators; DESIGN_ANSWERS A4's four-glyph
  vocabulary (◆ reference, ● aligned / constant offset, ▤ lag steps — re-tracking or a splice,
  ? speed-unknown, which `insufficient` folds into); greedy lane packing at a 4.8% label width so
  clustered dots stack downward and the container grows instead of clipping. Per DECISIONS Q3 the
  tooltip carries no ratioConfidence: LB-xxxxx · kind · ±N ppm.
Added: work-package D7 — dot clicks build a pair two at a time (click one dot to arm it, dashed
  outline; click a second to open that pair's dossier), which is README §6's own recommended
  production behaviour over its "blunt" prototype logic. The recommendation's other half —
  highlighting the clicked recording's whole matrix row/column — is not built: a second highlight
  state threaded through Matrix on top of its selection dimming is real risk for a hint the dot's
  own outline already gives.
Added: tests/test_tapematch_routes.py — five tests for the new route (latest-run selection over a
  multi-run date, a pre-speed_ppm observations.db, unknown date, absent DB, missing param).
  31 pass.
Note: a speed-unknown row's ratio confidence fell below the 6.0 minimum, so its stored ppm is an
  estimate the pipeline itself doesn't trust — and those are the extreme values that set the axis
  domain (1989-06-04 spans −29,073 to +55,312 ppm on four such rows). The design plots every
  recording on the axis and Q3 left no confidence field to key on, so they are positioned as
  stored with "(unconfident estimate)" in the tooltip; the alternatives (an off-axis gutter,
  clamping the domain to trusted kinds) are design questions, recorded in WORK_PACKAGE.md.
  Verified with /gui-check + /verify --electron on 1989-06-04, 1991-07-20 (all four glyphs in one
  strip) and 2001-10-30 (three lanes), in dark mode, across the pending → pair → restart clicks.

[2026-07-28] — feat: TapeMatch Curation phase 3 (pair dossier §8)
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — the §8 pair dossier, in
  both its docked (>1520px) and drawer forms. Drawer overlays the work column on a scrim with a
  ✕ in the header; scrim-click and Esc clear the selection (slide-in transition and focus trap
  stay Phase 9). Stack, top to bottom: header with family swatches, verdict block (similarity or
  n/c + one of same family / same family · secondary link / not comparable / different family),
  conflict callout, A/B listening, Primary evidence (residual correlation vs its 0.45 threshold
  mark, with the conditional note that says why the algorithm did what it did), Secondary evidence
  (windowed coverage vs 0.60, quiet-segment hiss, demoted fingerprint dice with its 0.15–0.50
  coincidence band), the LB-page claim with an agrees/disagrees/no-claim pill, and the 2×2
  judgment control with notes. The judgment control is UI only — draft state, toggle-off and
  Cancel work, the POST is Phase 6 per work-package D4.
Changed: work-package D3 superseded. It provisionally placed the A/B player just above the
  judgment control on the reading that design had not answered Q10; design had answered in code —
  tm-parts.jsx's Dossier renders ABPlayer directly after the conflict callout, above the evidence
  bars, and DESIGN_ANSWERS A9 fixes its 96px reserved height plus the one-line "not
  sample-alignable" reason for the common ineligible case. Built as designed. The player itself is
  carried over from ScreenTapeMatch's AbPlayerPanel unchanged in mechanic (one aligned WAV per
  source from POST /api/ab_clip, both <audio> elements started together, A/B toggle = mute swap).
Added: backend/app.py — GET /api/tapematch/pairs now also carries windowed_frac and hiss_median,
  the two secondary-evidence metrics evidence bars 2–3 draw. Like lb_says_same (D6) they live only
  in observations.db, so they ride the same best-effort live read. Both columns were added to that
  table after it first shipped, so their presence is probed with PRAGMA table_info — an older DB
  yields null for those two fields instead of raising and collapsing the whole enrichment block
  (judgments included) to nulls.
Fixed: backend/app.py — that probe now covers all six enriched columns, not just the two new
  ones, which repairs two tests red since phase 2: test_ab_clips.py's ab_eligible cases build a
  fixture observations.db without lb_says_same/lb_relation_text, so phase 2's hard SELECT raised
  and nulled ab_eligible along with everything else. Full suite 1044 pass.
Added: tests/test_tapematch_routes.py — the enrichment test now asserts the two new fields, and a
  new test drives the missing-columns path via a fixture DB built without them, proving
  human_judgment/lb_says_same still survive. 27 pass.
Note: §8's four bars have no slot for emb_score, and on the real corpus that is where many
  same-family merges actually come from (1989-06-04 LB-02470 × LB-14054: 85% similar, corr 0.004,
  windowed 0.0). Those pairs get labelled "secondary link" — directionally right, literally wrong
  about which signal merged them. Either a fifth bar or a design answer; recorded in WORK_PACKAGE.md,
  not invented here. Verified with /gui-check + /verify --electron on 1989-06-04 (same-family,
  conflict and A/B-eligible pairs, docked and drawer).

[2026-07-28] — feat: TapeMatch Curation phases 1–2 (shell + similarity matrix)
Added: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — new curation screen at
  /tapematch/curation, built from instructions/design_handoff_tapematch_curation/. Phase 1 (commit
  0ee5f804, unlogged at the time): family colour tokens in lib/tokens.ts, top bar §1, triage rail
  §2, date header §3 with the B3 verdict clamp, section wrapper §4, work grid + breakpoints. Phase
  2 (this session): the similarity matrix §5 — three colour regimes against --lbb-surface with the
  ^0.8 gamma on the non-family ramp, n/c hatching, LB-page conflict dot, symmetric selection with
  cross-dimming, legend, role="grid" with roving-tabindex arrow navigation, and §10.6 compact mode
  (fixed 22px columns, rotated headers, values to tooltip) past 20 recordings. Per D1 the old
  ScreenTapeMatch.tsx is untouched and keeps its nav entry until parity at Phase 6; the new screen
  still has no nav entry.
Added: backend/app.py — GET /api/tapematch/pairs now also returns lb_says_same and
  lb_relation_text. The app DB's tapematch_pairs carries no LB-page claim, but the route already
  opened observations.db live for human_judgment/ab_eligible enrichment, so the same SELECT now
  carries the claim too (work package D6). The matrix's conflict marker is lb_says_same &&
  !same_family — needing both the claim and the algorithm's verdict. Same best-effort null
  fallback as the rest of the block; no schema change, no re-sync.
Added: tests/test_tapematch_routes.py — coverage for that enrichment path, seeding a real
  observations.db (pairs + sources) so the block actually runs, and asserting human_judgment is
  populated too so the test cannot pass via the null fallback. 25 pass.
Fixed: gui_next/src/renderer/src/screens/ScreenTapeMatchCuration.tsx — two layout defects found
  by /verify --electron against live data, both invisible until the screen had real content. The
  triage rail grew to ~745px and squeezed the matrix: flex: 0 0 272px leaves min-width:auto, so
  long venue strings won on min-content; pinned with minWidth/maxWidth. The matrix wrap was also
  missing the design's 760px cap (§10.6 describes compact mode as the state that drops it).
Note: the rail renders its "Nothing here." empty state while /api/tapematch/dates is in flight
  rather than a §10.1 skeleton — carried to phase 9, recorded in WORK_PACKAGE.md. Verifying this
  screen requires /verify --electron; Tier A stubs window.api, so every panel renders empty.

[2026-07-27] — fix: BUG-278 (rule_d now fires live) + BUG-279 (test suite no longer spawns real
  sessions)
Fixed: BUG-278 — addon_links.rule_d fires during live clustering for the first time since it
  shipped enabled on 2026-07-04. tapematch/cli.py's _pair_metrics() never carried emb_score /
  emb_score_global, so verdict._rule_d_emb_both hit its None guard and abstained on every pair;
  emb_live populated those columns from _log_to_obs_db(), one stage after the verdict was decided.
  New emb_live.score_session_pairs() (DB-free) is shared by both paths so a live verdict and the
  persisted row cannot disagree; cli.py gains --concert-date (the embedding cache is date-keyed)
  and scores every pair before match.cluster; tapematch_session.py passes the date at both
  run_tapematch call sites. Lazy defensive import — any failure leaves scores None and rule_d
  abstains, exactly as before. VERIFIED on 1994-02-16: "embedding: scored 21 pair(s), 3 at/above
  the rule_d bar", producing exactly the 3 predicted flips (LB-10872 joined the {5202, 14921,
  15363} family via two direct links plus one transitive). Re-run of the other 79 affected dates
  launched detached; queue tools/tapematch/rerun_bug278.txt, log data/tapematch/bug278_rerun.log.
Fixed: BUG-279 — `pytest tests/` was launching real tapematch sessions: decoding audio from
  /mnt/DATA0 and committing runs to the production observations.db (two landed on 1989-06-04
  before it was caught; both reproduced the existing verdicts exactly, so no data damage).
  run_batch/run_year/run_crawl have spawned a fresh interpreter per date since ac804108
  (2026-06-18), but test_batch_queue.py still patched run_date, so its fakes were silent no-ops
  for ~6 weeks. Added a _spawn() seam used by all three drivers, a tests/conftest.py autouse
  fixture that replaces it with a raising stub (no test can spawn a real session), and rewrote the
  batch tests to patch _spawn and assert on the spawned argv with synthetic year-2999 dates. Also
  fixed the same staleness class in test_find_lb_folders_no_audio.py, which treated
  find_lb_folders' (found, excluded) tuple as a dict. Suite: 314 passed / 0 failed in 26s, from
  4 failed / 662s.

[2026-07-27] — docs/analysis: TODO-273 item (c) — embedding second pass over the contradicted
  corpus; file BUG-278 (rule_d dead in live sessions)
Added: tools/tapematch/emb_second_pass.py + CONTRADICTED_EMB_SECOND_PASS.md: second discriminator
  over the 1,822 curator-contradicted pairs, using the nmfp embedding (emb_score /
  emb_score_global) — the one persisted audio signal the metadata census did not use, and the only
  one with a calibrated production bar (addon_links.rule_d, t_emb 0.75 both-convention). Metadata +
  persisted-metric only: reads observations.db, decodes no audio, writes nothing back. Tiers over
  all 1,822: A rule_d-qualifying 46, B elevated 69, C control-like 1,655, no_emb 52.
Resolved: TODO-273 item (c) — the 377 `unexplained` pairs are NOT a hidden failure class. 333
  (88.3%) sit in the curator-silent negative-control emb band; combined with the census (clean on
  every metadata axis) the reading is curator label noise with no textual marker. Report states the
  caveat explicitly: the embedding recalls only 59% of confirmed pairs at that floor, so tier C is
  absence of evidence, not proof of difference. No new matcher is justified by this population.
  Corpus-wide reframe: contradicted emb quartiles (0.132/0.212/0.362) are indistinguishable from
  the 15,310 curator-silent different pairs (0.128/0.220/0.325) vs confirmed same-source at
  0.467/0.909/0.975.
Found: BUG-278 — addon_links.rule_d has never fired in a live tapematch session. cli.py's
  _pair_metrics() omits emb_score/emb_score_global from the dict passed to verdict.pair_links, so
  _rule_d_emb_both hits its None guard and abstains on every pair; emb_live.py populates the
  columns from _log_to_obs_db(), one stage after clustering has decided the verdict. The rule
  shipped enabled 2026-07-04 with a zero-new-FP calibration. Consequence: the 46 tier-A pairs are
  stale verdicts, not a matcher gap. Transitive corpus effect if wired: 58 curator-claimed + 80
  curator-silent pairs flip to same_family across 80 dates. Filed rather than patched — the
  wiring fix needs emb scores computed before clustering, not just two extra dict keys.
Validated: BUG-278's gate — the corpus-wide flips scored against the curator's own stance before
  proposing the fix. Separating lb_says_same=0 (EXPLICIT denial) from NULL (silent) is what
  resolves it: rule_d fires on 20.16% of claims-same (732/3,631), 4.17% of silent (721/17,293),
  0.39% of explicit denials (12/3,038) — a 52x discrimination, and 10 of those 12 already carry
  corr >= 0.83 so the primary signal merges them anyway (curator label noise, TODO-201's class).
  Of the 138 flips: 58 claimed-same, 79 silent, and exactly ONE contradicts an explicit denial
  (1999-11-09 LB-02737/LB-04289). That is the entire measured FP exposure — gate PASSED, fix
  unblocked. The earlier "80 unvalidated silent merges" framing was wrong: curator silence is not
  curator disagreement. Watch items recorded, neither blocking: 1978-03-09 is the only date where
  rule_d links every pair (whole date collapses to one family), and 156 of 793 rule_d-firing dates
  have median emb >= 0.60 (the BASELINE.md Task 8 same-show confound).

[2026-07-27] — fix/docs: close TODO-184 (polarity won't-ship), census the curator-contradicted
  corpus (TODO-273), file BUG-277
Fixed: tools/tapematch/validate_polarity.py: two defects in the TODO-184 stage-3 harness. (1) The
  POLARITY_RESCUE_RE regex matched source names with (\S+)/(\S+), but cli.py:486 emits folder
  names ("1994-10-23 Chicago (LB-12345)") which always contain spaces — so polarity_rescue_fired
  was hardcoded-false by construction on all 4,033 pairs of an already-completed 64.5-hour run,
  making it read as "the rescue never fired". Now matches on the double-space field delimiters,
  verified against three real name formats. (2) Self-pairs (lb_a == lb_b) from latest_pairs were
  scored as spurious new merges; now skipped. Underlying cause filed as BUG-277.
Added: tools/tapematch/census_contradicted.py + CONTRADICTED_CENSUS.md: metadata-only census
  (no audio decoded) classifying all 1,822 curator-contradicted pairs across 939 dates into
  priority-ordered failure buckets — alignment_failure 806 (44.2%), unexplained 377,
  duration_mismatch 316, label_contradiction 308, lb_collision 10, segment_patchwork 5. Headline:
  the patchwork/segment class is ~52 pairs (2.9%), not the corpus, so the corpus-scale framing
  that motivated TODO-273 was wrong by ~35x; alignment failure (ratio-lock never achieved) is the
  plurality at 44–70%. Also measures the curator evidence standard: the stock "same clapping wavs
  at end of dXtY" justification appears in 54.7% of contradicted claims vs 39.7% of confirmed
  ones, and is the one cue BASELINE.md Task 8 proved machine-unverifiable.
Changed: TODO.md/TODO_DONE.md/BUGS.md: TODO-184 closed won't-ship — the polarity strand is a dead
  end (max corr improvement ~0.008 across 4,033 pairs; code retained flag-off). TODO-273 filed,
  then rescoped the same day after discovering its original scope duplicated TODO-185, cancelled
  2026-06-25; the exact spike proposed (contiguous-run over residual_corr windows) already existed
  as calibrate_contig_run.py and returned zero. TODO-204 remeasured: band is 50 pairs not ~73 and
  its FN side fell 34→11, so the ceiling is ~+11 TP not +34; the band separates perfectly by
  curator testimony (11 fn_lowcorr all contradicted, 39 negatives none). BUG-210 repro confirmed
  after 5 weeks open — this session created the stray file itself via a guessed DB path in an ad
  hoc query; not an application bug.

[2026-07-27] — refactor(gui): retire the AppShell Topbar (TODO-274, reverses TODO-179 won't-do)
Changed: gui_next/src/renderer/src/components/AppShell.tsx: −145 lines removing the Topbar
  component (52px header) and its deriveCrumbs() helper — breadcrumb trail, per-screen actions
  slot, and global search field all gone, reclaiming vertical space for screen content. The
  appShell.search key was removed from all six locale files; all remain at 1,725 keys (parity
  intact, no /gui-next-i18n needed for a removal). Work was done in a prior session that ended
  without bookkeeping; recorded here retroactively. Verified before commit: no dangling Topbar/
  deriveCrumbs/appShell.search references under gui_next/src, gui-check PASS (node types 0,
  renderer types 0, production build clean). TODO-274 left OPEN because TODO-179 required a
  concrete decision on where breadcrumbs and global search relocate to, and that decision is not
  recorded — both affordances are currently removed rather than moved.

[2026-07-25] — feat: Pipeline Auto-reconcile toggle for the LBDIR stage (TODO-271)
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: a fourth toolbar toggle,
  Auto-reconcile (off by default), sitting between Auto-rename and Auto-collect. When on, any row
  whose LBDIR step lands yellow on missing_files/extra_files gets one unattended reconcile attempt:
  /api/lbdir/reconcile preview -> apply the safe subset -> re-run the lbdir pipeline step, so the
  row repaints from the backend's own verdict (green if it now passes, still yellow if not).
  The safe subset is deliberately narrower than the manual panel's: only MD5-matched rename and
  site/files-copy proposals are applied, plus extras moved to /extras/. Name-only matches are
  skipped — those are a different revision of the file, so renaming one converts a `missing` into
  a `mismatch` and would take a yellow row red; they still wait for a human. Rows with nothing
  safely actionable are left untouched. Serialized through reconcilingRef (reconcile hashes every
  file in the folder — one folder at a time); autoReconciledRef caps it at one attempt per row.
Added: gui_next locales: pipeline.autoReconcile / autoReconcileHint and the
  pipeline.lbdir.toast.autoReconciled / autoReconcilePartial toasts (en + de/fr/es/it/nl).

[2026-07-25] — fix: File Integrity scans now appear in the activity tray (BUG-276)
Fixed: backend/activity.py: the activity tray showed no file-integrity index/deep-verify runs.
  Those scans live in the newer backend/file_integrity.py subsystem (per-mount, parallel workers),
  not the older integrity_monitor the "scanning" adapter reads — so they were invisible to
  /api/activity/jobs. Added a multi-job source (_file_integrity_jobs) that expands each running
  mount scan into one activity record (per-mount id, stable "file_integrity" kind, indeterminate
  bar for index mode, running->finished edge into history), wired into snapshot().
Changed: backend/app.py: /api/file-integrity/scan/cancel now also reads mount_id from query args
  so the tray's Stop button (POSTs no body) can cancel a specific mount's scan.
Added: gui_next locales: appShell.statusBar.activity.file_integrity label (en + de/fr/es/it/nl).

[2026-07-25] — feat: Gaps screen retired — coverage folded into the Library performance lens (TODO-270)
Added: backend/gap_analysis.py: uncirculated_dates() — every olof_events concert date that
  classify_date() calls 'gap' or 'future', returned as {date_iso, coverage, venue, city, tour}
  with coverage renamed to the user-facing 'uncirculated'/'upcoming'. Covered/partial dates are
  skipped: those already reach the Library as entry-derived rows.
Added: backend/db.py: get_performances() unions those in as recording-less rows (recordings: [],
  status "Missing", id = the olof date_iso), skipping any date an entry-derived row already
  claims. Ordinary rows never carry `coverage`, so its presence IS the olof-only marker — 267
  such rows at ship time (259 uncirculated + 8 upcoming) on top of 3,837 entry-derived, 4,104 total.
Added: gui_next/.../components/library/DetailPanel.tsx: OlofShowZone — the Olof tab for
  olof-only rows. They have no lbNumber to key /api/olof/date or /api/olof/compare on, and no
  bobdylan_shows-backed perf.setlist either, so it falls back to perf.id (always the olof
  date_iso for these) and fetches the show drill-down. OlofEventCard's `songs` is now optional
  since that payload carries no song join.
Changed: gui_next/.../screens/ScreenLibrary.tsx: rollupOf() takes the whole PerformanceRow and
  branches on the backend's explicit coverage marker BEFORE the recording-count inference — an
  olof-only row has zero recordings, so count-based logic alone can't tell "no tape exists" from
  "we hold none of the tapes that do". New 'uncirculated' view in the Views menu; the Coverage
  facet's 'Undocumented' state splits into 'Uncirculated' + 'Upcoming' (both mute-toned).
Removed: gui_next/.../screens/ScreenGaps.tsx (586 lines) and its /gaps route, sidebar entry,
  'gaps' NavId, gaps icon path, command-palette note, and screen-tour step. Also the
  docs/index.html showcase tile and docs/screenshots/gaps.png, which advertised the dead screen.
Removed: backend/gap_analysis.py: get_summary(), get_grid(), get_year_detail() and the
  /api/gaps/summary|grid|year/<year>|date/<iso> routes — the grid they served has no consumer
  now. The drill-down survives, renamed to GET /api/shows/<date_iso>/olof.
Removed: library.coverage.noSource + library.coverageValue.undocumented from all six locales —
  the states they labelled no longer exist. The new uncirculated/upcoming keys were translated
  for de/fr/es/it/nl.
Changed: tests/test_gap_analysis.py drops the grid/summary/year suites and covers
  uncirculated_dates(); new tests/test_performances_uncirculated.py covers the get_performances
  union (18 tests total, 1042 in the full suite, all passing).
Note: classify_date() compares against today, so a show flips 'upcoming' → 'uncirculated' the
  morning after it happens — visible now as a Library row reading "No recording circulates" for
  a concert played last night. Pre-existing classifier semantics, carried over unchanged.

[2026-07-24] — fix: Gaps screen loaded in ~12s — collapsed 66 requests into one (BUG-275)
Fixed: gui_next/src/renderer/src/screens/ScreenGaps.tsx: the grid rendered one YearRow per
  year (65 of them) and every YearRow ran its own useQuery against /api/gaps/year/<year>, so
  mounting the screen fired 1 summary + 65 year requests. Each of those re-ran the
  full-corpus coverage scan and threw away all but one year. Measured 11.8s to populate at
  browser concurrency — and 6-way concurrency was *slower* than serial (11.8s vs 2.9s)
  because the parallel requests contend on SQLite. ScreenGaps now issues a single
  ['gaps-grid'] query and hands each year its cells as a prop; YearRow has no query at all.
Added: backend/gap_analysis.py: get_grid() — one pass that computes the entry coverage maps
  and olof event grouping ONCE and emits totals plus every year's date cells together.
  Cells are slim ({date_iso, coverage, label}) because the grid only draws a 14px square
  with a tooltip; the venue/city label is now joined server-side. Exposed as
  GET /api/gaps/grid in backend/app.py. get_summary/get_year_detail/get_date_detail and
  their routes are untouched and kept for API compat.
Changed: tests/test_gap_analysis.py: TestGetGrid asserts get_grid()'s totals and per-year
  counts match get_summary(), and that a year's date_iso order matches get_year_detail().
  Warm endpoint timing after the change: 47ms for the whole 320KB grid.

[2026-07-24] — feat: Disk Scanner — find audio folders on disk for bulk collection add (TODO-250)
Added: backend/disk_scanner.py: os.scandir walk over user-defined roots, reporting every
  directory that *directly* holds lossless audio. Prunes hidden dirs, DEFAULT_EXCLUDES
  (node_modules/.git/system paths) plus caller-supplied names, and never follows symlinked
  dirs (a symlink into an already-walked tree would loop or double-report). Background job
  shape (module job dict + lock, start_scan_async/get_scan_status/cancel_scan) deliberately
  mirrors integrity_monitor so the GUI polls both identically. Per-folder LB resolution:
  existing my_collection row → single folder_lb_link pin → LB-NNNNN name convention;
  unattributable folders are listed but not addable, since my_collection keys on lb_number.
Added: backend/app.py: POST /api/scanner/scan (400 empty roots, 409 already running),
  POST /api/scanner/scan/cancel, GET /api/scanner/scan/status, POST /api/scanner/add
  (per-path {ok, lb_number, error} with no_lb / already_in_collection); scanner_roots +
  scanner_excludes added to the /api/db/settings key list.
Added: gui_next/.../screens/ScreenScanner.tsx: new /scanner screen in the Ingest nav group —
  root list via the native folder picker + comma-separated excludes (both persisted), Scan /
  Cancel with live dirs-scanned/found progress, and a results table with per-row checkboxes
  and bulk add. In-collection rows are greyed and unselectable; no-LB rows show a warn pill.
Added: tests/test_disk_scanner.py: 20 tests — pruning, extension filtering, cancel, repeated
  roots, all three LB-resolution paths, and the add-result branches (insert stubbed, since
  db.add_to_collection goes through the write queue that binds to the first DB in a process).
Changed: tools/debug_screens.json: /scanner added to the screenshot tour.
Changed: gui_next/.../locales/*.json: new scanner.* namespace + appShell.nav.scanner (en) +
  de/fr/es/it/nl via DeepL (13,478 chars across two runs).

[2026-07-24] — fix: Gaps screen surfaces backend failures instead of hanging (BUG-274)
Fixed: gui_next/.../screens/ScreenGaps.tsx: the summary, year and date queries all used
  fetch().then(r => r.json()), which resolves for every HTTP status — react-query never
  saw an error, so a failed summary left the screen on "Loading…" forever and failed year
  requests left each row stuck on "…". New fetchJson<T> helper throws on !res.ok.
Added: gui_next/.../screens/ScreenGaps.tsx: three error surfaces driven by isError —
  GapsError (terminal, with a retry button; deliberately distinct from GapsUnavailable,
  which means the chronology genuinely isn't installed), a per-date error + retry in the
  detail pane, and a "Failed to load" marker on year rows.
Changed: gui_next/.../locales/*.json: new gaps.error.* namespace plus gaps.grid.error /
  gaps.detail.error (en) + de/fr/es/it/nl.

[2026-07-24] — feat: Saved smart views — named Library filter sets in the sidebar (TODO-269)
Added: gui_next/.../lib/libraryRows.ts: shared Library recording data layer extracted
  out of ScreenLibrary — RecordingRow + filter types/helpers (VALID_RATINGS,
  RATING_RANK, extractYear, decadeOf, HEALTH_CHECK), buildRecordingRows(),
  useLibraryRows(enabled), Set-based filterRecordingRows()/filtersToSets(), and
  countForView() for the sidebar badges, so screen and sidebar count identically.
Added: gui_next/.../lib/libraryFilterStore.ts: the persisted Library filter store
  moved out of ScreenLibrary (so the sidebar can drive it) plus
  snapshotRecordingFilters() / applyRecordingFilters() / hasRecordingFilters().
Added: gui_next/.../lib/savedViewsStore.ts: persisted useSavedViewsStore
  (localStorage key lbb-saved-views) — views[] with add/rename/remove.
Added: gui_next/.../components/SavedViews.tsx: sidebar "Saved Views" section —
  click applies the view's filters and jumps to the Library, hover reveals
  rename/delete, badge shows a live recording count; hidden when no views exist.
Added: gui_next/.../screens/ScreenLibrary.tsx: ⭐ "Save view" toolbar button
  (recording lens, shown once a filter is active) + naming modal with a suggested
  name built from the active filters; ~230 duplicated lines dropped in favour of
  the shared modules above.
Fixed: gui_next/.../components/AppShell.tsx: the SavedViews section rendered after
  every nav group, which put it below the fold of the scrollable sidebar — it was
  in the DOM but never visible. Now rendered inside the Library group, where the
  views belong.
Changed: gui_next/.../locales/*.json: new savedViews.* namespace (en) + de/fr/es/it/nl
  via DeepL (6,232 chars this run).

[2026-07-24] — fix: deterministic tombstone-migrate test (CI flake)
Fixed: tests/test_lb_master.py: test_migrate_deletes_tombstones raced init_db()'s
  fire-and-forget migrate_lb_master(wait=False) backfill — when the background
  migrate populated lb_master first, the test's synchronous call short-circuited
  on its existing>0 guard and returned before the async tombstone DELETE drained,
  intermittently asserting 1==0 on loaded CI runners. Flush the FIFO write queue
  before asserting.

[2026-07-24] — feat: Timeline navigator — zoomable Decade→Tour→Night grid (TODO-268)
Added: backend/timeline.py: live-computed timeline rollup (get_summary /
  get_decade_detail / get_tour_detail), mirroring gap_analysis.py — concert-only
  olof events joined to entries by resolved ISO date, best letter-grade per night
  via a new Python GRADE_RANK, no derived table. Feature-detects olof_events
  absence (available:false). 21 tests in tests/test_timeline.py.
Added: backend/app.py: GET /api/timeline/summary, /decade/<int:decade>,
  /tour?name=&decade= (read-only, gaps-route error convention).
Added: gui_next ScreenTimeline.tsx (route /timeline, Library nav group + palette,
  new timeline Icon glyph): Decade→Tour→Night zoom with breadcrumb back-out; cells
  colored by best grade on a new sequential --lbb-seq-* ramp in tokens.ts
  (single info-blue hue, dataviz-validated light+dark, its own applyTheme emission
  loop). In-app dossier iframe viewer with an "Open full export…" hand-off to the
  existing DossierExportModal. i18n across all 6 locales.
Changed: enforced a three-state model (graded / circulating-ungraded / no-tape)
  across all three tiers so ungraded-but-held nights — most of the 2020s — stay
  clickable to their dossier instead of reading as "no tape"; get_tour_detail
  gained a per-night circulating flag and get_decade_detail a circulating_count.
Fixed: backend/app.py: /api/dossier/html now honors inline=1 to drop the
  Content-Disposition: attachment header — the attachment disposition made the
  new iframe viewer render blank; the export/download flow (default) is unchanged.

[2026-07-24] — feat: filtered + "Not in collection" HTML export for My Collection
Added: backend/app.py: /api/collection/export/html/missing — exports the "Not in
  collection" LB list (database.get_missing_from_collection()) through the same
  interactive single-file HTML report as the main collection export, with a
  column set suited to never-owned entries (lb, status, date, location, rating,
  description).
Changed: backend/app.py: /api/collection/export/html now accepts an optional
  lb_numbers param (comma-separated), matching the existing pattern on
  /api/collection/export/m3u, so the export can be restricted to a subset
  instead of always dumping the full collection.
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx: the "Export
  HTML" button now passes the currently filtered/searched rows' LB numbers to
  the backend, so any active filter chip, search text, year, or copy-level
  filter narrows the export instead of always exporting everything. Added an
  "Export HTML" button next to "Export CSV" on the "Not in collection" tab,
  respecting its public/private toggle the same way.

[2026-07-24] — feat: file-level collection integrity — per-file bit-rot inventory (TODO-267)
Added: backend/file_integrity.py: durable per-file hash inventory over every file on
  every mount, to catch bit rot / silent corruption. The two existing hash stores
  structurally can't: pipeline_file_hash is a (size, mtime) cache and rot never touches
  mtime; collection_integrity_status only checks lbdir-manifest files and decodes FLAC
  for ffp (the slow part). Two modes from one read pass — index (stat-skip, fast) keeps
  the inventory current; verify (full re-read) detects rot — plus verify_batch, the
  rolling nightly slice that draws oldest-last_verified first so successive runs advance
  through the collection instead of re-checking the head of the walk. Triage: hash
  differs + stat unchanged => rot (baseline hash deliberately KEPT for restore
  confirmation); hash differs + stat moved => legitimate edit, re-baselined; unreadable
  => I/O error; inventoried-but-absent => missing (complete pass only, so a budgeted or
  cancelled run can't mass-flag). One worker per mount — parallel across spindles, serial
  within one (HDD seek thrash). rebaseline() is the only path that clears a sticky rot
  flag, operator-driven so rot can't launder itself into a new baseline.
Added: db.py: file_inventory (mount_id, rel_path -> xxh3_128 + sha256 + size/mtime +
  status + last_verified) and file_integrity_scans run history, indexed on
  (mount_id, last_verified) to drive the rolling verify; batched upsert/verify/flag/
  rebaseline helpers, per-mount summary, problems (rot-first), history (with mode filter).
Added: backend/app.py: /api/file-integrity/{scan,scan/cancel,status,summary,problems,
  history,rebaseline}. One scan per mount (409 on collision); different mounts scan
  concurrently. file_verify_* meta keys added to the settings allowlist.
Added: backend/scheduler.py: opt-in rolling deep-verify scheduler (file_verify_enabled).
  A full verify reads every byte (~15 h/mount at the ~125 MB/s a real walk sustains here),
  so instead of one blocking run it fires a budgeted slice per mount per night — whole
  collection covered in ~a month. Interval clock reads verify runs only, so a manual index
  scan can't defer it; _meta_float tolerates garbage meta rather than crashing the worker.
Added: gui_next ScreenFileIntegrity.tsx (/fileintegrity, Settings group, shield icon):
  collection roll-up, per-mount cards with Index / Deep Verify + live progress + Stop,
  rolling-verify toggle, rot-first problems list with per-file Re-baseline, recent-scans
  strip. Health badge says "clean" (no problems), not "verified" — an indexed mount is
  baselined, not deep-verified.
Fixed: ScreenFileIntegrity.tsx: render crash (mounts.map) — the /api/collection/mounts
  endpoint returns {mounts:[…]}, not a bare array; caught via /verify --electron before
  it shipped.
Changed: requirements.txt: pin xxhash==3.7.0 (was transitive-only via pybloom_live);
  hash choice is not the speed lever — every candidate outruns the disk, so both digests
  come from one read pass and sha256 is kept for cross-checking against checksums /
  lbdir manifests / site_inventory.local_sha256.

[2026-07-23] — feat: GUI for the preservation stack — Preservation tab + service layer (TODO-266)
Added: backend/preservation.py: single-instance background job runner for the four
  preservation operations (verify / baseline / linkcheck / snapshot). Jobs run on a
  daemon thread and expose a pollable status snapshot shaped like
  site_crawler.get_crawler_status, so the Scraper screen's existing status-diffing
  consumes it unchanged. Also serves the snapshot inventory (manifest stats + seal,
  read without re-hashing) and the report list/reader — read_report resolves and
  range-checks paths so a caller cannot walk out of data/exports/.
Changed: tools/verify_site_mirror.py, tools/check_mirror_links.py,
  tools/make_site_snapshot.py: optional progress_cb/should_stop hooks on verify(),
  baseline(), check_links() and make_snapshot(); defaults keep every existing CLI
  call byte-identical. verify/baseline stop between rows, the link check between
  pages, a snapshot between build stages — and a cancelled snapshot DELETES its
  partial directory, since only a sealed snapshot means anything. Results carry a
  `cancelled` flag and append CANCELLED to their summary. A cancelled verify skips
  the orphan sweep (a partial file list would report every unvisited file as an
  orphan). Also drops a pre-existing unused `hashlib` import from
  make_site_snapshot.py — the one real use lives inside the embedded-verifier string.
Added: backend/app.py: /api/preservation/{start,status,stop,snapshots,reports,report}.
  start 409s on a second concurrent job and 400s on an unknown job name. No upload
  path anywhere — distribution stays a manual human act.
Added: gui_next ScreenScraper.tsx: Preservation tab (curator-gated /scraper, which
  already owns the mirror these tools operate on). Job chips each carry a one-line
  explanation and their own options — sample size + full-walk for the link check,
  with-db / verify-first / tar for snapshots, with an inline warning when
  verify-first is cleared. Run/Stop, a 2 s poll driving progress + stage pill + log
  lines, a per-job result StatGrid with failed/cancelled banners and an Open report
  button, a mirror block with the restore one-liner, and a "Snapshots on disk" table
  (files, size, seal, sealed state, folder-open action).
Fixed: gui_next ScreenScraper.tsx (BUG-273): the Crawler and Bootleg history tables
  misaligned every column — TR injects a 3px leading <td> edge bar, so colgroups need
  a leading <col width=3> and theads a leading <TH>. Both omitted it; found by
  measuring header vs cell bounding boxes while verifying the new tab, which had
  inherited the same mistake. Header/cell left edges now match exactly.
Fixed: gui_next ScreenScraper.tsx: the first poll of a session replayed the last
  finished run as if it had just started (the backend keeps terminal status) — the
  first observation now seeds the diff refs without logging. Progress lines also read
  "linkcheckstarting…", since padEnd(9) on a 9-char job name emits no separator.
Added: tests/test_preservation_service.py (19): job lifecycle, error surfacing,
  single-instance guard, cooperative cancellation, progress reporting, snapshot and
  report inventory, traversal refusal, and back-compat of the new tool kwargs.
Note: verified against the live mirror — progress ticked to 87,250/115,115 rows and
  a stop landed cleanly at 87,499 hashed with 0 drift; in Electron on Xvfb a
  GUI-driven link check ran 504 pages / 3,595 links in 24.5 s with live progress and
  a green summary. Full backend suite 983 passed; gui-check green. i18n: 65 new keys
  under scraper.preservation filled for de/fr/es/it/nl via DeepL (10,408 chars);
  "unsealed" came back untranslated in de/it and was set by hand.

[2026-07-23] — feat: sealed snapshots + restore test — preservation stack complete (TODO-265 B2/B3/B4)
Added: tools/make_site_snapshot.py: builds data/exports/snapshots/lbsnap-YYYY-MM-DD[.N]/
  — site mirror + both olof mirrors + a full-channel DB export (export_master_db
  called in-process, never over HTTP), staged with os.link hardlinks so a 2.9 GB
  snapshot costs only the DB export in real disk. Writes manifest.txt
  (sha256␠␠size␠␠relpath, sorted for reproducibility), seal.txt (one hash over
  the manifest), a recipient-facing README.txt and a standalone stdlib
  verify_snapshot.py. Runs the B1 verify first and refuses to seal a mirror with
  missing files or drift (--no-verify overrides, logged loudly). --tar adds a
  .tar.gz + .sha256 sidecar; --no-db skips the export. No upload path anywhere,
  by design — distribution is a manual human act.
Added: tools/check_mirror_links.py: restore test — resolves internal
  href/src/action links against files on disk across 4 seed pages (home, LBM
  by-number index, year index, bootleg index) plus a seeded 500-page sample;
  --full walks everything. Seed-page breaks fail the run, sample findings are
  report-only unless --max-broken is given. Read-only; --report → data/exports/.
Added: tests/test_site_snapshot.py (15) + tests/test_mirror_links.py (12) —
  hardlink staging, embedded verifier pass/tamper/deletion, forged-manifest
  seal detection, build determinism, refusal to seal a drifted mirror, an AST
  check that the snapshot tool imports no network module; link resolution for
  relative/absolute/encoded/directory targets, seed gating, deterministic
  sampling, read-only behaviour.
Changed: PROJECT.md: new "Preservation stack" section under Site Crawler — the
  hash-provenance rule, the three tools, the restore one-liner
  (`python3 -m http.server -d data/site 8080`) and the no-upload constraint.
  instructions/README.md + FABLE_PLATFORM_ROADMAP.md §5 marked shipped; spec
  moved to instructions/complete/ (B4).
Note: real runs — snapshot of 116,150 files (2.9 GB apparent, 359 MB real)
  built in 39.8 s and verified by its own embedded verifier under
  /usr/bin/python3 with no repo and no venv: "116150 file(s) verified, 0
  problem(s)". Link check: all 4 seed pages resolve fully; 2 dead links in the
  500-page sample are findings for tj, not auto-fixed —
  detail/LB-00718.html → LB-00000.html and
  lbbcd/LBBCD-song-1096.html → LBBCD-tuit94-319.html (both look like authoring
  typos on the live site rather than mirror gaps).
Note: the checker ignores Word's <link rel="File-List"/themeData/
  colorSchemeMapping> export scaffolding. Much of the site was authored in Word,
  which emits those on every page; counting them failed all four seed pages over
  files no browser ever fetches.

[2026-07-23] — feat: site-mirror self-verification (TODO-265 bite B1)
Added: tools/verify_site_mirror.py: preservation-stack B1 — re-hashes the site
  mirror and reports missing files, hash drift, orphans and unbaselined rows.
  `--baseline` records the on-disk hash for rows that lack one; default mode is
  read-only verification; `--report` writes a dated file to data/exports/.
  Non-zero exit on missing/drift. Safe to run while the app is up.
Added: backend/db.py: site_inventory.local_sha256 (idempotent PRAGMA-guarded
  migration + DDL). body_sha256 is the hash of the RAW HTTP body, but HTML is
  saved link-rewritten, so it can never match the file on disk — re-hashing
  against it would have reported ~115k false drift errors. local_sha256 records
  the bytes as saved and is the only sound baseline for HTML.
Changed: backend/site_crawler.py: _save() now returns (path, sha256-of-written-
  bytes) and the crawl loop stores it as local_sha256, so every future fetch
  records both hashes. New public is_rewritten_html() is the single source of
  truth for that HTML-vs-verbatim distinction (previously duplicated inline in
  _save and the content_type expression). HTML is written via write_bytes rather
  than write_text so saved bytes are not newline-translated on Windows.
Added: tests/test_site_mirror_verify.py: 14 tests — baseline populates both
  file kinds, a verbatim file disagreeing with body_sha256 is flagged and
  deliberately NOT baselined (rot must keep surfacing), rewritten HTML never
  false-drifts, tamper/delete/stray → drift/missing/orphan, CLI exit codes.
Note: first real run baselined 114,915 files (26.9 s) and verified clean —
  0 missing, 0 drift, 0 verbatim-hash mismatches, zero false HTML drift. It
  also found 171 orphans (140 files/LBF-*, 31 detail/LB-*.html) — files the
  entry scraper downloaded into the mirror without a site_inventory row, since
  it writes entry_files instead (see site_crawler.py:415-419). Benign and
  self-healing on the next full crawl; noted so B2 stages the directory tree
  rather than building its manifest from the inventory table.

[2026-07-23] — fix: library crawl wedged by read-only example folder (BUG-272)
Fixed: tools/tapematch/tapematch_session.py: BUG-272 — the detached library
  crawl died 2026-07-22 20:06 with "10 consecutive failures overall" and sat
  idle ~17 h with 436 dates outstanding. Root cause: some source folders on the
  archive volumes are mode 0o555 and shutil.copytree preserves that mode on the
  copy it leaves in EXAMPLES_DIR; a read-only directory's entries cannot be
  unlinked, so clean_examples()' rmtree raised PermissionError at step [3] of
  every subsequent date — before any work — on one leftover folder
  ("1974-01-30 … (LB-03652)"). New _make_writable() restores the owner write
  bit across a tree; clean_examples() calls it before rmtree and copy_folders()
  strips the read-only mode right after each copytree, so a read-only source can
  no longer wedge the crawl.
Changed: data/tapematch/crawl_skip.txt: cleared six innocent dates (1974-01-31,
  02-02, 02-03, 02-04, 02-06, 02-09) that run_crawl.sh skip-listed only because
  each hit the shared PermissionError three times; they are back in the queue.
Added: tools/tapematch/tests/test_make_writable.py: regression tests — a 0o555
  tree blocks rmtree, _make_writable un-blocks it, missing paths are a no-op.

[2026-07-22] — feat: persisted Library view + instant relaunch (BUG-271)
Fixed: gui_next App.tsx: BUG-271 — first click on Library/Collection after a
  cold launch still took 12-15 s / 5 s (BUG-270's fix was warm-path only: cold
  954 MB DB page-ins + 3 bulk fetches staggered 3 s after launch + 22 MB JSON
  parse, worsened by library-crawl I/O contention). React-query cache for the
  four bulk keys (collection-prefetch, library-catalog/-performances/-badges)
  is now persisted to IndexedDB (PersistQueryClientProvider + idb-keyval,
  structured clone — no 60 MB JSON.stringify, 7-day maxAge, buster
  lbb-cache-v1); on relaunch the tables render instantly from last session's
  snapshot while a staggered background refetch (skips queries already fetched
  this session) reconciles. gcTime raised to maxAge so restored queries
  survive until re-persisted.
Added: gui_next App.tsx: last-route persistence — the app reopens on the
  screen it was closed on (localStorage lbb-last-route, RouteRestorer inside
  HashRouter; curator-gated routes still redirect via CuratorRoute).
Added: gui_next ScreenLibrary.tsx: useLibraryFilterStore now persisted
  (zustand persist → localStorage lbb-library-filters, Set-aware
  replacer/reviver) and extended with the remaining view state: lens,
  rec/perf groupByYear, collapsedYears, sort key/dir, detail-panel open,
  perf expandedShows/collapsedFams. Closing and reopening the app restores
  the exact filtered view (e.g. Year: 1999). Perf-lens auto-expand of the
  first show is skipped when a persisted expandedShows set was restored.
Changed: gui_next package.json: + @tanstack/react-query-persist-client
  (hoists react-query to 5.101.4 within ^5.80.5) and idb-keyval 6.3.0.
Changed: tools/debug_screens.json: tour now navigates to "/" first — app
  launch no longer lands on Home by default (route restore), so the first
  screenshot must pin its screen. Verified: /gui-check green; Tier B Electron
  two-phase persistence test (set Year:1999, quit, relaunch → Library
  restored, filtered, rendered ~4 s after process start) + full 20-screen
  tour PASS.

[2026-07-22] — fix: open-bug sweep — test temp-file containment (BUG-253/254), dead mirror URLs (BUG-255), lbdir unreconcilable entries (BUG-252), BUG-120 forensics
Fixed: backend/checksum_utils.py: BUG-252 — unreconcilable lbdir entries
  (self-referencing manifests, server-regenerated DigiFlawFinder reports; new
  _REGEN_REPORT_RE + _is_unreconcilable_entry) no longer count as missing or
  fail in verify_folder_lbdir (detail statuses stay visible) and are excluded
  from find_reconcilable_files / find_site_recoverable_files proposals.
  find_reconcilable_files also gained BUG-174's name-based fallback: on-disk
  near-duplicates (LBF-prefix-stripped basename match) surface as
  matched_by:'name' rename proposals with expected_md5.
Changed: gui_next LbdirDetail.tsx + lbdirStore.ts: rename-proposal rows render
  name matches with warn edge + "MD5 mismatch" pill (same treatment as site
  proposals); ReconcileProposal type gains optional expected_md5/matched_by.
Changed: BUGS: BUG-120 closed after full forensics — LB-06548 track 09 and
  LB-12181 d18-2 are non-FLAC corrupt files sharing an identical 420KB prefix
  (cross-linked clusters on DYLAN2 → TODO-264 disk check + re-source);
  LB-12181 d18-7 audio is bit-perfect (PCM md5 matches ffp), container-only
  change; LB-12181 lookup-not-found is expected (site has no checksums for it).
Fixed: conftest.py: BUG-253 — session-scoped autouse fixture routes
  tempfile.tempdir + TMPDIR into pytest's self-pruning basetemp; leaked
  lb_*_test_* dirs / tmp*.wav no longer accumulate in /tmp (verified: two full
  919-test runs, zero leaks; 1,545 stale dirs cleaned up). BUG-254 (flaky
  test_mixed_shn_and_wav_checksums_still_matched) closed as shared root cause —
  its single 2026-07-16 failure matches the ENOSPC casualties BUG-253 documents.
Fixed: backend/site_crawler.py: BUG-255 — entry_files.downloaded is now
  tri-state (0 missing / 1 mirrored / 2 dead): the 404 branch marks the
  matching row downloaded=2 so permanently-dead attachment URLs (stale seeds
  from regenerated pages + source-mangled hrefs, all confirmed not_found/404
  in site_inventory) stop being re-seeded. One-time backfill marked all 88
  residual rows dead — missing-attachments count converged 88 -> 0, with no
  content loss (every affected LB already has corrected-name siblings
  mirrored). Docstring (backend/db.py get_missing_attachment_urls), PROJECT.md
  entry_files schema note, tests in tests/test_scraper_crawler.py.

[2026-07-22] — fix: Collection/Library first-launch load time (BUG-270)
Fixed: backend/db.py: get_collection_duplicates N+1 — one query per duplicate
  group (3,220 full scans, entries had no date_str/location index) cost 3.5 s
  of the 4.1 s /api/collection/prefetch response. Rewritten as a single
  grouped-members query + new idx_entries_date_location. Output is identical
  except the redundant per-entry "owned" flag (unread by the GUI) is dropped.
  Warm endpoint: 4.1 s -> 0.80 s.
Added: backend/app.py: global after_request gzip for JSON responses >= 256 KB
  when the client advertises gzip (level 1, ~0.2 s CPU). Cuts the bulk
  endpoints ~4x on the wire (prefetch 35.8 MB -> 9.9 MB, /api/search
  22.5 MB -> 6.3 MB); Chromium fetch() decompresses transparently, streaming
  (direct_passthrough) responses are skipped.
Changed: gui_next/src/renderer/src/App.tsx: warm-prefetch library-catalog,
  library-performances, and library-badges 3 s after launch (staggered so
  JSON.parse doesn't fight Home's first paint) — first Library visit now hits
  a warm react-query cache, same keys/staleTime as ScreenLibrary.

[2026-07-22] — docs: user-facing docs pass — website restored + real screenshots (BUG-269)
Fixed: docs/index.html: BUG-269 — the GitHub Pages marketing site had been
  clobbered by a copy of the schema page in 7a9548c5 (2026-06-30); restored
  from a32a853d and refreshed for the current app (Electron/React copy,
  12-card feature grid incl. Library/Pipeline/Gaps/TapeMatch/Trading,
  installer-based install cards, first-run wizard notes).
Added: docs/screenshots/: 7 real app captures (home, quicklookup, library,
  search, map, gaps, pipeline) taken with the sanctioned Tier A screenshot
  engine against live data; wired into index.html hero + 5-item showcase.
  QuickLookup shot uses real LB-08287 ffp lines; map retaken with settle wait
  so tiles render. screenshots/README.md rewritten as inventory + refresh
  recipe (was placeholder guide).
Changed: README.md: website/wiki/schema links + hero screenshot added.
Changed: docs/wiki/: GUI.md Screenshots section; Collection-Pipeline.md,
  Setlist-Sources.md screenshot links; Home.md pointer to user-facing
  surfaces. PROJECT.md docs/screenshots/ description updated.

[2026-07-22] — docs: wiki build-out — 5 new pages, all 15 topic pages fresh
Added: docs/wiki/Setlist-Sources.md, Show-Dossier.md, Master-Data-Sync.md,
  Collection-Pipeline.md, Integrations.md — coverage for the setlist corpora,
  dossier, master-data distribution, filing pipeline, and outbound
  integrations subsystems (previously undocumented in the wiki).
Changed: docs/wiki/ — all 10 pre-existing topic pages regenerated from current
  sources (schema v11, export channels, derived-data recompute chain,
  staircase/frozen-set calibration state, /verify sanctioning, 20-screen GUI
  list, TODO-234 rescore counts); Home.md index updated. PROJECT.md file
  structure line for docs/wiki/ updated (8 → 15 topic pages).
Changed: .claude/CLAUDE.md: Context Discipline now directs sessions (and
  subagent prompts) to the matching docs/wiki/ page for subsystem orientation
  before grepping PROJECT.md — wires the wiki into the standard workflow.
Added: tools/wiki_staleness.py — compares each wiki page's `> Sources:` paths
  (globs supported) against git commits newer than its `Status:` date; wired
  into .claude/hooks/session_brief.sh as a `[wiki]` briefing line (+0.03s) and
  into /wiki-update step 1, so staleness is detected automatically instead of
  by hand-maintained status flags. Caught its first error on first run:
  Collection-Pipeline cited instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md,
  which had been retired to instructions/complete/ — header fixed, plus
  Integrations/Master-Data-Sync headers tightened to full repo paths.
Commits: d21b7f2b, 9198df7d, 33030811, c466fde5.

[2026-07-22] — refactor: single screenshot engine — browser_driver.mjs retired into electron_driver.mjs --renderer-only
Removed: tools/browser_driver.mjs — the older Tier A driver (tj's call: one
  engine, keep a fast flag).
Changed: tools/electron_driver.mjs: new --renderer-only mode absorbs Tier A —
  headless Chromium vs the Vite server (dev 5173 / --preview 4173,
  --no-server supported), window.api shim, PNGs → .debug/; Electron mode
  unchanged (PNGs → .debug/electron/). scale-matrix guarded Electron-only;
  main-eval fails cleanly per-step in renderer mode via driver_core caps.
  Build policy: Electron mode builds unless --no-build; renderer dev mode
  never builds; --preview builds unless --no-build.
Changed: tools/driver_core.mjs header, PROJECT.md tools section,
  .claude/skills/verify/SKILL.md (tier table + commands now
  --renderer-only), .claude/settings.json (dropped browser_driver allow
  rule).
Verified: renderer-only full 20-screen tour 47/47 ok; Electron-mode
  navigate+screenshot ok; scale-matrix correctly rejected under
  --renderer-only.

[2026-07-22] — fix: Home screen responsive layout + activity-table column alignment (BUG-265, BUG-266); screenshot engine sanctioned
Fixed: gui_next .../index.css + ScreenHome.tsx: bottom row (Recent activity |
  Tonight/Tips) moved from inline '1.45fr 1fr' grid to .lbb-home-grid-bottom —
  minmax(0, …) columns so content can shrink, stacking to one column below
  1400px. Previously the activity widget was invisible at 1280x768 (the app
  minimum) and a ~40px sliver at 1440x900, with the right column overflowing
  off-screen. Top row likewise → .lbb-home-grid-top. (BUG-265)
Fixed: gui_next .../ScreenHome.tsx: both activity tables (main + full-log
  modal) declared 5-col colgroups against 6-cell body rows (TR auto-injects
  the edge-bar td + manual type-dot TD) — every value rendered one column
  right of its header and WHEN timestamps truncated at all sizes. Added an
  18px dot col + empty TH, widened WHEN to 140px, realigned empty-state rows.
  (BUG-266)
Changed: .claude/CLAUDE.md, .claude/skills/verify/SKILL.md,
  .claude/commands/gui-check.md: screenshot engine (browser/electron drivers)
  sanctioned for use on Claude's own initiative for visual gui_next changes —
  tj cleared it 2026-07-22; /gui-check remains the required baseline.
Verified: electron_driver size-matrix at 1280/1440/1920/2560 + full-log modal
  session; tsc node/web + production build all pass.
Fixed: tools/debug_screens.json: /verify tour file was stale — still navigated
  pre-refactor routes (/lookup, /verify, /rename, /lbdir → blank screens) and
  missed 7 current screens; rewritten to the 20-screen registry from
  lib/navigation.ts. (BUG-268)
Fixed: gui_next locales en/de/fr/es/it/nl: gaps.grid.yearGap split into
  yearGap_one/yearGap_other so year rows with one gap no longer read
  "1 gaps". (BUG-267)
Verified: full Tier A /verify tour (20 screens) — all render, no blank
  screens, no raw i18n keys; scraper/fingerprint redirect Home as designed
  (curator mode off).
Changed: tools/driver_core.mjs: wait-for action now passes through a `state`
  option ('visible'|'attached'|'detached'|'hidden') so sessions can wait for
  loading placeholders to disappear, not just for elements to appear.
Changed: tools/debug_screens.json: settle waits added — text=Loading detached
  (20 s) on library/search/bootlegs/tapematch/songs/attachments/map, first
  date-cell button on gaps — so the tour captures loaded screens instead of
  transient "Loading…" states; a timed-out wait degrades to the old behavior
  (step fails ok:false, tour continues). Re-run: 47/47 steps ok, all
  previously mid-load screens now capture settled data.

[2026-07-21] — feat: command palette (Ctrl+K) — global fuzzy navigation (TODO-263)
Added: gui_next .../lib/navigation.ts — NAV_GROUPS + nav types extracted from
  AppShell.tsx so the sidebar and palette share one screen registry (curator
  gating applies to both); AppShell now imports it.
Added: gui_next .../lib/commandRegistry.ts — framework-free command registry
  (registerCommands/getCommands) as the palette's extension point for future
  specs (activity center, dossier, gaps); v1 built-ins = one nav command per
  screen + action.checkUpdate (GET /api/flat_file/discover, footer outcome).
Added: gui_next .../lib/fuzzyMatch.ts — standalone subsequence scorer (weights
  consecutive runs, word-start hits, match position).
Added: gui_next .../components/CommandPalette.tsx — Ctrl/Cmd+K overlay mounted
  once in AppShell. Ranked query interpretation: LB pattern → "Go to LB-N"
  (/library?lb=N), fuzzy commands, then debounced /api/search entries (≥2 chars,
  stale-response guard, silent degradation). Escape/arrows/Enter/click wired,
  scroll lock + focus restore. SSE-backed actions deferred to the activity
  center per spec D4.
Added: en.json + de/fr/es/it/nl — top-level `palette` locale namespace.
Docs: PROJECT.md (command-palette architecture bullet); instructions spec moved
  to complete/, FABLE_IDEAS UI §1 marked shipped, README index updated.

[2026-07-21] — feat: unified activity center — status-bar job tray (TODO-262)
Added: backend/activity.py — declarative JOB_ADAPTERS table (15 workers) +
  snapshot() normalizing every polled worker into one shape (spec §2 A1),
  50-entry in-memory finished-job history, and an SSE tee registry (track())
  giving the 6 text/event-stream routes presence while streaming. New route
  GET /api/activity/jobs. Implements instructions/FABLE_ACTIVITY_CENTER.md.
Changed: backend/app.py — /api/activity/busy re-based on the same adapter table
  (response byte-compatible), which also closes its blind spots: spectrogram,
  tapematch-crawl, pipeline-run, and archive.org jobs are now visible (spec D-3);
  extracted 5 module-level status getters (zero behavior change); wrapped all 6
  streamed generators in activity.track() (payloads byte-identical).
Added: gui_next lib/activityStore.ts — single ref-counted poller (adaptive 5s
  idle → 2s running) feeding a status-bar activity tray in AppShell.tsx (running
  jobs with progress + elapsed, Stop via cancel_route, click-through to owning
  screen, error badge; §3 defaults D-1/D-2/D-4). 17 new locale keys across
  de/fr/es/it/nl. Old inline activity/busy poller removed.
Tests: tests/test_activity.py (8) + tests/test_activity_sse.py (4). gui-check PASS.

[2026-07-21] — chore(docs): /session-close now commits + pushes automatically
Changed: .claude/commands/session-close.md — added Step 8 (commit + push without
  confirmation) so bookkeeping always lands on the remote at session end; split
  the old Step 7 into consistency-check (7) + report (9). No more per-step
  "want me to commit/push?" prompts.

[2026-07-21] — ci: skip full suite on pure-bookkeeping (**.md-only) pushes
Changed: .github/workflows/ci.yml — added paths-ignore: ['**.md'] to the push
  trigger. The bookkeeping discipline structurally produces .md-only commits
  (CHANGELOG/BUGS_DONE/TODO ledger moves) after every code commit; each was
  re-running the full backend-tests + backend-smoke + gui-check matrix that the
  preceding code commit already ran (5 of the last 8 runs were pure bookkeeping).
  paths-ignore skips a push only when EVERY changed file matches, so mixed
  code+docs commits still run; PR-to-main stays the unconditional gate.

[2026-07-21] — fix(db): writer thread owns its connection's close, not shutdown()'s caller (BUG-264)
Fixed: backend/db_queue.py — DatabaseWriteQueue.shutdown() closed self._conn from
  the caller thread after join(timeout). When a write outlived conftest's 2s join
  under CI's contended disk, the caller freed the connection out from under the
  still-running writer thread — a cross-thread SQLite use-after-free that
  segfaulted the backend-tests job at teardown (exit 139, flaky). The writer
  thread now closes its own connection when it drains the shutdown sentinel;
  shutdown() only signals + joins. Distinct from the BUG-261/262/263 init_db
  thread leaks. Added TestWriteQueueShutdown regression tests; full suite 905
  passed locally.
[2026-07-21] — feat(backend): CI on GitHub Actions + synthetic fixture DB generator (TODO-261)
Added: backend/paths.py — LOSSLESSBOB_APP_ROOT env override (unfrozen branch
  only) so CI/cloud agents/tests can point the whole backend at a throwaway
  data dir without touching real data/.
Added: tools/make_fixture_db.py — deterministic synthetic install generator
  (~101 entries/29 dates): multi-source dates, a two-show date, an xx-date,
  a private entry + lb_master row, an xref fileset group, 2 tapematch
  families, lineage-bearing descriptions, a curated list, olof song/event
  rarity shapes, bobdylan/setlistfm cross-refs, entry_files, my_collection
  rows. Runs the real derived recompute chain in-process; fixture tapers
  registered via the existing user_taper_aliases mechanism (TODO-241) so
  Layer 0 taper attribution produces real rows without fake names in the
  real known-taper list.
Added: tools/ci_smoke.py — builds the fixture, boots the real backend
  against it, curls the 4 cheap boot-smoke routes with a sanity check each.
Added: .github/workflows/ci.yml — backend-tests (compileall + full pytest
  suite), backend-smoke (ci_smoke.py), gui-check (typecheck+build) on every
  push (all branches) + PRs to main. tapematch-tests dropped per tj: its
  suite shells out to live tapematch_session.py/.venv-nmfp subprocesses,
  unsafe against a live crawl and not meaningful without real audio
  fixtures in CI. release.yml unchanged. Verified green on real GitHub
  Actions HEAD (kuddukan42/losslessbob run 29869608572).
Fixed: backend/db.py (BUG-261) — checksum bloom filter could race init_db()'s
  own caller: a background rebuild thread could snapshot the checksums table
  before the caller's own inserts landed (same db_path, so BUG-187's cross-DB
  guard didn't catch it), silently reporting freshly-inserted checksums as
  NOT FOUND for the rest of the session. rebuild_bloom() now stamps the row
  count it was built from; a live-count mismatch skips the bloom for that
  call and kicks off a fresh rebuild.
Fixed: backend/db.py (BUG-262) — migrate_lb_master()'s init_db()-spawned
  background thread could block up to 30s against a write queue a fast test
  suite was already tearing down. Added a wait=False fire-and-forget path
  for that one caller; synchronous callers (importer.py, flat_file.py)
  unaffected.
Fixed: backend/db.py (BUG-263) — the real segfault cause: init_db()'s four
  background threads each open a sqlite3 connection that was never
  explicitly closed (left for GC), leaking 3 FDs (WAL mode) per thread under
  fast test churn until GitHub Actions' runner ran out and crashed the
  interpreter outright. Each background task now explicitly closes its
  connection when done.
Changed: .claude/CLAUDE.md, PROJECT.md, README.md — CI citation rule, new
  files in the file-structure tree, Actions status badge.
[2026-07-21] — feat(gui): Collection "Misrouted" filter — surface folders in nonstandard mount locations (TODO-166)
Added: backend/db.py — _route_status() classifies each my_collection folder's
  disk_path against its show-year's configured routing: compares the mount the
  path actually sits under (_mount_label_for_path, longest-prefix match) with the
  mount collection_routes says that year should route to. Returns route_status
  (ok / wrong_mount / no_mount / no_route / no_date) + actual/expected mount
  labels + year on every get_collection() row. Pure string matching, no disk I/O.
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx — a conditional
  "Misrouted" filter chip (shown only when drift exists) surfacing wrong_mount +
  no_mount rows, a ⚠ marker in the Disk Path cell with an expected-vs-actual
  tooltip, and RouteStatus typing on CollectionRow. Chip label is hardcoded
  English, consistent with the sibling filter chips (no new i18n keys).
Closed: TODO-249 (Improve xref handling) — superseded/already-covered, per tj.
[2026-07-21] — feat(backend): pipeline step labels return i18n key+params, not rendered English (TODO-195)
Changed: backend/app.py — _pipeline_process_folder now emits label_key (stable
  snake_case enum) + label_params (dynamic values) on every pipeline step dict
  (verify/lookup/lbdir/rename/file), alongside the existing English `label` field
  which is retained as a fallback. Added _file_blocked_label_key() helper. Additive
  and backward-compatible — no field removed.
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx — added PIPELINE_LABEL
  (label_key → i18n key) map + stepLabelText() helper mirroring the STATE_LABEL/
  ERROR_MSG convention; all 5 raw {step.label} render sites and the deriveFolderStatus
  reason sites now translate via t(key, params) with raw-label fallback; the 4
  frontend-synthesized labels (Renamed/Filed/2×Failed) set label_key/label_params;
  the 'Renamed' text guard now checks label_key === 'renamed'. Locale-invariant data
  labels (matched LB-numbers, arbitrary error strings) deliberately keep label_key null.
Added: gui_next/src/renderer/src/locales/en.json — pipeline.stepLabels.* (29 keys).
  Other locales (de/fr/es/it/nl) fall back to English until a follow-up /gui-next-i18n pass.
[2026-07-21] — fix(scraper): hiss_median floor on the staircase corroboration gate (TODO-255)
Fixed: tools/tapematch/tapematch/verdict.py — _staircase_corroborated: the hiss
  corroboration branch required hiss_frac >= 0.05 with no median requirement, so
  noise-level hiss (hiss_median ~0.05) corroborated a staircase-relaxed fp merge
  (1995-12-09 LB-06083/06104: hiss_frac 0.0504, hiss_median 0.0496, corr ~0). Added
  an optional min_hiss_median floor: when set, the hiss branch also requires the
  median at/above the floor; None median with the floor set does not corroborate.
  Absent key = historical frac-only behaviour (byte-identical).
Changed: tools/tapematch/config.yaml — fingerprint.staircase_corroboration.min_hiss_median: 0.05
  (symmetric to min_hiss_frac; tj sign-off 2026-07-21). Cached frozen-set sweep
  (827 dates / 2,965 labeled pairs): −2 fp, 0 tp cost — strict precision gain, blocks
  the boundary case. Floors >=0.08 sever a real same-cluster edge (min real hiss
  median ~0.085). Evidence table in CALIBRATION_PROGRESS.md.
Added: tools/tapematch/tests/test_staircase_gating.py — 4 tests for the median floor
  (blocks noise, passes real hiss, None median blocks, windowed branch unaffected).

[2026-07-21] — feat(gui): collection-view right-click to reassign a folder's LB or rename it (TODO-259)
Added: backend/db.py — reassign_collection(old_lb, new_lb): atomically moves a
  my_collection row (folder_name/disk_path/notes/xref) to a different LB and carries
  its collection_meta (personal rating/tags/listen count) across so nothing is lost.
  Guards: target must exist in entries, must not already be owned, and can't equal the
  source — all raise ValueError. The folder on disk is untouched (that's what rename is
  for). Scope note: TODO-259's other two needs were already shipped — folder rename via
  /api/folder/rename and the pre-filing LB# override via the pipeline OverridePanel
  (BUG-257) — so this session only added the missing collection-view reassign lever.
Added: backend/app.py — POST /api/collection/reassign {old_lb, new_lb}; validation
  failures surface as 400.
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx — two new row
  context-menu entries, "Reassign LB…" and "Rename Folder…" (both disabled on unfiled
  rows), backed by a shared FolderEditModal. Rename reuses the existing
  /api/folder/rename (qBittorrent-sync aware); reassign hits the new endpoint and
  refetches the collection on success.
Changed: gui_next/.../locales/{en,de,fr,es,it,nl}.json — new collection.folderEdit.*
  strings (DeepL-synced; folderEdit fully covered in all five locales).
Added: tests/test_db_writes.py — TestReassignCollection (5 tests: move, meta migration,
  target-missing, already-owned, same-LB). Full suite green; backend restarted and the
  route live-verified (400s on bad/unknown input).

[2026-07-20] — chore(scraper): corpus rescore batch drained (561/561) — corroboration gate validated, staircase lag curves persisted (TODO-254, TODO-235)
Changed: tools/tapematch/CALIBRATION_PROGRESS.md — the 561-date targeted rescore
  (rescore_queue_20260717.txt, launched 07-17) completed 07-20T07:45. Ran the
  completion runbook: tapematch_sync (2,032 dates / 6,112 families / 0 errors) +
  taper_attribution.recompute() (8,159 total; 130 conflict — expected, families held
  on real evidence, not chased to 0). lag_segments_json now populated for 2,272 sources
  (was 0) → unblocks TODO-233 pt2 staircase A/B. Corroboration gate validated across all
  205 flip-sig dates: 749 staircase pairs in the relaxed fp band [0.40,0.50), 515
  uncorroborated correctly split to different_family (gate fired), no bare fp-only leaks
  (11 residual same_family all carry non-fp evidence). Completion record appended to the
  state file. TODO-234 dispositions + TODO-255 gate-floor sweep remain open (tj decisions).
Changed: instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — refreshed the conflict evidence
  table against the post-drain data (series-vs-series subset 18 → 14; 1990-11-08 / 1990-08-12
  / 1995-05-26 cleared). Fresh evidence flips most dispositions from hand-split to flip-to-
  label-review (families held on windowed/hiss/emb, not bare fp): 5 flips, 1 hand-split
  (1995-12-09, a TODO-255 gate-floor artifact), 1 ambiguous (1997-04-05), 1 edge-fix
  (1988-07-17). Recorded only — no DB changes; the 14 rows stay in the queue by design
  pending tj's per-family taper picks.

[2026-07-19] — fix(backend): keep the extras/ set-aside subtree out of checksum generate + verify (BUG-259, BUG-260)
Fixed: backend/checksum_utils.py — final-pass review of the in-flight BUG-257 work
  found two holes in the same extras/ contract the lookup fix established:
  (1) BUG-259: generate_checksums()'s new multi-disc recursion (rglob) also hashed
  audio under extras/ into a fresh top-level _mychecksums sidecar. Lookup only skips
  sidecars *under* extras/, so one press of "Generate FFP + MD5" on a reconciled
  folder fed the superseded fileset's hashes straight back into lookup — recreating
  the false multi-LB match BUG-257 had just fixed. Audio rglob now filters
  _is_reconciled_extra(); disc subfolders (CD1/…) still covered.
  (2) BUG-260: verify_folder() still parsed sidecars under extras/ (and counted
  extras audio), so a folder in the BUG-257 shape (extras/ holds only the alternate
  transfer's sidecar) wedged Step-1 Verify on 'incomplete' with phantom missing
  files. Both verify scans now skip the extras/ subtree, matching lookup and
  verify_folder_lbdir semantics.
  Both bugs repro'd before fixing; regression tests added
  (tests/test_checksum_extras.py, 4 tests); full suite green (880 + 11 dossier);
  backend restarted and freshness-verified.

[2026-07-19] — feat(backend): Show Dossier polish pass — app-blue dark theme, family grouping, attribution + working deep links
Changed: backend/templates/dossier.html — retheme from the sepia palette to the app's
  own look (gui_next tokens.ts "blue" frame + "indigo" accent; dark is now the default,
  light kept as toggle/print). Reordered sections: recommendation hero + circulating
  sources now sit above the setlist. Tape families are visually grouped (reel-icon header
  row per family with member count, confidence meter bar, review flag, and an accent
  spine down member rows) and buckets/members are ordered by pick rank. AI index grades
  render as colored grade seals (A=green/B=blue/C=amber/D=red, score /100 inline) in the
  sources table, glance strip, and recommendation hero. Tables centered + hover states,
  centered masthead with accent double rule. Per-section attribution credit lines
  (Olof Björner "Still on the Road" for context/setlist, setlist.fm for coordinates,
  LosslessBob for the catalog) and a full footer credits paragraph.
Added: backend/dossier.py — _build_xref(): the cross-reference cards are now built
  server-side with working deep links per show: LB detail page (paths.detail_url on the
  recommended/first source), the exact Olof page the show was ingested from (bobserve
  mirror, page_filename URL-quoted), Boblinks per-date setlist page (MMDDYYs.html,
  1995+ only; site home otherwise — pages are best-effort on their end), and the
  Bobserve year index (eventsperiod?period=YYYY). Each sources-table LB number also
  links to its LosslessBob detail page (member.url). Additive to the D1 JSON shape
  (dossier.xref); render_bbcode untouched. All link patterns verified live (HTTP 200),
  11 dossier tests green, template renders verified for 1966/1987/2002 dates.
  Mobile follow-up: the 7-column sources table now scrolls inside its own
  .tbl-scroll container (min-width 640px) instead of forcing page-level horizontal
  scroll; tightened <=720px padding/typography; overflow-wrap on xref URLs.

[2026-07-18] — fix(importer): private-metadata fill skipped bracketed folders + misread LB-<num>.txt sidecars (BUG-258)
Fixed: tools/import_private_metadata.py — the private-metadata fill appeared to
  stop before completing. Three defects, all in the folder pass:
  (1) info_txt_candidates() called glob.glob() on the raw folder path, and
  private folders carry [LB-NNNNN]/[taper] brackets that glob reads as character
  classes — so 43 folders whose .txt files were right there on disk were
  silently reported as no_info_txt. Fixed with glob.escape(folder).
  (2) _LINEAGE_LINE only matched space-padded ' -> '/' > ', missing unicode
  arrow (→), bare -> and no-space chains like cd>EAC>TLH>flac. Broadened to
  match →, -> and word>word.
  (3) extract_setlist() only read one-track-per-line, so the canonical
  LB-<num>.txt sidecars' inline comma-run setlists ('1 intro, 2 Roving Gambler…')
  never parsed — they wrap across physical lines mid-title, use 1-/1./101
  separators, and run the 'Please retain…' footer onto the last track. Added a
  block-based _setlist_from_inline(): de-wraps -----fenced blocks, splits only on
  ', <n>' boundaries (commas inside titles like "It's Alright, Ma" survive),
  reuses the existing 1,2,3…/disc-restart chain validator, and _clean_title()
  strips inline disc labels (', cd-2, November 16th…') and footer boilerplate.
  Applied to the live DB: setlists 1210 → 1309 (+99), descriptions 1356 → 1362,
  no_info_txt 54 → 11. Remaining gaps (63 setlist-less) are genuinely
  source-less — no sidecar, or metadata-only tab formats with no tracklist.

[2026-07-18] — feat(backend): Show Dossier high-fidelity redesign — sepia template + pre-rendered locator map (TODO-260)
Changed: backend/templates/dossier.html — full rebuild to the design-handoff sepia
  light/dark token system: fixed theme toggle (localStorage-persisted, print-hidden),
  masthead with LB mark, at-a-glance strip, table setlist with encore separator + rare
  badges, sources comparison table (pick-rank ordered, is-rec highlight, taper pill +
  source chain retained), recommended callout with signed scoring ledger, cross-reference
  grid, and print CSS that forces the light palette. All source flattening and glance/xref
  derivation happen in-template — the JSON API and render_bbcode are untouched.
Added: backend/dossier.py — _load_quality surfaces abs_score (numeric AI grade nn/100);
  _build_show adds lat/lng/country/city_line + _COUNTRY_MAP_META (world-atlas country name
  + Mercator scale, US/UK aliasing) sourced from setlistfm_shows-by-date; _render_locator_svg()
  pre-renders the country locator to self-contained inline SVG (replicates
  d3.geoMercator center/scale/translate, polar clamp, viewport clipping) so the downloadable
  dossier needs no CDN/JS/network and prints reliably offline (~28KB doc vs ~390KB if d3 were
  inlined).
Added: backend/assets/world_countries_110m.json — bundled 168KB GeoJSON (177 countries,
  Natural Earth names), decoded once from world-atlas@2.0.2 countries-110m.json; loaded and
  cached at render time. No new pip dependency (stdlib math/os/functools/json only).
Fixed: backend/templates/dossier.html — two Jinja Undefined hazards found during the redesign:
  the fam_conf guard crashed on a family with a label but no confidence (now bucket.get() so a
  missing key is real None), and the locator card was nested under d.context so a show with
  coordinates but no chronicle silently lost its map (now gated on coordinates independently).

[2026-07-18] — fix(backend)+feat(gui): lookup ignores extras/ sidecars; pipeline LB# override (BUG-257)
Fixed: backend/app.py — the pipeline Lookup stage gathered checksum sidecars with
  folder.rglob('*') and read every .ffp/.md5/.st5, INCLUDING those under extras/
  (the move_extras set-aside dir). When extras/ held a different transfer's
  sidecars, the merged input covered two distinct filesets, so lookup_checksums
  reported BOTH LBs as MATCHED and the _all_perfect guard auto-linked + renamed
  the folder "(LB-A+LB-B)" as if identical. Seen on 1975-07-03 The Other End,
  N.Y.: LB-12226 vs LB-16533 share Set I (tracks 01-11) but differ on Set II
  (12-19) — genuinely two transfers, falsely merged. Fix: skip paths matched by
  checksum_utils._is_reconciled_extra() (extras/ subtree + rename_log.txt) when
  building the lookup input. Verified on the live folder: LB-16533 drops
  MATCHED -> DUPLICATE, so the false multi-LB auto-link no longer fires.
Fixed (2): backend/app.py — an explicit folder pin was ignored by the LBDIR
  resolvers. _resolve_lb_number_for_folder + the three inline resolvers in
  /api/lbdir/check, /api/lbdir/retrieve and /api/lbdir/reconcile all resolved
  LB# as my_collection.disk_path -> folder-name regex -> hint/pin, with the pin
  DEAD LAST. So after a user overrode a folder to LB-16533, the LBDIR screen
  still verified against LB-12226 (this folder's stale my_collection row + its
  "(LB-12226+LB-16533)" name both point at 12226). New helper
  _pinned_lb_for_folder() makes a *single* explicit folder_lb_link authoritative
  ahead of the heuristics (multiple links stay ambiguous -> heuristics apply).
  Verified: /api/lbdir/check now returns 16533 and verifies the GOODY-FIXES
  manifest (23/23 pass) even when the GUI passes lb_number_hint=12226.
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx — OverridePanel, an
  "Override LB#" control on the Lookup stage (matched branch). Surfaces one button
  per matched candidate LB plus a manual LB# entry; each force-pins a single LB via
  the existing PUT /api/folder_link (replace_folder_link), which supersedes any
  auto-written multi-LB links and re-runs LBDIR/verify against that entry. Lets a
  user correct a wrong/merged auto-match (e.g. this folder -> pin LB-16533). i18n:
  new pipeline.lookup.override* keys (5) in en.json (de/fr/es/it/nl sync pending).
  node+renderer typecheck and production build PASS.
Note: 5 collection folders carry a "+LB-" merged name and 33 folders were
  auto-linked "multi-LB perfect match" pre-fix — worth an audit; the override
  control repairs them one at a time.

[2026-07-18] — fix(backend): pipeline lookup no longer wedges duplicate-fileset folders (BUG-256)
Fixed: backend/app.py — the pipeline Lookup stage's "complete match" guard used
  full_match = summary["matched"] == summary["given"], but summary["matched"] is
  the GLOBAL match count and double-counts checksums archived under >1 LB entry
  (matched == given*N). A show whose identical fileset lives under a duplicate LB
  (e.g. LB-16353 alias -> LB-16369 canonical) therefore stayed in "Incomplete
  match" forever — and pinning either LB couldn't clear it, since the guard read
  the inflated global count rather than the pinned LB's own totals. Now tested on
  distinct unmatched checksums instead: full_match = summary.get("unmatched", 1)
  == 0. Duplicate-fileset folder resolves ok to the canonical LB (with or without
  a pin); a genuine NOT-FOUND file still blocks. Verified against the live DB.

[2026-07-18] — feat(gui): Known Tapers curation widget on DB Editor (TODO-258)
Added: gui_next/src/renderer/src/screens/ScreenDbEditor.tsx — new "Known Tapers"
  collapsible sidebar SideSection (losslessbob DB only, collapsed by default since
  the builtin alias list is long). TaperPanel component: filterable/scrollable table
  of the merged known-taper aliases with builtin/user origin tags (GET /api/tapers/
  aliases), curator-gated inline add (alias -> canonical, POST) and remove-selected
  (DELETE, with builtin-suppression), and a "Recompute derived data" button that
  streams the chained POST /api/derived/recompute SSE (lineage -> attribution ->
  picks -> song index) with per-step status dots. Local readSSE helper mirrors
  OnboardingWizard's. Backend routes/curator gating all pre-existed (TODO-241) — this
  is GUI-only. i18n: new dbeditor.tapers.* block (27 keys) in en.json, synced to
  de/fr/es/it/nl via DeepL (same run also filled pre-existing locale gaps from
  earlier features). node+renderer typecheck and production build PASS.
Changed: PROJECT.md — ScreenDbEditor GUI-screens row now lists the Known Tapers panel.

[2026-07-17] — feat(gui,backend): Show dossier / liner-notes export ships (TODO-257)
Context: instructions/FABLE_SHOW_DOSSIER.md (FABLE_IDEAS §5, HIGH PRIORITY per tj
  2026-07-13) written and shipped same day, bites B1/B2/B3/B5 (B4 = this entry). One
  command renders everything the app knows about a date: rarity-flagged setlist,
  sources grouped by TapeMatch family with taper credit/pick ranking/quality verdicts,
  historical context, provenance footer. Verified against real data (1987-07-04
  Dylan & The Dead show) — 17 source buckets, correct pick evidence and a correct
  "live debut" rarity flag matching the olof_events notes text.
Added: backend/dossier.py — build_dossier() assembly (feature-detected end to end;
  fresh install degrades to a smaller valid dossier, never errors) + filter_dossier_
  sections()/render_bbcode() presentation layer. Three routes in backend/app.py:
  GET /api/dossier (JSON), /api/dossier/html (self-contained print-first Jinja render,
  backend/templates/dossier.html — first template in the repo), /api/dossier/bbcode
  (forum digest, shares the HTML route's filtered view so they can't drift).
  channel='public' (default) reduces any private entries.status source to
  {lb, private: true} only; channel='full' keeps everything; disk paths/collection/
  friend data are never touched. gui_next: Library performance-lens row action +
  DetailPanel ActionBar "Export dossier..." (components/library/actions.tsx registry),
  new DossierExportModal.tsx (channel/section/format options, remembered via
  useSettingsStore), Electron main-process dossier:printPdf IPC (hidden BrowserWindow
  + webContents.printToPDF, HTML-download fallback outside Electron). i18n in all 6
  locales. tests/test_dossier.py (11 tests).
Fixed: backend/dossier.py — ambiguous-date detection was originally keyed off
  entries.location (free text scraped per-recording, e.g. 9 different spellings of
  the 1987-07-04 Sullivan Stadium show), which false-positived on nearly every
  well-documented date; redesigned to key off the clean olof_events.venue field
  instead, matching get_performances()'s existing trust in that source. Caught during
  B1 verification against the real production DB, not by the unit tests.

[2026-07-17] — feat(gui,backend): Gaps view — "the living Kokay list" ships (TODO-256)
Context: instructions/complete/FABLE_GAPS_VIEW.md (written 2026-07-17, PLATFORM_ROADMAP
  §3) built and shipped same day, bites B1-B4. Read-only end to end: every olof_events
  concert date classified covered/partial/gap/future against entries coverage, computed
  live with no derived table.
Added: backend/gap_analysis.py — classify_date() pure classifier + get_summary/
  get_year_detail/get_date_detail; three GET routes (/api/gaps/summary, /api/gaps/year/
  <year>, /api/gaps/date/<iso>) in backend/app.py, all feature-detecting olof_events.
  gui_next/src/renderer/src/screens/ScreenGaps.tsx — new /gaps screen (Library nav group):
  decade-chip strip, year rows of coverage cells, right-hand tab-group detail pane with
  LB deep-links into Library. tests/test_gap_analysis.py (16 tests).
Changed: backend/geocoder.py — _entry_date_to_iso promoted to public entry_date_to_iso
  (alias kept) + new entry_date_month_key() for xx-partial date matching.

[2026-07-17] — feat(scraper): tapematch staircase corroboration gate live + lag-segment
  persistence (TODO-234 sweep signed off, TODO-235 engine half)
Context: two-part tapematch package (work done 2026-07-16, signed off + landed 2026-07-17).
  Part 1: the 2026-07-11 staircase over-merge hazard (1997-11-11 LB-01126, fp .410/win 0/
  hiss 0 crossing the relaxed 0.40 bar) — mitigations (a)/(b)/(c) measured against the
  frozen set + TODO-234 family replay; tj signed off (a): corroboration gate. Part 2:
  TODO-235 prerequisite — per-segment staircase lag curves were render-only (analysis.md
  text), now persisted numerically for backend ab_clips piecewise maps (TODO-233 pt2).
Added: tapematch/align.py: fit_lag_segments() — piecewise-linear lag model per splice
  segment (offset_sec/rate_ppm/r2, same step detection as locate_splice_points);
  tapematch/verdict.py: fingerprint.staircase_scope (source|pair) + staircase_corroboration
  gate (absent-key = historical behaviour, verified byte-identical tp=684 fp=9);
  tests/test_lag_segments.py + tests/test_staircase_gating.py (17 tests).
Changed: tapematch/cli.py: results.json sources rows now carry lag_ref/lag_segments/
  lag_curve (raw anchor rows kept for re-derivation); tapematch_session.py: observations.db
  sources + lag_ref_lb/lag_segments_json columns (idempotent ALTER); config.yaml:
  fingerprint.staircase_corroboration ENABLED (min_windowed_frac/min_hiss_frac 0.05) —
  new committed frozen baseline tp=671 fp=9 (was 684/9; −13 tp are all fp-only
  zero-corroboration pairs, 0 new FP — verified via regression.py score --cached);
  CALIBRATION_PROGRESS.md: sweep table + decision recorded.
Added: instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — evidence review of all 11
  conflict components; action A (3 curator rejects) applied, queue 22 → 18; actions B
  (same_as edge fixes) + C (lineage parser tie-break bug) ON HOLD pending tj; post-rescore
  validation checklist. TODO-234/235 stay Open: corpus rescore + validation remain.
Session 2 (same day) — CORPUS RESCORE LAUNCHED + priority-date validation:
Added: tools/tapematch/rescore_queue_20260717.txt — targeted 561-date rescore queue
  (8 priority + 200 flip-signature + 353 stale pre-fp-column staircase dates; scope
  rationale in CALIBRATION_PROGRESS.md); batch running detached (setsid), ETA ~07-20,
  resumable via # done markers.
Changed: tools/tapematch/CALIBRATION_PROGRESS.md — rescore launch note, priority-date
  results, and a RESCORE COMPLETION RUNBOOK at the file tail (session briefing surfaces
  it) for the next session to finish sync/recompute/spot-checks/bookkeeping;
  instructions/TODO-234_FAMILY_CONFLICT_REVIEW.md — post-rescore validation DONE on live
  re-runs: corroboration gate validated in the wild (1997-11-11 LB-01126 isolated), but
  most expected splits did NOT happen (live evidence: windowed .95 on 1996-07-07, hiss
  .62/.727 on 1993-02-07, plain-bar fp .50+ bridges) — dispositions await tj. Boundary
  artifact logged: 1995-12-09 6083–6104 passed the gate at exactly hiss_frac 0.05.
  Mid-batch tapematch_sync (2,032 dates / 5,811 families / 0 errors) +
  taper_attribution.recompute() run; both must re-run after the queue drains.

[2026-07-16] — refactor(gui): Advanced-tools screens removed; Pipeline absorbed the gaps
Context: tj found the Advanced sidebar section (Verify/Lookup/Rename/LBDIR standalone
  screens) confusing next to the Pipeline, which already runs the same steps per-row via
  the shared stores/detail components. Decision: delete the four screens, port only the
  genuine capability losses into Pipeline, repoint entry points. Net −3,085 lines.
Changed: gui_next screens/ScreenVerify|ScreenLookup|ScreenRename|ScreenLBDIR.tsx deleted;
  App.tsx routes + AppShell.tsx Advanced-tools nav block removed. Entry-point repoints:
  Library "reconfirm" + Collection "Send to →" → Pipeline queue; Collection missing-LB
  dblclick + "LosslessBob" button → Quick Lookup with router-state seed (auto-runs once).
  lookupStore/verifyStore/lbdirStore stripped to shared types (zustand stores dead).
  Locales: 133 dead keys removed, 11 added (en+de/fr/es/it/nl — hand-translated, not DeepL).
Added: ScreenPipeline.tsx — lbdir stage Re-scan button (re-runs POST /api/lbdir/check
  anytime, replaces the "Full screen" link into the deleted screen); rename stage
  multi-LB disambiguation panel ported from ScreenRename ("Choose LB" → /api/folder_link
  + /api/lb_alias/resolve, Pin re-runs lookup+rename, Standardize feeds the proposal via
  overrideProposed, Unpin/Skip). ScreenQuickLookup.tsx seed handling.
Dropped (deliberate, not ported): bulk verify-all (/api/verify), lookup extra sources
  (clipboard/listbox/file), CSV export, wishlist-from-lookup, shallow-scan toggle,
  rename plan export — backend endpoints left in place. Verified: typecheck + prod build
  clean; every t() key cross-checked against all 6 locales (zero dangling).

[2026-07-16] — feat(db): private LB metadata import — TODO-245 shipped (docs + folder txts)
Context: tj supplied data/private/lb_summary_all_private.html (Jeff's cp1252 summary sheet,
  2,213 LBs: date/loc/lineage/notes/rating) and 'No Torrent -LB number overview.xlsx'
  (2,355 LBs: title/xref/date/taper), plus 1,372 private collection folders with info txts.
  tj rules: the docs are OLD snapshots (1,035 of their numbers are public today) — fill blank
  fields only, never overwrite scraped metadata; private LBs flagged 'private', not 'missing'.
Added: tools/import_private_metadata.py — document pass + --folders pass. Targets only
  CURRENT lb_master lb_status='private'; per-field blank-only fill. Field mapping verified
  against 1,032 now-public LBs present in both the HTML and scraped entries (Date→date_str,
  loc→location, qual→description, rat→rating). Jeff's private comparison-notes column
  appended inside description under a '-- private notes --' marker (1,240 rows). Folder pass
  extracts setlists from numbered track lines validated as a sequential 1,2,3… chain (disc
  restarts allowed; prose starting with a number is dropped) + lineage lines for doc-less rows.
Changed: backend/db.py — entries.metadata_source column (NULL=scraped, 'private_import'=from
  private material; idempotent ALTER). MASTER_SCHEMA_VERSION 10→11 (entries is a MASTER table;
  snapshots carry the new column). backend/scraper.py — live scrapes re-check status='private'
  rows like 'missing'; a successful scrape's INSERT OR REPLACE supersedes the private import
  (status→'ok', metadata_source→NULL), so publication always wins.
Data: 1,405 entries.status missing→private; 1,361 rows metadata-filled (date 1,361,
  location 1,243, description 1,243+117 folder-lineage, rating 1,158, taper 1,121,
  source_chain 904, lb_category 1,357); 1,210 setlists (was 1). Checksums deliberately not
  imported — already covered 1,403/1,405 (that coverage is what derived 'private' status).
Verified: 0 public rows carry metadata_source='private_import'; spot-checks (LB-14614 public
  untouched; LB-2606 Supper Club filled incl. setlist); FTS trigger-synced; importer dry-run
  == apply counts. Residual: 36 private LBs fully blank, 54 folders without info txt.
Privacy: data/ is git-ignored (docs can't reach the public repo); schema.html carries no row
  data. Master-export channel decision split to TODO-253 (snapshots now carry private rows —
  friends-only OK, public publication would need export-time stripping).
Closed: TODO-245. Opened: TODO-253.
Follow-up same session (tj: "does that publish to github from our app?" → "do it") — TODO-253
  escalated and shipped: /api/master/github_release uploads snapshots to the PUBLIC repo
  kuddukan42/losslessbob (channel active, master-2026-07-14), so the next release would have
  leaked the imported private metadata. No leak occurred — existing releases predate the import.
Changed: db.py export_master_db(include_private=False) — public channel (default) blanks all
  private-entry metadata (status='private' OR metadata_source='private_import'): fields
  emptied, entries_fts rebuilt, number-level status='private' kept (same info as lb_master);
  checksums retained deliberately (clients derive 'private' from them; pre-existing exposure).
  New verify step 7c: RuntimeError if a public snapshot still carries private metadata.
  Manifest gains channel ('public'/'full') + private_rows_stripped.
Changed: app.py /api/master/export accepts {channel: 'public'(default)|'full'};
  /api/master/github_release refuses (400 private_data) any manifest whose channel is not
  'public' — including legacy manifests without the field. GUI flow unchanged → safe by default;
  friends-only full export via API channel='full' (never uploadable).
Verified: tests/test_master_data.py 14/14 (new test_export_strips_private_metadata_on_public_channel);
  live API export on real DB: channel=public, private_rows_stripped=1405, snapshot has 0 private
  metadata rows, 0 FTS hits for the notes marker, public rows byte-identical; guard returns 400
  for full-channel and legacy manifests; artifacts cleaned up.
Closed: TODO-253.

[2026-07-16] — feat(gui): propagated-taper outline pills in Library (TODO-242 decision)
Context: tj decision — propagated attributions get a pill too, visually distinct
  ("outline or fuzzy"). Outline uses Pill's existing non-soft mode (transparent bg, toned
  border) — zero component changes. Conflict rows stay pill-less (review filter only).
Changed: db.py _load_taper_attributions now carries the taper name for conflict-free
  confidence='propagated' rows ("propagated" key); get_pick_badges + get_performances emit it
  as taperPropagated (docstrings updated).
Changed: ScreenLibrary.tsx — taperPropagated in RecordingRow + both merge paths; all three
  pill sites (recording lens row, perf single-recording, family member row) render an outline
  info Pill with a "propagated from linked recording" tooltip when no confirmed attr exists.
  Solid-confirmed > outline-propagated > mute free-text pill precedence unchanged otherwise.
Added: en.json library.picks.taperPropagatedTitle + DeepL sync de/fr/es/it/nl (4,492 chars;
  residual gaps are the benign SKIP_KEYS/identical-in-target class).
Verified: taper_attribution 26 tests green; gui-check PASS (node+renderer types, build);
  live /api/library/badges: 2,657 taperConfirmed + 4,023 taperPropagated (4,045 review minus
  22 conflicts); tj's original pair resolves — LB-10678 solid 'ltf', LB-14922 outline 'ltf'.
Follow-up same day (tj: "do the backfill and legend too") — Q2 leftovers shipped:
Fixed: tapematch_sync.py _parse_verdict only extracted reasons from the canonical
  "needs review — <reason>" form; the corpus also has "needs review: <reason>" and
  "needs review (<reason>)" variants whose reasons were silently dropped (the actual root
  cause of the 17 NULL review_reason rows). Parser now accepts all three delimiters;
  3 new tests (43 green). Note: sync reads analysis.md from archive_dir (<run_id>_<date>);
  bare <run_id> dirs under data/tapematch/runs/ are stray empties.
Changed: one-off backfill of the 17 flagged NULL-reason tapematch_family_meta rows (5 runs) —
  4 runs re-parsed with the fixed parser; run 20260615_154028's verdict is bare "needs review"
  so its reason was hand-derived from the analysis body (LB-12192-vs-4378 commentary
  contradiction, LB-06940 inflated ingest, LB-01489 not on disk). 0 NULL-reason flagged rows
  remain; reasons verified live in /api/tapematch/families.
Added: ScreenLibrary LegendMenu — "Legend" popover (FilterMenu pattern, both lenses' toolbars)
  with live Pill samples: ★ recommended, solid/outline/mute taper pills, Needs review, family
  best, curated pick. en.json library.legend.* + DeepL sync (6,210 chars).
Verified: gui-check PASS (node+renderer types, build).

[2026-07-16] — feat(backend): taper alias curation conduit — add/remove known-taper handles without code edits (TODO-241)
Context: TODO-222 (tj's pick) turned out already shipped+closed 2026-07-14 (stale work-package
  row); substituted the nearest well-specified open item per tj's "next autonomous win" intent.
  Design Fable, implementation sonnet subagent, review+fix Fable.
Added: db.py user_taper_aliases table (USER-tier, in USER_TABLES, never exported): alias_norm PK,
  canonical, action add|remove (CHECK), approved, note, timestamps. 'add' rows add/override an
  alias; 'remove' rows suppress a builtin key.
Changed: db.py — builtin literal renamed _BUILTIN_TAPER_ALIASES; _KNOWN_TAPER_ALIASES is now the
  merged dict, rebuilt IN PLACE by reload_taper_aliases() (preserves dict identity for importers;
  derived _TAPER_UNIVERSE/_KNOWN_TAPER_KEYS_SORTED/_KNOWN_TAPER_RE reassigned). _normalise_alias_key()
  extracted from _normalise_taper + two inline duplicates. add/remove/list_taper_aliases() with
  BUG-246-style write-queue guard. list_taper_aliases() reloads first so a running backend converges
  on out-of-band CLI edits (gap caught in live smoke: merged count was stale cross-process).
Changed: taper_attribution.py — _ALIAS_KEYS_BY_CANONICAL build extracted to _rebuild_alias_index()
  (called at import + top of recompute()); _TAPER_UNIVERSE now read via db module attribute
  (frozenset reassigned on reload; direct import would go stale) + PEP 562 __getattr__ forwarder.
Added: app.py — reload_taper_aliases() at startup after init_db; GET/POST /api/tapers/aliases +
  DELETE /api/tapers/aliases/<alias> (writes curator-gated, matching adjacent taper routes).
Added: taper_review.html "Taper aliases" collapsible admin section (list w/ builtin|user badges,
  add form, remove/suppress buttons, recompute button); tools/taper_aliases.py CLI (list/add/remove,
  --recompute); tests/test_taper_aliases.py (14 tests).
Verified: 58 targeted (aliases+attribution+fingerprints) + full suite 850 green; backend restarted;
  live smoke: API add/remove, CLI out-of-band add visible to running backend (286→287→286 merged).
Ops (same session): mirror crawl session 33 (seeded 07-16 12:41) confirmed done — 4,269 fetched,
  0 failed; entry_files downloaded=0 4,357→88 (long-tail mangled/double-encoded URLs, 1 xref-named
  but not a checksum fileset). Backend was stale (predated xref_ingest routes) — restarted.
  POST /api/xref_ingest/scan rerun per TODO-252 note: staged 0 new (all 108 missing xref text
  files had landed before the 13:16 scan; TODO-252 import was complete as shipped).

[2026-07-16] — feat(backend): xref B8 promoted — site-mirror xref ingest shipped + 6,632 checksums imported (TODO-252)
Context: tj D-2 decision — promote B8 from report-only to a reviewed import path, then
  directed bulk import ("all these xref should get added, one go"). flat_file.py pattern.
Added: backend/xref_ingest.py — scan_mirror (parse LBF-*-xref-*-text.txt via
  _read_checksum_text + parse_checksum_text; "new" = no (checksum, lb_number) row; idempotent
  rescan, approved/rejected never touched), approve_filesets (INSERT OR IGNORE of is_new rows
  only, refuses non-staged ids), reject_filesets, get_filesets.
Added: db.py xref_ingest_filesets + xref_ingest_rows staging tables (USER tables — audit/
  provenance record, never exported; checksums schema untouched); 4 /api/xref_ingest/* routes;
  tests/test_xref_ingest.py (9 tests; full suite 836 green).
Changed: checksums 705,352 → 711,984 (+6,632). Scan: 2,087 mirror xref text files parsed,
  0 unparseable, 1,801 fully covered by master import already, 286 filesets staged (269 LBs,
  xref ids 9–2149) and all approved per tj. Private-linkage check (tj flagged): zero staged
  LBs among the 62 private pages / entries 'missing' / lb_missing.
Verified: lookup of ingested xref-1143 (LB-01124, 332 rows) resolves with zero NOT FOUND —
  46 matched to LB-01124 (matched_xref 1143) + six member filesets attributed to their
  canonical LBs. GUI review card (P2) dropped per bulk directive; rerun scans via API.

[2026-07-16] — fix(scraper): site mirror now downloads all known attachment links, xref included
Context: tj directive — mirror must cover every link incl. xref attachments. The crawler was
  purely BFS link-discovery, so entry_files URLs not linked from any re-fetched page were
  never queued: 4,357 attachments absent from disk (109 xref: -text.txt/-lbdir.txt/
  -DigiFlawFinder.html), only 9 known to site_inventory.
Added: backend/db.py get_missing_attachment_urls() — entry_files rows with downloaded=0.
Changed: backend/site_crawler.py crawl() seeds those URLs (discovered_by='entry_files',
  same-domain + skip-ext guards) after the index seeds, so the mirror converges on every
  attachment the scraper knows about; existing /files/ handling marks entry_files.downloaded=1
  on fetch. This is mirror-side only — no checksums ingest (B8/D-2 unchanged).
Added: tests/test_scraper_crawler.py::test_get_missing_attachment_urls_returns_undownloaded_only.
Verified: crawler test file 61 passed; backend restarted; incremental crawl session 33 started
  with queue_size 4,348 (the seeded set) — ~1.8 h at the 1.5 s delay.

[2026-07-16] — feat: xref incorporation shipped end to end — copy-level filesets (TODO-246, B1–B7)
Context: instructions/complete/FABLE_XREF_INCORPORATION.md; xref = fileset id (0 = canonical),
  copy-level (this copy IS xref-N) vs entry-level (entry HAS alt filesets) per
  docs/XREF_SEMANTICS.md. Covers B1/B2/B5/B6 committed in the cut-off prior session
  (never logged) + B3/B4/B7 today. B8 site-mirror ingest NOT built per D-2 default —
  master import stays the only checksums write path; D-1 (5-digit xrefYYYYY) and
  D-3 (legacy gui/ frozen) defaults also applied.
Added: backend lookup lb_summary carries matched_xref + xref_groups (B1); my_collection.xref
  + folder_lb_link.xref columns, pipeline names xref copies "… (LB-XXXXX-xrefYYYYY)" (B2).
Fixed: dff_reports rekeyed (lb_number, xref) — LBF-*-xref-* reports attributed to the right
  fileset (B5); cli.py dead XREF guard dropped, missing list uses winning fileset (B6).
Changed: gui_next lookup surfaces (B3) — XREF removed as a status; xref-NNNNN pill augments
  the status pill (quick lookup, summary, checksum groups); Cross-refs bar counts/filters
  matched_xref > 0 (lookupState.ts, lookupStore.ts, ScreenQuickLookup/ScreenLookup,
  LookupDetail).
Changed: gui_next entry-level surfaces (B4) — Search Xref column from xref_map; Collection
  filter split into "My xref copies" (copy-level) vs "Entries with alt filesets"
  (entry-level, detail-pane marker); Library/DetailPanel relabeled "Alt filesets",
  detail checksums grouped by fileset, canonical first (ScreenSearch/ScreenCollection/
  ScreenLibrary, DetailPanel).
Changed: locales de/fr/es/it/nl DeepL-synced (5,487 chars); dead xref keys pruned from all six.
Docs: PROJECT.md schema rows, matched_xref dimension, collection/lookup API fields (B7);
  spec moved to instructions/complete/ + README row.
Verified: /gui-check PASS (node+renderer types, build); fixture LB-2 xref-961 → MATCHED with
  matched_xref 961 + correct xref_groups (after backend restart — stale process gave null);
  backend suite 826 passed. One order-dependent flake logged as BUG-254 (passes solo,
  pre-existing).

[2026-07-16] — chore(docs): repo sweep — stray root files and dead Qt scripts moved to attic/
Context: root had ~19 stray one-off reports/artifacts; grep-verified nothing in live code
  references any of them (attic/README.md documents each file's origin and verdict).
Added: attic/ + attic/README.md — holding pen for deletion candidates, tj to review/purge.
Changed: moved to attic/ — 4 wtrf_*.md reports, shared_checksums_report.md,
  missing_from_collection.tsv, public_not_owned.html, scan.json, batch_verify_run.log,
  notes.todo (pre-TODO.md Qt-era notes, all items done/superseded), 0-byte root
  observations.db + losslessbob.db strays, losslessbob.tar.gz, screenshot_log.txt +
  screenshot-lookup.png, tools/tapematch/observations.db.bak-20260612 (month-old backup),
  and Qt-era scripts/{build_qm,port_qt_to_json,fix_ts,fix_ts2}.py (dead since GUI removal;
  scripts/deepl_translate_gui_next.py kept — used by /gui-next-i18n).
Changed: .gitignore: attic/observations.db.bak-* line (other moved blobs already covered
  by bare-name patterns).
Removed: .claude/worktrees/* — 19 stale agent worktrees, 68 MB (gitignored, no log entry
  impact). Left alone by decision: tapematch .venv-emb/.venv-nmfp (staircase rescore may
  still use fp code), docs/screenshots (live, wiki-referenced). CHANGELOG rotation checked:
  May already archived 07-06, June not due until August.

[2026-07-16] — chore(gui): legacy PyQt6 GUI removed — gui_next is the sole frontend
Context: spec'd and executed same-session (instructions/complete/LEGACY_GUI_REMOVAL_SPEC.md);
  tj signed off D1=delete Docker stack, D5=no frozen-build users. 4 commits (a4326e47,
  674249bb, 88676070 + docs), net ~49k lines removed.
Removed: gui/ (19 modules, 18.5k LOC, Qt locales/resources), main.py, run_next.py (dead
  pre-Electron launcher), losslessbob.spec + losslessbob_linux.spec, tools/losslessbob.iss +
  build_windows.bat, scripts/translate_ts.py, /i18n-update skill, Dockerfile +
  docker-compose.yml + docker/ (noVNC stack), .dockerignore, secrets/ (Docker-only secret
  templates; all .txt were 0 bytes — no real credentials), PyQt6/PyQt6-WebEngine pins
  (+ pytest-qt uninstalled from .venv).
Changed: backend/resources/ now hosts map.html + leaflet/ (moved from gui/resources/;
  /map + /leaflet routes repointed; QWebChannel bridge and Search-tab buttons stripped from
  map.html — postMessage filter path for gui_next's ScreenMap iframe kept). New
  backend/platform_utils.py hosts open_in_vlc (was gui.platform_utils). Qt test classes
  dropped from tests/test_lb_master.py.
Fixed: BUG-249 closed (resolved-by-removal: crashing qtbot test deleted); BUG-106 closed
  (obsolete: legacy Windows installer channel deleted).
Docs: PROJECT.md (tech stack, file tree, GUI sections replaced with removal note, legacy
  conventions cut), .claude/CLAUDE.md, BEST_PRACTICES.md, wiki (GUI/Architecture/
  Dev-Workflow/Home).
Verified: 799 tests pass without Qt; backend restart clean; /map + /leaflet serve 200 from
  new location. tj to eyeball ScreenMap visuals.

[2026-07-16] — chore(db): TODO-240 complete — venue gazetteer fully resolved, all entry locations geocoded
Context: overnight completion of the geo chain started 2026-07-15 (TODO-239 backfill → resolve → geocode).
Changed: venue_geocoded (data): resolve finished 4,071/4,071 — final mix 2,125 bounded_venue,
  1,388 setlistfm_city, 419 wikidata, 124 city_geocode, 15 failed. Pre-backfill city_geocode
  pins were reset + re-laddered (587/726 upgraded to venue-precision/zero-cost sources); old
  pins snapshotted in _city_geocode_backup_20260715 (drop the table once satisfied).
Changed: location_geocoded (data): geocoder run_batch processed all 6,584 remaining
  entries.location values — 6,008 via free gazetteer inheritance (4,003 venue + 2,005 city),
  531 skipped_not_concert, 9 live Nominatim calls. 0 un-geocoded remain.
Verified: db.get_map_data() spot-check — 11,090 markers, city_level 4,506 (40.6%).

[2026-07-15] — fix(db): BUG-118 degenerate-checksum lookup fix + geo backfill (TODO-239) + backlog burn-down (TODO-156/236/242, BUG-251)
Context: autonomous backlog session (xref items TODO-246/249 explicitly parked by tj).
Fixed: backend/db.py: BUG-118 phantom lookup conflicts — new _DEGENERATE_CHECKSUMS /
  _is_degenerate_checksum(); lookup_checksums treats empty-file MD5/SHA-1 and all-zero ffp
  as non-evidence in both directions (no match evidence, never counted missing; detail rows
  kept with ignored=True). Phantom quartet 04994/03029/06748/11900 shared the empty-file MD5.
  Verified: functional test vs real DB + 240 tests green (db_lookup/db_writes/setlistfm/geocoder).
Added: backend/importer.py: de-dup guard — incremental imports (≤500 new LBs) log checksums
  already present under other LB numbers (surfaces future BUG-118-class duplicates at import time).
Added: shared_checksums_report.md (repo root): BUG-118 item-1 report — 5,261 shared
  (checksum,chk_type) groups across 223 LB-sets; top cluster 16054/16101/16440/16511/16621
  shares 718 hashes (likely one recording under six entries; needs curator review).
Changed: lb_problems table (data, TODO-156): 32 rows added covering BUG-118 conflict pairs,
  the six-way 16000-series cluster, BUG-120 verify mismatches, BUG-252 reconcile entries.
Added: docs/wiki/Taper-Attribution-Flow.md (TODO-236): attribution pipeline flowcharts
  (Layer 0/1, disabled Layer 2, curator loop, conflict-queue split) + wiki Home index row.
Changed: data (TODO-239): setlist.fm force re-scrape backfilled city coords — 4,147/4,149
  setlistfm_shows rows now carry city_lat/lon (was 0). venue_gazetteer resolve re-launched
  for the 2,361-seeded remainder (07-14 batch had died at 1,710/4,071); setlistfm_city pins
  confirmed working. Geocoder run_batch still pending → TODO-240 In Progress.
Changed: BUG-251 closed without re-run: contamination scan of all 2,280 tapematch run dirs
  found only the known 20260602_205451 report; clean sibling 20260602_205500 (regenerated 9s
  later) supersedes it — SUPERSEDED.md marker dropped in the dir.
Changed: TODO.md: TODO-242 investigated → decision-ready (propagation works, both LBs carry
  ltf; asymmetry is the spec'd confirmed-only pill policy; "Needs review" = tapematch family
  review_flag with tooltip already wired — decision + optional reason-backfill remain).

[2026-07-15] — chore(docs): TODO-248 ledger ID integrity — open/done collisions fixed, archive frozen (option 1)
Context: 20 duplicate BUG ids in BUGS_DONE.md, 17 duplicate TODO ids across TODO files, and
  2 ids (BUG-175, BUG-200) that named an open bug and an unrelated fixed bug simultaneously,
  making ledger.py bug-close ambiguous. tj decided option 1 ("do 1 thats it"): leave archive
  duplicates frozen as historical noise; renumber only the 2 open bugs that collide.
Changed: BUGS.md: open BUG-200 (tapematch report.md cross-contamination) renumbered to
  BUG-251; open BUG-175 (LBDIR reconcile MD5 mismatch) renumbered to BUG-252; each entry
  carries a "Renumbered:" alias note so pre-2026-07-15 references stay traceable. The fixed
  BUG-175/BUG-200 in BUGS_DONE.md keep their numbers.
Changed: TODO.md: consistency check found 3 open/done TODO collisions of the same class
  (missed by the original TODO-248 census) — open TODO-155 "Improve xref handling" -> TODO-249,
  open TODO-107 "Disk Scanner" -> TODO-250, open TODO-106 "Trading multi-friend batch compare"
  -> TODO-251, each with a "Renumbered:" alias note; the done copies keep their numbers.
  TODO-172 cross-reference updated (BUG-175 -> BUG-252). Historical CHANGELOG/PROJECT.md
  references intentionally untouched. tools/ledger_dedup.py assessed: report-only, no rewrite
  path — hand edit was correct.
Closed: TODO-248 -> TODO_DONE.md (within-archive duplicates remain by decision).

[2026-07-15] — feat(gui): TODO-247 visual-verification driver — bite 4 + spec CLOSED (3b won't-do)
Context: instructions/complete/FABLE_VISUAL_VERIFICATION.md §8. tj chose bite 4 over bite 3b
  when the two were put to him as independent next steps, then killed 3b outright: "not
  enough animation in the app to matter". TODO-247 is CLOSED and the spec is closed in
  full — bites 1/2/3a/4 shipped, bite 3b deliberately never built.
Decision: bite 3b (dev-gated progress fixture) WON'T DO, tj sign-off 2026-07-15. Its only
  consumer was one progress meter (FileProgressBar) and its price was a test-only intercept
  inside start_file_job in PRODUCTION code (backend/filer.py), past three guards, plus a
  simulated _run() and a staged pipeline row (spec finding 12). Accepted consequence:
  acceptance criterion 4 is permanently unmet by choice and the meter's mid-fill state is
  not machine-verifiable. The `watch` ACTION itself is built and works (bite 3a) and still
  runs against real jobs — only the synthetic fixture was dropped; don't read this as
  "watch was cancelled". Finding 12 kept as the record of why, for any future revisit.
Added: .claude/skills/verify/SKILL.md `--electron` mode (Tier B). Documents both tiers as a
  table (driver, PNG dir, extra actions, window.api, cost) and when to reach for B over A:
  window chrome, real sizes, display scale, native preload flows, main-process state.
  Both tiers share tools/debug_screens.json, so the screen tour is identical.
Added: PROJECT.md tools/ listing now names all 7 driver files (browser_driver, driver_core,
  electron_driver, electron_preflight, electron_display, electron_driver.config.json,
  debug_screens.json). Closes a PRE-EXISTING gap — the listing mentioned no driver at all;
  browser_driver.mjs was already absent before this work. check_project_refs.py exits 0
  either way (it checks routes/tables/screens/backend modules, not tools/*.mjs).
Changed: .claude/CLAUDE.md Verification section — /verify is the named exception to the
  "no screenshots" rule, and only on explicit user invocation. Wording is deliberate:
  having the capability is not permission to use it on initiative.
Changed: instructions/FABLE_VISUAL_VERIFICATION.md -> instructions/complete/ (+ README.md
  row, + the instructions/ path references inside the 3 driver source headers).
  complete/ here means "design record for a shipped driver", NOT "every bite landed" —
  the spec's resume block and README row both say bite 3b is deferred.
Verified: full Tier B tour re-run after the path edits — all 17 screens captured to
  .debug/electron/, every action ok, backend on :5174 survived. `node --check` clean on
  all 5 .mjs files; check_project_refs.py exits 0. Screenshots NOT reviewed — that was a
  smoke test of the tool, not a /verify run; tj verifies visuals.
Remaining: nothing. Criteria 1/2/3/5/6 met; criterion 4 withdrawn with the fixture (above).
Verified (example run, tj-requested): 25 PNGs in .debug/electron/ — the 17-screen tour, plus
  size-matrix at exactly 1280x768/1440x900/1920x1080/2560x1440 and scale-matrix on /lookup at
  1440x900/1800x1128/2160x1350/2880x1800. Spot-checked two: live data, nothing clamped.

[2026-07-15] — feat(gui): TODO-247 visual-verification driver — bite 3a: resize/size/scale/watch
Context: instructions/FABLE_VISUAL_VERIFICATION.md §6. Bite 3 split into 3a (driver
  actions, tools/ only) and 3b (progress fixture) — see the Notes below.
Added: driver_core.mjs actions `resize`, `size-matrix`, `watch`, `main-eval`, shared by
  both tiers via a new `caps` opt ({resize, mainEval}) each driver supplies — a driver
  that can't do one omits it and the action fails that step cleanly instead of the run.
  Tier A resize = page.setViewportSize; Tier B = real window; Tier A has no mainEval.
Added: electron_driver.mjs `scale-matrix` (CLI-level, not a session action:
  --force-device-scale-factor is a launch flag, so each scale needs its own launch).
  Pins a 1440x900 DIP baseline per row, so the matrix means "same logical layout,
  varying DPR" rather than inheriting whatever the default window was.
Changed: Tier B resize uses setContentSize, NOT spec §6's setSize (deviation recorded in
  code + spec finding 9). Tier A's setViewportSize sets content size exactly, so an
  outer-frame Tier B would make the shared debug_screens.json produce different PNG
  sizes per tier — setSize gave 2559x1411 for a "2560x1440" shot, the title bar eating
  the difference. The app's minWidth/minHeight are outer constraints, still respected.
Changed: electron_driver.config.json xvfbScreen 2560x1440x24 -> 2920x1860x24. The screen
  is sized by both consumers: max(size-matrix largest content, scale-matrix baseline x
  max scale) + decoration. Undersizing silently CLAMPS rather than erroring — at
  2600x1500 the 2x row capped at 2600x1480, which is 1300x740 logical, below the app's
  own 768 minimum: a frame showing a layout no real user could have. ~22MB of extra
  virtual framebuffer is nothing against a lying screenshot.
Verified: size-matrix PNGs land at exactly 1280x768 / 1440x900 / 1920x1080 / 2560x1440
  (112-186KB each, non-blank); scale-matrix at 1440x900 / 1800x1128 / 2160x1350 /
  2880x1800, nothing clamped; watch emits 5 frames at 300ms and stops on both the
  selector and timeout paths; backend on :5174 survived every run.
Known: scale-matrix 1.25x is 1128px tall, not 1125 — Electron reports a 902 DIP content
  height at fractional DPR (902x1.25=1127.5). Accepted: the capture is honest about the
  window it got, and §10 puts pixel-diff baselines out of scope. Finding 11.
Remaining: bite 3b (progress fixture — finding 12: it needs a start_file_job intercept
  in backend/filer.py, not just driver work), bite 4 (/verify --electron, docs).

[2026-07-15] — feat(gui): TODO-247 Electron visual-verification driver (Tier B) — bites 1-2
Context: instructions/FABLE_VISUAL_VERIFICATION.md, attempt 3 at driving the real app.
  Prior attempts failed because they captured pixels from OUTSIDE the app (compositor/
  VNC) — locked down on Wayland, flaky on NVIDIA. This one captures from inside the
  render pipeline (Playwright page.screenshot() -> CDP), so neither is involved.
Added: tools/electron_preflight.mjs — probes all 4 display backends on this machine
  and records the winner in tools/electron_driver.config.json (committed; the one
  durable output of Bite 1). Result: Xvfb at 2560x1440x24, --ozone-platform=x11
  --disable-gpu --no-sandbox. Wayland and XWayland also booted (~1.6s, same as Xvfb)
  but a window cannot exceed its screen, and size-matrix needs 2560x1440 which no real
  display here provides; Xvfb is also deterministic and session-independent. Ozone
  headless is dead as the spec predicted — CDP attaches, no window is ever created.
Added: tools/electron_driver.mjs — Tier B MVP (screenshot/navigate/click/fill/eval/
  session), same session-JSON format as Tier A; PNGs go to .debug/electron/ so the two
  tiers can share debug_screens.json without overwriting each other. Full tour passes.
Added: tools/driver_core.mjs — action runner extracted and shared with browser_driver
  .mjs (spec §3: don't fork two copies); tools/electron_display.mjs — Xvfb lifecycle +
  X11/Wayland socket discovery, shared by preflight and driver.
Fixed: gui_next main/index.ts ensureBackend() now honors LB_NO_BACKEND_SPAWN=1 (dev
  only, !app.isPackaged) — it kills whatever owns :5174 and respawns, which would
  murder a manually-started backend mid-driver-session.
Notes: three findings amend the spec (§4/§6, recorded there for Bite 3). (1) Display
  env is never inherited — the shell has DISPLAY and WAYLAND_DISPLAY empty with
  XDG_SESSION_TYPE=tty; the sockets exist but must be discovered and set explicitly.
  This is a likely cause of the 2026-06-04 attempt's failure: the missing env, not the
  backend. (2) ready-to-show never fires under Playwright on any backend, and
  index.ts gates win.show() on it — every driver must force show via app.evaluate().
  (3) app.evaluate() has no require in scope; destructure electron off the callback arg.
Remaining: Bite 3 (resize/size-matrix/scale-matrix/watch + progress fixture), Bite 4
  (/verify --electron, docs). Screenshot verification stays user-invoked only.

[2026-07-15] — fix(gui): TODO-243 renderer silent-catch audit — surface user-action failures
Context: STRUCTURE_REVIEW item 15 follow-up. Audited all 29 (was 26) renderer
  `.catch(() => {})` sites; 23 kept (mount-time/passive display fetches, true polls,
  2 deliberate best-effort calls: LBDIR auto-retrieve, Pipeline stopRun server cancel),
  6 fixed where user-initiated actions failed invisibly. No new locale keys: Pipeline
  reuses translated verify.toast.* keys; Scraper/Spectrograms keep their screens'
  hardcoded-English convention. gui-check: node types + renderer types + build PASS.
Fixed: gui_next ScreenPipeline.tsx: VerifyStageContent copy-report now toasts
  ok/bad via shared Toast primitive (was silent; its ScreenVerify twin already toasted).
Fixed: gui_next ScreenScraper.tsx: LogPanel Copy button flashes "Copied ✓"/"Copy failed"
  (screen has no toast infra; local label feedback).
Fixed: gui_next ScreenLibrary.tsx: forum-post toasts no longer claim "link copied" when
  the clipboard write failed — copyUrls returns success and gates the copied-suffix.
Fixed: gui_next ScreenDbEditor.tsx: loadSchema surfaces errors via setStatus (matches loadRows).
Fixed: gui_next ScreenSpectrograms.tsx: Stop button toasts "Stop failed" on request failure.
Fixed: gui_next ScreenTapeMatch.tsx: A/B play() rejection reverts playing state (UI no
  longer stuck showing "playing" after autoplay/decode failure).

[2026-07-15] — docs: TODO-244 PROJECT.md reference sections regenerated from code — STRUCTURE_REVIEW COMPLETE
Context: final STRUCTURE_REVIEW session (P1, items 1-8 + item 19 listing + item 12 convention
  note). Review closed: doc moved to instructions/complete/, sole survivor item 15 -> TODO-243.
  Also committed the uncommitted 07-14/07-15 session tail first (84fa1e1f: TODO-214 fingerprints
  gated OFF, TODO-183 close, ledger moves) so this work got its own clean commit.
Changed: PROJECT.md (+428 lines): route tables for 78 undocumented Flask routes (~26 new
  group sections); 12 missing schema blocks (lb_master, lb_status_history, my_collection,
  collection_meta, my_wishlist, bobdylan_*, setlistfm_*, friend_collection*, wtrf_downloads),
  each flagged MASTER/USER; file tree regenerated from disk (gui_next/ layout, 12 backend
  modules, instructions/, docs/, ~26 test files, 13 tools/ scripts); gui_next screens table
  now 24 files (hardcoded count dropped), +lbUrl.ts/useResizableColumns.ts store rows; 4 stale
  data/pages|attachments refs -> data/site/detail|files; preload IPC list = actual 10-member
  window.api surface; port-5174 note enumerates all real sites; GUI Conventions retitled
  "Legacy GUI Conventions (frozen)" + new gui_next conventions section; concert_ranker listing
  gains quality_score.py/text_features.py; API error-shape convention note added.
Added: tools/check_project_refs.py — drift checker extracting routes/@app.route, tables/CREATE
  TABLE (excl. *_new migration temporaries), gui_next screens, backend modules from disk and
  requiring each to be mentioned in PROJECT.md; exit 1 on drift. Clean run: 294 routes,
  62 tables, 24 screens, 42 modules, 0 missing. Wired into /session-close step 5.
Notes: review's fingerprints/audio_tracks tables (item 2) don't exist in current code
  (taper_fingerprints computes in-memory) — nothing to document. ScreenFingerprint had already
  been documented since 07-04; 4 screen rows were truly missing, not 5.

[2026-07-15] — refactor: STRUCTURE_REVIEW P2+P3 cleared (items 9-14, 16-20) — dead code removed, site URL + conventions consolidated
Context: working through instructions/STRUCTURE_REVIEW.md (2026-07-04) bottom-up. Three commits:
  a305caf2 (P3), 30d97229 (item 9), 8f689b3a (items 10-14). Remaining: item 15 -> TODO-243,
  P1 doc regeneration -> TODO-244.
Fixed: backend/db.py — checksum-lookup detail_url built from int LB without zero-padding
  (LB-42.html -> 404); now uses paths.detail_url() which pads to 5 digits.
Added: backend/paths.py — SITE_BASE_URL + detail_url(lb), single source for losslessbob.com URLs
  (backend twin of BUG-221's lbUrl.ts). backend/app.py — JSON @app.errorhandler(Exception) in
  create_app(): unhandled exceptions return {"error": ...} 500 instead of Flask's HTML page;
  HTTPExceptions pass through. gui_next lib/lbUrl.ts — exports LB_SITE_BASE + lbLabel();
  ScreenScraper's two hardcoded base-URL literals replaced.
Changed: scraper/site_crawler/flat_file/forum_poster/app/db all derive from SITE_BASE_URL;
  checksum_utils.md5_file is the one canonical file-MD5 (raising; compute_md5 delegates,
  importer/scheduler import it); module loggers standardized to logger=getLogger(__name__) in
  db.py (10 inline calls + 3 local variants + 5 orphaned local imports), sharing.py, scheduler.py.
Removed: stray 0-byte backend/losslessbob.db; committed smoke-run output tests/pipeline_smoke_*
  (now gitignored; their BUG-200..202 ids were generator placeholders colliding with real ledger
  ids); tools/_wtrf_batch_85_runner.py; concert_ranker/BUILD_REPORT.md. Moved:
  backend/debug_forum_post.py -> tools/ (standalone CLI diagnostic); concert_ranker/test_pipeline.py
  -> tests/test_concert_ranker_pipeline.py, converted from print-only script (zero asserts, pytest
  collected nothing) to a real test — found its implied orderings no longer hold under production
  calibration (decent-AUD vs muddy-AUD synthetics within 0.009; lossy sibling unflagged); asserts
  kept to the stable invariant (clean SBD ranks #1).
Notes: full suite 799 passed (one order-dependent flake in test_db_lookup: daemon migrate_lb_master
  thread from an earlier test — pre-existing, passes on rerun). Renderer tsc is at 0 errors; the
  14-error ScreenScraper baseline in the gui-check skill doc is stale (updated this session).
  app.py static HTML footer link + html_utils.py docstring keep the URL literal deliberately.

[2026-07-15] — chore(backend): TODO-183 Concert Ranker CLOSED — sibilance_ratio_db demoted to informational, remaining riders won't-do
Context: the ranker has been functionally complete and in production for weeks (13,752 recordings
  scored; AUD CV Spearman 0.66 / SBD 0.56; GUI Quality tab since 07-01). tj signed off closing the
  open riders as not worth the value. One closing code action: resolved the open sibilance decision
  as option (b) from the 06-30 investigation.
Changed: concert_ranker/config.py — POLARITY["sibilance_ratio_db"] -1 -> 0 (informational; never
  de-confounded from brightness: rho +0.34 above 9 kHz hf_ceiling, artifact below it), its
  SEVERITY_BANDS entry ("slightly essy"/"sibilant") removed globally + from _build_decade_bands;
  sibilance_crest (validated, rho -0.34..-0.65 correct sign) kept at polarity -1 as the sibilance
  defect signal. concert_ranker/scoring.py — sibilance_ratio_db removed from FAMILY_METRICS["tonal"]
  fusion. Feature extraction (_sibilance_native) unchanged; both metrics still stored per recording.
Won't-do (documented in TODO_DONE-183): 9kHz-gate rescan, SBD-per-decade bands, pop/click detector,
  DFF-on-Linux, lossy_flag calibration, dynamic_range_dr production, band-label phrasing polish.
Verified: tests/test_concert_ranker.py 49/49 green.

[2026-07-15] — feat(backend): TODO-214 Layer-2 taper fingerprints BUILT + CALIBRATED — gated OFF pending tj sign-off
Context: implemented the Session-5 design (WORK_PACKAGE_2026-07-14.md), then calibration forced a
  redesign: raw argmax scoring was only ~53% precise on a 5-fold confirmed-tier holdout. Shipped
  design uses THREE gates — score >= 150, top1−top2 margin >= 80, and winner in a per-run
  cross-validated reliable-taper set (per-taper precision >= 0.90 with >= 10 gated assignments) —
  plus exclusion of ALL known taper alias tokens from every profile. Holdout at shipped gates:
  96.2% precision / 23.6% coverage / 12 reliable tapers / 93 would-be inferred rows.
Added: backend/taper_fingerprints.py — Monroe weighted-log-odds vocabulary profiles, DSU
  poisoned-component exclusion (conflict=1 / curator-unresolved components contribute no source
  docs), 3-gate infer(), K-fold calibrate(). LAYER2_ENABLED=False kill-switch (see below).
  tests/test_taper_fingerprints.py (18 tests; suite 44/44 green).
Changed: backend/taper_attribution.py — _compute_layers01() extracted from recompute() (returns
  rejects too); recompute() calls Layer 2 between _propagate_weak and the reject/unresolved
  re-apply, gated on LAYER2_ENABLED. tools/attribute_tapers.py — new --calibrate-fingerprints
  (read-only gate sweep + reliable-taper table).
Fixed (pre-ship, in-flight code): _poisoned_lbs missed edge-less curator-unresolved lbs (never
  entered the DSU); non-deterministic evidence-token ordering on tied weights.
Decision: NOT enabled — spot-checks of would-be rows on the real unattributed pool found
  systematic misattributions invisible to the holdout (profiles latch onto era/setlist vocabulary,
  description formatting style, and 16bit/44.1khz-type boilerplate; docs explicitly crediting
  OTHER tapers — Walkin' Dude, mary_lynch, Ray Ackerman, hanno — were assigned to profile owners;
  est. true precision ~60–75%, below the spec's >= 90% bar). Era-matched backgrounds and
  gear-token-only vocabularies were prototyped; neither eliminates the leakage. Verified: 44/44
  tests; --dry-run recompute writes Inferred: 0 with the flag off (6,702 rows, identical to
  pre-Layer-2 output).
Decided (tj, same day): leave disabled, revisit later — TODO-214 closed (won't-ship, revisit
  options preserved in WORK_PACKAGE_2026-07-14.md Session 6); FABLE_TAPER_ATTRIBUTION.md spec
  git-mv'd to instructions/complete/ (all code/doc references repointed, instructions/README.md
  row updated); taper_attribution.py tier docstring updated (inferred tier implemented but gated).

[2026-07-14] — feat(backend): TODO-226 COMPLETE — BobTalk/notes full-text search + Library lens search UI
Context: discovery shrank the scope — Part A's show-page surfacing (BobTalk quote, notes, NET
  concert #, chronicle) had already shipped with the TODO-162 P5b Olof tab in DetailPanel; the
  entry text was stale. Only the search was missing. Data: 859 events with bobtalk, 2,874 with
  notes (of 4,924) — LIKE suffices, no FTS5, no schema change.
Added: backend/db.py get_olof_bobtalk_search() (+_olof_like_pattern/_olof_snippet) — case-
  insensitive LIKE over olof_events.bobtalk/notes with %/_ escaping, ~60-char context snippets,
  both-fields dedupe (bobtalk wins), bobtalk-before-notes then date ordering. backend/app.py
  GET /api/olof/bobtalk_search (q min 2 chars else 400, limit capped 200) in the local-only olof
  route block. tests/test_olof_bobtalk_search.py (10).
Added: gui_next ScreenLibrary.tsx BobTalkSearch — speech-bubble IconButton + dropdown next to the
  performance-lens search (FilterMenu outside-click/Escape idiom), 300ms debounce, results show
  date + venue + snippet (italic for bobtalk); clicking navigates the lens to the show via the
  same selection path as a manual row click (un-collapse year, scrollToIndex, open DetailPanel);
  dates with no library rows render disabled with a "Not in library" hint. New Icon 'message'.
  Locale keys library.olof.search.* — en + DeepL de/fr/es/it/nl (4,730 chars).
Verification: full suite 780 passed / 5 skipped; tsc node+web 0 errors; production build clean.
  Reviewed subagent-reported git-stash incident: working tree verified clean, both pre-existing
  stashes intact, only intended files changed.
Bookkeeping: PROJECT.md olof route table + TODO-226 closed. TODO-240 opened for the TODO-223
  operational tail (trigger run_batch when the venue resolve batch — 652/4071 at close — finishes).

[2026-07-14] — feat(backend): TODO-223 COMPLETE — gazetteer wired into geocoder, map city-level flag (bite 3 of 3)
Context: bites 1–2 built venue_geocoded + the resolution ladder; this bite makes the gazetteer
  actually feed the map. High-value discovery: location_geocoded held only ~117 rows with 6,584
  distinct entry locations un-geocoded — gazetteer inheritance is the mechanism that populates the
  map without burning Nominatim calls.
Added: backend/geocoder.py — _venue_lookup_for_location()/_venue_key_for_location() derive the
  gazetteer (venue_norm, city_norm) key from the structured sources in seeding priority order
  (olof_events, setlistfm_shows, bobdylan_shows), normalizing via venue_gazetteer._norm_venue/_norm_city
  (deferred import; single source of truth for key form). run_batch(): eligible locations first
  inherit a resolved venue_geocoded pin (lat NOT NULL, source NOT IN seeded/failed) with no API call
  and no rate-limit sleep — source='gazetteer_venue', or 'gazetteer_city' + confidence capped
  'medium' for city pins (matches the TODO-222 cap; keeps the map's confidence != 'low' join);
  note records the venue key + gazetteer source. place_manual(): a fix whose location derives a
  venue key also upserts venue_geocoded (source='manual', manual_override=1 — resolve_venues never
  overwrites it) and immediately propagates to every other non-manual, non-skipped location_geocoded
  row at that venue (source='gazetteer_manual').
Added: backend/db.py get_map_data() emits city_level (bool; setlistfm_city/city_geocode/
  gazetteer_city/*-city sources); gui/resources/map.html popup shows a muted "city-level location
  (venue not yet pinned)" hint — deliberate narrow exception to the gui/ freeze: map.html is the
  shared Leaflet renderer that gui_next ScreenMap iframes, so the flag must live there (plain-JS
  page, hardcoded English like its other strings; no gui_next locale change).
Changed: backend/venue_gazetteer.py seed_venues() skips + cleans purely-numeric/empty venue keys
  (_is_numeric_or_empty_venue/_cleanup_numeric_junk; live run deleted 38 junk rows, table now 4071).
Fixed: backend/venue_gazetteer.py resolve_venues() now commits per venue — the 25-row batch commit
  held the SQLite write lock across the next venues' network waits (minutes at a stretch), which
  crashed backend startup with "database is locked" while a resolve batch ran. Found live when the
  post-deploy backend restart collided with the full resolution run.
Verification: +18 tests (tests/test_geocoder.py, test_venue_gazetteer.py) — key derivation/priority/
  miss, run_batch inheritance/fallthrough, place_manual propagation + skip cases, junk seed/cleanup.
  Full suite 770 passed / 5 skipped; gui_next tsc (node+web) + production build clean; backend
  restarted (uptime-verified) and coexists with the live resolve batch after the lock fix.
Operational: full resolution batch running (per-venue commits, ~2h; 280 resolved at last check —
  153 bounded_venue / 25 wikidata / 102 city). Follow-up once it completes: trigger geocoder
  run_batch so the 6,584 un-geocoded locations inherit pins (mostly zero API calls).

[2026-07-14] — backlog completion drive: landed in-flight GUI/docs work, closed 4 TODOs + 1 BUG
Context: session goal was shortening the backlog — close churners, not advance everything a little.
Changed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: library picks now show a muted
  known-taper fallback pill (taperBadgeLabel, tone=mute) when a taper is known but not confirmed —
  confirmed tapers keep the info-tone badge (in-flight from 07-13, committed 8fe70a3b after
  gui-check: node types PASS, renderer types PASS at 0 errors — old 14-error ScreenScraper baseline
  is gone — build PASS; reuses existing i18n keys, no locale run needed).
Added: instructions/FABLE_VISUAL_VERIFICATION.md (Electron visual-verification driver spec,
  attempt 3) + README.md index row, status "ready — not started" (in-flight from 07-13, 1d110c99).
Closed (no code change): TODO-233 by rescope (pt1 shipped 07-14, pt2 continues as TODO-235,
  pt3 out of scope); TODO-281 done — the 36 listed ruff violations no longer exist (ruff check
  clean across backend/, pytest 752 passed / 5 skipped; pre-commit auto-fix + feature commits since
  06-09 eliminated them), retroactive polish pass declined; TODO-209 won't-fix (cosmetic legacy
  ids, all in closed/archived entries, ledger.py prevents new collisions); TODO-179 won't-do
  (tentative "maybe"); BUG-230 won't-fix (dev-only cosmetic gear icon, reopen if packaged
  AppImage shows it). All five were user decisions 2026-07-14.

[2026-07-14] — feat(backend): TODO-223 (in progress) — venue gazetteer resolution ladder (bite 2 of 3)
Context: Bite 1 seeded 4109 distinct venues unresolved. This bite adds the ladder that turns a seeded
  venue into a coordinate. Planning premise correction: the ladder was specified to anchor on
  setlist.fm city coords (TODO-222), but those columns (setlistfm_shows.city_lat/city_lon/city_state)
  are entirely NULL — the force re-scrape that backfills them was never run (0/4131 rows). So the
  ladder anchors on a setlist.fm coord WHEN present, else a Nominatim city geocode — self-sufficient
  today, and it auto-upgrades if the backfill later runs.
Added: backend/venue_gazetteer.py resolution ladder, reusing backend.geocoder's geocode_one /
  _city_viewbox / 429-retry constants. Per seeded venue, stopping at the first hit: (1) bounded
  Nominatim venue-name search inside a ~30km box around the city anchor (source='bounded_venue');
  (2) Wikidata P625 via an mwapi EntitySearch SPARQL query, accepted only within 50km of the anchor
  so a same-name venue elsewhere is rejected (source='wikidata', covers demolished venues OSM lacks);
  (3) the city anchor itself as a city-level pin (source='setlistfm_city' or 'city_geocode',
  confidence='city'); else source='failed'. City anchors are cached per city so each city costs at
  most one Nominatim call. resolve_venues() drives the batch — processes source IN ('seeded'[,
  'failed' when retry_failed]), skips manual_override=1, updates in place, commits every 25, honors a
  limit. `python -m backend.venue_gazetteer resolve [N]` runs it. Helpers: _haversine_km,
  _geocode_retry (standalone 429 backoff + 1.1s Nominatim politeness), _city_anchor,
  _setlistfm_city_coord, _wikidata_venue_coord.
Verification: live smoke test (limit=3) resolved 1 bounded_venue + 2 city_geocode, 0 errors. Tests
  tests/test_venue_gazetteer.py +13 (27 total): haversine, anchor setlistfm-vs-geocode + cache,
  each ladder step, Wikidata accept/reject-by-distance/network-error, resolve_venues update + manual
  skip + limit. 88 passed with test_geocoder.
Deferred: the full 4109-venue resolution is a ~1-2h rate-limited Nominatim+Wikidata run — trigger
  it deliberately with `python -m backend.venue_gazetteer resolve`. Bite 3 wires resolved pins into
  geocoder run_batch (inherit, dedupe Nominatim) + place_manual venue propagation. Minor follow-up:
  38 purely-numeric junk venue seeds (~0.9%) should be filtered at seed time; the ladder currently
  falls them back to a city pin.

[2026-07-14] — feat(db): TODO-223 (in progress) — venue gazetteer table + seeding (bite 1 of 3)
Context: Shows repeat venues, so geocoding each show re-solves the same coordinate and scatters any
  manual fix across dates. TODO-223 builds a venue-level table so each distinct venue is solved once
  and every date inherits the pin. This is the first of three bites (table+seed, then the resolution
  ladder, then run_batch inheritance + place_manual propagation).
Added: backend/db.py — venue_geocoded(venue_norm, city_norm, venue, city, region, country, lat, lon,
  source, confidence, manual_override, note, geocoded_at), PK (venue_norm, city_norm), + source
  index. CREATE TABLE IF NOT EXISTS in SCHEMA_SQL (idempotent, additive).
  backend/venue_gazetteer.py — _norm_venue/_norm_city normalization (casefold + drop punctuation +
  collapse whitespace; the CITY key takes only the first comma-segment so a venue does not fragment
  across source-specific city strings like 'Birmingham' vs 'Birmingham, AL' vs 'Birmingham,
  Alabama'; venue keys keep commas since venue names legitimately contain them). seed_venues()
  enumerates DISTINCT concert venues from olof_events (event_type='concert'), setlistfm_shows and
  bobdylan_shows — richest source first — and inserts each unresolved (source='seeded', lat/lon
  NULL) via ON CONFLICT DO NOTHING, so re-seeding never disturbs resolved or manual_override rows.
Data: seeded 4109 distinct venues (the first-comma city key collapsed 6029→4109 by de-duplicating
  the same venue across city-string variants). Idempotent: a re-run inserts 0. bobserve 2022+
  festival venues (e.g. Ameris Bank Amphitheatre) now seed correctly thanks to the event_type fix.
Tests: tests/test_venue_gazetteer.py (14) — normalization keys incl. city-collapse and
  venue-comma-preservation, seed enumeration + concert filter + dedup, re-run idempotency preserving
  a manual row, tolerance of missing optional source tables. Full suite 739 passed, 5 skipped.
Deferred (later bites): resolution ladder (bounded Nominatim near the setlist.fm city coord →
  Wikidata SPARQL for demolished venues → setlistfm_city fallback), then geocoder run_batch
  inheriting gazetteer pins and place_manual writing venue-level fixes.

[2026-07-14] — fix(scraper): bobserve field normalization — 66 festival/benefit concerts now geocode; US location fields de-shifted (TODO-228 follow-up, unblocks TODO-223)
Context: TODO-228 loaded 391 bobserve shows (2022+) into olof_events, but three field-quality bugs
  made the data unusable by the geocoder (which trusts the DSN taxonomy) and by any concert-venue
  seed. (1) bobserve event_type is free text ('concert - outlaw music festival', 'benefit - farm
  aid', 'soundcheck', 'tribute speech - …') where the geocoder tests event_type=='concert' exactly,
  so 64 real festival/benefit concerts were flagged skipped_not_concert. (2) US location lines omit
  country and sometimes carry a district ('Hollywood, Los Angeles, California'); the shared
  _split_city_region_country assumed 'City, Region, Country' and shifted them to
  city=Hollywood/region=Los Angeles/country=California. (3) A few non-standard pages captured
  tour_name='Musicians' (a section header) or an 'Info via bobserve: <url>' line.
Changed: backend/bobserve_parser.py — _normalize_event_type() maps the pre-'-' prefix onto the DSN
  canonical set (concert|session|rehearsal|broadcast|interview|other; benefit→concert since Farm Aid
  et al. are real gigs, soundcheck/tribute→other), preserving any lost detail (festival/benefit/
  soundcheck qualifier) in notes as 'event_type_raw: …' — but only on a real difference, not a
  case-only 'Concert'→'concert' one (74 rows, not 391). _split_bobserve_location() + _US_STATES
  detect a trailing US state → region=state, country='' (matching DSN's empty-country-for-US
  convention), city=the token before the state (leading district dropped); non-US rows still defer
  to _split_city_region_country. tour_name extraction skips 'Musicians' / 'Info via bobserve:' /
  'http…' tail lines. Re-parsed the mirrored data/olof/bobserve_pages/ (idempotent, no network).
Data: source='bobserve' event_type now concert=383 (was 317, +66 to the geocoder), other=7,
  rehearsal=1 — zero 'concert -'-prefixed strings; 270 US rows carry empty country + state region;
  0 tour_name='Musicians' remain.
Tests: tests/test_bobserve_parser.py (new, 25 tests) — event_type mapping table, US 2-part /
  3-part-with-district splits, non-US unchanged, tour_name guard, case-only-no-notes. 86 passed
  (with test_geocoder).

[2026-07-14] — feat(backend): TODO-228 (CLOSED) — bobserve.com setlist scraper supersedes the PDF-chronicle approach for 2022+ shows
Context: TODO-228 assumed the 2013+ Yearly Chronicle PDFs just needed text extraction to feed the
  existing chronicle-appendix setlist parser. Extracting real 2022/2023 chronicle PDFs directly
  found they carry NO per-show setlists at all — a calendar diary + a bare tour-itinerary table
  (date/city/venue only). bobserve.com's own current site instead publishes a full setlist
  database, one page per show at /setlist?event=<id>, with real per-song setlists (incl. cover
  credits), confirmed against real 2022 (Oslo) and 2023 (NYC) pages. That's the actual 2022+
  source; the PDF-itinerary path was not built.
Added: backend/bobserve_fetcher.py — two-step mirror: bobserve.com/eventsperiod?period=<year>
  lists every show's event id chronologically (ids themselves are NOT chronologically assigned,
  confirmed: id 4000 -> a 2004 show, id 3950 -> a 2014 show, so the index page is the only
  reliable id-discovery path), then each event page is fetched once into
  data/olof/bobserve_pages/, registered in the shared olof_pages table (corpus='bobserve').
  Reuses backend.olof_fetcher's browser-UA/retry/rate-limit helpers.
  backend/bobserve_parser.py — extracts each page's `data-clipboard-text` attribute (a clean,
  pre-formatted plain-text show summary bobserve renders for its own copy button) rather than
  the surrounding Tailwind markup; parses date/venue/city/region/country/event_type/songs/
  tour_name/musicians into olof_events (source='bobserve', event_id = 9,000,000 + bobserve's own
  id — a disjoint range from DSN's ~440620 max and chronicle_appendix's year*1000+seq) and
  olof_songs, reusing EventRecord/SongRecord/_split_city_region_country/_split_title_credits
  from olof_parser. A medley entry wraps its second song onto an unnumbered continuation line
  (confirmed: event 4801, '8.Medley To Be Alone With You' / 'Watching The River Flow' with no
  leading number) — folded into the preceding song's title with ' / ' rather than silently
  dropping the whole show's setlist, which the first pass at the song-block detector did.
Data: full crawl of 2022-2026 (391 pages, 0 fetch errors) -> 391 olof_events / 6137 olof_songs,
  source='bobserve'. 373 pages parsed clean; the 18 partial are all legitimate (15 are
  not-yet-played 2026 shows with no setlist posted yet, 3 are non-dated entries like a tribute
  video/rehearsal/speech). /api/olof/date, /api/olof/event, and the setlist-fingerprint scan
  (TODO-225) all query olof_events/olof_songs unfiltered by source, so 2022+ shows surface
  through the existing GUI/matching paths with no further wiring.
Docs: PROJECT.md — documents the three disjoint event_id ranges and marks the chronicle-appendix
  setlist path (source='chronicle_appendix') as superseded/never populated for its stated reason.


Added: backend/setlistfm.py + backend/db.py — setlistfm_shows gains city_lat/city_lon/city_state
  columns (PRAGMA table_info migration guard), populated from the setlist.fm API's
  venue.city.coords/stateCode at scrape time — a zero-geocoding, guaranteed city-level coordinate.
  Existing rows backfill on the next force re-scrape (POST /api/setlistfm/update {force:true}).
Changed: backend/geocoder.py — folded two new steps into the TODO-220 cascade in run_batch():
  (1) once a bare venue name and a known setlist.fm city coordinate are both available, a
  Nominatim search for just the venue name, bounded to a ~30km viewbox around that coordinate
  (source='bounded_venue'), is tried right after the full structured-string attempts —
  Nominatim's unconstrained hit rate on venue names alone is poor but improves once spatially
  constrained; (2) if every attempt up to that point misses, the known setlist.fm city coordinate
  is used directly as a fallback pin with no further Nominatim call (source='setlistfm_city',
  confidence capped medium) before falling to a city-text Nominatim geocode. The four structured
  lookup helpers (_get_bobdylan_shows_location_string etc.) now also return a bare venue_only
  string alongside the existing full/city_only pair. geocode_one() gained optional
  viewbox/bounded params. Wikidata SPARQL (TODO-222's optional step 3, for demolished venues) is
  deferred to TODO-238's venue-level table, which already plans it explicitly.
Tests: tests/test_geocoder.py + tests/test_setlistfm.py — updated the 3 structured-lookup
  functions' expected tuples, added coverage for _get_setlistfm_city_coords, _city_viewbox,
  geocode_one's viewbox/bounded encoding, and both new cascade steps end-to-end via run_batch();
  700 passed, 5 skipped.

[2026-07-14] — fix(backend): BUG-246 (CLOSED) — remaining-writer audit; guard the last two DB writers that could split reads/writes across databases
Context: BUG-246 (live show_picks wiped 2026-07-10) was fixed defensively in picks._write_picks the
  same day; the ticket left a REMAINING AUDIT — sweep the other db_path-taking writers for the same
  first-init-wins exposure (a writer READS current state via get_connection(db_path) but commits a
  state-dependent write through the get_write_queue() singleton, which is first-caller-wins and may
  be bound to a DIFFERENT db). Swept taper_attribution, flat_file, tapematch_sync, parse_lineage,
  the scrapers, geocoder, importer, song_index, setlist_fingerprint.
Found: two unguarded matches. (1) taper_attribution._write_attributions — wholesale DELETE FROM
  taper_attributions + reinsert of read-derived rows through the unguarded queue (WIPE class,
  identical shape to the original show_picks bug). (2) flat_file.apply_flat_file_release — an
  add/change/remove diff computed from a get_connection(db_path) read, committed through the
  unguarded queue (DESYNC class: a path mismatch skips real removals rather than wiping). All other
  swept writers are safe: tapematch_sync reads+writes on the same conn (never uses the queue),
  parse_lineage/scrapers/geocoder/importer are upsert-only or externally-driven (no read-then-
  wholesale-replace), and song_index/setlist_fingerprint already carry the guard.
Fixed: added the sanctioned picks-style _run_write(fn, db_path) helper (mirrors
  setlist_fingerprint.py) to backend/taper_attribution.py and backend/flat_file.py — when
  db_path != the queue's bound db, the write goes DIRECTLY via get_connection(db_path) instead of
  the singleton. Routed taper_attribution._write_attributions (+ single-row confirm/reject/
  mark_unresolved, all of which take db_path) and flat_file.apply_flat_file_release through it. No
  empty-payload refusal added (unlike picks): the path-match guard is the whole fix and
  taper_attributions can be legitimately empty on a minimal DB.
Verified: 42 tests pass (tests/test_taper_attribution.py + tests/test_show_picks.py), including a
  new regression test test_write_targets_db_path_not_queue_binding that binds the queue to DB A,
  recomputes against DB B, and asserts the taper_attributions rows land in B and NOT in A. BUG-246
  closed.

[2026-07-14] — feat(backend): TODO-213 taper conflict queue — 'kind' filter + "can't determine" verdict; mention queue cleared
Context: the /taper-review conflict queue held 53 conflict=1 rows, but 22 are series-vs-series
  (two legitimate taper series on one over-merged recording_families family) — un-pickable in the
  hand queue and owned by TODO-234 (family split), while polluting the review flow. The other 31
  are mention-vs-mention. Separately, a genuine same-family two-taper conflict is a historical
  documentation error with no ground truth, so confirm (fabricates a pill) and reject (implicitly
  picks the sibling on recompute) are both dishonest — the queue had no way to say "attribute
  nothing" and move on. All 53 conflict rows were tier 'propagated' (no pill), so nothing was
  mis-badged; the cost was pure queue-gating.
Added: backend/taper_attribution.py — `_is_series_vs_series()` (reuses `_SERIES_CODE_RE` +
  `_CONFLICT_CAND_RE` to classify a conflict as all-series-code candidates) and a `conflict_kind`
  arg on `list_attributions()` ('mention' excludes series-vs-series, 'series' keeps only them).
  New `mark_unresolved(lb)` curator API (mirrors `reject()`): upserts a sticky `taper_confirmations`
  'unresolved' row + deletes the `taper_attributions` row immediately. `_apply_unresolved()` drops
  every taper for an unresolved lb during recompute (vs reject's single-taper suppression);
  `_apply_confirmations()` now returns `(rejects, unresolved)` and recompute re-applies both after
  propagation. Idempotent + sticky (verified: full recompute keeps 31 parked, 0 attribution rows,
  22 conflicts remain).
Added: backend/app.py — `POST /api/tapers/attributions/<lb>/unresolved` (curator-gated); `kind=`
  param on the attributions list route (validated, 400 on bad value).
Changed: backend/taper_review.html — queue fetches `conflict=1&kind=mention` (series-vs-series no
  longer shown); new "Can't determine (historical conflict)" button → `/unresolved`; done-state
  explains the series exclusion points to TODO-234.
Data: bulk-parked the 31 mention-vs-mention conflicts as 'unresolved' via the live endpoint after
  a DB backup (data/backups/…_pre_unresolved_bulk.db) — /taper-review hand queue now empty; 22
  series-vs-series remain for TODO-234. taper_confirmations ledger: 58 confirm / 10 reject / 31
  unresolved.
Verified: 25 taper-attribution tests pass; apply-logic unit test (unresolved suppresses all tapers,
  reject/confirm unaffected); live endpoint checks (kind=mention→0, kind=series→22, bad kind→400).

[2026-07-14] — feat(backend+gui): TODO-232 part 2 (CLOSES TODO-232) — A/B auto-pick start point (quiet vocal passage) + GUI prefill
Context: TODO-231/232 A/B listening defaulted the start field to 0 s (start of performance). The LB
  curator method (TODO-187) is to A/B on a musically quiet passage where a vocal is still clearly
  present. With part 1 (RMS match) already shipped this session, this closes TODO-232.
Added: backend/ab_clips.py — pick_start_frame() (pure, audio-free scorer over a concert_ranker
  TrackCache: per-frame 1-4 kHz vocal band from stft_mag vs its 20th-pct floor, minus 0.5x the
  broadband-energy excess, so a quiet-but-vocal window wins over both silence and loud
  instrumentation); _decode_mono_region() (ffmpeg f32le decode-to-memory, mirrors embed_extract);
  auto_pick_t_sec() decodes a bounded perf-time search region (skip 60 s head/tail, cap 300 s so a
  2 h show is never fully decoded), builds the TrackCache @22050, scores it, and maps the winning
  window back to perf time (region_start + picked/factor). Blanket-safe: any decode/analysis
  failure logs + returns a fallback t, never blocks a clip request. _resolve_auto_t_sec() analyzes
  the pair's reference source (else lb_a). generate_ab_clips() now takes t_sec: float|None and
  auto-picks when omitted (after the eligibility/recency gates, before the perf-bound check),
  returning the resolved t_sec.
Changed: backend/app.py — POST /api/ab_clip: t_sec is now optional (dropped from missing_fields;
  still 400 bad_t_sec on an unparseable value); omitted -> backend auto-picks. Docstrings updated.
Changed: gui_next ScreenTapeMatch.tsx (AbPlayerPanel) — start field defaults blank ("auto"); blank
  omits t_sec from the POST so the backend auto-picks, and the response's t_sec pre-fills the field
  so the curator can override + reload. New i18n keys tapematch.abPlayer.autoPlaceholder/
  autoPickHint (en + de/fr/es/it/nl via DeepL).
Verified: 37 ab_clips tests pass (4 new: pick_start_frame scorer, None-underflow, generate+route
  omitted-t_sec); real-ffmpeg end-to-end confirms auto-pick lands in a planted quiet-vocal region
  and the factor!=1 perf-time mapping; gui-check (node/renderer types + build) PASS.

[2026-07-14] — feat(backend): TODO-233 part 1 + TODO-232 part 1 — A/B listening: constant-speed-offset eligibility (resampled to reference speed) + RMS level-match
Context: only ~1/3 of sources qualified for A/B listening (reference/aligned only), so most
  ScreenTapeMatch pairs showed "Not cleanly aligned for A/B listening yet". constant-speed-offset
  is the single largest speed bucket (1,854 sources) and its perf->source map is fully derivable
  from the sources table (rate = 1 + speed_ppm/1e6, offset = trim_head_sec) — no run-archive
  parsing needed. speed_ppm confirmed fully populated for those rows; run_id is a sortable
  YYYYMMDD_HHMMSS so the stale-label recency gate is directly expressible.
Added: backend/ab_clips.py — constant-speed-offset added to ELIGIBLE_SPEED_KINDS; speed_factor()/
  raw_take_sec() and a factor arg on source_offset() generalise the perf->source map to
  `trim_head + t*factor` (mirrors embed_extract.py's nominal-time convention); build_clip() now
  extracts the raw dur*factor span, then _finalize_clip() speed-corrects it back to reference via
  `asetrate=44100*factor,aresample=44100` (only above RESAMPLE_MIN_ABS_PPM=50; reference/aligned
  keep the v1 straight cut). RMS level-match (TODO-232 pt1): _measure_rms_dbfs (ffmpeg
  volumedetect) + compute_gain_db normalise every clip to AB_RMS_TARGET_DBFS=-20 with a
  no-clip peak ceiling and a 30 dB max-gain cap. Stale-label recency gate (TODO-233):
  is_run_eligible() rejects speed labels from runs before the 2026-07-06 confidence tightening
  (commit 936e0a64); enforced in generate_ab_clips (409 not_eligible w/ run_id) and mirrored in
  the GET /api/tapematch/pairs ab_eligible enrichment so badges agree with POST. cache_filename
  now keys on speed_ppm too. get_source_info/get_pair_source_info select speed_ppm (PRAGMA-guarded
  for legacy DBs missing the column).
Changed: backend/app.py — ab_eligible enrichment adds is_run_eligible gate; POST /api/ab_clip
  docstring updated for the new eligibility tiers.
Verified: 33 ab_clips + 24 tapematch-route tests pass; real-ffmpeg smoke test confirms a 21 s
  raw clip at factor 1.05 finalises to 20.000 s at the -20 dBFS target under the peak ceiling.
Remaining: TODO-233 pts 2/3 (staircase/splice per-segment offsets; speed-unknown) and TODO-232
  pt2 (auto-pick quiet-vocal start point) stay open.

[2026-07-13] — fix(backend): TODO-213 — taper-attribution curation: exclude non-taper credits (lk/captain acid/jtt/robert), rename cb master→cb, downgrade bare mentions vs confirmed tapers
Context: tj worked the /taper-review conflict queue (68 confirm/reject decisions) and named a
  repeating pattern — NON-TAPER credits (curators / remasterers / transfer engineers) colliding
  with real tapers in a family, which the attribution engine surfaced as bogus conflicts and wrong
  taper-name badges (the specific complaint behind TODO-213).
Changed: backend/db.py — added `lk` (curator), `captain acid` (remaster), `jtt` (transfer/master
  engineer, "Mastered to Digital by JTT") to _NOT_TAPER, so they drop out of _TAPER_UNIVERSE and are
  never seeded as attribution candidates. A mention colliding with a real taper now auto-resolves to
  the real taper with NO conflict / no curation (e.g. LB-1945: ltd via LB-4396 vs captain acid via
  LB-4401 → ltd, conflict cleared). Kept them as _KNOWN_TAPER_ALIASES keys so the parser still
  collapses their spellings to one canonical token. Renamed canonical `cb master`→`cb` (cb is the
  taper; "master" = a master tape from cb). Removed `robert` from _KNOWN_TAPER_ALIASES entirely —
  too generic a bare token, it matched songwriter/personnel credits ("Robert Hunter", "Robert
  Friemark") in setlists (179 of its 198 attributions were false mentions).
Changed: backend/taper_attribution.py _propagate_strong — mention-downgrade rule. A bare `mention`
  (Layer 0's sole non-confirmed tier) no longer raises a conflict against a family's single
  confirmed series-code/explicit taper; per spec §4.2 the strong evidence wins silently and the
  mention member is flood-filled to the confirmed taper. Genuine strong-vs-strong disagreement
  (len(confirmed_tapers) >= 2, i.e. series-vs-series) still conflicts as before.
Data: migrated 185 entry_lineage + 19 taper_confirmations rows (cb master→cb); ran full
  deterministic taper_attribution.recompute() after each rule. Conflict queue 121 (stale 07-09
  snapshot; ~191 on a fresh recompute) → 161 (non-taper credits + cb) → 126 (robert) → 53
  (mention-downgrade). ~1200 spurious attribution rows dropped overall. Remaining 53 = 31
  genuine mention-vs-mention ambiguities (the real /taper-review queue) + 22 series-vs-series
  (tapematch family over-merge, for family-split review). DB backed up to
  data/backups/losslessbob_2026-07-13_221639_pre_todo213_curation.db.

[2026-07-13] — feat(backend+gui): TODO-212 (closes it) — recording-lens pick/curated badges + "any curated pick" view
Added: backend/db.py get_pick_badges() + GET /api/library/badges — flat
  {lb_number: {pickRank, absGrade, curated, taperConfirmed, taperReview}} map. Reuses the exact
  loaders get_performances() uses (so the two lenses can never disagree on a badge); only LBs with
  a signal appear, absent fields omitted. Empty on a fresh install pre-recompute.
Changed: gui_next ScreenLibrary.tsx — the recording lens (sourced from /api/search +
  /api/collection/prefetch, which join none of show_picks/quality/curated_lists/taper_attributions)
  now fetches /api/library/badges and merges it by lb_number client-side, same F4 pattern it already
  uses for TapeMatch families/prefetch (SPEC_INTEGRATION_NOTES.md F4). Rows render ★ recommended,
  curated pills, absGrade (owned), and a confirmed-taper pill that *upgrades* the raw free-text taper
  pill rather than duplicating it. Perf lens gains a combined "Any curated pick" view (curatedAny)
  alongside the per-curator carbonbit/10haaf views. Closes the last two deferred items from TODO-186's
  RANKING phase-4 close.
i18n: library.views.curatedAny added to en.json + de/fr/es/it/nl (DeepL).
Docs: TODO-187 verified complete (no code change) — concert_ranker/LB_KNOWLEDGE.md diffed against
  both live LosslessBob "what-it-means" source pages; all rating/comparison/EAC/notes semantics and
  17 terms / 22 images covered 1:1.

[2026-07-13] — feat(backend+gui): TODO-225 setlist fingerprinting curator review queue
Added: backend/setlist_fingerprint.py — scores an entry's folder tracklist against every Olof
  Björner setlist (olof_songs) to identify shows for entries whose date/location metadata is
  unusable ('various', empty/xx dates, or a location the TODO-221 geocoder filter parked in
  skipped_not_concert); candidates only (not bulk re-dating). Scoring blends entry_coverage,
  order-preservation (longest increasing subsequence of matched positions), and olof_coverage;
  matching reuses db.normalize_title_for_match/titles_match (containment-tolerant, same rule as
  compare_olof_setlist). New setlist_fingerprint_suggestions table (USER-tier, wholesale-
  recomputed per scan, curator dismiss status preserved across rescans). Suggestions only — never
  auto-applied to entries.
Added: backend/app.py — POST /api/fingerprint/scan, GET /api/fingerprint/suggestions, POST
  /api/fingerprint/suggestions/dismiss (curator-gated).
Added: gui_next/src/renderer/src/screens/ScreenFingerprint.tsx — curator review queue at
  /fingerprint (Curator nav group): scan button, status filter (pending/dismissed/all),
  expandable rows showing matched/missing songs, curator-only dismiss. New "fingerprint" Icon,
  nav entry, i18n across all 5 locales.
Added: tests/test_setlist_fingerprint.py — 10 tests (candidate selection, scoring/order,
  scan wholesale-replace + dismissed-status preservation, route + curator gating).
Changed: backend/db.py — _titles_match renamed to titles_match (public; now shared with
  setlist_fingerprint.py, not just compare_olof_setlist).

[2026-07-13] — feat(gui): TODO-158 batch forum posting via pasted LB list
Added: gui_next/src/renderer/src/screens/ScreenCollection.tsx — new "Post from list…" button
  opens ForumListModal, letting the user paste/type LB numbers (any separator) instead of
  multi-selecting rows; resolves against the full in-memory collection, shows matched/unmatched
  counts, then reuses the same preview_forum + post_forum sequence as the existing multi-select
  batch flow. Extracted the shared per-item post loop into runForumBatch() so the context-menu,
  toolbar multi-select, and new list-modal paths share one implementation instead of three copies.
Changed: gui_next/src/renderer/src/locales/en.json — added collection.forumList.* strings;
  de/fr/es/it/nl synced via /gui-next-i18n (also swept up unrelated pre-existing translation
  backlog in those five files, ~80-150 strings each, still English before this run).

[2026-07-13] — feat(backend): TODO-157 auto-create torrent + qBittorrent add on forum post
Added: backend/app.py post_forum — when no torrents record exists for the entry (and no
  torrent_id given), generates one via torrent_maker.make_torrent(lb, my_collection.disk_path)
  and adds it to qBittorrent via qbittorrent.add_torrent_from_db, reusing the same
  qbt_host/port/credential resolution as the existing qbt_add route. Runs after the TODO-159
  integrity gate, so a folder that already failed LBDIR verify is never auto-torrented/seeded.
  qBittorrent-add failure is reported (qbt_auto_add in the response) but doesn't block the
  forum post — the .torrent file was still created and can be added manually. Response gains
  torrent_auto_created/qbt_auto_add fields when this path fires.

[2026-07-13] — fix(backend): TODO-159 LBDIR verify gate before forum posting
Added: backend/app.py post_forum — before contacting WTRF, resolves the entry's
  my_collection.disk_path and runs checksum_utils.verify_folder() on it; blocks the post with a
  400 (mismatch/missing counts included) when status is fail or incomplete, so a folder whose
  audio no longer matches its stored checksums (BUG-120) can't be posted undetected. No-op when
  the LB isn't in my_collection.

[2026-07-13] — fix(gui): TODO-280 Collection tab header text overflow + missing i18n
Fixed: gui_next/src/renderer/src/components/table.tsx TH — headers had whiteSpace:nowrap but no
  overflow/textOverflow (unlike TD), so a header label wider than its resized column spilled
  unclipped into the next column instead of ellipsizing. Wrapped header content in a clipped
  inner span; resize-handle hit target unaffected.
Changed: gui_next/src/renderer/src/screens/ScreenCollection.tsx — "Type"/"Notes" column headers
  were hardcoded English, skipping i18n; now use t('collection.table.type'/'notes').
i18n: de/fr/es/it/nl synced via DeepL for the two new collection.table keys.

[2026-07-13] — docs: TODO-291 closed — r#### filename suffix is not per-recording source info
Investigated: grepped data/site/files/ archive-wide — only 57/7371 *.info.txt attachments carry
  a ".r####." filename suffix, and all 57 share the identical value r9453 across dates 1978-2004
  with no date/taper correlation; the 57 LB numbers cluster tightly in LB-04856..05215 (one
  import/scrape batch). The suffix is a session/collision-avoidance artifact of that batch, not
  a per-recording taper/source catalog id — a DB column would store a constant, not a signal.
  Closed as not-applicable.

[2026-07-12] — fix(gui): TODO-231 A/B player had no audio — missing CSP media-src directive
Fixed: gui_next/src/renderer/index.html — the Content-Security-Policy meta tag whitelisted
  http://127.0.0.1:5174 for connect-src/img-src/frame-src but had no media-src directive, so it
  fell back to default-src 'self' and silently blocked the AbPlayerPanel's <audio src=...> GET
  requests. POST /api/ab_clip (connect-src) succeeded — clips "loaded" fine — but the WAV bytes
  themselves never fetched, so Play produced no sound and no visible error. Added
  media-src 'self' http://127.0.0.1:5174.

[2026-07-12] — feat(backend+gui): TODO-231 (part 2/2, closes it) — A/B player widget
Added: gui_next/src/renderer/src/screens/ScreenTapeMatch.tsx — AbPlayerPanel, rendered next to
  JudgmentPanel when a matrix pair is selected. Position (t_sec) + duration inputs, "Load clips"
  hits POST /api/ab_clip; once loaded, two hidden <audio> elements are started together and stay
  sample-aligned for the clip's fixed duration, so the A/B chip toggle is an instant (un)mute swap
  rather than a reload/reseek. Disabled (inert controls + notEligible pill) when
  pair.ab_eligible !== true. Per-error messaging for the ab_clip failure taxonomy (not_eligible/
  t_out_of_range/folder_missing/locked).
Fixed: backend/app.py tapematch_pairs_for_date — ab_eligible enrichment computed eligibility from
  the (possibly stale) run_id synced into tapematch_pairs, not each pair's actual latest common
  tapematch run; a pair could show ab_eligible: false while POST /api/ab_clip accepted it fine
  (observed live: LB-5953/LB-6162 1995-07-08 — synced run had speed_kind staircase/splice, two
  newer un-synced runs had aligned/reference). Now resolved per-pair via
  ab_clips.get_pair_source_info, the same function generate_ab_clips uses, so the two routes can't
  disagree.
Changed: root adhoc_quality investigation scratch files (adhoc_quality.py/.json, adhoc_report.*,
  adhoc_tapematch.log, build_adhoc_pdf.py) moved to tools/adhoc_quality/; dropped a stray empty
  tools/tapematch/observations.db?mode=ro artifact (accidental sqlite URI-as-filename).
i18n: de/fr/es/it/nl synced via DeepL for the new tapematch.abPlayer.* keys; manually corrected
  three mistranslations of "Position" (fr "Poste", es "Puesto", nl "Functie" — all read as
  employment position, not playback position) to Position/Posición/Positie.

[2026-07-11] — feat(backend): TODO-231 (part 1/2) — LISTENING §2 aligned A/B clip service
Added: backend/ab_clips.py — POST /api/ab_clip {date, lb_a, lb_b, t_sec, dur_sec 5..60} extracts
  two performance-time-aligned WAV clips (16-bit/44.1k/stereo) via ffmpeg from the pair's library
  FLAC folders (my_collection.disk_path; t located across the folder's track sequence via cached
  ffprobe durations, clips may span N adjacent tracks via concat demuxer). Per-source offset =
  t + trim_head_sec from tools/tapematch/observations.db sources. v1 eligibility: both sources
  speed_kind IN ('reference','aligned') — 409 not_eligible otherwise; 404 no-common-run/
  folder_missing (unmounted drive path echoed), 409 locked (obs db write-locked), 400 bad t/dur.
  Clips cached in data/ab_clips/ (gitignored), pruned to newest 40; GET /api/ab_clip/<name> serves.
Added: GET /api/tapematch/pairs rows now carry ab_eligible (live best-effort from observations.db,
  same pattern as human_judgment enrichment; null when db missing/locked).
Fixed (Fable review of agent output, pre-commit): trims for A and B are now taken from the latest
  run containing BOTH sources (get_pair_source_info) — per-source-latest-run selection could mix
  trims from two runs whose performance windows disagree, silently misaligning the pair; clip
  cache key now hashes the post-trim source offset (not raw performance time) so a rerun that
  changes a trim can't serve a stale cached clip.
Tests: 24 in tests/test_ab_clips.py (ffmpeg/ffprobe mocked; offset math, boundary spanning,
  eligibility, cache prune, enrichment, same-run selection). Real-audio smoke test: LB-5953/
  LB-6162 1995-07-08 Munich, 15.0 s clips ffprobe-verified, incl. track-boundary concat path.
Note: part 2/2 (A/B player widget in ScreenTapeMatch + dup-encodes GUI rider) follows.

[2026-07-11] — feat(backend+gui): TODO-230 — LISTENING §3 song-centric index (olof_songs spine)
Added: backend/song_index.py — normalize_song_title (NFKD/casefold/apostrophe-unify/punct-strip),
  song_canonical seeding (most-frequent raw spelling wins; curator rows sticky via
  ON CONFLICT ... WHERE source != 'curator'), song_performances wholesale recompute (empty-replace
  guarded per BUG-246 pattern), upsert_alias, get_songs/get_song_performances queries.
Added: backend/db.py — song_canonical (alias_norm PK, canonical, source auto|curator) +
  song_performances (event_id+position PK, song_norm/song_canonical/concert_date_iso/is_encore/
  take_status/event_type; idx on norm + date) — both USER-tier, never in master export.
Added: tools/compute_song_performances.py CLI (--dry-run); song_index appended as 4th
  feature-detected step of POST /api/derived/recompute (F1 chain).
Added: backend/app.py routes — GET /api/songs?q= (counts + date span + n_dates_with_recordings
  via show_picks), GET /api/songs/performances?song= (venue/city from olof_events; recordings
  {lb_number, pick_rank, abs_grade} via show_picks + latest quality scan; 404 unknown),
  POST /api/songs/alias (curator-gated 403; recompute-on-write).
Added: gui_next ScreenSongs.tsx at /songs (Library nav group) — debounced song search rail,
  performance table (date/venue/event-type pill/take status/encore, LB deep-link buttons with
  pick + grade), date vs best-first sort, curator canonical-rename affordance. i18n songs.* keys,
  5 locales via /gui-next-i18n.
Data: real-DB recompute — 61,707 performance rows, 1,298 songs, 3,994 events (88.1% of all
  olof_events incl. sessions/broadcasts). Verified live: "visions of johanna" → 227 performances
  (220 concerts, 201 dates with local recordings). 13 new tests (tests/test_song_index.py).
Note: canonicalisation table feeds TODO-225 (setlist fingerprinting).

[2026-07-11] — test(backend): un-rot tests/test_geocoder.py (13 failures from TODO-220/224 behavior changes)
Fixed: 6 assertions updated to the (full, city_only) tuple returns introduced by TODO-220
  (9ac938b0); 5 TestRunBatch fixtures gained a blank-field olof_events concert row so the
  TODO-224 (f044dcd2) concert-only eligibility filter passes without adding a competing
  structured source; 3 note assertions updated to the "tried: ..." cascade-log format.
  Tests only — backend/geocoder.py untouched. Suite: 52/52 pass (was 39/52).

[2026-07-11] — feat(backend+gui): TODO-215 (parts 2+3/3, closes it) — crawl run management + LB deep-links
Added: backend/app.py POST /api/tapematch/crawl/start — wraps tools/tapematch/crawl_start.sh
  (optional body min_entries/allow_missing → script flags; the script's pgrep guard stays the
  single-instance authority — 409 already_running when it refuses). POST /api/tapematch/crawl/stop
  wraps crawl_stop.sh (SIGINT, no-op-safe, always 200).
Added: gui_next ScreenTapeMatch.tsx crawl strip — Start/Stop buttons with pending states,
  409-aware error copy (tapematch.crawl.* keys, 5 locales via /gui-next-i18n).
Added: LB deep-links (sub-feature 3): LbLinkButton in matrix headers/cells + family chips
  navigates to /library?lb=<n>; ScreenLibrary consumes the param one-shot (selects the row,
  opens the DetailPanel, clears the param). DetailPanel gains a drag-resizable width
  (useResizableWidth in useResizableColumns.ts, persisted to localStorage) and a horizontally-
  scrollable tab strip so the deep-linked panel never clips.
Tests: 10 new endpoint tests in tests/test_tapematch_routes.py (judgment set/clear/400/404,
  crawl start success/409/400/500, stop success/500; subprocess fully mocked — no real crawl).
Note: TODO-215 closed — TapeMatch screen v2 complete. A/B player + dup-encodes GUI riders
  carry to the LISTENING §2 stream (WORK_PACKAGE_NEXT slot 3).

[2026-07-11] — fix(backend+gui): pipeline severity/state correctness on partial runs, renames and moves
Fixed: backend/app.py — on a partial pipeline run, severity was computed from only the step(s)
  requested this call (others "mute"): _sev_step now folds last-known verdicts from the validated
  folder-state cache, so a re-verify of an already-filed folder keeps "done" instead of being
  demoted, and a lone verify on an unidentified folder is not promoted.
Fixed: gui_next ScreenPipeline.tsx applyRename — a rename promoted rows to "In collection" unless
  the file step was warn; inverted to promote only when file step is ok (rename never files).
Fixed: gui_next ScreenPipeline.tsx file/move — the persisted folder queue kept the old source
  path after a move, re-hydrating as a false "Missing/blocked" on next reload; now swaps in the
  new path (mirrors applyRename).

[2026-07-11] — feat(backend+gui): TODO-215 (part 1/3) — curator match feedback on the TapeMatch matrix
Added: backend/app.py POST /api/tapematch/pairs/judgment — writes human_judgment
  (confirmed_same|confirmed_different|uncertain|lb_wrong, or null to clear) + human_notes
  straight into tools/tapematch/observations.db pairs (opened read-write, unlike the mode=ro
  helper used elsewhere; BEGIN IMMEDIATE + busy_timeout). Vocabulary is authoritative —
  tools/tapematch/regression.py reads confirmed_same/confirmed_different as calibration truth.
  Validation: 400 bad_judgment/missing_fields, 404 no_run/pair_not_found, 409 locked when a
  crawl holds the DB (mirrors the /api/tapematch/analysis 409 pattern).
Added: gui_next ScreenTapeMatch.tsx — matrix cells clickable; a JudgmentPanel below the matrix
  (not a popover — the matrix lives in overflow-x) lets the curator set/clear a judgment + notes;
  judged cells get a tone marker. Saves via the new endpoint + invalidates the pairs query.
Changed: backend/app.py GET /api/tapematch/pairs now enriches each pair with human_judgment/
  human_notes read LIVE (best-effort) from observations.db so edits show without a re-sync.
Fixed: backend/app.py — the enrichment SELECT initially crashed on observations.db pairs rows
  with NULL lb_a/lb_b (single-source rows): sorted((None, int)) raised TypeError, aborting
  enrichment for the whole date so every judgment silently fell back to null. Now filters
  lb_a/lb_b IS NOT NULL in SQL. (Caught pre-commit via end-to-end HTTP verification.)
Note: TODO-215 stays open — sub-features 2 (run start/stop management) and 3 (LB deep-links)
  not yet done. Locales de/fr/es/it/nl updated via /gui-next-i18n.

[2026-07-11] — feat(gui): TODO-226B — About-screen data-source credits (setlist.fm, bobdylan.com, bobserve link)
Changed: gui_next AboutDialog.tsx: TODO-226 Part B — added setlist.fm and bobdylan.com credit
  cards to the Credits tab (after the existing Olof Björner card) and a "bobserve.com · About
  Bob" entry to the About-tab Links list. Ground truth vs. ticket: the Olof/bobserve credit it
  asked to add was already shipped (commit 3b9ca946); the "existing setlist.fm/bobdylan.com
  credits" it referenced did not exist — this fills that real gap. Component is static-English
  constants (no locale keys) so /gui-next-i18n is a no-op. Types + build pass. TODO-226 stays
  open for Part A (BobTalk search + show-page surfacing).

[2026-07-11] — feat(backend+gui): olof_events geocoder source + authoritative concert filter (TODO-224 pts 1–2), geocoder skipped/stopping GUI (TODO-229)
Added: backend/geocoder.py: TODO-224 pt 1 — _get_olof_events_location_string() slotted into
  _STRUCTURED_SOURCES directly after bobdylan_shows: on an entries-date match builds
  "venue, city, region, country" from olof_events' split fields (blank parts dropped) + a
  city-only variant for the TODO-220 cascade; prefers event_type='concert' on multi-event
  dates (mirrors db.compare_olof_setlist tie-break). _table_exists() feature-detects
  olof_events so installs without the Olof scraper degrade to prior behavior.
Changed: backend/geocoder.py: TODO-224 pt 2 — _is_concert_location() now returns
  (eligible, skip_note): an olof_events date match is AUTHORITATIVE (concert → eligible even
  past the keyword blacklist; any other event_type → skipped_not_concert with
  "olof_events: non-concert event_type=<type>" in note); no olof match → original TODO-221
  heuristic unchanged. Pt 3 (gazetteer seeding from olof_events) deliberately deferred to
  TODO-223 with the rest of the gazetteer work.
Added: tests/test_geocoder.py: 12 new tests (olof lookup hit/blank-drop/tie-break/absent-table,
  authoritative eligibility incl. conflict-with-bobdylan_shows case, 2 run_batch end-to-end).
  All 12 pass; 13 pre-existing failures from stale TODO-220/221-era fixtures confirmed present
  before this change (stash-verified) → BUG opened this session.
Changed: gui_next ScreenScraper.tsx: TODO-229 — GeocoderStatus gains skipped/stop_requested,
  GeoStats gains skipped; "Skipped" row in the geocoder Cache Stats grid; StripCard gains an
  optional badge override → geocoder card shows "stopping" while running && stop_requested.
  New scraper.geocoder.* keys in en.json; DeepL pass synced de/fr/es/it/nl (3,409 chars).
  Verified: backend restarted (live /api/geocode/stats serves skipped=31), tsc node+renderer
  0 errors, production build clean.
Added: instructions/WORK_PACKAGE_NEXT.md: queue for post-7/12 windows — LISTENING §3 (song
  index on the olof_songs spine) + §2 (A/B) + TODO-215 next window; TODO-213 standing preempt;
  N+2 slot unassigned (pipeline Phase 7, its original occupant, verified already shipped 07-09).

[2026-07-11] — feat(backend): geocoder stop support (TODO-219), concert-only eligibility filter (TODO-221), cascading Nominatim fallback (TODO-220)
Added: backend/geocoder.py: TODO-219 — stop() sets _progress["stop_requested"] under _lock;
  run_batch() checks it at the top of every location iteration and the 429 backoff sleep is
  sliced (1 s chunks, _StopSignal unwinds into the existing finally). get_progress() exposes
  stop_requested for the GUI badge.
Added: backend/app.py: POST /api/geocode/stop (mirrors /api/bobdylan/stop) — fixes the GUI Stop
  button's silent 404 (ScreenScraper.tsx already posted this path).
Added: backend/geocoder.py: TODO-221 — _is_concert_location(): non-venue keyword guard
  (compilation/outtakes/interview/rehearsal/soundcheck/demos/various) + requires one entry with
  a single clean date matching bobdylan_shows or setlistfm_shows (dylan_performances deliberately
  excluded — it date-matches interviews). Ineligible locations cached as
  source='skipped_not_concert' (lat/lon NULL, never retried, no Nominatim call), counted in new
  _progress["skipped"]; /api/geocode/stats excludes them from failed and reports skipped.
Changed: backend/geocoder.py: TODO-220 — cascading fallback: all structured-source full strings
  (priority order) → venue-stripped city-only variants (source suffix '-city', confidence capped
  at medium) → raw entries.location last; every attempted query recorded in note
  ("tried: <tag>:<query> | …") on success and failure; 1.1 s sleep between every Nominatim call
  incl. fallbacks. Shared _save_geocode_result() extracted for the UPSERT.
Fixed: data: re-ran the 48 source='failed' rows from the 2026-07-10 batch (retry_failed=true,
  limit=48, live-verified on 5174 post-restart): 17 geocoded (9 bobdylan_shows-city,
  1 setlistfm_shows-city, 7 full-string), 31 skipped_not_concert, 0 errors — failed count now 0,
  coverage 69 → 86 locations. Known wart: a non-venue location on a documented show date (e.g.
  "A Hotel Room, Denver" during a Lincoln NE run) passes eligibility and pins to the show's
  city; place_manual() is the escape hatch, gazetteer work (TODO-222/223) will revisit.

[2026-07-11] — feat(backend+scraper): quality-score family corroboration + dup-encode surfacing (TODO-210), crawl hot-loop guard (TODO-227)
Added: backend/tapematch_sync.py: TODO-210a conf bump — _load_latest_abs_scores (per-lb newest
  scored scan, abs_score/abs_grade feature-detected via PRAGMA, degrades to no-op pre-Ranker) +
  _has_quality_match (same scan_id, |Δabs_score| ≤ 0.5, same grade letter); families matching
  get a one-time min(1.0, conf + 0.05) bump in _sync_one_date, logged. Corroboration only —
  investigation showed raw score equality is >99.8% noise for surfacing new families.
Added: backend/tapematch_sync.py: TODO-210b duplicate_encode_candidates() — read-only pairs with
  byte-identical quality_recording_metrics.metric_json within one scan_id, grouped by
  entries.date_str (not via recording_families — the interesting leads aren't in families yet);
  never auto-merges. CLI: python -m backend.tapematch_sync --dup-encodes.
Added: backend/app.py: GET /api/tapematch/dup_encodes → {"candidates": [...]}. Live-verified on
  5174 post-restart: 15 pairs / 13 metric-identical groups incl. investigation's LB-3136/7538 +
  LB-3147/7523 (same_family=False) — GUI surfacing rides TODO-215 (TapeMatch screen v2).
Added: tools/tapematch/run_crawl.sh: TODO-227 failure guard — non-continue rc sleeps 30 s; 3
  consecutive failures on the same date append it to data/tapematch/crawl_skip.txt and move on;
  10 consecutive failures overall abort (systemic). Also fixed latent stale-$rc bug (rc never
  reset on success — would have cascaded false failures once the guard existed). Replaced via
  mv (new inode); the live crawl keeps its old copy until next restart.
Changed: tools/tapematch/tapematch_session.py: next_run() honors crawl_skip.txt (ISO date per
  line, # comments; prints skipped count) and writes the attempted date to
  crawl_last_attempt.txt before run_date so the shell guard knows what failed.
Changed: tests/test_tapematch_sync.py + tests/test_tapematch_routes.py: 26 new tests (bump
  apply/degrade/clamp, dup-encode grouping, route). Suite 607 passed / 5 skipped.

[2026-07-10] — feat(backend+gui): Olof P5 — surfacing: endpoints, tour-name fallback, setlist compare, GUI panel (FABLE_OLOF_FILES §5–§6; closes TODO-162 + TODO-290; Olof spec complete)
Added: backend/db.py: get_olof_date/get_olof_event/get_olof_chronicle_year/get_olof_status
  readers (all degrade to empty — olof_* stays local-only, NOT in MASTER_TABLES; export tier
  deliberately deferred as a redistribution-rights question); normalize_title_for_match (reuses
  checksum_utils apostrophe fold) + conservative containment matcher; parse_entry_setlist_titles
  (entries.setlist free-text tracklists, 11,796 rows); compare_olof_setlist order-independent
  greedy matcher returning matches/missing/match_pct + recording info for duration sanity.
Added: backend/app.py: GET /api/olof/date/<date>, /api/olof/event/<id>, /api/olof/chronicle/<year>,
  /api/olof/status; POST /api/olof/compare ({date_str, titles[] | lb_number}).
Changed: backend/db.py get_performances(): tour-name fallback chain setlistfm → olof_events
  (TODO-290) — setdefault so setlistfm wins, concert rows preferred; dated shows with a tour
  name 3,783 → 4,540 (+757; e.g. 1974-01-03 "Tour '74").
Added: gui_next DetailPanel.tsx: Olof tab on both library lenses — setlist (encore pills, cover
  credits, annotations, take status), NET/year concert #s, recording info, notes, BobTalk quote,
  chronicle entries, circulation provenance, per-copy setlist comparison (match %, missing
  titles, expected minutes). Gated on /api/olof/status events>0 (react-query staleTime Infinity).
Changed: gui_next AboutDialog.tsx: Olof Björner / bobserve.com acknowledgement card (TODO-226
  part B; part A remainder — BobTalk full-text search — stays open on TODO-226).
Changed: locales: 15 new library.olof.* + tabOlof keys; de/fr/es/it/nl via /gui-next-i18n
  (DeepL, 4,857 chars). /gui-check PASS (node+renderer tsc 0 errors, build clean).
Changed: instructions/FABLE_OLOF_FILES.md → instructions/complete/ (all P1–P5 shipped);
  instructions/README.md row removed. Verified live on 5174 post-restart (status counts,
  1990-05-29 panel data, compare normalization smoke test).

[2026-07-10] — feat(scraper): Olof P4 — Yearly Chronicles parser → olof_chronicle + olof_new_tapes (FABLE_OLOF_FILES §6; TODO-162 P4)
Added: backend/db.py: olof_chronicle + olof_new_tapes tables + date indexes (spec §4).
Added: backend/olof_chronicle_parser.py: chronicle corpus parser — heading-based section
  location tolerant of ~50 years of Word export drift, calendar diary entries (date-heading
  shapes: 'D Month', 'Month D', day lists/ranges, Early/Mid/Late), 'New tapes & bootlegs'
  subsections with ISO show-date from title, XE/PAGEREF field-junk stripping, per-year
  delete+reinsert idempotency, olof_pages bookkeeping, CLI mirroring olof_parser.
  Full-mirror parse: 1,244 olof_chronicle rows (43 years), 79 olof_new_tapes (17 years),
  253 pages ok / 2 partial / 0 error; 11 years are PDF-only stubs on Olof's site.
  DSN data untouched (4,533 events / 61,708 songs); rerun idempotent; junk-free (SQL check).
Changed: backend/olof_parser.py: extracted _split_city_region_country, corpus/year params on
  _ensure_page_row — shared with the chronicle parser, DSN behavior unchanged.
Note: 2022+ appendix setlist path (synthetic year*1000+seq event IDs) implemented but dormant —
  bobserve.com publishes 2013+ chronicles as PDF only (2016 excepted), so 0 synthetic events;
  structurally validated on 2002 A.htm incl. spec §7 malformed headers. TODO-228 opened for
  PDF fetch + extraction. Riders NOT parsed (deferred per spec §8): tour stats, uncirculated.
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof row updated — P4 done, next P5.

[2026-07-10] — feat(scraper): Olof P3 — DSN song/take parser → olof_songs (FABLE_OLOF_FILES §6; TODO-162 P3)
Added: backend/db.py: olof_songs table (event_id+position PK, title, cover credits, is_encore,
  take_number/status, annotations, released_on) + idx_olof_songs_title (spec §4).
Added: backend/olof_parser.py: song/take rows threaded through the P2 pipeline — combined
  ("N. Title (credits)") and split-cell session layouts, take statuses (incl. bare-status
  source quirk), encore separator, annotation/release position-range resolution with
  lineup-line guard, duplicate-position renumbering (Olof numbering slips), delete+reinsert
  idempotent upsert; coverage report extended (songs_emitted, % concerts with songs).
  Full-mirror parse: 61,708 song rows; 97.8% of concerts / 95.1% of sessions with ≥1 row.
  Gate: DSN01225 17/17 takes with statuses; DSN11050 19/19 titles match setlistfm bd4a956,
  encore + credits + annotation ranges correct; P2 event coverage byte-identical (4,533
  events), page ok/partial split unchanged. Known soft spot: "released in <country> on …"
  phrasing lands in annotations, not released_on (documented in module).
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof row updated — P3 done, next P4.

[2026-07-10] — feat(scraper): Olof scraper P1+P2 — bobserve.com mirror + DSN event parser (FABLE_OLOF_FILES §6; TODO-162 P1–P2) + tapematch crawl merged-folder crash fix
Added: backend/olof_fetcher.py: verbatim byte mirror of Olof Björner's Still On The Road +
  Yearly Chronicles (browser UA for Cloudflare, ≥2 s throttle, resume-safe skip/backfill,
  --corpus/--limit/--refresh/--dry-run). Full mirror fetched: 471 pages (214 DSN + 257
  chronicle), 324 MB, 0 errors → data/olof/pages/.
Added: backend/olof_parser.py: DSN event parser — windows-1252 Word-HTML, per-paragraph line
  joining, <a name=DSNnnnnn> segmentation; extracts date/venue/city/region/country, NET +
  year concert #, recording kind/mins, notes, BobTalk, releases, raw_text; event_type
  heuristic; coverage report. Full DSN corpus: 4,533 events (99.7% anchor→event, 95% ISO
  date; concert 3,879 / session 205 / broadcast 91 / interview 63 / rehearsal 6 / other 293).
  5-date archive spot-check passed (incl. 1966-05-17 Manchester vs "Royal Albert Hall" label).
Added: backend/db.py: olof_pages + olof_events tables + date/tour indexes (spec §4).
Fixed: tools/tapematch/tapematch_session.py: copy_folders() crashed on merged folders (two LB
  ids sharing one directory, e.g. "… (LB-05034 + LB-07279)") — FileExistsError crash-looped
  the detached crawl ~3 h on 2000-03-12; now dedupes by source path and skips already-copied
  folders. Crawl verified resumed (2000-03-13…16 processed).
Changed: instructions/WORK_PACKAGE_2026-07-09.md: Olof P1+P2 row added to Phase 2 timeline.

[2026-07-10] — docs: ONBOARDING P4 — README rewrite, retires PyQt flow docs (spec §6; closes TODO-218; ONBOARDING spec complete)
Changed: README.md: full rewrite — quickstart = Releases installer (AppImage / windows-Setup.exe,
  verified against v1.5.2 assets) + first-run wizard; data-model table (master release vs
  sitedata release vs monthly flat file, curator-only scraping note); dev setup (.venv,
  run_backend.py, gui_next npm run dev, dist:linux/win) + PROJECT.md pointer. Kept the
  flat-file + checksum format reference sections. Dropped: python main.py install, manual
  Setup-tab flat-file first-import, PyQt tab feature list, Map/WebEngine + PyInstaller sections.
Changed: instructions/FABLE_ONBOARDING_SYNC.md → instructions/complete/ (all P1–P4 shipped);
  instructions/README.md row swapped for new FABLE_OLOF_FILES.md entry.

[2026-07-10] — feat(gui): ONBOARDING P3 — first-run wizard + Home setup checklist + Setup/Scraper copy (spec §5–§6; closes TODO-217)
Added: gui_next/src/renderer/src/components/OnboardingWizard.tsx: 4-step first-run modal
  (1 master github_check/install SSE — required to proceed; 2 sitedata core/files checkboxes
  → sitedata github_install SSE; 3 navigation-only Mounts/Pipeline links; 4 summary +
  auto-fired POST /api/derived/recompute per SPEC_INTEGRATION_NOTES F1, per-step status list).
  Skip always available; controlled component — ScreenHome owns show/hide.
Added: gui_next/src/renderer/src/screens/ScreenHome.tsx: auto-opens wizard once per launch
  when onboarding/status entries_count==0 (sessionStorage dismiss flag set on Skip/Finish);
  setup-checklist card while complete==false — one row per unmet item (master, sitedata core,
  mounts, collection scan), each reopening the wizard at the right step or navigating.
Changed: gui_next/src/renderer/src/screens/ScreenSetup.tsx: flat-file card reworded to
  "Monthly update" framing (spec §6 demotion — no first-run role, copy only).
Changed: gui_next/src/renderer/src/screens/ScreenScraper.tsx: curator-only banner note
  (end users get scraped data via master + site-data releases).
Changed: gui_next/src/renderer/src/locales/*.json: ~45 new keys (onboarding.*,
  home.setupChecklist.*, scraper.curatorNote, setup.flatFile.*) — de/fr/es/it/nl via DeepL
  (10,294 chars); the 3 residual "gaps" are identical-in-target words (Version/Open), benign.
Verified: tsc node+web 0 errors (ScreenScraper baseline errors no longer present), vite build
  PASS.

[2026-07-10] — feat(backend): ONBOARDING P2 — sitedata github_check/github_install + onboarding/status (spec §3–§4; commit a9759209; closes TODO-216)
Added: backend/app.py: GET /api/sitedata/github_check — latest sitedata-* release, per-part
  (core/files) zip discovery by _core_/_files_ substring (collision-suffix tolerant, per P1's
  _2 core asset) paired with .manifest.json sidecars; parts missing a sidecar are omitted.
Added: backend/app.py: POST /api/sitedata/github_install (SSE, same event shapes as master
  install) — body {parts:[core|files]}, default core; downloads to data/imports/, verifies
  SHA256 against manifest BEFORE extraction (mismatch deletes zip + errors, site dir
  untouched), extracts into data/site/ via shared _restore_sitedata_zip (clean overwrite),
  writes .sitedata_<part>_manifest.json marker for cheap status reads.
Added: backend/app.py: GET /api/onboarding/status — {entries_count, master_version,
  sitedata_core_present, sitedata_files_count, mounts_configured, collection_count, complete};
  complete = entries ∧ master_version ∧ ≥1 mount. Live-verified: 63 ms (<100 ms spec target),
  github_check pairs both parts of the real sitedata-2026-07-10 release.
Changed: backend/app.py: /api/package/restore site-extraction path deduped into
  _restore_sitedata_zip; embedded-manifest types sitedata_core/sitedata_files now accepted.
Added: tests/test_sitedata_packaging.py: 7 P2 tests (mocked GitHub releases API + SSE stream
  parsing: check pairing, sha mismatch aborts pre-extraction, success + marker, invalid part,
  restore manifest types, onboarding status empty/populated) — 15/15 pass.

[2026-07-10] — feat(backend): ONBOARDING P1 — site-data split packaging + first sitedata GitHub release (spec §3; commit 55501726)
Added: backend/app.py: _package_site_data(part) — core (everything but files/) / files (files/
  only) / None (legacy whole-tree) zips of data/site/ with .manifest.json sidecars (type,
  created_at, file_count, total_bytes, sha256 — master manifest convention; new types
  sitedata_core/sitedata_files). POST /api/package/scrape_data grew ?part=core|files, no-arg
  callers (ScreenSetup, gui/setup_tab.py) keep the old whole-tree behavior. New
  POST /api/sitedata/github_release (curator, SSE) mirrors master_github_release: builds both
  zips + manifests, creates sitedata-<date>[.N] release, uploads 4 assets with progress.
Added: tests/test_sitedata_packaging.py — 8 tests (part selection, manifest sha256/counts,
  invalid part, curator gate); full suite 581 pass.
Changed: first sitedata release published to kuddukan42/losslessbob: tag sitedata-2026-07-10,
  core 24.9 MB (16,829 files) + files 187 MB + 2 manifests. Core asset carries a _2 filename
  suffix (collision counter vs a same-day smoke-test zip) — P2 discovery must match assets by
  _core_/_files_ pattern + manifest pairing, not exact filename. Verified: core zip sha256
  matches manifest, zero site/files/ entries in core.
Changed: ledger: TODO-216 (P2 endpoints, High — next session), TODO-217 (P3 wizard, Medium),
  TODO-218 (P4 README, Low) opened per the spec's allocate-at-first-session rule. PROJECT.md:
  show_picks schema corrected (concert_date is raw M/D/YY, + concert_date_iso column/index),
  picks date/tonight routes + Site-Data Packaging routes documented.

[2026-07-10] — feat(backend+gui): LISTENING §9 "tonight card" — concert_date_iso + picks date endpoints + Home card (spec step 6 complete)
Added: concert_ranker/picks.py: _parse_concert_date_iso() — M/D/YY→ISO reconciliation of
  show_picks.concert_date (two-digit year pivot 30, any 'xx' component → NULL); populated on
  every recompute. Live DB: 14,618/15,204 rows ISO-dated (586 NULL = 'xx' unknown-date entries,
  by design). Satisfies TODO-212's deferred GET /api/picks?date= item (TODO-212 stays open for
  the Recording-lens badges + combined curated view).
Added: backend/db.py: show_picks.concert_date_iso column (idempotent PRAGMA-guarded migration)
  + index. backend/app.py: GET /api/picks?date=YYYY-MM-DD exact-date filter and
  GET /api/picks/tonight — month-day match across all years (?mmdd=MM-DD override), returns
  ranked candidates. tests/test_picks_tonight.py (parser + endpoint coverage; suite 573 pass).
Added: gui_next ScreenHome.tsx "Tonight in Dylan history" card (right column, above Tips) —
  one random candidate from /api/picks/tonight (long-form date, rating pill, LB number,
  location, truncated description) + shuffle button (non-repeating; hidden when single
  candidate). Card fully hidden on fetch failure/empty. No deep-links (→ TODO-215). i18n:
  home.tonight.* en + DeepL de/fr/es/it/nl (3,639 chars). gui-check: node+web tsc 0 errors,
  production build clean.
Note: BUG-246 detour committed earlier in this slot (73266f6b, see 07-10 entry below); bug
  stays open for the db_path-writer audit (tapematch_sync, parse_lineage, taper_attribution,
  scrapers). Backend commit 70392d14, frontend 09e57b11. WORK_PACKAGE Phase 2 slot 1 done.

[2026-07-10] — fix(backend): BUG-246 — guard show_picks wholesale write against DB-path splits (73266f6b)
Fixed: live show_picks table found wiped (0 rows) at session open; root cause: a writer taking
  an explicit db_path could target a different DB than the queue-backed connection, letting the
  wholesale DELETE phase land without the INSERT phase. Guards added: empty-replace guard
  (refuse to replace non-empty table with 0 rows), path-mismatch direct write, queue re-init
  warning. 2 regression tests. Data restored via tools.compute_show_picks: 15,204 picks /
  4,031 dates. BUG-246 stays open for the same-class audit of other db_path-taking writers
  (tapematch_sync, parse_lineage, taper_attribution, scrapers).

[2026-07-10] — feat(backend+gui): LISTENING §1 pairs sync + TapeMatch screen v1 (closes TODO-170; work-package stretch slot)
Added: backend/tapematch_sync.py: sync_tapematch_pairs() — slim per-pair mirror of
  observations.db pairs into new USER-tier tapematch_pairs table (db.py schema + USER_TABLES;
  PK (concert_date, lb_a<lb_b), latest-complete-run-per-date via _pick_best_run, wholesale
  DELETE+INSERT per date so rows never blend two runs). similarity_pct() banded monotone blend
  calibrated 2026-07-10 against verdict distributions from 10,369 real pairs (same-family
  renders 85–100 from max(corr,emb) terms, different-family 0–40 from emb (corr fallback),
  both-NULL different-family → NULL = "n/c"). CLI _main() now syncs families then pairs.
  Live sync: 9,037 pairs / 1,094 dates, 0 errors; bands verified (diff mean 8.7, same mean 92).
Added: backend/app.py: POST /api/tapematch/sync chains families→pairs (existing keys unchanged;
  pairs_synced/pair_dates merged in). New GET routes: /api/tapematch/pairs?date= (per-date
  matrix rows), /api/tapematch/analysis?date= (best run's analysis.md text + parsed verdict;
  409 when observations.db locked), /api/tapematch/crawl/status (pgrep + runs-dir counts +
  log tail, read-only), /api/tapematch/dates (left-rail summary: n_lbs/n_pairs/has_analysis/
  needs_review/location). Fixed during review: dates location lookup joined ISO concert_date
  against US-format entries.date_str (matched 0/1,094 rows) — now resolves via the date's LB
  numbers; fixture date_str made US-format so a regression fails the test. 35 tapematch tests
  (tests/test_tapematch_sync.py + new tests/test_tapematch_routes.py); full suite 560 pass.
Added: gui_next ScreenTapeMatch.tsx (route /tapematch, Library nav group, existing tapematch
  icon) — tj-approved sketch built as-is: date rail (all/conflicts/no-analysis views, date+
  location text filter, analysis ✓ / needs-review ⚠ marks), per-date similarity-% matrix
  (color-mix heatmap tint on theme tokens, raw corr/emb/fp + verdict in cell tooltip, n/c for
  never-compared, diagonal —), family chips (F1/F2… by lowest LB from /api/tapematch/families
  fam_id groups), collapsible lazy-fetched analysis.md <pre> viewer, crawl status strip
  (30 s poll). Read-only v1 — no run controls or pair corrections (→ TODO-215). i18n:
  tapematch.* namespace + nav key, en + DeepL de/fr/es/it/nl (5,131 chars; residual gaps are
  benign identical-form strings). gui-check: node+web tsc 0 errors, production build clean.
Changed: ledger: TODO-170 closed (v1 shipped), TODO-215 opened (v2 remainder: pair
  corrections into observations.db, run start/stop, LB deep-links pending an in-app
  deep-link mechanism). WORK_PACKAGE_2026-07-09 stretch slot done.

[2026-07-09] — feat(backend+gui): TAPER phase 2 shipped — curator confirm/reject API, Library taper pill + filters, DetailPanel Taper tab (closes TODO-173)
Added: backend/taper_attribution.py: phase 2 curator API functions — confirm()/reject() write
  sticky MASTER taper_confirmations rows (upsert on lb_number PK, F2) and apply the decision to
  taper_attributions immediately, recompute-equivalent (confirm reuses _confirmed_row's shape via
  extraction from _apply_confirmations; reject uses _apply_rejects' pair-match rule so an
  unrelated attribution is never deleted while the suppression still lands). get_attribution_for_lb(),
  list_attributions() (confidence/taper/conflict filters), _resolve_taper() (explicit taper or
  sourced from existing row; confirm validates against _TAPER_UNIVERSE).
Added: backend/app.py: GET /api/tapers/attributions/<lb> (200 with attribution:null when absent),
  GET /api/tapers/attributions?confidence=&taper=&conflict=1 (spec §5 list), and curator-gated
  POST .../confirm + .../reject (400 on unresolvable taper). 11 new tests in
  tests/test_taper_attribution.py incl. _AppClient route tests (535 pass).
Added: backend/db.py: get_performances() F4 payload extension — optional taperConfirmed
  (confidence='confirmed' only, per spec §7 "no pill below confirmed") and taperReview
  (propagated/inferred/conflict) via _load_taper_attributions() single pre-fetched map,
  feature-detected for pre-attribution DBs.
Added: gui_next ScreenLibrary.tsx: confirmed-taper pill (collapsed + family-member rows) and two
  filter views ("Confirmed taper", "Taper: needs review" — the spec's review queue) with counts,
  mirroring the RANKING filter pattern. Heuristic recording-lens taper_name badge untouched (TODO-212).
Added: gui_next DetailPanel.tsx: Taper tab (TaperZone) — tier/conflict pills, taper Fact, shared
  EvidenceList, lazy fetch; confirm/reject buttons gated on curatorMode (TODO-160 convention),
  response pushed into the React Query cache. i18n: library.taper.* / views/tab keys, en + DeepL
  de/fr/es/it/nl (4,039 chars). gui-check: node/renderer tsc 0 errors, build clean.
Added: backend/db.py: get_performances() payload extension (F4 pattern — flat fields, no N+1):
  each recording gains optional pickRank (show_picks), absGrade (latest quality scan,
  PRAGMA-feature-detected), curated (list names). New delete_curated_list(),
  get_show_pick_for_lb(), 3 loader helpers.
Added: backend/app.py: GET/POST /api/curated_lists + DELETE /api/curated_lists/<name>
  (POST/DELETE curator-gated) — TODO-181 remainder; GET /api/picks/for/<lb> (evidence for
  DetailPanel, 204 pre-recompute). tests/test_library_picks_api.py (6 tests).
Added: gui_next EvidenceList.tsx — the one shared {kind, detail, points} evidence renderer
  (F3), reused by taper/listening specs later. DetailPanel: Picks tab (rank/score Facts +
  EvidenceList, lazy fetch), star/grade/curated badges in identity block + family MemberRow.
  ScreenLibrary: badges on performance-lens rows; 4 new Views filters (recommended,
  superseded, carbonbit's, 10haaf's); fixed latent bug where DetailPanel read the un-merged
  recording-lens row (mergedRowsByLb). i18n: 13 new keys, all 5 locales DeepL'd (3,992 chars).
Changed: ledger: TODO-181 + TODO-186 closed (phase 4 closes both per spec §7); TODO-212 opened
  (flat recording-lens badges + 'any curated pick' view + /api/picks?date= — the deferred
  remainder). FABLE_UNIFIED_RANKING.md retired to instructions/complete/ (all 4 phases done).
Changed: tools/tapematch: TODO-201 batch-1+2 FLIPs (83, tj-approved) applied via new
  make_regression_set_v3.py → regression_set_v3.json (positives 1578→1495, negatives
  1387→1470, total conserved; flip list embedded as v3_flips; v1/v2 untouched). Rescoring
  deferred — calibration frozen this window. FN_LABEL_REVIEW.md + CALIBRATION_PROGRESS.md
  updated. TODO-201 stays open (136 duration-only pairs + 8 UNSURE).
Verified: 34 backend tests pass (525 full suite per implementing agent); tsc node + web clean
  (0 errors, better than 14-error baseline); production build clean. tj visual eyeball:
  badges render, but derived DATA needs curation ("lots of obviously wrong badges but more
  are accurate") → TODO-213 (High) opened — collect wrong-badge examples, trace via the Picks
  tab's evidence trail, then weight-tune picks.py §4 terms. Pipeline itself signed off.
Fixed: backend/db.py: extract_taper_and_source() rule-12 short-handle heuristic captured
  quality/broadcast descriptor phrases ("mono", "poor sound", "dylan radio special hilversum3")
  as taper_name — stopword list didn't cover them (BUG-245). Tightened stopwords; added "poor
  sound"/"mono" to _NOT_TAPER. Added is_known_taper()/_TAPER_UNIVERSE (shared with
  taper_attribution.py, which now imports rather than recomputes it) and a taper_known field
  on every /api/search row, so the recording-lens grid pill and the DetailPanel Taper tab check
  the same curated universe instead of disagreeing. (TODO-212 is unrelated/still open — that's
  pickRank/absGrade/curated payload parity, not this taper pill.)
Changed: gui_next ScreenLibrary.tsx: taper pill now gates on row.taperKnown (backend
  is_known_taper()) in addition to the existing NON_TAPER_LABELS dedup, so unvalidated
  free-text guesses never render as an authoritative-looking pill.

[2026-07-09] — feat(backend): TAPER phase 1 + RANKING phase 2 — taper attribution engine, show picks, chained recompute endpoint
Added: backend/taper_attribution.py: taper attribution engine (FABLE_TAPER_ATTRIBUTION phase 1) —
  harvests evidence from entry_lineage / _KNOWN_TAPER_ALIASES / recording_families and writes
  per-LB designations with confidence tiers (confirmed/propagated/inferred), evidence_json audit
  trail, and conflict flagging. Live run: 7,817 attributions (2,643 confirmed / 5,174 propagated /
  168 conflicts flagged for curator review). tools/attribute_tapers.py CLI wrapper (run()/main,
  --dry-run). tests/test_taper_attribution.py.
Added: concert_ranker/picks.py: per-date "best of show" pick scoring (FABLE_UNIFIED_RANKING
  phase 2, §3/§4 model) over entries.rating, curated_lists, entry_lineage,
  quality_recording_scores, and taper_attributions (F5: attribution runs first so the taper
  reputation term sees fresh rows). tools/compute_show_picks.py CLI wrapper. Dry run against the
  real DB: 15,204 picks over 4,031 dates (median score 85.7). tests/test_show_picks.py.
Added: backend/db.py: new tables — taper_confirmations (MASTER, sticky curator confirm/reject
  decisions per SPEC_INTEGRATION_NOTES F2; curator API lands in TAPER phase 2),
  taper_attributions + show_picks (USER, derived, recomputed wholesale, never exported).
  MASTER_TABLES/USER_TABLES updated accordingly.
Added: backend/app.py: POST /api/derived/recompute — SSE-streamed chained recompute
  (parse_lineage → attribute_tapers → compute_show_picks) per SPEC_INTEGRATION_NOTES F1,
  replacing the ranking spec's standalone /api/picks/recompute; steps skip gracefully when a
  later phase's module isn't importable. Manual trigger only, not curator-gated (USER-tier
  output only).
Changed: tools/tapematch/FN_LABEL_REVIEW.md: TODO-201 batches 1+2 — 128 of 264 census-flagged
  pairs reviewed (83 FLIP / 37 KEEP / 8 UNSURE). Pending tj sign-off, flips would shrink the
  corr<0.05 FN population 830 → ~747. Remaining 136 duration-only pairs need a
  partial/incomplete-set judgment method (future chip); TODO-201 stays open.

[2026-07-09] — feat(tapematch): library crawl launched + analysis auto-triage; backlog consolidation
Added: tools/tapematch/crawl_start.sh / crawl_stop.sh / crawl_status.sh: detached single-instance
  wrapper set around run_crawl.sh, log at data/tapematch/crawl.log. Full-library crawl launched
  2026-07-09 over the 2,232 remaining eligible dates (954 of 3,306 ≥2-recording dates done at launch).
Added: tools/tapematch/triage_analysis.py: classifies the missing-analysis.md backlog into
  AUTO / ESCALATE / SKIP(incomplete); auto-writes gen_analysis-template analyses (honest
  "auto-triage" attribution line) only for complete all-distinct runs whose diagnostics are limited
  to [DISTINCT SOURCE]/[INCOMPLETE] and whose commentary raises no in-set pair notes. First pass:
  395 pending → 11 auto-written, 329 escalated to /tapematch-batch, 55 skipped incomplete.
  backend.tapematch_sync ran after: 892 dates, 2,902 families, 3,743 recordings linked, 0 errors.
Changed: instructions/: CC_TAPEMATCH_ADDON, CC_TAPEMATCH_FIXES, TAPEMATCH_PLAN, CC_WEB_GUI_PLAN
  retired to complete/ (efforts concluded / TODO-050..066 all shipped); README.md index updated.
  WORK_PACKAGE_2026-07-09.md added — agreed 7/09–7/12 window plan (tapematch calibration FROZEN,
  spec-pack order per SPEC_INTEGRATION_NOTES §2, TapeMatch screen as stretch goal).
Changed: ledger: TODO-182 closed (superseded by FABLE_UNIFIED_RANKING §5), TODO-203 closed
  (Tier C rejected twice; frozen), TODO-204 and TODO-209 annotated as deferred past the window.
Changed: tools/tapematch/CLAUDE.md: crawl wrapper + triage-before-batch conventions documented.
  .gitignore: observations.db-shm/-wal + tools/tapematch/tmp/ (live-crawl artifacts).

[2026-07-09] — feat: TODO-146 + TODO-171 + TODO-083 — flac.exe bundling, TapeMatch DB Editor, export column picker
Added: tools/flac.exe + tools/libFLAC.dll: bundled Windows FLAC 1.5.0 (Win64) binaries.
  backend/sox_utils.py: _find_flac()/get_flac() probe bundled tools/flac.exe (PyInstaller
  frozen + dev tree) before PATH/WSL, mirroring checksum_utils._find_shntool(). Wired into
  /api/spectrogram/check so flac shows green on fresh Windows installs with zero user setup.
  losslessbob.spec + losslessbob_backend.spec updated to bundle both files (TODO-146).
Added: backend/paths.py: TAPEMATCH_DB_PATH → tools/tapematch/observations.db. backend/app.py:
  _DBEDIT_READONLY_DBS map generalizes _dbedit_db_path()/_dbedit_is_batchverify() (was
  batchverify-only) to also resolve "tapematch", read-only, reused by dbedit_query()'s ?db=
  param too. gui_next/src/renderer/src/screens/ScreenDbEditor.tsx: DB picker widened from a
  2-way to a 3-way losslessbob/batch_verify/tapematch toggle (TODO-171).
Added: backend/app.py: collection_export_html() now accepts ?cols= (validated against a new
  _EXPORT_COLUMN_DEFS registry: lb/status/date/location/folder/notes plus disk_path/
  confirmed_at/source_type/lb_category/rating), always including lb. The exported HTML's
  thead/row-rendering/CSV-export/search/sort JS was converted from hardcoded 6-column markup
  to a data-driven COLS array injected via a new __COLS_JSON__ placeholder.
  gui_next/src/renderer/src/screens/ScreenCollection.tsx: new ColumnPickerModal (checkboxes
  for the 5 extra fields) + "Columns…" button next to Export HTML (TODO-083).
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: synced via DeepL for the
  new collection.columnPicker.* keys plus a pre-existing backlog of stale strings per locale
  unrelated to this session (nav labels, table headers) that DeepL picked up on this run.

[2026-07-09] — feat(gui): TODO-288 + TODO-152 + TODO-161 + TODO-148 + TODO-163 + TODO-164 — Pipeline/Scraper/Library polish batch
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: applyFile's success branch now
  updates the row's folderPath/id to the post-move result.dest (previously only rename did this),
  so the detail panel's Open button no longer resolves the pre-collect path (TODO-288). Same
  branch now clears the row's selected flag on transition to bucket 'done', so bulk-filing no
  longer leaves finished rows checked (TODO-152).
Changed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: the row action column always
  renders a fixed-size Button now — enabled Apply/File/Done pill when actionable, a disabled
  placeholder otherwise — instead of leaving blank space until the row becomes actionable
  (TODO-161).
Added: gui_next/src/renderer/src/lib/scraperLogStore.ts: module-level zustand store (not
  localStorage-persisted) holding the Scraper screen's per-tab live log lines.
  gui_next/src/renderer/src/screens/ScreenScraper.tsx: switched from local useState to this
  store so the log buffer survives the screen unmounting when the user navigates to another tab
  and back (TODO-148).
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: AssetStripZone's
  attachments pill now opens an inline popover listing each cached attachment's name (clickable,
  opens via window.api.openPath against data_dir from /api/db/settings), plus a "View all in
  Attachments" link — reuses ScreenLibrary's existing attachments-cached query key so no extra
  network request (TODO-163).
Added: gui_next/src/renderer/src/lib/tokens.ts: ThemeOptions.highContrast — applyTheme()
  brightens --lbb-fg/-fg2/-fg3 on dark themes when enabled (no-op in light mode).
  gui_next/src/renderer/src/screens/ScreenThemes.tsx: toggle added to the Advanced card,
  disabled outside dark mode (TODO-164).
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: synced via DeepL for the two
  new keys (library.assets.viewAll, themes.advanced.highContrast) plus a pre-existing backlog of
  ~90-124 stale strings per locale unrelated to this session (nav labels, table headers) that
  DeepL picked up on this run.

[2026-07-09] — feat(gui): TODO-169 + TODO-192 + TODO-168 + TODO-180 — Home/Library/AppShell UI cleanup batch
Changed: gui_next/src/renderer/src/screens/ScreenHome.tsx: removed the Hero ingest card and the
  now-dead STEP_STRIPS constant; reflowed "At a glance"/"Jump to" into a 2-column grid to fill
  the freed width (TODO-169).
Added: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: taper_name badge inline in the
  Location column of the recording-lens table, gated by a NON_TAPER_LABELS blocklist (master,
  sbd, bootleg, soundboard, audience, ald, mixed, incomplete, unknown, n/a) so generic
  source-type words parsed into taper_name by the free-text parser don't show as fake taper
  handles. No backend change — /api/search already returns taper_name (TODO-192).
Added: backend/app.py: GET /api/credentials/wtrf returns the stored WTRF username only (never
  the password). gui_next/src/renderer/src/components/AppShell.tsx: sidebar identity now shows
  the real username/initials instead of the hardcoded "rolling.thunder"/"RW", falling back to a
  new appShell.noWtrfAccount blank-state string when no WTRF credential is configured. Removed
  the dead appShell.user/userSub locale keys, which were never referenced (TODO-168).
Added: backend/filer.py: _compute_collection_size()/start_collection_size_scan_async()/
  get_collection_size_stats() — sums on-disk bytes across all my_collection folders, cached in
  meta (collection_size_bytes/_folders/_computed_at) and refreshed via a background thread when
  >24h stale (COLLECTION_SIZE_STALE_HOURS) rather than walking ~16k folders synchronously per
  request. Wired into GET /api/home/stats as collection_size {bytes, human, folders,
  computed_at, computing}; surfaced in the AppShell footer stats bar (TODO-180).
Changed: PROJECT.md: documented the collection_size field on GET /api/home/stats.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: DeepL sync for all new/removed
  keys above (library.columns.taper, appShell.noWtrfAccount, appShell.statusBar.collectionSize/
  computing; removed home.* hero-card keys and appShell.user/userSub).

[2026-07-09] — feat(backend): TODO-167 — geocoder pulls structured location from bobdylan_shows/setlistfm_shows
Changed: backend/geocoder.py: extracted _entries_iso_dates() shared helper; added
  _get_bobdylan_shows_location_string() and _get_setlistfm_location_string(), matching the
  existing dylan_performances lookup pattern. run_batch() now tries three structured sources
  in priority order via _STRUCTURED_SOURCES — bobdylan_shows (most standardized "City, ST"
  strings), then setlistfm_shows, then dylan_performances as a last resort — before falling
  back to the raw entries.location text. location_geocoded.source records whichever table
  matched ('bobdylan_shows' / 'setlistfm_shows' / 'performances') instead of always
  'nominatim'. No route or GUI changes needed — /api/geocode/run already calls run_batch()
  directly.
Changed: PROJECT.md: documented the new source priority order and source column enum.
Added: tests/test_geocoder.py: 13 new tests covering both new lookup functions plus run_batch
  priority ordering (bobdylan_shows > setlistfm_shows > dylan_performances).

[2026-07-09] — chore(backend): TODO-165 — deprecate old acoustic fingerprinting feature
Changed: backend/app.py: removed all /api/fingerprint/* routes (build/status/stop/queue,
  lb_numbers, stats, identify, duplicates/scan/stop, collection_by_date, identify_folder/
  status/stop, purge), the init_fp_db() startup call, background worker state/threads, the
  "fingerprints" key from GET /api/collection/prefetch, and the fingerprint_cache stat from
  GET /api/purge/stats.
Changed: gui_next ScreenCollection.tsx: removed the Fingerprinted column, its filter/sort key,
  and the "Fingerprint Folder" context-menu action (separate integration from the dedicated
  screen, found during scoping — confirmed with user before removing).
Changed: gui_next ScreenSetup.tsx + AboutDialog.tsx: removed the purge-fingerprint-cache option
  and the librosa dependency row.
Changed: requirements.txt + PROJECT.md: dropped librosa/numba/soxr — introduced solely for
  fingerprinting and unused elsewhere (Concert Ranker uses numpy/scipy directly, not these
  three); numpy/scipy kept.
Removed: backend/fingerprint.py (Wang/Shazam landmark acoustic fingerprinting engine),
  gui_next/.../screens/ScreenFingerprint.tsx + its nav entry/icon/route (App.tsx, AppShell.tsx,
  Icon.tsx), backend/paths.py FP_DB_PATH, and the orphaned fingerprint.* / collection.detail.
  fingerprinted* / collection.toast.fingerprint* / setup.purges.fingerprintCache* i18n keys
  across all 6 locales. Legacy gui/ (PyQt6, frozen) and cli.py still reference the deleted
  routes/module — left intentionally broken per user decision (frozen GUI, low-traffic CLI
  path) rather than extending changes into frozen code.

[2026-07-09] — feat(gui): TODO-205 Phase 7 (async job model) + TODO-211 (severity extraction) — pipeline structural tier COMPLETE
Changed: gui_next ScreenPipeline.tsx: TODO-205 Phase 7 GUI migration (design §8) — runSteps no
  longer posts one synchronous /api/pipeline/run per folder. It now enqueues a batch onto a
  client-side queue; a single drainJobQueue driver POSTs /api/pipeline/run/start once, then
  polls /api/pipeline/run/status every 400ms (PIPELINE_POLL_MS), merging each folder's verdict
  as it lands (device-grouped, out of enqueue order). Batches serialise client-side to respect
  the backend's single-job busy guard; concurrent runSteps calls stack and drain sequentially.
  stopRun now POSTs /api/pipeline/run/cancel, clears the client queue, and stops the poll loop.
  Removed the now-dead per-folder updateRow/AbortController path; added rowsRef for stale-free
  id→path resolution in the async driver. The targeted single-step follow-ups (pending-fetch
  retry, detail refresh, blocked-recheck, rename file-refresh) deliberately stay on sync /run.
Added: gui_next folderQueueStore.ts: TODO-205 Phase 7 — zustand persist middleware
  (localStorage 'lbb-pipeline-queue'), so the folder work queue survives an app restart.
  Verdicts stay server-side (P7 cache); only the path list is persisted client-side.
Added: gui_next ScreenPipeline.tsx + backend/app.py: TODO-205 Phase 7 warm-start. New route
  POST /api/pipeline/state returns last-known cached verdicts (fingerprint-validated, design
  R3) for a set of folders, with severity freshly computed. A mount effect hydrates the
  persisted queue's rows so buckets paint immediately after restart — before any re-run, and
  even with autorun off. Rows already running are left untouched; the file step is appearance-
  only (P8) and re-resolved live on the next run.
Changed: backend/app.py: TODO-211 — extracted the pipeline severity computation out of the
  _pipeline_process_folder closure into a module-level pure function compute_pipeline_severity
  (verify/lookup/lbdir/rename + file_status/error_code + lb_number → severity). The closure and
  the new warm-start route both call it, and tests/test_p8_blocked_severity.py now drives the
  REAL function instead of a verbatim mirror — mirror/real drift is now impossible. Behaviour
  unchanged; verified by the existing 4 P8 cases + full pipeline suite (23 passed).

[2026-07-09] — feat(gui): TODO-205 Phase 5 GUI half + Phase 6 P8 — lbdir prefetch retry effect, blocked-collect as live view (structural tier)
Added: gui_next ScreenPipeline.tsx: TODO-205 Phase 5 GUI half (design §5/P3) — pending_fetch
  retry effect. The backend parks a row on a background LBDIR prefetch with lbdir status
  "mute" + pending_fetch:true; the existing auto-complete effect resumes a stale row only
  once (ref-guarded), so a row still inflight at that resume used to park until a manual
  re-run. New effect polls POST /api/pipeline/run {steps:['lbdir']} every 5s (LBDIR_PENDING_
  POLL_MS), capped at 6 attempts (~30s, LBDIR_PENDING_MAX_ATTEMPTS); once pending_fetch
  clears it drops the attempt count and the autocompleteStarted guard so rename/file resume;
  on timeout the row is left a plain mute (no new StepStatus string). pending_fetch added to
  the StepResult type. Implemented by sonnet agent, orchestrated + verified by opus.
Changed: backend/app.py: TODO-205 Phase 6 P8 (design §6) — "blocked as a live view" severity
  split. A blocked file step now escalates to attn ONLY when error_code in {no_date,
  no_route} (structural, need human config); transient codes (mount_offline, dest_exists,
  db_error, and any unknown code — whitelist semantics) fall through to the ready/done/attn
  logic and land in "done", so already-verified work no longer gets forced into "needs" for
  a pointless full re-run.
Added: gui_next ScreenPipeline.tsx: TODO-205 Phase 6 P8 GUI — serverRowToPipeline re-buckets
  a done-severity row with a transient file block (status 'bad') to "shelf" not "In
  collection"; auto re-resolve (re-run ['lookup','file'], ref-guarded once per detail-panel
  open) so a shelved row self-clears when its mount returns; bulk "Retry N blocked collects"
  toolbar button (isTransientBlock predicate) re-running the file step for all transient-
  block shelf rows. Design §6 optional auto-retry-on-mount-reachability NOT built — see
  TODO-205 remaining notes.
Added: tests/test_p8_blocked_severity.py: 4 tests for the P8 severity split (transient →
  done, no_date/no_route → attn, unknown code → done, bad step elsewhere → attn). NB tests a
  mirror of the severity block, not the real closure — see TODO-211 for the extraction fix.
Changed: gui_next locales/*.json: new pipeline.retryBlockedCollects key translated to
  de/fr/es/it/nl via /gui-next-i18n (the run also filled the pending backlog from concurrent
  library-screen work; 3,555 DeepL chars).

[2026-07-08] — feat(backend): TODO-205 Phases 1–5(backend) — pipeline cache schema, async job model, state persistence, hash consultation, lbdir prefetch (structural tier)
Added: backend/app.py: TODO-205 Phase 5 backend half (design §5/P3) — background LBDIR
  prefetch: module-level _LBDIR_PREFETCH_INFLIGHT set + lock (dedupe by LB number, many
  folders can resolve to one LB) + lazy ThreadPoolExecutor(max_workers=2); submitted the
  moment lookup resolves an LB whose lbdir attachment is uncached; worker mirrors the
  inline retrieval incl. canonical-alias fallback, failures swallowed (prefetch is
  advisory). While the LB is inflight the lbdir step returns status "mute" + label
  "Fetching LBDIR…" + pending_fetch:true instead of scraping synchronously; when NOT
  inflight the original synchronous scrape fallback runs unchanged. pending_fetch rides a
  marker field (GUI STATUS_TO_STATE union is closed); pending verdicts are never persisted
  to pipeline_folder_state and never served cached; severity exempts a pending_fetch lbdir
  mute from the "downstream not run" attn escalation. GUI half (pending_fetch retry effect
  in ScreenPipeline.tsx) deliberately deferred — see design §9 Phase 5 row for the handoff.
  Implemented by opus agent; verified: full suite 477 passed, /backend-restart, cold 1.1s →
  warm 95ms cached serve, no spurious pending_fetch on cached-attachment flows.
Added: backend/checksum_utils.py: TODO-205 Phase 4 (design §2a/§3) — _cached_file_hashes():
  verify_folder and verify_folder_lbdir consult pipeline_file_hash per file ((size,mtime)
  R1 validation at consumption); on a miss md5+sha256 are computed in ONE read (sha256 rides
  along to feed filing's tree digest); ffp cached incidentally (header-only read anyway);
  shntool never cached. Cache key is the raw posix rel-path (not the apostrophe-normalised
  matching name) so verify and filing share one keyspace. ANY cache-layer failure degrades
  silently to plain compute — verdicts can never change because the cache is unavailable.
Changed: backend/filer.py: filing's SOURCE-side tree digest now derives from cached sha256s
  (_source_tree_digest → db.derive_tree_digest, hash_tree fallback on any error); the
  DESTINATION is always freshly hashed — a poisoned cache can only cause a false mismatch
  (abort), never a false match, so hash-verify-before-remove holds unconditionally.
Added: backend/filer.py: stale_verify guard in start_file_job (design §3a hard rule,
  enforced for ALL filing, auto + manual): if a pipeline_folder_state row exists and the
  recomputed folder fingerprint differs, filing is refused with error_code "stale_verify"
  ("re-run the pipeline"); folders with no pipeline state proceed as before.
Added: tests/test_hash_cache_verify.py: 9 tests — cold/warm verify identical + md5&sha256
  populated, edited file detected as mismatch (not stale cached Pass), poisoned-stale row
  ignored, cache-failure degradation, source digest == hash_tree cold/warm + fallback,
  stale_verify blocks / matching fingerprint proceeds / no state proceeds. Full suite 477
  passed. Implemented by opus (code) + sonnet (tests) agents; verified live: cold 2×150MB
  verify 0.454s → touch one file → 0.233s (only the touched file re-hashed); edit-then-file
  refused with stale_verify.
Added: backend/app.py: TODO-205 Phase 3 (design §2b/§3/§4d) — _pipeline_process_folder now
  persists all step verdicts + post-run folder fingerprint to pipeline_folder_state after
  every run, and serves the two expensive hash steps (verify, lbdir) from cache with
  cached:true when the recomputed fingerprint matches (the R3 sweep). Three refinements over
  the design (recorded in its §9 as-built notes): lookup/rename/file ALWAYS run fresh
  (cheap + DB-dependent — pins/aliases/status invisible to the fs fingerprint; file is a P8
  live view); cached lbdir verdicts carry the lb_number they verified and are rejected after
  a re-pin (and never re-stamp set_lbdir_verified); persistence uses the post-run fingerprint
  since the lbdir step copies the manifest into the folder mid-run. New optional force:bool
  on sync /api/pipeline/run and async /run/start bypasses the cache. Implemented by an opus
  agent from the pinned spec; verified live: cached serve 15ms vs 220ms fresh (200MB
  fixture), force recomputes, touch → fingerprint miss → fresh → re-cached, mixed
  cached-verify/fresh-lookup row + severity correct, persisted JSON stores no cached flag.
Added: backend/app.py: TODO-205 Phase 2 (design §4) — async multi-folder pipeline job:
  POST /api/pipeline/run/start {folders, steps?, workers?:1-4}, GET /api/pipeline/run/status,
  POST /api/pipeline/run/cancel. Module-level _PIPELINE_JOB state +
  _pipeline_run_async_coordinator: folders grouped by os.stat st_dev (one drain thread per
  device, serial within a device — same-spindle seek-thrash guard), global
  Semaphore(workers) cap, cooperative per-folder cancel, per-folder try/except so one bad
  folder never kills the job. Busy contract mirrors filer.start_file_job
  ({ok:false, error_code:"busy"}). Sync /api/pipeline/run unchanged; GUI still uses it
  (migration is Phase 7). Implemented by a sonnet agent from the design spec; verified live:
  busy guard mid-run, cancel left in-flight folder to finish (verify "Pass") and skipped the
  23 queued, 400 bad_input on unknown steps, sync route byte-identical behaviour.
Changed: PROJECT.md: routes table — documented the three new async pipeline endpoints.
Added: backend/db.py: `pipeline_file_hash` (per-file md5/ffp/sha256 cache; (size, mtime) are
  validation columns per design rule R1) and `pipeline_folder_state` (per-folder step verdicts
  keyed by a per-file stat-sweep fingerprint, rule R2) tables per
  instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md §2; both registered in USER_TABLES so master
  exports drop them (they hold local absolute paths). Helpers: upsert_file_hash / get_file_hash /
  get_folder_hashes, folder_fingerprint, get/put_folder_state (fingerprint-scoped merge — a new
  fingerprint discards all prior verdicts), derive_tree_digest (reproduces filer.hash_tree
  byte-for-byte from cached sha256s with fresh-read write-through on any miss),
  prune_pipeline_cache (missing-folder sweep + 180-day age cap — design §10 Q1 decided). All
  writes route through db_queue (§4e). Inert: nothing consults the tables until Phases 3/4.
Added: tests/test_pipeline_cache.py: 10 tests — fingerprint stability/sensitivity (in-place edit,
  rename), hash-cache round-trip + replace-on-stat-change, folder-state merge/discard, derived
  tree digest == hash_tree on a fixture with a lone-surrogate filename (cold, warm, and
  poisoned-stale cache), USER_TABLES registration, prune. Discovered en route: SQLite TEXT cannot
  bind lone-surrogate paths — guarded via db._cacheable(); such files are never cached, always
  hashed fresh (speed cost only, never correctness).
Changed: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md: Phase 1 marked shipped with as-built
  notes; §10 Q1 (eviction) decided, Q1b surrogate-path constraint recorded.
Changed: TODO.md: TODO-205 retitled/rescoped to implementation tracking (design shipped
  2026-07-07; Phase 1 done, Phases 2–7 remaining). Stays Open.
Changed: PROJECT.md: schema section — documented the two new USER tables.

[2026-07-08] — feat/fix: orchestrated parallel-agent session — 8 items closed (BUG-233/236, TODO-149/174/175/176/207/208) + ledger cleanup
Fixed: backend/wtrf_scraper.py: BUG-233 — Content-Disposition parsing extracted into
  _filename_from_content_disposition(): plain filename= preferred; RFC 5987 filename*= decoded
  (strip charset''lang'', percent-decode); attach-id/LB fallback kept. 11 new tests in
  tests/test_wtrf_scraper.py. Note: the core regex fix was already committed (c3257c02) but the
  ledger was never updated — this session added the testable seam + tests and closed the entry.
Fixed: gui_next renderer: BUG-236 / TODO-206 — all 14 baseline TS errors fixed (two were real
  functional bugs: ScreenCollection addSource sent a wrong payload shape, ScreenPipeline
  shift-click range-select read shiftKey off ChangeEvent — moved to onClick). Pill title /
  IconButton disabled / Input type props added properly. typecheck script added to
  gui_next/package.json; gui-next-typecheck hook wired into .pre-commit-config.yaml alongside
  ruff. tsc -b + production build clean (zero-error baseline).
Changed: backend/setlistfm.py: TODO-149 — run_update() true incremental update: stops paginating
  when force=False and a full page yields zero newly-inserted rows (INSERT OR IGNORE rowcount);
  force=True keeps the full walk; stop_reason/pages_fetched logged. 3 stubbed-API tests.
Changed: backend/app.py: TODO-175 — /api/dbedit rows lb_filter accepts multiple comma/space-
  separated LB numbers via parameterized lb_number IN (...); invalid tokens fall back to
  unfiltered (prior semantics); GUI passes the raw string through so it works end-to-end.
  7 new tests (tests/test_dbedit_lb_filter.py).
Changed: gui_next ScreenBootlegs.tsx: TODO-176 — Year filter popover switched to a 5-column CSS
  grid ('All years' full-width top row); no new i18n keys.
Fixed: backend/scraper.py + backend/site_crawler.py: TODO-174 guardrails — (a) scrape_entry now
  marks already-on-disk files downloaded=1 (fixes permanent flag desync when site_crawler
  fetched the file first); (b) site_crawler skips network fetch for /files/ URLs already on
  disk while keeping inventory + entry_files bookkeeping. Investigation verdict: keep both
  mechanisms (different triggers/granularity), consolidation rejected. 2 new tests.
Added: tools/gui_next_locale_parity.py: TODO-207 — dotted-path key diff of en.json vs
  de/fr/es/it/nl (exit 0/1/2). Current status: full parity, 1381 keys in all 6 locales.
Added: .claude/hooks/session_end_check.sh: TODO-208 — SessionEnd hook (registered in
  .claude/settings.json) flags unrecorded changes to .claude/state/session_end_stale.flag;
  session_brief.sh surfaces the warning at next SessionStart and clears it. .claude/state/
  gitignored. Flag round-trip verified.
Added: tools/ledger_dedup.py: TODO-209 progress — duplicate-header-ID audit (report-only
  default; --apply experimental/unused). Finds 21 duplicated BUG ids + the TODO set, proposes
  keep/renumber per entry, lists all cross-references needing manual attribution. TODO-209
  stays open for the renumbering pass.
Changed: BUGS.md housekeeping — 11 entries that were marked Fixed but never archived moved to
  BUGS_DONE.md verbatim (BUG-193, 195, 202, 203, 204, 205, 208, 213, 214, 217, 223); BUGS.md
  is down to 9 genuinely open bugs. BUG-193's duplicate id (an unrelated importer BUG-193
  already in the archive) noted inline pending the TODO-209 dedup pass.
Tests: full suite 458 passed / 5 skipped; gui_next typecheck + production build clean.

[2026-07-08] — docs: close stale TODO-292 (TapeMatch recall recovery) — work completed 2026-07-02, ledger never updated
Changed: TODO.md/TODO_DONE.md: TODO-292 (CC_TAPEMATCH_FIXES Tasks 2-7) closed via
  `tools/ledger.py todo-close` — text was frozen at a mid-day 2026-07-02 snapshot ("Tasks 2-7
  remaining, curator-lineage/hf_ceiling NOT wired into live cli.py") but later 2026-07-02
  CHANGELOG entries show all of it landed same-day: Task 2 rerun_cat3.py executed (0/6 Cat-3
  flipped), Tasks 3.2/4.1/4.2 wired into live cli.py + validated, Tasks 5-7 implemented and
  calibrated (triplet fingerprint rejected/disabled after live calibration showed false merges).
  Final: recall 41.6%/precision 98.6%/fp=9 vs 38.3%/98.2% baseline; further gains scoped to
  CC_TAPEMATCH_ADDON.md (TODO-199).
Note: found a pre-existing ledger integrity issue while closing this — TODO_DONE.md now has two
  entries both numbered TODO-198 (this one and an unrelated "Quality page" TODO closed
  2026-07-01). Root cause: the TapeMatch entry's number was hand-set rather than assigned via
  `ledger.py next-id todo`, reusing an already-closed id (`_collect_ids` scans both files
  correctly, so this couldn't happen through the tool itself). No other file references
  TODO-198, so a renumber is low-risk whenever addressed. Flagging only, not fixed this session.
Added: TODO-209 — full header-ID audit found 17 duplicated TODO ids and 22 duplicated BUG ids
  across the open/done file pairs (mostly legacy debt predating ledger.py, added 2026-07-07 per
  TODO-205). Scoped as a batch renumbering job, not manual edits.

[2026-07-07] — fix: full-codebase bug hunt — 7 bugs found, confirmed via repro, fixed (BUG-238..244)
Fixed: backend/sharing.py: BUG-238 — _reaper_loop had no exception guard; one corrupt
  expires_at or persist OSError permanently killed share expiry (expired shares kept serving
  over the public tunnel). Loop body now guarded + logs; invalid-expiry shares reaped;
  _persist()'s mkdir moved inside its best-effort try.
Fixed: backend/sharing.py: BUG-239 — list_shares() popped expired shares without
  revoke_share(), skipping _persist() and the stop-tunnel-on-last-share logic (cloudflared
  ran forever with zero shares). Now revokes properly outside the lock.
Fixed: backend/scheduler.py: BUG-240 — scheduled integrity scans compared SQLite
  CURRENT_TIMESTAMP (UTC) against local datetime.now(); on CDT every scan fired 5 h late.
  Now parsed as UTC-aware and compared in UTC.
Fixed: gui_next/src/main/index.ts: BUG-241 — killProcessTree() only tree-killed on Windows;
  Linux/macOS app quit orphaned the backend's ffmpeg/sox/shntool children. Backend now
  spawned detached on POSIX and killed via process-group kill(-pid) with fallback;
  killPortProcess routes through killProcessTree.
Fixed: backend/importer.py: BUG-242 — flat-file import silently dropped malformed rows
  (except: pass). Now counts skips, logs first 5 with line numbers + a summary WARNING;
  except narrowed to (ValueError, sqlite3.Error).
Fixed: backend/db_queue.py: BUG-243 — async write failures left no trace despite the
  docstring's claim of DEBUG logging. Writer thread now logs them at WARNING with traceback.
Fixed: backend/db.py + backend/app.py: BUG-244 — re-pinning a folder to a different LB
  accumulated links (set_folder_link went additive in the composite-PK migration) and the
  old pin won lookups via pinned_lbs[0]. New replace_folder_link() (atomic DELETE+INSERT in
  one write-queue transaction) now backs PUT /api/folder_link.
Changed: tests/test_db_writes.py: stale test_replace_existing (failed on main) split into
  test_set_is_additive (auto-link semantics) + test_replace_existing (re-pin semantics).
Note: repros kept in .debug/ (repro_s1_reaper.py, repro_s2_scan_tz.py + _fixed,
  repro_s3_killtree.mjs, repro_s4_list_shares.py, repro_s5_s6.py). Full pytest suite
  435 passed / 0 failed; gui-check node types + build PASS (renderer baseline still 14
  errors, but now spread over 6 files, not just ScreenScraper.tsx — BUGS.md BUG-236 note
  is stale). Informational, not fixed: /api/spectrogram/png serves any absolute *.png path
  (single-user app, basic-auth web GUI) — flagged only.

[2026-07-07] — feat/chore: pipeline dev-loop quick wins (spec D1/D2/D3/P5) — auto-collect toggle, ledger CLI, advisory hooks, change-log dedup
Added: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: "Auto-collect" toggle (spec P5) —
  third header toggle, default off, session-only; auto-files rows meeting the fileableRows guard
  (verify/lookup/lbdir/rename all ok), serialized via the existing filing lock, skipConfirm path.
  State ~line 1323, ref ~1378, effect ~1820, toggle UI ~2080.
Added: gui_next/src/renderer/src/locales/{en,de,fr,es,it,nl}.json: pipeline.autoCollect +
  pipeline.autoCollectHint strings (DeepL-synced for the new toggle).
Added: tools/ledger.py (spec D2): stdlib CLI for BUG/TODO ledger operations (next-id,
  bug-open/close, todo-open/close, --dry-run) — atomic raw-text surgery preserving irregular
  separators byte-exactly; replaces hand-edits of BUGS.md/TODO.md across all four ledger files.
Added: .claude/hooks/py_compile_check.sh (spec D3): PostToolUse hook on Edit|Write of .py files —
  runs py_compile, exit-2 feedback on syntax error.
Added: .claude/hooks/i18n_reminder.sh (spec D3): PostToolUse hook on gui_next en.json edits —
  reminds to sync locale files.
Added: .claude/hooks/changelog_check.sh (spec D3): Stop hook — warns (never blocks) if source
  changed this session but CHANGELOG.md's head entry isn't dated today.
Changed: .claude/settings.json: registered the three new hooks alongside the existing
  schema-deploy/session-brief/access-guard hooks.
Changed: PROJECT.md (spec D1): `## Change Log` table frozen as of 2026-07-07 (historical rows
  kept, notice added at ~line 1619) — CHANGELOG.md is now the sole narrative change log.
Changed: .claude/commands/session-close.md: rewired to route all BUGS/TODO moves through
  tools/ledger.py; PROJECT.md step no longer adds Change Log rows.
Changed: .claude/CLAUDE.md: Bookkeeping + Verification bullets trimmed to match the ledger.py
  workflow and the frozen Change Log table.
Note: structural pipeline items P1/P2/P3/P7/P8 from
  instructions/complete/FABLE_PIPELINE_DEVLOOP_IDEATION.md deliberately deferred pending a
  combined design doc (see TODO-205); the ideation doc was later moved to instructions/complete/
  once its remaining open item (D6) was captured as TODO-207.
Added: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md (TODO-205, design only — no code
  changes): combined design for the structural pipeline tier — P7 (persist pipeline row
  state, resume across restart) + P1 (shared per-file hash cache) + P2 (async multi-folder
  job model), with P3 (LBDIR prefetch) and P8 (blocked-as-live-view bucketing) layered on
  the same cache/state tables; phased 7-step implementation plan. TODO-205 remains OPEN
  (design done, implementation not started). Reviewed and corrected against sources: (1)
  spec correction carried forward — `useFolderQueueStore` (gui_next/src/renderer/src/lib/
  folderQueueStore.ts) has no zustand `persist` middleware, so the folder queue does NOT
  survive a GUI restart today (the ideation doc's §65 assumption was wrong; this design's
  P7 GUI migration adds `persist`, mirroring `useSettingsStore`'s `'lbb-settings'` key); (2)
  documented the exact reproduction requirements for deriving `filer.hash_tree`'s digest
  from the new cache — `rel_path.encode("utf-8", "surrogatepass")` (surrogatepass is
  load-bearing for lone-surrogate filenames), raw 32-byte `file.digest()` output (not hex)
  fed into the tree hash, and `root.rglob("*")` scope covering every file under root (not
  just audio) — verified byte-for-byte against filer.py:322-340; (3) fixed an incorrect
  citation pointing the P3 "auto-complete" GUI-effect predicate at the wrong `useEffect`
  (was citing the unrelated auto-rename effect at ScreenPipeline.tsx:1661-1682; corrected
  to the actual resume effect at ScreenPipeline.tsx:1549-1560, predicate
  `lookup.status === 'ok' && lbdir.status === 'mute'`); (4) corrected a db.py line
  citation for the `location_geocoded` ALTER-TABLE additive-column precedent (was pointing
  at the table's `CREATE TABLE` line 280; the actual precedent is db.py:1629-1632).
Fixed: .claude/CLAUDE.md: Code Rules SQLite bullet corrected — the repo's actual idempotency
  convention is `CREATE TABLE IF NOT EXISTS` + `PRAGMA table_info` column-existence checks
  before `ALTER TABLE` (db.py:1572-1636), not the previously-stated `ALTER TABLE` + `try/except`.
Added: TODO-206 — gui_next: fix 14 baseline renderer typecheck errors (IconButton `disabled`
  prop, `shiftKey`-on-ChangeEvent in ScreenPipeline.tsx), then wire typecheck into pre-commit
  alongside the existing ruff-only Python gate.
Investigated: backend/checksum_utils.py `verify_folder` — confirmed `.st5` checksums ARE
  effectively verified (not a bug): they're merged into the `shntool` expected slot
  (checksum_utils.py:568-575) and compared against a freshly computed shntool hash for `.shn`
  audio files (:640-643); `st5_status` stays hardcoded `'na'` only because the pass/fail
  surfaces under `shntool_status` instead.
Changed: instructions/FABLE_PIPELINE_DEVLOOP_IDEATION.md retired to instructions/complete/
  (its last open item, D6, captured as TODO-207); added instructions/README.md as an
  active/complete spec index; added a session-close rule to auto-move finished specs into
  instructions/complete/ and update the index; opened TODO-207 (gui_next locale key-parity
  check script, spec D6 remnant).

[2026-07-05] — docs: CLAUDE.md optimization — targeted context reads, skill delegation
Changed: .claude/CLAUDE.md: rewrote for token efficiency — replaced mandatory full reads of
  PROJECT.md/BUGS.md/TODO.md (~3,300 lines/session) with grep-first targeted reads; moved
  BUG/TODO/CHANGELOG entry templates out (now in /session-close); verification + backend-restart
  rules now delegate to /gui-check and /backend-restart skills; added .venv/bin/python3 PATH
  rule; merged Known Pitfalls into Debugging. 108 → 76 lines, no rules dropped.
Changed: .claude/commands/session-close.md: now self-contained source of truth for BUG-<NNN>/
  TODO-<NNN> entry formats (templates inlined, CLAUDE.md pointer removed).
Added: CHANGELOG_ARCHIVE.md: 2026-05 entries (393, ~3,800 lines) rotated out of CHANGELOG.md;
  CHANGELOG.md now keeps a rolling ~2-month window (policy noted in CLAUDE.md Bookkeeping).
Added: gui/CLAUDE.md: legacy-GUI rules (frozen status, QThread-only backend calls, /i18n-update);
  QThread rule moved here from root CLAUDE.md.
Added: tools/tapematch/CLAUDE.md: tapematch conventions (WORKFLOW.md/CALIBRATION_PROGRESS.md
  first, no concurrent live sessions, runs in data/tapematch/runs/, batch rules).
Changed: PROJECT.md: new "## Contents" grep index after the intro; Change Log row added.

[2026-07-05] — test(tapematch): TODO-202 densification probe concluded — 12× REJECTED, 5× Rule D kept
Changed: tools/tapematch/TIER_B_FULLSET_REPORT.md: new "Densification probe" section — full
  12×60s re-embed (embed_cache_12x/, 1942+523 sources) + emb_score_pairs + v1/v2 sweeps;
  gate (flips > 25 at abs fp ≤9/≤6) met only at the both_tol 0.725 plateau edge (26 flips,
  net +1 TP, −3 shipped recoveries regress, one gain 0.015 above bar) — one step from the
  0.700 FP cliff the 5× calibration refused. Kept t_emb 0.75 on the 5× cache; sparse-excerpt
  TP-tail hypothesis falsified as a broad effect. Sweep logs: tools/tapematch/logs/
  fullset_eval_12x_{v1,v2}.log; 12× artifacts retained for TODO-204.
Fixed: tools/tapematch/emb_fullset_eval.py: BUG-237 — acceptance check compared the sweep's
  deliberately pre-Rule-D baseline against post-ship `score --cached` semantics
  (_passthrough_with_rule_d union), a guaranteed 25-TP false MISMATCH; reference now strips
  rule_d (identity re-proven: tp=659/916/9/1381 v1, 662/916/6/1381 v2) and prints the
  shipped confusion + derived ship bar alongside. Docstrings document the replacement framing.
Changed: TODO.md/TODO_DONE.md: TODO-202 → Done (moved); TODO-204 unblocked (sequencing note
  updated); handoff block item 2 marked done. BUGS_DONE.md: BUG-237 added.

[2026-07-04] — chore(docs): skill/command audit — fixed stale paths and rule violations
Changed: .claude/skills/analyze-runs/SKILL.md: repurposed as read-only roll-up of existing
  analysis.md files; old version pointed at nonexistent tools/tapematch/runs/ and used the
  abandoned claude -p subagent-writer approach (superseded by /tapematch-batch).
Changed: .claude/skills/verify/SKILL.md: rewritten around the real tooling
  (tools/browser_driver.mjs + tools/debug_screens.json, /api/status health check); old
  one-liner referenced Electron+Xvfb which the driver explicitly does not use. Marked as
  the explicit user-invoked exception to the no-GUI-screenshots rule.
Changed: .claude/commands/tapematch-batch.md: merged complete-sets-only filter (same-line
  "DB entries | Found on disk" parse, === CLUSTERS === check) and default batch size 25 → 5,
  per established workflow feedback; backlog report now splits eligible vs skipped-incomplete.
Changed: .claude/commands/find-bugs.md: added repo conventions (venv python, backend restart
  before verify, BUGS_DONE/CHANGELOG bookkeeping, encoding pitfalls, known-bug cross-check,
  optional scope argument).
Changed: .claude/commands/i18n-update.md: fixed bare `python` → .venv/bin/python3; DeepL key
  now read from env (settings.local.json) instead of prompting; scoped to legacy PyQt6 GUI.
Changed: .claude/commands/gui-next-i18n.md: added description frontmatter.
Added: .claude/commands/session-close.md: end-of-session bookkeeping skill (CHANGELOG entry,
  BUGS/TODO moves with cross-file next-free numbering, PROJECT.md change-log row, consistency
  check).
Added: .claude/commands/backend-restart.md: full kill+relaunch of run_backend.py with uptime/status
  verification; documents that /api/admin/restart does NOT reload code under run_backend.py (the
  callback only recycles werkzeug in-process — modules stay imported).
Added: .claude/commands/gui-check.md: sanctioned non-visual GUI verification — tsc --noEmit on
  tsconfig.node.json + tsconfig.web.json, then electron-vite build; 14-error renderer baseline
  noted (BUG-236).
Added: BUGS.md: BUG-236 (Open) — 14 pre-existing TS2322 errors in ScreenScraper.tsx, found while
  validating gui-check's typecheck commands.

[2026-07-04] — feat(tapematch): TODO-200 live emb integration + TODO-202 densification probe + dolphinsmile taper fix
Added: tools/tapematch/emb_live.py: live sessions now populate pairs.emb_score/emb_score_global
  (subprocess into .venv-nmfp for cache misses, shared emb_score_pairs.score_pair scoring,
  UPDATE keyed by run_id; any failure leaves NULL → Rule D abstains). Hooked after
  insert_pairs in tapematch_session.py; gated by new config.yaml rule_d.live_embed flag.
  Tests: tools/tapematch/tests/test_emb_live.py (4) + verdict equivalence 177 → 181 pass;
  score --cached byte-identical (tp=684 fn=891 fp=9 tn=1381).
Changed: tools/tapematch/emb_score_pairs.py: `_score_pair` → public `score_pair` (importable
  by emb_live; CLI output verified byte-identical).
Added: tools/tapematch/nmfp_embed.py: `--n-excerpts` flag (default 5, byte-identical) for the
  TODO-202 densification probe. 12×60s pilot (523 sources, embed_cache_12x): kill condition
  NOT triggered — genuine-TN tail max 0.704 both-conv (vs 0.680 at 5×), still under the 0.75
  bar; full-set 12× embed + sweep proceeding.
Fixed: backend/db.py: dolphinsmile removed from _KNOWN_TAPER_ALIASES and added to _NOT_TAPER
  (+ misspelling variants) — he curates/transfers others' tapes, not a taper (curator ruling).
  Backfill: 463 entries.taper_name attributions NULLed in data/losslessbob.db.
Added: TODO.md TODO-203: Tier C retrain with family-aware hard negatives — sampler grouped
  hard negatives by (date, slot) ignoring family_id; 16.2% of same-date pairs are verified
  same-family → contrastive training pushed same-tape transfers apart. Includes
  taper-attribution negatives design (curated _KNOWN_TAPER_ALIASES handles only; raw
  taper_name strings measured NOT truth-grade: 381/2366 diff-raw-taper conflicts).

[2026-07-04] — feat(tapematch): nmfp Rule D SHIPPED (+25 TP, zero new FP) + label-set v2 + FN census
Added: tools/tapematch/tapematch/verdict.py: `_rule_d_emb_both` — both-convention embedding
  merge (emb_score aligned AND emb_score_global ≥ t_emb, cross-source only, NULL abstains);
  wired into `_addon_links`. config.yaml `addon_links.rule_d` ENABLED at t_emb 0.75 after
  full-frozen-set proof: score --cached tp=684 fn=891 fp=9 (recall 41.8%→43.4%, zero new FP);
  v2 labels tp=687 fp=6 (43.5%/99.1%). Full narrative: tools/tapematch/TIER_B_FULLSET_REPORT.md
  (re-opens the 2026-07-03 Tier B rejection — the p10/p90 gap gate tested lone-merge mode; the
  deferred absolute-FP curve through transitive clustering was the decisive measurement).
Added: tools/tapematch/tapematch_session.py: pairs.emb_score + pairs.emb_score_global
  (REAL nullable, idempotent ALTER, fp_triplet_score pattern); populated for 2240 frozen
  pairs via new tools/tapematch/persist_emb_scores.py (read-back verified via latest_pairs).
Changed: tools/tapematch/regression.py: `--set PATH` on the score subcommand (defaults to
  frozen v1 — byte-identical); passthrough branch extended (`_passthrough_with_rule_d`):
  on historical dates Rule D is strictly ADDITIVE over stored SAME_FAMILY edges (metric
  replay is not authoritative there — force-recompute probe collapsed baseline tp 659→512).
Added: tools/tapematch/regression_set_v2.json (+ make_regression_set_v2.py): v1 with the 3
  waveform-contradicted negatives (LB4642/9900, LB6825/9180, LB3431/3455, corr 0.93-0.95,
  label_suspect=1) flipped — real frozen FP count is 6, precision 99.1%. v1 stays frozen.
Added: tools/tapematch/fn_label_census.py (report-only): objective label-noise census over
  all 855 corr<0.05 FN — 265 (31.0%) flagged (128 explicit "different recording" curator
  text, 162 duration >15% off unity, 25 both).
Added: tools/tapematch/emb_fullset_eval.py: pre-registered threshold sweep (15 T × 3
  variants) over the full frozen set with absolute post-transitive-clustering FP counting
  against both label sets; acceptance-checked byte-identical to score --cached. Lone
  aligned-only variant REJECTED (transitive FP floor abs fp≥10 — guard-masking trap
  observed live); self-pair LB-3164/LB-3164 excluded as unmeasurable.
Changed: tools/tapematch/tests/test_verdict_equivalence.py: +3 Rule-D cases (dormant
  byte-identical, NULL abstain, self-pair never links) — 177 pass.

[2026-07-04] — feat(tapematch): Tier B nmfp harness extended to the full frozen set
Added: tools/tapematch/build_fullset_worklist.py: generalizes build_embed_eval_set.py's
  ~180-source pilot population to the entire frozen regression_set.json — every frozen
  negative pair ("neg") plus every frozen positive currently FN (derived exactly as
  `regression.py score --cached` derives it, imported not reimplemented) with corr<0.05
  ("fn_lowcorr"). Writes fullset_pairs.json (flat date/lb_a/lb_b/tag/corr list) +
  fullset_sources.json (embed_eval_set.json-shaped per-source metadata, deduped to the
  kept pairs) — consumable directly by nmfp_embed.py --eval-set. --pilot N --seed 42
  restricts to N random "neg" pairs + their sources for a cheap dry run. Read-only
  against observations.db; no audio/model run. Validated: 2245 kept (1390 neg + 855
  fn_lowcorr), 0 skipped for missing metadata, 726 dates / 2467 sources, <1s runtime.
Added: tools/tapematch/emb_score_pairs.py: computes nmfp emb_score for any
  build_fullset_worklist.py pairs file against embed_cache/, reusing embed_eval.py's
  _load_source/_pair_score verbatim (no refactor needed — already plain module
  functions) for both the tol=2s aligned and tol=0 global conventions. Outputs
  <stem>_scores.json + a min/median/p90/max summary per tag/tol. Validated against the
  existing 184-source embed_cache/ (scored the overlapping pairs correctly, nulled the
  rest as missing-cache).
Changed: tools/tapematch/nmfp_embed.py: docstring only — documented the pre-existing
  (unused-until-now) --eval-set PATH option, which already works generically against
  any embed_eval_set.json-shaped source list including the new fullset/pilot outputs;
  no code change needed. --workers was requested but skipped: forking after the
  TF/essentia model + checkpoint are loaded (and any GPU context init) risks
  duplicated/corrupted TF state across worker processes, so it was not added.

[2026-07-03] — docs(tapematch): Tier C ad hoc calibration probe report — reconfirms REJECT
Added: tools/tapematch/TIER_C_CALIBRATION_PROBE_REPORT.md: user-requested spot-check of the
  dormant Tier C contrastive encoder (ckpt/tierc.pt) against a 7-date/17-source calibration set
  with ground truth sourced independently of tapematch (entry_lineage same_as_lb parsing +
  explicit "different recording" curator-text scan via new tools/tapematch/
  _mine_calibration_candidates.py, cross-validated against observations.db history for 2 of the
  4 mined dates). Result: reconfirms the CC_TAPEMATCH_ADDON Tier C gate rejection on fresh
  out-of-sample data — same-source pairs Tier C didn't need to solve score high (0.85), the two
  hard historical same-source pairs (waveform corr ~0) separate only weakly from distinct pairs
  (0.32 vs 0.28 ceiling), and critically the one deliberately-hard case (2025-11-17 LB-16545, a
  full stem-separated remix of the same base recording) scores indistinguishable from genuinely
  distinct sources (0.22-0.29, inside the 0.18-0.28 distinct band) — Tier C cannot see through
  heavy reprocessing any better than waveform correlation can. No config/verdict/schema changes;
  read-only probe against the already-dormant checkpoint. Script: tools/tapematch/_tierc_probe.py.

[2026-07-03] — fix(tapematch): trim.performance_envelope spurious mistrim on compressed sources (BUG-235)
Fixed: tools/tapematch/tapematch/trim.py: performance_envelope now bails out to the full
  recording when whole-source energy dynamic range (p90-p10) is below the new
  trim.min_dynamic_range_db (10.0). Found via live 2025-11-16/17 Glasgow runs: two sources
  were cut to a 20-second "performance" window because the fixed p10+6dB energy gate
  chattered on heavily-normalised audio with only 6.4-8.5dB of crowd/music contrast, vs.
  11.9-15.4dB on known-good control dates. Re-running both dates post-fix keeps full
  length on all previously-broken sources and turned 2025-11-16's LB-16525/LB-16544
  same-source merge from a low-confidence fingerprint-only link (Dice 0.455) into a
  high-confidence primary correlation (0.924).
Added: tools/tapematch/tests/test_trim.py: synthetic wide/narrow dynamic-range + boundary
  tests for the new guard.
Changed: tools/tapematch/config.yaml: new trim.min_dynamic_range_db: 10.0 knob.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON effort concluded — Tier C rejected, calibration audit tool added
Changed: tools/tapematch/CALIBRATION_PROGRESS.md: confirmed with user that Gate 7.3.2's negative
  result (gap -0.017 tol=0 / -0.074 tol=2, both below the >=0.10 bar and both worse than Tier B's
  -0.034/nmfp baseline) stands as a final REJECT per the pre-agreed protocol — no Rule-C wiring, no
  pairs.emb_score column, no verdict/regression.py changes. Closes out the whole CC_TAPEMATCH_ADDON
  effort (Tiers 0/A/B/C) at the unchanged shipped state: recall 41.6%, precision 98.6%, fp=9.
Added: tools/tapematch/dump_calibration_audit.py + build_calibration_audit_html.py — reuse
  regression.py's exact score --cached internals to dump every frozen pair (2965 pairs, 3157 unique
  LB#s) with its truth label (lb_says_same), current verdict category (TP/FN/FP/TN), corr/fp_score/
  hiss_median, label_suspect flag, and the LB catalog relation-text the truth label was derived from.
  Outputs tools/tapematch/calibration_audit.json (data) + calibration_audit.html (self-contained
  interactive search/filter/sort table, published as a Claude Code artifact) so labels can be
  manually spot-checked against the actual curator notes — motivated by the known ~37% label-noise
  rate in the FN population and 3 confirmed mislabeled negatives found during Tier B.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier C (Task 7) — training run + gates 7.3.1/7.3.2 (decision pending)
Added: tools/tapematch/embedding/aug_sanity.py (Gate 7.3.1) — loads the trained checkpoint, samples
  200 cached windows, compares each window's clean embedding vs one AugmentChain-augmented view via
  cosine similarity, logs mean/median/min/p10. Result: mean=0.9638 median=0.9767 min=0.7921
  p10=0.9147 — PASS (bar >=0.80 mean/median).
Changed: tools/tapematch/embedding/ckpt/ — trained tierc.pt via train.py --device cuda, 30
  epochs/7170 steps, 69.8 min wall time, final loss ~0.029 (throughput measured first:
  --max-steps 100 gave steady-state 1.678 steps/sec, confirming the config default 30 epochs
  already lands in the 1-2h target with no config change needed).
Added: tools/tapematch/embed_cache_tierc/ — infer.py --device cuda over all 184 Task-6 eval
  sources (extracted=184 skip=0 fail=0, 46 dates).
Result: Gate 7.3.2 (decisive, embed_eval.py) — tol=0 gap p10(TP)-p90(TN) = 0.475-0.492 = -0.017;
  tol=2 gap = 0.267-0.341 = -0.074. Both below the >=0.10 bar and worse than the Tier B/nmfp
  -0.034 baseline at tol=2. Ship/reject decision intentionally left PENDING for user review — no
  Rule-C wiring, pairs.emb_score, or regression.py scoring touched. Full numbers in
  tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier C (Task 7) — package + training cache built (PAUSED before training)
Added: tools/tapematch/embedding/ package (isolated torch env .venv-emb, torch 2.6.0+cu124, RTX 3080):
  config.yaml (all hyperparams; embedding.CHECKPOINT + ENABLED=false), melspec.py (shared torchaudio
  log-mel, train/infer parity), data.py (hard-neg mining from observations.db same-date different-family
  EXCL label_suspect + 67 eval dates; time-aligned (date,slot) window cache so same-slot windows across
  a date's sources are same-show hard negatives; RESUMABLE per-source shard build), train.py (GPU NT-Xent
  loop, cosine LR+warmup), infer.py (CPU/GPU batch inference → embed_cache_tierc/, Tier-B harness format).
  augment.py + model.py landed via sonnet agents (see the two entries below).
Added: training cache tools/tapematch/embedding/audio_cache/windows.npy (gitignored) — 61,253 windows
  (float16, 1s@16k) from 1,278 sources / 200 densest multi-source dates; 9,600 (date,slot) groups, ALL
  multi-source (every group carries same-show hard negatives). Verified: no NaNs, sane amplitudes.
Verified: full loop smoke end-to-end (cache→train→infer→embed_eval gate) on a 2-date cache; batches
  carry 42/64 same-show hard negatives; mel(8,1,64,63)→encoder(8,128 unit-norm)→NT-Xent→backward OK.
Note: PAUSED for review BEFORE the training run per user request. Cache/env/nmfp-vendor all gitignored.
  Build ran DETACHED (setsid+nohup) after tool-managed background shells were repeatedly SIGKILLed;
  resumable shards made interruptions safe. NEXT (not started): throughput measure → full training →
  aug-sanity gate 7.3.1 → infer 184 eval sources → decisive p10(TP)-p90(TN) gate vs Tier B -0.034.
  Resume steps in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Task 7.1 — Tier C transfer-chain augmentation
Added: tools/tapematch/embedding/augment.py: AugmentChain(cfg, rng) — synthetic-positive
  generator for the contrastive embedding. Ops (each gated by its own config.yaml AUGMENT.*.P):
  speed warp (Fraction-based resample_poly, +-MAX_PCT), lowpass (6th-order Butterworth
  sosfiltfilt, cutoff in [F_MIN_HZ,F_MAX_HZ]), MP3 round-trip (real ffmpeg subprocess, f32le ->
  mp3 @ random KBPS -> f32le, FFT cross-correlation realignment to strip the ~1105-sample
  LAME encoder/decoder delay so the "positive" stays time-aligned with its source), tape hiss
  (additive gaussian at random SNR_DB), level ride (slow sinusoidal gain envelope, +-MAX_DB),
  EQ tilt (linear-in-frequency spectral tilt via rfft/irfft, +-MAX_DB), wow/flutter (sinusoidal
  time-warp via np.interp, +-MAX_PCT at RATE_HZ). GEN_STACK composes MIN_OPS..MAX_OPS
  (2-3) randomly-ordered distinct ops per call, re-rolling each op's own P; all randomness
  drawn from the injected np.random.Generator for reproducible training. Output is always
  cropped/zero-padded back to the input length (_fix_length) regardless of which
  length-changing ops fired. numpy+scipy only (no librosa); ffmpeg via subprocess.
Added: tools/tapematch/embedding/tests/test_augment.py: 21 pytest cases (parametrized per-op
  finite/same-length/changed checks, MP3 round-trip correlates-but-not-identical, full-chain
  determinism under equal-seed rng, 10-seed log-magnitude-spectrum similarity sanity >=0.3 using
  a band-limited-noise fixture — a pure-tone fixture was tried first and rejected: narrowband
  line spectra decorrelate under a few-% frequency shift even though the augmentation is mild,
  which is a test-signal artifact, not a bug). All pass under .venv-emb.
Fixed: tools/tapematch/embedding/augment.py: MP3 round-trip was silently time-shifting the
  "positive" view by ~1105 samples (69 ms @ 16 kHz, the LAME encoder+decoder delay) relative to
  its source before length-cropping — waveform corr at lag 0 was -0.70 on a caught test signal
  vs 0.997 at the true alignment. Fixed by FFT cross-correlating the decoded PCM (which ffmpeg
  returns ~1280 samples longer than input) against the input over all valid offsets and cropping
  the best-aligned n-sample window, instead of naively taking the first n samples.
Note: implements spec 7.1 (augmentation menu) only. data.py (hard-negative mining/sampler),
  train.py, infer.py are NOT yet implemented — Task 7 is still in progress.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Task 7.2 — Tier C ConvEncoder + NT-Xent loss
Added: tools/tapematch/embedding/model.py: ConvEncoder(cfg) — small conv stack (stem + 4x
  stride-2 Conv2d/BN/ReLU blocks downsampling freq+time jointly) + AdaptiveAvgPool2d + Linear
  projection to EMB_DIM (128) + L2-normalize; (B,1,64,T) log-mel in -> (B,128) unit-norm
  embedding out. 587,712 params (config-driven via MODEL.WIDTH=64/EMB_DIM=128), well under the
  10M hard budget (spec 7.2). Also adds nt_xent(z1, z2, temperature): symmetric NT-Xent/InfoNCE
  over the 2B-row batch (positives z1[i]<->z2[i], all other 2B-2 entries as in-batch negatives)
  — same-show hard negatives from the data sampler (TRAIN.HARD_NEG_MIN_FRAC>=0.25) need no extra
  masking, they simply sit in the negative set.
Added: tools/tapematch/embedding/tests/test_model.py: 5 pytest cases — forward shape + exact
  unit L2 norm, param count <=10M, CPU-only run, NT-Xent scalar/finite/backward, NT-Xent rewards
  agreement (z2==z1 loss < random-z2 loss). All pass under .venv-emb (installed pip+pytest into
  that env via ensurepip; PyYAML was already present).
Note: this implements spec 7.2 model+loss only. data.py (hard-negative mining/sampler),
  augment.py, train.py, infer.py are NOT yet implemented — Task 7 is still in progress.
Added: tools/tapematch/nmfp_embed.py: real embedding extractor (runs under isolated .venv-nmfp,
  TF2.13/essentia/CPU). Reproduces neural-music-fp's exact essentia-mel + FingerPrinter (nmfp-triplet
  ckpt-100) on exactly-8000-sample segments → faithful 128-d L2-normalized fingerprints. Decodes each
  track individually + concatenates PCM (Shorten .shn has no timestamps → ffmpeg concat demuxer stops
  after track 1; fixed by per-file decode). All 184/184 eval sources embedded.
Added: tools/tapematch/TIER_B_EMBED_REPORT.md: full Task 6 report (model justification, distributions,
  gap vs triplet, label-noise analysis, verdict).
Added: tools/tapematch/.venv-nmfp (gitignored): isolated py3.11 env (uv) — tensorflow-cpu 2.13.0,
  numpy 1.24.3, essentia 2.1b6.dev1110, pandas 2.1.4, h5py, pyyaml, soundfile. vendor/neural-music-fp
  repo + Zenodo checkpoint (gitignored, ~200 MB). Main .venv untouched (nmfp deps NOT in requirements.txt).
Result: TP median 0.912 vs same-show-TN median 0.150 (aligned) — learned similarity SEPARATES the
  population that killed every content-based signal (triplet median Δ≈0). BUT p10(TP)-p90(TN) gap
  = -0.034 (aligned) / +0.007 (global), both < 0.10 → REJECT per spec 6.2 (tail overlap; nmfp is
  Rule-C-only). Killer TN tail (max 0.961) is LABEL NOISE: 3 frozen negatives are waveform-contradicted
  (corr 0.92-0.95, same family) — flagged pairs.label_suspect=1 (poison as Tier C hard negatives).
  Excluding them, genuine same-show collisions cap at 0.605; Rule-C bar ~0.65 recovers 8/60 FN with
  0 clean-neg FP (marginal, only over 59 negs; NOT shipped — no emb_score/Rule C wiring, per spec
  "fail gap → stop Tier B"). Strong positive signal for Tier C (Task 7): a PRETRAINED fingerprint
  already separates; contrastive training targets the 0.3-0.6 genuine-collision band this isolates.
Changed: tools/tapematch/embed_extract.py: _NmfpBackend now points to nmfp_embed.py (the real TF-env
  extractor) instead of an in-process wire. tools/tapematch/observations.db: 3 negative label-error
  pairs flagged label_suspect=1. Resume/Tier-C handoff in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-03] — feat(tapematch): CC_TAPEMATCH_ADDON Tier B (Task 6) measurement harness — built + proven, gated on model install
Added: tools/tapematch/build_embed_eval_set.py: Task 6.1.4 eval-set builder. Date-clustered
  selection (embed each source once, reuse across in-stratum pairs) → embed_eval_set.json with
  60 TP (frozen positives, corr>=0.05) / 60 same-date different-source TN / 60 target-FN
  (frozen positives corr<0.05, excluding Task-1 label_suspect). 67 dates, 184 distinct sources.
Added: tools/tapematch/embed_extract.py: Task 6.1 extraction. Pluggable backend — `synthetic`
  (audio/model-free plumbing) proven end-to-end; `nmfp` (raraz15/neural-music-fp, TF2.13/8kHz —
  the spec-ideal degradation-robust FP with a discriminative head) and `muq` (torch foundation
  fallback) real paths written but NotImplementedError until an isolated model env is set up.
  Embeds 1s/0.5s-hop windows over 5×60s excerpts; nominal time = seconds-into-performance (from
  trim_head, speed-corrected) so both transfers of a concert share an origin; caches per-source npz.
Added: tools/tapematch/embed_eval.py: Task 6.2 gate + report (numpy-only, model-free). Per-pair
  emb_score = median A-window cosine-max to B (±tol aligned neighbourhood, or global when tol<=0);
  prints TP/same-show-TN/FN distributions + p10(TP)-p90(TN) gap, mirrors calibrate_triplet.py.
  Ships Tier B only if gap>=0.10 (triplet baseline -0.012); else structural REJECT.
Verified: synthetic backend end-to-end on the real 60/60/60 eval set — all pairs scored, gap ~0
  (noise floor, as expected: different-LB synthetic pairs share no lineage signal). ffmpeg/ffprobe
  present; all sampled eval sources resolve in my_collection with readable audio → real extraction
  de-risked. REMAINING (gated on user's model choice): install model, run live extraction, report
  the real gap. No conda/uv/py3.11 on host → nmfp needs an isolated py3.11 env bootstrap.
Note: torch 2.12 + tensorflow 2.21 both install on py3.13; RTX 3080 (10 GB) available. Main .venv
  stays pinned — model deps go in an isolated env (.venv-nmfp/.venv-emb, gitignored).

[2026-07-03] — test(tapematch): CC_TAPEMATCH_ADDON Phase 2 calibration COMPLETE — Tier A verdict (dormant)
Changed: tools/tapematch/config.yaml: calibration done over 11 dates. flaw_match_score is the one
  precision-SAFE Tier A signal (TN max 0.133 vs TP→0.900, no triplet-style collision) but coverage is
  ~6% of frozen FN, so a precision-safe threshold nets only +1..+2 TP (+0.1 recall pt). The aggressive
  zero-FP bar 0.143 gave abs fp=10 via TRANSITIVE clustering (per-run guard said "new FP: none" — the
  guard-masking trap; absolute fp is the real gate). Left DORMANT: addon_links.rule_a.enabled=false
  (t_flaw documented 0.45 for opt-in), rule_b/c false, flaw/stationarity/env computation flags false.
  spec_stationarity + env_corr REJECTED (individual gaps fail; Rule B AND-gate recovers 0 — content-
  adjacent same-show collision). Config back at the shipped 41.6% recall / fp=9 baseline (byte-identical).
  CONCLUSION: Tier A forensic signals hit their ceiling; the non-correlating FN bulk needs Tier B/C
  learned similarity. Verdict table + resume steps in tools/tapematch/CALIBRATION_PROGRESS.md.

[2026-07-02] — test(tapematch): CC_TAPEMATCH_ADDON Phase 2 live calibration harness + detached run
Added: tools/tapematch/calibrate_addon.py: DB-only calibration analyzer for the three Tier A signals
  (mirrors calibrate_triplet.py). Per signal: TP / same-date-diff-source-TN distributions, p10(TP)−p90(TN)
  gap gate (ship iff ≥0.10), a zero-FP bar (max-TN) for the lineage-pure flaw path, target-FN coverage,
  and a Rule B conjunction (spec_stationarity AND env_corr) scan. Excludes label_suspect=1 from TP.
Added: tools/tapematch/calib_logs/run_addon_measure.sh: detached (nohup, PPID→init) measurement watcher —
  waits for the population batch + any live session to clear, re-runs any unpopulated date (idempotent),
  then runs calibrate_addon.py + `regression.py score --cached` and writes `ADDON_CALIB_DONE`. Survives
  Claude session limits (the calibration agent died on one). Config: three metric-COMPUTATION flags set
  true (no merge armed — addon_links rules stay false); population is precision-safe.
Note: preliminary (8/11 dates) — flaw_match_score shows a clean zero-FP separation (TN max 0.133 vs TP→0.900,
  16/42 TP recoverable at ~0.14, 0 in-sample FP); stationarity/env reject the p10/p90 gap (conjunctive-only,
  content-adjacent). Full 11-date RESULTS land in calib_logs/addon_calib_progress.log. See CALIBRATION_PROGRESS.md.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 5 (Tier A close-out) — evidence combination + coverage instrumentation
Added: tools/tapematch/tapematch/verdict.py: `addon_links` evaluated in `pair_links` alongside
  every other OR-path — `_rule_a_lone_lineage` (`flaw_match_score >= t_flaw` AND both-side
  `flaw_n_events >= min_events`), `_rule_b_two_leg` (`spec_stationarity >= t_stat` AND
  `env_corr >= t_env`, conjunctive by construction — the only route either signal has into a
  verdict), `_rule_c_belt_and_braces` (`emb_score >= t_emb` AND (`flaw_match_score >=
  t_flaw_weak` OR `spec_stationarity >= t_stat`); `emb_score` has no persisted column yet
  (Task 6) so this rule reads it via `dict.get` and abstains defensively rather than crashing).
  Every rule independently gated on its own `enabled` flag (all `enabled: false`); NULL on ANY
  leg means that rule abstains, never coerced to 0.0. No rule reads `lb_says_same` or
  `entry_lineage` (frozen-set validity guard). `METRIC_KEYS` gains `emb_score` for forward
  round-tripping (always None/absent today — no column exists).
Changed: tools/tapematch/tapematch/verdict.py: **reconciled** the Task 2.3 standalone flaw
  OR-path (previously gated solely on `flaw_fingerprint.enabled`, living directly in
  `pair_links`) into Rule A — removed the standalone block so there is exactly one canonical
  flaw-fingerprint merge path, not two competing ones. `flaw_fingerprint.enabled` now only
  gates whether the metric is *computed* (cli.py, unchanged); `addon_links.rule_a.enabled`
  gates whether it may *merge*.
Added: tools/tapematch/config.yaml `addon_links:` block — `rule_a` (`t_flaw: 0.6`,
  `min_events: 8`, carried over unchanged from the superseded `flaw_fingerprint.
  merge_threshold`/`min_events_merge`), `rule_b` (`t_stat: 0.7`, `t_env: 0.90`), `rule_c`
  (`t_emb: 0.70`, `t_flaw_weak: 0.4`, `t_stat: 0.7`) — all `enabled: false`, every threshold
  marked "uncalibrated — set by Calibration protocol". Removed the now-superseded
  `flaw_fingerprint.merge_threshold`/`min_events_merge` keys (comment points to
  `addon_links.rule_a`).
Added: tools/tapematch/regression.py: `_ADDON_METRIC_COLS` + `_addon_coverage()` /
  `_print_addon_coverage()` — Task 5.3 per-signal FN coverage. For each of
  `flaw_match_score`/`spec_stationarity`/`env_corr`/`emb_score` that exists as a `pairs`
  column, counts how many frozen FN pairs (positives the candidate verdicts
  `different_family`) carry a non-NULL value; printed as a new section after `score --cached`'s
  existing confusion-matrix output (columns not yet present, e.g. `env_corr`/`emb_score` in
  the current `observations.db`, are omitted rather than shown as a misleading 0). Bounds each
  signal's max possible recall contribution and surfaces low-coverage signals immediately.
Added: tools/tapematch/tests/test_verdict_equivalence.py — `test_addon_links_rule_a_fires_
  when_enabled_and_gated`, `test_addon_links_rule_a_null_column_is_inert_on_historical_rows`,
  `test_flaw_fingerprint_enabled_alone_no_longer_merges` (proves the reconciliation — the old
  key alone can no longer merge), `test_addon_links_rule_b_two_leg_conjunctive`,
  `test_addon_links_rule_c_abstains_when_emb_score_absent` (both key-missing and
  explicit-None forms), `test_addon_links_rule_c_fires_when_enabled_and_gated`,
  `test_addon_links_all_disabled_is_byte_identical_to_no_addon_links`. Full non-`test_batch_
  queue` suite: 269 passed, 2 pre-existing unrelated failures in
  `test_find_lb_folders_no_audio.py` (untouched by this change — `find_lb_folders` return-type
  drift from an earlier uncommitted `tapematch_session.py` edit), 4 deselected.
Not done: real-audio calibration (CC_TAPEMATCH_ADDON.md Calibration protocol) for any rule —
  all `addon_links` rules `enabled: false`; do not enable without a fresh gap check on frozen
  TP/same-show-TN/FN per rule. Task 6 (`emb_score` column + Rule C activation) and Task 7 not
  started.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 4 (Tier A) — band-limited envelope correlation
Added: tools/tapematch/tapematch/match.py: `envelope_corr(mono_a, mono_b, sr, cfg, hf_ceiling_hz_a,
  hf_ceiling_hz_b, speed_ratio, offset_sec)` — zero-phase Butterworth bandpass both sides to
  `[band_lo_hz, min(hf_ceiling_a, hf_ceiling_b, band_hi_cap_hz)]` (200 Hz / 2000 Hz defaults, never
  above the narrower side's HF ceiling), computes a 20 Hz RMS envelope per side (`_rms_envelope`
  helper), affine speed-maps A's envelope clock onto B's (`t_mapped = offset_sec + speed_ratio *
  t_a`, identical convention to `flaw_match_score`), linearly interpolates B onto the mapped grid,
  and returns Pearson correlation over the overlap. Returns `None` (never 0.0) when the band is
  degenerate (narrower HF ceiling at/below `band_lo_hz`) or mapped overlap < `min_overlap_min`
  (10 min default). **High same-show collision risk** — envelope is music-dominated (the triplet
  failure mode); flagged explicitly in match.py/config.yaml/WORKFLOW.md as conjunctive-only and
  banned from ever becoming a lone-merge OR-path, even post-calibration (spec 4.2 hard rule).
Added: config.yaml `envelope_corr:` block — `band_lo_hz: 200.0`, `band_hi_cap_hz: 2000.0`,
  `filter_order: 6`, `frame_rate_hz: 20.0`, `min_overlap_min: 10.0`, `enabled: false` (uncalibrated).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.env_corr REAL`
  (idempotent ALTER); `insert_pairs` populates it from the run JSON's `secondary_pairs` entries
  (same dormant-NULL pattern as `spec_stationarity`/`flaw_match_score`).
Changed: tools/tapematch/tapematch/cli.py: cross_pairs secondary-match loop computes `env_corr` per
  pair when `envelope_corr.enabled` (reuses the Task 3 lineage pre-pass `hf_ceiling_hz` values and
  the pair's speed ratio/coarse offset, same predicted-lag-aware offset computation as the
  `flaw_match_score` block); `None`/skipped entirely while disabled (zero cost dormant).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains `env_corr` for cached-scoring
  round-tripping. Deliberately **no OR-path** — spec 4.2 bans a lone-merge path for this signal
  permanently (not just pending calibration, unlike `spec_stationarity`); combination rules are
  Task 5's `addon_links` (e.g. AND'd with `spec_stationarity`).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains `env_corr`.
Added: tools/tapematch/tests/test_envelope_corr.py — 7 synthetic tests (no live audio): same
  recording + fixed band-limit/EQ + noise → corr ≥0.9; independent signals → corr ≤0.5; <10 min
  overlap → None; offset pushes overlap out of range → None; ±5000 ppm speed-warp robustness (both
  directions) → corr ≥0.85; HF ceiling below `band_lo_hz` → None. Extended
  tests/test_verdict_equivalence.py with `test_env_corr_null_column_is_inert`, proving the new
  nullable column leaves `pair_links` byte-identical on historical (NULL) and populated-but-dormant
  rows, alongside `spec_stationarity`. Full suite (Tasks 2/3/4 + verdict equivalence): 193 passed.
Not done: real-audio calibration (CC_TAPEMATCH_ADDON.md Calibration protocol) — `enabled: false`,
  no verdict wiring change; do not enable or add to Task 5 `addon_links` before that gap check.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 3 (Tier A) — spectral-ratio stationarity
Added: tools/tapematch/tapematch/match.py: `spectral_ratio_stationarity(mono_a, mono_b, sr, cfg,
  hf_ceiling_hz_a, hf_ceiling_hz_b, noise_floor_db_a, noise_floor_db_b, predicted_lag=None)` —
  reuses the windowed-coverage grid (own `spectral_stationarity.*` knobs; per-window local-lag or
  predicted-lag-centered search, same as `secondary_corr_pair`); per window converts both aligned
  sides to log-mel (32 bands via `librosa.filters.mel`, capped at
  `min(hf_ceiling_a, hf_ceiling_b, 0.45*sr)`), excludes frames where either side is below its own
  `noise_floor_db + noise_floor_margin_db`, takes `R_w[band] = median_t(logmel_A-logmel_B)` over
  kept frames; `stationarity = 1 - mean_band(std_w(R_w)) / stationarity_norm_db` clipped [0,1].
  Returns `None` (never 0.0) below `stationarity_min_windows` (6) usable windows or when the HF cap
  is 0. Phase-blind/magnitude-only, so it works where `residual_corr` dies (corr ~0.005).
Added: config.yaml `spectral_stationarity:` block — grid/mel/noise-floor/norm knobs,
  `stationarity_norm_db: 6.0`, `stationarity_min_windows: 6`, `enabled: false` (uncalibrated).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.spec_stationarity REAL`
  (idempotent ALTER); `insert_pairs` populates it from the run JSON's `secondary_pairs` entries
  (same dormant-NULL pattern as `flaw_match_score`).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains `spec_stationarity` for
  cached-scoring round-tripping. Deliberately **no OR-path** — spec bans a lone-merge path for this
  signal (content-adjacent; combination rules deferred to Task 5's `addon_links`, conjunctive only).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains `spec_stationarity`.
Changed: tools/tapematch/tapematch/cli.py: moved the "lineage pre-pass" (`lineage_evidence` per
  source — `hf_ceiling_hz`/`noise_floor_db`) earlier, ahead of the secondary-match cross_pairs loop
  instead of after it (pure reordering, unconditional either way, no behaviour change) so
  `hf_ceiling`/`noise_floor` are available for the per-pair stationarity call; cross-pair loop scores
  `spec_stationarity` gated on `spectral_stationarity.enabled` (zero cost while dormant).
Added: tools/tapematch/tests/test_spectral_stationarity.py — same-signal+fixed-EQ high
  stationarity, two-different-signals and slowly-time-varying-EQ low/lower stationarity,
  +-0.4s alignment-jitter robustness, None-not-0.0 on too-short/zero-HF-cap inputs, [0,1] clip
  (7 tests).
Changed: tools/tapematch/tests/test_verdict_equivalence.py — 1 new test proving `spec_stationarity`
  is registered in `METRIC_KEYS` but stays fully inert (NULL or populated-and-high, with or without
  the config block) since no OR-path reads it; other legs' outcomes unaffected by its presence
  (185 tests total in the verdict/flaw/stationarity trio, all green).
Verify before calibration: `noise_floor_margin_db`'s quiet-frame gate compares STFT-power dB
  against `lineage_evidence`'s Welch-PSD dB — an intentional same-side-relative simplification (the
  absolute scale differs; only the per-side comparison matters), but the effective margin should be
  sanity-checked against a handful of real hf_ceiling/noise_floor readings before the Calibration
  protocol's >=100-pair real-audio pass.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 2 (Tier A) — shared-flaw event fingerprint
Added: tools/tapematch/tapematch/match.py: `extract_flaw_events(mono, sr, cfg, trim_head_sec,
  trim_tail_sec)` — per-source flaw timeline (dropout: 20ms-hop RMS >20dB below its 2s local
  median for 40-800ms; click: sample-domain residual >6sigma of local 50ms MAD, isolated <5ms,
  capped at 200 strongest; cut: joint 100ms spectral-centroid+RMS discontinuity >4sigma — extends
  the jump-vs-sigma technique `align.locate_splice_points` uses on a pairwise lag curve to a
  per-source RMS/centroid curve instead, so no reference source is needed). Reuses
  `find_quiet_segments` so between-song gaps are never counted as dropouts/cuts. All detectors are
  memmap-block-read (2h-source safe) except the sample-domain click pass, which materializes one
  float32 residual array (consistent with the existing `lowband_envelope_corr` full-array pattern).
Added: tools/tapematch/tapematch/match.py: `flaw_match_score(events_a, events_b, speed_ratio,
  offset_sec, cfg)` — matched/min(|A|,|B|) dropout+click+cut events after mapping A's clock onto
  B's via the pair's speed ratio + coarse offset (tol 0.5s); returns `None` (never 0.0) below
  `flaw_min_events` (5) — absence of flaws is absence of evidence, not evidence of difference.
Added: config.yaml `flaw_fingerprint:` block — all extraction/scoring/verdict thresholds,
  `enabled: false` (uncalibrated; do not enable without a real-audio gap check per the
  Calibration protocol in CC_TAPEMATCH_ADDON.md).
Changed: tools/tapematch_session.py: `open_obs_db()` gains nullable `pairs.flaw_match_score REAL`,
  `flaw_n_events_a/b INTEGER` (idempotent ALTER); `insert_pairs` populates them from the run JSON's
  `secondary_pairs` entries (same dormant-NULL pattern as `fp_triplet_score`).
Changed: tools/tapematch/tapematch/verdict.py: `METRIC_KEYS` gains the three flaw columns;
  `pair_links` gains an OR-path — `flaw_match_score >= flaw_fingerprint.merge_threshold` AND both
  `flaw_n_events_a/b >= min_events_merge` (8), gated on `flaw_fingerprint.enabled`, inert on NULL
  (mirrors the dormant triplet-fingerprint path exactly).
Changed: tools/tapematch/regression.py: `_SECONDARY_METRIC_COLS` gains the three flaw columns so
  `score --cached` recomputes verdicts when they're populated.
Changed: tools/tapematch/tapematch/cli.py: computes `extract_flaw_events` per source upfront
  (full-length, gated on `flaw_fingerprint.enabled` — zero cost while disabled) alongside the
  existing fingerprint/triplet pass; cross-pair loop scores `flaw_match_score` (offset reuses the
  Task-4 predicted-lag anchor-0 lag when already computed, else one fresh `local_lag` call — flaw
  sets are sparse); run JSON `sources[name]` gains `flaw_event_count` + serialized `flaw_events`
  timeline (variable-length, so run-JSON-only per spec, not the DB).
Added: tools/tapematch/tests/test_flaw_fingerprint.py — synthetic dropout/click/cut injection +
  extraction tests, inherited-flaw pair score ~1.0 under +-5000ppm speed warp, independent-flaw
  pair score ~0, None-not-coerced-to-0.0 sanity, between-song quiet-gap exclusion (10 tests).
Changed: tools/tapematch/tests/test_verdict_equivalence.py — 3 new tests proving the flaw OR-path
  is byte-identical-inert when `enabled: false` (default) or when the DB column is NULL
  (historical rows), and fires correctly when enabled + both gates clear (177 tests total, all
  green; pre-existing `test_find_lb_folders_no_audio.py` failures are unrelated/pre-dated this
  session, confirmed via `git stash`).
Unresolved: the "cut" detector's "reuse/extend the CDR re-tracking (staircase) edit detector"
  requirement is honored as a *technique* reuse (jump-vs-robust-sigma, mirroring
  `align.locate_splice_points`), not a literal call — the staircase detector is inherently
  pairwise (two sources' lag curve), while Task 2.1 specifies a single-source detector. Flag for
  review before calibration.

[2026-07-02] — feat(tapematch): CC_TAPEMATCH_ADDON Task 1 (Tier 0) — FN forensic audit + label-noise quantification
Added: tools/tapematch/audit_fn.py — recomputes the current corr<0.05 FN population (859 pairs,
  same `verdict.cluster_verdicts` path as `regression.py score --cached`), draws a stratified
  60-pair sample (20 speed-corrected/20 speed-unknown/20 staircase x hf_ceiling-gap secondary
  strata), builds a per-pair evidence dossier (LB source/relation text, raw metrics, a throwaway
  4-band envelope-corr quick check via direct ffmpeg window decode — no session/staging-dir use,
  so the live-session concurrency hazard doesn't apply), and a transparent label_assessment
  heuristic (explicit "different recording" text > taper-name conflict > duration-ratio mismatch
  > explanatory lossy/band-limited lineage > envelope-corr hint > indeterminate).
Added: tools/tapematch/FN_AUDIT_REPORT.md — 60-pair dossier + headline: label-noise rate 36.7%
  (22/60, Wilson 95% CI 25.6-49.3%) extrapolated to the 859-pair population (~315 pairs, CI
  220-424) — re-based recall ceiling **~80.0%** (CI 73.1-86.0%), re-scoping Tiers B/C targets
  down from the naive "no perfect matcher could exceed 100%" framing.
Changed: tools/tapematch_session.py: open_obs_db() gains nullable pairs.label_suspect INTEGER
  (idempotent ALTER; NULL=not-assessed, 1=suspect) so Tier C training/eval can exclude flagged
  pairs. 22 pairs flagged from the sample; frozen-set labels themselves left untouched.

[2026-07-02] — docs(tapematch): CC_TAPEMATCH_ADDON spec — add-on approaches past the 42% recall ceiling
Added: instructions/CC_TAPEMATCH_ADDON.md — three-tier spec for the 93% non-correlating FN bulk:
  Tier 0 FN forensic audit + label-noise quantification (Task 1, sets the honest ceiling and
  pairs.label_suspect flag); Tier A content-blind lineage-forensic signals (Tasks 2-5: shared-flaw
  event fingerprint / spectral-ratio stationarity / envelope corr conjunctive-only / verdict
  addon_links + coverage reporting); Tier B pretrained neural-fingerprint embedding eval (Task 6);
  Tier C contrastive lineage embedding with same-show hard negatives, curator labels eval-only
  (Task 7). Codifies the triplet lesson (content-based similarity collides on same-concert
  different-source negatives) as a mandatory calibration protocol: real same-date TN population,
  gap >= 0.10 or structural reject, absolute fp <= 9 guard.
Added: TODO.md — TODO-199 tracking the addon spec.

[2026-07-02] — feat(tapematch): Tasks 5-7 (estimate_ratio_v2 / lag-residual / pyin / triplet fingerprint); triplet REJECTED; ~42% recall ceiling documented
Added: tools/tapematch/tapematch/match.py — estimate_ratio_v2 (prior-centered, confidence-reporting;
  old estimate_ratio kept as estimate_ratio_v1_deprecated for A/B), duration_ratio_prior,
  pitch_ratio_pyin + _pick_pitch_windows (Tasks 5 / 6.2), and a DORMANT ratio-invariant triplet
  fingerprint (triplet_hashes / triplet_window / _fingerprint_peaks / _quant_log, Task 7).
Added: tools/tapematch/tapematch/align.py — residual_ppm_from_lag_curve (r²>0.85 + <4-anchor guards,
  Task 6.1), wired into the PRIMARY residual-corr loop in cli.py only (never before secondary_corr_pair).
Changed: tools/tapematch/tapematch/cli.py — v2 confidence gate (align.ratio_confidence_min) →
  speed_kind="speed-unknown" routing + count; duration prior plumbed from trim_bounds; per-pair
  fp_triplet_score computed when triplet enabled.
Changed: tools/tapematch/tapematch/verdict.py — triplet OR-path (fingerprint.triplet), inert on the
  NULL column → 164 verdict-equivalence tests stay byte-identical.
Added: observations.db pairs.fp_triplet_score column (CREATE + idempotent ALTER in open_obs_db;
  insert_pairs persists it; regression.py auto-selects via METRIC_KEYS). New tools/tapematch/calibrate_triplet.py
  (Task 7.4 DB-only calibrator) + RECALL_RECOVERY_REPORT.md + cat3_rerun_report.md.
Rejected: fingerprint.triplet.enabled=false — live calibration (116 real pairs) showed same-show
  different-source pairs collide (triplet Dice 0.63–0.65, OVERLAPPING true-same-source 0.66, gap −0.012);
  at threshold 0.45 it manufactured 5 false merges on frozen negatives. Disabled; code kept dormant.
Result: final precision-safe recall 41.6% / precision 98.6% / fp=9 (vs 38.3%/98.2% audit baseline).
  estimate_ratio_v2 precision-safe but only +0.2 on Cat-1 dates; ratio_confidence_min sweep 6.0→4.5
  recovered nothing (pairs resample but corr stays 0.002–0.010); Cat-3 re-run 0/6 flipped. 93% of FN
  are non-correlating even when correctly speed-aligned → >80% needs the out-of-scope contrastive-
  embedding model. Full analysis: tools/tapematch/RECALL_RECOVERY_REPORT.md.
Added: tools/tapematch/tests/test_speed_v2_pyin.py (7) + test_triplet_fingerprint.py (4) — 175 tests green.
Config: align.ratio_confidence_min=6.0, align.pyin_fallback=true, fingerprint.triplet.* (enabled=false).

[2026-07-02] — feat(tapematch): calibration verdict — staircase 0.40 KEPT (+5 TP, 0 new FP) + curator/lo-fi live wiring in cli.py
Changed: tools/tapematch/tapematch/cli.py — production-wired Tasks 4.1/4.2: `_pair_metrics` now
  supplies lb_a/lb_b (folder-name regex), lineage pairs (new `--lineage-db`, defaults to
  data/losslessbob.db, inert on failure) and hf_ceiling/nyquist from a lineage-evidence pre-pass
  moved before clustering (print section reuses it; byte-identical output). Validated live on the
  1991-02-10 session (rc=0) + 164 equivalence tests green.
Added: tools/tapematch/CALIBRATION_PROGRESS.md — calibration results: staircase fp bar 0.40 nets
  recall 39.2%→39.6% (+5 TP, all 1996-11-04 staircase pairs fp 0.433–0.447) with ZERO new FP on
  2965 frozen pairs → kept per decision rule. Curator relaxation NOT shipped as measured
  (entry_lineage covers 244/1575; lb_says_same keying tautological — human_judgment NULL DB-wide).
  1993-06-27 staircase FNs (fp 0.27–0.37) overlap negatives (≤0.387) → unrecoverable, Cat-1 land.
Fixed: session concurrency hazard documented — `regression.py score --dates` runs LIVE sessions
  sharing /mnt/DATA0/examples/tapematch staging; a concurrent run killed the batch's 1996-11-04
  session (re-run cleanly after). Never run live sessions concurrently.
Added: tools/tapematch/calib_logs/ — run_batch.sh/run_batch2.sh (detached calibration batches),
  analyze_staircase.sh (A/B + fp/hiss band table), per-date logs, staircase_analysis.txt.

[2026-07-02] — feat(tapematch): Task 1 regression harness + verdict.py extraction (CC_TAPEMATCH_FIXES) + Tasks 2-4 no-audio scaffolding
Recovered: tools/tapematch/observations.db — the labeled-pairs DB (8022 pairs / 885 dates) had
  been moved to ~/.local/share/Trash on 2026-06-25 and the working copies left as 0-byte stubs.
  Restored (copied from Trash, original kept as backup); verified it reproduces the spec baseline
  signature exactly (fn=957; raw-pairs confusion 663/1066/12/1422 = P0.982/R0.383).
Added: tools/tapematch/tapematch/verdict.py — single source of truth for the pairwise clustering
  decision (Task 1.3). Pure `pair_links()` predicate mirroring match.cluster's OR-logic;
  per-pair `fp_threshold()` with staircase- (Task 3.2) and curator-lineage- (Task 4.1) conditional
  fingerprint thresholds; `_effective_hiss_median()` lo-fi relaxation (Task 4.2); transitive
  `cluster_verdicts()` (union-find); `load_lineage_pairs()` from entry_lineage.
Added: tools/tapematch/regression.py — recall/precision regression harness (Task 1.1/1.2/1.3).
  `freeze` extracts labeled pairs from the latest_pairs view (deduped) → regression_set.json,
  records the audit baseline + logs dedup drift; `score --cached` re-scores from stored rows with
  no audio (reproduces baseline exactly: R39.2/P98.6, zero delta, exit 0); `score --dates/
  --all-frozen-dates` re-runs sessions live (audio). New-FP on a frozen negative → exit 1.
Changed: tools/tapematch/tapematch/match.py: cluster() gains an optional `link_fn` predicate so
  cli.py can route the decision through verdict.pair_links (behaviour-identical; proven by
  tests/test_verdict_equivalence.py, 160 randomized cases). tapematch/cli.py clustering now calls
  it via a per-pair metrics builder.
Added: config.yaml fingerprint.cluster_threshold_staircase (0.40) / _curator (0.43) and
  secondary_match.hiss_merge_median_lofi (0.40) / hiss_lofi_ceiling_hz (12000). All optional —
  absent keys restore the prior single-scalar behaviour.
Added: tapematch_session.py: pairs table gains nullable windowed_frac/hiss_frac/hiss_median/
  fp_score/nyquist_capped_a/nyquist_capped_b columns (CREATE + idempotent ALTER migration in
  open_obs_db); insert_pairs now persists them from the run's secondary_pairs/sources JSON so
  Tasks 3/4 become score --cached-able once dates are re-run.
Added: tools/tapematch/rerun_cat3.py — Task 2 focused Cat-3 re-run (stage the pair alone, re-run,
  report before/after verdict). Parameterized (--list/--dates/--limit/--dry-run); execution is
  audio-gated. NOTE: the documented FN query matches 137 pairs, not the spec's stale "6".
Added: tools/tapematch/tests/test_verdict_equivalence.py — 164 tests: refactor equivalence +
  conditional-threshold + lo-fi + transitivity units.
Note: Task 3.1 (either-side staircase fallback) was ALREADY implemented in cli.py (line 497) — the
  spec premise was stale, like the latest_pairs view and migrate_observations.py. Pre-existing:
  the test_batch_queue-family tests hang when run against the real mounted /mnt collection
  (unrelated to this change; the 208 tests touching changed code all pass in 8.4s).

[2026-07-02] — fix(scraper): BUG-233 torrent filename data loss + close BUG-234 as verified-correct
Fixed: backend/wtrf_scraper.py: _download_torrent Content-Disposition parsing (BUG-233) — the old
  regex matched the RFC 5987 `filename*=UTF-8''real.torrent` parameter and captured "UTF-8" instead
  of the real name, so every batch-run download landed at the same "UTF-8.torrent" path and
  overwrote the previous one. Now prefers a plain `filename="..."` parameter and, only when absent,
  parses `filename*=charset''value` per RFC 5987 (strips the charset prefix, URL-decodes the value).
Fixed: BUGS.md/BUGS_DONE.md: BUG-234 closed as Wontfix — logged into WTRF and confirmed topic 55005
  is a legitimate 3-show Crystal Cat "Garden Party" boxset (CD1 Phoenix 5/13/25, CD2 Chula Vista
  5/15/25, CD3 George WA 5/25/25); LB-16404/16405/16406 each genuinely own one CD's checksums, so
  all three matching the same post is correct, not a signal collision.
Changed: backend/wtrf_scraper.py: _download_torrent now prefixes every saved filename with
  `LB-{lb_number:05d}-`, even when a real name comes from Content-Disposition. Needed because
  BUG-234's box-set case has three LB entries sharing one physical .torrent, so the header-derived
  filename alone was still identical across entries and would overwrite on disk per download.

[2026-07-01] — chore(scraper): re-ran WTRF skipped-review batch against checksum-search gains (TODO-197)
Changed: wtrf_skipped_review_rerun.md: re-ran all 85 LB entries from wtrf_skipped_review.md through
  tools/wtrf_fetch_missing.py post-BUG-231/232; 30/85 (35%) now resolve automatically (28
  definitive, 1 high, 1 medium), 13 needs_review, 11 ambiguous, 31 not_found.
Fixed: BUGS.md: BUG-233 note updated — confirmed the junk "UTF-8.torrent" filename causes batch
  runs to silently overwrite all but the last downloaded torrent (data loss, not just cosmetic).
Added: BUGS.md: BUG-234 — checksum body-search false-matched LB-16404/16405/16406 (three different
  shows) to the same WTRF topic 55005; needs investigation into over-broad checksum signal reuse.

[2026-07-01] — feat(gui): Concert Ranker audio metrics visualizations on the Quality tab
Added: backend/app.py: GET /api/quality/<lb_number> now also returns a `metrics` sub-dict —
  stereo/mono + width, clip_fraction, crowd_snr_db, bass/mud/harsh tonal-balance ratios, and
  source-type flags (lossy/minidisc/32k DAT/cassette/TV-band) — read from
  quality_recording_metrics.metric_json and banded to human labels via concert_ranker's own
  scoring.band_metric()/config.resolve_band_set() (same thresholds as verdict_text) so the UI
  never re-implements the banding logic. New helper: backend/app.py:_quality_metrics_for().
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: QualityMetricsPanel renders
  below the LB Rating/AI Quality Index tiles — thin tone-colored MetricBar meters for channels
  (mono/stereo + width), clipping %, crowd separation (dB), and bass/mud/harsh tonal balance, plus
  FlagChip pills for any tripped source-type flags (or a "no flags" note).
Added: gui_next locales (en/de/es/it/nl/fr): library.quality.metrics.{label,channels,mono,stereo,
  clipping,crowdSeparation,tonalBalance,bass,mud,harsh,balanced,sourceFlags,noFlags}.

[2026-07-01] — feat(gui): Quality page in library detail panel (LB Rating + AI Quality Index)
Added: backend/app.py: GET /api/quality/<lb_number> returns the latest Concert Ranker scan's
  abs_score/abs_grade/final_score/rank_in_family/verdict_text for one recording (204 if unscanned).
Added: gui_next/src/renderer/src/components/library/DetailPanel.tsx: new "Quality" tab on the
  recording detail panel (alongside Overview/Assets/Seed & Share, owned rows only) — QualityZone
  lazy-fetches /api/quality/<lb> and shows the catalog LB Rating side by side with the AI Quality
  Index (Concert Ranker's abs_grade + abs_score/100), bold Fact cards, plus the verdict_text note.
Added: gui_next locales (en/de/es/it/nl/fr): library.panel.tabQuality, library.quality.{label,
  lbRating,aiIndex,notScannedNote}.

[2026-07-01] — fix(scraper): WTRF checksum body-search + cross-recording guard (BUG-231/232)
Added: backend/db.py: lookup_checksum_owners() maps a set of MD5/SHA1 hashes to the lb_numbers
  that own them in the checksums table (chunked to stay under SQLite's parameter limit).
Added: backend/wtrf_scraper.py: deterministic checksum body-search as the primary lookup —
  _search_board gained a subject_only flag (False searches post bodies), _checksum_search_terms
  picks up to 3 of the entry's own hashes, and find_torrent_for_lb tries them first; a full-text
  hit lands directly on the correct taper's post regardless of topic-title date format (BUG-232).
Changed: backend/wtrf_scraper.py: date-variant subject search is now the fallback and unions
  candidates across ALL variants instead of breaking at the first that returns results; entries
  with an unparseable date (xx/xx/YY) are no longer rejected up front when checksums are available
  for a body search.
Fixed: backend/wtrf_scraper.py: candidates whose body checksums resolve to a different lb_number
  are now disqualified (they document another taper's recording), so an entry with no post of its
  own no longer produces a false "ambiguous" tie between two other tapers' posts (BUG-231).
  Verified: LB-16644 (nightly moth, Abilene 2026-05-01) now resolves definitively to topic 60289
  instead of tying LB-16616 (BenM) and LB-16617 (soomlos).

[2026-07-01] — feat(gui): double stage-icon size on pipeline detail screen
Changed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: StageStepper now passes
  size={48} (was default 24) to StageNode, doubling the Verify/Lookup/LBDIR/Rename/Collect tile icons
  on the pipeline detail screen's stage stepper row.
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineIcon.tsx, index.css: round glyph size
  and tile border-radius to even pixel values (was e.g. 27px glyph / 14.4px radius), which landed on
  half-pixel boundaries and rendered slightly blurred after the size increase; now sharp at any size.

[2026-07-01] — fix(backend): treat missing self-referencing lbdir-*.txt manifest as pass in LBDIR check
Fixed: backend/checksum_utils.py: in verify_folder_lbdir, a listed-but-not-on-disk file whose name
  matches the lbdir-*.txt manifest is now counted as pass (green) instead of missing. The manifest
  self-references its own checksum, which can never match the finished file, so it's unreconcilable —
  a folder whose only "missing" entry is the manifest now reaches status=pass instead of missing_files.
Added: backend/checksum_utils.py: _is_lbdir_manifest_name() helper + _LBDIR_MANIFEST_RE.

[2026-07-01] — feat(gui): custom app icon for Electron window/taskbar + packaged installers (TODO-196)
Added: gui_next/resources/icon.png: LB blue logo icon (1000x1000 PNG) picked up by electron-builder
  buildResources convention for packaged app/installer icons on Windows/macOS/Linux.
Changed: gui_next/src/main/index.ts: added `icon` (path resolved for packaged vs dev) to the
  BrowserWindow constructor. On native Wayland (GNOME) the dock icon is resolved only by matching
  the window's Wayland app_id to an installed .desktop basename, so a documenting comment records
  that the dev app_id is "losslessbob-next" (from package.json "name").
Added: gui_next/resources/losslessbob-next.desktop: dev-helper .desktop template, named to match
  the dev Wayland app_id. Install to ~/.local/share/applications/losslessbob-next.desktop so the
  `npm run dev` window shows the LB icon in the GNOME dock (BrowserWindow `icon` and StartupWMClass
  are ignored on native Wayland). The packaged AppImage gets its own generated .desktop from
  electron-builder and is unaffected.

[2026-07-01] — docs: close BUG-308, already fixed (BUG-308)
Fixed: BUGS.md/BUGS_DONE.md: BUG-308 (performance screen column widths) moved to BUGS_DONE.md as
  Fixed — no code change needed, user confirmed the performance-view table columns are already
  correct. On review, ScreenLibrary.tsx's performance table column model (~1849-2126) is
  internally consistent with the current 10-column layout.

[2026-07-01] — fix(gui): Pipeline screen untranslated English throughout (BUG-201)
Fixed: gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx: STATE/BUCKET step-state
  and bucket vocabularies and DEFAULT_STAGES stage labels were plain hardcoded strings baked into
  module-level consts, so StatusTag/StageNode/StageStepper/QueueRow always rendered English text
  regardless of locale. Converted each entry to a `labelKey` resolved via `t()` inside the
  consuming components (all four already are or now are function components with hook access);
  DEFAULT_STAGES reuses the pre-existing but previously-unused `pipeline.queue.{verify,lookup,
  lbdir,rename,collect}` keys.
Fixed: gui_next/src/renderer/src/components/pipeline/lookupState.ts: STATE_TONE lookup-state
  labels (Matched/Incomplete/Not found/Duplicate/XRef) hardcoded; changed to `labelKey` pointing
  at the existing `lookup.states.*` keys, resolved at each of the three call sites in
  LookupDetail.tsx (which already had `useTranslation()`).
Fixed: gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx: "Type" table header, row
  "Open"/"Pin LB-XXXXX & continue" button title/label, and "{n} row(s)" group-count text were
  hardcoded; wired to `t()` with new `lookup.table.openTitle`/`pinAndContinue` keys and the
  existing `lookup.table.type`/`lookup.status.rows` keys.
Fixed: gui_next/src/renderer/src/screens/ScreenPipeline.tsx: systematic pass replacing ~110
  hardcoded English strings across VerifyStageContent, LookupStageContent, RenameStageContent,
  CollectReadyDetail/CollectStageContent, LbdirStageContent, DetailPanel, the queue rail, table
  headers/row actions, and the context menu. STATE_LABEL (LBDIR status pills) and the file-error
  ERROR_MSG map were frontend-owned lookups keyed by stable backend enum codes (status/error_code)
  — converted their values to translated labelKeys the same way as PipelineParts, since only the
  key is backend-controlled, not the displayed text. deriveFolderStatus() (bucket/reason text for
  the batch table's Status column) now takes a `TFunction` param and returns translated
  label/reason strings instead of hardcoded English, reusing pipeline.stepStates/buckets keys
  where the wording overlaps. Left untouched, by design: raw backend `step.label`/`step.error`
  free-text values (e.g. verify's "Pass"/"Mismatch", lbdir's per-file messages, file-stage
  error.error fallback) — these originate as English strings from backend/app.py with embedded
  dynamic data and can't be safely mapped to locale keys without backend i18n plumbing; see
  TODO-195.
Added: gui_next/src/renderer/src/locales/en.json: ~120 new keys under `pipeline.*` (rerunStage,
  verify.*, lookup.*, rename.*, lbdir.*, collect.* additions, stepStates.*, buckets.*, status.*,
  detail.*, table.* additions, contextMenu.*, queueRow.*) plus `lookup.table.openTitle`/
  `pinAndContinue`.
Changed: gui_next/src/renderer/src/locales/{de,fr,es,it,nl}.json: ran deepl_translate_gui_next.py
  for all new keys, then hand-corrected a handful of single ambiguous words DeepL left as English
  in 4/5 languages (pipeline.buckets.shelf, pipeline.contextMenu.shelve/unshelve) for consistency
  with sibling `pipeline.filter.shelf` wording.

[2026-07-01] — fix(gui): Map screen renders blank — CSP frame-src/origin mismatch (BUG-305)
Fixed: gui_next/src/renderer/src/screens/ScreenMap.tsx:63: MAP_URL hardcoded
  `http://localhost:5174/map` for the live-map iframe src, but index.html's CSP
  frame-src/connect-src/img-src directives only allowlist `http://127.0.0.1:5174`
  (matching window.api.flaskBase, the convention every other screen uses). CSP treats
  localhost and 127.0.0.1 as distinct origins, so the browser silently blocked the
  iframe navigation, leaving the Map screen blank/white. Changed MAP_URL to
  `${window.api.flaskBase}/map`, matching the CSP allowlist and the rest of the app.
Changed: gui_next/src/renderer/src/locales/{en,de,fr,es,nl,it}.json: map.desc text
  updated from "localhost:5174/map" to "127.0.0.1:5174/map" to match the corrected URL.

[2026-07-01] — fix(gui): Library search/filter state survives navigation (BUG-219)
Fixed: gui_next/src/renderer/src/screens/ScreenLibrary.tsx: react-router unmounts ScreenLibrary
  on route change, so the recording-lens (scope/query/activeDecade/activeStatus/activeRating/
  activeSource/activeHealth) and performance-lens (query/activeDecade/activeYear/activeCoverage/
  activeSource/activeRating/perfView, in the PerformanceLensView child component) filter state
  were plain useState and reset to defaults every time the user navigated away and back. Added a
  new module-scope `useLibraryFilterStore` (zustand, no persist middleware — survives route
  changes within a session, not app restarts) and swapped both lenses' filter useState calls for
  it. Store setters mirror React's `Dispatch<SetStateAction<T>>` signature so existing
  `toggleSet()`/`setX(new Set())` call sites needed no changes. View/selection-only state
  (groupByYear, sortKey/sortDir, selectedLb, detailPanelOpen, checkedIds, expandedShows, etc.)
  intentionally left as local useState — out of scope for a search/filter bug. `tsc --noEmit`
  clean for this file (pre-existing unrelated errors remain in other files).

[2026-07-01] — fix(backend): scrape_start now queues gap LB numbers, not just stubs (BUG-220)
Fixed: backend/app.py: scrape_start's gap-fill loop (~line 1816) inserted a `missing`
  placeholder via insert_missing_entry() for every LB number in [start_lb, effective_end]
  with no existing checksums row, but never added those numbers to `lb_numbers`, so
  `_start_scrape_thread` never actually scraped them — including user-typed start_lb/end_lb
  boundaries. Now gap numbers are appended to `lb_numbers` (and the list re-sorted) after
  stubbing, except any gap number whose lb_master.lb_status is 'private' — preserving the
  route's documented private-LB exclusion. Verified with an isolated temp-DB simulation:
  gaps get queued and end up scraped/re-marked, private gaps are skipped, existing
  checksum'd numbers are untouched.

[2026-07-01] — chore(backend): consolidate all log files under data/logs/
Added: backend/paths.py: `LOGS_DIR = DATA_DIR / "logs"`, created by `ensure_data_dirs()`.
Changed: main.py (`losslessbob.log`, `startup.log`), cli.py (`_daemon_log_file()` ->
  `backend.log`), backend/paths.py (`LOG_FILE` -> `scraper.log`) now all write under
  `data/logs/` instead of loose at `data/` root. Existing loose log files at `data/` root
  and stray scratch logs at the repo root / `tools/tapematch/` moved into `data/logs/`
  (filesystem move only — `data/` is already gitignored wholesale, no tracked-file changes).

[2026-07-01] — fix(gui): consolidate LB detail-page URL construction (BUG-221)
Added: gui_next/src/renderer/src/lib/lbUrl.ts: `lbDetailUrl(lb)` — one helper that always
  zero-pads and "LB-"-prefixes an LB number before building the losslessbob.wonderingwhattochoose.com
  detail-page URL.
Fixed: gui_next/src/renderer/src/components/library/DetailPanel.tsx,
  gui_next/src/renderer/src/screens/ScreenLibrary.tsx,
  gui_next/src/renderer/src/components/pipeline/LookupDetail.tsx,
  gui_next/src/renderer/src/screens/ScreenSearch.tsx,
  gui_next/src/renderer/src/screens/ScreenCollection.tsx: 5 call sites each built the
  detail-page URL inline with inconsistent formats — 2 sites interpolated `row.lb` raw
  (404 whenever it wasn't already zero-padded/prefixed). All 5 now call `lbDetailUrl()`;
  DetailPanel/ScreenLibrary pass `row.lbNumber` instead of `row.lb`.
