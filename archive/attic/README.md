# Attic — candidates for deletion

Stray files swept here on 2026-07-16. Nothing in live code references any of
them (verified by grep across backend/, scripts/, tools/, cli.py, .claude/).
Review and delete when convenient; pull anything back out if it's still wanted.

## One-off reports and exports (root strays)

| File | Origin | Why here |
|------|--------|----------|
| `wtrf_batch_85_report.md` | WTRF scrape batch report (Jul 2) | one-off output, run complete |
| `wtrf_missing_status_2026-07-02.md` | WTRF missing-status snapshot | superseded by later runs |
| `wtrf_skipped_review.md` / `wtrf_skipped_review_rerun.md` | WTRF skip review notes | review complete |
| `shared_checksums_report.md` | shared-checksums analysis (Jul 15) | one-off report output |
| `missing_from_collection.tsv` | collection gap export (Jun 3) | one-off export, was gitignored |
| `public_not_owned.html` | public-not-owned report (Jun 3) | one-off export, was gitignored |
| `scan.json` | scan output (Jun 1, 544 KB) | regenerable, was gitignored |
| `batch_verify_run.log` | verify run log (Jun 3, 380 KB) | stale log, was gitignored |

## Stale artifacts

| File | Why here |
|------|----------|
| `observations.db` | 0-byte stray at repo root — the real one lives at `tools/tapematch/observations.db` |
| `losslessbob.db` | 0-byte stray at repo root — real DB is `data/losslessbob.db` |
| `observations.db.bak-20260612_124147` | month-old tapematch DB backup (moved from `tools/tapematch/`) |
| `losslessbob.tar.gz` | May 8 source archive, predates most of the repo's history since |
| `screenshot_log.txt` / `screenshot-lookup.png` | June 9 / May 29 debug leftovers |
| `notes.todo` | pre-TODO.md planning notes (May 23); every open item is done or superseded (db-integrity plan → lb_master system, xref items → TODO-246, translations → gui-next-i18n) |

## Qt-era scripts (legacy GUI removed 2026-07-16)

| File | Why here |
|------|----------|
| `build_qm.py` | compiled Qt `.qm` translation files |
| `port_qt_to_json.py` | one-time Qt → JSON locale port (done) |
| `fix_ts.py` / `fix_ts2.py` | one-off Qt `.ts` fixups |

`scripts/deepl_translate_gui_next.py` stays — it's used by `/gui-next-i18n`.
