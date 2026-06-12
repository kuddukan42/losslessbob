# 14 · Pipeline Workspace — Gap Punch-list & Harvest Map

**Scope:** the Pipeline Workspace **per-folder detail panels** — the five stage bodies that
render on the right when you click a folder in the queue (`DetailPanel` in `ScreenPipeline.tsx`).
Everything else CC built on `feat/pipeline-v2-storage-mounts` — the stepper, queue, gating,
buckets, virtualization, i18n, Flask wiring — is **correct. Do not rewrite it.**

> ### The one thing to understand before touching code
> The polished detail **already exists in the repo.** CC built rich **standalone screens**
> (`ScreenVerify`, `ScreenLookup`, `ScreenLBDIR`) as advanced power-tools — *and they stay*
> (the user wants them as advanced tools for now). Those screens, plus their Zustand stores,
> already render every table, picker, and state the design calls for, **and the backend already
> sends the data** (`verifyStore.FileRow[]`, `lookupStore.LookupDetail[]`,
> `lbdirStore.CheckResult/ReconcileResult`).
>
> **The pipeline's stage panels are thin only because they don't reuse that work.** So this is
> overwhelmingly a **frontend extract-and-share** job, *not* a backend buildout and *not* a
> rebuild. Lift the rich render bodies out of the standalone screens into shared components, then
> render those components in both places. **Only the Collect mount picker is genuinely new
> backend work** (that's the whole point of the `storage-mounts` branch).

**Reference design (the polished target):** `_source/pipeline2-stages.jsx` (642 lines) +
`_source/pipeline2-data.js`. Open `Pipeline Workspace (standalone).html` to see every state live.

**Current code:** stage bodies inline in `ScreenPipeline.tsx` — `VerifyStageContent` (L479),
`LookupStageContent` (L603), `RenameStageContent` (L673), `CollectStageContent` (L853), and the
generic fallback used for LBDIR.

---

## 1 · The harvest map (do this, in this order)

Create shared components under `components/pipeline/` and have **both** the standalone screen and
the pipeline detail panel render them. Net new UI written from scratch ≈ one component (Collect).

| New shared component | Lift the body from | Backing store (already populated) | Render in |
|---|---|---|---|
| `VerifyDetail.tsx` | `ScreenVerify.tsx` L361–460 (the Files chip-bar + per-file `TableShell`) | `verifyStore` → `VerifyFolder.files: FileRow[]` | ScreenVerify **and** pipeline Verify panel |
| `LookupDetail.tsx` | `ScreenLookup.tsx` L580–755 (summary table, grouped detail, xref column, not-found hint) | `lookupStore` → `LookupSummary` + `LookupDetail[]` | ScreenLookup **and** pipeline Lookup panel |
| `RenameDetail.tsx` | already inline & good — `ScreenPipeline.tsx` `RenameStageContent` L673 | — | extract so ScreenRename can share it too (optional) |
| `LbdirDetail.tsx` | `ScreenLBDIR.tsx` (CheckResult stat grid + file list + `ReconcileResult` proposals + site/extras) | `lbdirStore` → `CheckResult` + `ReconcileResult` | ScreenLBDIR **and** pipeline LBDIR panel (currently generic fallback) |
| `CollectDetail.tsx` | **NEW** — no standalone equivalent | needs `mounts`/routing (see doc 15) | pipeline Collect panel |

**Why this is safe:** the standalone screens keep working (they render the same shared component),
and the pipeline finally shows the same fidelity. One source of truth per stage.

---

## 2 · What each pipeline panel is missing — and where the fix already lives

Legend: ✅ faithful · ⚠️ partial · ❌ missing · **HARVEST** = the render already exists in a
standalone screen, just reuse it · **NEW** = genuinely new UI.

### 2.1 — VERIFY · panel `VerifyStageContent` L479 · harvest from `ScreenVerify.tsx`

| Element | Pipeline now | Standalone has it? | Action |
|---|---|---|---|
| 5-stat grid | ✅ | — | keep |
| No-checksums → Generate | ⚠️ copy differs | yes | align heading to `"No checksums in this folder yet"` |
| **Per-file table** (Problems/All chips, MD5 exp/act, FFP exp/act, st5, disk, overall) | ❌ | ✅ `ScreenVerify` L361–460 | **HARVEST → `VerifyDetail`** |
| shntool-missing state | ❌ | ✅ `verifyStore` `status:'shntool'` + `tools.shntool_available` | HARVEST the banner |
| Running / hashing progress | ❌ | partial | UI-only; drive width from `pass/total` |
| "Open in Finder" head button | ❌ | yes | UI-only |

The table is the marquee gap (your screenshot 5). It is **fully built** in `ScreenVerify` —
columns, the `Chip active={!showAll}` Problems/All toggle, `Copy report`, per-row `edge` colour,
`StatusDot`, the "showing problems — show all" footer. Data is `row.files` (`FileRow[]`), already
on every verified folder. Extract L361–460 into `VerifyDetail` verbatim, then render it in the
pipeline panel under the stat grid.

### 2.2 — LOOKUP · panel `LookupStageContent` L603 · harvest from `ScreenLookup.tsx`

| Element | Pipeline now | Standalone has it? | Action |
|---|---|---|---|
| Matched hero | ⚠️ no right-side stat / type | partial | add `{matched}/{given}` + category pill |
| **Ambiguous / incomplete picker** | ❌ | ✅ `incomplete` state + `lb_summary` rows | **HARVEST → `LookupDetail`** |
| **Cross-reference (xref)** | ❌ | ✅ `xref` state + `LookupDetail.xref` column (L724) | HARVEST |
| Not-found table + "Mark as new entry" | ⚠️ banner only | ✅ grouped detail + `notFoundHint` (L748) | HARVEST |
| Duplicate state | ❌ | ✅ `duplicate` in `STATE_TONE` | HARVEST |

`ScreenLookup` already models all five states (`matched · incomplete · notfound · duplicate ·
xref`, L14) with the full summary table (Given/Matched/Not-found/Missing/Dups/Xrefs/Status,
L595–624) and the grouped per-checksum detail with the xref check column (L671–726). The pipeline
panel should render `LookupDetail` scoped to the single active folder's LB# group.

### 2.3 — RENAME · panel `RenameStageContent` L673 · ✅ essentially complete

Wrong-LB banner, current→proposed diff with struck-through LB#, inline edit, Copy diff, dry-run +
`rename_history` reversibility, Apply — all present and faithful. **Leave the behaviour.** Optional:
extract into `RenameDetail` so a future `ScreenRename` can share it. Micro-copy nits in §3.

### 2.4 — LBDIR · panel = generic fallback (❌ whole body) · harvest from `ScreenLBDIR.tsx`

Currently `lbdir` steps fall through to the generic `StatusTag + Re-run` fallback, so there is no
stage body at all. Everything needed exists in `lbdirStore` + `ScreenLBDIR`:

- **Stat grid** — `CheckResult.total/pass/mismatch/missing`.
- **File list** — `CheckResult.files: CheckFile[]` (filename, md5_status, on_disk, length, ratio…).
- **Reconcile section** — `ReconcileResult.proposals: {disk_rel→lbdir_rel, md5}[]` with the
  `reconSelected` Set + apply action. (Source `ReconcileSection`, pipeline2-stages L359.)
- **Site / extras section** — `ReconcileResult.site_proposals` + `unmatched_disk` →
  the "move to /extras" UI with `siteSelected`. (Source `ExtrasSection`, L392.)
- States: `pass · fail · missing_files · no_lbdir · no_lb · shntool_missing` (`LbdirState`).

Extract `ScreenLBDIR`'s body into `LbdirDetail`, render it in the pipeline panel, and route
`lbdir` steps to it instead of the fallback.

### 2.5 — COLLECT · panel `CollectStageContent` L853 · **the only genuinely-new build**

No standalone screen exists — this is the `storage-mounts` feature. Build `CollectDetail`:

| Element | Pipeline now | Action |
|---|---|---|
| Staging→final route card | ✅ | keep |
| Error-code state | ✅ (CC added) | keep |
| **Mount-picker grid** (4 mount cards: id · span · free · "suggested", radio-select, year-routed) | ❌ | **NEW** — needs `mounts` + routing, doc 15 |
| Pending "bridge into My Collection" banner | ⚠️ terse | replace copy (§3) |
| "Tag in the collection" table + live item counter | ❌ | NEW (mostly static; counter `+backend`) |
| "What filing does" banner + `File into collection` | ⚠️ | wrap button in the banner |
| Overridden-stages warning | ❌ | UI-only |
| Pass-state detail rows | ⚠️ | add LB#/Mount/Confirmed/Added rows |

Source: `CollectStage` L486–640 + `MOUNTS`/`destPath` in `pipeline2-data.js`. This is the one
place doc 15's backend fields are actually required.

---

## 3 · Exact micro-copy & status-text (match character-for-character)

Stage subtitles (from `steps.<stage>.reason`): Verify `"Checksums vs audio on disk"` · Lookup
`"Identify the LB# in the master DB"` · Rename `"Append the canonical (LB-XXXXX)"` · LBDIR
`"Reconcile the official archive sidecar"` · Collect `"File into final storage & tag in the collection"`.

**Verify** — empty-table banner `"Every file checks out"` / `"All {n} files match their FFP + MD5
checksums. Nothing to fix here."` · blocker `"This is the blocker"` · running `"Hashing files —
{pass} of {total} done. This folder will advance to Lookup automatically."` · shntool `"Can't
decode .shn without shntool"` (button `"Install shntool"`) · Files header static `"Checked: FFP +
MD5"`, chips `"Problems"`/`"All"`, button `"Copy report"`. Generate button `"Generate FFP + MD5"`.

**Lookup** — ambiguous head `"Which show is this?"`, pin button `"Pin {lb} & continue"`, hint
`"Pinning writes folder_lb_link so it never asks again."` · matched flow line `"The match flows
straight into Rename as a confident proposal — no extra step."` · not-found title `"No matches
found"`, right button `"Mark as new entry…"`.

**Rename** (reference) — dry-run title `"Dry-run — nothing changes until you apply"`, `"Copy diff"`,
wrong-LB title `"This folder is mislabeled {wrongLb}"`. Pending heading `"Append the canonical
(LB-XXXXX)"`; applied banner mentions `"reversible from Recent activity for 30 days"`.

**LBDIR** — pending banner title `"Runs after rename"` (button `"Retrieve sidecar now"`) · pass
banner `"Archive-clean"` / `"Every file referenced in the official sidecar is present and matches.
This folder is fully reconciled."` · pass right button `"Open lbdir.txt"`.

**Collect** — pending banner: *"This is the last step — the bridge into **My Collection**. Once the
sidecar reconciles in **LBDIR**, the folder is routed to the right storage mount, moved there, and
tagged as owned. Finish the earlier stages first — or use **Mark complete** on any stage to bypass
the locks and file from here."* · mount label `"Storage mount"`, routed pill `"Routed by year ·
{year} → {mount}"`, `"Reset to suggested"`, `"suggested"` · tag section `"Tag in the collection"`,
counter `"15,967 → 15,968 items"` · filing banner title `"What filing does"`, button `"File into
collection"` · overridden warning: *"One or more pipeline stages were **marked complete** manually
rather than passing on their own. Filing will still move & tag the folder — just double-check it's
the right show."*

**Tooltips (`title=`) to add on icon-only buttons:** `Copy report`/`Copy diff` →
`"Copy to clipboard"` · `Open in Finder`/reveal → `"Reveal folder in Finder"` · LB.com →
`"Open this entry on losslessbob.com"` · mount card → `"{span} · {free} free"` · re-run buttons →
`"Re-run this stage"`.

---

## 4 · Commit order (smallest blast radius first)

1. ✅ **Copy alignment only** — Verify no-checksums heading, Collect pending paragraph + "What filing
   does" banner, Rename wording. Zero backend, zero risk.
2. ✅ **Extract `VerifyDetail`** from `ScreenVerify` L361–460; render in pipeline Verify panel. (HARVEST)
3. ✅ **Extract `LookupDetail`** from `ScreenLookup` L580–755; render scoped to active LB#. (HARVEST)
   — done 2026-06-10. "Mark as new entry…" button (§2.2/§3) deliberately skipped — no backend
   support exists for creating new lb_master entries.
4. ✅ **Extract `LbdirDetail`** from `ScreenLBDIR`; route `lbdir` steps to it. (HARVEST)
   — done 2026-06-10. `LbdirFileTable` (resizable Filename/MD5/Disk/Overall/Length/Fmt/Ratio
   columns) and `ReconcilePanel` (rename proposals, extras, and site/files recovery) harvested
   into `components/pipeline/LbdirDetail.tsx`; the pipeline LBDIR panel (`LbdirStageContent`),
   which previously rendered a truncated 12-row file list and a reconcile block missing the
   site recovery section, now renders the same `<LbdirDetail compact>` as the standalone
   LBDIR screen.
5. ✅ **Build `CollectDetail`** mount picker + tag table. (NEW — see doc 15, the only backend work.)
   — done 2026-06-10. `backend/filer.py` gains `get_mounts_with_stats()` (span/free/online per
   mount) and `mount_id_override` on `resolve_destination_for_lb`/`file_folder`; the file step
   result now carries `mounts`/`recommended_mount`/`routed_year`/`collection_count`;
   `components/pipeline/CollectDetail.tsx` (`MountPicker` + `TagTable`) is rendered by the new
   `CollectReadyDetail` in the pipeline Collect panel, with `/api/pipeline/file/preview`
   re-resolving the route card live when the user picks a different mount.
6. ✅ **Pass-state detail rows, tooltips, Open-in-Finder, running progress.** (polish, UI-only)
   — done 2026-06-10. `backend/app.py` pipeline verify step now handles `shntool_missing` status
   (was falling through to `bad/Mismatch`). `ScreenPipeline.tsx`: `VerifyStageContent` gains a
   "Hashing files…" banner when `step.status === 'mute' && row.running`, and a "Can't decode .shn
   without shntool" warn banner when `step.shntool_missing`. `CollectStageContent` pass state now
   shows LB# and Mount detail rows below the "Added to collection" banner. All re-run/re-check
   buttons gained `title="Re-run this stage"`; Copy diff got `title="Copy to clipboard"`; the
   DetailPanel "Open" button got `title="Reveal folder in Finder"`. Overridden-stages warning
   deliberately skipped — requires "Mark complete" feature not yet implemented.

Steps 2–4 add almost no new code — they move existing, working render bodies into shared
components. Step 5 is the real feature work.
