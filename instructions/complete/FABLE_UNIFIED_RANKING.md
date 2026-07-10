# Unified "Best of Show" Ranking — Design Spec

Spec author: Fable 5, 2026-07-06. Execution target: Sonnet session(s).
Consolidates TODO-181 (curated lists — remaining API/UI), TODO-182 (community pick —
decision recorded below), TODO-183 (Concert Ranker — done, consumed here), TODO-186
(badges + filter views), TODO-187 (rating philosophy doc — prerequisite reading).
Companion spec: FABLE_TAPER_ATTRIBUTION.md (optional signal, graceful when absent).

---

## 1. Problem

Four TODOs circle one question the app can't currently answer: **"which LB should I
listen to for this date?"** The ingredients all exist but live in silos:

| Signal | Where it lives today | Status |
|---|---|---|
| LB curator rating (A+..F / 0–5) | `entries.rating` | authoritative, semantics in TODO-187 |
| Absolute audio quality 0–100 + grade | `quality_recording_scores.abs_score/abs_grade` (owned+scanned copies only) | done (TODO-183, AUD ρ=0.66) |
| Best transfer within a family | `quality_recording_scores.rank_in_family`, `vetoed` | done (`concert_ranker/families.py`) |
| Curated picks | `curated_lists` + `curated_list_entries` (carbonbit 4,503; 10haaf 7,572) | imported; **no API/UI yet** |
| Cross-LB supersession claims | `entry_lineage.better_than_lb`, `derived_from_lb`, `same_as_lb` | populated |
| Same-source families | `recording_families` / `tapematch_family_meta` | synced |
| Confirmed taper | `taper_attributions` (companion spec) | future/optional |

Goal: one derived per-date pick model with an auditable evidence trail, surfaced in the
Library as badges + filters + a per-date "recommended" marker.

## 2. Design principles

- **Derived, recomputable, USER-tier.** Like `quality_recording_scores`: rewritten
  wholesale, never hand-edited, never exported in master.
- **Evidence over magic.** Every pick carries an evidence list; the UI can always answer
  "why this one?". Mirror `verdict_text` style from the ranker.
- **Graceful degradation.** Most dates have zero scanned copies (metrics only exist for
  owned recordings). The model must produce sane picks from ratings + curated lists +
  lineage alone, and get sharper when audio metrics exist — never require them.
- **The LB curator's rating is the anchor.** Per TODO-187 semantics it is the most
  trustworthy single signal; everything else adjusts around it, ±1-tier drift caveats noted.

## 3. Data model

```sql
CREATE TABLE IF NOT EXISTS show_picks (
    concert_date   TEXT NOT NULL,
    lb_number      INTEGER NOT NULL,
    pick_score     REAL NOT NULL,        -- comparable within a date only
    pick_rank      INTEGER NOT NULL,     -- 1 = recommended for the date
    evidence_json  TEXT NOT NULL,        -- ordered list of {kind, detail, points}
    computed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (concert_date, lb_number)
);
CREATE INDEX IF NOT EXISTS idx_show_picks_lb ON show_picks(lb_number);
```

Idempotent creation per repo SQLite rules. Recomputed by a single CLI entry point
`tools/compute_show_picks.py` (+ `POST /api/picks/recompute`, manual trigger like
tapematch sync — not at startup).

## 4. Scoring model (v1: transparent points, not ML)

Deliberately a hand-weighted linear points model — auditable, tweakable in one config
dict (`PICK_WEIGHTS` in the new module), and the evidence list doubles as the score
derivation. Resist the urge to train anything; there is no ground truth to train on, and
the ranker already did the ML where labels existed.

Per candidate LB on a date, sum:

1. **Rating base** (dominant term): map `entries.rating` via the ranker's existing
   `RATING_RANK` (`concert_ranker/calibrate.py:27`) to a 0–100 base. Missing rating →
   neutral 40 with evidence `"unrated"`.
2. **Curated pick bonus**: +8 per list that includes the LB (carbonbit, 10haaf —
   independent picks agreeing is strong), evidence names the list. Weight per-list in
   config so future lists (or a TODO-182 community list) slot in.
3. **Supersession**: for each `better_than_lb` claim: +6 to the claimer, −6 to the
   claimed-against **when both are on this date** (claims are directional and rare —
   trust them). `derived_from_lb`: child gets −4 vs its parent unless the child carries a
   higher rating (a superior remaster earns its keep via signals, not lineage).
4. **Family dedup / best-transfer**: within a `recording_families` family, the member
   with `rank_in_family=1` (latest scan) gets +5; other members get −3 (same performance,
   inferior transfer). `vetoed=1` → hard −25 (lossy-sourced etc. should not win a date).
   EAC-match note from TODO-187 §6: if description matches "exact/close eac match",
   treat as −10 ("offers nothing new") — cheap regex, big precision.
5. **Audio quality adjustment** (only when scanned): blend `abs_score` in at 25% weight
   *relative to the rating base* (`0.25 * (abs_score − rating_base)`), clamped ±10. The
   scanner refines, never overrules, the curator.
6. **Taper reputation** (only if `taper_attributions` exists — feature-detect the table):
   confirmed taper whose median entry rating is high (e.g. mike millard tier) → +3.
   Skip silently when absent.

`pick_rank` orders by score within the date; ties break toward lower LB number (older
entry = the circulating standard). Dates with one candidate still get a row
(rank 1, evidence `"only circulating copy"`) so the UI code has no special case.

## 5. TODO-182 decision (record it, defer it)

Real cross-user voting needs shared infrastructure this local-first app doesn't have.
**Decision: the WTRF-sticky-thread variant is the right shape** — a scraped/parsed
"best of" thread becomes just another curated list in `curated_lists` with its own
weight in term 2. No new architecture, no new table. Out of scope for v1; when wanted,
it is a scraper task, not a ranking task. Close TODO-182 in favor of this paragraph.

## 6. API + UI

- `GET /api/picks?date=` → picks for a date with evidence; `GET /api/picks/for/<lb>` →
  that LB's rank on its date. Bulk shape for the Library grid: extend the existing
  library payload with `pick_rank` + `abs_grade` + curated-list flags rather than N+1
  calls (follow how tapematch family data was exposed flat).
- `GET /api/curated_lists` (+ curator-gated POST/DELETE) — this is the explicitly
  deferred remainder of TODO-181; build it here.
- Library screen (gui_next `ScreenLibrary.tsx`, filter sets around line 336):
  - **Badges** (TODO-186): quality grade pill (`abs_grade`, owned+scanned only),
    curated-pick badge per list, ★ marker on `pick_rank=1` rows.
  - **Filters**: "carbonbit's picks", "10haaf's picks", "recommended per date",
    "superseded" (rank>1 owned copies — doubles as a collection-pruning view).
  - DetailPanel: evidence list rendered as plain rows ("LB rating A− · +85",
    "carbonbit pick · +8", "better transfer exists: LB-1234 · −3").
- i18n for all new strings via `/gui-next-i18n`; verify with `/gui-check`. No screenshots.

## 7. Phases

1. **TODO-187 knowledge doc first** (`concert_ranker/LB_KNOWLEDGE.md`) — the rating
   semantics anchor the weights; TODO-187's description already contains the full outline,
   so this is transcription, not research.
2. **Scoring module + CLI + `show_picks`** (`concert_ranker/picks.py` — it consumes
   ranker output and belongs in that package). Unit tests: one date fixture per term of
   §4, plus the degraded no-metrics case. Report score distribution + top-10 upsets
   (pick ≠ highest-rated) for eyeball validation.
3. **API routes + Library payload extension.**
4. **Badges + filters + DetailPanel evidence** (closes TODO-186 and TODO-181's UI half).

## 8. Acceptance criteria

- A date with no scanned copies, no curated picks, and no lineage still yields a pick
  (highest rating wins) with truthful evidence.
- For 10 well-known shows with a famous "the" source, `pick_rank=1` matches consensus —
  where it doesn't, the evidence list must show *why* the model disagreed (that's a
  weight-tuning session, not a bug).
- Recompute is idempotent and fast enough to run after any rating/list/scan change
  (target: full DB < 30 s; it's per-date arithmetic over indexed reads).
- No UI regression when `show_picks` is empty (pre-first-run).

## 9. Out of scope

Training a learned pick model; cross-user voting infrastructure (§5); auto-downloading
recommended copies (compose later with the WTRF fetcher, TODO-193/194); re-ranking
inside tapematch itself.
