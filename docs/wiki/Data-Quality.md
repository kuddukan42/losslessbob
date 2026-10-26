# Data Quality

> Sources: `PROJECT.md` §`qc_findings` … `corrections` (~line 1468), §`/api/qc/*` routes
> (grep `/api/qc/summary`) · `backend/qc/` · `backend/qc_review.html` · `backend/dossier_qc.py` ·
> `tools/dossier_sweep.py` · `tools/dossier_acceptance.py` · `tools/dossier_golden.py` ·
> `archive/specs/SHOW_DOSSIER_REDESIGN_PLAN.md` (Phase 2/2b/8) · Status: seeded 2026-10-25

Built for the Show Dossier redesign (TODO-342) but corpus-wide: a rule engine finds bad rows in
the parsed and derived data, a curator console decides them, and the dossier's QC gate withholds
or refuses anything resting on an open error. Guiding rule: when a value can't be verified, the
page shows the field's fallback and lists it as withheld — it never guesses.

## Corpus rules (`backend/qc/`)

`rules.py` holds `RULES` — pure `(conn) -> Iterable[Finding]` functions; add a rule = a function
plus a `RULES` entry (tests in `tests/test_qc*.py`). `store.run_rule()` reconciles each run
against `qc_findings` (one row per rule × entity) under the decision vocabulary:
`open → confirmed | false_positive | corrected | fixed`; a changed `evidence_hash` reopens a
dismissal. Run: `.venv/bin/python3 -m backend.qc run`.

| Family | Rules | Checks |
|---|---|---|
| Olof parse | R-O1…R-O4 | parsed vs raw song counts, city/country, stray annotations, setlist disputed by ≥2 sources |
| Geocode / entries | R-G1, R-E1, R-E2 | venue POI mismatch, field ranges, tracklist fits <20% of the dated setlist |
| Families | R-F1, R-F2 | weak/flagged TapeMatch merges, members stating different mics |
| Tapers | R-T1…R-T6 | bare mentions, propagation over weak edges or out of era, TUIT disagreement, broadcast sources, 2+ confirmed tapers |
| Freshness / releases | R-S1, R-R1 | derived table older than its inputs, unknown release string |

`corroborate.py` is the cross-source layer (Olof vs setlist.fm, bobdylan.com, TUIT): setlist
quorum (feeds R-O4), tour premieres, rotation, tracklist, file format, taper and venue checks.
See [Setlist-Sources](Setlist-Sources.md).

## Curator console

`/qc-review` (`backend/qc_review.html`, Flask-served, experimental): Findings workbench + a
keyboard-driven Queue tab. Writes are curator-gated and go through `decisions.py`
(`decide`/`bulk_decide`/`add_correction`/`classify_release`), logged to `qc_decision_log`.
All five QC tables are USER-tier, local-only, never exported ([Database](Database.md)).

## Dossier gate (`dossier_qc.py`)

`run_gate()` runs G1–G8 on every dossier: G1 identity (no Olof event → reduced dossier from
setlist.fm/bobdylan.com identity, a chooser when they disagree, else refuse with HTTP 422 —
TODO-371),
G2 source-show fit, G3 provenance, G4 quarantine (`store.quarantined()` — open/confirmed
errors on the source row), G5 invariants, G6 freshness (R-S1), G7 claims (drops any claim over a
withheld scope), G8 public-channel leak backstop. The result is embedded in the page
(`lb-qc` JSON) so `tools/dossier_verify_export.py` can detect drift later.
See [Show-Dossier](Show-Dossier.md).

## Verification tooling

| Tool | Use |
|---|---|
| `tools/dossier_sweep.py` | builds every concert date through the gate; `data/logs/dossier_sweep_<date>.md`; nightly 03:15 cron, notifies when errors rise |
| `tools/dossier_acceptance.py --all` | every plan accept case against live data, one PASS/FAIL summary |
| `tools/dossier_golden.py --check` | 18 tj-verified golden specs: fixture == live |
| `tools/olof_reparse_diff.py` | snapshot/diff gate for any Olof reparse (UNEXPLAINED must be 0) |

Phase 8 order of checks (C34): backend restart → pytest → `qc run` → acceptance → sweep →
`/verify` Tier A (dossier iframe, light/dark) → `/verify --electron` PDF export.
