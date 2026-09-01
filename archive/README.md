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
| `tools-throwaway/` | `_qbt_sysctl.conf`, `_qbt_tune.sh`, `_route_audit.py`, `_route_dryrun.py` | `tools/_<name>` is the repo's throwaway-script convention (`.claude/CLAUDE.md`). The qBittorrent tuning pair was untracked; the route scripts shipped their work in 62cbb8f2 (TODO-317). |

## Deliberately left alone

- `data/` — user data, 33 GB, gitignored. `data/webengine_cache/` (a Qt
  WebEngine cache orphaned by the 2026-07-16 PyQt6 removal) and the
  `data/lossless_bob.db` / `data/losslessbob.db` pair look stale, but they are
  yours to judge.
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` — regenerable caches, not archive material.
- `instructions/complete/` — already serves as the spec archive.
- Everything under `tools/` that is not `_`-prefixed: reference counts alone
  could not prove any of it dead, so none of it was moved.
