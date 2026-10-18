# Taper Attribution Flow

> Sources: `archive/specs/FABLE_TAPER_ATTRIBUTION.md` (design spec) ·
> `backend/taper_attribution.py` · `backend/taper_fingerprints.py` · `backend/taper_curation.py` ·
> `backend/taper_review.html` · `backend/taper_curation.html` ·
> `backend/db.py` (`_KNOWN_TAPER_ALIASES`, `_NOT_TAPER`, `_TAPER_UNIVERSE`) ·
> Status: fresh 2026-10-18

Turns raw entry text into a per-LB taper credit with an auditable confidence tier.
Entry point `taper_attribution.recompute()` (CLI: `tools/attribute_tapers.py`).
Routes: PROJECT.md "Taper Attribution" (~line 1992) and `/taper-curation` (~2358);
tables: PROJECT.md `taper_confirmations` (~1270).

## Confidence tiers

| Tier | Source | UI |
|---|---|---|
| confirmed | curator `taper_confirmations` row, explicit `Taper:` label, or series code (`lta`–`ltz`, `net taper a`–`z`) | only tier that renders a pill |
| propagated | inherited across a same-source edge, or a bare handle *mention* (weakest signal) | no pill |
| inferred | Layer 2 vocabulary fingerprints | **disabled** |

Layer 2 is built but `taper_fingerprints.LAYER2_ENABLED = False` (closed won't-ship
2026-07-15): holdout precision didn't transfer to the live pool (profiles latched onto
era/format vocabulary). `recompute()` skips it while the flag is off.

## Layers

- **Layer 0** — direct extraction from `entry_lineage.taper_normalised`, gated by
  `_TAPER_UNIVERSE`.
- **Layer 1** — `_propagate_strong`: union-find over non-flagged `recording_families`
  cliques + `same_as_lb` + `derived_from_lb`, then BFS flood of the one confirmed taper
  to unattributed members (evidence `kind` family/same_as/derived_from, plus `via_lb`).
  A weak pass over review-flagged family edges only fills gaps; it never beats strong.
- Curator `reject` / `unresolved` suppressions are re-applied last, so re-derivation
  cannot resurrect them.

## Rules worth remembering

- **Mention-downgrade**: with exactly one confirmed taper in a component, disagreeing
  bare mentions are dropped; only 2+ *confirmed* tapers set `conflict=1`.
- **Sticky decisions**: `taper_confirmations` (MASTER) is read first; `confirm` wins,
  `reject` suppresses one (lb, taper) pair, `unresolved` suppresses any taper for that lb.
- **Conflict split**: `list_attributions(conflict_kind=...)` separates `mention`
  (hand curation) from `series` (series-vs-series via `_is_series_vs_series` — two real
  tapers on one over-merged family; fix is a TapeMatch family split, TODO-234).
- **Decision log** (TODO-312): `_log_decision()` writes USER-tier `taper_decision_log`
  inside the engine before the upsert; `revert_decision()` replays `prev_action`/`prev_taper`.
  Undoing a first-ever decision drops the derived row and returns `needs_recompute`.

## Wordlists (`backend/db.py`)

- `_KNOWN_TAPER_ALIASES` — alias → canonical map. `_NOT_TAPER` — never seeds an
  attribution: source-type noise (`sbd`, `aud`, `master`…), `dolphinsmile` (curator, not
  taper), `lk`, `captain acid`, `jtt` (TODO-213).
- `user_taper_flags` (TODO-313, USER-tier) overrides `_NOT_TAPER` at runtime, applied after
  the subtraction in `reload_taper_aliases()`, so a local `is_taper` beats the shipped call.
- `_TAPER_UNIVERSE` = aliases − `_NOT_TAPER` ± user flags; also what `is_known_taper()`
  checks, so the UI never shows a taper the engine would reject.

## Curation surfaces (served by Flask, not gui_next)

| Page | Purpose |
|---|---|
| `/taper-review` (`taper_review.html`) | Queue / Entries (faceted, bulk decide, revert) / Tapers rollup / Taper list (`/api/tapers/vocabulary`: alias edit, not-a-taper toggle, merge/rename) |
| `/taper-curation` (`taper_curation.html` + `taper_curation.py`, TODO-327) | One wide row per entry: LB text, parser normalisation, derived attribution, TUIT-declared handle, TapeMatch family, curator decision; `+ vocab` admits names outside the universe |

Workbench reads: `/api/tapers/curation`, `/curation/isolated` (excluded + unknown names;
regex scan cached), `/curation/tapers`. Placeholders (`unknown`, `n/a`) in TUIT fields
count as no tag; barred names never create "sources disagree" rows. Writes reuse the
curator-gated routes, so decisions are logged identically. A vocabulary merge carries
`taper_confirmations` across; derived rows wait for a recompute (`attributions_pending`).

## Related

- [TapeMatch](TapeMatch.md) — `recording_families` origin, family-split leads.
- [Database](Database.md) — `taper_confirmations` is MASTER; `taper_attributions` is USER-tier.
- [Show Dossier](Show-Dossier.md) — consumes taper credit per source.
