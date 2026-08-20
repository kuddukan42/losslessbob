# Unrouted Collection Backlog — Work Package

> Created 2026-08-17 · Status: **not started** · Owner: tj
> Audit scripts: `tools/_route_audit.py`, `tools/_route_dryrun.py` (throwaway,
> delete when this package closes). Live plan data: `.debug/unrouted_plan.csv`.

## Scope

`my_collection` rows whose `disk_path` sits outside the routed mount roots
(`collection_mounts` × `collection_routes`). Audit of 2026-08-17: 3,151 total.

| Set | Folders | Decision |
|---|---|---|
| `PRIVATE LB` / `Private Clean Ups`, `status=private` | 1,171 | **Out of scope** — deliberate segregation (tj, 2026-08-17) |
| `PRIVATE LB` / `Private Clean Ups`, `status=ok` | 1,205 | **In scope** — formerly private, now public → move out to the routed public tree (tj, 2026-08-17) |
| `PRIVATE LB`, `status=missing` | 4 | Out of scope — `no_date` anyway |
| `/mnt/DYLAN1/LB HOPPER` | 753 | In scope |
| `/mnt/DYLAN2/LB HOPPER` | 4 | In scope |
| `/mnt/DYLAN2/LK Collections` | 9 | In scope, but **exclude from filing** (see Phase 5) |
| `/mnt/DYLAN1/Double LBs` | 5 | In scope |
| **Total in scope** | **1,976** | 1,968 resolve cleanly, 8 blocked `no_date` |

Payload ≈ 1.36 TB. Every in-scope folder already carries an LB number, exists on
disk, and has **zero** destination collisions against the filed tree. The
now-public set drops its `-NFT` suffix automatically — `build_standard_name`
derives it from `status`, and only 1 of the 1,205 currently has NFT in its name.

## Capacity (the actual constraint)

| Move | Folders | Size | Free at dest | Verdict |
|---|---|---|---|---|
| DYLAN1 → DYLAN1 (same mount) | 338 | 241 GB | n/a | free — rename only |
| DYLAN2 → DYLAN2 (same mount) | 155 | 110 GB | n/a | free — rename only |
| DYLAN1 → DYLAN2 | 70 | 63 GB | 630 GB | fits |
| DYLAN2 → DYLAN1 | 2 | small | 73 GB | fits |
| DYLAN1 → DYLAN3 | 346 | 305 GB | 219 GB | **BLOCKED — short ~90 GB** |
| DYLAN2 → DYLAN1 (now-public) | 1,047 | 599 GB | 73 GB | **BLOCKED — short ~526 GB** |

Cross-mount filing is copy → SHA-256 tree-verify → delete (`filer.hash_tree`),
so the destination needs the full size up front. Moves *off* a mount don't help
the mounts that are short: DYLAN1 is 100% full (73 GB of 7.3 TB) and is the
routed destination for 1,047 of the now-public folders, spread over 29 years
concentrated in 1986–2002.

**Options for the two blocked groups (tj decision, Phase 4):**

1. Add capacity — the only option that preserves one-mount-per-year.
2. Re-point years 1986–2002 (and the DYLAN3-bound years) in `collection_routes`
   to DYLAN2's 630 GB. The 1,047 then become *same-mount* moves — instant, no
   copy, no verify. Cost: those years end up **split across two mounts**, since
   the already-filed folders stay on DYLAN1. Migrating them too is not possible
   (far more than 630 GB).
3. Free ~90 GB on DYLAN3 to unblock that group alone (346 folders), leaving the
   1,047 for option 1 or 2.

---

## Checklist

### Phase 0 — Safety

- [ ] DB backup before the first mutating batch (`backend.db` backup helper).
- [ ] Any ad-hoc staging goes to `/mnt/DATA0/tmp/`, never `/tmp` (CLAUDE.md).
- [ ] `/backend-restart` so the running Flask is the code being driven.

### Phase 1 — Fix the slash-in-name hazard (blocks everything)

- [ ] `build_standard_name` passes `location` through raw; 9 folders repo-wide
      produce canonical names containing `/` (e.g. `1980-01-21 Rainbow Music
      Hall / Denver (LB-00116)`). Neither `/api/folder/rename` nor
      `/api/rename/apply` sanitizes, so a bulk run creates nested dirs.
- [ ] Sanitize in `backend/folder_naming.py` (illegal set: `/ \ : * ? " < > |`).
- [ ] Unit test pinning the 9 known cases.
- [ ] Re-run `tools/_route_dryrun.py`; expect 0 names with illegal chars.

### Phase 2 — Rename in place (~1,974 folders, no capacity risk)

Decoupled from filing on purpose: same-parent renames are instant, audited to
`rename_history`, qbt-synced via `_sync_qbt_location`, and reversible.

- [ ] Driver script feeding `/api/rename/apply` from `.debug/unrouted_plan.csv`,
      batches of ~100, checkpointed to a resume file, **stop on first error**.
- [ ] Batch 1 (100) — spot-check all 100 results by hand before continuing.
- [ ] Verify the now-public batch comes out **without** `-NFT`.
- [ ] Remaining batches to completion.
- [ ] Re-run `tools/_route_audit.py`; expect `rename_needed` → 0 for in-scope.

### Phase 3 — File the unblocked 565

Use `/api/pipeline/file/start` — never ad-hoc `mv`. It carries the guards
(`stale_verify`, `no_date`, `no_route`, `mount_offline`, `dest_exists`), the
hash verification, and the qbt path sync.

- [ ] 338 same-mount DYLAN1 → DYLAN1 (no copy, no space needed).
- [ ] 155 same-mount DYLAN2 → DYLAN2, now-public (no copy).
- [ ] 70 DYLAN1 → DYLAN2 (63 GB into 630 GB free).
- [ ] 2 DYLAN2 → DYLAN1.
- [ ] Re-audit between each group; halt on the first guard failure.

### Phase 4 — Unblock the 1,393 that don't fit

- [ ] **Decision required (tj):** pick option 1, 2, or 3 above.
- [ ] 346 DYLAN1 → DYLAN3 (needs ~90 GB freed on DYLAN3, or a re-route).
- [ ] 1,047 DYLAN2 → DYLAN1 now-public (needs ~526 GB, or re-route to DYLAN2).
- [ ] File per year, one year at a time, re-auditing between years.

### Phase 5 — Exclusions and stragglers

- [ ] 9 `LK Collections` folders are nested *inside* DVD-set directories
      (e.g. `.../bd1980 Leg 1 DVD 1/...`); filing them breaks the sets.
      Recommend leaving in place — needs tj sign-off either way.
- [ ] 8 `no_date` folders (5 hopper + 3 now-public) — manual dating, then
      re-run Phase 2/3 for them.

### Phase 6 — Close-out

- [ ] Integrity-monitor scan on every touched mount.
- [ ] `tools/_route_audit.py` final run: in-scope unrouted count → 0
      (excluding the deliberate private set + signed-off exclusions).
- [ ] Confirm the 1,171 `status=private` folders are untouched and still in
      `PRIVATE LB` / `Private Clean Ups`.
- [ ] Delete `tools/_route_audit.py`, `tools/_route_dryrun.py`.
- [ ] `/session-close` — CHANGELOG, ledger moves.

---

## Open questions for tj

1. **Canonical renames for the remaining private folders** — the 1,171
   `status=private` folders staying in place are also non-canonical. Renaming
   them in place (keeping `-NFT`, keeping the location) is independent of
   routing and carries the same low risk as Phase 2. Do it or leave it?
2. **Ongoing drift** — nothing currently moves a folder out of `PRIVATE LB`
   when its `lb_status` flips private → public. Worth a recurring audit or a
   hook on the status change, else this backlog rebuilds.
