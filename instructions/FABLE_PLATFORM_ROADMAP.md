# FABLE_PLATFORM_ROADMAP — data-platform leverage plan (2026-07-15)

Origin: Fable 5 interview/brainstorm session 2026-07-15 ("collector-partner interview").
This is a planning document, not a spec — each workstream below needs its own scoping
pass before implementation. Numbers marked **[verified]** were queried live against
`data/losslessbob.db` on 2026-07-15; re-verify before building on them.

Priority order set by tj: **§1 and §2 first** (both high in TODO priority — filed as
TODO-245 / TODO-246), then the rest roughly in document order. §7 is explicitly parked.

---

## 1. Private LB entries — import Jeff's unpublished metadata (HIGH → TODO-245)

**Problem.** Some LB numbers were assigned by Jeff with full metadata, but the detail
pages were never published to the website — "private" entries, intended for friends
only, not for public www use. Our scraper sees them as 404s, so they sit as blank/
`missing` rows in the DB. Jeff is the sole holder of their metadata; tj holds copies
of *some* of it (received as a friend).

**Verified state (2026-07-15):**
- `site_inventory`: 92 `not_found` URLs total; **62 are `/detail/LB-XXXXX.html` pages**
  — these are the private entries (e.g. LB-00000, LB-09075, LB-09599, LB-10723,
  LB-14093, LB-08893, LB-08894). The other ~30 are site cruft (Word-export
  `filelist.xml`/`themedata.thmx`, help-screen pages).
- `entries`: 15,207 `ok` + 1,446 `missing` rows. The `missing` set is larger than the
  private set — it also contains never-assigned numbering holes. `lb_missing`
  (confirmed non-existent) has only 36 rows. Reconciling these three populations is
  part of the work.

**Work sketch:**
1. Inventory what tj actually holds (files/notes with private-entry metadata); map
   holdings → the 62 private LB numbers. Expect partial coverage.
2. Import path: fill the blank `entries` rows (date, location, description, checksums
   into `checksums`/`entry_files` where held) with a provenance marker
   (`source_type` or new column) saying the data came from private material, not a scrape.
3. **Privacy flag is mandatory**: add a `private` flag (entries and/or `lb_master`) so
   private metadata is excluded from every public-facing surface: the public GitHub repo
   (data/ is local-only, but double-check nothing derived leaks into docs/),
   `docs/schema.html` Cloudflare deploy, archive.org uploads, and any future published
   mirror (§5). Friends-only distribution channels (flat-file releases to known friends,
   §5 snapshots) may include them — decide per-channel at implementation time.
4. Reconcile the three "absent" populations: private (62), confirmed non-existent
   (`lb_missing`, 36), and plain numbering holes — so the DB can distinguish
   "Jeff kept it private" from "never existed".

**Respecting intent:** Jeff deliberately kept these off the www. Import is for local/
friends use only. Nothing private ever lands on a public URL.

---

## 2. Xref audit — semantics + pipeline wiring (HIGH → TODO-246)

**Problem (tj).** The app shows xref badges but they are probably not used correctly,
and xref numbering is not properly wired in the pipeline the way it should be.

**Verified state (2026-07-15):** this is not a corner case —
**70,751 checksums have `xref > 0`, spanning 1,507 distinct LB numbers** (~9% of the
catalog). `checksums.xref` = cross-reference entry (not primary). Current touchpoints:
- Backend: `backend/db.py`, `backend/app.py`, `backend/importer.py`, `backend/flat_file.py`;
  API: `GET /api/checksums/xref_lb_numbers`, `GET /api/checksums/xref_map`.
- GUI (9 files): `lookupStore.ts`, `lookupState.ts`, `LookupDetail.tsx`,
  `ScreenLookup/QuickLookup/Search/Collection/Library`, `library/DetailPanel.tsx`.
- Known historical wobble (PROJECT.md changelog 2026-05-16): the Collection "Xref only"
  filter was changed to match `folder_name LIKE '%xref%'` instead of the master DB xref
  list — a string heuristic where a data lookup existed. Likely emblematic.

**Work sketch:**
1. Write down the *intended* semantics first (what an xref number means on the site,
   how Jeff assigns them, what a folder named `LB-N-xrefXXXX` implies) — one page,
   before touching code.
2. Audit each touchpoint above against that semantics doc; list divergences
   (badge conditions, filters, pipeline lookup/resolve steps, rename logic).
3. Fix wiring so the pipeline resolves xref checksums to their primary LB consistently,
   and badges mean one documented thing everywhere.

---

## 3. Gaps view — "the living Kokay list"

**Idea.** Les Kokay's uncirculated-shows list, as a self-updating view instead of a
document nobody has received in years. Absence made visible.

**Verified first cut (2026-07-15):** Olof mirror gives 4,131 ISO-dated concerts
(`olof_events`, `event_type='concert'`); entries resolve to 3,919 exact dates
(m/d/yy normalized, century pivot ≤26→20xx) + 112 partial `xx` date-strings.
**347 concert dates have no LB entry.** By decade: 1950s 2, 60s 69, 70s 35, 80s 29,
90s 23, 2000s 27, 2010s 82, 2020s 80.

**Known refinements needed:** exclude future/scheduled shows (Olof lists 2026 dates not
yet played); handle the 112 `xx` partial dates (month-level matching); cross-check
`lb_missing`; 1960s coffeehouse events likely never taped (Olof `recording_info` often
says — surface it); extend the modern show universe with bobserve (TODO-228) for 2022+.

**Display concept:** year-by-year timeline grid, every known show a cell, colored by
coverage (has recordings / partial-date only / nothing circulates), click-through to
Olof event detail (venue, tour, recording notes). The per-date drill-down page is the
future home of §6 family trees — build it as a screen with room for a second tab.

---

## 4. Shadow-pile triage — the unresolved downloads

**Problem.** Hundreds of GB of unorganized Dylan-related downloads that don't resolve
to LB (Jeff excluded them as lossy / duplicate / out-of-scope — or they're simply
unknown). Currently invisible to the platform.

**Approach — four existing subsystems pointed at a new directory tree:**
1. Checksum resolve (pipeline) — pass 1, already effectively done ("doesn't resolve").
2. TapeMatch fingerprints vs known families — identifies "same tape as LB-N with a
   haircut" (retracked/retagged/transcoded), which is presumably most of the pile.
3. Spectral quality metrics (concert_ranker plumbing) — automated lossy-source verdict
   replacing "maybe lossy".
4. Gap cross-reference (§3) — surviving folders' dates checked against the gap list.

**Disposition bins (every folder lands in exactly one):**
- (a) same tape as an LB entry → dedupe or keep-as-variant per policy
- (b) lossy-sourced → quarantine, but **log the date first** (a lossy copy of a gap
  date is still the only copy)
- (c) out of scope (non-Dylan etc.) → route out
- (d) real + lossless + unknown to LB → the annex (see §7 for numbering — parked;
  bin (d) items just get inventoried, not numbered, for now)

Triage ≠ organization: hash, fingerprint, date, bin. Manual review only for bin (d),
expected <5% of the pile.

---

## 5. Preservation stack — the Jeff-continuity problem

**Context.** losslessbob.com has had ≥2 extended outages with scarce updates; Jeff is
tired (fewer ratings/comments); he wrote his own site tooling and is presumably the
only person with it. There is no succession plan. tj does not want to be the successor
— the goal is that **the data cannot be lost**.

**Verified state — the mirror already substantially exists:** `site_inventory` tracks
110,938 URLs, **110,846 downloaded with per-body SHA-256**, last refresh 2026-07-14;
`entry_changes` holds 62,984 field-level diffs over 32 scrape sessions (we have the
site's *history*, not just a copy).

**Three gaps to archival grade, in order of cheapness:**
1. **Mirror self-verification** — a pass that re-hashes mirrored files against stored
   `body_sha256` and reports drift/rot. An unverified backup is a hope.
2. **Sealed snapshots, distributed** — dated snapshot + per-file manifest + one seal
   hash over the manifest (BagIt-style); distribute to a few friends on different
   continents (LOCKSS). Patterns already in-house: `flat_file_releases` (release
   mechanics), `friend_collections` (the people). §1's private flag governs contents
   per channel.
3. **Restore test** — static read-only rebuild of the site served from the mirror.
   Proves continuity of *reference* (what friends actually needed during outages).

**Ethics (agreed 2026-07-15):** private dark archive = preservation, unambiguously
right. *Publishing* the mirror is a different act requiring Jeff's blessing. The repo
being public changes nothing here — site data stays local/friends-only.

Three continuities, kept separate: data (solved above), reference (restore test),
curation (the monthly update stream — no tool solves this; out of scope).

---

## 6. Lineage / genealogy — per-family tape trees (follow-on)

**Verdict from the session: more possible than assumed.** Raw material **[verified]**:
- `entry_lineage` already parses directional edges: 461 non-empty `same_as_lb`,
  133 `derived_from_lb` (contains self-reference noise, e.g. LB-604 → [604] — clean
  first), 1,143 `mentions_lb`, 20 `better_than_lb`.
- 8,627 entries have a `source_chain` (`aud > dat > cdr…`) — generation depth hints.
- TapeMatch: 4,535 LBs clustered into families, **749 multi-member families** — the
  "same tape" trunks are already solved.

**Honest limits:** fingerprints prove same-tape, not direction. Direction comes from
text edges + generation counts + the physics check (a child transfer cannot exceed its
parent's signal — `quality_recording_metrics` can test bandwidth ordering). Scope is
**per-date family trees with partial ordering + confidence tiers** for the 749
multi-member families — not an archive-wide grand genealogy.

**Sequencing:** after §3 (inherits the per-date drill-down screen) and ideally after
§4 (fingerprinting the shadow pile enriches family membership).

---

## 7. PARKED — annex numbering / assigning new LB-like numbers

tj, 2026-07-15: building tooling to assign new LB numbers is **not my job and I don't
want a tool for that right now** — written down here for later consideration only.
Context if ever revisited: §4 bin (d) produces verified-real-but-uncatalogued items;
"if Jeff walks away" the community loses the numbering authority; our curator-layer
tables (`lb_alias`, `lb_problems`, `curated_lists`) plus the scraper/DB stack mean the
"only Jeff has tools" objection no longer holds technically. Do not build without an
explicit go.

---

## Cross-references

- TODO-245 (private LB import, §1), TODO-246 (xref audit, §2) — filed 2026-07-15.
- TODO-228 (bobserve setlists) feeds §3's modern show universe.
- TODO-234 (family over-merge review) interacts with §6 — split decisions change trees.
- `instructions/CC_TRADING_PLAN.md` overlaps §5 snapshot distribution (friends channel).
