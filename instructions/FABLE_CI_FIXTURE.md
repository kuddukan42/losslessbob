# FABLE spec — CI on GitHub Actions + golden fixture DB (FABLE_IDEAS dev-workflow §2)

Written 2026-07-17 (Fable 5). Expands FABLE_IDEAS.md dev-workflow idea 2 into a handoff
spec. Audience: **sonnet implementation sessions** — every bite states exact commands
and accept criteria; when reality diverges from a stated fact below, stop and re-verify
before improvising.

Two pieces that reinforce each other:
1. a **synthetic fixture dataset generator** — a data-shaped miniature of the real
   install (~100 entries) that anything (CI, cloud agents, onboarding tests) can build
   in seconds without tj's real 2.4 GB `data/` tree;
2. a **CI workflow** on the public repo (kuddukan42/losslessbob) that runs compile
   checks, the backend test suite, a fixture-backed backend boot smoke, and the
   gui_next typecheck+build on every push.

**What this is NOT:** no publishing, no release changes (`release.yml` stays
untouched), nothing user-facing, no real checksums/taper names in the fixture.

---

## 1. Verified facts (2026-07-17 — trust these, re-verify only on contradiction)

- Test suite: `.venv/bin/python3 -m pytest tests/ -q` collects **854 tests** (40
  files, repo-root `conftest.py` resets the DatabaseWriteQueue singleton between
  tests). Tests are already self-contained: temp-file DBs seeded via SQL, all network
  mocked. The old order-dependence flake (BUG-187, bloom-filter leak) is **fixed**
  (see BUGS_DONE.md) — a full-suite run is expected green.
- `pytest` is NOT in `requirements.txt` (runtime deps only, pinned exact). There is
  no dev requirements file yet.
- `.github/workflows/release.yml` already exists (tag-triggered release build). Reuse
  its versions: Python `'3.11'`, Node `'22'`, `actions/checkout@v5`,
  `actions/setup-python@v6`, `actions/setup-node@v4`.
- gui_next: `npm ci`, then `npm run typecheck` (`tsc -b tsconfig.json`) and
  `npm run build` (`electron-vite build`) — the same pair `/gui-check` runs.
- `tools/tapematch/` has its own tests (`tools/tapematch/tests/`) and its own light
  `requirements.txt` (numpy/scipy/soundfile/pyyaml — no librosa/torch).
- DB location: `backend/paths.py` → `APP_ROOT = Path(__file__).parent.parent` (when
  not frozen), `DATA_DIR = APP_ROOT / "data"`, `DB_PATH = DATA_DIR /
  "losslessbob.db"`. **No env override exists** — B1 adds one.
- Schema is fully created by `db.init_db()` (idempotent, `CREATE TABLE IF NOT
  EXISTS`). Derived tables are rebuilt by the recompute chain
  (`tools/parse_lineage.py` → `tools/attribute_tapers.py` →
  `tools/compute_show_picks.py` → `backend/song_index.py`), same order as
  `POST /api/derived/recompute`.
- Cheap boot-smoke routes that exercise real query paths:
  `GET /api/onboarding/status`, `GET /api/search?q=`,
  `GET /api/library/performances`, `GET /api/songs?q=`.

---

## 2. Target design

### D1 — `LOSSLESSBOB_APP_ROOT` env override

`backend/paths.py::_app_root()`: in the unfrozen branch, honor
`os.environ.get("LOSSLESSBOB_APP_ROOT")` before falling back to
`Path(__file__).parent.parent`. Frozen branches unchanged. This is the single switch
that lets CI, cloud agents, and future tests point the whole backend at a throwaway
data dir. Nothing else in the app changes — every path constant already derives from
`APP_ROOT`.

### D2 — Fixture generator, not a committed binary

`tools/make_fixture_db.py` (CLI, argparse): builds a complete synthetic install into
`--dest` (default `data/fixture/`, gitignored). Steps: create `<dest>/data/`, call
`db.init_db()` against it, insert synthetic rows (D3), then run the real derived
recompute chain in-process against the fixture DB. Deterministic — fixed seed, fixed
dates, stable ids — so two runs produce identical row sets (timestamps exempt).
The *generator* is the checked-in artifact; the DB is built on demand (~seconds),
which keeps git free of binary churn and guarantees the fixture always matches the
current schema (it goes through `init_db()` every time).

### D3 — Fixture content: small, but every interesting shape

~100 `entries` across ~30 dates, ALL text synthetic (fake venue names, fake taper
handles like `testtaper_a` — never real taper names attached to fake data, never
real checksums; md5s are seeded-random hex). Must include at least:

| Shape | Why |
|---|---|
| multi-source dates (3+ LBs, one date) | families/picks/dossier grouping |
| a two-show date (same `date_str`, two `location`s) | performance-lens + dossier disambiguation |
| an `xx`-date entry (`concert_date_iso` NULL path) | picks/song-index NULL handling |
| `entries.status='private'` entry (+ matching `lb_master` row) | privacy-strip / channel tests |
| an xref group in `checksums` (canonical + xref>0 fileset) | lookup/xref surfaces |
| `recording_families` + `tapematch_family_meta` (2 families) | family grouping without observations.db |
| descriptions carrying lineage phrases ("same source as LB-N", "Taper: …", chain text) | so `parse_lineage`/`attribute_tapers` produce real derived rows |
| a curated list with 2–3 members | badges/picks term |
| `olof_events`/`olof_songs` rows matching several fixture dates (one song appearing once = `only`, one common song) | song index, rarity flags |
| one `bobdylan_shows` + one `setlistfm_shows` row | performance cross-refs |
| `entry_files` rows | attachments paths |
| `lb_master` rows spanning public/private/missing/nonexistent | integrity/status logic |
| `my_collection` rows for a handful of LBs (disk_path pointing inside `<dest>`, folders NOT created) | collection queries; missing-folder tolerance |

After generation, assert in-generator (fail loudly): entries ≥ 100, ≥ 1 private,
≥ 2 families, `show_picks` non-empty, `song_performances` non-empty,
`taper_attributions` non-empty. These prove the recompute chain actually ran.

### D4 — CI workflow `.github/workflows/ci.yml`

Triggers: `push` (all branches) + `pull_request` to `main`; concurrency group per
ref with `cancel-in-progress: true`. Four jobs, independent (no `needs` except
smoke → backend-deps caching is optional, keep it simple first):

1. **backend-tests** (ubuntu-latest): setup-python 3.11, `pip install -r
   requirements.txt -r requirements-dev.txt`, then
   `python -m compileall -q backend tools concert_ranker` and
   `python -m pytest tests/ -q`.
2. **backend-smoke** (ubuntu-latest): same setup + `python tools/make_fixture_db.py
   --dest /tmp/fixture`, start the app (`LOSSLESSBOB_APP_ROOT=/tmp/fixture python -m
   backend.app` or the waitress entry point — check how `backend/app.py` is launched
   and use that), wait for the port, then curl the four D1-listed routes and assert
   HTTP 200 + non-empty JSON (a ~30-line `tools/ci_smoke.sh` or python script,
   checked in, so cloud agents can run the identical smoke locally).
3. **gui-check** (ubuntu-latest): setup-node 22, `npm ci` + `npm run typecheck` +
   `npm run build` in `gui_next/` (cache: `npm`, `cache-dependency-path:
   gui_next/package-lock.json`).
4. **tapematch-tests** (ubuntu-latest): `pip install -r
   tools/tapematch/requirements.txt` + pytest over `tools/tapematch/tests/`
   (confirm its invocation from `tools/tapematch/CLAUDE.md` first).

New `requirements-dev.txt` (repo rule: pinned exact): `pytest==<current .venv
version>` (check `.venv/bin/python3 -m pytest --version`) — nothing else unless a
job actually needs it.

### D5 — What CI green means for sessions (docs contract)

Once live: CLAUDE.md's Verification section gets one line — "CI (`ci.yml`) runs the
backend suite + gui-check on every push; a session may cite a green run instead of
re-running the full local suite for unrelated code" — and the session-close skill can
mention pushing to get a CI verdict. (Do NOT weaken the local rules for code the
session actually changed — `/backend-restart` + targeted tests still apply.)

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 committed fixture DB** — default: generator-only (D2). Alternative: also
  commit a pre-built `fixture.db` for instant cloud-agent boots.
- **D-2 trigger scope** — default: every push on every branch. Alternative:
  `main` + PRs only (halves Actions minutes; pushes on work/* branches lose the net).
- **D-3 tapematch job** — default: include (deps are light). Drop if flaky on CI.
- **D-4 README badge** — default: add the standard Actions status badge to README.md
  (public repo, quiet advertising). Skip if you'd rather not surface build state.

---

## 4. Work bites (handoff units — commit each separately; sonnet tier)

Allocate ONE TODO id for the whole spec at the first implementation session (repo
numbering rules in `/session-close`). Repo rules apply throughout: type hints +
Google docstrings, `logging` not `print`, 100-char lines, PROJECT.md updated on any
dep/route/file change.

### B1 — env override (XS)
`LOSSLESSBOB_APP_ROOT` in `backend/paths.py` (D1). One new test in a suitable
existing file: subprocess or importlib-reload check that the override redirects
`DB_PATH`. **Accept:** default behavior byte-identical when the var is unset; test
green.

### B2 — fixture generator (M) — after B1
`tools/make_fixture_db.py` per D2/D3 + `data/fixture/` in `.gitignore`.
`tests/test_make_fixture.py`: generate into `tmp_path`, assert the D3 coverage
checklist (counts + one probe per shape, e.g. the private entry's metadata present,
the xref group's two filesets, a rarity-`only` song). **Accept:** two consecutive
runs produce identical non-timestamp content (compare a canonical dump); tests
green; generation < 60 s.

### B3 — smoke script (S) — after B2
`tools/ci_smoke.sh` (or `.py`): generate fixture → boot backend with the override →
poll until up → curl the 4 routes → assert 200 + sanity keys → clean shutdown
(kill the process; trap on exit). Runnable locally: document the one-liner in the
script header. **Accept:** exits 0 locally against a fresh fixture; exits non-zero
if a route 500s (verify by temporarily breaking one).

### B4 — workflow (S) — after B3
`.github/workflows/ci.yml` per D4 + `requirements-dev.txt`. Push to the current
work branch and watch the run (`gh run watch`). **Accept:** all four jobs green on
GitHub for real HEAD. Guard: `release.yml` untouched.

### B5 — triage (S–M, only if B4 is red)
Environment-dependent failures (missing ffmpeg, locale, timing) get fixed OR
skipped with `@pytest.mark.skipif` + a one-line reason naming the CI constraint —
never bare skips, never deleting assertions. Each skip listed in the commit message.
**Accept:** suite green on CI *and* still green locally.

### B6 — docs contract (XS) — last
CLAUDE.md one-liner (D5), PROJECT.md (new files, requirements-dev.txt, env var,
workflow), README badge (per D-4). CHANGELOG via `/session-close`.

Order: B1 → B2 → B3 → B4 (→ B5) → B6.

---

## 5. Definition of done

1. `python tools/make_fixture_db.py --dest /tmp/f && LOSSLESSBOB_APP_ROOT=/tmp/f
   <backend launch>` yields a browsable app with populated Library, songs, picks,
   families — from a clean checkout with zero real data.
2. Every push to the public repo gets a green/red verdict covering compileall,
   854+ backend tests, fixture boot smoke, gui typecheck+build.
3. A cloud agent given only the repo can run `tools/ci_smoke.sh` and exercise the
   real backend end to end.
4. No real checksums, taper names, or private-entry text anywhere in the fixture.
5. `release.yml` behavior unchanged; local verification rules unchanged for
   changed code (D5's citation rule is additive only).
