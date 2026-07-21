# Taper Attribution Engine — Design Spec

> **✅ CLOSED — 2026-07-15. DO NOT treat as open work.** Phases 1–2 shipped
> 2026-07-09 (`7a304abf` schema/L0/L1/CLI, `947845bd` confirm-reject API + Library
> pill + DetailPanel). Phase 3 (Layer-2 fingerprints, TODO-214) built + calibrated
> but **gated OFF** by decision — `backend/taper_fingerprints.py:72 LAYER2_ENABLED=False`
> (precision didn't transfer past era/format confounds); revisit paths in
> WORK_PACKAGE_2026-07-14.md Session 6. Live tables: `taper_attributions`,
> `taper_confirmations`. Only residual work is TODO-234 (curator conflict-review
> queue this engine generates) — a curator decision, not a build task.

Spec author: Fable 5, 2026-07-06. Execution target: Sonnet session(s).
Consolidates and extends TODO-173 (confirmed taper tag). Feeds FABLE_UNIFIED_RANKING.md.

---

## 1. Problem

`entries.taper_name` (backend/db.py:143) is a best-guess parse from free text via
`extract_taper_and_source()` (db.py:753+). It has no confidence model, no curation, and
nothing gates display. TODO-173's philosophy is explicit: **only show a taper tag when
confirmed**. Meanwhile most attributable entries carry *indirect* evidence that the parser
cannot use today:

- TapeMatch proved thousands of same-source relationships (`recording_families`) — if any
  member of a family has a confirmed taper, **every member has that taper**.
- `entry_lineage` already extracts cross-LB claims (`same_as_lb`, `derived_from_lb`) —
  another same-source edge set.
- Descriptions of a taper's known recordings share vocabulary (gear, phrasing, locations)
  that can fingerprint unattributed entries.

Goal: an attribution engine that turns these into per-LB taper designations with an
explicit confidence tier, a curator confirmation workflow, and evidence you can audit.

## 2. Existing infrastructure (do not rebuild)

| Piece | Where | Use as |
|---|---|---|
| Known-taper alias map | `_KNOWN_TAPER_ALIASES` (db.py:1120), `_KNOWN_TAPER_KEYS_SORTED` (db.py:1305) | canonical name universe + normalisation |
| Text extractor | `extract_taper_and_source()` (db.py:779) | Layer-0 evidence source, unchanged |
| Parsed lineage | `entry_lineage` table (db.py:709; PROJECT.md "entry_lineage" section); populated by `tools/parse_lineage.py` | same-source edges + existing `taper_normalised` |
| Same-source families | `recording_families` / `tapematch_family_meta` (PROJECT.md §tables), synced by `backend/tapematch_sync.py` | propagation graph |
| Heuristic per-entry taper | `entries.taper_name` | display fallback only; never treated as confirmed |

**Caveat carried from curation history:** `dolphinsmile` appears in older taper lists but
is an uploader, **not** a taper. Exclude him from the alias universe used for attribution
(text mentioning him is uploader credit, not taper evidence).

## 3. Data model

New table `taper_attributions`. Tier decision: **MASTER** — attributions are curated
knowledge worth exporting, like `lb_alias`. (If the curator disagrees at implementation
time, USER-tier is a one-line change; everything else is identical.) Follow the existing
idempotent `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` in try/except convention.

```sql
CREATE TABLE IF NOT EXISTS taper_attributions (
    lb_number         INTEGER PRIMARY KEY,
    taper_normalised  TEXT NOT NULL,      -- canonical key into _KNOWN_TAPER_ALIASES values
    confidence        TEXT NOT NULL,      -- 'confirmed' / 'propagated' / 'inferred'
    evidence_json     TEXT NOT NULL,      -- list of evidence records, see §4
    conflict          INTEGER NOT NULL DEFAULT 0,  -- 1 = contradictory evidence, needs review
    confirmed_at      TIMESTAMP,          -- set only when curator confirms
    computed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_taper_attr_name ON taper_attributions(taper_normalised);
CREATE INDEX IF NOT EXISTS idx_taper_attr_conf ON taper_attributions(confidence);
```

Confidence tiers:
- **confirmed** — curator-approved, or direct explicit `Taper:` label matching a known
  alias (Layer 0 with `parse_confidence='high'`). Only this tier renders a UI pill (TODO-173).
- **propagated** — inherited through same-source edges from a confirmed member (§4.2).
  One curator click away from confirmed; surfaced in a review queue.
- **inferred** — vocabulary-fingerprint match (§4.3). Review queue only, never auto-promoted.

Evidence record shape (one list entry per signal):
`{"kind": "explicit|family|same_as|derived_from|series_code|fingerprint",
  "detail": "...", "via_lb": <int|null>, "fam_id": "<str|null>", "score": <float|null>}`

## 4. Attribution layers (run in this order)

### 4.0 Layer 0 — direct extraction (exists)
Re-run `tools/parse_lineage.py` so `entry_lineage` is fresh. Seed `taper_attributions`
with rows where `entry_lineage.taper_normalised` maps to a known alias:
- explicit `Taper:` label match → `confirmed` (this is the site curator's own text)
- bare handle mention elsewhere in the description → `propagated` (mentions are weaker:
  "thanks to spot" ≠ "taped by spot"); include the snippet in evidence.
- Series codes (lta–ltz, nta–ntz) → `confirmed` with `kind:"series_code"`.

### 4.1 Build the same-source graph
Undirected edges over lb_numbers, union of:
- `recording_families` membership (same `fam_id` ⇒ clique), carrying `tapematch_family_meta.conf`
  and respecting `review_flag` (edges from review-flagged dates get weight "weak");
- `entry_lineage.same_as_lb` (bidirectional);
- `entry_lineage.derived_from_lb` (directed parent→child; child inherits parent's taper —
  a remaster of spot's tape is still spot's recording).

### 4.2 Layer 1 — propagation (the high-precision win)
Fixed-point iteration: any node with tier `confirmed` pushes its taper to connected nodes
lacking an attribution, as tier `propagated` (evidence: `kind:"family"|"same_as"|"derived_from"`,
`via_lb`, `fam_id`). Iterate until no change (propagated nodes push too, but tier never
upgrades by distance — everything reached is `propagated`).

**Conflicts:** if a component contains two different confirmed tapers, do NOT propagate
into the contested region; set `conflict=1` on all nodes of that component that would have
received contradictory pushes, keep the confirmed rows untouched, and list both candidates
in evidence. A conflict either means a wrong family/edge or a wrong attribution — both are
exactly what the curator wants surfaced. Weak edges (review-flagged tapematch dates) lose
to strong edges instead of raising a conflict.

### 4.3 Layer 2 — vocabulary fingerprints (lower precision, gated)
For each taper with ≥ ~8 attributed entries (confirmed+propagated), build a token profile
from those entries' descriptions: informative tokens only (gear models — "schoeps",
"neumann", "csb", "nak", recorder names, characteristic phrases), scored by weighted
log-odds vs the corpus of all other descriptions. Score every *unattributed* entry against
every profile; a match above threshold (tune so precision beats recall — start where
spot-checks show ≥ ~90% precision on held-out confirmed entries) writes an `inferred` row
with the matched tokens in evidence. Never let Layer-2 output feed back into Layer-1
propagation. Implementation: stdlib + collections; no new deps needed.

### 4.4 Idempotency & refresh
Single entry point `tools/attribute_tapers.py` (CLI, mirrors `parse_lineage.py` style):
recompute layers 1–2 wholesale on each run, but **never overwrite** rows with
`confirmed_at` set (curator decisions are sticky). Log a one-line summary per tier.

## 5. Curator workflow + API + UI

- `GET /api/tapers/attributions?confidence=&taper=&conflict=1` — list with evidence.
- `POST /api/tapers/attributions/<lb>/confirm` and `/reject` (curator-gated, like other
  curator routes). Reject deletes the row and records the lb in a small suppression table
  (`taper_attribution_rejects(lb_number, taper_normalised, rejected_at)`) so recompute
  doesn't resurrect it.
- Library UI (gui_next): taper pill on entry rows **only for `confirmed`** — this is also
  TODO-192's badge, so implement them together. DetailPanel: show tier + evidence for any
  attribution, with confirm/reject buttons in curator mode (TODO-160 conventions).
- Review queue: simplest viable = a Library filter "taper: needs review"
  (propagated/inferred/conflict) rather than a new screen.

## 6. Phases (each independently shippable)

1. **Schema + Layer 0 + Layer 1 + CLI.** The propagation harvest. Report: attributions
   per tier, conflict count, top tapers by entry count.
2. **API + confirm/reject + Library pill & filter + DetailPanel evidence.** i18n via
   `/gui-next-i18n`; verify with `/gui-check`.
3. **Layer 2 fingerprints.** Only after phase 2 exists to review its output; calibrate
   threshold against confirmed entries held out from profile building.

## 7. Acceptance criteria

- Re-running the CLI twice produces identical tables (idempotent); confirmed rows survive.
- No pill in the UI for anything below `confirmed`.
- Every attribution row's evidence_json reconstructs *why* without reading code.
- Conflict components are visible via API/filter, not silently resolved.
- Spot-check: pick 10 famous same-source families with a known taper; propagation must
  cover the family and nothing outside it.

## 8. Out of scope

Attributing tapers not in the known-alias universe (new-taper discovery), editing the
alias list from the UI, and any WTRF scraping for taper claims (possible later evidence
layer; leave a `kind` value free for it).
