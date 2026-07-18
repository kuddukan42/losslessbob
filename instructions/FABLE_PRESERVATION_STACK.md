# FABLE spec — Preservation stack, the Jeff-continuity problem (PLATFORM_ROADMAP §5)

Written 2026-07-17 (Fable 5). Expands FABLE_PLATFORM_ROADMAP.md §5 into a handoff
spec. Audience: **sonnet implementation sessions** — every bite states exact accept
criteria; when reality diverges from a stated fact below, stop and re-verify before
improvising.

Goal: the losslessbob.com data **cannot be lost**. The mirror already substantially
exists — this spec closes the three gaps to archival grade: (1) mirror
self-verification, (2) sealed distributable snapshots, (3) a restore test.

**What this is NOT:** no publishing, no uploads of any kind (the mirror stays
local/friends-only — ethics agreed 2026-07-15: private dark archive =
preservation; *publishing* would need Jeff's blessing), no scraping changes beyond
one column write, no curation-continuity tooling (out of scope per roadmap), no
GUI (CLI-only per D-4 default).

---

## 1. Verified facts (2026-07-17 — trust these, re-verify only on contradiction)

- `site_inventory`: 110,938 URLs, **110,846 status='downloaded' with per-body
  SHA-256**, last refresh 2026-07-14. Columns: `url` PK, `status`,
  `relative_path` (relative to `data/site/` = `SITE_DIR` in `backend/paths.py`),
  `content_type`, `size_bytes`, `http_status`, `last_fetched_at`,
  `last_checked_at`, `last_modified`, `body_sha256`, `discovered_by`,
  `session_id`.
- **CRITICAL hash provenance** (`backend/site_crawler.py`, crawl loop + `_save`):
  `body_sha256` and `size_bytes` are computed on the **raw HTTP body**, but HTML
  files (ext `.html` or none) are saved **link-rewritten** (`rewrite_links`) and
  re-encoded utf-8 `errors="replace"`. So on-disk HTML can NEVER match
  `body_sha256` — a naive re-hash pass would report ~100k false drift errors.
  Non-HTML files are written verbatim (`write_bytes`) and DO match. The design
  below (D1) adds a `local_sha256` on-disk baseline for this reason.
- `entry_changes`: 62,984 field-level diffs over 32 scrape sessions — the site's
  *history* lives in the SQLite DB, so the DB snapshot is part of preservation,
  not just the file mirror.
- Master export already exists: `POST /api/master/export` with `channel:
  'public'|'full'` — `'full'` keeps private-entry metadata (friends-only tier,
  TODO-245/253). Find the underlying function in `backend/app.py` and call it
  directly (in-process, not HTTP) from the snapshot tool.
  `POST /api/master/github_release` **refuses any non-public channel** — snapshot
  artifacts must never gain an upload path; distribution is manual (drives/links
  to friends on different continents, LOCKSS-style).
- Olof/bobserve mirrors: pages verbatim in `data/olof/pages/` and
  `data/olof/bobserve_pages/`, per-page sha256 in `olof_pages.sha256`.
- `friend_collections` names the distribution audience; `flat_file_releases` +
  `instructions/complete/CC_TRADING_PLAN.md` are the existing release-mechanics
  patterns — read for shape, don't couple to them.
- SQLite rules: `PRAGMA table_info` column-existence check before `ALTER TABLE`;
  never assume clean DB. Python is `.venv/bin/python3`.

---

## 2. Target design

### D1 — Mirror self-verification (`tools/verify_site_mirror.py`)

An unverified backup is a hope. Add nullable `local_sha256` column to
`site_inventory` (idempotent migration in `db.py` per repo SQLite rules):
sha256 of the file **as saved on disk**.

- Crawler change (one spot): after `_save`, hash the saved file and include
  `local_sha256` in the `upsert_inventory` call — every future fetch records both
  hashes.
- `--baseline` mode: for rows with `status='downloaded'` and `local_sha256 IS
  NULL`, hash the current on-disk file and store it. This TRUSTS the current
  mirror state (nothing better exists for already-rewritten HTML); say so in the
  report. For non-HTML rows, first compare against `body_sha256` and flag
  mismatches BEFORE baselining them — those are real pre-existing rot candidates.
- Default (verify) mode, read-only: re-hash every downloaded row's file, compare
  to `local_sha256` (fallback `body_sha256` for non-HTML rows not yet baselined);
  report **missing** (row says downloaded, file absent), **drift** (hash
  mismatch), **orphans** (files under `data/site/` with no inventory row),
  **unbaselined** count. One line per issue, single-line summary at the end
  (repo CLI output rule), non-zero exit iff missing/drift found. `--report` writes
  the same to a dated file under `data/exports/`.

### D2 — Sealed snapshots (`tools/make_site_snapshot.py`)

Builds `data/exports/snapshots/lbsnap-YYYY-MM-DD[.N]/` (BagIt-style, plain
stdlib):

1. Runs D1 verify first; refuses on missing/drift (`--no-verify` escape hatch,
   logged loudly).
2. Calls the master-export function in-process with `channel='full'` → includes
   the snapshot `.db` + its `.manifest.json`.
3. Stages content per D-1 decision (default: `data/site/` + both olof mirror
   dirs + the DB export). Use `os.link` hardlinks when staging on the same
   filesystem, copy fallback — never duplicate GBs by default.
4. Writes `manifest.txt`: `sha256␠␠size␠␠relpath`, sorted by relpath (stable
   across runs); `seal.txt`: single sha256 over `manifest.txt`; `README.txt`:
   what this is, date, counts, how to verify, and the friends-only/no-publishing
   note.
5. Embeds a standalone `verify_snapshot.py` (pure stdlib, zero repo imports —
   a friend runs `python3 verify_snapshot.py` inside the snapshot dir with
   nothing else installed).
6. `--tar` additionally produces `lbsnap-<date>.tar.gz` + `.sha256` sidecar
   (stdlib tarfile/gzip; no new deps — D-2).

No upload code anywhere in this tool. Distribution is a human act.

### D3 — Restore test (`tools/check_mirror_links.py`)

Proves continuity of *reference* — during outages friends need to look things up.
The mirror's HTML is already link-rewritten to relative paths, so a restore is
just "serve the directory". The check, read-only: walk mirrored HTML (default a
deterministic 500-page sample seeded to include the site home, the LBM master
index, and both bootleg/year indexes; `--full` walks everything), extract internal
`href`/`src` targets, assert each resolves to a file on disk; report broken links
per page + summary, non-zero exit above a `--max-broken` threshold (default 0 for
the four seed pages, unlimited-report-only for the sample). Document the serve
one-liner in the script header and PROJECT.md:
`python3 -m http.server -d data/site 8080`.

Three continuities, kept separate: data (D1+D2), reference (D3), curation (the
monthly update stream — no tool solves this; explicitly out of scope).

---

## 3. Decisions for tj (defaults apply if unaddressed)

- **D-1 snapshot contents** — default: site mirror + olof + bobserve mirrors +
  full-channel DB export. Alternatives: site+DB only (smaller), or also
  `data/exports/` flat-file history.
- **D-2 archive format** — default: plain directory, optional `--tar` tar.gz,
  stdlib only. Alternative: zstd (new pinned dep — not worth it unless size
  hurts).
- **D-3 cadence** — default: manual (document a suggested monthly habit in the
  README.txt + PROJECT.md). Alternative: `/schedule` a monthly verify+snapshot
  routine — do NOT set this up unprompted.
- **D-4 GUI surface** — default: none, CLI-only. Alternative: a card on
  ScreenScraper showing last verify result (defer; not in these bites).

---

## 4. Work bites (handoff units — commit each separately; sonnet tier)

Allocate ONE TODO id for the whole spec at the first implementation session (repo
numbering rules in `/session-close`). Repo rules apply throughout: type hints +
Google docstrings, `logging` not `print`, 100-char lines, module-constant paths
derived from `backend/paths.py` — no hardcoded path literals.

### B1 — local_sha256 + verify tool (M)
Migration + crawler write + `tools/verify_site_mirror.py` per D1. Tests build a
tmp mirror (few HTML + one binary + inventory rows in a temp DB): baseline run
populates `local_sha256`; tamper a file → drift + non-zero exit; delete a file →
missing; stray file → orphan; binary with wrong `body_sha256` flagged during
baseline. **Accept:** tests green; `--baseline` then verify against the real
mirror completes with **zero false drift on HTML** (the §1 hash-provenance trap);
paste the real summary line for tj.

### B2 — snapshot builder (M) — after B1
`tools/make_site_snapshot.py` + embedded `verify_snapshot.py` per D2. Tests: build
from the tmp mirror; embedded verifier exits 0; tamper one staged file → embedded
verifier fails naming the path; two builds from unchanged input produce identical
`manifest.txt` (timestamps only in README); hardlink staging verified (same
inode). **Accept:** tests green; a real snapshot builds end-to-end (report size +
duration for tj — do NOT commit or upload the artifact anywhere).

### B3 — restore test (S) — after B1 (independent of B2)
`tools/check_mirror_links.py` per D3. Tests: tmp mirror with a broken + a valid
link. **Accept:** tests green; one real run — the four seed pages fully resolve;
broken-link findings from the sample are LISTED in the session summary as
findings for tj, not auto-fixed.

### B4 — docs (XS) — last
PROJECT.md (new tools, `local_sha256` column, serve one-liner), roadmap §5 status
line + instructions/README.md row, cross-ref note in CC_TRADING_PLAN.md overlap
section if one exists. CHANGELOG via `/session-close`.

Order: B1 → B2 / B3 (either order) → B4.

---

## 5. Definition of done

1. Every future crawl records both raw and on-disk hashes; a periodic
   `verify_site_mirror.py` run proves the 110k-file mirror is intact or names
   exactly what rotted.
2. One command produces a sealed, self-verifying snapshot a non-technical friend
   can check with stock Python — no repo, no deps.
3. The DB (history + full-channel metadata) travels inside the snapshot, not
   just the file mirror.
4. `python3 -m http.server -d data/site` serves a browsable site; the link check
   proves the core index pages resolve.
5. Zero upload paths; nothing about the mirror becomes publishable by accident.
6. All three tools are safe to run while the app is up (read-only against the
   live DB except the baseline column write).
