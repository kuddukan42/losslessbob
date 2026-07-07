# Spec Pack Integration Notes

Author: Fable 5, 2026-07-06. Cross-review of the four specs in `instructions/`
(FABLE_TAPER_ATTRIBUTION, FABLE_UNIFIED_RANKING, FABLE_LISTENING_INSIGHT_IDEAS,
FABLE_ONBOARDING_SYNC). **Read this before implementing any of them.** Each finding
says which spec(s) it amends; the specs themselves are unchanged.

---

## 1. Findings that amend the specs

### F1 — Derived tables are empty after onboarding (amends ONBOARDING + RANKING)

Verified: `entry_lineage` is NOT in `MASTER_TABLES` (backend/db.py:37), and
`show_picks` / `taper_attributions`(non-confirmed) / `song_performances` are
derived-by-design. A fresh install via the onboarding wizard gets entries, families,
and curated lists from master — but **zero lineage, zero attributions, zero picks**,
so the recommended-★, supersession scoring, and taper pills silently don't exist for
new users.

Also verified: `tools/parse_lineage.py` reads only `entries.description` (already in
master), so everything IS regenerable client-side. Fix is one addition to the
onboarding spec:

> **Wizard "Done" step (or first checklist completion) triggers the derived-recompute
> chain: `parse_lineage` → `attribute_tapers` → `compute_show_picks`** (each skipped
> gracefully if its module doesn't exist yet). Expose as one backend endpoint, e.g.
> `POST /api/derived/recompute` (SSE, sequential), so Setup can also offer a
> "Recompute derived data" button — the same button curators press after rating/list
> changes. This replaces the ranking spec's standalone `POST /api/picks/recompute`
> (build the chained endpoint instead; per-step CLIs remain the primary interface).

### F2 — `taper_attributions` as MASTER-tier is inconsistent as specced (amends TAPER)

The table mixes curated rows (`confirmed`, sticky) with recomputable rows
(`propagated`/`inferred`) — exporting the latter in master contradicts the ranking
spec's own principle (derived = USER-tier) and bloats master with rows any install
can regenerate (F1). Two amendments:

1. **Master-export only curator knowledge**: rows `WHERE confirmed_at IS NOT NULL`,
   plus the **entire `taper_attribution_rejects` table** — the spec forgot rejects,
   and without them every other install's recompute resurrects what the curator
   rejected. Simplest compliant implementation: keep `taper_attributions` USER-tier,
   add a small MASTER-tier `taper_confirmations(lb_number, taper_normalised,
   action 'confirm'|'reject', decided_at)` that the recompute reads first. This keeps
   the wholesale-replace import semantics of MASTER_TABLES safe (a master import can
   never clobber locally-computed propagation).
2. Check `MASTER_TABLES` import (db.py:4790 wholesale-replaces per table) before
   choosing option 1-vs-splitting; the split table (option above) is recommended
   precisely because wholesale replace + partially-derived table = lost local rows.

### F3 — Evidence JSON: adopt one shape now (amends TAPER + RANKING, helps LISTENING)

Taper spec: `{kind, detail, via_lb, fam_id, score}`. Ranking spec:
`{kind, detail, points}`. Converge before either lands:

> Common core `{kind: str, detail: str}` + optional extras (`points`, `score`,
> `via_lb`, `fam_id`). `kind` stays free-text (no CHECK constraint) — listening §8
> already plans a future `"geography"` kind.

Then gui_next builds **one `EvidenceList` component** (plain rows, per ranking §6
style) reused by: taper DetailPanel evidence, picks DetailPanel evidence, and later
listening features. Whoever ships UI first builds it; the other reuses it.

### F4 — Library payload + DetailPanel are shared surfaces (sequencing rule)

Three specs extend the same two places:

- **Library bulk payload** (flat fields, no N+1 — tapematch-families precedent):
  ranking adds `pick_rank`/`abs_grade`/curated flags; taper adds confirmed-taper;
  listening §1 could add pair info later. Rule: **ranking phase 3 defines the
  payload-extension pattern; taper phase 2 follows it.**
- **DetailPanel**: taper evidence, picks evidence, §1 matrix, §5 timeline, §6 gallery
  all want space. Rule: first UI session introduces **collapsible sections** in
  DetailPanel; every later spec adds a section, never inline content. Listening §1/§5
  should prefer the TapeMatch screen (TODO-170) when it exists.

### F5 — Shared freshness precondition (amends TAPER + RANKING)

Both consume `entry_lineage` (taper: same_as/derived_from edges + Layer 0; ranking:
better_than/derived_from scoring). Both CLIs must start by checking/refreshing
lineage staleness (parse_lineage is incremental via `text_hash` — cheap). The F1
chained endpoint encodes the canonical order:
**parse_lineage → attribute_tapers → compute_show_picks** (attribution before picks
so ranking term 6 sees fresh attributions; term is feature-detected, so order is an
optimization, not a hard dependency).

### F6 — `derived_from` semantics differ by design (no code sharing)

Taper: child inherits parent's taper (remaster still = original taper). Ranking:
child penalized −4 vs parent unless higher-rated. Both correct, intentionally
different — **do not** extract a shared "lineage graph" module; each builds its own
small traversal. Noting it here so a Sonnet session doesn't "helpfully" unify them.

## 2. Recommended cross-spec implementation order

| # | Session | Why here |
|---|---|---|
| 1 | RANKING phase 1 (LB_KNOWLEDGE.md) | Prerequisite doc. **May already exist** — `concert_ranker/LB_KNOWLEDGE.md` is untracked on the current branch; verify completeness against TODO-187 before rewriting. |
| 2 | TAPER phase 1 (schema + L0 + L1 + CLI) | Backend-only harvest; lets picks term 6 be live from its first compute. Apply F2 + F3 + F5. |
| 3 | RANKING phase 2 (picks.py + CLI + show_picks) | Apply F3 + F5; build the F1 chained recompute endpoint here (it owns the chain's tail). |
| 4 | RANKING phases 3–4 (API + Library payload + badges/filters + EvidenceList) | Defines F4 patterns. Closes TODO-186/181-UI. |
| 5 | TAPER phase 2 (confirm/reject API + pill + filter + DetailPanel) | Reuses F4 payload pattern + F3 EvidenceList. Closes TODO-173/192. |
| 6 | LISTENING §1 (pairs sync) + §9 (tonight card) | §9 consumes show_picks (now populated); §1 seeds TODO-170. |
| 7 | ONBOARDING P1→P3 | With F1 amendment; by now the recompute chain exists to call. Master release published after step 5 includes taper confirmations. |
| 8 | ONBOARDING P4 (README) + LISTENING §3 onward | Per the listening spec's own ordering. |
| — | TAPER phase 3 (fingerprints), LISTENING §8 | Only after 5; §8 also needs TODO-167. |

Steps 1–3 are backend-only and can share sessions if budget allows; 4 and 5 each end
with `/gui-next-i18n` + `/gui-check` + `/session-close`.

## 3. Bookkeeping consolidations (do at the relevant session-close)

- TODO-182: close with pointer to RANKING §5 (WTRF-thread-as-curated-list decision).
- TODO-192 badge: implemented inside TAPER phase 2 — don't schedule separately.
- TODO-181 remainder (curated-lists API/UI): lands in RANKING phases 3–4.
- ONBOARDING allocates new TODO IDs at its first session (spec header says so).
- New tables to document in PROJECT.md schema section as they land:
  `taper_attributions` (+ confirmations, per F2), `show_picks`, `tapematch_pairs`,
  `song_performances`, `show_gaps`.
