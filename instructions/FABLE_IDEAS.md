# FABLE_IDEAS — raw idea dump (2026-07-06)

Verbatim capture of a Fable 5 brainstorm, per user request. NOT a spec — an executing
session should expand any chosen idea into a plan first (existing spec-pack docs in
instructions/ show the expected shape). None of these overlap the six existing specs.

---

**1. The Repair Shop (measurements → fixes).** The pipeline now *measures* defects it never acts on: exact speed error (`speed_ppm`, soon ENF-precise), staircase segment boundaries, hum frequency, trim offsets, channel issues. Add an "export corrected copy" action: speed-correct via resample, notch the measured hum and harmonics, apply patch-map composites (§5) into a single best-listenable file with a generated lineage note documenting exactly what was done. No tool in the trading world does measured, documented, reversible restoration. Every piece of analysis you've hardened becomes a repair instruction.

**2. Arrangement evolution explorer.** Dylan is the one artist where this matters most — he rearranges songs beyond recognition. Once the song index exists, compute per-performance features (tempo, key, duration, electric/acoustic band energy) for every performance of a song and cluster them into arrangement eras: "Tangled Up in Blue has 6 distinct arrangements; here's when each lived, here's the best-graded recording of each." Nobody has ever built this; your quality grades make it a *listening guide*, not just a chart.

**3. Listening journal + coverage map.** The app knows the archive but not what you've actually *heard*. Log plays (from the A/B player and any future player affordance), then render coverage: "you've heard 340 of 1,850 circulating shows — 90% of 1966, 4% of the gospel years," with a "next unheard, best-graded show from your weakest era" suggestion. It also quietly produces a personal-taste signal that could someday become another weight in `show_picks`.

**4. Ask the Archive (semantic search).** Descriptions, lineage notes, and (post-ASR-spec) transcripts are a text corpus nobody can currently query except by keyword. Embed it and answer questions like "soundboards from 1981 with complete In the Garden" or "which Supper Club show does carbonbit call the keeper?" — results are LB entries with evidence snippets, never generated prose without a citation. Local embedding model, fully offline, fits the app's philosophy.

**5. Show dossier / liner notes export.** One command renders everything the app knows about a date into a beautiful printable page: setlist with rarities flagged, all circulating sources with family tree and pick ranking, taper credit, quality verdict with artifact snippets, historical context from the scraped data. Export as PDF/HTML for archive folders, trades, or forum posts — every dossier shared on WTRF is quiet advertising for the project.

---

Fable's rank for value: 1 and 2 are the standouts — the Repair Shop converts all the
tapematch hardening work into user-audible payoff, and the arrangement explorer is a
genuinely novel contribution to Dylan scholarship. (Context notes: "§5" in idea 1 refers
to the patch map in FABLE_LISTENING_INSIGHT_IDEAS.md; "ASR-spec" in idea 4 refers to
FABLE_TAPEMATCH_LISTENING_SIGNALS.md §3.)

---

# UI ideas (same session, verbatim)

**1. Command palette (Ctrl+K).** One fuzzy-search box that does everything: type an LB number, a date, a venue, a screen name, or an action ("recompute picks", "check master updates") and jump straight there. For an app whose users think in LB numbers and dates, this collapses most navigation to two keystrokes. It's also the cheapest way to make every future feature reachable without new menu real estate — each spec just registers palette actions.

**2. Timeline as a first-class navigator.** The archive is fundamentally temporal, but browsing is list-shaped. A zoomable horizontal timeline strip (decades → tours → individual nights), with density/color encoding what you hold and how good it is — dark gap for no circulating tape, warm color for high grades. Click to zoom, land in the Library pre-filtered. It doubles as the natural home for the gap list and tonight-in-history features, and it's the first screen that would make a visitor say "whoa."

**3. Side-by-side entry comparison.** Curators constantly compare two LBs — checksums, lineage, ratings, family membership, quality metrics. A "compare" mode (select two rows → split view with differences highlighted, like a diff) turns that from tab-juggling into one glance. Later it becomes the natural shell around the A/B listening player and the pairwise-similarity score.

**4. Unified activity center.** The app runs many long jobs — scrapes, scans, master installs, tapematch syncs, future recompute chains — each with its own per-screen SSE progress today. One persistent tray (bottom corner) listing running/queued/finished jobs with progress, elapsed time, and a click-through to the owning screen. Kill the "did that scan finish?" screen-hopping, and every future spec's SSE endpoint plugs into it for free.

**5. Saved smart views.** Let the user save any Library filter+sort combination as a named view pinned to the sidebar with a live count badge — "Unrated 1978 AUDs (34)", "Superseded copies I still hold (112)". The specs keep adding filter dimensions (picks, tapers, grades, gaps); saved views are how a real person composes them into recurring workflows instead of rebuilding filters every session. Counts that tick down as you work double as a progress tracker.

Fable's rank: 4 and 1 are the quality-of-life multipliers that pay off on every existing
screen today; 2 is the showpiece.

---

# Development-workflow ideas (same session, verbatim)

**1. `/session-open` — the missing mirror of `/session-close`.** Every session cold-starts by re-deriving state: git status, which TODOs are in flight, where calibration stands, what the last session changed. A skill that greps exactly those places (last CHANGELOG entry, open branch diff summary, CALIBRATION_PROGRESS tail, TODO items tagged in-progress) and emits a ~20-line briefing would save that discovery cost every single session — and it's precisely the kind of token conservation you already optimize for. Close writes the state down; open should read it back.

**2. CI on GitHub Actions, backed by a checked-in fixture dataset.** The repo is public but nothing verifies it between sessions. Two pieces that reinforce each other: a tiny golden fixture DB (~100 entries, synthetic checksums, a few families) checked into the repo, and an Actions workflow running `py_compile`, backend unit tests against the fixture, and the `/gui-check` pair (tsc + vite build) on every push. Payoffs beyond safety: Claude sessions can trust CI instead of re-running builds locally, cloud agents (ultrareview, remote workers) can actually exercise the backend without your 2.4 GB of data, and the fixture doubles as the onboarding spec's "new person test" environment.

**3. Verification hooks instead of verification steps.** CLAUDE.md tells every session to remember to run `py_compile` and `/gui-check`. Move the cheap half into PostToolUse hooks (the Cloudflare deploy hook is the pattern): any Edit/Write to `*.py` auto-runs `py_compile` on that file; edits under `gui_next/src` set a flag that `/session-close` checks ("gui changed but gui-check never ran"). Rules that enforce themselves don't consume instruction-following attention — which is exactly what's scarce in cheaper models.

**4. Commit checkpoints, not session-sized diffs.** 2026-07-06 git status showed ~40 modified files uncommitted on `concert-ranker` — one bad `git checkout` or disk hiccup from losing weeks of distinct changes, and impossible for `/code-review` to review meaningfully. Two habit changes: `/session-close` ends with a commit (it already writes the CHANGELOG entry that *is* the commit message), and each spec-implementation stream gets its own branch/worktree so parallel sessions can't tangle. Smaller commits also make `git bisect` usable when a regression surfaces three sessions later.

**5. A work queue that matches tasks to budget.** The user already routes by hand — Fable for specs, Opus/Sonnet for implementation — and ran out of budget mid-week. Make it explicit: a short `QUEUE.md` (task → spec/TODO ref → model tier → rough size) that `/session-close` appends to and each session pulls from the top of. Then push the routine, zero-judgment items — tapematch-batch runs, i18n passes, CHANGELOG archive rotation — to scheduled cloud agents on Haiku/Sonnet overnight, so interactive budget only ever buys judgment, never chores.

Fable's rank: 3 and 4 are the highest value-per-effort (each is under an hour to set up
and pays forever); 2 is the biggest structural upgrade.
