# archive/

Obsolete material moved out of the working tree on 2026-09-01. **Nothing here
was deleted** — this is a holding area, not a graveyard with a timer. Anything
that turns out to still be needed can be moved straight back.

`venvs/`, `build-artifacts/`, `debug/` and `scratch/` are gitignored (bulky and
machine-local); `attic/` and `tools-throwaway/` are tracked.

| Path | What it is | Why it was archived |
|---|---|---|
| `venvs/venv-broken-py313/` | 642 MB Python 3.13 virtualenv | Broken and superseded by `.venv/`; the name said so already. |
| `build-artifacts/gui_next-dist-1.2.0-2026-05-29/` | `electron-builder` output, incl. a 124 MB AppImage | Built 2026-05-29 at v1.2.0; `VERSION` is now 1.4.0. Regenerate with `npm run dist:linux` in `gui_next/`. |
| `scratch/taper-tier-2026-07-17/` | Former `.scratch/` — taper tier recompute scripts, shortlist JSON, a standalone `taper_review.html` draft | One-off 2026-07-17 working set; superseded by `backend/taper_review.html` (TODO-312/313) and the `/taper-curation` workbench (TODO-327). |
| `debug/` | 318 `.debug/` artifacts dated before 2026-08-01 (screenshots, driver sessions, coverage, scratch JSON) | `.debug/` is disposable by convention. `.debug/` itself and its `electron/`/`screenshots/` subdirs remain in place — `/verify` writes to those exact paths. |
| `attic/` | The pre-existing ad-hoc `attic/` directory, moved verbatim | Folded in so there is one archive rather than two. Its own `README.md` still describes the contents. |
| `tools-throwaway/` | `_qbt_sysctl.conf`, `_qbt_tune.sh`, `_route_audit.py`, `_route_dryrun.py` | `tools/_<name>` is the repo's throwaway-script convention (`.claude/CLAUDE.md`). The qBittorrent tuning pair was untracked; the route scripts shipped their work in 62cbb8f2 (TODO-317). 2026-10-18 (TODO-360): one-shots whose task closed. These came from `tools/` unless a path says otherwise: `build_adhoc_pdf.py` (`tools/adhoc_quality/`, the July adhoc report), `refetch_html_attachments.py` (TODO-329), `tuit_overlay_repair.sh` (TODO-337), `migrate_gazetteer_city_country.py` (TODO-352, applied 2026-09-30); `tapematch/bug326_{scan,diff}.py` + `bug326_rerun_queue.txt` (`tools/tapematch/`, TODO-323); `tapematch_calib_logs/{rerun_9611,run_catval,run_confsweep}.sh` (`tools/tapematch/calib_logs/`, the Phase-2 calibration runs). Most expect to run from their original path, so move one back before running it. |
| `specs/` | Every shipped spec, plan and design handoff (HTML prototypes, JSX, screenshots) — formerly `instructions/complete/`, plus the pipeline-refresh inventory + phases 1–3 and `SHOW_DOSSIER_AUDIT.md` | Moved 2026-10-17 so `instructions/` holds only live work. Retire a spec by `git mv`-ing it here (see `instructions/README.md`). |

## Deliberately left alone

- `data/` — user data, 33 GB, gitignored. `data/webengine_cache/` was deleted
  outright on tj's call (see the CHANGELOG). The `data/lossless_bob.db` /
  `data/losslessbob.db` pair still looks stale, but it is yours to judge.
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` — regenerable caches, not archive material.
- Everything under `tools/` that is not `_`-prefixed: reference counts alone
  could not prove any of it dead, so none of it was moved. (TODO-360 later
  archived the ones whose task had closed and listed the rest in `tools/README.md`.)
