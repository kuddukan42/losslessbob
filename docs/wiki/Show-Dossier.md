# Show Dossier

> Sources: `PROJECT.md` §Show Dossier routes (~line 1982) · `backend/dossier.py` ·
> `backend/dossier_anchors.py` · `backend/dossier_claims.py` · `backend/dossier_fields.py` ·
> `backend/dossier_qc.py` · `backend/templates/dossier.html` · `backend/qc/` ·
> `instructions/SHOW_DOSSIER_REDESIGN_PLAN.md` · `archive/specs/FABLE_SHOW_DOSSIER.md` ·
> Status: fresh 2026-10-18

Answers "which copy of this show should I get, and why" for one date. Original build
TODO-257/260 (2026-07-17); redesign TODO-342 (phases 1–8, rulings A–I closed under
TODO-354) is implemented on `feat/dossier-redesign` — golden-set sign-off (C32) is still
pending. Not yet merged to main.

## Pipeline

`dossier.build_dossier(date, location?, channel, show?, link_mode)` assembles the D1
payload → `dossier_anchors.build_view()` derives the view model (`ANCHORS` registry of
`Field`s, each with value/tier/source/confidence; every anchor degrades to a registered
fallback, never raises) → `dossier_claims.attach_claims()` → `dossier_qc.run_gate()`
writes `dossier["qc"]` and withholds anything failing checks G1–G8.

| Module | Role |
|---|---|
| `dossier.py` | assembly, locator map (`_render_locator_svg`), `filter_dossier_sections`, `render_bbcode` |
| `dossier_fields.py` | track matcher, per-source completeness (D-01), official-release (D-03), stated rigs, venue wiki link |
| `dossier_anchors.py` | view model + fallbacks, `link_mode` (`none`/`inline`/`file`) |
| `dossier_claims.py` | **only** producer of comparative wording ("only", "best", "first"…); returns a Claim only if no nulls/disputes, full scope, ties reported |
| `dossier_qc.py` | per-dossier gate; G1 identity can refuse the whole page |
| `backend/qc/` | corpus QC rules (`/qc-review`), feeds the gate ([Setlist-Sources](Setlist-Sources.md)) |

## Routes (`app.py`)

| Route | Output |
|---|---|
| `GET /api/dossier?date=&location?=&show?=&channel?=` | JSON; HTTP 300 `{ambiguous, candidates}` for a multi-venue date or a same-venue two-show day (`show` = afternoon/evening, TODO-345) |
| `GET /api/dossier/html` | print-first page (`templates/dossier.html`; `dossier_chooser.html` for `chooser=1`); `inline=1` serves in-page, else attachment; adds `sections?`, `local_analysis?=0`, `link_mode?` |
| `GET /api/dossier/bbcode` | `{text}` digest from the same filtered view |

HTML and BBcode return HTTP 422 `{refused, reasons}` when the QC gate refuses.

## Page layout

Recommended copy (pick) · Setlist (with per-source completeness) · Circulating sources
(grouped by TapeMatch family, taper credit; conflicted attributions skipped) · Context ·
Venue (map) · Cross-reference. Rarity flags `only`/`first`/`last`/`rare`.

## Invariants

- Feature-detected: absent source tables drop their section, never null-fake.
- Ambiguity uses distinct `olof_events.venue`, not `entries.location`.
- `public` channel reduces private sources to `{lb, private: true}`; disk paths,
  ownership, friend data, wishlists never appear.

## GUI and tooling

Library `DossierExportModal.tsx` (export) and `ScreenTimeline.tsx` (inline iframe viewer,
`inline=1&chooser=1`). CLIs: `tools/dossier_golden.py` (golden/silver fixtures; `--html`
export), `dossier_sweep.py` (corpus sweep), `dossier_audit.py`, `dossier_acceptance.py`,
`dossier_verify_export.py`. Tests: `tests/test_dossier*.py`. See [Taper-Attribution-Flow](Taper-Attribution-Flow.md).
