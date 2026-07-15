
TODO-244: STRUCTURE_REVIEW P1: regenerate PROJECT.md reference sections from code
Priority: Medium
Status: Open
Added: 2026-07-15
Description: Items 1-8 of instructions/STRUCTURE_REVIEW.md: 88 undocumented Flask routes, 14 undocumented tables, file tree omits gui_next/ + 11 backend modules, stale screens/IPC/port/GUI-conventions sections, stale data/pages refs. Prefer generating routes/schema/tree from code (@app.route decorators, CREATE TABLE statements, disk) so it cannot drift again. Also fold in: item 19 concert_ranker module listing (quality_score.py/text_features.py), item 12 error-shape convention note ({"error": ...} + JSON errorhandler, added 2026-07-15).

TODO-243: Audit 26 renderer fetch sites with silent .catch(() => {}) — keep only on polling loops (STRUCTURE_REVIEW item 15)
Priority: Medium
Status: Open
Added: 2026-07-15
Description: gui_next renderer has 26 fetch calls swallowing errors via .catch(() => {}) (heaviest: ScreenScraper x5, ScreenPipeline x3, ScreenLBDIR x3, ScreenCollection x3). Fine for interval polls, wrong for user-initiated actions which should Toast. Audit each site; keep silent-catch only on polls. See instructions/STRUCTURE_REVIEW.md item 15.

TODO-242: Clarify taper propagation and "Needs review" flags in library view
Priority: Medium
Status: Open
Added: 2026-07-14
Description: Two UI clarity issues discovered in library view (1996 filtered): (1) Taper propagation across families — LB-14922 is tagged "ltf" but links to same_as LB-10678; the library view doesn't clarify whether these should show matching tapers or if the propagation failed. Check recording_families flood-fill logic (backend/taper_attribution.py _propagate_strong) — does it traverse same_as links? If yes, why isn't LB-10678 also showing "ltf"? If no, should it? (2) "Needs review" badge visibility — multiple recordings (LB-07911, LB-16158, Family A, LB-13789, LB-03987, LB-18258, LB-14779, LB-13159) display "Needs review" without clear signal what triggered it. Is it: attribution conflict? quality concern? incomplete metadata (missing venue/tour/notes)? The backend must set this flag somewhere — trace it (likely taper_attributions.conflict=1 or a quality_flag column, or missing venue gazetteer entry). Add a tooltip or legend in the library UI to explain. Related: [TODO-241] (taper curation), [TODO-236] (attribution flowchart), [TODO-234] (series-vs-series conflicts).

TODO-241: Build UI/CLI conduit for taper curation — add/remove from known list without code changes
Priority: Medium
Status: Open
Added: 2026-07-14
Description: Discovered while reviewing library/recording views: several legitimate tapers (cartoonist, 10kat, greeney55, nak300, markp) appear in recording descriptions but do NOT badge as taper attributions because they're missing from backend/db.py _KNOWN_TAPER_ALIASES. Current workflow requires manual code edits to backend/db.py + re-deploy. Build a low-friction curation path: (1) add a /taper-admin page (or extend /taper-review) with controls to add/remove handles from the known list, (2) persist to a .db table (e.g., user_taper_aliases) with approval_flag, (3) export the merged list on backend startup, (4) add a button/endpoint to trigger taper_attribution.recompute() after updates (or schedule overnight). This unblocks rapid taper onboarding (TODO-213 taper curation was manual mention-downgrade; this is handle discovery). Bonus: compare learned handles vs FABLE_TAPER_ATTRIBUTION.md mention-tier rules to flag borderline cases. Related: [TODO-236] (attribution flowchart), [TODO-213] (conflict curation).

TODO-240: Trigger geocoder run_batch once the 2026-07-14 venue resolve batch completes
Priority: Medium
Status: Open
Added: 2026-07-14
Description: Operational follow-up to TODO-223 (closed): a full 'python -m backend.venue_gazetteer resolve' batch was still running at session close 2026-07-14 (652/4071 resolved; per-venue commits, durable, detached). When it finishes, trigger geocoder run_batch (POST /api/geocode/run or CLI) so the ~6,584 un-geocoded entries.location values inherit venue_geocoded pins — mostly zero Nominatim calls via the TODO-223 bite-3 inheritance. Then spot-check /api/map/data marker counts and city_level flags. If the resolve batch died early, re-run it (idempotent: processes source='seeded' remainder only).

TODO-239: Backfill setlist.fm city coords (force re-scrape) to upgrade venue gazetteer anchors
Priority: Medium
Status: Open
Added: 2026-07-14
Description: Discovered during TODO-223 bite 2: setlistfm_shows.city_lat/city_lon/city_state are entirely NULL (0/4131 rows) — the TODO-222 step-1 columns exist but were never populated because the force re-scrape that stores venue.city.coords at scrape time has not run. Consequence: the venue_gazetteer resolution ladder (backend/venue_gazetteer.py) cannot anchor on a stored city coord, so it falls back to a per-city Nominatim geocode (source='city_geocode') and can never use the zero-cost 'setlistfm_city' pin. Action: run POST /api/setlistfm/update {force:true} to backfill, then re-run 'python -m backend.venue_gazetteer resolve --retry-failed' so city-level pins get a chance to upgrade to bounded_venue precision. No code change expected — operational. Verifies TODO-222's backfill claim.

TODO-236: Build a flowchart of the taper attribution process
Priority: Low
Status: Open
Added: 2026-07-14
Description: Document the end-to-end taper attribution pipeline as a flowchart — the path from raw source metadata to a confirmed/inferred taper credit. Cover the layered evidence tiers (Layer 0 mentions, series_code/explicit strong signals, Layer 2 token-profile inferred tier — see TODO-214), the _NOT_TAPER / _KNOWN_TAPER_ALIASES filtering in backend/db.py, the mention-downgrade and strong-wins propagation rules in taper_attribution._propagate_strong, family flood-fill via recording_families, and the conflict-queue outcomes (mention-vs-mention hand-curation vs series-vs-series family over-merge — see TODO-234). Sources: FABLE_TAPER_ATTRIBUTION.md (spec), backend/taper_attribution.py, backend/db.py, and the /taper-review page. Likely a Mermaid diagram in docs/ (consider docs/wiki/ so /wiki-update keeps it fresh). Related: [TODO-213], [TODO-214], [TODO-234].

TODO-235: Persist per-segment staircase lag curves in tapematch runs (unblocks TODO-233 pt2 A/B)
Priority: Medium
Status: Open
Added: 2026-07-14
Description: Prerequisite for TODO-233 part 2 (staircase/splice A/B listening). Investigated 2026-07-14: the staircase per-segment lag curve is computed transiently during a tapematch run and only RENDERED AS TEXT into analysis.md (gen_analysis.py '### <lb> — staircase lag curve'); it is NOT persisted numerically anywhere the backend can read. results.json sources rows carry only summary fields (trim_head_sec, speed_ppm, speed_kind); observations.db sources likewise. anchors_sec in results.json is run-level, not per-source segment offsets. So backend/ab_clips.py cannot build the piecewise perf->source time map staircase A/B needs (unlike constant-speed-offset, which was fully derivable from speed_ppm+trim_head — see TODO-233 pt1, shipped 2026-07-14). Work: (1) in the tapematch engine (tools/tapematch/), persist the per-source staircase lag curve — segment breakpoints + per-segment offset/rate — to results.json and/or a new observations.db sources column (idempotent CREATE/ALTER per CLAUDE.md); this re-runs the frozen calibration pipeline so coordinate with CALIBRATION_PROGRESS.md and re-score the corpus. (2) Then TODO-233 pt2: ab_clips builds a piecewise map, and clip extraction handles a window that straddles a segment boundary (discontinuity) — resample each segment span independently before concat. Note the A/B window is short (~20s) so most picks land inside one segment; the boundary-straddle case is the tricky part. speed-unknown (TODO-233 pt3) remains out of scope (no time mapping exists).

TODO-234: TapeMatch family over-merge review — 22 series-vs-series taper conflicts
Priority: Medium
Status: Open
Added: 2026-07-13
Description: After the TODO-213 taper-attribution curation pass (non-taper credits excluded, robert removed, mention-downgrade rule) the taper_attributions conflict queue dropped to 53, of which 22 are SERIES-vs-SERIES: two *legitimate* taper series (e.g. ltc/ltg, net taper a/net taper i, lta/ntj) attributed to members of one recording_families family, both with strong (series_code/explicit) evidence. These are NOT an attribution bug and NOT a wordlist fix — they indicate the fingerprint/clustering pulled two genuinely different sources into one family (a false-merge). Recurs around prolific series: net taper a (10 merges), ltb (6), ltc/ltg (5). Approach: for each of the 22, pull the family's members + tapematch evidence (observations.db corr / duration / explicit signals for the pair), decide split vs keep; if split, the family_meta review_flag or a family-split path in tapematch is the lever, then re-run taper_attribution.recompute(). Belongs to the tapematch calibration/family subsystem, not backend/db.py taper curation. Query for the 22: SELECT lb_number, evidence_json FROM taper_attributions WHERE conflict=1 — filter to rows whose candidate tokens are all lt[a-z]/net taper [a-z]. Related: [TODO-213].

TODO-204: emb-gated MrMsDTW confirmation probe (near-miss band rescue)
Priority: Low
Status: Open
Added: 2026-07-04
Deferred (2026-07-09): calibration frozen for the 7/09–7/12 window
  (WORK_PACKAGE_2026-07-09 decision 1) — this is the parked breakthrough probe;
  12× embed-cache artifacts retained for it.
Description: The emb near-miss band (both-conventions in [0.55, 0.75)) holds 34 low-corr FN
+ 39 frozen negatives (~73 pairs total) — too mixed to threshold, small enough for expensive
per-pair alignment. Probe: synctoolbox MrMsDTW alignment on band pairs only, then confirm
via residual corr (the trusted zero-FP-risk signal); true same-tape pairs flip, negatives
fail to confirm. Ceiling ≈ +34 TP (+1.6 recall pts). Also targets staircase/heavy-drift
pairs where the anchor/lag aligner fails. Rejected alternatives from the same review
(measured grounds): spectral-ratio stationarity = shipped spec_stationarity, rejected, 4.6%
FN coverage (alignment-gated); Panako-style speed-invariant hashing = wrong failure mode
(fp_triplet fails on same-show COLLISION Δ≈0, not speed; many sources cap at 3-4kHz HF);
htdemucs stem geometry = EQ shifts stems differentially (invariance claim fails) + massive
compute. UNBLOCKED 2026-07-05: TODO-202 densification done (12× REJECTED, 5×/0.75 kept —
net +1 flip only at the plateau edge; see TIER_B_FULLSET_REPORT.md); the near-miss band
stands, and embed_cache_12x/ + fullset_pairs_12x_scores.json are retained as a second
measurement the probe can cross-check band pairs against.

TODO-201: Curator review of census-flagged frozen-set labels (265 pairs)
Priority: Medium
Status: Open
Added: 2026-07-04
Description: fn_label_census.py flags 265/855 (31.0%) of the remaining corr<0.05 frozen FN
with objective label-noise markers (128 explicit "different recording" curator text, 162
speed-corrected duration ratio >15% off unity). These require curator domain judgment (only
the 3 machine-provable negative flips went into regression_set_v2.json). Reviewing them
would re-base the honest recall denominator (~52% at current tp if all confirmed). Use
calibration_audit.html for browsing; census output lists the pairs + evidence snippets.

TODO-195: Backend pipeline step.label strings need i18n key+params, not rendered English
Priority: Low
Status: Open
Added: 2026-07-01
Description: BUG-201's frontend-generated Pipeline UI vocabulary (stage names, step states,
  bucket labels) is now fully translated, but backend/app.py's pipeline step results
  (verify/lookup/lbdir/rename/file `label` and `error`/`error_code` payload fields) still return
  pre-rendered English strings — e.g. "Pass", "Missing 3", "Incomplete match", "Filed to
  Vault_A" — which the frontend displays as-is (see ScreenPipeline.tsx step.label usages and the
  no_checksums/shntool_missing/mismatch paths). Some are static enough for a frontend lookup map
  (done for STATE_LABEL/ERROR_MSG, keyed by stable status/error_code enums), but others embed
  dynamic data (counts, filenames, mount names) baked into the string server-side, which can't be
  cleanly localized without the backend returning a translation key + params instead of a
  finished sentence. Requires backend route changes (pipeline check/lookup/rename/file handlers
  in app.py) plus a frontend mapping layer — deferred out of BUG-201's scope by user decision.

TODO-194: WTRF scraper — improve match quality for remaining needs_review/ambiguous cases
Priority: Medium
Status: Open
Added: 2026-06-30
Description: After BUG-225 (LB-tag mismatch disqualification) and BUG-226 (10s search-delay
  floor) fixed the worst false-positive/false-negative classes, a validated 25-item batch run
  still leaves 9/25 entries genuinely unresolved (not counting clean not_found / date-parse
  failures). Audit results from that run, for use as concrete test cases when refining scoring:

  Ambiguous — real positive-score ties, not just the score=5 floor:
  - LB-16596: top two posts (topic=60197, topic=60199) tied at score=733, both with
    filename_matches=72 equipment_matches=1. This is a hard case — likely two near-identical
    posts for the same show/taper (e.g. original + re-up, or two encodes), so filename overlap
    alone can't break the tie. Needs an additional differentiator: post date, attachment file
    size/count vs checksums table row count, or post age (prefer earliest/most-replied topic).
  - LB-16644: topic=59943 / topic=59965 tied at score=5 (no real signal either side) — genuine
    toss-up, no data to disambiguate from.

  needs_review — single surviving candidate, weak signal:
  - LB-16633, LB-16632: RESOLVED by BUG-227, not a needs_review case — the lone candidate
    (topic=54221) isn't an unmatched pre-app post, it's explicitly labeled "LB-8" in the post
    body with an attached torrent named "LB-00008.torrent" (user-confirmed by inspecting the
    page directly). It documents LB-8, an unrelated entry, not either Del Mar 16000-series
    duplicate. The original score=5/has_torrent-only read was correct about the weak signal but
    missed the tag because the Round 0 regex required 3-5 digits (missed unpadded "LB-8") and
    never scanned attachment filenames at all. Both gaps fixed in backend/wtrf_scraper.py; this
    candidate now hard-disqualifies instead of surfacing as needs_review. The placeholder
    taper_name ("same source recording") idea below may still be worth doing for other entries,
    just not load-bearing for this pair anymore.
  - LB-16614: score=33, equipment_matches=1 + taper_match=mkws — single equipment token plus a
    taper hit still isn't enough to clear the 'medium' bar under _classify_confidence's
    `(eq>=2 and tap) or (fname>=1 and eq>=2)` rule. Worth checking whether 1 equipment token +
    taper match should count as medium.
  - LB-16613, LB-16612: score=21, equipment_matches=2 only (no taper, no filename) — sits right
    at the medium threshold's eq>=2 condition but fails because that branch also requires
    `tap` or `fname>=1`. Worth revisiting whether eq>=2 alone, with no contradicting signal,
    should be enough.
  - LB-16586, LB-16622: score=5, has_torrent only, no other signal — likely genuine not_found;
    the search is matching on date alone with no content confirmation.

  DONE (2026-06-30): Two more disqualification/scoring gaps fixed in backend/wtrf_scraper.py:
  - Download-date window: entries.description's "bittorrent download MM/YY" note (this
    curator's own acquisition date) is now parsed and any candidate post made more than 6
    months before it is hard-disqualified — a post can't be the source of a download that
    predates it. Live-verified: LB-16627's stale 2024-10-14 candidate now filtered while its
    genuine FFP match still downloads; LB-16633/16632's lone candidate disqualified on date too
    (independent of the BUG-227 LB-tag fix above). LB-16586, LB-16622, LB-16613, LB-16612 (the
    has_torrent-only / weak-equipment cases below) should be re-tested against this — some may
    now resolve to a clean not_found (correctly) rather than lingering as needs_review.
  - MD5/SHA1 checksum round added alongside FFP (chk_type 'm'/'s', same 100pt/definitive tier)
    — older SHN-era posts often list raw hashes instead of FFP fingerprints, which were
    previously invisible to scoring entirely.

  Ideas still open, roughly in order of expected payoff:
  1. Tie-breaker for positive-score ambiguous matches (post date / attachment size or count /
     reply count) — currently any tie at any score, even a strong one like 733, is treated
     identically to a zero-signal tie. (Post date is now extracted per-candidate for the
     download-window check above — reuse it here instead of refetching.)
  2. Exclude placeholder taper_name values ("same source recording" and similar) from the
     taper-match round so they don't mask genuinely unmatchable entries as "weak signal"
     when they're actually "no signal available."
  3. Revisit _classify_confidence's medium-tier boundary — eq>=2 alone and (fname>=1 OR
     eq=1)+taper currently don't clear it; check against more real examples before loosening.
  4. Board-page crawl mode (already listed under TODO-193) as a fallback for entries that are
     consistently not_found via search2.
  Relates to: [[TODO-193]] (WTRF torrent fetcher — GUI surface and review flow).

TODO-193: WTRF torrent fetcher — GUI surface and review flow
Priority: Medium
Status: Open
Added: 2026-06-29
Description: backend/wtrf_scraper.py + tools/wtrf_fetch_missing.py implement the
  search/download/qbt pipeline for missing items (see CHANGELOG 2026-06-29d).
  LIVE TESTING (2026-06-30): user ran it against the real WTRF instance — search2
  + scoring confirmed working in most cases. Two real-world failure modes observed:
  'ambiguous' (two posts score identically, no way to auto-pick), and cases where
  the best match wasn't actually the most relevant post. Both already land in
  wtrf_downloads as status='skipped' with confidence 'ambiguous'/'needs_review' for
  manual review — the manual-review action below is what's needed to actually act
  on them; not yet scoped further than that.
  CLI list/range input added 2026-06-30: --lbs flag accepts comma-separated LB
  numbers and/or ranges (e.g. '16640-16650,16700'), mutually exclusive with --lb.
  CLI now also prints the matched topic_url for skipped (needs_review/ambiguous/
  not_found) rows, including both tied URLs on an ambiguous match, so the user can
  manually open and check candidates without a DB query — a stopgap ahead of the
  full GUI review action below.
  REFINEMENT (2026-06-30): root-caused both observed failure modes from a 25-item
  dry run. (1) BUG-225: candidate scoring never checked whether a post body's own
  "LB-NNNNN" tag (embedded by forum_poster.py's metadata header) named a DIFFERENT
  entry, so posts documenting other shows competed on weak date/has_torrent signals
  and won 'ambiguous'/'needs_review' ties — fixed by hard-disqualifying tag
  mismatches in find_torrent_for_lb. (2) BUG-226: search2 queries were spaced only
  delay*1.5 (3.0s at the default --delay 2.0) apart, below WTRF's ~5s search
  flood-control window — likely caused some 'not_found' results to be silently
  throttled empty pages rather than genuine no-match. Fixed by flooring
  search_delay at 10.0s (_SEARCH_DELAY constant). wtrf_downloads rows written
  before this fix should be treated as unreliable, especially 'not_found' rows.
  PAUSED-ADD (2026-06-30): `--paused` CLI flag (backend/qbittorrent.py
  `add_torrent_for_download(paused=...)`) lets `--add-to-qbt` queue matches in
  qBittorrent without starting the download — used for a full batch run against the
  220 missing LB entries above LB-16000 (113 paused-added, 22 downloaded-only, 85
  unmatched; skipped list with candidate links exported to wtrf_skipped_review.md
  for manual review). This covers the "don't auto-download unreviewed matches"
  half of the manual-review action below; the GUI surface to actually review/
  confirm/reject from the app is still open.
  Remaining work:
  - GUI screen or panel to drive the crawl (start/stop, progress, results table)
    that surfaces wtrf_downloads rows with confidence + signals for review.
  - Manual review action for 'needs_review' / 'ambiguous' rows: show the matched
    topic URL so the user can open it and manually confirm/reject before adding
    to qBittorrent (or resuming a paused-added torrent).
  - Board-page crawl mode as an alternative to search2 when SMF search is
    throttled or returns unexpected results (walk board=16.0, board=16.20, …).
  Relates to: [[TODO-135]] (scrape WTRF for existing posts), [[TODO-194]] (match quality
    refinement — audit data from the 2026-06-30 batch runs).

TODO-184: tapematch — rescue same-source false-negatives (channel-polarity inversion + partial overlap)
Priority: Medium
Status: In Progress
Added: 2026-06-24
Description: Across the Jun-22 analysis batch, tapematch repeatedly contradicts LB curator
  "same recording" commentary with near-zero correlation (~37 contradicted vs 3 corroborated
  among verdicts that cite an explicit same-source claim). Root-cause audit:
    - SPEED OFFSET — ALREADY HANDLED. estimate_ratio search is ±30000 ppm, lag-slope
      refine_speed_ratio (config refine.enabled) and the high_ppm secondary_corr_pair path
      were committed 2026-06-21. The opus Winnipeg (1990-06-17) analysis that flagged speed
      as the cause was written 2026-06-20, i.e. before that fix landed.
    - CHANNEL-POLARITY INVERSION — NOT handled. Curator notes like "right channel inverted"
      / "channels swapped and wavs inverted" (e.g. 1991-11-05 LB-10660) defeat correlation
      because Pass 1 ingests MONO ONLY (cli.py:143 mono=True, a deliberate RAM optimisation),
      so the L-R side signal needed to detect a one-channel polarity flip is discarded before
      matching. residual_corr's abs() only catches a WHOLE-signal flip (both channels), not
      one inverted channel, and a pure L<->R swap (no inversion) already survives the L+R
      mixdown. So the unhandled subset is specifically single-channel polarity inversion.
    - PARTIAL OVERLAP / PATCHWORK COMPOSITES — partially handled. secondary_corr_pair's
      windowed-coverage fraction can link a partial match, but whole-recording median corr
      still collapses and the verdict reports needs-review.
  PLAN (staged):
    1. [done] Config-gated polarity block + polarity-aware correlation helper + unit test
       (synthetic inverted-channel pair must be rescued; independent pair must NOT merge).
    2. [done] Wired stereo ingest behind the flag: Pass 1 (cli.py) now decodes stereo when
       polarity.enabled and writes an L-R "side" memmap per stereo source (same trim bounds as
       mid); the residual matrix loop re-scores a near-zero pair (med < rescue_corr_ceiling) via
       match.polarity_rescue (mid-side / side-mid, each with its OWN per-anchor lag lock, speed-
       corrected by the pair ratio), keeps the max, logs POLARITY_RESCUE. _mmap_side helper +
       side_paths dict added; default path is flag-guarded and byte-identical. 6 polarity tests +
       22-test matcher subset green.
    3. [todo] Re-run the ~37 contradicted-claim dates with polarity: true on (validate the
       Pass-1 stereo memory profile on real multi-source dates first); confirm rescues are
       genuine (curator-claimed) and no spurious merges appear; then consider default-on.
    DRY-RUN 2026-06-24 (1991-11-05 Madison, 5 sources, polarity:true via temp config, non-
    destructive — staged symlinks, package CLI direct, no archive/DB write):
      - PLUMBING VALIDATED: all 5 sources decoded stereo + got side memmaps; POLARITY_RESCUE
        fired on 4 eligible pairs. Memory peaked RSS ~2.7 GB (vs ~1.1 GB mono estimate) — the
        resample of BOTH mid and side for high-ppm pairs is the spike; acceptable but real.
      - SAFETY VALIDATED: every off-diagonal stayed ~0.002-0.007 (max 0.0065); rescue nudged
        only 0.002->0.003; n_families 5 == baseline 5. No false merge despite all pairs eligible.
      - NO RESCUE WIN HERE: LB-10660's "channels swapped and wavs inverted" is NOT a whole-
        recording single-channel inversion — the curator match is SEGMENT-level ("same clapping
        wavs at end of d1t1/d1t8/d1t10") inside patchwork composites (LB-09174 is cassette+CD,
        perf trimmed to 4934s). A whole-recording cross-term corr averages over mostly non-
        matching material -> stays near-zero. This date is really the PARTIAL-OVERLAP class.
      - IMPLICATION: partial-overlap/segment matching (clapping-wav level) looks like the bigger
        remaining lever for the contradicted-claim dates than polarity. To demonstrate a polarity
        WIN, pick a date whose curator note is a clean whole-recording "right channel inverted"
        (not segment clapping-wav). Consider a new TODO for segment-level overlap rescue.

TODO-178: Minimized left sidebar — new icon-only nav representation
Priority: Low
Status: Open
Added: 2026-06-22
Description: No collapsed/minimized sidebar mode currently exists in
  gui_next/src/renderer/src/components/AppShell.tsx (Sidebar component, ~lines 120-561) —
  nav items always render icon + label. Implementing "new icons for when left bar is
  minimized" depends on first adding a minimize/collapse toggle for the sidebar, then
  rendering a icon-only nav state (just the Icon, no label, narrower width) using new icon
  assets suited to that compact form.

TODO-177: Implement the new app icon
Priority: Low
Status: Open
Added: 2026-06-22
Description: Replace the app icon with a new design. No icon asset exists yet in the repo
  (gui_next/resources/ only has installer.nsh; no .ico/.icns/.png app icon found) and no new
  asset has been provided yet — needs the actual icon file before implementation, then wire
  it into the Electron build config (gui_next build resources) and installer.

TODO-172: DB Editor — make it more like a real SQL management tool (SSMS-style)
Priority: Low
Status: Open
Added: 2026-06-22
Description: Note: column-header click-to-sort already exists (ScreenDbEditor.tsx:1492-1509,
  with ▲/▼ indicator) — not a gap. Broader ask is to make gui_next/src/renderer/src/screens/
  ScreenDbEditor.tsx feel more like SQL Server Management Studio generally. Candidate
  features to scope out: resizable/reorderable columns, a schema tree sidebar (tables/views
  grouped, expandable to show columns+types), multi-tab query windows (multiple
  SqlQueryPanel instances open at once, ScreenDbEditor.tsx:566), copyable cell/row selection
  in the results grid, query history/favorites, pinned/frozen first column, and per-column
  type-aware cell formatting (dates, booleans, NULL styling) in the rows view.

TODO-166: Collection screen — view/filter folders stored in nonstandard locations (not matching mount routing)
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Add a view or filter on gui_next/src/renderer/src/screens/ScreenCollection.tsx
  to surface my_collection folders whose disk_path doesn't match the expected mount/year
  routing — i.e. _mount_for_path (backend/integrity_monitor.py:115) resolves to a mount
  other than the one upsert_collection_routes (backend/db.py:5057) says that folder's year
  should route to, or resolves to no configured mount at all. Lets the user spot folders
  that drifted to a nonstandard location instead of finding them by accident.

TODO-160: Revamp curator mode — consolidate options and hide existence from normal users
Priority: Medium
Status: Open
Added: 2026-06-22
Description: Curator mode currently exposes itself to every user: AppShell.tsx:400-424 always
  renders a visible "curatorHint" block + "Enable curator mode" link in the sidebar when
  curatorMode is off, so any user can discover and turn it on. The "Curator" nav group
  (AppShell.tsx:78, gated at :226 via `group.gatedGroup && !curatorMode`) and the
  curatorMode/setCuratorMode flag (store.ts:5-17) otherwise work as a simple client-side
  toggle with no real access control. Needs a revamp: (1) consolidate whatever curator-only
  options exist into one coherent settings surface instead of scattering gated items, and
  (2) replace the always-visible hint/link with a hidden trigger (e.g. a secret key
  combo, hidden settings entry, or build-time flag) so normal users have no visible
  indication curator mode exists at all.

TODO-156: Populate all the LB problem entries
Priority: Medium
Status: Open
Added: 2026-06-22
Description: The lb_problems table (backend/db.py:497-503, CRUD in db.py:4803-4894, API at
  app.py:3827+) exists but is not populated for all known problem LB numbers. Need to go
  through known problem cases (e.g. lookup conflicts in BUG-118, verify mismatches in
  BUG-120, reconcile issues in BUG-175) and add corresponding lb_problems rows so they
  surface consistently via get_lb_problem_count()/the lb_problems UI instead of only living
  in BUGS.md.

TODO-155: Improve xref handling
Priority: Medium
Status: Open
Added: 2026-06-22
Description: xref handling needs improvement. Current xref logic lives in the `checksums`
  table (backend/db.py:114, idx_lb_xref0 partial index at :121-122), importer.py:65-164,
  and flat_file.py:362-530 (sync/diff logic comparing xref values between incoming and
  current rows). Lookup-side, the Pipeline Lookup UI surfaces an "Xref" status pill
  (see BUG-201, LookupDetail.tsx STATE_TONE). Specific improvements not yet scoped —
  needs follow-up on what's currently breaking/missing in xref handling before
  implementation.

TODO-136: Post editor form for existing WTRF posts
Priority: Low
Status: Open
Added: 2026-06-10
Description: Add a UI form to edit the subject and body of a WTRF forum topic that was
previously posted through the app (or discovered via TODO-135 scraper). The backend
already has the topic_url stored in forum_posts; use SMF's edit-post endpoint (POST to
index.php?action=post2 with the existing msg ID and sa=useredit or equivalent). The GUI
should surface this as an "Edit post…" action on the forum post history entry for an LB
entry — pre-populate subject/body from a scrape of the existing topic, allow editing in a
textarea, then submit. Depends on TODO-135 for posts not originally made through this app.

TODO-135: Scrape WTRF board for existing LB posts
Priority: Medium
Status: Open
Added: 2026-06-10
Description: Scrape the WTRF SMF board(s) to discover which LB entries already have a forum
topic, regardless of whether they were posted through this app. Parse board index pages
(sorted by date) and individual topic subjects to extract the LB number. Store results in
the existing `forum_posts` table (or a parallel `scraped_posts` table) so the GUI can show
"already posted" status on the Rename/post panel without relying solely on the local log.
Should be runnable on-demand (e.g. "Sync from WTRF" button) and optionally on startup.
Credentials already managed by credentials.py; HTTP session logic already in forum_poster.py.

TODO-107: Disk Scanner — find audio folders on disk for bulk collection add
Priority: Medium
Status: Open
Added: 2026-06-03
Description: Add a Disk Scanner screen that walks user-defined root paths (e.g. /mnt/nas,
  /home/user/music) using os.scandir() with early pruning, finds all directories containing
  lossless audio files (FLAC, WAV, APE, ALAC, AIFF), and presents them as candidates to
  add to the collection DB.

  Backend:
  - POST /api/scanner/scan — accepts {"roots": [...], "extensions": [...]}; walks each root
    with os.scandir(), skips hidden dirs and a configurable exclude list (system paths,
    node_modules, .git, etc.); returns list of {path, file_count, extensions, in_collection}
    where in_collection is True if the path already exists in lbdir.
  - Scan runs in a background thread; streams progress via SSE or returns a job ID to poll.
  - No persistent index — one-shot on demand. plocate can be used as an optional fast-path
    if installed (locate -r '\.flac$' | dirname | sort -u).

  GUI (new ScreenScanner.tsx):
  - Left panel: editable list of root paths to scan + exclude patterns; Scan button.
  - Right panel: results table — path, file count, extensions found, "In Collection" badge.
  - Checkboxes for bulk selection; "Add Selected to Collection" button calls existing
    LBDIR add logic.
  - Progress bar / spinner during scan; cancel button to abort background job.
  - Already-in-collection rows shown but greyed out so user can see full picture.

---

TODO-106: Trading — multi-friend batch compare
Priority: Low
Status: Open
Added: 2026-05-30
Description: Extend the Trading screen to compare your collection against multiple friends at
  once — show a matrix view (friends × shows) so you can find the best candidate to trade
  any given recording with. Also: add a GET /api/trading/friends/<id>/entries route so the
  GUI can retrieve raw friend entries without going through the compare diff endpoint.

---

---

TODO-085: Map tab — sequential date-linked travel view across the globe
Priority: Low
Status: Open
Added: 2026-05-21
Description: Add a new sub-view (or toggle) on the Map tab that renders concert locations
  as a chronological travel trail — polylines (or an animated path) connecting each
  geocoded entry to the next in date order, visualising movement across the globe over
  the years. Current map just plots pins with no temporal linkage.
  Design considerations:
    • Sort geocoded entries by date_str ascending; skip entries with no lat/lon.
    • Draw a Leaflet polyline (or GeoJSON LineString) through the ordered coordinates.
    • Optionally colour-code segments by decade so different eras are visually distinct.
    • Consider a play/scrub slider to animate the route year-by-year.
    • Hook into the existing MapTab _open_filtered_map() or add a separate "Travel view"
      button that generates a different HTML payload from the /api/map endpoint.
    • Cluster of same-venue returns (same lat/lon) should be shown as a loop or ignored
      to keep the line readable.

---

---

