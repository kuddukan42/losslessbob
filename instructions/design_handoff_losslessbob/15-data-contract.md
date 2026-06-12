# 15 · Pipeline Data Contract — what already exists vs. what's new

Doc 14's earlier draft assumed the rich panels needed new backend fields. **They mostly don't.**
This is the audit. The pixel target is `Pipeline Workspace (standalone).html`; the data to power
it is — with one exception — already flowing to the standalone screens' Zustand stores.

## Already exists — reuse, don't rebuild

| Panel needs | Already in store | Backend already sends it? |
|---|---|---|
| Verify per-file table (md5/ffp expected+actual, st5, disk, overall) | `verifyStore` → `VerifyFolder.files: FileRow[]` | ✅ yes — `ScreenVerify` renders it today |
| Verify shntool state | `verifyStore` `status:'shntool'` + `tools.shntool_available` | ✅ |
| Lookup matched / incomplete / notfound / duplicate / xref | `lookupStore` → `LookupSummary.lb_summary[]` + `LookupDetail[]` (incl. `.xref`, `.lb_category`, `.owned`) | ✅ — `ScreenLookup` renders all five |
| LBDIR stat grid + file list | `lbdirStore` → `CheckResult` (`total/pass/mismatch/missing` + `files: CheckFile[]`) | ✅ |
| LBDIR reconcile moves | `lbdirStore` → `ReconcileResult.proposals: {disk_rel, lbdir_rel, md5}[]` | ✅ |
| LBDIR extras / site moves | `lbdirStore` → `ReconcileResult.site_proposals` + `unmatched_disk` | ✅ |
| Rename proposed name / wrong-LB | already wired in `RenameStageContent` | ✅ |

**Implication:** steps 2–4 of doc 14's commit order are pure frontend. The data is on the row /
in the store the moment a folder has been run through that stage. The pipeline panel just needs to
read the same store the standalone screen reads (or take the row as a prop) and render the shared
component.

## Genuinely new — the Collect mount picker (the `storage-mounts` feature)

This is the only place new backend data is required. The collect/file step needs:

```ts
mounts?: Mount[]            // the picker grid (4 cards in the mock)
recommended_mount?: string  // id of the year-routed suggestion
routed_year?: number        // drives "Routed by year · {year} → {mount}"
collection_count?: number   // drives the "15,967 → 15,968 items" counter (nice-to-have)

interface Mount { id: string; span: string; free: string }
// e.g. { id: "DYLAN4", span: "2010s–2020s · current", free: "6.4 TB" }
```

Routing logic in the mock (`pipeline2-data.js`, `mountForYear`): `≥2010→DYLAN4, ≥1990→DYLAN3,
≥1970→DYLAN2, else DYLAN1, null→DYLAN4`. Mirror the real collection-routing config. The "Tag in the
collection" rows (Status→Public, Owned, Confirmed→today, Fingerprint→queued) are mostly static; only
`collection_count` is a live value and it's optional.

## Notes

- Hashes can stay full-length; the table cells already ellipsis-truncate (`slice(0,12)+'…'` in
  `ScreenVerify`). No payload change needed.
- All Collect fields are optional — folders without them render today's route card unchanged.
- Nothing here changes the happy path or the stores' existing consumers (the standalone screens).

See `_source/pipeline2-data.js` for a complete fixture of every shape; the standalone screens'
stores (`verifyStore.ts`, `lookupStore.ts`, `lbdirStore.ts`) confirm the real fields already exist.
