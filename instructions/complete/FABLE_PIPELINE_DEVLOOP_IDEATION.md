# Workflow Ideation Report — LB Pipeline & CLAUDE.md Dev-Loop

**Scope:** Process improvements only (no code written). Sources reviewed: `PROJECT.md` (Collection Routing & Pipeline Filing section, lines 848–871; change-log entries for TODO-137/138, BUG-159/161/172, pipeline v2 phases), `backend/app.py` (`_pipeline_process_folder` lines 5871–6265, `/api/pipeline/run|scan-tree|scan-dir`, `/api/folder/rename`), `backend/filer.py` (full), `backend/checksum_utils.py` (`verify_folder`), `gui_next/src/renderer/src/components/pipeline/PipelineParts.tsx` (full), `gui_next/src/renderer/src/screens/ScreenPipeline.tsx` (queue sync, `runSteps`, auto-run/auto-complete/auto-rename effects, `applyRename`, `applyFile`, bucket logic), `.claude/CLAUDE.md` (full).

---

## Part 1 — Current-State Observations (grounding for the ideas)

### Pipeline mechanics as built

| Fact | Where |
|---|---|
| Stage order is `verify → lookup → lbdir → rename → file`; LBDIR deliberately moved before Rename (TODO-137) so reconcile happens before the folder name changes | `app.py:5871ff`, `PipelineParts.tsx:45-51` |
| `/api/pipeline/run` is fully synchronous; the GUI sends **one folder per HTTP request** in a sequential `for` loop (`runSteps`) to get incremental UI updates | `ScreenPipeline.tsx:1494-1528` |
| Verify hashes every audio file (md5 + ffp/shntool); LBDIR verify **re-hashes the same files** against the lbdir manifest; a cross-device/copy filing then reads all bytes **twice more** (`hash_tree` on source and dest). Worst case ≈ 4–5 full-content reads per folder | `checksum_utils.py:526ff`, `app.py:6100`, `filer.py:322-340, 517-536` |
| Verify and Lookup each independently `rglob` and parse the same `.ffp/.md5/.st5` files | `checksum_utils.py:550-583` vs `app.py:5939-5952` |
| The LBDIR step can trigger a **synchronous web scrape** (`scraper.scrape_entry`) inside the request when the lbdir attachment isn't cached | `app.py:6080-6092` |
| Filing is a **global singleton job** (`_FILE_JOB` + lock); "File all ready" serializes strictly, even across different physical mounts | `filer.py:263-277`, `ScreenPipeline.tsx:1812-1818` |
| Step results are cached **client-side only** (module-level `Map`, lost on app restart); backend re-runs everything from scratch on any re-run | `ScreenPipeline.tsx:153-156` |
| Auto-run (default on) drains new queue rows through all 5 steps; auto-complete resumes rows where lookup is ok but lbdir stayed mute; Auto-rename (default off) applies unambiguous proposals; **there is no auto-collect** — every filing needs a click (or "File all ready" which skips per-folder confirm) | `ScreenPipeline.tsx:1537-1558, 1662-1680, 1705-1717` |
| Rename→Collect coupling: after a rename the GUI makes an extra `/api/pipeline/run {steps:['file']}` round trip because the resolved `dest` embedded the old folder name | `ScreenPipeline.tsx:1612-1632` |
| An "Incomplete match" in Lookup mutes all downstream steps until the user pins; a pin lives in `folder_lb_link` and is re-keyed on rename (BUG-212) | `app.py:6054-6060`, `app.py:6336-6339` |

### Dev-loop ritual as written

- **Before any task:** read `PROJECT.md` (~2,000 lines), `BUGS.md`, `TODO.md`.
- **After every code change:** prepend `CHANGELOG.md`; conditionally update `PROJECT.md` **including a Change Log table row** (largely duplicating the CHANGELOG entry); maintain `BUGS.md`/`BUGS_DONE.md` and `TODO.md`/`TODO_DONE.md` with move-to-top-of-done semantics; update 6 locale JSONs for user-facing changes; `py_compile` touched Python; restart the backend before verifying.

---

## Part 2 — LB Pipeline Ideas

### P1. Single-pass hashing with a shared hash cache (Verify + LBDIR + Filing)

- **Pain point:** The same audio bytes are read and hashed up to 4–5 times per folder (Verify md5/ffp, LBDIR re-verify, filing `hash_tree` source, filing `hash_tree` dest). On multi-GB FLAC sets over a NAS this dominates wall-clock time and disk wear.
- **Proposed change:** One hashing pass per folder produces a per-file record `{rel_path, size, mtime, md5, ffp, sha256}`, cached (in-memory dict or a small SQLite table keyed on `(path, size, mtime)`). Verify and LBDIR compare their respective expectation sets against the same cache; filing's source-side `hash_tree` is derived from the cached sha256s. Only the **destination** hash after a copy must always be freshly computed.
- **Constraints it touches:** The hash-verify-before-remove invariant is preserved as long as the *destination* is always re-read; reusing a cached *source* hash is safe only if `(size, mtime)` still match at filing time — the cache key must be validated then, not just at Verify time. Verify and LBDIR intentionally have distinct failure attribution (local checksum files vs. lbdir manifest); merging the *hash pass* is fine, merging the *verdicts* is not.

### P2. Parallelize across folders with a real job model (replace per-folder synchronous requests)

- **Pain point:** `runSteps` processes the queue strictly serially: one folder, one blocking HTTP request, next folder. Lookup (DB), LBDIR scrape (network), and Verify (disk) for different folders could overlap; a 50-folder scan-tree import is a long single-file line.
- **Proposed change:** Move `/api/pipeline/run` to the async job pattern the codebase already uses for filing and integrity scans: `POST /api/pipeline/run/start {folders, steps, workers:N}` + status poll (or SSE). Backend runs N folder-workers (N=2–3), each executing the stage chain for its folder. GUI keeps its incremental row updates via the poll.
- **Constraints it touches:** Hashing two folders on the *same* spindle concurrently can be slower than serial (seek thrash) — worker count should be small and ideally grouped by source device. The LBDIR scraper likely shouldn't hit the site with high concurrency (be polite; the WTRF/site guards exist for a reason). SQLite writes (`set_folder_link`, `set_lbdir_verified`) are fine at this concurrency but need the existing connection discipline. The `_FILE_JOB` singleton is untouched — this parallelizes stages 1–4 only.

### P3. Prefetch LBDIR attachments in the background, out of the stage chain

- **Pain point:** When an lbdir file isn't cached, the LBDIR step blocks the whole folder's run on a live scrape — the slowest, least reliable link sits in the middle of the chain.
- **Proposed change:** As soon as Lookup resolves an LB# for any queued folder, fire an async prefetch of the lbdir attachment (respecting a small concurrency cap). The LBDIR stage then almost always finds the file already cached. Folders whose prefetch is still pending get a `lbdir: pending-fetch` state instead of blocking, and auto-complete (which already exists for `lbdir.status === 'mute'`) resumes them.
- **Constraints it touches:** Scraper rate limits / forum-guard conventions; prefetch must dedupe against a running scrape for the same LB# (simple per-LB lock). Idempotent because `find_lbdir_attachment` checks the cache first.

### P4. Run Verify and Lookup concurrently, and parse checksum files once

- **Pain point:** Verify and Lookup are sequential but independent — Lookup needs only the checksum *file text* (matched against the DB), not Verify's verdict. Both do their own `rglob` + parse of the same `.ffp/.md5/.st5` files.
- **Proposed change:** In `_pipeline_process_folder`, do one checksum-file collection pass, hand the parsed text to Lookup and the expectation map to Verify, and run Verify's hashing while Lookup's DB match is in flight (Lookup is milliseconds; the win is mostly the single parse plus code clarity — the *user-visible* win is that Lookup's LB# appears in the row immediately, before hashing finishes, which makes P3's prefetch fire earlier).
- **Constraints it touches:** None structural. Downstream gating (LBDIR/Rename/File require the Lookup LB#) is unchanged; only Verify moves off the critical path for LB# resolution.

### P5. "Auto-collect" toggle — close the last manual gap

- **Pain point:** With Auto-run + Auto-rename on, a clean folder still parks in `shelf` ("Ready to file") until the user clicks File (or "File all ready"). For the happy path — all stages green, unambiguous LB#, routed mount online, no dest conflict — the click adds nothing but latency and attention cost.
- **Proposed change:** Third header toggle, **Auto-collect** (default off, like Auto-rename): rows with verify/lookup/lbdir/rename all `ok` and `file.status === 'ready'` auto-enqueue into the filing worker with `skipConfirm`. Combined with Auto-run + Auto-rename this makes the pipeline genuinely hands-off for clean folders; humans only touch `needs`.
- **Constraints it touches:** This is the point of maximum blast radius — auto-moving data. Mitigations that must hold: hash-verify-before-remove already protects moves; `dest_exists` already blocks overwrites; it should respect the same `fileableRows` guard (no pending rename proposal, not shelved). Default-off and per-session (not persisted) is the right safety posture, mirroring Auto-rename. Consider restricting it to `file_mode=move` on same-device *or* copy — i.e. never auto-run the one path with no verification (same-device `os.rename` is atomic, so actually all paths are safe; the real risk is filing to the *wrong* place, which the routing preview mitigates).

### P6. Filing queue instead of the "busy" singleton

- **Pain point:** `_FILE_JOB` holds exactly one job; a second start returns `busy` and the GUI serializes with `filingRef`. "File all ready" over 20 folders means the user must keep the screen alive for the whole sequence; an app restart mid-batch loses the remaining list (the queue store persists paths but not the "you were filing these" intent).
- **Proposed change:** Backend-side FIFO filing queue (`/api/pipeline/file/enqueue` accepting many folders; status endpoint returns the queue + current job). Optionally one worker **per destination mount** — filings to different physical disks don't contend and could run 2-wide.
- **Constraints it touches:** Hash-verify-before-remove per job is unchanged. Per-mount parallelism must never let two jobs write the same `dest_parent` simultaneously (year routes make collisions unlikely but the `dest_exists` check must move inside the worker, at dequeue time, not enqueue time — same TOCTOU note as P8). The GUI's single-progress-bar model needs a per-row job id instead of "the one global job".

### P7. Persist pipeline row state server-side; resume instead of restart

- **Pain point:** Step results live in a module-level `Map` in the renderer. Close the app (or clear the queue) and every folder re-verifies from zero — hours of re-hashing for large queues. The auto-complete effect can resume *within* a session, but nothing survives across sessions.
- **Proposed change:** A `pipeline_state` SQLite table keyed on `(folder_path, folder_mtime)` storing the last step results JSON + timestamps. `/api/pipeline/run` consults it: steps whose inputs are unchanged (folder mtime, checksum-file set, DB lookup inputs) return cached verdicts marked `cached: true`; the GUI shows a "re-check" affordance to force. Restores the queue exactly where it was after an app or backend restart.
- **Constraints it touches:** SQLite schema change → must follow the repo's `ALTER TABLE` + try/except idempotency rule. Staleness is the real risk: mtime on a *directory* doesn't change when a file's content changes in place — the cache key needs per-file `(size, mtime)` aggregation (dovetails with P1's cache; these two ideas share one table). A stale "pass" that lets a corrupted folder reach filing is still caught by filing's own hash-verify only on copy paths — so cached *verify* verdicts should expire or be revalidated cheaply (size/mtime sweep) before enabling auto-collect (P5) on top of them.

### P8. Move the `dest_exists` / mount-online check to filing time only (declutter "blocked")

- **Pain point:** The File step resolves at pipeline-run time, so a mount that's asleep or a transient `dest_exists` marks the row `blocked` and pushes it into `needs` — the user re-runs the whole row later just to refresh a resolution that steps 1–4 never needed. Failed/blocked Collect forces re-attention on already-verified work.
- **Proposed change:** Treat Collect resolution as a *live view*, not a stage verdict: the row's overall status ignores `file: blocked` for bucketing (park such rows in `shelf` with a "mount offline / dest exists" chip), and the Collect panel re-resolves on open/poll — which `CollectDetail`'s preview re-resolve already half-does. A "retry blocked collects" sweep (or auto-retry when a mount comes back online, piggybacking on the existing reachability checks) absorbs the manual re-runs.
- **Constraints it touches:** `start_file_job` already re-resolves at start, so correctness is unaffected; this is purely a severity/bucketing and refresh-policy change. Keep `no_date`/`no_route` as true attention states (they need human config), distinct from transient `mount_offline`/`dest_exists`.

### P9. Batch-level triage view instead of strictly per-folder attention

- **Pain point:** With scan-tree imports of dozens of folders, the `needs` bucket mixes fundamentally different manual tasks: "pin one of 2 LBs" (5 seconds), "checksums diverge from archive" (investigate), "no checksums at all" (different tool). The user context-switches per row.
- **Proposed change:** Group `needs` by *reason* (lookup-conflict, incomplete-match, lbdir-missing-files, no-checksums, verify-mismatch) with reason-specific bulk affordances — e.g. a "resolve conflicts" mode that walks only the pin decisions one after another (each pin already auto-resumes downstream via the auto-complete effect), or "shelve all no-checksum folders". Same data, different sort key.
- **Constraints it touches:** None backend-side; the reason is already in `errors[]`/step labels. Pure GUI restructure.

### P10. Merge Rename into Collect (single "finalize" action)

- **Pain point:** Rename and Collect are two user decisions about the same fact ("this folder is LB-X and belongs in the archive"). The split also creates the post-rename `file`-re-resolve round trip and the `renamePending` guard that blocks filing until rename is applied.
- **Proposed change:** Collect's confirm dialog shows the proposed final name and performs rename+file as one backend transaction (`rename → resolve dest with new name → move`). The Rename stage remains as a *preview* tile but stops being a separate click; Auto-rename becomes redundant.
- **Constraints it touches:** This intentionally softens the LBDIR-before-Rename ordering rationale? No — LBDIR still runs before the combined step, so TODO-137's invariant (reconcile against lbdir before the name changes) holds. But it couples two failure domains: a rename that succeeds followed by a move that fails leaves a renamed-but-unfiled folder — exactly the state the current design surfaces cleanly as `shelf`. The qBittorrent sync would fire twice (rename sync + relocate) unless combined. **Recommend as a design option, not a clear win** — the current split has real diagnostic value; P5 (auto-collect) captures most of the same click savings without the coupling.

---

## Part 3 — CLAUDE.md Dev-Loop Ideas

### D1. Kill the CHANGELOG ↔ PROJECT.md Change Log duplication

- **Pain point:** Nearly every session writes the same prose twice — a `CHANGELOG.md` entry *and* a `PROJECT.md` Change Log table row (the PROJECT.md rows quoted above are full paragraphs). It's the single largest toil item and the two drift.
- **Proposed change:** Make `CHANGELOG.md` the sole narrative log. `PROJECT.md`'s Change Log table either (a) gets deleted with a pointer to CHANGELOG, or (b) is auto-generated (a tiny script renders the last N CHANGELOG entries into the table — could run from a PostToolUse/Stop hook like the existing schema-deploy hook). CLAUDE.md rule shrinks to: "PROJECT.md: update *reference* sections (structure/schema/routes/tabs/deps) only".
- **Constraints it touches:** PROJECT.md is the "read before any task" document — if history moves out, sessions that relied on skimming recent changes there must read CHANGELOG head instead (cheaper anyway: prepend-ordered).

### D2. Scripted BUG/TODO ledger operations (`tools/ledger.py`)

- **Pain point:** Opening a bug requires reading `BUGS.md` to find the next free number, formatting a block by hand; closing one requires cut-from-one-file, paste-to-top-of-another with date stamps. Same for TODOs. Mechanical, error-prone (number collisions, wrong file ordering), and burns tokens on full-file reads.
- **Proposed change:** A small CLI: `ledger.py bug-open "title" --files x:y`, `bug-close 227 --root-cause ... --fix ...`, `todo-open/close`, `next-id`. It allocates numbers, formats blocks, and does the move-to-top-of-DONE transactionally. CLAUDE.md rule becomes "use ledger.py" — one Bash call instead of two Read+Edit cycles per item.
- **Constraints it touches:** The file formats are consumed by humans and prior sessions — the script must emit byte-identical block formats. Must live inside the project dir (file-access hook scope). Should be pure Python 3.11 stdlib and run via `.venv/bin/python3` per repo convention.

### D3. Hook-enforced ritual instead of memory-enforced ritual

- **Pain point:** "After every code change update X/Y/Z" relies on the model remembering at the right moment; misses surface as drift discovered sessions later. Meanwhile `py_compile` and "restart backend" are pure mechanical checks.
- **Proposed change:** Three hooks in `.claude/settings.json`:
  1. **PostToolUse on `Edit|Write` of `*.py`** → run `.venv/bin/python3 -m py_compile` on the file (removes a whole rule from CLAUDE.md).
  2. **PostToolUse on `locales/en.json`** → reminder (or auto-invoke note) that the other 5 locales + the `gui-next-i18n` skill are pending.
  3. **Stop/SessionEnd hook** → check `CHANGELOG.md` head is dated today when the session touched tracked source files; warn if not. (Advisory, not blocking — sessions legitimately end mid-task.)
- **Constraints it touches:** Hooks execute regardless of model attention — exactly why they beat CLAUDE.md prose — but a blocking py_compile hook would fire on intentionally-intermediate edits; keep it advisory or scope it to the Stop hook. The repo already runs a PostToolUse deploy hook (schema.html → Cloudflare), so the pattern is established.

### D4. Batch doc updates to end-of-session, verified by the D3 Stop hook

- **Pain point:** "After **every** code change" literally means interleaving doc edits with code edits — churn, extra tool calls, and CHANGELOG entries that get amended repeatedly within one session. In practice sessions already batch; the rule and reality disagree.
- **Proposed change:** Reword the ritual to "before ending the session (or before any commit), write the CHANGELOG entry and ledger updates for everything changed" — one consolidated doc pass, safety-netted by the Stop-hook check from D3. Commits remain the hard barrier: no commit without docs.
- **Constraints it touches:** Risk: a crashed/interrupted session loses the doc trail for changes already on disk. Mitigation: the Stop hook fires on interrupt too, and `git diff` reconstructs what changed; the current per-change rule doesn't actually survive crashes either (the doc edit is just as unsaved).

### D5. Slim the "Before Any Task" read

- **Pain point:** Reading `PROJECT.md` + `BUGS.md` + `TODO.md` before *any* task front-loads thousands of lines even for a one-line fix — directly against the user's own grep+offset/limit memory rule.
- **Proposed change:** Restructure the rule: read a ~50-line `PROJECT.md` header (structure map + pointers) always; read deep sections (routes tables, schema) only when the task touches them; grep `BUGS.md`/`TODO.md` for keywords related to the task instead of full reads. Optionally split PROJECT.md into `PROJECT.md` (index) + `PROJECT_REFERENCE.md` (route/schema tables) so the always-read part is small by construction.
- **Constraints it touches:** The full pre-read exists to prevent duplicate BUG/TODO numbers and missed context — D2's `ledger.py next-id` removes the numbering reason, and keyword grep covers the collision-awareness reason. Splitting PROJECT.md is a one-time doc migration that all prior instructions/links must survive.

### D6. Locale-update automation as part of the feature loop

- **Pain point:** Every user-facing string fans out to 6 JSON files; it's listed in Workflow Conventions but is a per-key mechanical translation chore (the git status shows all 6 locales touched together, again).
- **Proposed change:** Standardize on: edit `en.json` only during feature work; run the existing `gui-next-i18n` skill once per session as a batch step (triggered by the D3 en.json hook reminder). Add a tiny check script (keys present in en.json but missing elsewhere) runnable in the Stop hook.
- **Constraints it touches:** None — the skill already exists; this just moves it from "remember per string" to "checked once per session".

---

## Part 4 — Combined Ranking (impact vs. effort)

| # | Idea | Domain | Impact | Effort | Notes on ratio |
|---|------|--------|--------|--------|----------------|
| 1 | **D1** Deduplicate CHANGELOG vs PROJECT.md change log | Dev-loop | High (every session) | Low (doc rule change + optional generator) | Best ratio overall; pure toil deletion |
| 2 | **D3** Hooks for py_compile / i18n / changelog check | Dev-loop | High (removes memory-dependence) | Low–Med (settings.json + 2 tiny scripts) | Pattern already proven by schema-deploy hook |
| 3 | **P5** Auto-collect toggle | Pipeline | High (removes last click on happy path) | Low (mirrors existing Auto-rename effect + skipConfirm path) | All safety rails already exist |
| 4 | **D2** `ledger.py` for BUG/TODO ops | Dev-loop | Med–High (every bug/todo touch) | Low–Med (one CLI script) | Also enables D5 by removing the numbering pre-read |
| 5 | **P8** Collect blocked-state as live view + auto-retry | Pipeline | Med–High (kills pointless full re-runs) | Low–Med (bucketing + refresh policy, no data-path change) | Zero risk to filing invariants |
| 6 | **P3** Background LBDIR prefetch | Pipeline | Med–High (removes slowest sync link) | Med (async fetch + per-LB lock) | Big tail-latency win on uncached LBs |
| 7 | **D5** Slim pre-task reads / split PROJECT.md | Dev-loop | Med (token + time per session) | Med (one-time doc restructure) | Depends on D2 for the numbering excuse |
| 8 | **P1** Shared hash cache, single hash pass | Pipeline | High (biggest wall-clock win on large sets) | High (touches verify, lbdir-verify, filer; staleness keys) | Highest absolute payoff, do after P2/P7 shape the job model |
| 9 | **P7** Persist pipeline state; resume across restarts | Pipeline | Med–High (no re-hash after restart) | Med–High (new table + staleness rules; ALTER-TABLE idempotency) | Shares its cache table with P1 — design together |
| 10 | **P2** Async job model with small worker pool | Pipeline | Med (throughput on big imports) | High (new job/status plumbing, GUI rework) | Do before P1 if both are planned; disk-contention caveat caps the win |
| 11 | **D4** End-of-session doc batching | Dev-loop | Med (less churn) | Low (rule rewording) — but only safe **after** D3's hook exists | Sequenced behind D3 |
| 12 | **P9** Reason-grouped triage for `needs` | Pipeline | Med (attention efficiency) | Med (GUI only) | Value grows with queue size |
| 13 | **D6** Batched i18n via skill + key-diff check | Dev-loop | Low–Med | Low | Mostly formalizes current practice |
| 14 | **P6** Filing queue / per-mount workers | Pipeline | Med (unattended batch filing) | High (job model, TOCTOU care, GUI per-row progress) | Queue part worthwhile; per-mount parallelism marginal |
| 15 | **P4** Verify∥Lookup + single checksum parse | Pipeline | Low (Lookup is cheap) | Low–Med | Nice-to-have; earlier LB# helps P3 slightly |
| 16 | **P10** Merge Rename into Collect | Pipeline | Low–Med (clicks already absorbed by P5) | Med–High (couples failure domains, double qbt sync) | Weakest ratio; current split has diagnostic value — recommend against unless P5 proves insufficient |

### Suggested sequencing

1. **Quick wins, this week-scale:** D1 → D3 → P5 → D2 (each independent, low risk).
2. **Structural pipeline work, one design doc covering all three:** P7 + P1 share a cache table and staleness model; P2 decides where that cache is consulted. Designing them together avoids doing the job-model plumbing twice. P3 and P8 slot into that job model naturally.
3. **Defer / re-evaluate after the above:** P6 per-mount parallelism, P9, P10, P4.

### Invariants deliberately preserved throughout

- **Hash-verify-before-remove** on any copied data (P1 only ever caches *source* hashes with size/mtime revalidation; destination is always freshly hashed).
- **LBDIR-before-Rename** (TODO-137) — no idea reorders these; P10 merges Rename *forward* into Collect, not backward.
- **Single-writer filing per destination** — P6 relaxes the global singleton but keeps per-`dest_parent` exclusivity and moves `dest_exists` checks to dequeue time.
- **SQLite idempotency** — P7/P1's new table follows the repo's `ALTER TABLE` + try/except convention.
- **Pins survive renames** (BUG-212 rekeying) and **qBittorrent sync on any path change** — untouched by all proposals.
